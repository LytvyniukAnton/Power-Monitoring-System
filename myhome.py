import time
import threading
import sqlite3
import telebot
import json
import logging
from logging.handlers import RotatingFileHandler
from telebot import types
from flask import Flask, request, render_template, jsonify
from datetime import datetime, timedelta
import pytz
import os
import io
from dotenv import load_dotenv

# ================= CONFIG (LOAD FROM ENV) =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

LOG_DIR = os.path.join(BASE_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

TELEGRAM_TOKEN = os.getenv("TG_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
API_SECRET = os.getenv("API_SECRET")

PORT = int(os.getenv("PORT", 5000))
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", 180))
REAL_OUTAGE_THRESHOLD = float(os.getenv("REAL_OUTAGE_THRESHOLD", 5.0))
LOCATION_NAME = os.getenv("LOCATION_NAME", "") 

TZ = pytz.timezone("Europe/Kyiv")
DB_PATH = os.path.join(BASE_DIR, "power_monitor.db")
STATE_FILE = os.path.join(BASE_DIR, "system_state.json")

# ================= LOGGING SETUP =================

# Читаємо ім'я файлу з .env (за замовчуванням server.log)
LOG_FILE_NAME = os.getenv("LOG_FILE", "server.log")

# Тепер логи пишуться і в файл (для logrotate), і в консоль
logger = logging.getLogger("PowerMonitor")
logger.setLevel(logging.INFO)

# Форматування
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Файловий хендлер
log_path = os.path.join(LOG_DIR, LOG_FILE_NAME)
file_handler = logging.FileHandler(log_path)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Консольний хендлер
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.info(f"Logging initialized. Writing to: {log_path}")

# === СЛОВНИК ПЕРЕКЛАДУ ПРИЧИН ===
REASON_TRANSLATION = {
    "Power On": "⚡Увімкнення світла (звичайний запуск)",
    "Brownout (Voltage Dip)": "📉Перепад напруги (світло моргнуло)",
    "Software Reset": "🔄Програмне перезавантаження",
    "Watchdog (Interrupt)": "⚠️ Системний збій (WDT)",
    "Watchdog (Task)": "⚠️ Системний збій (Task WDT)",
    "Watchdog (Other)": "⚠️ Системний збій (Other)",
    "Exception/Panic": "❌Критична помилка (Panic)",
    "Deep Sleep": "🌙Вихід зі сну",
    "Unknown": "❓Невідома причина",
    "N/A": "Невідомо"
}

# ================= INIT =================

app = Flask(__name__, 
            template_folder='templates', 
            static_folder='static',
            static_url_path='/static')
bot = telebot.TeleBot(TELEGRAM_TOKEN)
lock = threading.Lock()
last_auth_error_time = 0

# ================= STATE =================

def load_state():
    default_state = {
        "is_online": True,
        "last_heartbeat": time.time(),
        "outage_start": None,
        "online_start": time.time(),
        "last_boot_id": None,
        "last_ip": None,
        "notification_sent": False,
	"last_outage_msg_id": None
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
                for k, v in default_state.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return default_state

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except: pass

state = load_state()

# ================= DATABASE =================

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = db()
        conn.execute("CREATE TABLE IF NOT EXISTS outages (start_time TEXT, end_time TEXT, duration_minutes REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS system_events (time TEXT, duration_minutes REAL, reason TEXT, raw_reason TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS ip_history (time TEXT, ip TEXT)")
        conn.commit()
        conn.close()
    except: pass

# ================= HELPERS =================

def fmt(sec: float) -> str:
    if sec < 0: sec = 0
    m = int(sec // 60); h = m // 60
    return f"{h}г {m % 60}хв" if h else f"{m}хв"

def get_header():
    return f"🏠 {LOCATION_NAME}\n" if LOCATION_NAME else ""

# --- КЛАВІАТУРИ ---

# 1. Для СПОВІЩЕНЬ (Зелені/Червоні/Жовті повідомлення)
def kb_notification():
    k = types.InlineKeyboardMarkup(row_width=2)
    # Ті самі кнопки, що в меню
    btn_stats = types.InlineKeyboardButton("📊 Звіт", callback_data="stats")
    btn_last = types.InlineKeyboardButton("📜 Історія", callback_data="history")
    k.add(btn_stats, btn_last)
    # Кнопка оновлення саме цього повідомлення
    btn_update = types.InlineKeyboardButton("🔄 Оновити статус", callback_data="status")
    k.add(btn_update)
    return k

# 2. Для МЕНЮ (Панель керування - закріплене)
def kb_menu():
    k = types.InlineKeyboardMarkup(row_width=2)
    btn_stats = types.InlineKeyboardButton("📊 Звіт за день", callback_data="stats")
    btn_last = types.InlineKeyboardButton("📜 Історія (10)", callback_data="history")
    k.add(btn_stats, btn_last)
    btn_status = types.InlineKeyboardButton("🔄 Стан зараз", callback_data="status")
    k.add(btn_status)
    return k

# ================= WEB & API (FOR HTML DASHBOARD) =================

@app.route("/")
def index():
    # Беремо назву з .env, або ставимо дефолтну
    title = os.getenv("LOCATION_NAME", "Energy Monitor")
    return render_template("index.html", page_title=title)

@app.route("/api/stats")
def api_stats():
    # Отримуємо параметри дати
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    
    now = datetime.now(TZ)
    PROJECT_START_DATE = "2026-01-26" # Фіксуємо для бекенда теж
    
    # Логіка дат за замовчуванням (7 днів)
    if not start_str or not end_str:
        end_dt = now
        start_dt = end_dt - timedelta(days=7)
    else:
        try:
            # Тут має бути 12 пробілів від початку рядка (4 для def, 4 для else, 4 для try)
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=TZ)
            end_dt = datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=TZ)
        except:
             end_dt = now
             start_dt = end_dt - timedelta(days=7)

    # Додаємо обмеження, щоб не брати сміття раніше 26.01
    actual_start = max(start_dt, datetime.strptime(PROJECT_START_DATE, "%Y-%m-%d").replace(tzinfo=TZ))

    # Формуємо SQL запит
    conn = db()
    cursor = conn.cursor()
    
    # Вибираємо відключення, які перетинаються з діапазоном
    query = """
        SELECT start_time, end_time, duration_minutes 
        FROM outages 
        WHERE start_time <= ? AND end_time >= ?
        ORDER BY start_time DESC
    """
    cursor.execute(query, (end_dt.isoformat(), actual_start.isoformat()))
    rows = cursor.fetchall()
    conn.close()

    outages_list = []
    total_off_minutes = 0
    # total_events = 0

    # Додаємо активне відключення, якщо воно є в базі або в стейті
    if not state["is_online"] and state.get("notification_sent"):
        current_dur = (time.time() - state["outage_start"]) / 60
        outages_list.append({
            "start": datetime.fromtimestamp(state["outage_start"], TZ).isoformat(),
            "end": None,
            "duration_min": round(current_dur, 2),
            "is_active": True
        })
        total_off_minutes += current_dur

    for row in rows:
        outages_list.append({
            "start": row['start_time'],
            "end": row['end_time'],
            "duration_min": row['duration_minutes'],
            "is_active": False
        })
        total_off_minutes += row['duration_minutes']

    # Розрахунок загального часу діапазону для %
    total_range_min = (end_dt - actual_start).total_seconds() / 60
    if total_range_min <= 0: total_range_min = 1
    
    off_percent = min(100, (total_off_minutes / total_range_min) * 100)

    return jsonify({
        "is_online": state["is_online"],
        "last_update": now.strftime("%Y-%m-%dT%H:%M:%S"), # ISO формат для надійного JS
        "stats": {
            "on_percent": round(100 - off_percent, 1),
            "off_percent": round(off_percent, 1),
            "on_hours": round((total_range_min - total_off_minutes) / 60, 1),
            "off_hours": round(total_off_minutes / 60, 1),
            "total_events": len(outages_list),
            "avg_duration": fmt((total_off_minutes / len(outages_list) * 60)) if outages_list else "0"
        },
        "meta": {
            "display_range": f"{actual_start.strftime('%d.%m')} - {end_dt.strftime('%d.%m')}"
        },
        "outages": outages_list
    })

# ================= API (POST) =================

@app.route("/ping", methods=["POST"])
def ping():
    global last_auth_error_time

    # === DEBUG DEBUG DEBUG ===
    # 1. Отримуємо IP так, як його бачить Nginx
    # real_ip = request.headers.get('X-Real-IP') or request.remote_addr
    
    # 2. Читаємо сире тіло запиту (RAW JSON)
    # raw_data = request.get_data(as_text=True)
    
    # logger.info(f"🔍 DEBUG PING:")
    # logger.info(f"🌍 Connection IP (Nginx sees): {real_ip}")
    # logger.info(f"📦 Payload (ESP sent): {raw_data}")
    # =========================

    data = request.get_json(silent=True)
    if not data: return "Bad Request: No JSON", 400

    if data.get("key") != API_SECRET:
        now = time.time()
        if now - last_auth_error_time > 300:
            last_auth_error_time = now
            try:
                ip = request.headers.get('X-Real-IP') or request.remote_addr
                bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ **AUTH ERROR**\nIP: `{ip}`", parse_mode="Markdown")
            except: pass
        return "Forbidden", 403

    uptime = int(data.get("uptime", 0))
    boot_id = data.get("boot_id")
    first = str(data.get("first")) == "1" 
    ip = data.get("ip")
    raw_reason = data.get("reason", "N/A")
    reason_ua = REASON_TRANSLATION.get(raw_reason, raw_reason)

    now = time.time()

    with lock:
        old_ip = state.get("last_ip")
        state["last_heartbeat"] = now

        if ip and ip != old_ip:
            state["last_ip"] = ip
            try:
                conn = db()
                conn.execute("INSERT INTO ip_history VALUES (?, ?)", (datetime.now(TZ).isoformat(), ip))
                conn.commit(); conn.close()
            except: pass

        if not state["is_online"]:
            start_outage = state["outage_start"] or (now - 60)
            time_restored = now
            
            is_hard_reboot = (first or (boot_id and boot_id != state.get("last_boot_id")))
            if is_hard_reboot:
                adjust = uptime if uptime > 60 else 120
                time_restored = now - adjust

            duration_off = (time_restored - start_outage) / 60

            # 1. Довге відключення (було сповіщення)
            if state.get("notification_sent", False):
                
                # === FIX START: Фільтрація технічних збоїв ===
                TECH_ERRORS = ["Brownout", "Software Reset", "Watchdog", "Exception", "Panic"]
                is_tech_error = any(err in raw_reason for err in TECH_ERRORS)

                if is_tech_error:
                    # Це був ТЕХНІЧНИЙ ЗБІЙ. Таймер "online_start" НЕ чіпаємо!
                    try:
                        conn = db()
                        conn.execute("INSERT INTO system_events VALUES (?, ?, ?, ?)",
                                     (datetime.fromtimestamp(time_restored, TZ).isoformat(),
                                      duration_off, reason_ua, raw_reason))
                        conn.commit(); conn.close()
                    except: pass

                    # Жовте повідомлення
                    try:
                        msg = (f"{get_header()}⚠️ **Зв'язок відновлено (після збою)**\n"
                               f"⏱ Не було зв'язку: {fmt(duration_off * 60)}\n"
                               f"ℹ️ Причина: {reason_ua}\n"
                               f"✅ У статистику відключень не записано.")
                        
                        reply_to = state.get("last_outage_msg_id")
                        bot.send_message(TELEGRAM_CHAT_ID, msg,
                                         parse_mode="Markdown",
                                         reply_markup=kb_notification(),
                                         reply_to_message_id=reply_to)
                        state["last_outage_msg_id"] = None
                    except Exception as e: print(f"❌ SEND ERROR: {e}")

                else:
                    # Це справжнє відключення - оновлюємо таймер
                    state["online_start"] = time_restored 

                    try:
                        conn = db()
                        conn.execute("INSERT INTO outages VALUES (?, ?, ?)",
                                     (datetime.fromtimestamp(start_outage, TZ).isoformat(),
                                      datetime.fromtimestamp(time_restored, TZ).isoformat(), duration_off))
                        conn.commit(); conn.close()
                    except: pass

                    restored_dt = datetime.fromtimestamp(time_restored, TZ)
                    try:
                        msg = (f"{get_header()}🟢 **Відновлено електропостачання**\n"
                               f"⏰ Увімкнули приблизно о {restored_dt.strftime('%H:%M, %d.%m')}\n"
                               f"🪫 Світла не було: {fmt(duration_off * 60)}")
                        if raw_reason != "N/A": msg += f"\nℹ️ Інфо: {reason_ua}"

                        reply_to = state.get("last_outage_msg_id")
                        bot.send_message(TELEGRAM_CHAT_ID, msg,
                                         parse_mode="Markdown",
                                         reply_markup=kb_notification(),
                                         reply_to_message_id=reply_to)
                        state["last_outage_msg_id"] = None
                    except Exception as e: print(f"❌ SEND ERROR: {e}")
                # === FIX END ===

            # 2. Короткий збій (глюк, сповіщення не було)
            else:
                try:
                    conn = db()
                    conn.execute("INSERT INTO system_events VALUES (?, ?, ?, ?)", 
                                 (datetime.fromtimestamp(time_restored, TZ).isoformat(), 
                                  duration_off, reason_ua, raw_reason))
                    conn.commit(); conn.close()
                except: pass
                
                try:
                    msg = (f"{get_header()}⚠️ **ЗАФІКСОВАНО ТЕХНІЧНИЙ ЗБІЙ**\n"
                           f"⏱ Втрата зв'язку: {fmt(duration_off * 60)}\n"
                           f"ℹ️ Причина: {reason_ua}\n"
                           f"✅ Таймер світла працює далі (статистику не збито).")
                    bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown", reply_markup=kb_menu())
                except Exception as e: print(f"❌ SEND ERROR: {e}")

            state["is_online"] = True
            state["outage_start"] = None
            state["notification_sent"] = False 

        if boot_id: state["last_boot_id"] = boot_id
        save_state()

    return "OK", 200

# ================= WATCHDOG =================

def watchdog():
    while True:
        time.sleep(10)
        with lock:
            if state["is_online"] and time.time() - state["last_heartbeat"] > TIMEOUT_SECONDS:
                state["is_online"] = False
                state["outage_start"] = state["last_heartbeat"]
                state["notification_sent"] = False
                save_state() 

            if not state["is_online"] and not state.get("notification_sent", False):
                current_duration_min = (time.time() - state["outage_start"]) / 60.0
                
                if current_duration_min > REAL_OUTAGE_THRESHOLD:
                    state["notification_sent"] = True 
                    
                    was_on_duration = ""
                    if state.get("online_start"):
                        duration_on = state["outage_start"] - state["online_start"]
                        if duration_on > 300: 
                            was_on_duration = f"\n🔋 Світло було: {fmt(duration_on)}"

                    off_dt = datetime.fromtimestamp(state['outage_start'], TZ)
                    try:
                        sent_msg = bot.send_message(TELEGRAM_CHAT_ID,
                            f"{get_header()}🔴 **Відключили електропостачання**\n"
                            f"⏰ Вимкнули приблизно о {off_dt.strftime('%H:%M, %d.%m')}{was_on_duration}",
                            parse_mode="Markdown", reply_markup=kb_notification())
                        
                        # Зберігаємо ID повідомлення для майбутнього Reply
                        state["last_outage_msg_id"] = sent_msg.message_id
                        
                    except Exception as e: print(f"❌ SEND ERROR: {e}")
                    
                    save_state()

# ================= REPORT GENERATION =================

def generate_daily_report_html():
    now = datetime.now(TZ)
    # Початок сьогоднішнього дня (00:00:00)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now # До поточного моменту

    conn = db()
    cursor = conn.cursor()
    
    # Шукаємо відключення:
    # 1. Ті, що закінчилися сьогодні (end_time > 00:00)
    # 2. Ті, що почалися сьогодні (start_time >= 00:00)
    # 3. Ті, що ще тривають (активні)
    
    # Беремо трохи з запасом (вчора), а фільтрувати будемо в Python
    query = """
        SELECT start_time, end_time, duration_minutes 
        FROM outages 
        WHERE end_time >= ? OR start_time >= ?
        ORDER BY start_time DESC
    """
    cursor.execute(query, (start_of_day.isoformat(), start_of_day.isoformat()))
    rows = cursor.fetchall()
    conn.close()

    total_off_sec = 0
    event_list_html = ""

    # Додаємо поточне активне відключення, якщо є
    active_event = None
    if not state["is_online"] and state.get("notification_sent"):
        active_start = datetime.fromtimestamp(state["outage_start"], TZ)
        active_event = {
            "start": active_start,
            "end": now,
            "is_active": True
        }

    # Обробка завершених відключень
    for row in rows:
        e_start = datetime.fromisoformat(row['start_time']).astimezone(TZ)
        e_end = datetime.fromisoformat(row['end_time']).astimezone(TZ)

        # Перевіряємо перетин з сьогоднішнім днем
        # Ефективний початок (не раніше 00:00)
        eff_start = max(e_start, start_of_day)
        # Ефективний кінець (не пізніше зараз)
        eff_end = min(e_end, end_of_day)

        if eff_end > eff_start:
            dur = (eff_end - eff_start).total_seconds()
            total_off_sec += dur
            
            # Форматуємо рядок для HTML
            # Якщо почалося вчора - показуємо оригінальний час, але додаємо помітку
            time_str = f"{e_start.strftime('%H:%M')} - {e_end.strftime('%H:%M')}"
            note = ""
            if e_start < start_of_day:
                note = f"<br><small>(почалось {e_start.strftime('%d.%m')})</small>"
            
            event_list_html += f"""
            <div class="event-row">
                <div class="icon red">🔴</div>
                <div class="info">
                    <div class="time">{time_str}{note}</div>
                    <div class="dur">Тривалість: {fmt(dur)} (сьогодні)</div>
                </div>
            </div>
            """

    # Обробка активного (якщо є)
    if active_event:
        e_start = active_event["start"]
        e_end = active_event["end"]
        
        eff_start = max(e_start, start_of_day)
        eff_end = min(e_end, end_of_day)
        
        if eff_end > eff_start:
            dur = (eff_end - eff_start).total_seconds()
            total_off_sec += dur
            
            time_str = f"{e_start.strftime('%H:%M')} - ..."
            note = ""
            if e_start < start_of_day:
                note = f"<br><small>(почалось {e_start.strftime('%d.%m')})</small>"

            event_list_html = f"""
            <div class="event-row active">
                <div class="icon red pulse">⚡</div>
                <div class="info">
                    <div class="time">{time_str}{note}</div>
                    <div class="dur">Триває вже: {fmt(dur)} (сьогодні)</div>
                </div>
            </div>
            """ + event_list_html

    # Підсумки
    # total_period_sec = (end_of_day - start_of_day).total_seconds()
    # off_percent = (total_off_sec / total_period_sec) * 100
    # on_percent = 100 - off_percent

    # --- ЗМІНА ЛОГІКИ: ДІЛИМО НА 24 ГОДИНИ (86400 сек) ---
    TOTAL_DAY_SECONDS = 24 * 60 * 60  # 86400
    
    # Відсоток відключень від ВСІЄЇ ДОБИ
    off_percent = (total_off_sec / TOTAL_DAY_SECONDS) * 100
    if off_percent > 100: off_percent = 100 # На випадок збоїв часу
    
    # Решта - це світло (включно з майбутнім)
    on_percent = 100 - off_percent
    
    # Час "Світло було/буде" - це 24г мінус "Світла не було"
    total_on_sec = TOTAL_DAY_SECONDS - total_off_sec

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: sans-serif; background: #f4f4f5; padding: 20px; color: #333; }}
            .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 15px; }}
            h2 {{ margin-top: 0; color: #2563eb; }}
            .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }}
            .stat-box {{ background: #eff6ff; padding: 15px; border-radius: 8px; text-align: center; }}
            .stat-val {{ font-size: 24px; font-weight: bold; display: block; }}
            .stat-label {{ font-size: 12px; color: #666; }}
            .red {{ color: #dc2626; background: #fef2f2; }}
            .green {{ color: #16a34a; background: #dcfce7; }}
            
            .event-row {{ display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid #eee; }}
            .event-row:last-child {{ border-bottom: none; }}
            .icon {{ width: 30px; font-size: 18px; }}
            .time {{ font-weight: bold; }}
            .dur {{ font-size: 13px; color: #666; }}
            .active {{ background: #fff1f2; padding: 10px; border-radius: 8px; border: 1px solid #fecdd3; }}
            .pulse {{ animation: pulse 1s infinite; }}
            @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>📊 Звіт: {LOCATION_NAME}</h2>
            <div>📅 Дата: <b>{now.strftime('%d.%m.%Y')}</b></div>
            <div>⏱ Час звіту: {now.strftime('%H:%M')}</div>
        </div>

        <div class="stats-grid">
            <div class="stat-box green">
                <span class="stat-val">{round(on_percent, 1)}%</span>
                <span class="stat-label">Світло було</span>
                <small>{fmt(total_on_sec)}</small>
            </div>
            <div class="stat-box red">
                <span class="stat-val">{round(off_percent, 1)}%</span>
                <span class="stat-label">Без світла</span>
                <small>{fmt(total_off_sec)}</small>
            </div>
        </div>

        <div class="card">
            <h3>📜 Історія за сьогодні</h3>
            {event_list_html if event_list_html else "<div style='text-align:center; color:#999'>Світло не вимикали! 🎉</div>"}
        </div>
    </body>
    </html>
    """
    return io.BytesIO(html.encode('utf-8'))

# ================= MENU & CONTROLS =================

# 1. КОМАНДА /menu (ДЛЯ ЗАКРІПЛЕННЯ)
@bot.message_handler(commands=['menu'])
@bot.channel_post_handler(commands=['menu'])
def send_menu(message):
    try:
        header = get_header()
        msg = f"{header}🎛 **Панель керування**\n\n👇 Оберіть дію:"
        # Відправляємо з кнопками МЕНЮ (kb_menu)
        bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=kb_menu())
    except Exception as e:
        pass

# ================= BUTTON HANDLER =================

@bot.callback_query_handler(func=lambda c: True)
def handle_buttons(call):
    chat_id = call.message.chat.id
    
    # === A. КНОПКА СТАТУСУ (ОНОВИТИ) ===
    if call.data == "status":
        with lock:
            now = time.time()
            header = get_header().replace("**", "") 
            
            if state["is_online"]:
                start_t = state.get("online_start", state["last_heartbeat"])
                dur = now - start_t
                start_dt = datetime.fromtimestamp(start_t, TZ).strftime('%H:%M, %d.%m')
                text_main = (f"🟢 Світло є вже: {fmt(dur)}\n"
                             f"⏰ З'явилось о: {start_dt}")
            else:
                start_t = state["outage_start"] or now
                dur = now - start_t
                start_dt = datetime.fromtimestamp(start_t, TZ).strftime('%H:%M, %d.%m')
                status_text = f"🔴 Світла немає вже: {fmt(dur)}" if state.get("notification_sent") else f"🟡 Немає зв'язку: {fmt(dur)} (перевірка...)"
                text_main = (f"{status_text}\n⏰ Зникло о: {start_dt}")
            
            # Якщо це меню - оновлюємо текст і показуємо kb_menu
            if "Панель керування" in call.message.text or "Оберіть дію" in call.message.text:
                 full_text = f"{header}🎛 **Панель керування**\n\n{text_main}\n\n👇 Оберіть дію:"
                 try: 
                     bot.edit_message_text(full_text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=kb_menu())
                     bot.answer_callback_query(call.id, "✅ Дані оновлено")
                 except: 
                     bot.answer_callback_query(call.id, "Вже актуально")
            else:
                 # Якщо це сповіщення - показуємо Alert і не чіпаємо кнопки (kb_notification лишається)
                 alert_text = text_main.replace("\n"," \n")
                 try: bot.answer_callback_query(call.id, alert_text, show_alert=True)
                 except: pass
                 
    # === B. КНОПКА ЗВІТУ (ФАЙЛ) ===
    elif call.data == "stats":
        try:
            bot.answer_callback_query(call.id, "📊 Генерую звіт...")
            file_obj = generate_daily_report_html()
            # ФІКС ЧАСУ ДЛЯ НАЗВИ ФАЙЛУ (TZ)
            file_obj.name = f"Звіт_{datetime.now(TZ).strftime('%d_%m')}.html"
            bot.send_document(chat_id, file_obj, caption="📊 **Ваш звіт за сьогодні**", parse_mode="Markdown")
        except Exception as e:
            pass

     # === C. КНОПКА ІСТОРІЇ (ТЕКСТ 10 шт) ===
    elif call.data == "history":
        try:
            bot.answer_callback_query(call.id, "📜 Шукаю дані...")
            
            conn = db()
            cursor = conn.cursor()
            # Беремо 10, але потім підріжемо якщо треба
            cursor.execute("SELECT start_time, end_time, duration_minutes FROM outages ORDER BY start_time DESC LIMIT 10")
            rows = cursor.fetchall()
            conn.close()

            msg = f"{get_header()}📜 **Останні 10 відключень:**\n```\n"
            
            # --- ЛОГІКА АКТИВНОГО ВІДКЛЮЧЕННЯ ---
            is_active_outage = not state["is_online"] and state.get("notification_sent")
            
            if is_active_outage:
                start_ts = state["outage_start"]
                start_dt = datetime.fromtimestamp(start_ts, TZ)
                duration = time.time() - start_ts
                # Вирівнювання з додатковим пробілом: {HH:MM}- ...  |
                msg += f"{start_dt.strftime('%d.%m %H:%M')}- ...  | {fmt(duration)}\n"
                
                # Якщо є активне, залишаємо тільки 9 архівних (щоб сума була 10)
                if len(rows) > 9:
                    rows = rows[:9]
            # -------------------------------------

            if not rows and not is_active_outage: msg += "Записів немає."
            else:
                for row in rows:
                    start = datetime.fromisoformat(row[0]).astimezone(TZ)
                    end_str = "??"
                    if row[1]:
                        end = datetime.fromisoformat(row[1]).astimezone(TZ)
                        end_str = end.strftime('%H:%M') 
                    dur = row[2]
                    msg += f"{start.strftime('%d.%m %H:%M')}-{end_str} | {fmt(dur*60)}\n"
            msg += "```"
            
            bot.send_message(chat_id, msg, parse_mode="Markdown")
        except Exception as e: 
            print(f"History error: {e}")

# ================= OTHER COMMANDS =================

@bot.message_handler(commands=['last', 'history'])
@bot.channel_post_handler(commands=['last', 'history'])
def handle_last_events(message):
    try:
        conn = db()
        cursor = conn.cursor()
        cursor.execute("SELECT start_time, end_time, duration_minutes FROM outages ORDER BY start_time DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()

        msg = f"{get_header()}📜 **Останні 10 відключень:**\n```\n"
        
        is_active_outage = not state["is_online"] and state.get("notification_sent")
        
        if is_active_outage:
            start_ts = state["outage_start"]
            start_dt = datetime.fromtimestamp(start_ts, TZ)
            duration = time.time() - start_ts
            # Вирівнювання з додатковим пробілом
            msg += f"{start_dt.strftime('%d.%m %H:%M')}- ...  | {fmt(duration)}\n"
            if len(rows) > 9:
                rows = rows[:9]

        if not rows and not is_active_outage: msg += "Записів немає."
        else:
            for row in rows:
                start = datetime.fromisoformat(row[0]).astimezone(TZ)
                end_str = "??"
                if row[1]:
                    end = datetime.fromisoformat(row[1]).astimezone(TZ)
                    end_str = end.strftime('%H:%M')
                dur = row[2]
                msg += f"{start.strftime('%d.%m %H:%M')}-{end_str} | {fmt(dur*60)}\n"
        msg += "```"
        
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")

@bot.message_handler(commands=['debug', 'info'])
@bot.channel_post_handler(commands=['debug', 'info'])
def handle_debug(message):
    with lock:
        boot_id = state.get("last_boot_id", "Unknown")
        ip = state.get("last_ip", "Unknown")
        reason = state.get("last_reason", "N/A")
        msg = (f"{get_header()}🛠 **Технічна інфо:**\n🌐 IP: `{ip}`\n🆔 Boot ID: `{boot_id}`\nℹ️ Last Reboot: {reason}")
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=["status", "start"])
def handle_status_private(message):
    with lock:
        now = time.time()
        header = get_header()
        if state["is_online"]:
            dur = now - state.get("online_start", state["last_heartbeat"])
            msg = f"{header}🟢 Світло є вже: {fmt(dur)}"
        else:
            dur = now - (state["outage_start"] or now)
            msg = f"{header}🔴 Світла немає вже: {fmt(dur)}"
    # Приватні команди теж отримують розширену клавіатуру
    try: bot.send_message(message.chat.id, msg, reply_markup=kb_notification())
    except: pass

# ================= AUTO-STARTUP =================

init_db()

if not any(t.name == "WatchdogThread" for t in threading.enumerate()):
    logger.info("Starting Watchdog thread...")
    threading.Thread(target=watchdog, daemon=True, name="WatchdogThread").start()

if not any(t.name == "BotThread" for t in threading.enumerate()):
    logger.info("Starting Telegram Bot thread...")
    threading.Thread(target=bot.infinity_polling, daemon=True, name="BotThread").start()

if __name__ == "__main__":
    logger.info(f"Manual run detected. Server starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)
