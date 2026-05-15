# -*- coding: utf-8 -*-
"""
CRM-система для продажи генераторов и стартеров.
Telegram-бот + веб-интерфейс. Версия 15.0 – серверный рендеринг, без ошибок.
"""
import os, logging, threading, json
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler, ContextTypes
)

# ─────────── Настройки ───────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000").rstrip("/")
WEB_PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", SCOPE)
gc = gspread.authorize(creds)

# ─────────── Структура листов ───────────
SHEET_SCHEMA = {
    "Клиенты":   ["ID", "Имя", "Телефон", "Авто", "VIN", "Агрегат", "Тип", "Состояние",
                  "Цена", "Комментарий", "Статус", "История", "Менеджер_ID", "Дата_создания"],
    "Агрегаты":  ["ID", "Тип", "Модель", "Аналог", "Характеристики", "Наличие", "Цена", "Гарантия"],
    "Сделки":    ["ID", "Название", "Клиент_ID", "Товар_ID", "Сумма", "Статус", "Дата", "Менеджер_ID", "Комментарий"],
    "Звонки":    ["ID", "Менеджер_ID", "Клиент_ID", "Результат", "Дата"],
    "Менеджеры": ["Telegram_ID", "Имя", "Роль"],
    "Задачи":    ["ID", "Менеджер_ID", "Описание", "Дата", "Время", "Статус", "Комментарий"],
}

def open_wb():
    return gc.open_by_url(SHEET_URL)

def ws(name: str):
    return open_wb().worksheet(name)

def init_sheets():
    wb = open_wb()
    existing = {ws.title for ws in wb.worksheets()}
    for name, headers in SHEET_SCHEMA.items():
        if name not in existing:
            ws = wb.add_worksheet(title=name, rows=500, cols=len(headers) + 2)
            ws.insert_row(headers, 1)
            logger.info(f"Создан лист: {name}")
        else:
            ws = wb.worksheet(name)
            row1 = ws.row_values(1)
            for h in headers:
                if h not in row1:
                    ws.add_cols(1)
                    ws.update_cell(1, len(row1) + 1, h)
                    row1.append(h)
            if name == "Клиенты":
                for extra in ["Менеджер_ID", "Дата_создания"]:
                    if extra not in row1:
                        ws.add_cols(1)
                        ws.update_cell(1, len(row1) + 1, extra)
                        row1.append(extra)
try:
    init_sheets()
except Exception as e:
    logger.error(f"init_sheets: {e}")

# ─────────── Вспомогательные функции ───────────
def next_id(records: list) -> int:
    ids = []
    for r in records:
        raw = str(r.get("ID", "")).strip()
        if raw.isdigit():
            ids.append(int(raw))
    return max(ids, default=0) + 1

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def today() -> str:
    return date.today().isoformat()

# ── Менеджеры ──
def get_manager_name(mid: str) -> str:
    try:
        for r in ws("Менеджеры").get_all_records():
            if str(r.get("Telegram_ID", "")).strip() == str(mid).strip():
                return r.get("Имя", f"Менеджер #{mid}")
        return f"Менеджер #{mid}"
    except Exception as e:
        logger.error(f"get_manager_name: {e}")
        return f"Менеджер #{mid}"

def register_manager(mid: str, name: str, role: str = "Менеджер"):
    try:
        w = ws("Менеджеры")
        records = w.get_all_records()
        for r in records:
            if str(r.get("Telegram_ID", "")).strip() == str(mid).strip():
                return
        w.append_row([str(mid), name, role])
    except Exception as e:
        logger.error(f"register_manager: {e}")

# ── Клиенты ──
def get_clients(mid: str | None = None) -> list:
    try:
        records = ws("Клиенты").get_all_records()
        if mid:
            return [r for r in records if str(r.get("Менеджер_ID", "")).strip() == str(mid).strip()]
        return records
    except Exception as e:
        logger.error(f"get_clients: {e}")
        return []

