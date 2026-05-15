# -*- coding: utf-8 -*-
"""
CRM-система для продажи генераторов и стартеров.
Telegram-бот + веб-интерфейс. Версия 7.0 — полностью переписанная.

Исправлено:
- Ошибка с _row в gspread (используем enumerate + смещение)
- Авторизация через cookie работает корректно
- ConversationHandler не перехватывает главное меню
- Правильная обработка всех HTTP-методов
- Безопасное чтение данных из таблиц
- Улучшена аналитика и дашборд
"""

import os
import logging
import threading
import json
import re
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
SHEET_URL   = os.getenv("GOOGLE_SHEET_URL", "")
ADMIN_IDS   = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
RENDER_URL  = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000").rstrip("/")
WEB_PORT    = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds  = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", SCOPE)
gc     = gspread.authorize(creds)

# Структура листов
SHEET_SCHEMA = {
    "Клиенты":   ["ID", "Имя", "Телефон", "Авто", "VIN", "Агрегат", "Тип", "Состояние",
                  "Цена", "Комментарий", "Статус", "История", "Менеджер_ID", "Дата_создания"],
    "Агрегаты":  ["ID", "Тип", "Модель", "Аналог", "Характеристики", "Наличие", "Цена", "Гарантия"],
    "Сделки":    ["ID", "Клиент_ID", "Товар_ID", "Сумма", "Статус", "Дата", "Менеджер_ID"],
    "Звонки":    ["ID", "Менеджер_ID", "Клиент_ID", "Результат", "Дата"],
    "Скрипты":   ["Возражение", "Ответ"],
    "Менеджеры": ["Telegram_ID", "Имя", "Роль"],
    "Задачи":    ["ID", "Менеджер_ID", "Описание", "Дата", "Время", "Статус", "Комментарий"],
    "Товары":    ["ID", "Тип", "Модель", "Цена", "Статус", "Описание", "Фото_ID"],
}

def _open_wb():
    return gc.open_by_url(SHEET_URL)

def _ws(name: str):
    return _open_wb().worksheet(name)

def init_sheets():
    wb = _open_wb()
    existing = {ws.title for ws in wb.worksheets()}
    for name, headers in SHEET_SCHEMA.items():
        if name not in existing:
            ws = wb.add_worksheet(title=name, rows=500, cols=len(headers) + 2)
            ws.insert_row(headers, 1)
            logger.info("Создан лист: %s", name)
        else:
            # Добавить недостающие колонки (мягко)
            ws = wb.worksheet(name)
            row1 = ws.row_values(1)
            for h in headers:
                if h not in row1:
                    ws.add_cols(1)
                    ws.update_cell(1, len(row1) + 1, h)
                    row1.append(h)

try:
    init_sheets()
except Exception as exc:
    logger.error("init_sheets: %s", exc)

# ─────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ДАННЫХ
# ─────────────────────────────────────────────
def _next_id(records: list) -> int:
    ids = []
    for r in records:
        raw = str(r.get("ID", "")).strip()
        if raw.isdigit():
            ids.append(int(raw))
    return max(ids, default=0) + 1

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def _today() -> str:
    return date.today().isoformat()

# ── Менеджеры ──
def get_manager_name(mid: str) -> str:
    try:
        for r in _ws("Менеджеры").get_all_records():
            if str(r.get("Telegram_ID", "")).strip() == str(mid).strip():
                return r.get("Имя", f"Менеджер #{mid}")
        return f"Менеджер #{mid}"
    except Exception as e:
        logger.error("get_manager_name: %s", e)
        return f"Менеджер #{mid}"

def register_manager(mid: str, name: str, role: str = "Менеджер"):
    try:
        ws = _ws("Менеджеры")
        records = ws.get_all_records()
        for r in records:
            if str(r.get("Telegram_ID", "")).strip() == str(mid).strip():
                return  # уже есть
        ws.append_row([str(mid), name, role])
    except Exception as e:
        logger.error("register_manager: %s", e)

# ── Клиенты ──
def get_clients(mid: str | None = None) -> list:
    try:
        records = _ws("Клиенты").get_all_records()
        if mid:
            return [r for r in records if str(r.get("Менеджер_ID", "")).strip() == str(mid).strip()]
        return records
    except Exception as e:
        logger.error("get_clients: %s", e)
        return []

def add_client(data: dict, mid: str) -> bool:
    try:
        ws = _ws("Клиенты")
        nid = _next_id(ws.get_all_records())
        ws.append_row([
            str(nid),
            data.get("name", ""),
            data.get("phone", ""),
            data.get("auto", ""),
            data.get("vin", ""),
            data.get("unit", ""),
            data.get("unit_type", ""),
            data.get("condition", ""),
            data.get("price", ""),
            data.get("comment", ""),
            data.get("status", "Новый"),
            data.get("history", ""),
            str(mid),
            _now(),
        ])
        return True
    except Exception as e:
        logger.error("add_client: %s", e)
        return False

def update_client_status(client_id: str, new_status: str, mid: str) -> bool:
    try:
        ws = _ws("Клиенты")
        records = ws.get_all_records()
        for i, r in enumerate(records, start=2):
            if str(r.get("ID", "")) == str(client_id) and str(r.get("Менеджер_ID", "")) == str(mid):
                ws.update_cell(i, 11, new_status)  # колонка Статус (11-я)
                return True
        return False
    except Exception as e:
        logger.error("update_client_status: %s", e)
        return False

def search_clients(query: str, mid: str | None = None) -> list:
    q = query.lower()
    clients = get_clients(mid)
    return [
        c for c in clients
        if q in str(c.get("Имя", "")).lower()
        or q in str(c.get("Телефон", "")).lower()
        or q in str(c.get("VIN", "")).lower()
        or q in str(c.get("Авто", "")).lower()
    ]

# ── Агрегаты ──
def get_aggregates(search: str = "") -> list:
    try:
        records = _ws("Агрегаты").get_all_records()
        if search:
            s = search.lower()
            records = [r for r in records
                       if s in str(r.get("Модель", "")).lower()
                       or s in str(r.get("Тип", "")).lower()
                       or s in str(r.get("Аналог", "")).lower()]
        return records
    except Exception as e:
        logger.error("get_aggregates: %s", e)
        return []

def add_aggregate(data: dict) -> bool:
    try:
        ws = _ws("Агрегаты")
        nid = _next_id(ws.get_all_records())
        ws.append_row([
            str(nid),
            data.get("type", ""),
            data.get("model", ""),
            data.get("analog", ""),
            data.get("features", ""),
            data.get("availability", ""),
            data.get("price", ""),
            data.get("warranty", ""),
        ])
        return True
    except Exception as e:
        logger.error("add_aggregate: %s", e)
        return False

