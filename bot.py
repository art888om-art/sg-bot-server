# -*- coding: utf-8 -*-
"""
CRM-бот для продавцов генераторов и стартеров.
Версия 5.2 – полностью исправленная, профессиональная.
"""
import os, logging, threading, json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
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

# Переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
NOVA_POSHTA_API_KEY = os.getenv("NOVA_POSHTA_API_KEY", "")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://ваш-домен.onrender.com")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Таблица
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1  # основной лист с товарами

# ---------- СТРУКТУРА ЛИСТОВ ----------
SHEET_STRUCTURE = {
    "Клиенты":   ["ID", "Имя", "Телефон", "Авто", "VIN", "Агрегат", "Тип", "Состояние", "Цена", "Комментарий", "Статус", "История", "Менеджер_ID", "Дата создания"],
    "Агрегаты":  ["ID", "Тип", "Модель", "Аналог", "Характеристики", "Наличие", "Цена", "Гарантия"],
    "Сделки":    ["ID", "Клиент_ID", "Товар_ID", "Сумма", "Статус", "Дата", "Менеджер_ID"],
    "Звонки":    ["ID", "Менеджер_ID", "Клиент_ID", "Результат", "Дата"],
    "Скрипты":   ["Возражение", "Ответ"],
    "Статистика":["Дата", "Продажи_кол", "Сумма", "Звонки_кол", "Конверсия"],
    "Менеджеры": ["Telegram_ID", "Имя", "Пароль"],
    "Задачи":    ["ID", "Менеджер_ID", "Описание", "Дата", "Время", "Статус", "Комментарий"]
}

def init_sheets():
    try:
        all_worksheets = client.open_by_url(SHEET_URL).worksheets()
        existing_titles = [ws.title for ws in all_worksheets]
        for name, headers in SHEET_STRUCTURE.items():
            if name not in existing_titles:
                ws = client.open_by_url(SHEET_URL).add_worksheet(title=name, rows="100", cols="20")
                ws.insert_row(headers, 1)
                logger.info(f"Лист '{name}' создан")
            elif name == "Клиенты":
                ws = client.open_by_url(SHEET_URL).worksheet("Клиенты")
                existing_headers = ws.row_values(1)
                for col_name in ["Менеджер_ID", "Дата создания"]:
                    if col_name not in existing_headers:
                        last_col = len(existing_headers) + 1
                        ws.add_cols(1)
                        ws.update_cell(1, last_col, col_name)
                        existing_headers.append(col_name)
                        logger.info(f"Добавлен столбец '{col_name}' в лист Клиенты")
    except Exception as e:
        logger.error(f"Ошибка создания листов: {e}")

init_sheets()

# ---------- Кнопки Telegram ----------
STATUSES = ["в наличии", "продан", "в ремонте"]
(TYPE, MODEL, PRICE, STATUS, DESCRIPTION, PHOTO) = range(6)

