# -*- coding: utf-8 -*-
"""
CRM-система для продажи генераторов и стартеров.
Telegram-бот + веб-интерфейс. Версия 6.0 – полностью переписанная, стабильная.
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

# ---------- НАСТРОЙКИ ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://ваш-домен.onrender.com")
NOVA_POSHTA_API_KEY = os.getenv("NOVA_POSHTA_API_KEY", "")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", scope)
client = gspread.authorize(creds)
main_sheet = client.open_by_url(SHEET_URL).sheet1  # товары

# ---------- СТРУКТУРА ТАБЛИЦ ----------
SHEETS = {
    "Клиенты":   ["ID", "Имя", "Телефон", "Авто", "VIN", "Агрегат", "Тип", "Состояние", "Цена", "Комментарий", "Статус", "История", "Менеджер_ID", "Дата создания"],
    "Агрегаты":  ["ID", "Тип", "Модель", "Аналог", "Характеристики", "Наличие", "Цена", "Гарантия"],
    "Сделки":    ["ID", "Клиент_ID", "Товар_ID", "Сумма", "Статус", "Дата", "Менеджер_ID"],
    "Звонки":    ["ID", "Менеджер_ID", "Клиент_ID", "Результат", "Дата"],
    "Скрипты":   ["Возражение", "Ответ"],
    "Менеджеры": ["Telegram_ID", "Имя", "Пароль"],
    "Задачи":    ["ID", "Менеджер_ID", "Описание", "Дата", "Время", "Статус", "Комментарий"]
}

def init_sheets():
    for name, headers in SHEETS.items():
        try:
            wb = client.open_by_url(SHEET_URL)
            existing = [ws.title for ws in wb.worksheets()]
            if name not in existing:
                ws = wb.add_worksheet(title=name, rows="100", cols="20")
                ws.insert_row(headers, 1)
                logger.info(f"Лист '{name}' создан")
            elif name == "Клиенты":
                ws = wb.worksheet(name)
                row1 = ws.row_values(1)
                for extra in ["Менеджер_ID", "Дата создания"]:
                    if extra not in row1:
                        ws.add_cols(1)
                        ws.update_cell(1, len(row1)+1, extra)
                        row1.append(extra)
        except Exception as e:
            logger.error(f"Ошибка инициализации листа {name}: {e}")

init_sheets()

# ---------- КНОПКИ БОТА ----------
STATUSES = ["в наличии", "продан", "в ремонте"]
(TYPE, MODEL, PRICE, STATUS, DESCRIPTION, PHOTO) = range(6)

def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📋 Клиенты"), KeyboardButton("🗄️ Агрегаты")],
        [KeyboardButton("📜 Скрипты"), KeyboardButton("📊 Аналитика")],
        [KeyboardButton("📈 Отчёт"), KeyboardButton("🔗 Поиск VIN/Агрегатов")],
        [KeyboardButton("🚚 Новая Почта"), KeyboardButton("🆘 Помощь")],
        [KeyboardButton("📱 Приложение")]
    ], resize_keyboard=True)

def agregat_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Добавить товар")],
        [KeyboardButton("📋 Все товары"), KeyboardButton("🔍 Поиск по модели")],
        [KeyboardButton("✏️ Изменить статус"), KeyboardButton("🔙 Назад")],
        [KeyboardButton("❌ Отмена")]
    ], resize_keyboard=True)

# ---------- HTTP-СЕРВЕР И АВТОРИЗАЦИЯ ----------
class CRMHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/": self._html(LOGIN_PAGE)
        elif path == "/clients": self._html(CLIENTS_PAGE)
        elif path == "/aggregates": self._html(AGGREGATES_PAGE)
        elif path == "/deals": self._html(DEALS_PAGE)
        elif path == "/tasks": self._html(TASKS_PAGE)
        elif path == "/dashboard": self._html(DASHBOARD_PAGE)
        elif path == "/api/clients": self._json(get_my_clients(self._auth()))
        elif path == "/api/aggregates": self._json(get_aggregates())
        elif path == "/api/analytics": self._json(get_analytics(self._auth()))
        elif path == "/api/dashboard": self._json(get_dashboard(self._auth()))
        elif path == "/api/tasks": self._json(get_my_tasks(self._auth()))
        elif path == "/api/deals": self._json(get_my_deals(self._auth()))
        else: self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._body()
        mid = self._auth()
        if path == "/api/login": self._login(body)
        elif path == "/api/add_client": self._json({"ok": add_client(body, mid)})
        elif path == "/api/add_aggregate": self._json({"ok": add_aggregate(body)})
        elif path == "/api/add_task": self._json({"ok": add_task(body, mid)})
        elif path == "/api/add_deal": self._json({"ok": add_deal(body, mid)})
        elif path == "/api/update_task": self._json({"ok": update_task(body.get("id"), body.get("status"), mid)})
        else: self.send_error(404)

    def _html(self, content):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def _auth(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if "auth_token=" in part:
                return part.split("=")[-1].strip()
        return None

    def _login(self, data):
        tg_id = str(data.get("tg_id")).strip()
        if not tg_id:
            self._json({"ok": False, "error": "Введите ID"}, 400)
            return
        try:
            wb = client.open_by_url(SHEET_URL).worksheet("Менеджеры")
            recs = wb.get_all_records()
            name = next((r["Имя"] for r in recs if str(r.get("Telegram_ID")) == tg_id), f"Менеджер {tg_id}")
        except:
            name = f"Менеджер {tg_id}"
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Set-Cookie", f"auth_token={tg_id}; Path=/")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "name": name}).encode())

# ---------- ФУНКЦИИ ДЛЯ ТАБЛИЦ ----------
def get_my_clients(mid):
    if not mid: return []
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Клиенты")
        return [r for r in ws.get_all_records() if str(r.get("Менеджер_ID")) == mid]
    except: return []

def add_client(data, mid):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Клиенты")
        rows = ws.get_all_records()
        new_id = max([int(r["ID"]) for r in rows if r["ID"].isdigit()] + [0]) + 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws.append_row([
            str(new_id), data["name"], data["phone"], data["auto"], data["vin"],
            data["unit"], data["unit_type"], data["condition"], data["price"],
            data["comment"], data["status"], data.get("history", ""), mid, now
        ])
        return True
    except Exception as e:
        logger.error(f"Add client: {e}")
        return False

def get_aggregates():
    try: return client.open_by_url(SHEET_URL).worksheet("Агрегаты").get_all_records()
    except: return []

def add_aggregate(data):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Агрегаты")
        recs = ws.get_all_records()
        nid = max([int(r["ID"]) for r in recs if r["ID"].isdigit()] + [0]) + 1
        ws.append_row([str(nid), data["type"], data["model"], data["analog"],
                       data["features"], data["availability"], data["price"], data["warranty"]])
        return True
    except Exception as e:
        logger.error(f"Add aggregate: {e}")
        return False

def get_analytics(mid):
    try:
        deals = client.open_by_url(SHEET_URL).worksheet("Сделки").get_all_records()
        my = [d for d in deals if str(d.get("Менеджер_ID")) == mid]
        total = sum(float(d.get("Сумма", 0)) for d in my)
        count = len(my)
        calls = 0
        try:
            calls_ws = client.open_by_url(SHEET_URL).worksheet("Звонки").get_all_records()
            calls = len([c for c in calls_ws if str(c.get("Менеджер_ID")) == mid])
        except: pass
        conv = round(count / calls * 100, 1) if calls else 0
        return {"total_sales": total, "total_deals": count, "total_calls": calls, "conversion": conv}
    except: return {"total_sales": 0, "total_deals": 0, "total_calls": 0, "conversion": 0}

def get_dashboard(mid):
    name = "Менеджер"
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Менеджеры")
        for r in ws.get_all_records():
            if str(r.get("Telegram_ID")) == mid:
                name = r.get("Имя", name)
                break
    except: pass
    analytics = get_analytics(mid)
    team_rev = 0.0
    try:
        deals_ws = client.open_by_url(SHEET_URL).worksheet("Сделки").get_all_records()
        month_start = datetime.now().strftime("%Y-%m-01")
        team_rev = sum(float(d.get("Сумма", 0)) for d in deals_ws if d.get("Дата", "") >= month_start)
    except: pass
    tasks_today = []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        tasks_ws = client.open_by_url(SHEET_URL).worksheet("Задачи").get_all_records()
        tasks_today = [t for t in tasks_ws if str(t.get("Менеджер_ID")) == mid and t.get("Дата") == today]
    except: pass
    clients = get_my_clients(mid)[:3]
    return {"name": name, "analytics": analytics, "team_revenue": team_rev,
            "tasks": tasks_today, "last_clients": clients}

def get_my_tasks(mid):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Задачи").get_all_records()
        return [t for t in ws if str(t.get("Менеджер_ID")) == mid]
    except: return []

def add_task(data, mid):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Задачи")
        recs = ws.get_all_records()
        nid = max([int(r["ID"]) for r in recs if r["ID"].isdigit()] + [0]) + 1
        ws.append_row([str(nid), mid, data["description"], data["date"],
                       data["time"], data.get("status", "Запланировано"), ""])
        return True
    except: return False

def update_task(task_id, new_status, mid):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Задачи")
        recs = ws.get_all_records()
        for i, r in enumerate(recs, start=2):
            if str(r.get("ID")) == str(task_id) and str(r.get("Менеджер_ID")) == mid:
                ws.update_cell(i, 6, new_status)
                return True
        return False
    except: return False

def get_my_deals(mid):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Сделки").get_all_records()
        return [d for d in ws if str(d.get("Менеджер_ID")) == mid]
    except: return []

def add_deal(data, mid):
    try:
        ws = client.open_by_url(SHEET_URL).worksheet("Сделки")
        recs = ws.get_all_records()
        nid = max([int(r["ID"]) for r in recs if r["ID"].isdigit()] + [0]) + 1
        ws.append_row([str(nid), data["client_id"], data["product_id"],
                       data["amount"], data.get("status", "Новая"),
                       datetime.now().strftime("%Y-%m-%d %H:%M"), mid])
        return True
    except: return False

# ---------- HTML (все страницы) ----------
LOGIN_PAGE = """
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Вход</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light d-flex justify-content-center align-items-center vh-100"><div class="card p-4 shadow" style="width:320px"><h4 class="mb-3">🔐 Вход в CRM</h4><input class="form-control mb-3" placeholder="Ваш Telegram ID" id="tg_id"><button class="btn btn-primary w-100" onclick="login()">Войти</button><div id="error" class="text-danger mt-2" style="display:none"></div></div><script>
async function login(){
  const tg_id=document.getElementById('tg_id').value;
  if(!tg_id){alert('Введите ID');return;}
  const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tg_id})});
  const data=await res.json();
  if(data.ok){
    localStorage.setItem('manager_name',data.name);
    localStorage.setItem('manager_id',tg_id);
    window.location.href='/dashboard';
  }else{
    document.getElementById('error').textContent=data.error||'Ошибка';
    document.getElementById('error').style.display='block';
  }
}
</script></body></html>"""

DASHBOARD_PAGE = """
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Дашборд</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><nav class="navbar navbar-expand navbar-dark bg-dark mb-3"><div class="container"><a class="navbar-brand" href="#">CRM</a><div class="navbar-nav"><a class="nav-link active" href="/dashboard">Дашборд</a><a class="nav-link" href="/clients">Мои клиенты</a><a class="nav-link" href="/aggregates">Агрегаты</a><a class="nav-link" href="/deals">Сделки</a><a class="nav-link" href="/tasks">Задачи</a></div><div class="navbar-text text-white ms-auto me-3" id="manager_name"></div><button class="btn btn-outline-light btn-sm" onclick="logout()">Выйти</button></div></nav><div class="container"><h2>📊 Мой дашборд</h2><p class="text-muted">Вы вошли: <span id="login_time"></span></p><div class="row" id="stats"><div class="col-md-3"><div class="card p-3 text-center"><h6>Сделок (сегодня)</h6><h4 id="my_deals_today">0</h4></div></div><div class="col-md-3"><div class="card p-3 text-center"><h6>Выручка</h6><h4 id="my_revenue">0 ₴</h4></div></div><div class="col-md-3"><div class="card p-3 text-center"><h6>Конверсия</h6><h4 id="conversion">0 %</h4></div></div><div class="col-md-3"><div class="card p-3 text-center"><h6>Выручка команды (мес)</h6><h4 id="team_revenue">0 ₴</h4></div></div></div><div class="row mt-4"><div class="col-md-6"><div class="card p-3"><h6>📋 Задачи на сегодня</h6><ul id="tasks_today" class="list-unstyled"></ul></div></div><div class="col-md-6"><div class="card p-3"><h6>🚗 Мои клиенты (последние)</h6><ul id="last_clients" class="list-unstyled"></ul></div></div></div></div><script>
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('login_time').textContent=new Date().toLocaleString('ru-RU');
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
  if(data.tasks.length===0){tasksUl.innerHTML='<li>Нет задач</li>';}
  else{data.tasks.forEach(t=>{tasksUl.innerHTML+=`<li>${t.Опис||''} (${t.Дата||''} ${t.Время||''})</li>`;});}
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