# ── Товары (основной склад) ──
def get_products(search: str = "") -> list:
    try:
        ws = _open_wb().sheet1  # первый лист = Товары
        records = ws.get_all_records()
        if search:
            s = search.lower()
            records = [r for r in records
                       if s in str(r.get("Модель", "")).lower()
                       or s in str(r.get("Тип", "")).lower()]
        return records
    except Exception as e:
        logger.error("get_products: %s", e)
        return []

def add_product(data: dict) -> tuple[bool, int]:
    try:
        ws = _open_wb().sheet1
        records = ws.get_all_records()
        nid = _next_id(records)
        ws.append_row([
            str(nid),
            data.get("type", ""),
            data.get("model", ""),
            data.get("price", ""),
            data.get("status", "в наличии"),
            data.get("description", ""),
            data.get("photo_id", ""),
        ])
        return True, nid
    except Exception as e:
        logger.error("add_product: %s", e)
        return False, 0

def update_product_status(row_index: int, new_status: str) -> bool:
    try:
        ws = _open_wb().sheet1
        ws.update_cell(row_index, 5, new_status)
        return True
    except Exception as e:
        logger.error("update_product_status: %s", e)
        return False

# ── Сделки ──
def get_deals(mid: str | None = None) -> list:
    try:
        records = _ws("Сделки").get_all_records()
        if mid:
            return [r for r in records if str(r.get("Менеджер_ID", "")).strip() == str(mid).strip()]
        return records
    except Exception as e:
        logger.error("get_deals: %s", e)
        return []

def add_deal(data: dict, mid: str) -> bool:
    try:
        ws = _ws("Сделки")
        nid = _next_id(ws.get_all_records())
        ws.append_row([
            str(nid),
            data.get("client_id", ""),
            data.get("product_id", ""),
            data.get("amount", ""),
            data.get("status", "Новая"),
            _now(),
            str(mid),
        ])
        return True
    except Exception as e:
        logger.error("add_deal: %s", e)
        return False

# ── Задачи ──
def get_tasks(mid: str | None = None, only_today: bool = False) -> list:
    try:
        records = _ws("Задачи").get_all_records()
        if mid:
            records = [r for r in records if str(r.get("Менеджер_ID", "")).strip() == str(mid).strip()]
        if only_today:
            today = _today()
            records = [r for r in records if r.get("Дата", "") == today]
        return records
    except Exception as e:
        logger.error("get_tasks: %s", e)
        return []

def add_task(data: dict, mid: str) -> bool:
    try:
        ws = _ws("Задачи")
        nid = _next_id(ws.get_all_records())
        ws.append_row([
            str(nid),
            str(mid),
            data.get("description", ""),
            data.get("date", ""),
            data.get("time", ""),
            data.get("status", "Запланировано"),
            "",
        ])
        return True
    except Exception as e:
        logger.error("add_task: %s", e)
        return False

def update_task(task_id: str, new_status: str, mid: str) -> bool:
    try:
        ws = _ws("Задачи")
        records = ws.get_all_records()
        for i, r in enumerate(records, start=2):
            if str(r.get("ID", "")) == str(task_id) and str(r.get("Менеджер_ID", "")) == str(mid):
                ws.update_cell(i, 6, new_status)
                return True
        return False
    except Exception as e:
        logger.error("update_task: %s", e)
        return False

# ── Аналитика ──
def get_analytics(mid: str | None = None) -> dict:
    try:
        deals = get_deals(mid)
        total_rev = sum(float(str(d.get("Сумма", 0)).replace(",", ".") or 0) for d in deals)
        count = len(deals)
        try:
            calls_all = _ws("Звонки").get_all_records()
            calls = len([c for c in calls_all if not mid or str(c.get("Менеджер_ID", "")) == str(mid)])
        except Exception:
            calls = 0
        conversion = round(count / calls * 100, 1) if calls > 0 else 0
        # Продажи за этот месяц
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
        logger.error("get_analytics: %s", e)
        return {"total_revenue": 0, "total_deals": 0, "total_calls": 0,
                "conversion": 0, "month_revenue": 0, "month_deals": 0}

def get_dashboard(mid: str) -> dict:
    name = get_manager_name(mid)
    analytics = get_analytics(mid)
    # Общая выручка команды за месяц
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

# ─────────────────────────────────────────────
# HTML-СТРАНИЦЫ
# ─────────────────────────────────────────────
_NAV = """
<nav class="navbar">
  <div class="nav-inner">
    <a class="brand" href="/dashboard">⚡ AutoCRM</a>
    <div class="nav-links">
      <a href="/dashboard">Дашборд</a>
      <a href="/clients">Клиенты</a>
      <a href="/aggregates">Агрегаты</a>
      <a href="/deals">Сделки</a>
      <a href="/tasks">Задачи</a>
    </div>
    <div class="nav-right">
      <span id="nav_user"></span>
      <button class="btn-logout" onclick="logout()">Выйти</button>
    </div>
  </div>
</nav>
<script>
document.getElementById('nav_user').textContent = localStorage.getItem('manager_name') || '';
function logout(){
  localStorage.clear();
  document.cookie = 'auth_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  window.location.href = '/';
}
</script>
"""