# ── Товары (Sheet1) ──
def get_products(search: str = "") -> list:
    try:
        w = open_wb().sheet1
        records = w.get_all_records()
        if search:
            s = search.lower()
            records = [r for r in records if s in str(r.get("Модель", "")).lower() or s in str(r.get("Тип", "")).lower()]
        return records
    except Exception as e:
        logger.error(f"get_products: {e}")
        return []

def add_product(data: dict) -> tuple[bool, int]:
    try:
        w = open_wb().sheet1
        records = w.get_all_records()
        nid = next_id(records)
        w.append_row([
            str(nid), data.get("type", ""), data.get("model", ""),
            data.get("price", ""), data.get("status", "в наличии"),
            data.get("description", ""), data.get("photo_id", "")
        ])
        return True, nid
    except Exception as e:
        logger.error(f"add_product: {e}")
        return False, 0

# ── Агрегаты ──
def get_aggregates(search: str = "") -> list:
    try:
        records = ws("Агрегаты").get_all_records()
        if search:
            s = search.lower()
            records = [r for r in records if s in str(r.get("Модель", "")).lower() or s in str(r.get("Тип", "")).lower()]
        return records
    except Exception as e:
        logger.error(f"get_aggregates: {e}")
        return []

# ── Сделки ──
def get_deals(mid: str | None = None) -> list:
    try:
        records = ws("Сделки").get_all_records()
        if mid:
            return [r for r in records if str(r.get("Менеджер_ID", "")).strip() == str(mid).strip()]
        return records
    except Exception as e:
        logger.error(f"get_deals: {e}")
        return []

# ── Задачи ──
def get_tasks(mid: str | None = None, only_today: bool = False) -> list:
    try:
        records = ws("Задачи").get_all_records()
        if mid:
            records = [r for r in records if str(r.get("Менеджер_ID", "")).strip() == str(mid).strip()]
        if only_today:
            t = today()
            records = [r for r in records if r.get("Дата", "") == t]
        return records
    except Exception as e:
        logger.error(f"get_tasks: {e}")
        return []

# ── Аналитика ──
def get_analytics(mid: str | None = None) -> dict:
    try:
        deals = get_deals(mid)
        total_rev = sum(float(str(d.get("Сумма", 0)).replace(",", ".") or 0) for d in deals)
        count = len(deals)
        try:
            calls_all = ws("Звонки").get_all_records()
            calls = len([c for c in calls_all if not mid or str(c.get("Менеджер_ID", "")) == str(mid)])
        except Exception:
            calls = 0
        conversion = round(count / calls * 100, 1) if calls > 0 else 0
        month_prefix = datetime.now().strftime("%Y-%m")
        month_deals = [d for d in deals if str(d.get("Дата", "")).startswith(month_prefix)]
        month_rev = sum(float(str(d.get("Сумма", 0)).replace(",", ".") or 0) for d in month_deals)
        return {
            "total_revenue": round(total_rev, 2),
            "total_deals": count,
            "total_calls": calls,
            "conversion": conversion,
            "month_revenue": round(month_rev, 2),
            "month_deals": len(month_deals),
        }
    except Exception as e:
        logger.error(f"get_analytics: {e}")
        return {"total_revenue": 0, "total_deals": 0, "total_calls": 0,
                "conversion": 0, "month_revenue": 0, "month_deals": 0}

def get_dashboard(mid: str) -> dict:
    name = get_manager_name(mid)
    analytics = get_analytics(mid)
    team_analytics = get_analytics()
    tasks_today = get_tasks(mid, only_today=True)
    last_clients = get_clients(mid)[-5:]
    return {
        "name": name,
        "analytics": analytics,
        "team_month_revenue": team_analytics["month_revenue"],
        "team_month_deals": team_analytics["month_deals"],
        "tasks_today": tasks_today,
        "last_clients": last_clients,
    }