CLIENTS_PAGE = """
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Мои клиенты</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><nav class="navbar navbar-expand navbar-dark bg-dark mb-3"><div class="container"><a class="navbar-brand" href="#">CRM</a><div class="navbar-nav"><a class="nav-link" href="/dashboard">Дашборд</a><a class="nav-link active" href="/clients">Мои клиенты</a><a class="nav-link" href="/aggregates">Агрегаты</a><a class="nav-link" href="/deals">Сделки</a><a class="nav-link" href="/tasks">Задачи</a></div><div class="navbar-text text-white ms-auto me-3" id="manager_name"></div><button class="btn btn-outline-light btn-sm" onclick="logout()">Выйти</button></div></nav><div class="container"><h2>📋 Мои клиенты</h2><button class="btn btn-success mb-3" onclick="toggleForm()">➕ Добавить клиента</button><div id="addForm" class="card p-3 mb-3 d-none"><div class="row g-2"><div class="col-md-4"><input class="form-control" placeholder="Имя" id="name"></div><div class="col-md-4"><input class="form-control" placeholder="Телефон" id="phone"></div><div class="col-md-4"><input class="form-control" placeholder="Авто" id="auto"></div><div class="col-md-4"><input class="form-control" placeholder="VIN" id="vin"></div><div class="col-md-4"><input class="form-control" placeholder="Агрегат" id="unit"></div><div class="col-md-2"><select class="form-select" id="unit_type"><option>Стартер</option><option>Генератор</option></select></div><div class="col-md-2"><select class="form-select" id="condition"><option>Новый</option><option>Восстановленный</option><option>Б/У</option></select></div><div class="col-md-2"><input class="form-control" placeholder="Цена" id="price"></div><div class="col-md-6"><input class="form-control" placeholder="Комментарий" id="comment"></div><div class="col-md-3"><select class="form-select" id="status"><option>Новый</option><option>В обработке</option><option>Закрыт</option></select></div><div class="col-12 mt-2"><button class="btn btn-primary" onclick="addClient()">Сохранить</button><button class="btn btn-secondary" onclick="toggleForm()">Отмена</button></div></div></div><table class="table table-bordered bg-white"><thead><tr><th>Имя</th><th>Телефон</th><th>Авто</th><th>VIN</th><th>Агрегат</th><th>Тип</th><th>Состояние</th><th>Цена</th><th>Статус</th><th>Комментарий</th><th>Дата</th></tr></thead><tbody id="clients-body"></tbody></table></div><script>
document.getElementById('manager_name').textContent=localStorage.getItem('manager_name')||'';
function toggleForm(){document.getElementById('addForm').classList.toggle('d-none')}
function formatDate(dateStr){
  if(!dateStr) return '';
  const d=new Date(dateStr);
  if(isNaN(d)) return dateStr;
  return d.toLocaleString('ru-RU',{weekday:'long',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
}
async function loadClients(){
  const res=await fetch('/api/clients');
  if(res.status===403){window.location.href='/';return}
  const data=await res.json();
  const tbody=document.getElementById('clients-body');
  tbody.innerHTML=data.map(c=>`<tr>
    <td>${c.Имя||''}</td><td>${c.Телефон||''}</td><td>${c.Авто||''}</td><td>${c.VIN||''}</td>
    <td>${c.Агрегат||''}</td><td>${c.Тип||''}</td><td>${c.Состояние||''}</td><td>${c.Цена||''}</td>
    <td>${c.Статус||''}</td><td>${c.Комментарий||''}</td><td>${formatDate(c['Дата создания'])}</td>
  </tr>`).join('');
}
async function addClient(){
  const data={
    name:document.getElementById('name').value,
    phone:document.getElementById('phone').value,
    auto:document.getElementById('auto').value,
    vin:document.getElementById('vin').value,
    unit:document.getElementById('unit').value,
    unit_type:document.getElementById('unit_type').value,
    condition:document.getElementById('condition').value,
    price:document.getElementById('price').value,
    comment:document.getElementById('comment').value,
    status:document.getElementById('status').value,
    history:''
  };
  const res=await fetch('/api/add_client',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await res.json();
  if(result.ok){
    toggleForm();
    loadClients();
  }else{
    alert('Ошибка при добавлении клиента');
  }
}
loadClients();
</script></body></html>"""