_BASE_CSS = """
<style>
  :root {
    --bg: #0d0f14;
    --surface: #161922;
    --surface2: #1e2230;
    --border: #2a2f42;
    --accent: #f5a623;
    --accent2: #e85d04;
    --text: #e8eaf0;
    --muted: #6b7280;
    --green: #22c55e;
    --red: #ef4444;
    --blue: #3b82f6;
    --radius: 10px;
    --shadow: 0 4px 24px rgba(0,0,0,0.4);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }
  a { color: var(--accent); text-decoration: none; }
  
  /* Navbar */
  .navbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0 24px; position: sticky; top: 0; z-index: 100; }
  .nav-inner { display: flex; align-items: center; height: 56px; gap: 24px; }
  .brand { font-size: 18px; font-weight: 700; color: var(--accent); letter-spacing: -0.5px; }
  .nav-links { display: flex; gap: 4px; flex: 1; }
  .nav-links a { padding: 6px 14px; border-radius: 6px; color: var(--muted); font-size: 14px; transition: all 0.2s; }
  .nav-links a:hover, .nav-links a.active { background: var(--surface2); color: var(--text); }
  .nav-right { display: flex; align-items: center; gap: 12px; }
  #nav_user { color: var(--muted); font-size: 13px; }
  .btn-logout { background: transparent; border: 1px solid var(--border); color: var(--muted); padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
  .btn-logout:hover { border-color: var(--red); color: var(--red); }

  /* Layout */
  .container { max-width: 1280px; margin: 0 auto; padding: 28px 24px; }
  .page-title { font-size: 22px; font-weight: 700; margin-bottom: 20px; color: var(--text); }
  
  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
  .card-header { font-size: 13px; color: var(--muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
  .card-value { font-size: 28px; font-weight: 700; color: var(--text); }
  .card-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
  
  /* Stats grid */
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  
  /* Buttons */
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 7px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s; }
  .btn-primary { background: var(--accent); color: #000; }
  .btn-primary:hover { background: #e09520; }
  .btn-success { background: var(--green); color: #000; }
  .btn-success:hover { filter: brightness(0.9); }
  .btn-danger { background: var(--red); color: #fff; }
  .btn-danger:hover { filter: brightness(0.9); }
  .btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { border-color: var(--accent); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  
  /* Table */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: var(--surface2); color: var(--muted); text-align: left; padding: 10px 14px; font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  td { padding: 10px 14px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.02); }

  /* Badge */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
  .badge-yellow { background: rgba(245,166,35,0.15); color: var(--accent); }
  .badge-red { background: rgba(239,68,68,0.15); color: var(--red); }
  .badge-blue { background: rgba(59,130,246,0.15); color: var(--blue); }
  .badge-gray { background: rgba(107,114,128,0.15); color: var(--muted); }

  /* Form */
  .form-section { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 20px; display: none; }
  .form-section.open { display: block; }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
  .form-group { display: flex; flex-direction: column; gap: 5px; }
  label { font-size: 12px; color: var(--muted); }
  input, select, textarea { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 8px 12px; font-size: 13px; outline: none; transition: border-color 0.2s; width: 100%; }
  input:focus, select:focus, textarea:focus { border-color: var(--accent); }
  select option { background: var(--surface2); }
  .form-actions { margin-top: 16px; display: flex; gap: 8px; }

  /* Search bar */
  .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
  .search-input { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 8px 14px; border-radius: 7px; font-size: 13px; outline: none; min-width: 240px; }
  .search-input:focus { border-color: var(--accent); }

  /* Dashboard widgets */
  .widgets-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 24px; }
  .widget { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
  .widget h3 { font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; }
  .task-item { padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
  .task-item:last-child { border-bottom: none; }
  .client-item { padding: 8px 0; border-bottom: 1px solid var(--border); }
  .client-item:last-child { border-bottom: none; }
  .client-name { font-weight: 600; font-size: 13px; }
  .client-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }

  /* Toast */
  #toast { position: fixed; bottom: 24px; right: 24px; padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 500; display: none; z-index: 9999; }
  #toast.success { background: var(--green); color: #000; }
  #toast.error { background: var(--red); color: #fff; }

  /* Login */
  .login-wrap { display: flex; justify-content: center; align-items: center; min-height: 100vh; }
  .login-card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 40px; width: 360px; text-align: center; }
  .login-card h1 { font-size: 24px; margin-bottom: 6px; }
  .login-card p { color: var(--muted); font-size: 14px; margin-bottom: 28px; }
  .login-card input { margin-bottom: 12px; }
  .login-card .btn { width: 100%; justify-content: center; }
  .login-logo { font-size: 48px; margin-bottom: 16px; }

  @media (max-width: 768px) {
    .widgets-row { grid-template-columns: 1fr; }
    .nav-links { display: none; }
    .form-grid { grid-template-columns: 1fr; }
  }
</style>
<script>
function toast(msg, type='success'){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = type;
  t.style.display = 'block';
  setTimeout(()=>{ t.style.display='none'; }, 3000);
}
function statusBadge(s){
  const map = {
    'Новый':'badge-blue','В обработке':'badge-yellow','Закрыт':'badge-gray',
    'в наличии':'badge-green','продан':'badge-red','в ремонте':'badge-yellow',
    'Новая':'badge-blue','Выполнено':'badge-green','Просрочено':'badge-red',
    'Запланировано':'badge-yellow','Закрыта':'badge-gray',
  };
  const cls = map[s] || 'badge-gray';
  return `<span class="badge ${cls}">${s}</span>`;
}
</script>
<div id="toast"></div>
"""

LOGIN_PAGE = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoCRM — Вход</title>{_BASE_CSS}</head><body>
<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo">⚡</div>
    <h1>AutoCRM</h1>
    <p>CRM для продажи генераторов и стартеров</p>
    <input type="text" id="tg_id" placeholder="Ваш Telegram ID" />
    <input type="text" id="name_inp" placeholder="Ваше имя (первый вход)" />
    <button class="btn btn-primary" onclick="doLogin()">Войти</button>
    <div id="err" style="color:var(--red);font-size:13px;margin-top:12px;"></div>
  </div>