# ─────────── HTML-шаблоны (с серверной подстановкой) ───────────
_STYLE = """<style>
:root{--primary:#1e3a5f;--accent:#f97316;--bg:#f1f5f9;--card:#fff;--text:#1e293b;--muted:#64748b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
a{color:var(--accent);text-decoration:none}
.btn{display:inline-flex;align-items:center;padding:10px 20px;border-radius:8px;border:none;cursor:pointer;font-weight:600}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#e0650f}
.card{background:var(--card);border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.badge-green{background:#dcfce7;color:#166534}
.badge-yellow{background:#fef9c3;color:#854d0e}
.badge-blue{background:#dbeafe;color:#1e40af}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:8px 12px;background:#f8fafc;color:var(--muted);font-weight:600}
td{padding:8px 12px;border-bottom:1px solid #e2e8f0}
</style>"""

LOGIN_PAGE = _STYLE + """
<div style="display:flex;justify-content:center;align-items:center;min-height:100vh;background:linear-gradient(135deg,#1e3a5f,#0f172a)">
  <div class="card" style="width:360px;text-align:center">
    <h1 style="color:var(--primary)">⚡ CRM Агрегати</h1>
    <p style="color:var(--muted);margin:12px 0 24px">Стартери & Генератори</p>
    <input type="text" id="tg_id" placeholder="Ваш Telegram ID" style="width:100%;padding:10px;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:12px;font-size:14px">
    <button class="btn btn-primary" onclick="login()" style="width:100%">Войти</button>
    <div id="err" style="color:red;margin-top:8px;font-size:13px"></div>
  </div>
</div>
<script>
async function login(){
  const tg = document.getElementById('tg_id').value.trim();
  if(!tg) { document.getElementById('err').textContent='Введите ID'; return; }
  const r = await fetch('/api/login', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({tg_id: tg})
  });
  const d = await r.json();
  if(d.ok) {
    window.location.href = '/dashboard';
  } else {
    document.getElementById('err').textContent = d.error || 'Ошибка';
  }
}
</script>
"""

def build_dashboard(mid: str) -> str:
    d = get_dashboard(mid)
    name = d["name"]
    a = d["analytics"]
    team_rev = d["team_month_revenue"]
    tasks_today = d["tasks_today"]
    last_clients = d["last_clients"]

    def badge(status):
        if status in ("Оплачено","Выполнено","в наличии"): return "badge-green"
        if status in ("Новый","Переговоры","Новая","Запланировано"): return "badge-blue"
        return "badge-yellow"

    tasks_html = ""
    if tasks_today:
        for t in tasks_today:
            tasks_html += f'<tr><td>{t.get("Описание","")}</td><td>{t.get("Время","")}</td><td><span class="badge {badge(t.get("Статус",""))}">{t.get("Статус","")}</span></td></tr>'
    else:
        tasks_html = '<tr><td colspan="3" style="color:var(--muted)">Нет задач на сегодня</td></tr>'

    clients_html = ""
    if last_clients:
        for c in last_clients:
            clients_html += f'<tr><td>{c.get("Имя","—")}</td><td>{c.get("Авто","")}</td><td>{c.get("Агрегат","")}</td><td><span class="badge {badge(c.get("Статус",""))}">{c.get("Статус","")}</span></td></tr>'
    else:
        clients_html = '<tr><td colspan="4" style="color:var(--muted)">Нет клиентов</td></tr>'

    return _STYLE + f"""
    <div style="display:flex;min-height:100vh">
      <div style="background:var(--primary);width:250px;color:#fff;padding:20px">
        <h3>⚡ CRM Агрегати</h3>
        <p style="font-size:12px;opacity:0.7">Стартери & Генератори</p>
        <nav style="margin-top:20px;display:flex;flex-direction:column;gap:4px">
          <a href="/dashboard" style="color:#fff;padding:8px;border-radius:6px;background:rgba(255,255,255,0.1)">📊 Дашборд</a>
          <a href="#" style="color:rgba(255,255,255,0.7);padding:8px">🗄️ Агрегаты</a>
          <a href="#" style="color:rgba(255,255,255,0.7);padding:8px">👥 Клиенты</a>
          <a href="#" style="color:rgba(255,255,255,0.7);padding:8px">💰 Сделки</a>
          <a href="#" style="color:rgba(255,255,255,0.7);padding:8px">📝 Задачи</a>
        </nav>
        <div style="margin-top:auto;padding-top:20px;border-top:1px solid rgba(255,255,255,0.2)">
          <p style="font-size:14px">{name}</p>
          <a href="/logout" style="color:rgba(255,255,255,0.7);font-size:12px">Выйти</a>
        </div>
      </div>
      <div style="flex:1;padding:24px">
        <h1 style="margin-bottom:24px">Добро пожаловать, {name} 👋</h1>
        <div class="grid2">
          <div class="card"><div style="color:var(--muted);font-size:13px">Сделок всего</div><div style="font-size:28px;font-weight:700">{a["total_deals"]}</div></div>
          <div class="card"><div style="color:var(--muted);font-size:13px">Выручка всего</div><div style="font-size:28px;font-weight:700">{a["total_revenue"]} ₴</div></div>
          <div class="card"><div style="color:var(--muted);font-size:13px">Конверсия</div><div style="font-size:28px;font-weight:700">{a["conversion"]}%</div></div>
          <div class="card"><div style="color:var(--muted);font-size:13px">Выручка команды (мес)</div><div style="font-size:28px;font-weight:700">{team_rev} ₴</div></div>
        </div>
        <div class="grid2" style="grid-template-columns:1fr 1fr">
          <div class="card">
            <h3 style="margin-bottom:12px">📋 Задачи на сегодня</h3>
            <table>{tasks_html}</table>
          </div>
          <div class="card">
            <h3 style="margin-bottom:12px">🚗 Последние клиенты</h3>
            <table><tr><th>Имя</th><th>Авто</th><th>Агрегат</th><th>Статус</th></tr>{clients_html}</table>
          </div>
        </div>
      </div>
    </div>
    """