AGGREGATES_PAGE = """
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Агрегаты</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><nav class="navbar navbar-expand navbar-dark bg-dark mb-3"><div class="container"><a class="navbar-brand" href="#">CRM</a><div class="navbar-nav"><a class="nav-link" href="/dashboard">Дашборд</a><a class="nav-link" href="/clients">Мои клиенты</a><a class="nav-link active" href="/aggregates">Агрегаты</a><a class="nav-link" href="/deals">Сделки</a><a class="nav-link" href="/tasks">Задачи</a></div><div class="navbar-text text-white ms-auto me-3" id="manager_name"></div><button class="btn btn-outline-light btn-sm" onclick="logout()">Выйти</button></div></nav><div class="container"><h2>🗄️ Агрегаты</h2><button class="btn btn-success mb-3" onclick="toggleForm()">➕ Добавить агрегат</button><div id="addForm" class="card p-3 mb-3 d-none"><div class="row g-2"><div class="col-md-3"><select class="form-select" id="type"><option>Стартер</option><option>Генератор</option></select></div><div class="col-md-3"><input class="form-control" placeholder="Модель" id="model"></div><div class="col-md-3"><input class="form-control" placeholder="Аналог" id="analog"></div><div class="col-md-3"><input class="form-control" placeholder="Характеристики" id="features"></div><div class="col-md-3"><input class="form-control" placeholder="Наличие" id="availability"></div><div class="col-md-2"><input class="form-control" placeholder="Цена" id="price"></div><div class="col-md-2"><input class="form-control" placeholder="Гарантия" id="warranty"></div><div class="col-12 mt-2"><button class="btn btn-primary" onclick="addAggregate()">Сохранить</button><button class="btn btn-secondary" onclick="toggleForm()">Отмена</button></div></div></div><table class="table table-bordered bg-white"><thead><tr><th>Тип</th><th>Модель</th><th>Аналог</th><th>Характеристики</th><th>Наличие</th><th>Цена</th><th>Гарантия</th></tr></thead><tbody id="agg-body"></tbody></table></div><script>
document.getElementById('manager_name').textContent=localStorage.getItem('manager_name')||'';
function toggleForm(){document.getElementById('addForm').classList.toggle('d-none')}
async function loadAggregates(){
  const res=await fetch('/api/aggregates');
  if(res.status===403){window.location.href='/';return}
  const data=await res.json();
  const tbody=document.getElementById('agg-body');
  tbody.innerHTML=data.map(a=>`<tr><td>${a.Тип||''}</td><td>${a.Модель||''}</td><td>${a.Аналог||''}</td><td>${a.Характеристики||''}</td><td>${a.Наличие||''}</td><td>${a.Цена||''}</td><td>${a.Гарантия||''}</td></tr>`).join('');
}
async function addAggregate(){
  const data={
    type:document.getElementById('type').value,
    model:document.getElementById('model').value,
    analog:document.getElementById('analog').value,
    features:document.getElementById('features').value,
    availability:document.getElementById('availability').value,
    price:document.getElementById('price').value,
    warranty:document.getElementById('warranty').value
  };
  const res=await fetch('/api/add_aggregate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await res.json();
  if(result.ok){
    toggleForm();
    loadAggregates();
  }else{
    alert('Ошибка при добавлении агрегата');
  }
}
loadAggregates();
</script></body></html>"""