</div>
<script>
async function doLogin(){{
  const tg_id = document.getElementById('tg_id').value.trim();
  const name = document.getElementById('name_inp').value.trim();
  if(!tg_id){{ document.getElementById('err').textContent='Введите Telegram ID'; return; }}
  const res = await fetch('/api/login', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{tg_id, name}})}});
  const data = await res.json();
  if(data.ok){{
    localStorage.setItem('manager_name', data.name);
    localStorage.setItem('manager_id', tg_id);
    window.location.href = '/dashboard';
  }} else {{
    document.getElementById('err').textContent = data.error || 'Ошибка';
  }}
}}
document.addEventListener('keydown', e => {{ if(e.key==='Enter') doLogin(); }});
</script>
</body></html>"""

DASHBOARD_PAGE = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Дашборд — AutoCRM</title>{_BASE_CSS}</head><body>
{_NAV}
<div class="container">
  <div class="page-title">Добро пожаловать, <span id="greet_name">...</span> 👋</div>
  <div class="stats-grid">
    <div class="card"><div class="card-header">Сделок всего</div><div class="card-value" id="s_deals">—</div><div class="card-sub">все время</div></div>
    <div class="card"><div class="card-header">Выручка всего</div><div class="card-value" id="s_rev">—</div><div class="card-sub">₴</div></div>
    <div class="card"><div class="card-header">Сделок за месяц</div><div class="card-value" id="s_m_deals">—</div><div class="card-sub">текущий месяц</div></div>
    <div class="card"><div class="card-header">Выручка за месяц</div><div class="card-value" id="s_m_rev">—</div><div class="card-sub">₴</div></div>
    <div class="card"><div class="card-header">Звонков</div><div class="card-value" id="s_calls">—</div><div class="card-sub">Конверсия: <span id="s_conv">—</span>%</div></div>
    <div class="card" style="border-color:var(--accent)"><div class="card-header">Выручка команды (месяц)</div><div class="card-value" id="s_team">—</div><div class="card-sub">₴ / <span id="s_team_deals">—</span> сделок</div></div>
  </div>
  <div class="widgets-row">
    <div class="widget"><h3>📋 Задачи на сегодня</h3><div id="w_tasks">Загрузка...</div></div>
    <div class="widget"><h3>🚗 Последние клиенты</h3><div id="w_clients">Загрузка...</div></div>
  </div>
</div>
<script>
async function load(){{
  const res = await fetch('/api/dashboard');
  if(res.status===403){{ window.location.href='/'; return; }}
  const d = await res.json();
  document.getElementById('greet_name').textContent = d.name;
  document.getElementById('nav_user').textContent = d.name;
  const a = d.analytics;
  document.getElementById('s_deals').textContent = a.total_deals;
  document.getElementById('s_rev').textContent = a.total_revenue.toLocaleString('uk-UA');
  document.getElementById('s_m_deals').textContent = a.month_deals;
  document.getElementById('s_m_rev').textContent = a.month_revenue.toLocaleString('uk-UA');
  document.getElementById('s_calls').textContent = a.total_calls;
  document.getElementById('s_conv').textContent = a.conversion;
  document.getElementById('s_team').textContent = d.team_month_revenue.toLocaleString('uk-UA');
  document.getElementById('s_team_deals').textContent = d.team_month_deals;
  const tasks = d.tasks_today;
  document.getElementById('w_tasks').innerHTML = tasks.length === 0 ? '<p style="color:var(--muted);font-size:13px">Нет задач на сегодня</p>' :
    tasks.map(t=>`<div class="task-item"><b>${{t.Описание||''}}</b> <span style="color:var(--muted)">${{t.Время||''}}</span> ${{statusBadge(t.Статус)}}</div>`).join('');
  const clients = d.last_clients;
  document.getElementById('w_clients').innerHTML = clients.length === 0 ? '<p style="color:var(--muted);font-size:13px">Нет клиентов</p>' :
    clients.map(c=>`<div class="client-item"><div class="client-name">${{c.Имя||'—'}}</div><div class="client-meta">${{c.Авто||''}} · ${{c.Агрегат||''}} · ${{statusBadge(c.Статус)}}</div></div>`).join('');
}}
load();
</script>
</body></html>"""

CLIENTS_PAGE = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Клиенты — AutoCRM</title>{_BASE_CSS}</head><body>
{_NAV}
<div class="container">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
    <div class="page-title" style="margin:0">📋 Мои клиенты</div>
    <button class="btn btn-primary" onclick="toggleForm()">➕ Добавить клиента</button>
  </div>
  <div class="form-section" id="addForm">
    <div class="form-grid">
      <div class="form-group"><label>Имя *</label><input id="f_name" placeholder="Иван Иванов"/></div>
      <div class="form-group"><label>Телефон *</label><input id="f_phone" placeholder="+380..."/></div>
      <div class="form-group"><label>Автомобиль</label><input id="f_auto" placeholder="Toyota Camry 2018"/></div>
      <div class="form-group"><label>VIN</label><input id="f_vin" placeholder="VIN-код"/></div>
      <div class="form-group"><label>Агрегат</label><input id="f_unit" placeholder="12V 120A Bosch"/></div>
      <div class="form-group"><label>Тип агрегата</label><select id="f_type"><option>Генератор</option><option>Стартер</option></select></div>
      <div class="form-group"><label>Состояние</label><select id="f_cond"><option>Новый</option><option>Восстановленный</option><option>Б/У</option></select></div>
      <div class="form-group"><label>Цена (₴)</label><input id="f_price" type="number" placeholder="3500"/></div>
      <div class="form-group"><label>Статус</label><select id="f_status"><option>Новый</option><option>В обработке</option><option>Закрыт</option></select></div>
      <div class="form-group" style="grid-column:span 2"><label>Комментарий</label><input id="f_comment" placeholder="Доп. информация..."/></div>
    </div>
    <div class="form-actions">
      <button class="btn btn-success" onclick="saveClient()">Сохранить</button>
      <button class="btn btn-secondary" onclick="toggleForm()">Отмена</button>
    </div>
  </div>
  <div class="toolbar">
    <input class="search-input" id="search" placeholder="🔍 Поиск по имени, телефону, VIN..." oninput="filterTable()"/>
    <span id="cnt" style="color:var(--muted);font-size:13px"></span>
  </div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="table-wrap">
      <table id="tbl">
        <thead><tr><th>Имя</th><th>Телефон</th><th>Авто</th><th>VIN</th><th>Агрегат</th><th>Тип</th><th>Состояние</th><th>Цена</th><th>Статус</th><th>Комментарий</th><th>Дата</th></tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>