# ─────────── HTTP-сервер ───────────
class CRMHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0]
        mid = self._auth()
        if p == "/":
            if mid:
                self._html(build_dashboard(mid))
            else:
                self._html(LOGIN_PAGE)
        elif p == "/dashboard":
            if not mid:
                self._redirect("/")
            else:
                self._html(build_dashboard(mid))
        elif p == "/logout":
            self._redirect("/")
        elif p == "/api/managers":
            self._json(ws("Менеджеры").get_all_records())
        else:
            self.send_error(404)

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._body()
        mid = self._auth()
        if p == "/api/login":
            self._login(body)
        else:
            self.send_error(404)

    def _html(self, content):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data, status=200):
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _redirect(self, location):
        self.send_response(302); self.send_header("Location", location); self.end_headers()

    def _auth(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if "auth_token=" in part.strip():
                return part.strip().split("=")[-1]
        return None

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length))
        except: return {}

    def _login(self, data):
        tg_id = str(data.get("tg_id", "")).strip()
        if not tg_id:
            self._json({"ok": False, "error": "Введите ID"}, 400)
            return
        register_manager(tg_id, "Менеджер")
        mname = get_manager_name(tg_id)
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", f"auth_token={tg_id}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "name": mname}, ensure_ascii=False).encode())

# ─────────── Telegram-бот ───────────
T_TYPE, T_MODEL, T_PRICE, T_STATUS, T_DESCRIPTION, T_PHOTO = range(6)
PRODUCT_STATUSES = ["в наличии", "продан", "в ремонте"]

def kb_main():
    return ReplyKeyboardMarkup([
        ["📋 Клиенты", "🗄️ Агрегаты"],
        ["📜 Скрипты", "📊 Аналитика"],
        ["🔗 Поиск", "🚚 Нова Пошта"],
        ["📱 Веб-приложение", "🆘 Помощь"],
    ], resize_keyboard=True)

def kb_agregat():
    return ReplyKeyboardMarkup([
        ["➕ Добавить товар", "📋 Все товары"],
        ["🔍 Поиск товара", "✏️ Изменить статус"],
        ["🔙 Назад", "❌ Отмена"],
    ], resize_keyboard=True)