DEALS_PAGE = """
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Сделки</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><nav class="navbar navbar-expand navbar-dark bg-dark mb-3"><div class="container"><a class="navbar-brand" href="#">CRM</a><div class="navbar-nav"><a class="nav-link" href="/dashboard">Дашборд</a><a class="nav-link" href="/clients">Мои клиенты</a><a class="nav-link" href="/aggregates">Агрегаты</a><a class="nav-link active" href="/deals">Сделки</a><a class="nav-link" href="/tasks">Задачи</a></div><div class="navbar-text text-white ms-auto me-3" id="manager_name"></div><button class="btn btn-outline-light btn-sm" onclick="logout()">Выйти</button></div></nav><div class="container"><h2>💰 Мои сделки</h2><button class="btn btn-success mb-3" onclick="toggleForm()">➕ Добавить сделку</button><div id="addForm" class="card p-3 mb-3 d-none"><div class="row g-2"><div class="col-md-3"><input class="form-control" placeholder="ID клиента" id="client_id"></div><div class="col-md-3"><input class="form-control" placeholder="ID товара" id="product_id"></div><div class="col-md-3"><input class="form-control" placeholder="Сумма" id="amount"></div><div class="col-md-3"><select class="form-select" id="deal_status"><option>Новая</option><option>В обработке</option><option>Закрыта</option></select></div><div class="col-12 mt-2"><button class="btn btn-primary" onclick="addDeal()">Сохранить</button><button class="btn btn-secondary" onclick="toggleForm()">Отмена</button></div></div></div><table class="table table-bordered bg-white"><thead><tr><th>ID</th><th>Клиент</th><th>Товар</th><th>Сумма</th><th>Статус</th><th>Дата</th></tr></thead><tbody id="deals-body"></tbody></table></div><script>
document.getElementById('manager_name').textContent=localStorage.getItem('manager_name')||'';
function toggleForm(){document.getElementById('addForm').classList.toggle('d-none')}
async function loadDeals(){
  const res=await fetch('/api/deals');
  if(res.status===403){window.location.href='/';return}
  const data=await res.json();
  const tbody=document.getElementById('deals-body');
  tbody.innerHTML=data.map(d=>`<tr>
    <td>${d.ID||''}</td><td>${d.Клиент_ID||''}</td><td>${d.Товар_ID||''}</td>
    <td>${d.Сумма||''}</td><td>${d.Статус||''}</td><td>${d.Дата||''}</td>
  </tr>`).join('');
}
async function addDeal(){
  const data={
    client_id:document.getElementById('client_id').value,
    product_id:document.getElementById('product_id').value,
    amount:document.getElementById('amount').value,
    status:document.getElementById('deal_status').value
  };
  const res=await fetch('/api/add_deal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await res.json();
  if(result.ok){
    toggleForm();
    loadDeals();
  }else{
    alert('Ошибка добавления сделки');
  }
}
loadDeals();
</script></body></html>"""