</div>
<script>
let allClients = [];
function toggleForm(){{ document.getElementById('addForm').classList.toggle('open'); }}
function fmt(s){{
  if(!s) return '—';
  const d = new Date(s);
  if(isNaN(d)) return s;
  return d.toLocaleString('uk-UA',{{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}});
}}
function filterTable(){{
  const q = document.getElementById('search').value.toLowerCase();
  const rows = allClients.filter(c =>
    (c.Имя||'').toLowerCase().includes(q) ||
    (c.Телефон||'').toLowerCase().includes(q) ||
    (c.VIN||'').toLowerCase().includes(q) ||
    (c.Авто||'').toLowerCase().includes(q)
  );
  render(rows);
}}
function render(data){{
  document.getElementById('cnt').textContent = data.length + ' клиентов';
  document.getElementById('tbody').innerHTML = data.map(c=>`<tr>
    <td><b>${{c.Имя||'—'}}</b></td>
    <td><a href="tel:${{c.Телефон}}">${{c.Телефон||'—'}}</a></td>
    <td>${{c.Авто||'—'}}</td><td>${{c.VIN||'—'}}</td>
    <td>${{c.Агрегат||'—'}}</td><td>${{c.Тип||'—'}}</td><td>${{c.Состояние||'—'}}</td>
    <td>${{c.Цена ? c.Цена+'₴' : '—'}}</td>
    <td>${{statusBadge(c.Статус)}}</td>
    <td>${{c.Комментарий||'—'}}</td>
    <td>${{fmt(c.Дата_создания)}}</td>
  </tr>`).join('');
}}
async function load(){{
  const res = await fetch('/api/clients');
  if(res.status===403){{ window.location.href='/'; return; }}
  allClients = await res.json();
  render(allClients);
}}
async function saveClient(){{
  const data = {{
    name: document.getElementById('f_name').value.trim(),
    phone: document.getElementById('f_phone').value.trim(),
    auto: document.getElementById('f_auto').value.trim(),
    vin: document.getElementById('f_vin').value.trim(),
    unit: document.getElementById('f_unit').value.trim(),
    unit_type: document.getElementById('f_type').value,
    condition: document.getElementById('f_cond').value,
    price: document.getElementById('f_price').value,
    comment: document.getElementById('f_comment').value.trim(),
    status: document.getElementById('f_status').value,
  }};
  if(!data.name || !data.phone){{ toast('Заполните имя и телефон','error'); return; }}
  const res = await fetch('/api/add_client',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
  const r = await res.json();
  if(r.ok){{ toast('Клиент добавлен'); toggleForm(); load(); }}
  else toast('Ошибка сохранения','error');
}}
load();
</script>
</body></html>"""

AGGREGATES_PAGE = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Агрегаты — AutoCRM</title>{_BASE_CSS}</head><body>
{_NAV}
<div class="container">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
    <div class="page-title" style="margin:0">🗄️ База агрегатов</div>
    <button class="btn btn-primary" onclick="toggleForm()">➕ Добавить агрегат</button>
  </div>
  <div class="form-section" id="addForm">
    <div class="form-grid">
      <div class="form-group"><label>Тип</label><select id="f_type"><option>Генератор</option><option>Стартер</option></select></div>
      <div class="form-group"><label>Модель *</label><input id="f_model" placeholder="Bosch 0 124 525 001"/></div>
      <div class="form-group"><label>Аналог</label><input id="f_analog" placeholder="Valeo 437344"/></div>
      <div class="form-group"><label>Характеристики</label><input id="f_feat" placeholder="12V, 120A"/></div>
      <div class="form-group"><label>Наличие</label><select id="f_avail"><option>В наличии</option><option>Под заказ</option><option>Нет</option></select></div>
      <div class="form-group"><label>Цена (₴)</label><input id="f_price" type="number"/></div>
      <div class="form-group"><label>Гарантия</label><input id="f_war" placeholder="12 месяцев"/></div>
    </div>
    <div class="form-actions">
      <button class="btn btn-success" onclick="saveAgg()">Сохранить</button>
      <button class="btn btn-secondary" onclick="toggleForm()">Отмена</button>
    </div>
  </div>
  <div class="toolbar">
    <input class="search-input" id="search" placeholder="🔍 Поиск по модели, типу, аналогу..." oninput="filterTable()"/>
    <span id="cnt" style="color:var(--muted);font-size:13px"></span>
  </div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="table-wrap">
      <table><thead><tr><th>Тип</th><th>Модель</th><th>Аналог</th><th>Характеристики</th><th>Наличие</th><th>Цена</th><th>Гарантия</th></tr></thead>
      <tbody id="tbody"></tbody></table>
    </div>
  </div>
</div>
<script>
let all = [];
function toggleForm(){{ document.getElementById('addForm').classList.toggle('open'); }}
function filterTable(){{
  const q = document.getElementById('search').value.toLowerCase();
  render(all.filter(a => (a.Тип||'').toLowerCase().includes(q)||(a.Модель||'').toLowerCase().includes(q)||(a.Аналог||'').toLowerCase().includes(q)));
}}
function render(data){{
  document.getElementById('cnt').textContent = data.length + ' агрегатов';
  document.getElementById('tbody').innerHTML = data.map(a=>`<tr>
    <td>${{a.Тип||'—'}}</td><td><b>${{a.Модель||'—'}}</b></td>
    <td>${{a.Аналог||'—'}}</td><td>${{a.Характеристики||'—'}}</td>
    <td>${{statusBadge(a.Наличие)}}</td>
    <td>${{a.Цена ? a.Цена+'₴':'—'}}</td><td>${{a.Гарантия||'—'}}</td>
  </tr>`).join('');
}}
async function load(){{
  const res = await fetch('/api/aggregates');
  if(res.status===403){{ window.location.href='/'; return; }}
  all = await res.json();
  render(all);
}}
async function saveAgg(){{
  const data={{type:document.getElementById('f_type').value,model:document.getElementById('f_model').value.trim(),
    analog:document.getElementById('f_analog').value.trim(),features:document.getElementById('f_feat').value.trim(),
    availability:document.getElementById('f_avail').value,price:document.getElementById('f_price').value,
    warranty:document.getElementById('f_war').value.trim()}};
  if(!data.model){{toast('Введите модель','error');return;}}
  const res = await fetch('/api/add_aggregate',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
  const r = await res.json();
  if(r.ok){{toast('Агрегат добавлен');toggleForm();load();}}
  else toast('Ошибка','error');
}}
load();
</script>
</body></html>"""

DEALS_PAGE = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Сделки — AutoCRM</title>{_BASE_CSS}</head><body>
{_NAV}
<div class="container">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
    <div class="page-title" style="margin:0">💰 Мои сделки</div>
    <button class="btn btn-primary" onclick="toggleForm()">➕ Добавить сделку</button>
  </div>
  <div class="form-section" id="addForm">
    <div class="form-grid">
      <div class="form-group"><label>ID клиента *</label><input id="f_client" placeholder="ID из базы клиентов"/></div>
      <div class="form-group"><label>ID товара *</label><input id="f_product" placeholder="ID агрегата"/></div>
      <div class="form-group"><label>Сумма (₴) *</label><input id="f_amount" type="number"/></div>
      <div class="form-group"><label>Статус</label><select id="f_status"><option>Новая</option><option>В обработке</option><option>Закрыта</option></select></div>
    </div>
    <div class="form-actions">
      <button class="btn btn-success" onclick="saveDeal()">Сохранить</button>
      <button class="btn btn-secondary" onclick="toggleForm()">Отмена</button>
    </div>
  </div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="table-wrap">
      <table><thead><tr><th>#</th><th>Клиент ID</th><th>Товар ID</th><th>Сумма</th><th>Статус</th><th>Дата</th></tr></thead>
      <tbody id="tbody"></tbody></table>
    </div>
  </div>
</div>
<script>
function toggleForm(){{ document.getElementById('addForm').classList.toggle('open'); }}
async function load(){{
  const res = await fetch('/api/deals');
  if(res.status===403){{ window.location.href='/'; return; }}
  const data = await res.json();
  document.getElementById('tbody').innerHTML = data.map(d=>`<tr>
    <td>${{d.ID||''}}</td><td>${{d.Клиент_ID||'—'}}</td><td>${{d.Товар_ID||'—'}}</td>
    <td><b>${{d.Сумма ? d.Сумма+'₴':'—'}}</b></td>
    <td>${{statusBadge(d.Статус)}}</td><td>${{d.Дата||'—'}}</td>
  </tr>`).join('');
}}
async function saveDeal(){{
  const data={{client_id:document.getElementById('f_client').value,product_id:document.getElementById('f_product').value,
    amount:document.getElementById('f_amount').value,status:document.getElementById('f_status').value}};
  if(!data.client_id||!data.amount){{toast('Заполните обязательные поля','error');return;}}
  const res = await fetch('/api/add_deal',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
  const r = await res.json();
  if(r.ok){{toast('Сделка добавлена');toggleForm();load();}}
  else toast('Ошибка','error');
}}
load();
</script>
</body></html>"""

TASKS_PAGE = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Задачи — AutoCRM</title>{_BASE_CSS}</head><body>
{_NAV}
<div class="container">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
    <div class="page-title" style="margin:0">📝 Мои задачи</div>
    <button class="btn btn-primary" onclick="toggleForm()">➕ Добавить задачу</button>
  </div>
  <div class="form-section" id="addForm">
    <div class="form-grid">
      <div class="form-group" style="grid-column:span 2"><label>Описание *</label><input id="f_desc" placeholder="Позвонить клиенту..."/></div>
      <div class="form-group"><label>Дата *</label><input id="f_date" type="date"/></div>
      <div class="form-group"><label>Время</label><input id="f_time" type="time"/></div>
    </div>
    <div class="form-actions">
      <button class="btn btn-success" onclick="saveTask()">Сохранить</button>
      <button class="btn btn-secondary" onclick="toggleForm()">Отмена</button>
    </div>
  </div>
  <div class="card" style="padding:0;overflow:hidden">
    <div class="table-wrap">
      <table><thead><tr><th>Описание</th><th>Дата</th><th>Время</th><th>Статус</th><th>Действия</th></tr></thead>
      <tbody id="tbody"></tbody></table>
    </div>
  </div>
</div>
<script>
function toggleForm(){{ document.getElementById('addForm').classList.toggle('open'); }}
async function load(){{
  const res = await fetch('/api/tasks');
  if(res.status===403){{ window.location.href='/'; return; }}
  const data = await res.json();
  document.getElementById('tbody').innerHTML = data.map(t=>`<tr>
    <td>${{t.Описание||'—'}}</td><td>${{t.Дата||'—'}}</td><td>${{t.Время||'—'}}</td>
    <td>${{statusBadge(t.Статус)}}</td>
    <td style="display:flex;gap:6px;flex-wrap:wrap">
      ${{t.Статус!=='Выполнено'?`<button class="btn btn-sm btn-success" onclick="setStatus('${{t.ID}}','Выполнено')">✓ Выполнено</button>`:''}}</td>
  </tr>`).join('');
}}
async function setStatus(id, status){{
  await fetch('/api/update_task',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id,status}})}});
  load();
}}
async function saveTask(){{
  const data={{description:document.getElementById('f_desc').value.trim(),date:document.getElementById('f_date').value,time:document.getElementById('f_time').value}};
  if(!data.description||!data.date){{toast('Заполните описание и дату','error');return;}}
  const res = await fetch('/api/add_task',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
  const r = await res.json();
  if(r.ok){{toast('Задача добавлена');toggleForm();load();}}
  else toast('Ошибка','error');
}}
document.getElementById('f_date').value = new Date().toISOString().split('T')[0];
load();
</script>
</body></html>"""

# ─────────────────────────────────────────────
# HTTP-СЕРВЕР
# ─────────────────────────────────────────────
class CRMHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # отключаем стандартные логи
        pass

    # ─── Routing ───
    def do_GET(self):
        p = self.path.split("?")[0]
        routes = {
            "/": LOGIN_PAGE,
            "/dashboard": DASHBOARD_PAGE,
            "/clients": CLIENTS_PAGE,
            "/aggregates": AGGREGATES_PAGE,
            "/deals": DEALS_PAGE,
            "/tasks": TASKS_PAGE,
        }
        if p in routes:
            self._html(routes[p])
            return
        mid = self._auth()
        api = {
            "/api/clients":    lambda: get_clients(mid),
            "/api/aggregates": lambda: get_aggregates(self._qparam("search")),
            "/api/deals":      lambda: get_deals(mid),
            "/api/tasks":      lambda: get_tasks(mid),
            "/api/dashboard":  lambda: get_dashboard(mid) if mid else self._forbidden(),
            "/api/analytics":  lambda: get_analytics(mid),
        }
        if p in api:
            if not mid and p not in ("/api/aggregates",):
                self._forbidden_json(); return
            self._json(api[p]())
        else:
            self.send_error(404)

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._body()
        mid = self._auth()
        if p == "/api/login":
            self._do_login(body)
        elif p == "/api/add_client":
            if not mid: self._forbidden_json(); return
            self._json({"ok": add_client(body, mid)})
        elif p == "/api/add_aggregate":
            self._json({"ok": add_aggregate(body)})
        elif p == "/api/add_deal":
            if not mid: self._forbidden_json(); return
            self._json({"ok": add_deal(body, mid)})
        elif p == "/api/add_task":
            if not mid: self._forbidden_json(); return
            self._json({"ok": add_task(body, mid)})
        elif p == "/api/update_task":
            if not mid: self._forbidden_json(); return
            self._json({"ok": update_task(body.get("id",""), body.get("status",""), mid)})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ─── Helpers ───
    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _forbidden_json(self):
        self._json({"error": "Unauthorized"}, 403)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def _auth(self) -> str | None:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("auth_token="):
                val = part[len("auth_token="):].strip()
                return val if val else None
        return None

    def _qparam(self, key: str) -> str:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        return params.get(key, [""])[0]

    def _forbidden(self):
        self._forbidden_json()

    def _do_login(self, data: dict):
        tg_id = str(data.get("tg_id", "")).strip()
        name  = str(data.get("name", "")).strip()
        if not tg_id:
            self._json({"ok": False, "error": "Введите Telegram ID"})
            return
        try:
            register_manager(tg_id, name or f"Менеджер #{tg_id}")
            mname = get_manager_name(tg_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", f"auth_token={tg_id}; Path=/; HttpOnly; SameSite=Lax")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "name": mname}, ensure_ascii=False).encode())
        except Exception as e:
            logger.error("login: %s", e)
            self._json({"ok": False, "error": str(e)})

# ─────────────────────────────────────────────
# TELEGRAM-БОТ
# ─────────────────────────────────────────────
# Состояния для добавления товара
T_TYPE, T_MODEL, T_PRICE, T_STATUS, T_DESCRIPTION, T_PHOTO = range(6)
# Состояния для добавления клиента
C_NAME, C_PHONE, C_AUTO, C_VIN, C_UNIT, C_UNIT_TYPE, C_COND, C_PRICE, C_COMMENT, C_STATUS = range(10, 20)

PRODUCT_STATUSES = ["в наличии", "продан", "в ремонте"]
CLIENT_STATUSES  = ["Новый", "В обработке", "Закрыт"]

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
        ["🔙 Назад"],
    ], resize_keyboard=True)

def kb_cancel():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

# ── Утилиты бота ──
async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=kb_main())
    return ConversationHandler.END