def kb_cancel():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

async def _cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=kb_main())
    return ConversationHandler.END

def _is_cancel(text):
    return text.strip() in ("❌ Отмена", "🔙 Назад", "/cancel")

async def cmd_start(update, context):
    user = update.effective_user
    name = user.full_name or f"Пользователь #{user.id}"
    register_manager(str(user.id), name)
    await update.message.reply_text(f"👋 Привет, *{name}*!\n\nДобро пожаловать в AutoCRM!", parse_mode="Markdown", reply_markup=kb_main())

async def cmd_help(update, context):
    await update.message.reply_text("🆘 *Справка*\n\n📋 *Клиенты* — база в веб\n🗄️ *Агрегаты* — склад\n📜 *Скрипты* — ответы на возражения\n📊 *Аналитика* — дашборд\n🔗 *Поиск* — Avto.pro, Exist.ua\n🚚 *Нова Пошта* — трекинг\n📱 *Веб-приложение* — открыть CRM", parse_mode="Markdown", reply_markup=kb_main())

async def handle_clients(update, context):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть базу клиентов", web_app=WebAppInfo(url=RENDER_URL + "/clients"))]])
    await update.message.reply_text("📋 Нажмите для открытия:", reply_markup=btn)

async def handle_agregats(update, context):
    await update.message.reply_text("🗄️ Управление агрегатами:", reply_markup=kb_agregat())

async def handle_scripts(update, context):
    await update.message.reply_text("📜 *Скрипты продаж*\n\n🔴 «Дорого» — гарантия 12 мес.\n🔴 «Хочу по месту» — отправим НП за 1-2 дня\n🔴 «Не доверяю отправке» — работаем 5+ лет\n🔴 «Подумаю» — товар в дефиците\n🔴 «Если не подойдёт?» — заменим\n🔴 «Есть ли гарантия?» — да, 12 мес.\n🔴 «Скиньте фото» — сделаем фото/видео", parse_mode="Markdown", reply_markup=kb_main())

async def handle_analytics(update, context):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть дашборд", web_app=WebAppInfo(url=RENDER_URL + "/dashboard"))]])
    mid = str(update.effective_user.id)
    a = get_analytics(mid)
    text = f"📊 *Ваша аналитика*\n💰 Выручка всего: *{a['total_revenue']} ₴*\n💰 За месяц: *{a['month_revenue']} ₴*\n📦 Сделок всего: *{a['total_deals']}*\n📦 За месяц: *{a['month_deals']}*\n📞 Звонков: *{a['total_calls']}*\n🎯 Конверсия: *{a['conversion']}%*"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=btn)

async def handle_search(update, context):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 Avto.pro", url="https://avto.pro/")],
        [InlineKeyboardButton("🔎 Exist.ua", url="https://exist.ua/")],
    ])
    await update.message.reply_text("🔗 Выберите сервис:", reply_markup=btn)

async def handle_nova_poshta(update, context):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Трекинг", url="https://tracking.novaposhta.ua/#/uk")],
        [InlineKeyboardButton("⏱ Срок доставки", url="https://forms.novapost.world/delivery_time/")],
    ])
    await update.message.reply_text("🚚 Нова Пошта:", reply_markup=btn)

async def handle_webapp(update, context):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть CRM", web_app=WebAppInfo(url=RENDER_URL))]])
    await update.message.reply_text("📱 Нажмите кнопку:", reply_markup=btn)

# ── Добавление товара ──
async def prod_start(update, context):
    await update.message.reply_text("Тип товара:", reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"], ["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True))
    return T_TYPE

async def prod_type(update, context):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    if txt not in ("Генератор", "Стартер"):
        await update.message.reply_text("Выберите: Генератор или Стартер")
        return T_TYPE
    context.user_data["p_type"] = txt
    await update.message.reply_text("Введите модель:", reply_markup=kb_cancel())
    return T_MODEL

async def prod_model(update, context):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    context.user_data["p_model"] = txt
    await update.message.reply_text("Цена (грн, число):", reply_markup=kb_cancel())
    return T_PRICE