TASKS_PAGE = """
<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Задачи</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head><body class="bg-light"><nav class="navbar navbar-expand navbar-dark bg-dark mb-3"><div class="container"><a class="navbar-brand" href="#">CRM</a><div class="navbar-nav"><a class="nav-link" href="/dashboard">Дашборд</a><a class="nav-link" href="/clients">Мои клиенты</a><a class="nav-link" href="/aggregates">Агрегаты</a><a class="nav-link" href="/deals">Сделки</a><a class="nav-link active" href="/tasks">Задачи</a></div><div class="navbar-text text-white ms-auto me-3" id="manager_name"></div><button class="btn btn-outline-light btn-sm" onclick="logout()">Выйти</button></div></nav><div class="container"><h2>📝 Мои задачи</h2><button class="btn btn-success mb-3" onclick="toggleForm()">➕ Добавить задачу</button><div id="addForm" class="card p-3 mb-3 d-none"><div class="row g-2"><div class="col-md-6"><input class="form-control" placeholder="Описание" id="description"></div><div class="col-md-3"><input class="form-control" type="date" id="date"></div><div class="col-md-3"><input class="form-control" type="time" id="time"></div><div class="col-md-12 mt-2"><button class="btn btn-primary" onclick="addTask()">Сохранить</button><button class="btn btn-secondary" onclick="toggleForm()">Отмена</button></div></div></div><table class="table table-bordered bg-white"><thead><tr><th>Описание</th><th>Дата</th><th>Время</th><th>Статус</th><th>Действия</th></tr></thead><tbody id="tasks-body"></tbody></table></div><script>
document.getElementById('manager_name').textContent=localStorage.getItem('manager_name')||'';
function toggleForm(){document.getElementById('addForm').classList.toggle('d-none')}
async function loadTasks(){
  const res=await fetch('/api/tasks');
  if(res.status===403){window.location.href='/';return}
  const data=await res.json();
  const tbody=document.getElementById('tasks-body');
  tbody.innerHTML=data.map(t=>`<tr>
    <td>${t.Опис||''}</td><td>${t.Дата||''}</td><td>${t.Время||''}</td>
    <td>${t.Статус||''}</td>
    <td>
      ${t.Статус!=='Выполнено' ? `<button class="btn btn-sm btn-success me-1" onclick="updateTask('${t.ID}','Выполнено')">Выполнено</button>` : ''}
      ${t.Статус!=='Просрочено' ? `<button class="btn btn-sm btn-danger" onclick="updateTask('${t.ID}','Просрочено')">Просрочено</button>` : ''}
    </td>
  </tr>`).join('');
}
async function updateTask(id,newStatus){
  await fetch('/api/update_task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,status:newStatus})});
  loadTasks();
}
async function addTask(){
  const data={
    description:document.getElementById('description').value,
    date:document.getElementById('date').value,
    time:document.getElementById('time').value
  };
  const res=await fetch('/api/add_task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await res.json();
  if(result.ok){
    toggleForm();
    loadTasks();
  }else{
    alert('Ошибка добавления задачи');
  }
}
loadTasks();
</script></body></html>"""