def _is_cancel(text: str) -> bool:
    return text.strip() in ("❌ Отмена", "🔙 Назад", "/cancel")

# ── Команды ──
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.full_name or f"Пользователь #{user.id}"
    try:
        register_manager(str(user.id), name)
    except Exception:
        pass
    await update.message.reply_text(
        f"👋 Привет, *{name}*!\n\nДобро пожаловать в AutoCRM — систему управления продажами генераторов и стартеров.",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *Справка по боту*\n\n"
        "📋 *Клиенты* — открыть базу клиентов в веб\n"
        "🗄️ *Агрегаты* — управление складом\n"
        "📜 *Скрипты* — ответы на возражения\n"
        "📊 *Аналитика* — открыть дашборд\n"
        "🔗 *Поиск* — Avto.pro, Exist.ua\n"
        "🚚 *Нова Пошта* — трекинг и расчёт\n"
        "📱 *Веб-приложение* — полный CRM-интерфейс\n\n"
        "Команды:\n`/start` — главное меню\n`/help` — помощь\n`/cancel` — отмена",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )

# ── Главное меню — обработчики ──
async def handle_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("Открыть базу клиентов", web_app=WebAppInfo(url=RENDER_URL + "/clients"))
    ]])
    await update.message.reply_text("📋 Нажмите для открытия базы клиентов:", reply_markup=btn)