async def prod_price(update, context):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    if not txt.isdigit():
        await update.message.reply_text("Введите целое число")
        return T_PRICE
    context.user_data["p_price"] = txt
    await update.message.reply_text("Статус:", reply_markup=ReplyKeyboardMarkup([[s] for s in PRODUCT_STATUSES] + [["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True))
    return T_STATUS

async def prod_status(update, context):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    if txt not in PRODUCT_STATUSES:
        await update.message.reply_text("Выберите из предложенных")
        return T_STATUS
    context.user_data["p_status"] = txt
    await update.message.reply_text("Описание (или «нет»):", reply_markup=kb_cancel())
    return T_DESCRIPTION

async def prod_description(update, context):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    context.user_data["p_desc"] = "" if txt.lower() in ("нет", "-", "no") else txt
    await update.message.reply_text("Отправьте фото товара (или «нет»):", reply_markup=kb_cancel())
    return T_PHOTO

async def prod_photo(update, context):
    txt = update.message.text.strip() if update.message.text else ""
    if _is_cancel(txt): return await _cancel(update, context)
    photo_id = ""
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    elif txt.lower() not in ("нет", "-", "no", ""):
        await update.message.reply_text("Отправьте фото или напишите «нет»")
        return T_PHOTO
    d = context.user_data
    ok, nid = add_product({"type": d.get("p_type", ""), "model": d.get("p_model", ""), "price": d.get("p_price", ""), "status": d.get("p_status", "в наличии"), "description": d.get("p_desc", ""), "photo_id": photo_id})
    context.user_data.clear()
    if ok:
        await update.message.reply_text(f"✅ Товар *{d['p_model']}* добавлен (ID {nid})", parse_mode="Markdown", reply_markup=kb_agregat())
    else:
        await update.message.reply_text("❌ Ошибка сохранения", reply_markup=kb_agregat())
    return ConversationHandler.END

# ── Все товары, изменение статуса, поиск ──
async def show_all_products(update, context):
    products = get_products()
    if not products:
        await update.message.reply_text("📭 Склад пуст.", reply_markup=kb_agregat())
        return
    btns = []
    for i, p in enumerate(products[:15]):
        label = f"{p.get('Тип','?')} {p.get('Модель','?')} — {p.get('Цена','')}₴ [{p.get('Статус','')}]"
        btns.append([InlineKeyboardButton(label[:64], callback_data=f"pd_{i}")])
    context.user_data["products_cache"] = products[:15]
    await update.message.reply_text(f"📋 Товаров: *{len(products)}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

async def cb_product_detail(update, context):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split("_")[1])
    products = context.user_data.get("products_cache", [])
    if idx >= len(products):
        await q.edit_message_text("Товар не найден")
        return
    p = products[idx]
    text = f"*{p.get('Тип','')} — {p.get('Модель','')}*\nЦена: *{p.get('Цена','')} ₴*\nСтатус: {p.get('Статус','')}\nОписание: {p.get('Описание','—')}"
    photo = p.get("Фото_ID", "")
    try:
        if photo:
            await context.bot.send_photo(chat_id=q.message.chat_id, photo=photo, caption=text, parse_mode="Markdown")
        else:
            await q.edit_message_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"product detail: {e}")
        await q.edit_message_text(text, parse_mode="Markdown")

async def change_status_start(update, context):
    products = get_products()
    if not products:
        await update.message.reply_text("Нет товаров.")
        return
    btns = [[InlineKeyboardButton(f"{p.get('Тип','?')} {p.get('Модель','?')} [{p.get('Статус','')}]"[:64], callback_data=f"chs_{i}")] for i, p in enumerate(products[:15])]
    context.user_data["products_cache"] = products[:15]
    await update.message.reply_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(btns))

async def cb_change_status_select(update, context):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split("_")[1])
    context.user_data["edit_idx"] = idx
    btns = [[InlineKeyboardButton(s, callback_data=f"sts_{s}")] for s in PRODUCT_STATUSES]
    await q.edit_message_text("Новый статус:", reply_markup=InlineKeyboardMarkup(btns))

async def cb_set_status(update, context):
    q = update.callback_query
    await q.answer()
    new_status = q.data[4:]
    idx = context.user_data.get("edit_idx")
    products = context.user_data.get("products_cache", [])
    if idx is None or idx >= len(products):
        await q.edit_message_text("Ошибка сессии")
        return
    # обновление статуса
    w = open_wb().sheet1
    w.update_cell(idx + 2, 5, new_status)
    await q.edit_message_text(f"✅ Статус изменён на *{new_status}*", parse_mode="Markdown")
    context.user_data.pop("edit_idx", None)

async def search_product_ask(update, context):
    await update.message.reply_text("Введите модель или тип:", reply_markup=kb_cancel())
    context.user_data["awaiting_search"] = True

async def search_product_result(update, context):
    if not context.user_data.get("awaiting_search"):
        return
    txt = update.message.text.strip()
    context.user_data.pop("awaiting_search", None)
    if _is_cancel(txt):
        await update.message.reply_text("Отменено.", reply_markup=kb_agregat())
        return
    results = get_products(search=txt)
    if not results:
        await update.message.reply_text("🔍 Ничего не найдено.", reply_markup=kb_agregat())
        return
    btns = [[InlineKeyboardButton(f"{p.get('Тип','?')} {p.get('Модель','?')} — {p.get('Цена','')}₴"[:64], callback_data=f"pd_{i}")] for i, p in enumerate(results[:10])]
    context.user_data["products_cache"] = results[:10]
    await update.message.reply_text(f"🔍 Найдено: *{len(results)}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(btns))

async def handle_text(update, context):
    txt = update.message.text.strip()
    if txt == "🗄️ Агрегаты":
        await handle_agregats(update, context)
    elif txt == "📋 Клиенты":
        await handle_clients(update, context)
    elif txt == "📜 Скрипты":
        await handle_scripts(update, context)
    elif txt == "📊 Аналитика":
        await handle_analytics(update, context)
    elif txt == "🔗 Поиск":
        await handle_search(update, context)
    elif txt == "🚚 Нова Пошта":
        await handle_nova_poshta(update, context)
    elif txt == "📱 Веб-приложение":
        await handle_webapp(update, context)
    elif txt == "🆘 Помощь":
        await cmd_help(update, context)
    elif txt == "📋 Все товары":
        await show_all_products(update, context)
    elif txt == "✏️ Изменить статус":
        await change_status_start(update, context)
    elif txt == "🔍 Поиск товара":
        await search_product_ask(update, context)
    elif txt in ("🔙 Назад", "❌ Отмена"):
        context.user_data.clear()
        await update.message.reply_text("Главное меню:", reply_markup=kb_main())
    else:
        if context.user_data.get("awaiting_search"):
            await search_product_result(update, context)
        else:
            await update.message.reply_text("Используйте кнопки меню.", reply_markup=kb_main())

# ─────────── Запуск ───────────
def run_web():
    httpd = HTTPServer(("0.0.0.0", WEB_PORT), CRMHandler)
    logger.info(f"Веб-сервер на порту {WEB_PORT}")
    httpd.serve_forever()

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^➕ Добавить товар$"), prod_start)],
        states={
            T_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_type)],
            T_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_model)],
            T_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_price)],
            T_STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_status)],
            T_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_description)],
            T_PHOTO: [MessageHandler(filters.PHOTO, prod_photo), MessageHandler(filters.TEXT & ~filters.COMMAND, prod_photo)],
        },
        fallbacks=[CommandHandler("cancel", _cancel), MessageHandler(filters.Regex(r"^❌ Отмена$"), _cancel)],
        allow_reentry=True,
    )

    app.add_handler(add_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", _cancel))
    app.add_handler(CallbackQueryHandler(cb_product_detail, pattern=r"^pd_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_change_status_select, pattern=r"^chs_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_set_status, pattern=r"^sts_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