# ---------- TELEGRAM-ОБРАБОТЧИКИ ----------
async def start(update, context):
    await update.message.reply_text("👋 Добро пожаловать в CRM!\nИспользуйте кнопки.", reply_markup=main_menu())

async def help_command(update, context):
    await update.message.reply_text(
        "📌 *CRM бот*\n\n"
        "📋 Клиенты — карточки клиентов\n"
        "🗄️ Агрегаты — база товаров\n"
        "📜 Скрипты — ответы на возражения\n"
        "📊 Аналитика — статистика\n"
        "📈 Отчёт — ежедневный отчёт\n"
        "🔗 Поиск VIN/Агрегатов — Avto.pro, Exist.ua\n"
        "🚚 Новая Почта — трекинг и срок доставки\n"
        "📱 Приложение — открыть веб-интерфейс\n"
        "🆘 Помощь — это сообщение",
        parse_mode="Markdown", reply_markup=main_menu()
    )

async def clients_start(update, context):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть CRM", web_app=WebAppInfo(url=RENDER_URL))]])
    await update.message.reply_text("📋 Нажмите кнопку, чтобы открыть базу клиентов.", reply_markup=keyboard)

async def agregat_start(update, context):
    await update.message.reply_text("🗄️ База агрегатов:", reply_markup=agregat_menu())

async def scripts_start(update, context):
    text = (
        "📜 *Скрипты продаж*\n\n"
        "• *Дорого*: «Мы даём гарантию 12 мес, цена оправдана.»\n"
        "• *Хочу по месту*: «Отправляем Новой Почтой за 1-2 дня, оплата при получении.»\n"
        "• *Не доверяю отправке*: «Работаем более 5 лет, множество отзывов.»\n"
        "• *Подумаю*: «Товар в дефиците, лучше забронировать сейчас.»\n"
        "• *Если не подойдёт?*: «Пришлём фото и VIN-сверку, возврат в течение 14 дней.»\n"
        "• *Есть ли гарантия?*: «Да, 12 месяцев официальной гарантии.»\n"
        "• *Я ещё посмотрю*: «Пришлите VIN, я проверю наличие аналогов.»\n"
        "• *Скиньте фото*: «Фото высылаем в чат.»\n"
        "• *А это точно подойдёт?*: «Сверяем по VIN и маркировке, даём 100% гарантию.»"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

async def analytics_start(update, context):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть аналитику", web_app=WebAppInfo(url=RENDER_URL + "/dashboard"))]])
    await update.message.reply_text("📊 Нажмите, чтобы посмотреть аналитику.", reply_markup=keyboard)

async def report_start(update, context):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть отчёт", web_app=WebAppInfo(url=RENDER_URL + "/dashboard"))]])
    await update.message.reply_text("📈 Ваш персональный отчёт доступен в личном кабинете.", reply_markup=keyboard)

async def search_start(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 Поиск агрегатов (Avto.pro)", url="https://avto.pro/")],
        [InlineKeyboardButton("🔎 Поиск по VIN (Exist.ua)", url="https://exist.ua/")],
    ])
    await update.message.reply_text("🔗 Выберите сервис:", reply_markup=keyboard)