async def handle_agregats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🗄️ Управление агрегатами:", reply_markup=kb_agregat())

async def handle_scripts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 *Скрипты продаж*\n\n"
        "🔴 *«Дорого»*\n"
        "Мы даём 12 месяцев гарантии — это дешевле, чем через 3 месяца снова платить. Плюс оригинальные запчасти.\n\n"
        "🔴 *«Хочу купить по месту»*\n"
        "Отправляем Новой Почтой за 1-2 дня, оплата при получении. Экономите время на поиске.\n\n"
        "🔴 *«Не доверяю отправке»*\n"
        "Работаем 5+ лет, сотни отзывов. Фото и видео до отправки — без риска.\n\n"
        "🔴 *«Подумаю»*\n"
        "Товар в дефиците. Лучше забронировать сейчас — цена может вырасти.\n\n"
        "🔴 *«Если не подойдёт?»*\n"
        "Сверяем по VIN и маркировке. Если ошибёмся — заменим или вернём деньги.\n\n"
        "🔴 *«Есть ли гарантия?»*\n"
        "Да — 12 месяцев официальной гарантии на все агрегаты.\n\n"
        "🔴 *«А точно подойдёт?»*\n"
        "Проверяем по VIN и марке авто — 100% совместимость.\n\n"
        "🔴 *«Скиньте фото»*\n"
        "Сделаем фото/видео и пришлём в чат сразу."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb_main())

async def handle_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("Открыть дашборд", web_app=WebAppInfo(url=RENDER_URL + "/dashboard"))
    ]])
    mid = str(update.effective_user.id)
    a = get_analytics(mid)
    text = (
        f"📊 *Ваша аналитика*\n\n"
        f"💰 Выручка всего: *{a['total_revenue']} ₴*\n"
        f"💰 За месяц: *{a['month_revenue']} ₴*\n"
        f"📦 Сделок всего: *{a['total_deals']}*\n"
        f"📦 За месяц: *{a['month_deals']}*\n"
        f"📞 Звонков: *{a['total_calls']}*\n"
        f"🎯 Конверсия: *{a['conversion']}%*"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=btn)

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 Avto.pro — поиск агрегатов", url="https://avto.pro/")],
        [InlineKeyboardButton("🔎 Exist.ua — поиск по VIN", url="https://exist.ua/")],
        [InlineKeyboardButton("📦 РозеткаПро — запчасти", url="https://pro.rozetka.com.ua/")],
    ])
    await update.message.reply_text("🔗 Выберите сервис для поиска:", reply_markup=btn)

async def handle_nova_poshta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Трекинг посылок", url="https://tracking.novaposhta.ua/#/uk")],
        [InlineKeyboardButton("⏱ Срок доставки", url="https://forms.novapost.world/delivery_time/#/?source=site&locale=uk")],
        [InlineKeyboardButton("🏢 Найти отделение", url="https://novaposhta.ua/branch/tab/branch")],
    ])
    await update.message.reply_text("🚚 Нова Пошта — выберите действие:", reply_markup=btn)

async def handle_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("Открыть AutoCRM", web_app=WebAppInfo(url=RENDER_URL))
    ]])
    await update.message.reply_text(
        "📱 Нажмите кнопку для открытия CRM:",
        reply_markup=btn,
    )

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Главное меню:", reply_markup=kb_main())

# ── Добавление товара (ConversationHandler) ──
async def prod_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Тип товара:",
        reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"], ["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return T_TYPE

async def prod_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    if txt not in ("Генератор", "Стартер"):
        await update.message.reply_text("Выберите: Генератор или Стартер")
        return T_TYPE
    context.user_data["p_type"] = txt
    await update.message.reply_text("Введите модель:", reply_markup=kb_cancel())
    return T_MODEL

async def prod_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    context.user_data["p_model"] = txt
    await update.message.reply_text("Цена (грн, только число):", reply_markup=kb_cancel())
    return T_PRICE