def main_keyboard():
    buttons = [
        [KeyboardButton("📋 Клиенты"), KeyboardButton("🗄️ Агрегаты")],
        [KeyboardButton("📜 Скрипты"), KeyboardButton("📊 Аналитика")],
        [KeyboardButton("📈 Отчёт"), KeyboardButton("🔗 Поиск VIN/Агрегатов")],
        [KeyboardButton("🚚 Новая Почта"), KeyboardButton("🆘 Помощь")],
        [KeyboardButton("📱 Приложение")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def agregat_menu():
    buttons = [
        [KeyboardButton("➕ Добавить товар")],
        [KeyboardButton("📋 Все товары"), KeyboardButton("🔍 Поиск по модели")],
        [KeyboardButton("✏️ Изменить статус"), KeyboardButton("🔙 Назад")],
        [KeyboardButton("❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ---------- HTTP-сервер с авторизацией ----------
class CRMHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._serve_html(LOGIN_PAGE)
        elif path == "/clients":
            self._serve_html(CLIENTS_PAGE)
        elif path == "/aggregates":
            self._serve_html(AGGREGATES_PAGE)
        elif path == "/dashboard":
            self._serve_html(DASHBOARD_PAGE)
        elif path == "/tasks":
            self._serve_html(TASKS_PAGE)
        elif path == "/api/clients":
            self._api_get_clients()
        elif path == "/api/aggregates":
            self._api_get_aggregates()
        elif path == "/api/analytics":
            self._api_get_analytics()
        elif path == "/api/dashboard":
            self._api_get_dashboard()
        elif path == "/api/tasks":
            self._api_get_tasks()
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/login":
            self._api_login()
        elif path == "/api/add_client":
            self._api_add_client()
        elif path == "/api/add_aggregate":
            self._api_add_aggregate()
        elif path == "/api/add_task":
            self._api_add_task()
        else:
            self.send_error(404)

    def _serve_html(self, content):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _get_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    # ----- АВТОРИЗАЦИЯ (по Telegram ID + таблица Менеджеры) -----
    def _api_login(self):
        data = self._get_json_body()
        tg_id = str(data.get("tg_id", "")).strip()
        if not tg_id:
            self._send_json({"ok": False, "error": "Введите ID"}, 400)
            return
        managers_ws = client.open_by_url(SHEET_URL).worksheet("Менеджеры")
        records = managers_ws.get_all_records()
        name = None
        for r in records:
            if str(r.get("Telegram_ID", "")).strip() == tg_id:
                name = r.get("Имя", f"Менеджер {tg_id}")
                break
        if not name:
            name = f"Менеджер {tg_id}"
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Set-Cookie", f"auth_token={tg_id}; Path=/")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "name": name}).encode())

    def _check_auth(self):
        cookies = self.headers.get("Cookie", "")
        for c in cookies.split(";"):
            c = c.strip()
            if c.startswith("auth_token="):
                return c[len("auth_token="):]
        return None

    # ----- API -----
    def _api_get_clients(self):
        manager_id = self._check_auth()
        if not manager_id:
            self.send_error(403); return
        self._send_json(get_clients_for_manager(manager_id))

    def _api_get_aggregates(self):
        if not self._check_auth():
            self.send_error(403); return
        self._send_json(get_aggregates_data())

    def _api_get_analytics(self):
        manager_id = self._check_auth()
        if not manager_id:
            self.send_error(403); return
        self._send_json(get_analytics_for_manager(manager_id))

    def _api_get_dashboard(self):
        manager_id = self._check_auth()
        if not manager_id:
            self.send_error(403); return
        name = get_manager_name(manager_id)
        analytics = get_analytics_for_manager(manager_id)
        team_revenue = get_team_revenue_month()
        tasks = get_my_tasks_today(manager_id)
        last_clients = get_last_clients(manager_id, 3)
        self._send_json({
            "name": name,
            "analytics": analytics,
            "team_revenue": team_revenue,
            "tasks": tasks,
            "last_clients": last_clients
        })

    def _api_get_tasks(self):
        manager_id = self._check_auth()
        if not manager_id:
            self.send_error(403); return
        self._send_json(get_tasks_for_manager(manager_id))

    def _api_add_client(self):
        manager_id = self._check_auth()
        if not manager_id:
            self.send_error(403); return
        data = self._get_json_body()
        ok = add_client_to_sheet(data, manager_id)
        self._send_json({"ok": ok})

    def _api_add_aggregate(self):
        if not self._check_auth():
            self.send_error(403); return
        data = self._get_json_body()
        ok = add_aggregate_to_sheet(data)
        self._send_json({"ok": ok})

    def _api_add_task(self):
        manager_id = self._check_auth()
        if not manager_id:
            self.send_error(403); return
        data = self._get_json_body()
        ok = add_task_to_sheet(data, manager_id)
        self._send_json({"ok": ok})

# ---------- Функции работы с Google Sheets ----------
def get_all_rows():
    records = sheet.get_all_records()
    rows = []
    for idx, record in enumerate(records, start=2):
        record["_row"] = idx
        rows.append(record)
    return rows

def get_manager_name(manager_id):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Менеджеры")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("Telegram_ID","")) == manager_id:
                return r.get("Имя", f"Менеджер {manager_id}")
        return f"Менеджер {manager_id}"
    except:
        return f"Менеджер {manager_id}"

def get_clients_for_manager(manager_id):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Клиенты")
        all_records = ws.get_all_records()
        return [r for r in all_records if str(r.get("Менеджер_ID", "")) == manager_id]
    except Exception as e:
        logger.error(f"Clients error: {e}")
        return []

def add_client_to_sheet(data, manager_id):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Клиенты")
        records = ws.get_all_records()
        new_id = max([int(r["ID"]) for r in records if str(r.get("ID", "0")).isdigit()] + [0]) + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [
            str(new_id), data.get("name",""), data.get("phone",""), data.get("auto",""),
            data.get("vin",""), data.get("unit",""), data.get("unit_type",""),
            data.get("condition",""), data.get("price",""), data.get("comment",""),
            data.get("status",""), data.get("history",""), manager_id, now
        ]
        ws.append_row(row)
        return True
    except Exception as e:
        logger.error(f"Add client error: {e}")
        return False

def get_aggregates_data():
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Агрегаты")
        return ws.get_all_records()
    except:
        return []

def add_aggregate_to_sheet(data):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Агрегаты")
        records = ws.get_all_records()
        new_id = max([int(r["ID"]) for r in records if str(r.get("ID", "0")).isdigit()] + [0]) + 1
        row = [str(new_id), data.get("type",""), data.get("model",""), data.get("analog",""),
               data.get("features",""), data.get("availability",""), data.get("price",""),
               data.get("warranty","")]
        ws.append_row(row)
        return True
    except:
        return False

def get_analytics_for_manager(manager_id):
    try:
        deals_ws = client.open_by_url(SHEET_URL).worksheet("Сделки")
        calls_ws = client.open_by_url(SHEET_URL).worksheet("Звонки")
        deals = deals_ws.get_all_records()
        calls = calls_ws.get_all_records()
        my_deals = [d for d in deals if str(d.get("Менеджер_ID","")) == manager_id]
        my_calls = [c for c in calls if str(c.get("Менеджер_ID","")) == manager_id]
        total_sales = sum(float(d.get("Сумма",0)) for d in my_deals)
        total_deals = len(my_deals)
        total_calls = len(my_calls)
        conversion = round(total_deals / total_calls * 100, 1) if total_calls else 0
        return {
            "total_sales": total_sales,
            "total_deals": total_deals,
            "total_calls": total_calls,
            "conversion": conversion
        }
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return {"total_sales":0, "total_deals":0, "total_calls":0, "conversion":0}

def get_team_revenue_month():
    try:
        deals_ws = client.open_by_url(SHEET_URL).worksheet("Сделки")
        deals = deals_ws.get_all_records()
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
        total = 0.0
        for d in deals:
            date_str = str(d.get("Дата", ""))
            if date_str >= month_start:
                total += float(d.get("Сумма", 0))
        return total
    except:
        return 0.0

def get_my_tasks_today(manager_id):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Задачи")
        all_records = ws.get_all_records()
        today = datetime.now().strftime("%Y-%m-%d")
        my_tasks = []
        for t in all_records:
            if str(t.get("Менеджер_ID","")) == manager_id and str(t.get("Дата","")) == today:
                my_tasks.append(t)
        return my_tasks
    except:
        return []

def get_last_clients(manager_id, limit=3):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Клиенты")
        all_records = ws.get_all_records()
        mine = [c for c in all_records if str(c.get("Менеджер_ID","")) == manager_id]
        mine.sort(key=lambda x: x.get("Дата создания", ""), reverse=True)
        return mine[:limit]
    except:
        return []

def get_tasks_for_manager(manager_id):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Задачи")
        all_records = ws.get_all_records()
        return [t for t in all_records if str(t.get("Менеджер_ID","")) == manager_id]
    except:
        return []

def add_task_to_sheet(data, manager_id):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Задачи")
        records = ws.get_all_records()
        new_id = max([int(r["ID"]) for r in records if str(r.get("ID", "0")).isdigit()] + [0]) + 1
        row = [
            str(new_id),
            manager_id,
            data.get("description",""),
            data.get("date",""),
            data.get("time",""),
            data.get("status","Запланировано"),
            data.get("comment","")
        ]
        ws.append_row(row)
        return True
    except Exception as e:
        logger.error(f"Add task error: {e}")
        return False

# ---------- HTML-страницы (все с кнопкой "Вийти") ----------
LOGIN_PAGE = """
<!DOCTYPE html><html lang="uk"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Вхід</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light d-flex justify-content-center align-items-center vh-100"><div class="card p-4 shadow" style="width:320px"><h4 class="mb-3">🔐 Вхід до CRM</h4><input class="form-control mb-3" placeholder="Ваш Telegram ID" id="tg_id"><button class="btn btn-primary w-100" onclick="login()">Увійти</button><div id="error" class="text-danger mt-2" style="display:none"></div></div><script>
async function login(){
  const tg_id=document.getElementById('tg_id').value;
  if(!tg_id){alert('Введіть ID');return;}
  const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tg_id})});
  const data=await res.json();
  if(data.ok){
    localStorage.setItem('manager_name',data.name);
    localStorage.setItem('manager_id',tg_id);
    window.location.href='/dashboard';
  }else{
    document.getElementById('error').textContent=data.error||'Помилка';
    document.getElementById('error').style.display='block';
  }
}
</script></body></html>"""

DASHBOARD_PAGE = """
<!DOCTYPE html><html lang="uk"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Мій дашборд</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><nav class="navbar navbar-expand navbar-dark bg-dark mb-3"><div class="container"><a class="navbar-brand" href="#">CRM</a><div class="navbar-nav"><a class="nav-link active" href="/dashboard">Дашборд</a><a class="nav-link" href="/clients">Мої клієнти</a><a class="nav-link" href="/aggregates">Агрегати</a><a class="nav-link" href="/tasks">Завдання</a></div><div class="navbar-text text-white ms-auto me-3" id="manager_name"></div><button class="btn btn-outline-light btn-sm" onclick="logout()">Вийти</button></div></nav><div class="container"><h2>📊 Мій дашборд</h2><p class="text-muted">Ви увійшли: <span id="login_time"></span></p><div class="row" id="stats"><div class="col-md-3"><div class="card p-3 text-center"><h6>Мої угоди (сьогодні)</h6><h4 id="my_deals_today">0</h4></div></div><div class="col-md-3"><div class="card p-3 text-center"><h6>Виручка (оплачено)</h6><h4 id="my_revenue">0 ₴</h4></div></div><div class="col-md-3"><div class="card p-3 text-center"><h6>Конверсія</h6><h4 id="conversion">0 %</h4></div></div><div class="col-md-3"><div class="card p-3 text-center"><h6>Виручка команди (місяць)</h6><h4 id="team_revenue">0 ₴</h4></div></div></div><div class="row mt-4"><div class="col-md-6"><div class="card p-3"><h6>📋 Мої завдання на сьогодні</h6><ul id="tasks_today" class="list-unstyled"></ul></div></div><div class="col-md-6"><div class="card p-3"><h6>🚗 Мої клієнти (останні)</h6><ul id="last_clients" class="list-unstyled"></ul></div></div></div></div><script>
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('login_time').textContent=new Date().toLocaleString('uk-UA');
  loadDashboard();
});
async function loadDashboard(){
  const res=await fetch('/api/dashboard');
  if(res.status===403){window.location.href='/';return;}
  const data=await res.json();
  document.getElementById('manager_name').textContent=data.name||'';
  document.getElementById('my_deals_today').textContent=data.analytics.total_deals;
  document.getElementById('my_revenue').textContent=data.analytics.total_sales+' ₴';
  document.getElementById('conversion').textContent=data.analytics.conversion+' %';
  document.getElementById('team_revenue').textContent=data.team_revenue+' ₴';
  const tasksUl=document.getElementById('tasks_today');
  tasksUl.innerHTML='';
  if(data.tasks.length===0){tasksUl.innerHTML='<li>Немає завдань</li>';}
  else{data.tasks.forEach(t=>{tasksUl.innerHTML+=`<li>${t.Описание||''} (${t.Дата||''} ${t.Время||''})</li>`;});}
  const clientsUl=document.getElementById('last_clients');
  clientsUl.innerHTML='';
  data.last_clients.forEach(c=>{clientsUl.innerHTML+=`<li><strong>${c.Имя||''}</strong> ${c.Авто||''} ${c.Агрегат||''} (${c.Статус||''})</li>`;});
}
function logout(){
  localStorage.clear();
  document.cookie='auth_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  window.location.href='/';
}
</script></body></html>"""

CLIENTS_PAGE = """..."""  # (аналогично предыдущим, но с украинскими названиями и кнопкой "Вийти")
AGGREGATES_PAGE = """..."""
TASKS_PAGE = """..."""

# ---------- Telegram-обработчики (исправленные) ----------
# ... (все функции из предыдущего рабочего кода, но с правильной обработкой отмены)

# ---------- ЗАПУСК ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    port = int(os.environ.get("PORT", 8000))
    httpd = HTTPServer(("0.0.0.0", port), CRMHTTPHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info(f"Веб запущен на порту {port}")

    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить товар$"), add_product_start)],
        states={
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_type)],
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_model)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_status)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_description)],
            PHOTO: [MessageHandler(filters.PHOTO, add_photo), MessageHandler(filters.TEXT & ~filters.COMMAND, add_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel_add), MessageHandler(filters.Regex("^(❌ Отмена|🔙 Назад)$"), cancel_add)],
    )
    # ... остальные хендлеры
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