async def nova_poshta_start(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Трекинг посылок", url="https://tracking.novaposhta.ua/#/uk")],
        [InlineKeyboardButton("⏱ Срок доставки", url="https://forms.novapost.world/delivery_time/#/?source=site&locale=uk")],
    ])
    await update.message.reply_text("🚚 Новая Почта – выберите действие:", reply_markup=keyboard)

async def open_webapp(update, context):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть приложение", web_app=WebAppInfo(url=RENDER_URL))]])
    await update.message.reply_text("Нажмите, чтобы открыть CRM как приложение.", reply_markup=keyboard)

async def handle_message(update, context):
    text = update.message.text
    if text == "📋 Клиенты": await clients_start(update, context)
    elif text == "🗄️ Агрегаты": await agregat_start(update, context)
    elif text == "📜 Скрипты": await scripts_start(update, context)
    elif text == "📊 Аналитика": await analytics_start(update, context)
    elif text == "📈 Отчёт": await report_start(update, context)
    elif text == "🔗 Поиск VIN/Агрегатов": await search_start(update, context)
    elif text == "🚚 Новая Почта": await nova_poshta_start(update, context)
    elif text == "🆘 Помощь": await help_command(update, context)
    elif text == "📱 Приложение": await open_webapp(update, context)
    elif text == "📋 Все товары": await show_all_products(update, context)
    elif text == "✏️ Изменить статус": await change_status_start(update, context)
    elif text == "➕ Добавить товар":
        await update.message.reply_text("Выберите тип товара:", reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"]], one_time_keyboard=True, resize_keyboard=True))
        return TYPE
    elif text == "🔍 Поиск по модели":
        await update.message.reply_text("Введите модель для поиска:")
        return 0
    elif text in ("🔙 Назад", "❌ Отмена"):
        if context.user_data: context.user_data.clear()
        await update.message.reply_text("Главное меню:", reply_markup=main_menu())
        return ConversationHandler.END
    else:
        await update.message.reply_text("Используйте кнопки меню.")

# ---------- СТАРЫЕ ФУНКЦИИ ----------
async def show_all_products(update, context):
    rows = main_sheet.get_all_records()
    if not rows:
        await update.message.reply_text("📭 Товаров пока нет.")
        return
    keyboard = []
    for row in rows[:10]:
        label = f"{row['Модель']} ({row['Статус']}) - {row['Цена']}₴"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"detail_{row['_row']}")])
    await update.message.reply_text("📋 Все товары:", reply_markup=InlineKeyboardMarkup(keyboard))

async def product_detail(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "show_more":
        await query.edit_message_text("Функция листания не реализована.")
        return
    row_num = int(data.split("_")[1])
    try:
        row_values = main_sheet.row_values(row_num)
        if len(row_values) < 7:
            await query.edit_message_text("Ошибка: неполные данные.")
            return
        _, typ, model, price, status, desc, photo_id = row_values[:7]
        text = f"*{typ}* — {model}\nЦена: {price}₴\nСтатус: {status}\nОписание: {desc}"
        if photo_id:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo_id, caption=text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка деталей: {e}")
        await query.edit_message_text("Не удалось загрузить данные.")

async def add_product_start(update, context):
    await update.message.reply_text("Выберите тип товара:", reply_markup=ReplyKeyboardMarkup([["Генератор", "Стартер"]], one_time_keyboard=True, resize_keyboard=True))
    return TYPE

async def add_type(update, context):
    txt = update.message.text
    if txt in ("🔙 Назад", "❌ Отмена"): return await cancel_add(update, context)
    if txt not in ("Генератор", "Стартер"):
        await update.message.reply_text("Пожалуйста, выберите Генератор или Стартер.")
        return TYPE
    context.user_data["type"] = txt
    await update.message.reply_text("Введите модель:", reply_markup=agregat_menu())
    return MODEL

async def add_model(update, context):
    txt = update.message.text.strip()
    if txt in ("🔙 Назад", "❌ Отмена"): return await cancel_add(update, context)
    if not txt:
        await update.message.reply_text("Модель не может быть пустой.")
        return MODEL
    context.user_data["model"] = txt
    await update.message.reply_text("Введите цену (число, в гривнах):")
    return PRICE

async def add_price(update, context):
    txt = update.message.text.strip()
    if txt in ("🔙 Назад", "❌ Отмена"): return await cancel_add(update, context)
    try:
        price = int(txt)
    except ValueError:
        await update.message.reply_text("Цена должна быть целым числом.")
        return PRICE
    context.user_data["price"] = price
    await update.message.reply_text("Выберите статус:", reply_markup=ReplyKeyboardMarkup([[s] for s in STATUSES], one_time_keyboard=True, resize_keyboard=True))
    return STATUS

async def add_status(update, context):
    txt = update.message.text.strip()
    if txt in ("🔙 Назад", "❌ Отмена"): return await cancel_add(update, context)
    if txt not in STATUSES:
        await update.message.reply_text("Выберите статус из предложенных.")
        return STATUS
    context.user_data["status"] = txt
    await update.message.reply_text("Введите описание (или 'нет'):", reply_markup=agregat_menu())
    return DESCRIPTION

async def add_description(update, context):
    txt = update.message.text.strip()
    if txt in ("🔙 Назад", "❌ Отмена"): return await cancel_add(update, context)
    if txt.lower() in ("нет", "-", "no", "нету"): txt = ""
    context.user_data["description"] = txt
    await update.message.reply_text("Отправьте фото товара (или напишите 'нет'):")
    return PHOTO

async def add_photo(update, context):
    # Проверка на кнопки выхода (если сообщение текстовое)
    if update.message and update.message.text and update.message.text.strip() in ("❌ Отмена", "🔙 Назад"):
        return await cancel_add(update, context)

    photo_id = ""
    # Если пришло фото — берём file_id
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    # Если текст — проверяем, что это "нет"
    elif update.message.text and update.message.text.strip().lower() in ("нет", "no", "-"):
        pass  # пропускаем фото
    else:
        # Всё остальное — просим прислать фото или написать "нет"
        await update.message.reply_text("Отправьте фото или напишите 'нет'.")
        return PHOTO  # остаёмся в состоянии PHOTO

    # Сохраняем товар
    data = context.user_data
    all_rows = main_sheet.get_all_records()
    new_id = max([int(r["ID"]) for r in all_rows if r["ID"].isdigit()] + [0]) + 1
    try:
        main_sheet.append_row([
            str(new_id), data["type"], data["model"], str(data["price"]),
            data["status"], data["description"], photo_id
        ])
        await update.message.reply_text(
            f"✅ Товар *{data['model']}* добавлен! (ID {new_id})",
            parse_mode="Markdown", reply_markup=agregat_menu()
        )
    except Exception as e:
        logger.error(f"Ошибка сохранения товара: {e}")
        await update.message.reply_text("❌ Не удалось сохранить товар. Попробуйте ещё раз.", reply_markup=agregat_menu())

    # Очищаем данные и выходим из диалога
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_add(update, context):
    # На случай, если cancel_add вызывается из callback-а (но у нас всегда сообщение)
    await update.message.reply_text("Добавление отменено.", reply_markup=main_menu())
    context.user_data.clear()
    return ConversationHandler.END

async def change_status_start(update, context):
    rows = main_sheet.get_all_records()
    if not rows:
        await update.message.reply_text("Нет товаров.")
        return
    keyboard = []
    for row in rows:
        label = f"{row['Модель']} ({row['Статус']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"status_{row['_row']}")])
    await update.message.reply_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(keyboard))