async def prod_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    if not txt.isdigit():
        await update.message.reply_text("Введите целое число (цену в гривнах):")
        return T_PRICE
    context.user_data["p_price"] = txt
    await update.message.reply_text(
        "Статус:",
        reply_markup=ReplyKeyboardMarkup([[s] for s in PRODUCT_STATUSES] + [["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True),
    )
    return T_STATUS

async def prod_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    if txt not in PRODUCT_STATUSES:
        await update.message.reply_text("Выберите из предложенных вариантов")
        return T_STATUS
    context.user_data["p_status"] = txt
    await update.message.reply_text("Описание (или «нет»):", reply_markup=kb_cancel())
    return T_DESCRIPTION

async def prod_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if _is_cancel(txt): return await _cancel(update, context)
    context.user_data["p_desc"] = "" if txt.lower() in ("нет", "-", "no") else txt
    await update.message.reply_text("Отправьте фото товара (или «нет»):", reply_markup=kb_cancel())
    return T_PHOTO

async def prod_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip() if update.message.text else ""
    if _is_cancel(txt): return await _cancel(update, context)

    photo_id = ""
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    elif txt.lower() not in ("нет", "-", "no", ""):
        await update.message.reply_text("Отправьте фото или напишите «нет»")
        return T_PHOTO

    d = context.user_data
    ok, nid = add_product({
        "type": d.get("p_type", ""),
        "model": d.get("p_model", ""),
        "price": d.get("p_price", ""),
        "status": d.get("p_status", "в наличии"),
        "description": d.get("p_desc", ""),
        "photo_id": photo_id,
    })
    context.user_data.clear()
    if ok:
        await update.message.reply_text(
            f"✅ Товар *{d['p_model']}* добавлен (ID {nid})",
            parse_mode="Markdown",
            reply_markup=kb_agregat(),
        )
    else:
        await update.message.reply_text("❌ Ошибка сохранения", reply_markup=kb_agregat())
    return ConversationHandler.END

# ── Просмотр всех товаров ──
async def show_all_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_products()
    if not products:
        await update.message.reply_text("📭 Склад пуст.", reply_markup=kb_agregat())
        return
    # Показываем первые 10 кнопками
    btns = []
    for i, p in enumerate(products[:15]):
        label = f"{p.get('Тип','?')} {p.get('Модель','?')} — {p.get('Цена','')}₴ [{p.get('Статус','')}]"
        btns.append([InlineKeyboardButton(label[:64], callback_data=f"pd_{i}")])
    context.user_data["products_cache"] = products[:15]
    await update.message.reply_text(
        f"📋 Товаров на складе: *{len(products)}*\n(показаны первые {min(15, len(products))})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btns),
    )

async def cb_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split("_")[1])
    products = context.user_data.get("products_cache", [])
    if idx >= len(products):
        await q.edit_message_text("Ошибка: товар не найден")
        return
    p = products[idx]
    text = (
        f"*{p.get('Тип','')} — {p.get('Модель','')}*\n"
        f"Цена: *{p.get('Цена','')} ₴*\n"
        f"Статус: {p.get('Статус','')}\n"
        f"Описание: {p.get('Описание','—')}"
    )
    photo = p.get("Фото_ID", "")
    try:
        if photo:
            await context.bot.send_photo(chat_id=q.message.chat_id, photo=photo, caption=text, parse_mode="Markdown")
        else:
            await q.edit_message_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error("product detail: %s", e)
        await q.edit_message_text(text, parse_mode="Markdown")

# ── Изменение статуса товара ──
async def change_status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_products()
    if not products:
        await update.message.reply_text("Нет товаров.")
        return
    btns = []
    for i, p in enumerate(products[:15]):
        label = f"{p.get('Тип','?')} {p.get('Модель','?')} [{p.get('Статус','')}]"
        btns.append([InlineKeyboardButton(label[:64], callback_data=f"chs_{i}")])
    context.user_data["products_cache"] = products[:15]
    await update.message.reply_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(btns))

async def cb_change_status_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split("_")[1])
    context.user_data["edit_idx"] = idx
    btns = [[InlineKeyboardButton(s, callback_data=f"sts_{s}")] for s in PRODUCT_STATUSES]
    await q.edit_message_text("Выберите новый статус:", reply_markup=InlineKeyboardMarkup(btns))

async def cb_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    new_status = q.data[4:]  # убираем 'sts_'
    idx = context.user_data.get("edit_idx")
    products = context.user_data.get("products_cache", [])
    if idx is None or idx >= len(products):
        await q.edit_message_text("Ошибка сессии")
        return
    # В gspread нам нужен номер строки = idx+2 (заголовок = 1, первая запись = 2)
    ok = update_product_status(idx + 2, new_status)
    if ok:
        await q.edit_message_text(f"✅ Статус изменён на *{new_status}*", parse_mode="Markdown")
    else:
        await q.edit_message_text("❌ Не удалось обновить статус")
    context.user_data.pop("edit_idx", None)

# ── Поиск товара ──
async def search_product_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите модель или тип для поиска:", reply_markup=kb_cancel())
    context.user_data["awaiting_search"] = True

async def search_product_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    btns = []
    for i, p in enumerate(results[:10]):
        label = f"{p.get('Тип','?')} {p.get('Модель','?')} — {p.get('Цена','')}₴"
        btns.append([InlineKeyboardButton(label[:64], callback_data=f"pd_{i}")])
    context.user_data["products_cache"] = results[:10]
    await update.message.reply_text(
        f"🔍 Найдено: *{len(results)}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btns),
    )

# ── Главный обработчик текста ──
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()

    # Агрегаты-меню
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
        await handle_back(update, context)
    else:
        # Может быть поиск товара
        if context.user_data.get("awaiting_search"):
            await search_product_result(update, context)
        else:
            await update.message.reply_text("Используйте кнопки меню.", reply_markup=kb_main())

# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def run_web():
    httpd = HTTPServer(("0.0.0.0", WEB_PORT), CRMHandler)
    logger.info("Веб-сервер запущен на порту %d", WEB_PORT)
    httpd.serve_forever()

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return

    # Запускаем HTTP-сервер в фоне
    threading.Thread(target=run_web, daemon=True).start()

    # Строим Telegram-приложение
    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler для добавления товара
    add_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^➕ Добавить товар$"), prod_start)],
        states={
            T_TYPE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_type)],
            T_MODEL:       [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_model)],
            T_PRICE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_price)],
            T_STATUS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_status)],
            T_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_description)],
            T_PHOTO: [
                MessageHandler(filters.PHOTO, prod_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, prod_photo),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", _cancel),
            MessageHandler(filters.Regex(r"^❌ Отмена$"), _cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(add_product_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", _cancel))
    app.add_handler(CallbackQueryHandler(cb_product_detail,      pattern=r"^pd_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_change_status_select, pattern=r"^chs_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_set_status,           pattern=r"^sts_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