async def status_select_product(update, context):
    query = update.callback_query
    await query.answer()
    row_num = int(query.data.split("_")[1])
    context.user_data["edit_row"] = row_num
    keyboard = [[InlineKeyboardButton(s, callback_data=f"setstatus_{s}")] for s in STATUSES]
    await query.edit_message_text("Новый статус:", reply_markup=InlineKeyboardMarkup(keyboard))

async def status_set_new(update, context):
    query = update.callback_query
    await query.answer()
    new_status = query.data.split("_")[1]
    row_num = context.user_data.get("edit_row")
    if not row_num:
        await query.edit_message_text("Ошибка сессии.")
        return
    try:
        main_sheet.update_cell(row_num, 5, new_status)
        await query.edit_message_text(f"✅ Статус изменён на *{new_status}*", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка обновления статуса: {e}")
        await query.edit_message_text("❌ Не удалось обновить статус.")
    finally:
        context.user_data.pop("edit_row", None)

async def search_model_input(update, context):
    query = update.message.text.strip()
    rows = main_sheet.get_all_records()
    results = [r for r in rows if query.lower() in r["Модель"].lower()]
    if not results:
        await update.message.reply_text("🔍 Ничего не найдено.", reply_markup=agregat_menu())
        return ConversationHandler.END
    keyboard = []
    for r in results[:5]:
        label = f"{r['Модель']} ({r['Статус']}) - {r['Цена']}₴"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"detail_{r['_row']}")])
    await update.message.reply_text("🔍 Результаты поиска:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ---------- ЗАПУСК ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    port = int(os.environ.get("PORT", 8000))
    httpd = HTTPServer(("0.0.0.0", port), CRMHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    logger.info(f"Веб-интерфейс запущен на порту {port}")

    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить товар$"), add_product_start)],
        states={
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_type)],
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_model)],
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
            STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_status)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_description)],
            PHOTO: [
                MessageHandler(filters.PHOTO, add_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_photo),
            ],
        },
        fallbacks=[
        CommandHandler("cancel", cancel_add),
        MessageHandler(filters.Regex("^(❌ Отмена|🔙 Назад)$"), cancel_add)
    ],
    )

    search_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Поиск по модели$"), lambda u, c: search_model_input(u, c))],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_model_input)]},
        fallbacks=[],
    )

    app.add_handler(add_conv)
    app.add_handler(search_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", lambda u, c: u.message.reply_text(SHEET_URL)))
    app.add_handler(CallbackQueryHandler(product_detail, pattern="^detail_"))
    app.add_handler(CallbackQueryHandler(status_select_product, pattern="^status_"))
    app.add_handler(CallbackQueryHandler(status_set_new, pattern="^setstatus_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
