# -*- coding: utf-8 -*-
"""🍔 ربات فلافل فروشی — نسخه 0.3.0 (PostgreSQL + SQLite)"""

import requests, time, random, json, sys, traceback, re, os, threading
from datetime import datetime, date, timedelta
from flask import Flask

try:
    import sqlite3
except ImportError:
    sqlite3 = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False

try:
    import zoneinfo
    TEHRAN_TZ = zoneinfo.ZoneInfo("Asia/Tehran")
except Exception:
    TEHRAN_TZ = None


def now_local():
    return datetime.now(TEHRAN_TZ) if TEHRAN_TZ else datetime.now()


def today_local():
    return now_local().date()


def is_weekend():
    return now_local().weekday() in (3, 4)


web_app = Flask(__name__)


@web_app.route('/')
def home():
    return "Bot is running"


@web_app.route('/health')
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)


VERSION = "0.3.0"
SOURCE_NAME = "🍔 ربات فلافل فروشی"

TOKEN = os.environ.get("BOT_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", f"https://tapi.bale.ai/bot{TOKEN}/")
DB_PATH = "falafel_game.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

# تشخیص نوع دیتابیس
USE_POSTGRES = bool(DATABASE_URL) and PSYCOPG2_AVAILABLE
if USE_POSTGRES:
    print("✅ استفاده از PostgreSQL")
else:
    print("⚠️ استفاده از SQLite (محلی)")

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60
POLLING_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 3
MAX_MESSAGE_AGE = 120

ADMIN_IDS_RAW = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

print("✅ تنظیمات امنیتی تایید شد")
FORCED_CHANNEL = os.environ.get("FORCED_CHANNEL", "")
FORCED_CHANNEL_TITLE = os.environ.get("FORCED_CHANNEL_TITLE", "")

FORCED_CHANNEL_NORM = None
_join_cache = {}
JOIN_CACHE_TTL = 300
_join_pm_sent = {}
JOIN_PM_COOLDOWN = 300
# ==================== چک امنیتی ====================
if not TOKEN:
    print("❌ خطا: BOT_TOKEN توی Env Vars ست نشده!")
    sys.exit(1)

if not ADMIN_IDS:
    print("❌ خطا: ADMIN_IDS توی Env Vars ست نشده!")
    sys.exit(1)

if not FORCED_CHANNEL:
    print("❌ خطا: FORCED_CHANNEL توی Env Vars ست نشده!")
    sys.exit(1)

CARD_NUMBER = os.environ.get("CARD_NUMBER", "6037-XXXX-XXXX-XXXX")
CARD_OWNER = os.environ.get("CARD_OWNER", "نام صاحب کارت")

SHOP_PACKAGES = {
    "small":  {"name": "🟢 بسته کوچک",  "coins": 50000,   "price": 50000},
    "medium": {"name": "🔵 بسته متوسط", "coins": 150000,  "price": 130000},
    "large":  {"name": "🟣 بسته بزرگ",  "coins": 500000,  "price": 400000},
    "mega":   {"name": "🔴 بسته مگا",   "coins": 1500000, "price": 1000000},
}

BANK_DAILY_PROFIT = 0.20
BANK_MIN_INVEST = 1000
BANK_MAX_BALANCE = 10000000
BOX_PRICE = 2000
ADMIN_MONEY_LIMIT = 100000
TRANSFER_MIN = 500
TRANSFER_MAX = 50000
TRANSFER_COMMISSION = 0.02
WEEKEND_MULTIPLIER = 2.0
BOOSTER_PRICE = 5000
BOOSTER_MULTIPLIER = 2.0
BOOSTER_DURATION = 3600
LOTTERY_PRICE = 1000
PET_FEED_PRICE = 500
PET_MAX_LEVEL = 10
SLOT_MIN = 1000
SLOT_MAX = 50000
SKIP_OLD_UPDATES = False

NUMERIC_FIELDS = [
    "money", "gems", "flour", "chickpeas", "oil", "cheese", "spice",
    "falafel_simple", "falafel_special", "falafel_sandwich",
    "falafel_cheese", "falafel_spicy", "falafel_deluxe",
    "level", "exp", "oven_level", "mixer_level", "counter_level",
    "skill_cook", "skill_trade", "skill_luck", "skill_charm",
    "pet_level", "pet_exp", "pet_hunger",
    "total_sold", "total_earned", "total_cooked", "daily_streak",
    "win_streak", "best_streak",
]

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_numbers(text):
    if not text:
        return text
    text = text.translate(PERSIAN_DIGITS)
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


def is_admin(uid):
    return uid in ADMIN_IDS


def safe_md(text):
    if not text:
        return ""
    text = str(text)
    for ch in ["_", "*", "[", "]", "`", "("]:
        text = text.replace(ch, " ")
    return text


def format_money(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def log(*a):
    if DEBUG:
        ts = now_local().strftime('%H:%M:%S')
        print(f"[{ts}] [v{VERSION}]", *a, flush=True)


def log_err():
    if DEBUG:
        traceback.print_exc()


def ph():
    """Placeholder برای پارامتر در کوئری."""
    return "%s" if USE_POSTGRES else "?"


# ==================== API ====================
_calls = []
_user_cmd_cooldown = {}
USER_CMD_COOLDOWN = 1.5


def check_user_cooldown(uid):
    if is_admin(uid):
        return True
    now = time.time()
    if len(_user_cmd_cooldown) > 1000:
        cutoff = now - 60
        for k in list(_user_cmd_cooldown.keys()):
            if _user_cmd_cooldown[k] < cutoff:
                del _user_cmd_cooldown[k]
    last = _user_cmd_cooldown.get(uid, 0)
    if now - last < USER_CMD_COOLDOWN:
        return False
    _user_cmd_cooldown[uid] = now
    return True


def rate_limit():
    now = time.time()
    while _calls and now - _calls[0] > 1:
        _calls.pop(0)
    if len(_calls) >= 25:
        time.sleep(0.4)
    _calls.append(time.time())


def api(method, params=None, req_timeout=None):
    if req_timeout is None:
        req_timeout = (CONNECT_TIMEOUT, READ_TIMEOUT)
    rate_limit()
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(BASE_URL + method, data=params, timeout=req_timeout)
            return r.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            log(f"⚠️ API error [{method}]: {e}")
            return {"ok": False}
    return {"ok": False}


def get_updates(offset=None, timeout=POLLING_TIMEOUT):
    p = {"timeout": timeout}
    if offset:
        p["offset"] = offset
    return api("getUpdates", p, req_timeout=(CONNECT_TIMEOUT, timeout + READ_TIMEOUT))


def send_message(chat_id, text, reply_markup=None, safe=True):
    if not text:
        text = "."
    if safe:
        text = safe_md(text)
    p = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        p["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return api("sendMessage", p)


def answer_callback(cb_id, text=None, alert=False):
    p = {"callback_query_id": cb_id}
    if text:
        p["text"] = text
        p["show_alert"] = alert
    return api("answerCallbackQuery", p)


# ==================== دیتابیس ====================
def db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def close(conn):
    try:
        conn.close()
    except Exception:
        pass


def _t_serial():
    return "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"


def _t_real():
    return "DOUBLE PRECISION" if USE_POSTGRES else "REAL"


def _t_int_pk():
    return "BIGINT PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY"


def init_db():
    conn = db()
    try:
        c = conn.cursor()
        tables = [
            f"""CREATE TABLE IF NOT EXISTS players (
                user_id {_t_int_pk()}, first_name TEXT, username TEXT,
                money INTEGER DEFAULT 5000, gems INTEGER DEFAULT 0,
                flour INTEGER DEFAULT 10, chickpeas INTEGER DEFAULT 10,
                oil INTEGER DEFAULT 10, cheese INTEGER DEFAULT 0, spice INTEGER DEFAULT 0,
                falafel_simple INTEGER DEFAULT 0, falafel_special INTEGER DEFAULT 0,
                falafel_sandwich INTEGER DEFAULT 0, falafel_cheese INTEGER DEFAULT 0,
                falafel_spicy INTEGER DEFAULT 0, falafel_deluxe INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0,
                oven_level INTEGER DEFAULT 0, mixer_level INTEGER DEFAULT 0,
                counter_level INTEGER DEFAULT 0,
                skill_cook INTEGER DEFAULT 0, skill_trade INTEGER DEFAULT 0,
                skill_luck INTEGER DEFAULT 0, skill_charm INTEGER DEFAULT 0,
                pet_level INTEGER DEFAULT 0, pet_exp INTEGER DEFAULT 0, pet_hunger INTEGER DEFAULT 100,
                win_streak INTEGER DEFAULT 0, best_streak INTEGER DEFAULT 0,
                total_sold INTEGER DEFAULT 0, total_earned INTEGER DEFAULT 0,
                total_cooked INTEGER DEFAULT 0, last_daily {_t_real()} DEFAULT 0,
                daily_streak INTEGER DEFAULT 0, last_spin {_t_real()} DEFAULT 0,
                active_customer TEXT DEFAULT '', customer_expire {_t_real()} DEFAULT 0,
                customer_order TEXT DEFAULT '', customer_reward INTEGER DEFAULT 0,
                last_slot {_t_real()} DEFAULT 0, created_at {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS achievements (
                user_id BIGINT, achievement_id TEXT, unlocked_at {_t_real()},
                PRIMARY KEY (user_id, achievement_id))""",
            f"""CREATE TABLE IF NOT EXISTS transactions (
                id {_t_serial()}, user_id BIGINT, type TEXT,
                amount INTEGER, description TEXT, ts {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS shop_orders (
                id {_t_serial()}, user_id BIGINT, package_key TEXT, coins INTEGER, price INTEGER,
                receipt_file_id TEXT DEFAULT '', tracking_code TEXT DEFAULT '',
                status TEXT DEFAULT 'pending', created_at {_t_real()},
                reviewed_by BIGINT DEFAULT 0, reviewed_at {_t_real()}, note TEXT DEFAULT '')""",
            "CREATE TABLE IF NOT EXISTS user_states (user_id BIGINT PRIMARY KEY, state TEXT, data TEXT)",
            f"""CREATE TABLE IF NOT EXISTS clans (
                id {_t_serial()}, name TEXT UNIQUE, owner_id BIGINT, treasury INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0, created_at {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS clan_members (
                clan_id BIGINT, user_id BIGINT PRIMARY KEY, joined_at {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS duels (
                id {_t_serial()}, challenger_id BIGINT, opponent_id BIGINT, amount INTEGER,
                winner_id BIGINT, ts {_t_real()})""",
            "CREATE TABLE IF NOT EXISTS daily_missions (user_id BIGINT, day TEXT, missions TEXT, completed TEXT, PRIMARY KEY (user_id, day))",
            f"""CREATE TABLE IF NOT EXISTS admin_txns (
                id {_t_serial()}, target_id BIGINT, admin_id BIGINT, amount INTEGER,
                note TEXT, reversed INTEGER DEFAULT 0, ts {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS banks (
                user_id BIGINT PRIMARY KEY, balance INTEGER DEFAULT 0, invested INTEGER DEFAULT 0,
                last_collect {_t_real()} DEFAULT 0, total_profit INTEGER DEFAULT 0, last_invest {_t_real()} DEFAULT 0)""",
            f"""CREATE TABLE IF NOT EXISTS casino_log (
                id {_t_serial()}, user_id BIGINT, amount INTEGER, result TEXT, bet_type TEXT, ts {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS card_transfers (
                id {_t_serial()}, sender_id BIGINT, receiver_id BIGINT, amount INTEGER,
                commission INTEGER, note TEXT, ts {_t_real()})""",
            "CREATE TABLE IF NOT EXISTS discount_codes (code TEXT PRIMARY KEY, amount INTEGER, max_uses INTEGER DEFAULT 1, uses INTEGER DEFAULT 0, created_by BIGINT, created_at DOUBLE PRECISION, used_by TEXT DEFAULT '[]')",
            f"""CREATE TABLE IF NOT EXISTS boosters (
                user_id BIGINT PRIMARY KEY, multiplier {_t_real()} DEFAULT 2.0,
                expires_at {_t_real()} DEFAULT 0, bought_at {_t_real()} DEFAULT 0)""",
            f"""CREATE TABLE IF NOT EXISTS reminders (
                id {_t_serial()}, user_id BIGINT, chat_id BIGINT, text TEXT,
                remind_at {_t_real()}, created_at {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS lottery (
                id {_t_serial()}, user_id BIGINT, tickets INTEGER DEFAULT 0,
                week TEXT, joined_at {_t_real()})""",
            f"""CREATE TABLE IF NOT EXISTS lottery_winners (
                id {_t_serial()}, week TEXT, user_id BIGINT, tickets INTEGER,
                prize INTEGER, paid INTEGER DEFAULT 0, ts {_t_real()})""",
            "CREATE TABLE IF NOT EXISTS daily_events (day TEXT PRIMARY KEY, event_type TEXT, description TEXT)",
            f"""CREATE TABLE IF NOT EXISTS gems_log (
                id {_t_serial()}, user_id BIGINT, amount INTEGER, reason TEXT, ts {_t_real()})""",
        ]
        for t in tables:
            try:
                c.execute(t)
            except Exception as e:
                log(f"⚠️ Table error: {e}")
        conn.commit()
    finally:
        close(conn)


# ==================== Game Data ====================
INGREDIENTS = {
    "flour":     {"name": "آرد", "emoji": "🌾", "base_price": 200},
    "chickpeas": {"name": "نخود", "emoji": "🫘", "base_price": 300},
    "oil":       {"name": "روغن", "emoji": "🛢", "base_price": 150},
    "cheese":    {"name": "پنیر", "emoji": "🧀", "base_price": 400},
    "spice":     {"name": "ادویه", "emoji": "🌶", "base_price": 250},
}

RECIPES = {
    "simple":   {"name": "فلافل ساده",    "emoji": "🟡", "ing": {"flour": 1, "chickpeas": 1, "oil": 1}, "base_price": 1200, "exp": 5},
    "special":  {"name": "فلافل مخصوص",   "emoji": "🟠", "ing": {"flour": 2, "chickpeas": 2, "oil": 1}, "base_price": 2500, "exp": 12},
    "sandwich": {"name": "ساندویچ فلافل", "emoji": "🥙", "ing": {"flour": 3, "chickpeas": 2, "oil": 2}, "base_price": 4000, "exp": 25},
    "cheese":   {"name": "فلافل پنیری",   "emoji": "🧀", "ing": {"flour": 2, "chickpeas": 2, "oil": 2, "cheese": 2}, "base_price": 3800, "exp": 20},
    "spicy":    {"name": "فلافل تند",     "emoji": "🌶", "ing": {"flour": 2, "chickpeas": 3, "oil": 2, "spice": 2}, "base_price": 3500, "exp": 18},
    "deluxe":   {"name": "فلافل دلوکس",   "emoji": "👑", "ing": {"flour": 5, "chickpeas": 4, "oil": 3, "cheese": 3, "spice": 3}, "base_price": 9000, "exp": 60},
}

UPGRADES = {
    "oven":    {"name": "🔥 تنور", "max_level": 5, "base_cost": 3000, "cost_mult": 2},
    "mixer":   {"name": "🥣 مخلوط‌کن", "max_level": 5, "base_cost": 2500, "cost_mult": 2},
    "counter": {"name": "🏪 پیشخوان", "max_level": 5, "base_cost": 4000, "cost_mult": 2},
}

SKILLS = {
    "cook":   {"name": "🍳 آشپزی",  "desc": "هر لول ۳٪ شانس پخت دوتایی", "max": 5, "cost": 5},
    "trade":  {"name": "💼 تجارت",  "desc": "هر لول ۳٪ تخفیف مواد", "max": 5, "cost": 5},
    "luck":   {"name": "🍀 شانس",   "desc": "هر لول ۳٪ شانس برد کازینو", "max": 5, "cost": 8},
    "charm":  {"name": "😊 جذابیت",  "desc": "هر لول ۳٪ پاداش مشتری", "max": 5, "cost": 10},
}

ACHIEVEMENTS = {
    "first_cook": {"name": "🥇 آشپز تازه‌کار", "reward": 500},
    "cook_10":    {"name": "🍳 آشپز", "reward": 1000},
    "cook_100":   {"name": "👨‍🍳 سرآشپز", "reward": 5000},
    "cook_1000":  {"name": "🏆 استاد فلافل", "reward": 25000},
    "earn_10k":   {"name": "💵 تاجر", "reward": 2000},
    "earn_100k":  {"name": "💎 میلیونر", "reward": 15000},
    "earn_1m":    {"name": "👑 سلطان فلافل", "reward": 100000},
    "level_5":    {"name": "⭐ سطح ۵", "reward": 1000},
    "level_10":   {"name": "🌟 سطح ۱۰", "reward": 5000},
    "all_upgrades": {"name": "⚙️ مجهز", "reward": 10000},
    "daily_7":    {"name": "📅 ۷ روز پیاپی", "reward": 3000},
    "banker":     {"name": "🏦 بانکدار", "reward": 5000},
    "investor":   {"name": "📈 سرمایه‌گذار", "reward": 10000},
    "pet_lover":  {"name": "🐔 پت‌باز", "reward": 1000},
    "streak_5":   {"name": "🔥 استریک ۵", "reward": 5000},
    "streak_10":  {"name": "🔥🔥 استریک ۱۰", "reward": 20000},
}

CUSTOMER_TYPES = [
    {"name": "عادی",     "emoji": "👤", "mult": 1.0, "patience": 15},
    {"name": "خوش‌شانس", "emoji": "😊", "mult": 1.5, "patience": 20},
    {"name": "عجول",     "emoji": "🏃", "mult": 1.8, "patience": 5},
    {"name": "VIP",      "emoji": "🎩", "mult": 2.5, "patience": 10},
    {"name": "تورگرد",   "emoji": "🧑‍🦱", "mult": 1.3, "patience": 25},
]

BOX_PRIZES = [
    ("💰 پول کم", "money", 500, 30), ("💰 پول متوسط", "money", 2000, 25),
    ("💰 پول زیاد", "money", 8000, 10), ("💰 جکپات", "money", 25000, 2),
    ("🌾 آرد x5", "flour", 5, 10), ("🫘 نخود x5", "chickpeas", 5, 10),
    ("🛢 روغن x5", "oil", 5, 10), ("🧀 پنیر x3", "cheese", 3, 5),
    ("🌶 ادویه x3", "spice", 3, 5), ("😢 خالی", "none", 0, 3),
]

SLOT_SYMBOLS = [
    ("🍒", 20, 5), ("🍋", 15, 6), ("🍇", 10, 8),
    ("⭐", 8, 12), ("💎", 5, 25), ("7️⃣", 2, 100),
]

DAILY_EVENTS = [
    ("double_money", "💰 *امروز ۱.۵ برابر پوله!*"),
    ("cheap_ingredients", "🛒 *امروز ۲۵٪ تخفیف مواد!*"),
    ("lucky_casino", "🎰 *امروز شانس کازینو بالاست!*"),
    ("cook_bonus", "🍳 *امروز ۲ برابر تجربه!*"),
    ("normal", "🌟 *روز عادی*"),
]

GEM_SHOP = {
    "booster":  {"name": "⚡ بوستر ۱ ساعته", "cost": 10, "desc": "درآمد ۲x"},
    "reroll":   {"name": "🎲 ریست ماموریت", "cost": 5, "desc": "ماموریت جدید"},
    "luck":     {"name": "🍀 شانس موقت", "cost": 15, "desc": "۱۰ دقیقه شانس بیشتر"},
    "streak_fix": {"name": "🔥 حفظ استریک", "cost": 20, "desc": "استریک شکسته رو برگردون"},
}


# ==================== Player helpers ====================
def get_player(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT * FROM players WHERE user_id={ph()}", (uid,))
        r = c.fetchone()
        if not r:
            return None
        d = dict(r)
        for k in NUMERIC_FIELDS:
            if d.get(k) is None:
                d[k] = 0
        for k in ["last_daily", "last_spin", "customer_expire", "last_slot"]:
            if d.get(k) is None:
                d[k] = 0
        for k in ["active_customer", "customer_order"]:
            if d.get(k) is None:
                d[k] = ""
        return d
    finally:
        close(conn)


def create_player(uid, fn="کاربر", un=""):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO players (user_id, first_name, username, created_at) VALUES ({ph()},{ph()},{ph()},{ph()}) ON CONFLICT (user_id) DO NOTHING" if USE_POSTGRES else
                  "INSERT OR IGNORE INTO players (user_id, first_name, username, created_at) VALUES (?,?,?,?)",
                  (uid, fn, un, time.time()))
        conn.commit()
    except Exception as e:
        log(f"⚠️ create_player error: {e}")
    finally:
        close(conn)


def update_player(uid, **kw):
    if not kw:
        return
    conn = db()
    try:
        c = conn.cursor()
        fields = ", ".join([f"{k}={ph()}" for k in kw.keys()])
        vals = list(kw.values()) + [uid]
        c.execute(f"UPDATE players SET {fields} WHERE user_id={ph()}", vals)
        conn.commit()
    except Exception as e:
        log(f"⚠️ update_player error: {e}")
    finally:
        close(conn)


def log_txn(uid, type_, amount, desc):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO transactions (user_id, type, amount, description, ts) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()})",
                  (uid, type_, amount, desc, time.time()))
        conn.commit()
    except Exception as e:
        log(f"⚠️ log_txn: {e}")
    finally:
        close(conn)


def add_gems(uid, amount, reason=""):
    p = get_player(uid)
    if not p:
        return
    new = max(0, (p.get("gems", 0) or 0) + amount)
    update_player(uid, gems=new)
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO gems_log (user_id, amount, reason, ts) VALUES ({ph()},{ph()},{ph()},{ph()})",
                  (uid, amount, reason, time.time()))
        conn.commit()
    except Exception:
        pass
    finally:
        close(conn)


def add_exp(uid, amount):
    """🆕 رفع باگ: جلوگیری از منفی شدن و کرش"""
    p = get_player(uid)
    if not p:
        return None
    if amount < 0:
        amount = 0
    cook_skill = p.get("skill_cook", 0) or 0
    if cook_skill > 0:
        amount = int(amount * (1 + cook_skill * 0.03))
    new_exp = (p.get("exp", 0) or 0) + amount
    new_level = p.get("level", 1) or 1
    while new_exp >= 100:
        new_exp -= 100
        new_level += 1
    update_player(uid, exp=new_exp, level=new_level)
    if new_level > (p.get("level", 1) or 1):
        add_gems(uid, 1, f"سطح {new_level}")
        return new_level
    return None


def ing_price(item, mixer, player=None):
    if mixer is None:
        mixer = 0
    base = INGREDIENTS[item]["base_price"]
    discount = min(mixer * 0.03, 0.15)
    if player:
        discount += (player.get("skill_trade", 0) or 0) * 0.03
    if get_today_event() == "cheap_ingredients":
        discount += 0.25
    return max(1, int(base * (1 - min(discount, 0.5))))


def sell_price(key, counter, player=None):
    if counter is None:
        counter = 0
    base = RECIPES[key]["base_price"]
    bonus = counter * 0.05
    if player:
        bonus += (player.get("skill_charm", 0) or 0) * 0.03
        bonus += (player.get("pet_level", 0) or 0) * 0.02
    if get_today_event() == "double_money":
        bonus += 0.5
    return int(base * (1 + bonus))


def count_falafel(p):
    return sum(p.get(f"falafel_{k}", 0) or 0 for k in RECIPES)


def upgrade_cost(uid, key):
    p = get_player(uid)
    if not p:
        return None
    cur = p.get(f"{key}_level", 0) or 0
    if cur >= UPGRADES[key]["max_level"]:
        return None
    return UPGRADES[key]["base_cost"] * (UPGRADES[key]["cost_mult"] ** cur)


def get_active_booster(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT multiplier, expires_at FROM boosters WHERE user_id={ph()}", (uid,))
        r = c.fetchone()
        if not r:
            return 1.0
        if r["expires_at"] and time.time() < r["expires_at"]:
            return r["multiplier"] or 1.0
        return 1.0
    finally:
        close(conn)


def get_total_multiplier(uid):
    mult = 1.0
    if is_weekend():
        mult *= WEEKEND_MULTIPLIER
    mult *= get_active_booster(uid)
    return mult


# ==================== Events ====================
def get_today_event():
    today = today_local().isoformat()
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT event_type FROM daily_events WHERE day={ph()}", (today,))
        r = c.fetchone()
        if r:
            return r["event_type"]
        event = random.choices(DAILY_EVENTS, weights=[15, 15, 15, 15, 40])[0]
        c.execute(f"INSERT INTO daily_events (day, event_type, description) VALUES ({ph()},{ph()},{ph()})",
                  (today, event[0], event[1]))
        conn.commit()
        return event[0]
    except Exception:
        return "normal"
    finally:
        close(conn)


def get_today_event_desc():
    event = get_today_event()
    for e in DAILY_EVENTS:
        if e[0] == event:
            return e[1]
    return ""


# ==================== Bank ====================
def get_bank(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT * FROM banks WHERE user_id={ph()}", (uid,))
        r = c.fetchone()
        if r:
            d = dict(r)
            for k in ["balance", "invested", "total_profit", "last_collect", "last_invest"]:
                if d.get(k) is None:
                    d[k] = 0
            return d
        try:
            c.execute(f"INSERT INTO banks (user_id) VALUES ({ph()})", (uid,))
            conn.commit()
        except Exception:
            pass
        return {"user_id": uid, "balance": 0, "invested": 0, "last_collect": 0, "total_profit": 0, "last_invest": 0}
    finally:
        close(conn)


def update_bank(uid, **kw):
    if not kw:
        return
    conn = db()
    try:
        c = conn.cursor()
        fields = ", ".join([f"{k}={ph()}" for k in kw.keys()])
        vals = list(kw.values()) + [uid]
        c.execute(f"UPDATE banks SET {fields} WHERE user_id={ph()}", vals)
        conn.commit()
    except Exception as e:
        log(f"⚠️ update_bank: {e}")
    finally:
        close(conn)


def collect_bank_profit(uid):
    b = get_bank(uid)
    if b["invested"] <= 0:
        return 0
    now = time.time()
    ref = b["last_collect"] if b["last_collect"] > 0 else (b["last_invest"] if b["last_invest"] > 0 else now)
    days = int((now - ref) // 86400)
    if days <= 0:
        return 0
    profit = int(b["invested"] * BANK_DAILY_PROFIT * days)
    new_balance = min(b["balance"] + profit, BANK_MAX_BALANCE)
    update_bank(uid, balance=new_balance, last_collect=ref + days * 86400, total_profit=b["total_profit"] + profit)
    return profit


def do_bank(uid, chat_id, first_name):
    profit = collect_bank_profit(uid)
    b = get_bank(uid)
    text = (f"🏦 *بانک*\n━━━━━━━━━━━━━━━\n👤 {first_name}\n\n"
            f"💰 موجودی: {format_money(b['balance'])} تومان\n"
            f"📈 سرمایه: {format_money(b['invested'])} تومان\n"
            f"💵 سود کل: {format_money(b['total_profit'])} تومان\n\n")
    if profit > 0:
        text += f"🎉 *سود جدید:* +{format_money(profit)}\n\n"
    text += ("📊 سود روزانه: ۲۰٪\n\n`بانک واریز ۵۰۰۰`\n`بانک برداشت ۵۰۰۰`\n"
             "`بانک سرمایه ۵۰۰۰`\n`بانک پایان ۵۰۰۰`\n`بانک جمع`")
    send_message(chat_id, text, BANK_KB(), safe=False)


def do_bank_deposit(uid, chat_id, amount):
    p = get_player(uid)
    if amount <= 0 or p["money"] < amount:
        send_message(chat_id, "❌ پول کافی نداری!")
        return
    b = get_bank(uid)
    if b["balance"] + amount > BANK_MAX_BALANCE:
        send_message(chat_id, f"❌ سقف {format_money(BANK_MAX_BALANCE)} تومانه.")
        return
    update_player(uid, money=p["money"] - amount)
    update_bank(uid, balance=b["balance"] + amount)
    send_message(chat_id, f"✅ {format_money(amount)} واریز شد.")


def do_bank_withdraw(uid, chat_id, amount):
    b = get_bank(uid)
    if amount <= 0 or b["balance"] < amount:
        send_message(chat_id, "❌ حساب کافی نیست!")
        return
    p = get_player(uid)
    update_player(uid, money=p["money"] + amount)
    update_bank(uid, balance=b["balance"] - amount)
    send_message(chat_id, f"✅ {format_money(amount)} برداشت شد.")


def do_bank_invest(uid, chat_id, amount):
    p = get_player(uid)
    if amount < BANK_MIN_INVEST or p["money"] < amount:
        send_message(chat_id, f"❌ حداقل {format_money(BANK_MIN_INVEST)} و پول کافی!")
        return
    collect_bank_profit(uid)
    b = get_bank(uid)
    now = time.time()
    update_player(uid, money=p["money"] - amount)
    update_bank(uid, invested=b["invested"] + amount, last_invest=now,
                last_collect=b["last_collect"] if b["last_collect"] > 0 else now)
    send_message(chat_id, f"📈 {format_money(amount)} سرمایه‌گذاری شد!\n💰 کل: {format_money(b['invested'] + amount)}")


def do_bank_end_invest(uid, chat_id, amount):
    b = get_bank(uid)
    if amount <= 0 or b["invested"] < amount:
        send_message(chat_id, "❌ سرمایه کافی نیست!")
        return
    collect_bank_profit(uid)
    b = get_bank(uid)
    update_bank(uid, invested=b["invested"] - amount, balance=b["balance"] + amount)
    send_message(chat_id, f"✅ {format_money(amount)} برگشت.")


def do_bank_collect(uid, chat_id):
    profit = collect_bank_profit(uid)
    if profit > 0:
        send_message(chat_id, f"🎉 *سود:* +{format_money(profit)}")
    else:
        b = get_bank(uid)
        if b["invested"] <= 0:
            send_message(chat_id, "❌ سرمایه‌ای نداری!\n`بانک سرمایه ۵۰۰۰`")
        else:
            ref = b["last_collect"] if b["last_collect"] > 0 else b["last_invest"]
            left = max(0, 86400 - (time.time() - ref))
            send_message(chat_id, f"⏰ بعدی: {int(left // 3600)}س {int((left % 3600) // 60)}د")


# ==================== Casino + Slot ====================
def do_casino(uid, chat_id, amount, bet_type):
    if amount < 500 or amount > 100000:
        send_message(chat_id, "❌ شرط بین ۵۰۰ تا ۱۰۰,۰۰۰!")
        return
    p = get_player(uid)
    if p["money"] < amount:
        send_message(chat_id, "❌ پول کافی نداری!")
        return
    luck = (p.get("skill_luck", 0) or 0) * 0.03
    win_chance = min(0.5 + luck + (0.15 if get_today_event() == "lucky_casino" else 0), 0.85)
    result = random.choice(["شیر", "خط"])
    correct = (result == bet_type)
    if not correct and random.random() < (win_chance - 0.5) * 2:
        correct = True
        result = bet_type
    if correct:
        new_streak = (p.get("win_streak", 0) or 0) + 1
        best = max(p.get("best_streak", 0) or 0, new_streak)
        bonus = min(new_streak, 5) * 100
        update_player(uid, money=p["money"] + amount + bonus,
                      win_streak=new_streak, best_streak=best)
        log_txn(uid, "casino_win", amount + bonus, "برد کازینو")
        extra = f"\n🔥 استریک: {new_streak}" + (f" (+{bonus})" if bonus > 0 else "")
        send_message(chat_id,
                     f"🎰 *کازینو*\n💰 {format_money(amount)} — {bet_type}\n🎲 *{result}*\n\n"
                     f"🎉 بردی! +{format_money(amount + bonus)}{extra}", safe=False)
    else:
        update_player(uid, money=p["money"] - amount, win_streak=0)
        log_txn(uid, "casino_lose", -amount, "باخت کازینو")
        send_message(chat_id,
                     f"🎰 *کازینو*\n💰 {format_money(amount)} — {bet_type}\n🎲 *{result}*\n\n😢 باختی!",
                     safe=False)


def do_slot(uid, chat_id, amount):
    if amount < SLOT_MIN or amount > SLOT_MAX:
        send_message(chat_id, f"❌ شرط بین {format_money(SLOT_MIN)} تا {format_money(SLOT_MAX)}!")
        return
    p = get_player(uid)
    if p["money"] < amount:
        send_message(chat_id, "❌ پول کافی نداری!")
        return
    weights = [s[1] for s in SLOT_SYMBOLS]
    reels = [random.choices(SLOT_SYMBOLS, weights=weights)[0] for _ in range(3)]
    symbols = [r[0] for r in reels]
    win = 0
    msg_extra = ""
    if symbols[0] == symbols[1] == symbols[2]:
        mult = reels[0][2]
        win = amount * mult
        msg_extra = f"🎉 *جکپات {mult}x!*"
    elif symbols[0] == symbols[1] or symbols[1] == symbols[2] or symbols[0] == symbols[2]:
        win = amount * 2
        msg_extra = "🎉 *دو تا یکی!*"
    elif "7️⃣" in symbols:
        win = amount
        msg_extra = "🟡 هفت آوردی!"
    if win > 0:
        update_player(uid, money=p["money"] + win)
        log_txn(uid, "slot_win", win, "برد اسلات")
        send_message(chat_id,
                     f"🎰 *اسلات*\n┃ {symbols[0]} ┃ {symbols[1]} ┃ {symbols[2]} ┃\n\n"
                     f"{msg_extra}\n💰 +{format_money(win)}", safe=False)
    else:
        update_player(uid, money=p["money"] - amount)
        log_txn(uid, "slot_lose", -amount, "باخت اسلات")
        send_message(chat_id,
                     f"🎰 *اسلات*\n┃ {symbols[0]} ┃ {symbols[1]} ┃ {symbols[2]} ┃\n\n"
                     f"😢 باختی! -{format_money(amount)}", safe=False)


# ==================== Box ====================
def do_mystery_box(uid, chat_id):
    p = get_player(uid)
    if p["money"] < BOX_PRICE:
        send_message(chat_id, f"❌ پول کافی نداری! ({format_money(BOX_PRICE)})")
        return
    weights = [b[3] for b in BOX_PRIZES]
    prize = random.choices(BOX_PRIZES, weights=weights)[0]
    name, kind, amount, _ = prize
    update_player(uid, money=p["money"] - BOX_PRICE)
    msg = f"🎁 *جعبه شانس*\n💰 {format_money(BOX_PRICE)}\n\n"
    if kind == "money":
        np = get_player(uid)
        update_player(uid, money=np["money"] + amount)
        log_txn(uid, "box_win", amount, "جایزه جعبه")
        msg += f"🎉 {name}\n💰 +{format_money(amount)}"
    elif kind == "none":
        msg += "😢 خالی!"
    else:
        np = get_player(uid)
        update_player(uid, **{kind: (np.get(kind, 0) or 0) + amount})
        msg += f"🎉 {name}\n{INGREDIENTS[kind]['emoji']} +{amount}"
    send_message(chat_id, msg, safe=False)


# ==================== Booster ====================
def do_booster(uid, chat_id):
    p = get_player(uid)
    if p["money"] < BOOSTER_PRICE:
        send_message(chat_id, "❌ پول کافی نداری!")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT expires_at FROM boosters WHERE user_id={ph()}", (uid,))
        r = c.fetchone()
        if r and r["expires_at"] and time.time() < r["expires_at"]:
            left = int((r["expires_at"] - time.time()) // 60)
            send_message(chat_id, f"⚡ بوستر فعالت {left} دقیقه دیگه!")
            return
        new_expires = time.time() + BOOSTER_DURATION
        if USE_POSTGRES:
            c.execute(f"INSERT INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES ({ph()},{ph()},{ph()},{ph()}) ON CONFLICT (user_id) DO UPDATE SET multiplier={ph()}, expires_at={ph()}, bought_at={ph()}",
                      (uid, BOOSTER_MULTIPLIER, new_expires, time.time(), BOOSTER_MULTIPLIER, new_expires, time.time()))
        else:
            c.execute("INSERT OR REPLACE INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES (?,?,?,?)",
                      (uid, BOOSTER_MULTIPLIER, new_expires, time.time()))
        conn.commit()
    finally:
        close(conn)
    update_player(uid, money=p["money"] - BOOSTER_PRICE)
    send_message(chat_id, f"⚡ *بوستر فعال!*\n💰 -{format_money(BOOSTER_PRICE)}\n🎁 2x برای ۱ ساعت")


def booster_status(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT expires_at, multiplier FROM boosters WHERE user_id={ph()}", (uid,))
        r = c.fetchone()
        if r and r["expires_at"] and time.time() < r["expires_at"]:
            left = int((r["expires_at"] - time.time()) // 60)
            return f"⚡ بوستر: {left} دقیقه ({r['multiplier']}x)"
        return "⚡ بوستری نیست"
    finally:
        close(conn)


# ==================== Reminders ====================
def do_reminder_set(uid, chat_id, text_body, seconds):
    if not text_body.strip() or seconds < 60 or seconds > 86400:
        send_message(chat_id, "مثال: `یادآور ۱۰m جلسه` (۱ دقیقه تا ۲۴ ساعت)")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO reminders (user_id, chat_id, text, remind_at, created_at) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()})",
                  (uid, chat_id, text_body, time.time() + seconds, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"🔔 ثبت شد! بعد از {seconds // 60} دقیقه")


def do_reminder_list(uid, chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT id, text, remind_at FROM reminders WHERE user_id={ph()} ORDER BY remind_at ASC LIMIT 10", (uid,))
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "🔕 یادآوری نداری.")
        return
    txt = "🔔 *یادآورها*\n"
    for r in rows:
        txt += f"• {r['text']} ({int((r['remind_at'] - time.time()) // 60)} دقیقه)\n"
    send_message(chat_id, txt, safe=False)


# ==================== Lottery ====================
def get_week_key():
    today = today_local()
    days_since_sat = (today.weekday() - 5) % 7
    return (today - timedelta(days=days_since_sat)).isoformat()


def get_lottery_tickets(uid):
    week = get_week_key()
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT tickets FROM lottery WHERE user_id={ph()} AND week={ph()}", (uid, week))
        r = c.fetchone()
        return r["tickets"] if r else 0
    finally:
        close(conn)


def do_lottery_buy(uid, chat_id):
    p = get_player(uid)
    if p["money"] < LOTTERY_PRICE:
        send_message(chat_id, "❌ پول کافی نداری!")
        return
    week = get_week_key()
    update_player(uid, money=p["money"] - LOTTERY_PRICE)
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT id FROM lottery WHERE user_id={ph()} AND week={ph()}", (uid, week))
        if c.fetchone():
            c.execute(f"UPDATE lottery SET tickets=tickets+1 WHERE user_id={ph()} AND week={ph()}", (uid, week))
        else:
            c.execute(f"INSERT INTO lottery (user_id, tickets, week, joined_at) VALUES ({ph()},{ph()},{ph()},{ph()})",
                      (uid, 1, week, time.time()))
        conn.commit()
        c.execute(f"SELECT tickets FROM lottery WHERE user_id={ph()} AND week={ph()}", (uid, week))
        total = c.fetchone()["tickets"]
    finally:
        close(conn)
    send_message(chat_id, f"🎫 بلیط خریداری شد!\n🎯 بلیط‌های تو: {total}")


def do_lottery_panel(uid, chat_id):
    tickets = get_lottery_tickets(uid)
    conn = db()
    try:
        c = conn.cursor()
        week = get_week_key()
        c.execute(f"SELECT SUM(tickets) s FROM lottery WHERE week={ph()}", (week,))
        total = c.fetchone()["s"] or 0
    finally:
        close(conn)
    prize = total * LOTTERY_PRICE * 80 // 100
    send_message(chat_id,
                 f"🎫 *لاتاری*\n━━━━━━━━━━━━━━━\n"
                 f"🎯 بلیط تو: {tickets}\n📊 کل: {total}\n"
                 f"💰 جایزه: {format_money(prize)}\n\n"
                 f"`لاتاری بخر` — {format_money(LOTTERY_PRICE)}", safe=False)


def draw_lottery():
    week = get_week_key()
    today = today_local()
    days_since_sat = (today.weekday() - 5) % 7
    prev_week = (today - timedelta(days=days_since_sat + 7)).isoformat()
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT week FROM lottery_winners WHERE week={ph()}", (prev_week,))
        if c.fetchone():
            return
        c.execute(f"SELECT user_id, tickets FROM lottery WHERE week={ph()}", (prev_week,))
        participants = c.fetchall()
        if not participants:
            return
        pool = []
        for p in participants:
            pool.extend([p["user_id"]] * (p["tickets"] or 1))
        winner = random.choice(pool)
        c.execute(f"SELECT SUM(tickets) s FROM lottery WHERE week={ph()}", (prev_week,))
        total = c.fetchone()["s"] or 0
        prize = total * LOTTERY_PRICE * 80 // 100
        c.execute(f"INSERT INTO lottery_winners (week, user_id, tickets, prize, paid, ts) VALUES ({ph()},{ph()},{ph()},{ph()},1,{ph()})",
                  (prev_week, winner, total, prize, time.time()))
        conn.commit()
    finally:
        close(conn)
    wp = get_player(winner)
    if wp:
        update_player(winner, money=wp["money"] + prize)
        try:
            send_message(winner, f"🎉 *برنده لاتاری!*\n💰 +{format_money(prize)}")
        except Exception:
            pass


# ==================== Skills ====================
def do_skills_panel(uid, chat_id):
    p = get_player(uid)
    gems = p.get("gems", 0) or 0
    txt = f"🎓 *مهارت‌ها*\n💎 الماس: {gems}\n\n"
    for key, s in SKILLS.items():
        lvl = p.get(f"skill_{key}", 0) or 0
        bar = "█" * lvl + "░" * (s["max"] - lvl)
        txt += f"{s['name']}: {bar} ({lvl}/{s['max']})\n  {s['desc']}\n  💎 {s['cost']}\n\n"
    txt += "`مهارت بخر [cook|trade|luck|charm]`"
    send_message(chat_id, txt, safe=False)


def do_skill_buy(uid, chat_id, key):
    if key not in SKILLS:
        send_message(chat_id, "❌ نامعتبر. cook|trade|luck|charm")
        return
    p = get_player(uid)
    s = SKILLS[key]
    lvl = p.get(f"skill_{key}", 0) or 0
    if lvl >= s["max"]:
        send_message(chat_id, "✅ مکس شده!")
        return
    gems = p.get("gems", 0) or 0
    if gems < s["cost"]:
        send_message(chat_id, f"❌ الماس کافی نیست! نیاز: {s['cost']} 💎")
        return
    add_gems(uid, -s["cost"], f"خرید مهارت {key}")
    update_player(uid, **{f"skill_{key}": lvl + 1})
    send_message(chat_id, f"✅ {s['name']} → سطح {lvl + 1}!")


# ==================== Pet ====================
def do_pet_panel(uid, chat_id):
    p = get_player(uid)
    lvl = p.get("pet_level", 0) or 0
    if lvl == 0:
        send_message(chat_id, "🐔 *پتی نداری!*\n`پت بخر` — ۱۰,۰۰۰ تومان")
        return
    exp = p.get("pet_exp", 0) or 0
    hunger = p.get("pet_hunger", 100) or 100
    bar = "█" * lvl + "░" * (PET_MAX_LEVEL - lvl)
    send_message(chat_id,
                 f"🐔 *پت*\n⭐ {bar} ({lvl}/{PET_MAX_LEVEL})\n"
                 f"⭐ تجربه: {exp}/100\n🍖 سیری: {hunger}%\n\n"
                 f"`پت غذا بده` — {format_money(PET_FEED_PRICE)}", safe=False)


def do_pet_buy(uid, chat_id):
    p = get_player(uid)
    if (p.get("pet_level", 0) or 0) > 0:
        send_message(chat_id, "❌ پت داری!")
        return
    if p["money"] < 10000:
        send_message(chat_id, "❌ ۱۰,۰۰۰ تومان لازمه!")
        return
    update_player(uid, money=p["money"] - 10000, pet_level=1, pet_exp=0, pet_hunger=100)
    check_ach(uid, chat_id)
    send_message(chat_id, "🎉 *پت جدید!* 🐔")


def do_pet_feed(uid, chat_id):
    p = get_player(uid)
    if (p.get("pet_level", 0) or 0) == 0:
        send_message(chat_id, "❌ اول `پت بخر`")
        return
    if p["money"] < PET_FEED_PRICE:
        send_message(chat_id, "❌ پول کافی نداری!")
        return
    lvl = p.get("pet_level", 0) or 0
    exp = (p.get("pet_exp", 0) or 0) + 30
    hunger = min(100, (p.get("pet_hunger", 100) or 100) + 20)
    update_player(uid, money=p["money"] - PET_FEED_PRICE, pet_hunger=hunger)
    if exp >= 100 and lvl < PET_MAX_LEVEL:
        lvl += 1
        exp -= 100
        send_message(chat_id, f"🎉 پتت لول آپ شد! ({lvl})")
    update_player(uid, pet_level=lvl, pet_exp=exp)
    send_message(chat_id, f"🍖 غذا خورد!\n⭐ {exp}/100\n🍖 {hunger}%")


# ==================== Gem Shop ====================
def do_gem_shop(uid, chat_id):
    p = get_player(uid)
    gems = p.get("gems", 0) or 0
    txt = f"💎 *فروشگاه الماس*\n💰 الماس تو: {gems}\n\n"
    for key, item in GEM_SHOP.items():
        txt += f"• {item['name']} — 💎 {item['cost']}\n  {item['desc']}\n\n"
    txt += "`الماس بخر [نام]`"
    send_message(chat_id, txt, safe=False)


def do_gem_buy(uid, chat_id, key):
    if key not in GEM_SHOP:
        send_message(chat_id, f"❌ نامعتبر. {list(GEM_SHOP.keys())}")
        return
    p = get_player(uid)
    item = GEM_SHOP[key]
    gems = p.get("gems", 0) or 0
    if gems < item["cost"]:
        send_message(chat_id, f"❌ الماس کافی نیست! نیاز: {item['cost']} 💎")
        return
    add_gems(uid, -item["cost"], f"خرید {key}")
    if key == "booster":
        conn = db()
        try:
            c = conn.cursor()
            new_expires = time.time() + BOOSTER_DURATION
            if USE_POSTGRES:
                c.execute(f"INSERT INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES ({ph()},{ph()},{ph()},{ph()}) ON CONFLICT (user_id) DO UPDATE SET multiplier={ph()}, expires_at={ph()}, bought_at={ph()}",
                          (uid, BOOSTER_MULTIPLIER, new_expires, time.time(), BOOSTER_MULTIPLIER, new_expires, time.time()))
            else:
                c.execute("INSERT OR REPLACE INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES (?,?,?,?)",
                          (uid, BOOSTER_MULTIPLIER, new_expires, time.time()))
            conn.commit()
        finally:
            close(conn)
        send_message(chat_id, "⚡ بوستر فعال شد!")
    elif key == "reroll":
        today = today_local().isoformat()
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"DELETE FROM daily_missions WHERE user_id={ph()} AND day={ph()}", (uid, today))
            conn.commit()
        finally:
            close(conn)
        send_message(chat_id, "🎲 ماموریت جدید! `ماموریت` رو بزن.")
    elif key == "luck":
        conn = db()
        try:
            c = conn.cursor()
            new_expires = time.time() + 600
            if USE_POSTGRES:
                c.execute(f"INSERT INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES ({ph()},{ph()},{ph()},{ph()}) ON CONFLICT (user_id) DO UPDATE SET multiplier={ph()}, expires_at={ph()}, bought_at={ph()}",
                          (uid, 1.5, new_expires, time.time(), 1.5, new_expires, time.time()))
            else:
                c.execute("INSERT OR REPLACE INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES (?,?,?,?)",
                          (uid, 1.5, new_expires, time.time()))
            conn.commit()
        finally:
            close(conn)
        send_message(chat_id, "🍀 شانس موقت فعال شد (۱۰ دقیقه)!")
    elif key == "streak_fix":
        update_player(uid, win_streak=1)
        send_message(chat_id, "🔥 استریک ریست شد!")


# ==================== Achievements ====================
def check_ach(uid, chat_id):
    p = get_player(uid)
    if not p:
        return
    b = get_bank(uid)
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT achievement_id FROM achievements WHERE user_id={ph()}", (uid,))
        have = {r["achievement_id"] for r in c.fetchall()}
        checks = [
            ("first_cook", p["total_cooked"] >= 1),
            ("cook_10", p["total_cooked"] >= 10),
            ("cook_100", p["total_cooked"] >= 100),
            ("cook_1000", p["total_cooked"] >= 1000),
            ("earn_10k", p["total_earned"] >= 10000),
            ("earn_100k", p["total_earned"] >= 100000),
            ("earn_1m", p["total_earned"] >= 1000000),
            ("level_5", p["level"] >= 5),
            ("level_10", p["level"] >= 10),
            ("all_upgrades", p["oven_level"] >= 5 and p["mixer_level"] >= 5 and p["counter_level"] >= 5),
            ("daily_7", p["daily_streak"] >= 7),
            ("banker", b["balance"] >= 10000),
            ("investor", b["invested"] >= 50000),
            ("pet_lover", (p.get("pet_level", 0) or 0) >= 5),
            ("streak_5", (p.get("best_streak", 0) or 0) >= 5),
            ("streak_10", (p.get("best_streak", 0) or 0) >= 10),
        ]
        for aid, cond in checks:
            if cond and aid not in have:
                try:
                    c.execute(f"INSERT INTO achievements (user_id, achievement_id, unlocked_at) VALUES ({ph()},{ph()},{ph()})",
                              (uid, aid, time.time()))
                    conn.commit()
                except Exception:
                    pass
                reward = ACHIEVEMENTS[aid]["reward"]
                p2 = get_player(uid)
                update_player(uid, money=p2["money"] + reward)
                add_gems(uid, 2, f"دستاورد {aid}")
                send_message(chat_id, f"🎉 *دستاورد!*\n{ACHIEVEMENTS[aid]['name']}\n💵 +{reward:,}\n💎 +۲", safe=False)
    finally:
        close(conn)


# ==================== Force Join ====================
def normalize_channel(ch):
    if not ch:
        return ""
    ch = str(ch).strip()
    for prefix in ["https://ble.ir/", "http://ble.ir/", "https://t.me/", "http://t.me/", "ble.ir/", "t.me/"]:
        if ch.startswith(prefix):
            ch = ch[len(prefix):]
    ch = ch.strip("/").strip()
    if not ch.startswith("@") and not ch.lstrip("-").isdigit():
        ch = "@" + ch
    return ch


def get_forced_channel():
    global FORCED_CHANNEL_NORM
    if FORCED_CHANNEL_NORM is None:
        FORCED_CHANNEL_NORM = normalize_channel(FORCED_CHANNEL)
    return FORCED_CHANNEL_NORM


def clear_join_cache(uid=None):
    if uid:
        _join_cache.pop(uid, None)
    else:
        _join_cache.clear()


def is_joined(uid, use_cache=True):
    if is_admin(uid):
        return True
    ch = get_forced_channel()
    if not ch:
        return True
    now = time.time()
    if use_cache and uid in _join_cache:
        cached, ts = _join_cache[uid]
        if now - ts < JOIN_CACHE_TTL:
            return cached
    r = api("getChatMember", {"chat_id": ch, "user_id": uid})
    if not r.get("ok"):
        err = str(r.get("description", "")).lower()
        if "not found" in err or "user not found" in err or "chat not found" in err:
            _join_cache[uid] = (False, now)
            return False
        _join_cache[uid] = (True, now)
        return True
    status = r.get("result", {}).get("status", "")
    result = status in ("member", "administrator", "creator", "restricted")
    _join_cache[uid] = (result, now)
    return result


def send_join_pm(uid, first_name="کاربر", force=False):
    now = time.time()
    if not force and uid in _join_pm_sent and now - _join_pm_sent[uid] < JOIN_PM_COOLDOWN:
        return
    _join_pm_sent[uid] = now
    ch = get_forced_channel()
    url = f"https://ble.ir/{ch[1:]}" if ch.startswith("@") else f"https://ble.ir/{ch.lstrip('-')}"
    title = FORCED_CHANNEL_TITLE or ch
    text = (f"🔒 سلام {first_name}!\n━━━━━━━━━━━━━━━\n"
            f"برای استفاده ابتدا در کانال زیر عضو شو:\n\n📢 *{title}*\n\n"
            f"بعد روی «✅ عضو شدم» بزن.")
    jk = {"inline_keyboard": [
        [{"text": f"📢 عضویت در {title}", "url": url}],
        [{"text": "✅ عضو شدم", "callback_data": "check_join"}],
    ]}
    send_message(uid, text, jk, safe=False)


# ==================== Customer ====================
def spawn_customer(uid):
    p = get_player(uid)
    if not p or (p["active_customer"] and time.time() < (p["customer_expire"] or 0)):
        return None
    ctype = random.choices(CUSTOMER_TYPES, weights=[40, 30, 15, 8, 7])[0]
    recipe = random.choice(list(RECIPES.keys()))
    qty = random.randint(1, 3)
    reward = int(RECIPES[recipe]["base_price"] * qty * ctype["mult"])
    expire = time.time() + ctype["patience"] * 60
    update_player(uid, active_customer=ctype["name"], customer_expire=expire,
                  customer_order=f"{recipe}:{qty}", customer_reward=reward)
    return {"type": ctype, "recipe": recipe, "qty": qty, "reward": reward, "expire": expire}


def customer_text(cust):
    r = RECIPES[cust["recipe"]]
    mins = int((cust["expire"] - time.time()) / 60)
    return (f"🔔 *مشتری!*\n{cust['type']['emoji']} {cust['type']['name']}\n"
            f"📋 {cust['qty']} {r['emoji']} {r['name']}\n⏰ {mins} دقیقه\n"
            f"💰 {format_money(cust['reward'])}\n\n`تحویل بده`")


def fulfill_customer(uid, chat_id):
    p = get_player(uid)
    if not p or not p["active_customer"]:
        return None
    if time.time() > (p["customer_expire"] or 0):
        update_player(uid, active_customer="", customer_order="", customer_reward=0, customer_expire=0)
        return "expired"
    try:
        recipe, qty = p["customer_order"].split(":")
        qty = int(qty)
    except Exception:
        return None
    field = f"falafel_{recipe}"
    have = p.get(field, 0) or 0
    if have < qty:
        return ("missing", recipe, qty - have)
    reward = int((p["customer_reward"] or 0) * get_total_multiplier(uid))
    update_player(uid, **{field: have - qty}, money=p["money"] + reward,
                  total_earned=(p["total_earned"] or 0) + reward,
                  total_sold=(p["total_sold"] or 0) + qty,
                  active_customer="", customer_order="", customer_reward=0, customer_expire=0)
    add_exp(uid, 10 * qty)
    check_ach(uid, chat_id)
    return ("ok", reward, qty, recipe)


# ==================== Action Helpers ====================
def do_buy(uid, chat_id, item, qty):
    p = get_player(uid)
    if item not in INGREDIENTS:
        send_message(chat_id, "❌ آیتم نامعتبر.")
        return False
    price = ing_price(item, p["mixer_level"], p) * qty
    if p["money"] < price:
        send_message(chat_id, f"❌ پول کافی نداری! نیاز: {format_money(price)}")
        return False
    have = p.get(item, 0) or 0
    update_player(uid, money=p["money"] - price, **{item: have + qty})
    log_txn(uid, "buy", -price, f"خرید {qty} {INGREDIENTS[item]['name']}")
    track_mission(uid, "buy", 1, chat_id)
    send_message(chat_id, f"✅ {qty} {INGREDIENTS[item]['emoji']} {INGREDIENTS[item]['name']}\n💵 -{format_money(price)}\n📦 {have + qty}")
    return True


def do_cook(uid, chat_id, recipe):
    p = get_player(uid)
    if recipe not in RECIPES:
        send_message(chat_id, "❌ نامعتبر.")
        return
    r = RECIPES[recipe]
    missing = []
    for item, need in r["ing"].items():
        have = p.get(item, 0) or 0
        if have < need:
            missing.append(f"{INGREDIENTS[item]['emoji']} {have}/{need}")
    if missing:
        send_message(chat_id, "❌ مواد کم: " + " | ".join(missing))
        return
    double_chance = (p["oven_level"] or 0) * 0.05 + (p.get("skill_cook", 0) or 0) * 0.03
    qty_prod = 2 if random.random() < double_chance else 1
    field = f"falafel_{recipe}"
    up = {field: (p.get(field, 0) or 0) + qty_prod, "total_cooked": (p["total_cooked"] or 0) + qty_prod}
    for item, need in r["ing"].items():
        up[item] = (p.get(item, 0) or 0) - need
    update_player(uid, **up)
    exp = r["exp"] * qty_prod
    if get_today_event() == "cook_bonus":
        exp *= 2
    lvl = add_exp(uid, exp)
    msg = f"✅ {qty_prod}x {r['emoji']} {r['name']}"
    if qty_prod == 2:
        msg += " 🔥"
    msg += f"\n⭐ +{exp}"
    if lvl:
        msg += f"\n🎉 سطح {lvl}! (💎+۱)"
    check_ach(uid, chat_id)
    track_mission(uid, "cook", qty_prod, chat_id)
    send_message(chat_id, msg)


def do_sell(uid, chat_id, target):
    p = get_player(uid)
    mult = get_total_multiplier(uid)
    extra = ""
    if is_weekend():
        extra += "\n🎉 آخر هفته!"
    if get_active_booster(uid) > 1.0:
        extra += "\n⚡ بوستر!"
    if target == "all":
        total, qty, up = 0, 0, {}
        for k in RECIPES:
            h = p.get(f"falafel_{k}", 0) or 0
            if h:
                total += sell_price(k, p["counter_level"], p) * h
                qty += h
                up[f"falafel_{k}"] = 0
        if qty == 0:
            send_message(chat_id, "❌ چیزی نداری!")
            return
        total = int(total * mult)
        update_player(uid, money=p["money"] + total, total_sold=(p["total_sold"] or 0) + qty,
                      total_earned=(p["total_earned"] or 0) + total, **up)
        add_exp(uid, qty * 3)
        check_ach(uid, chat_id)
        track_mission(uid, "sell", total, chat_id)
        send_message(chat_id, f"💰 {qty} فلافل!\n💵 +{format_money(total)}{extra}", safe=False)
        return
    h = p.get(f"falafel_{target}", 0) or 0
    if h == 0:
        send_message(chat_id, f"❌ نداری!")
        return
    total = int(sell_price(target, p["counter_level"], p) * h * mult)
    update_player(uid, money=p["money"] + total, total_sold=(p["total_sold"] or 0) + h,
                  total_earned=(p["total_earned"] or 0) + total, **{f"falafel_{target}": 0})
    add_exp(uid, h * 3)
    check_ach(uid, chat_id)
    track_mission(uid, "sell", total, chat_id)
    send_message(chat_id, f"💰 {h}x {RECIPES[target]['emoji']} {RECIPES[target]['name']}\n💵 +{format_money(total)}{extra}", safe=False)


def do_daily(uid, chat_id):
    p = get_player(uid)
    now = time.time()
    last = p["last_daily"] or 0
    if now - last < 86400:
        h = int((86400 - (now - last)) // 3600)
        m = int(((86400 - (now - last)) % 3600) // 60)
        send_message(chat_id, f"⏰ بعدی: {h}س {m}د")
        return
    streak = (p["daily_streak"] or 0) + 1 if now - last < 172800 else 1
    reward = 500 + min(streak * 200, 3000)
    gems_reward = min(streak // 3, 3)
    up = {"last_daily": now, "daily_streak": streak, "money": p["money"] + reward}
    extra = ""
    if streak % 3 == 0:
        up["flour"] = (p.get("flour", 0) or 0) + 3
        up["chickpeas"] = (p.get("chickpeas", 0) or 0) + 3
        up["oil"] = (p.get("oil", 0) or 0) + 2
        extra += "\n🎉 بونوس: 🌾+۳ 🫘+۳ 🛢+۲"
    update_player(uid, **up)
    if gems_reward > 0:
        add_gems(uid, gems_reward, "جایزه روزانه")
        extra += f"\n💎 +{gems_reward}"
    log_txn(uid, "daily", reward, "جایزه روزانه")
    check_ach(uid, chat_id)
    send_message(chat_id, f"🎁 جایزه!\n💰 +{format_money(reward)}\n🔥 {streak} روز{extra}")


def do_spin(uid, chat_id):
    p = get_player(uid)
    now = time.time()
    if now - (p["last_spin"] or 0) < 86400:
        h = int((86400 - (now - (p["last_spin"] or 0))) // 3600)
        send_message(chat_id, f"⏰ بعدی: {h} ساعت")
        return
    prizes = [
        ("💰 پول کم", 300, "m_300"), ("💰 پول متوسط", 1000, "m_1000"),
        ("💰 پول زیاد", 3000, "m_3000"), ("🌾 آرد", 5, "f_5"),
        ("🫘 نخود", 5, "c_5"), ("🛢 روغن", 5, "o_5"),
        ("💎 الماس", 2, "g_2"), ("💎 جکپات", 5, "g_5"),
        ("💰 جکپات", 10000, "m_10000"), ("😢 خالی", 0, "x"),
    ]
    pr = random.choices(prizes, weights=[22, 18, 8, 10, 10, 10, 8, 3, 3, 8])[0]
    up = {"last_spin": now}
    if pr[2].startswith("m_"):
        up["money"] = p["money"] + pr[1]
        msg_ = f"💵 +{format_money(pr[1])}"
    elif pr[2].startswith("f_"):
        up["flour"] = (p.get("flour", 0) or 0) + pr[1]
        msg_ = f"🌾 +{pr[1]}"
    elif pr[2].startswith("c_"):
        up["chickpeas"] = (p.get("chickpeas", 0) or 0) + pr[1]
        msg_ = f"🫘 +{pr[1]}"
    elif pr[2].startswith("o_"):
        up["oil"] = (p.get("oil", 0) or 0) + pr[1]
        msg_ = f"🛢 +{pr[1]}"
    elif pr[2].startswith("g_"):
        add_gems(uid, pr[1], "گردونه")
        msg_ = f"💎 +{pr[1]}"
    else:
        msg_ = "😢 خالی!"
    update_player(uid, **up)
    send_message(chat_id, f"🎰 *گردونه!*\n🎉 {pr[0]}\n{msg_}", safe=False)


def do_upgrade(uid, chat_id, key):
    p = get_player(uid)
    cost = upgrade_cost(uid, key)
    if cost is None:
        send_message(chat_id, "✅ مکس شده!")
        return
    if p["money"] < cost:
        send_message(chat_id, f"❌ نیاز: {format_money(cost)}")
        return
    new_lvl = (p.get(f"{key}_level", 0) or 0) + 1
    update_player(uid, money=p["money"] - cost, **{f"{key}_level": new_lvl})
    check_ach(uid, chat_id)
    send_message(chat_id, f"✅ {UPGRADES[key]['name']} → {new_lvl}!\n💵 -{format_money(cost)}")


def do_profile(uid, chat_id, first_name):
    p = get_player(uid)
    b = get_bank(uid)
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) c FROM achievements WHERE user_id={ph()}", (uid,))
        ach = c.fetchone()["c"]
    finally:
        close(conn)
    weekend_line = "🎉 آخر هفته: ۲x!" if is_weekend() else ""
    pet_line = f"🐔 پت: سطح {p.get('pet_level', 0) or 0}" if (p.get("pet_level", 0) or 0) > 0 else "🐔 پت نداری"
    tickets = get_lottery_tickets(uid)
    streak_line = f"🔥 استریک: {p.get('win_streak', 0) or 0}" if (p.get("win_streak", 0) or 0) > 0 else ""
    send_message(chat_id,
                 f"👤 *پروفایل {first_name}*\n━━━━━━━━━━━━━━━\n"
                 f"⭐ {p['level']} ({p['exp']}/100)\n"
                 f"💰 {format_money(p['money'])}\n"
                 f"💎 {p.get('gems', 0) or 0}\n"
                 f"🏦 {format_money(b['balance'])}\n"
                 f"📈 {format_money(b['invested'])}\n\n"
                 f"🌾{p.get('flour',0)} 🫘{p.get('chickpeas',0)} 🛢{p.get('oil',0)} 🧀{p.get('cheese',0)} 🌶{p.get('spice',0)}\n"
                 f"🍽 {count_falafel(p)}\n"
                 f"📦 {p['total_sold']} | 💵 {format_money(p['total_earned'])} | 🍳 {p['total_cooked']}\n"
                 f"🎯 {ach}/{len(ACHIEVEMENTS)}\n"
                 f"🔥 {p['daily_streak']} روز\n{streak_line}\n{pet_line}\n"
                 f"🎫 {tickets}\n{booster_status(uid)}\n{weekend_line}", safe=False)


def do_top(chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT first_name, total_earned, level FROM players ORDER BY total_earned DESC LIMIT 10")
        rows = c.fetchall()
    finally:
        close(conn)
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    txt = "🏆 *رتبه‌بندی*\n━━━━━━━━━━━━━━━\n"
    for i, r in enumerate(rows):
        txt += f"{medals[i]} {r['first_name']} — {r['level']} — {format_money(r['total_earned'] or 0)}\n"
    send_message(chat_id, txt, safe=False)


def do_customer(uid, chat_id):
    p = get_player(uid)
    if not p["active_customer"] or time.time() > (p["customer_expire"] or 0):
        if random.random() < 0.4:
            c = spawn_customer(uid)
            if c:
                send_message(chat_id, customer_text(c), safe=False)
                return
        send_message(chat_id, "🔕 مشتری نیست!")
        return
    ctype = next((x for x in CUSTOMER_TYPES if x["name"] == p["active_customer"]), CUSTOMER_TYPES[0])
    recipe, qty = p["customer_order"].split(":")
    c = {"type": ctype, "recipe": recipe, "qty": int(qty),
         "reward": p["customer_reward"], "expire": p["customer_expire"]}
    send_message(chat_id, customer_text(c), safe=False)


def do_serve(uid, chat_id):
    r = fulfill_customer(uid, chat_id)
    if r is None:
        send_message(chat_id, "🔕 مشتری نداری!")
        return
    if r == "expired":
        send_message(chat_id, "⏰ مشتری رفت!")
        return
    if isinstance(r, tuple) and r[0] == "missing":
        send_message(chat_id, f"❌ {r[2]} عدد {RECIPES[r[1]]['name']} کم داری!")
        return
    _, reward, qty, recipe = r
    send_message(chat_id, f"🎉 {qty}x {RECIPES[recipe]['emoji']}\n💰 +{format_money(reward)}")


# ==================== Clan ====================
def get_clan_by_name(name):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT * FROM clans WHERE name={ph()}", (name,))
        r = c.fetchone()
        return dict(r) if r else None
    finally:
        close(conn)


def get_user_clan(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT c.* FROM clans c JOIN clan_members m ON c.id=m.clan_id WHERE m.user_id={ph()}", (uid,))
        r = c.fetchone()
        return dict(r) if r else None
    finally:
        close(conn)


def do_clan_create(uid, chat_id, name):
    name = name.strip()
    if not name or len(name) > 20:
        send_message(chat_id, "❌ اسم ۱-۲۰ کاراکتر.")
        return
    if get_user_clan(uid):
        send_message(chat_id, "❌ توی کلنی!")
        return
    if get_clan_by_name(name):
        send_message(chat_id, "❌ وجود داره.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO clans (name, owner_id, created_at) VALUES ({ph()},{ph()},{ph()})",
                  (name, uid, time.time()))
        c.execute(f"SELECT id FROM clans WHERE name={ph()}", (name,))
        cid = c.fetchone()["id"]
        c.execute(f"INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES ({ph()},{ph()},{ph()})",
                  (cid, uid, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"🏰 کلن «{name}» ساخته شد!")


def do_clan_join(uid, chat_id, name):
    if get_user_clan(uid):
        send_message(chat_id, "❌ توی کلنی!")
        return
    clan = get_clan_by_name(name)
    if not clan:
        send_message(chat_id, "❌ پیدا نشد.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES ({ph()},{ph()},{ph()})",
                  (clan["id"], uid, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"✅ عضو کلن «{name}» شدی!")


def do_clan_leave(uid, chat_id):
    clan = get_user_clan(uid)
    if not clan:
        send_message(chat_id, "❌ توی کلنی نیستی.")
        return
    if clan["owner_id"] == uid:
        send_message(chat_id, "❌ مالک نمی‌تونه خارج شه.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"DELETE FROM clan_members WHERE user_id={ph()}", (uid,))
        c.execute(f"SELECT COUNT(*) as cnt FROM clan_members WHERE clan_id={ph()}", (clan["id"],))
        if c.fetchone()["cnt"] == 0:
            c.execute(f"DELETE FROM clans WHERE id={ph()}", (clan["id"],))
            send_message(chat_id, f"✅ خارج شدی. کلن حذف شد.")
        else:
            send_message(chat_id, f"✅ خارج شدی.")
        conn.commit()
    finally:
        close(conn)


def do_clan_info(uid, chat_id):
    clan = get_user_clan(uid)
    if not clan:
        send_message(chat_id, "❌ توی کلنی نیستی.\n`کلن بساز [اسم]`")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT user_id FROM clan_members WHERE clan_id={ph()}", (clan["id"],))
        members = [r["user_id"] for r in c.fetchall()]
    finally:
        close(conn)
    send_message(chat_id,
                 f"🏰 *کلن {clan['name']}*\n👑 مالک: `{clan['owner_id']}`\n"
                 f"👥 اعضا: {len(members)}\n💰 گنجینه: {format_money(clan['treasury'] or 0)}\n"
                 f"⭐ امتیاز: {clan['points'] or 0}", safe=False)


def do_clan_donate(uid, chat_id, amount):
    clan = get_user_clan(uid)
    if not clan:
        send_message(chat_id, "❌ اول عضو شو.")
        return
    p = get_player(uid)
    if amount <= 0 or p["money"] < amount:
        send_message(chat_id, "❌ پول کافی نیست.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"UPDATE clans SET treasury=treasury+{ph()}, points=points+{ph()} WHERE id={ph()}",
                  (amount, amount // 100, clan["id"]))
        conn.commit()
    finally:
        close(conn)
    update_player(uid, money=p["money"] - amount)
    send_message(chat_id, f"✅ {format_money(amount)} به گنجینه اضافه شد!")


def do_clan_top(chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT name, treasury, points FROM clans ORDER BY points DESC, treasury DESC LIMIT 10")
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "هنوز کلنی نیست.")
        return
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    txt = "🏆 *کلن‌ها*\n"
    for i, r in enumerate(rows):
        txt += f"{medals[i]} {r['name']} — ⭐{r['points'] or 0} — 💰{format_money(r['treasury'] or 0)}\n"
    send_message(chat_id, txt, safe=False)


# ==================== Duel ====================
def do_duel(challenger_id, chat_id, opponent_id, amount):
    if challenger_id == opponent_id:
        send_message(chat_id, "❌ با خودت نمی‌شه!")
        return
    if amount < 1000:
        send_message(chat_id, "❌ حداقل ۱,۰۰۰!")
        return
    cp = get_player(challenger_id)
    op = get_player(opponent_id)
    if not cp or not op:
        send_message(chat_id, "❌ یکی نیست.")
        return
    if cp["money"] < amount or op["money"] < amount:
        send_message(chat_id, "❌ یکی پول کافی نداره!")
        return
    winner_id = random.choice([challenger_id, opponent_id])
    loser_id = opponent_id if winner_id == challenger_id else challenger_id
    tax = amount * 2 // 20
    wp = get_player(winner_id)
    lp = get_player(loser_id)
    update_player(winner_id, money=wp["money"] + amount - tax,
                  total_earned=(wp["total_earned"] or 0) + amount - tax)
    update_player(loser_id, money=lp["money"] - amount)
    send_message(chat_id,
                 f"⚔️ *دوئل!*\n💰 {format_money(amount)}\n🎲 کمیسیون: {format_money(tax)}\n\n"
                 f"🏆 برنده: {wp['first_name']}\n💰 سود: {format_money(amount - tax)}", safe=False)


# ==================== Missions ====================
def get_missions(uid):
    today = today_local().isoformat()
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT missions, completed FROM daily_missions WHERE user_id={ph()} AND day={ph()}", (uid, today))
        r = c.fetchone()
        if r:
            return json.loads(r["missions"]), json.loads(r["completed"])
        missions = [
            {"id": "cook", "title": "🍳 بپز", "target": random.randint(3, 8), "reward": random.randint(500, 1500), "progress": 0},
            {"id": "sell", "title": "💰 فروش بگیر", "target": random.randint(3000, 12000), "reward": random.randint(1000, 2500), "progress": 0},
            {"id": "buy", "title": "🛒 مواد بخر", "target": random.randint(3, 10), "reward": random.randint(500, 1000), "progress": 0},
        ]
        try:
            if USE_POSTGRES:
                c.execute(f"INSERT INTO daily_missions (user_id, day, missions, completed) VALUES ({ph()},{ph()},{ph()},{ph()}) ON CONFLICT (user_id, day) DO NOTHING",
                          (uid, today, json.dumps(missions), json.dumps([])))
            else:
                c.execute("INSERT OR REPLACE INTO daily_missions VALUES (?,?,?,?)",
                          (uid, today, json.dumps(missions), json.dumps([])))
            conn.commit()
        except Exception:
            pass
        return missions, []
    finally:
        close(conn)


def track_mission(uid, kind, value, chat_id):
    try:
        today = today_local().isoformat()
        missions, completed = get_missions(uid)
        changed = False
        for m in missions:
            if m["id"] == kind and m["id"] not in completed:
                m["progress"] += value
                if m["progress"] >= m["target"]:
                    completed.append(m["id"])
                    p = get_player(uid)
                    update_player(uid, money=p["money"] + m["reward"])
                    log_txn(uid, "mission", m["reward"], m["title"])
                    send_message(chat_id, f"🎯 ماموریت!\n{m['title']} ✅\n💰 +{format_money(m['reward'])}")
                changed = True
        if changed:
            conn = db()
            try:
                c = conn.cursor()
                c.execute(f"UPDATE daily_missions SET missions={ph()}, completed={ph()} WHERE user_id={ph()} AND day={ph()}",
                          (json.dumps(missions), json.dumps(completed), uid, today))
                conn.commit()
            finally:
                close(conn)
    except Exception:
        pass


def do_missions(uid, chat_id):
    missions, completed = get_missions(uid)
    txt = "🎯 *ماموریت‌های امروز*\n"
    for m in missions:
        done = "✅" if m["id"] in completed else "⏳"
        bar_len = min(int((m["progress"] / m["target"]) * 10), 10) if m["target"] else 0
        txt += f"{done} {m['title']}: {m['progress']}/{m['target']} {'█'*bar_len}{'░'*(10-bar_len)} 💰{format_money(m['reward'])}\n"
    send_message(chat_id, txt, safe=False)


# ==================== Card Transfer ====================
def do_transfer(sender_id, chat_id, receiver_id, amount, sender_name="کاربر"):
    if sender_id == receiver_id:
        send_message(chat_id, "❌ به خودت نمی‌شه!")
        return
    if amount < TRANSFER_MIN or amount > TRANSFER_MAX:
        send_message(chat_id, f"❌ بین {format_money(TRANSFER_MIN)} و {format_money(TRANSFER_MAX)}!")
        return
    sp = get_player(sender_id)
    rp = get_player(receiver_id)
    if not sp or not rp:
        send_message(chat_id, "❌ یکی نیست.")
        return
    commission = int(amount * TRANSFER_COMMISSION)
    total = amount + commission
    if sp["money"] < total:
        send_message(chat_id, f"❌ نیاز: {format_money(total)} (با کمیسیون)")
        return
    update_player(sender_id, money=sp["money"] - total)
    update_player(receiver_id, money=rp["money"] + amount)
    log_txn(sender_id, "transfer_out", -total, f"به {receiver_id}")
    log_txn(receiver_id, "transfer_in", amount, f"از {sender_id}")
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO card_transfers (sender_id, receiver_id, amount, commission, ts) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()})",
                  (sender_id, receiver_id, amount, commission, time.time()))
        conn.commit()
    except Exception:
        pass
    finally:
        close(conn)
    send_message(chat_id,
                 f"💳 *کارت به کارت*\n👤 به: {rp['first_name']}\n💰 {format_money(amount)}\n"
                 f"💸 کمیسیون: {format_money(commission)}\n💰 موجودی: {format_money(sp['money'] - total)}", safe=False)
    try:
        send_message(receiver_id, f"💳 *پول گرفتی!*\n👤 از: {sender_name}\n💰 +{format_money(amount)}", safe=False)
    except Exception:
        pass


def do_admin_transfer(admin_id, chat_id, receiver_id, amount, note=""):
    if not is_admin(admin_id):
        return
    if amount <= 0 or amount > ADMIN_MONEY_LIMIT:
        send_message(chat_id, f"❌ ۱ تا {format_money(ADMIN_MONEY_LIMIT)}!", ADMIN_KB())
        return
    rp = get_player(receiver_id)
    if not rp:
        send_message(chat_id, f"❌ `{receiver_id}` پیدا نشد.", ADMIN_KB(), safe=False)
        return
    update_player(receiver_id, money=rp["money"] + amount)
    log_txn(receiver_id, "admin_transfer", amount, "ادمین")
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"INSERT INTO admin_txns (target_id, admin_id, amount, note, ts) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()})",
                  (receiver_id, admin_id, amount, note or "کارت به کارت ادمین", time.time()))
        conn.commit()
    except Exception:
        pass
    finally:
        close(conn)
    send_message(chat_id, f"✅ به `{receiver_id}` {format_money(amount)}", ADMIN_KB(), safe=False)
    try:
        send_message(receiver_id, f"💳 ادمین {format_money(amount)} بهت داد!")
    except Exception:
        pass


# ==================== Admin ====================
def do_admin_add_money(uid, chat_id, target_id, amount):
    if not is_admin(uid):
        return
    if amount <= 0 or amount > ADMIN_MONEY_LIMIT:
        send_message(chat_id, f"❌ ۱ تا {format_money(ADMIN_MONEY_LIMIT)}!")
        return
    tp = get_player(target_id)
    if not tp:
        send_message(chat_id, f"❌ `{target_id}` نیست.", ADMIN_KB(), safe=False)
        return
    update_player(target_id, money=tp["money"] + amount)
    log_txn(target_id, "admin_add", amount, "افزودن ادمین")
    send_message(chat_id, f"✅ به `{target_id}` {format_money(amount)} اضافه شد.", ADMIN_KB(), safe=False)
    try:
        send_message(target_id, f"🎁 ادمین {format_money(amount)} بهت داد!")
    except Exception:
        pass


def do_admin_undo(txn_id, admin_id, chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT * FROM admin_txns WHERE id={ph()}", (txn_id,))
        r = c.fetchone()
        if not r:
            send_message(chat_id, "❌ نیست.", ADMIN_KB())
            return
        txn = dict(r)
        if txn["reversed"]:
            send_message(chat_id, "❌ قبلاً برگشت خورد.", ADMIN_KB())
            return
        tp = get_player(txn["target_id"])
        if not tp:
            send_message(chat_id, "❌ کاربر نیست.", ADMIN_KB())
            return
        update_player(txn["target_id"], money=tp["money"] - txn["amount"])
        c.execute(f"UPDATE admin_txns SET reversed=1 WHERE id={ph()}", (txn_id,))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"✅ برگشت خورد.", ADMIN_KB(), safe=False)


def do_reset_all(uid, chat_id):
    if not is_admin(uid):
        return
    conn = db()
    try:
        c = conn.cursor()
        for t in ["players", "achievements", "transactions", "shop_orders", "clans", "clan_members",
                  "duels", "daily_missions", "admin_txns", "banks", "user_states",
                  "casino_log", "card_transfers", "discount_codes", "boosters", "reminders",
                  "lottery", "lottery_winners", "daily_events", "gems_log"]:
            try:
                c.execute(f"DELETE FROM {t}")
            except Exception:
                pass
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, "✅ *ریست کلی انجام شد!*", ADMIN_KB(), safe=False)


def do_redeem_code(uid, chat_id, code):
    code = code.strip().upper()
    if not code:
        send_message(chat_id, "مثال: `کد WELCOME`")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT * FROM discount_codes WHERE code={ph()}", (code,))
        r = c.fetchone()
        if not r:
            send_message(chat_id, "❌ کد نیست!")
            return
        d = dict(r)
        if d["uses"] >= d["max_uses"]:
            send_message(chat_id, "❌ ظرفیت پر!")
            return
        try:
            used = json.loads(d["used_by"] or "[]")
        except Exception:
            used = []
        if uid in used:
            send_message(chat_id, "❌ استفاده کردی!")
            return
        p = get_player(uid)
        amount = d["amount"] or 0
        update_player(uid, money=p["money"] + amount)
        used.append(uid)
        c.execute(f"UPDATE discount_codes SET uses=uses+1, used_by={ph()} WHERE code={ph()}",
                  (json.dumps(used), code))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"✅ کد فعال!\n💰 +{format_money(amount)}")


def do_admin_create_code(uid, chat_id, code, amount, max_uses=1):
    if not is_admin(uid):
        return
    code = code.strip().upper()
    if not code or amount <= 0 or amount > 100000:
        send_message(chat_id, "فرمت: `کد بساز WELCOME 5000 10`")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT code FROM discount_codes WHERE code={ph()}", (code,))
        if c.fetchone():
            send_message(chat_id, f"❌ وجود داره.", ADMIN_KB(), safe=False)
            return
        c.execute(f"INSERT INTO discount_codes (code, amount, max_uses, created_by, created_at, used_by) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()},'[]')",
                  (code, amount, max_uses, uid, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"✅ کد `{code}` ساخته شد!", ADMIN_KB(), safe=False)


def do_admin_list_codes(uid, chat_id):
    if not is_admin(uid):
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM discount_codes ORDER BY created_at DESC LIMIT 15")
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "🎟 کدی نیست.", ADMIN_KB())
        return
    txt = "🎟 *کدها*\n"
    for r in rows:
        txt += f"• `{r['code']}` — {format_money(r['amount'])} ({r['uses']}/{r['max_uses']})\n"
    send_message(chat_id, txt, ADMIN_KB(), safe=False)


# ==================== Parser ====================
def parse_text_command(uid, chat_id, first_name, username, text):
    text = normalize_numbers(text)
    if text.startswith(("خرید", "بخر", "آشپزی", "بپز", "فروش", "بفروش", "جایزه", "گردونه",
                        "آپگرید", "مشتری", "تحویل", "کازینو", "اسلات", "جعبه",
                        "کارت", "انتقال", "بوستر", "کد", "لاتاری", "مهارت", "پت",
                        "هدیه", "الماس", "رتبه", "پروفایل")):
        if not check_user_cooldown(uid):
            return True
    p = get_player(uid)
    if not p:
        create_player(uid, first_name, username)
        p = get_player(uid)
    t = text.strip()
    if not t:
        return False
    nums = re.findall(r'\d+', t)
    qty = int(nums[0]) if nums else 1

    # خرید
    if t.startswith("خرید") or t.startswith("بخر"):
        if "آرد" in t:
            do_buy(uid, chat_id, "flour", qty); return True
        if "نخود" in t:
            do_buy(uid, chat_id, "chickpeas", qty); return True
        if "روغن" in t:
            do_buy(uid, chat_id, "oil", qty); return True
        if "پنیر" in t:
            do_buy(uid, chat_id, "cheese", qty); return True
        if "ادویه" in t:
            do_buy(uid, chat_id, "spice", qty); return True
        send_message(chat_id, "🛒 `خرید آرد ۵` | `خرید نخود ۳` | ...", safe=False)
        return True

    if t.startswith("آشپزی") or t.startswith("بپز") or t.startswith("پخت"):
        if "ساندویچ" in t:
            do_cook(uid, chat_id, "sandwich"); return True
        if "دلوکس" in t or "لوکس" in t:
            do_cook(uid, chat_id, "deluxe"); return True
        if "پنیر" in t:
            do_cook(uid, chat_id, "cheese"); return True
        if "تند" in t:
            do_cook(uid, chat_id, "spicy"); return True
        if "حرفه" in t or "مخصوص" in t or "ویژه" in t:
            do_cook(uid, chat_id, "special"); return True
        if "ساده" in t or "معمولی" in t:
            do_cook(uid, chat_id, "simple"); return True
        send_message(chat_id, "🍳 `آشپزی ساده` | `آشپزی حرفه‌ای` | ...", safe=False)
        return True

    if t.startswith("فروش") or t.startswith("بفروش"):
        if "همه" in t or "کل" in t:
            do_sell(uid, chat_id, "all"); return True
        if "ساندویچ" in t:
            do_sell(uid, chat_id, "sandwich"); return True
        if "دلوکس" in t:
            do_sell(uid, chat_id, "deluxe"); return True
        if "پنیر" in t:
            do_sell(uid, chat_id, "cheese"); return True
        if "تند" in t:
            do_sell(uid, chat_id, "spicy"); return True
        if "حرفه" in t or "مخصوص" in t:
            do_sell(uid, chat_id, "special"); return True
        if "ساده" in t:
            do_sell(uid, chat_id, "simple"); return True
        send_message(chat_id, "💰 `فروش همه`")
        return True

    if t.startswith("جایزه") or t.startswith("پاداش"):
        do_daily(uid, chat_id); return True
    if t.startswith("گردونه") or "گردونه" in t:
        do_spin(uid, chat_id); return True
    if t.startswith("آپگرید") or t.startswith("ارتقا"):
        if "تنور" in t:
            do_upgrade(uid, chat_id, "oven"); return True
        if "مخلوط" in t:
            do_upgrade(uid, chat_id, "mixer"); return True
        if "پیشخوان" in t or "کانتر" in t:
            do_upgrade(uid, chat_id, "counter"); return True
        send_message(chat_id, "⚙️ `آپگرید تنور` | `مخلوط‌کن` | `پیشخوان`")
        return True
    if t.startswith("پروفایل") or t == "من":
        do_profile(uid, chat_id, first_name); return True
    if t.startswith("رتبه") or t.startswith("تاپ") or t.startswith("برترین"):
        do_top(chat_id); return True
    if t.startswith("مشتری") or t.startswith("سفارش"):
        do_customer(uid, chat_id); return True
    if t.startswith("تحویل") or "تحویل بده" in t:
        do_serve(uid, chat_id); return True
    if t.startswith("ماموریت"):
        do_missions(uid, chat_id); return True

    if t.startswith("بانک"):
        body = t[4:].strip()
        amt = int(nums[0]) if nums else 0
        if body.startswith("واریز"):
            do_bank_deposit(uid, chat_id, amt); return True
        if body.startswith("برداشت"):
            do_bank_withdraw(uid, chat_id, amt); return True
        if body.startswith("سرمایه"):
            do_bank_invest(uid, chat_id, amt); return True
        if body.startswith("پایان"):
            do_bank_end_invest(uid, chat_id, amt); return True
        if body.startswith("جمع") or body.startswith("سود"):
            do_bank_collect(uid, chat_id); return True
        do_bank(uid, chat_id, first_name); return True

    if t.startswith("کازینو"):
        body = t[6:].strip()
        if not nums:
            send_message(chat_id, "🎰 `کازینو ۵۰۰۰ شیر` / `خط`")
            return True
        if "شیر" in body:
            do_casino(uid, chat_id, int(nums[0]), "شیر"); return True
        if "خط" in body:
            do_casino(uid, chat_id, int(nums[0]), "خط"); return True
        send_message(chat_id, "❌ `کازینو ۵۰۰۰ شیر`")
        return True

    if t.startswith("اسلات"):
        amt = int(nums[0]) if nums else 0
        do_slot(uid, chat_id, amt); return True

    if t.startswith("جعبه"):
        do_mystery_box(uid, chat_id); return True

    if t.startswith("بوستر"):
        if "وضعیت" in t:
            send_message(chat_id, booster_status(uid)); return True
        if "بخر" in t or t == "بوستر":
            do_booster(uid, chat_id); return True
        send_message(chat_id, "⚡ `بوستر بخر` — ۵,۰۰۰"); return True

    if t.startswith("لاتاری"):
        body = t[6:].strip()
        if body.startswith("بخر"):
            do_lottery_buy(uid, chat_id); return True
        do_lottery_panel(uid, chat_id); return True

    if t.startswith("مهارت"):
        body = t[5:].strip()
        if body.startswith("بخر"):
            key = body.replace("بخر", "").strip().lower()
            do_skill_buy(uid, chat_id, key); return True
        do_skills_panel(uid, chat_id); return True

    if t.startswith("پت"):
        body = t[2:].strip()
        if body.startswith("بخر"):
            do_pet_buy(uid, chat_id); return True
        if body.startswith("غذا"):
            do_pet_feed(uid, chat_id); return True
        do_pet_panel(uid, chat_id); return True

    if t.startswith("الماس"):
        body = t[5:].strip()
        if body.startswith("بخر"):
            key = body.replace("بخر", "").strip().lower()
            do_gem_buy(uid, chat_id, key); return True
        do_gem_shop(uid, chat_id); return True

    if t.startswith("هدیه"):
        nums_h = re.findall(r'\d+', t)
        if len(nums_h) >= 2:
            rid = int(nums_h[0]) if int(nums_h[0]) > 99999 else int(nums_h[1])
            amt = int(nums_h[1]) if int(nums_h[0]) > 99999 else int(nums_h[0])
            sp = get_player(uid)
            rp = get_player(rid)
            if not rp or sp["money"] < amt or amt < 100:
                send_message(chat_id, "❌ نامعتبر یا پول کافی نیست.")
                return True
            update_player(uid, money=sp["money"] - amt)
            update_player(rid, money=rp["money"] + amt)
            send_message(chat_id, f"🎁 به {rp['first_name']} {format_money(amt)} هدیه دادی!")
            return True
        send_message(chat_id, "مثال: `هدیه 123456789 5000`"); return True

    if t.startswith("یادآور"):
        body = t[5:].strip()
        if body.startswith("لیست") or not body:
            do_reminder_list(uid, chat_id); return True
        parts = body.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id, "`یادآور ۱۰m جلسه`"); return True
        m = re.match(r'^(\d+)([smh])$', parts[0].lower())
        if not m:
            send_message(chat_id, "❌ فرمت: `۱۰m`"); return True
        sec = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]
        do_reminder_set(uid, chat_id, parts[1], sec); return True

    if t.startswith("کد"):
        body = t[2:].strip()
        if not body:
            send_message(chat_id, "`کد WELCOME`"); return True
        if is_admin(uid) and ("بساز" in body or "ساخت" in body):
            parts = body.replace("بساز", "").replace("ساخت", "").strip().split()
            if len(parts) < 2:
                send_message(chat_id, "`کد بساز WELCOME 5000 10`"); return True
            code = parts[0]
            amount = int(parts[1]) if parts[1].isdigit() else 0
            max_uses = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
            do_admin_create_code(uid, chat_id, code, amount, max_uses); return True
        if is_admin(uid) and body.startswith("لیست"):
            do_admin_list_codes(uid, chat_id); return True
        do_redeem_code(uid, chat_id, body.split()[0]); return True

    if t.startswith("کارت به کارت") or t.startswith("انتقال"):
        nums_ct = re.findall(r'\d+', t)
        if len(nums_ct) >= 2:
            if int(nums_ct[0]) > 99999:
                rid = int(nums_ct[0]); amt = int(nums_ct[1])
            else:
                amt = int(nums_ct[0]); rid = int(nums_ct[1])
            do_transfer(uid, chat_id, rid, amt, first_name); return True
        send_message(chat_id, "❌ `کارت به کارت ID مبلغ` یا ریپلای."); return True

    if t.startswith("کلن"):
        body = t[3:].strip()
        if body.startswith("بساز"):
            name = body.replace("بساز", "").strip()
            do_clan_create(uid, chat_id, name); return True
        if body.startswith("عضو شو"):
            name = body.replace("عضو شو", "").strip()
            do_clan_join(uid, chat_id, name); return True
        if body.startswith("خروج") or body.startswith("ترک"):
            do_clan_leave(uid, chat_id); return True
        if body.startswith("لیست") or body.startswith("رتبه"):
            do_clan_top(chat_id); return True
        if body.startswith("اهدا") or body.startswith("کمک"):
            nums2 = re.findall(r'\d+', body)
            if nums2:
                do_clan_donate(uid, chat_id, int(nums2[0])); return True
        do_clan_info(uid, chat_id); return True

    if t.startswith("راهنما") or t == "کمک":
        send_message(chat_id,
                     "📋 *دستورات*\n"
                     "🛒 `خرید آرد ۵` | 🍳 `آشپزی ساده` | 💰 `فروش همه`\n"
                     "🎁 `جایزه روزانه` | 🎰 `گردونه` | 🎰 `اسلات ۵۰۰۰`\n"
                     "🏦 `بانک` | ⚙️ `آپگرید تنور` | 👤 `پروفایل`\n"
                     "🔔 `مشتری` | ✅ `تحویل بده` | 🎯 `ماموریت`\n"
                     "🎫 `لاتاری` | 🎓 `مهارت‌ها` | 🐔 `پت`\n"
                     "💎 `الماس` | ⚡ `بوستر بخر` | 🎁 `جعبه`\n"
                     "💳 `کارت به کارت ID مبلغ` (یا ریپلای)\n"
                     "🎟 `کد WELCOME` | 🏰 `کلن بساز [اسم]`\n"
                     "⚔️ ریپلای + `دوئل ۵۰۰۰`\n\n"
                     "🎮 `/game` — منوی گروه", safe=False)
        return True

    return False


# ==================== Keyboards ====================
def kb(rows):
    return {"keyboard": [[{"text": t} for t in row] for row in rows], "resize_keyboard": True}


def PRIVATE_KB(uid=None):
    rows = [
        ["🛒 فروشگاه", "🏦 بانک"],
        ["🎰 کازینو", "🎰 اسلات"],
        ["🎫 لاتاری", "🎁 جعبه"],
        ["🎓 مهارت‌ها", "🐔 پت"],
        ["⚡ بوستر", "💎 الماس"],
        ["💳 کارت به کارت", "🔔 یادآور"],
        ["📖 راهنما", "👤 پروفایل من"],
        ["💳 خریدهای من"],
    ]
    if uid and is_admin(uid):
        rows.append(["👑 پنل ادمین"])
    return kb(rows)


def ADMIN_KB():
    return kb([
        ["📥 سفارشات", "📊 آمار کل"],
        ["💰 افزودن پول", "💳 کارت به کارت ادمین"],
        ["🎁 هدیه همگانی", "🎟 کد تخفیف"],
        ["📢 پیام همگانی", "🗑 ریست کلی"],
        ["🔙 بازگشت"]
    ])


def BANK_KB():
    return kb([["🏦 موجودی", "📊 راهنما"], ["🔙 بازگشت"]])


def GROUP_KB():
    return {"inline_keyboard": [
        [{"text": "🛒 خرید", "callback_data": "g:buy"}, {"text": "🍳 آشپزی", "callback_data": "g:cook"}],
        [{"text": "💰 فروش", "callback_data": "g:sell"}, {"text": "🎁 جایزه", "callback_data": "g:daily"}],
        [{"text": "🎰 گردونه", "callback_data": "g:spin"}, {"text": "🎰 اسلات", "callback_data": "g:slot"}],
        [{"text": "⚙️ آپگرید", "callback_data": "g:up"}, {"text": "🏦 بانک", "callback_data": "g:bank"}],
        [{"text": "🏰 کلن", "callback_data": "g:clan"}, {"text": "⚔️ دوئل", "callback_data": "g:duel"}],
        [{"text": "🎯 ماموریت", "callback_data": "g:mission"}, {"text": "👤 پروفایل", "callback_data": "g:me"}],
        [{"text": "🏆 رتبه", "callback_data": "g:top"}, {"text": "❌ بستن", "callback_data": "g:close"}],
    ]}


GUIDES = {
    "buy": "🛒 *خرید*\n\n`خرید آرد ۵`\n`خرید نخود ۳`\n`خرید روغن ۲`\n`خرید پنیر ۳`\n`خرید ادویه ۳`",
    "cook": "🍳 *آشپزی*\n\n`آشپزی ساده` 🟡\n`آشپزی حرفه‌ای` 🟠\n`آشپزی ساندویچ` 🥙\n`آشپزی پنیری` 🧀\n`آشپزی تند` 🌶\n`آشپزی دلوکس` 👑",
    "sell": "💰 *فروش*\n\n`فروش همه`\n`فروش ساده` | `فروش مخصوص`",
    "daily": "🎁 *جایزه روزانه*\n\n`جایزه روزانه`",
    "spin": "🎰 *گردونه*\n\n`گردونه شانس`",
    "up": "⚙️ *آپگرید*\n\n`آپگرید تنور` 🔥\n`آپگرید مخلوط‌کن` 🥣\n`آپگرید پیشخوان` 🏪",
    "me": "👤 *پروفایل*\n\n`پروفایل`",
    "top": "🏆 *رتبه*\n\n`رتبه`",
    "cust": "🔔 *مشتری*\n\n`مشتری` | `تحویل بده`",
    "clan": "🏰 *کلن*\n\n`کلن بساز [اسم]`\n`کلن عضو شو [اسم]`\n`کلن من`\n`کلن لیست`\n`کلن اهدا ۵۰۰۰`\n`کلن خروج`",
    "duel": "⚔️ *دوئل*\n\nروی پیام حریف ریپلای کن:\n`دوئل ۵۰۰۰`",
    "mission": "🎯 *ماموریت*\n\n`ماموریت`",
    "bank": "🏦 *بانک*\n\n`بانک واریز ۵۰۰۰`\n`بانک برداشت ۵۰۰۰`\n`بانک سرمایه ۵۰۰۰`\n`بانک جمع`",
    "casino": "🎰 *کازینو*\n\n`کازینو ۵۰۰۰ شیر`\n`کازینو ۵۰۰۰ خط`",
    "slot": "🎰 *اسلات*\n\n`اسلات ۵۰۰۰`",
    "boost": "⚡ *بوستر*\n\n`بوستر بخر` — ۵,۰۰۰",
    "lottery": "🎫 *لاتاری*\n\n`لاتاری` | `لاتاری بخر`",
    "skills": "🎓 *مهارت*\n\n`مهارت‌ها`\n`مهارت بخر cook`",
    "pet": "🐔 *پت*\n\n`پت` | `پت بخر` | `پت غذا بده`",
    "gems": "💎 *فروشگاه الماس*\n\n`الماس`\n`الماس بخر booster`",
}


# ==================== State ====================
def set_state(uid, state, data=""):
    conn = db()
    try:
        c = conn.cursor()
        if USE_POSTGRES:
            c.execute(f"INSERT INTO user_states (user_id, state, data) VALUES ({ph()},{ph()},{ph()}) ON CONFLICT (user_id) DO UPDATE SET state={ph()}, data={ph()}",
                      (uid, state, json.dumps(data), state, json.dumps(data)))
        else:
            c.execute("INSERT OR REPLACE INTO user_states VALUES (?,?,?)", (uid, state, json.dumps(data)))
        conn.commit()
    finally:
        close(conn)


def get_state(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT state, data FROM user_states WHERE user_id={ph()}", (uid,))
        r = c.fetchone()
        if not r:
            return None, None
        try:
            data = json.loads(r["data"]) if r["data"] else None
        except Exception:
            data = r["data"]
        return r["state"], data
    finally:
        close(conn)


def clear_state(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"DELETE FROM user_states WHERE user_id={ph()}", (uid,))
        conn.commit()
    finally:
        close(conn)


# ==================== Private Handler ====================
def handle_private(msg, uid, chat_id, first_name, username, text):
    if text == "/start":
        clear_join_cache(uid)
    if text == "/cancel":
        clear_state(uid)
        send_message(chat_id, "✅ لغو شد.", PRIVATE_KB(uid)); return
    if text == "/check":
        clear_join_cache(uid)
        if is_joined(uid, use_cache=False):
            send_message(chat_id, "✅ تایید شد!", PRIVATE_KB(uid))
        else:
            send_join_pm(uid, first_name, force=True)
        return
    if not is_joined(uid):
        send_join_pm(uid, first_name, force=(text == "/start")); return
    if not get_player(uid):
        create_player(uid, first_name, username)
    p = get_player(uid)

    if text == "/myid":
        send_message(chat_id, f"🆔 `{uid}`", PRIVATE_KB(uid), safe=False); return
    if text == "/version":
        send_message(chat_id, f"📦 `{VERSION}`\n🗄 {'PostgreSQL' if USE_POSTGRES else 'SQLite'}", PRIVATE_KB(uid), safe=False); return

    if text in ("/admin", "/panel", "👑 پنل ادمین"):
        if is_admin(uid):
            show_admin_panel(chat_id, uid)
        else:
            send_message(chat_id, f"⛔ ادمین نیستی.\nآیدی تو: `{uid}`\nآیدی‌های ادمین: `{ADMIN_IDS}`",
                         safe=False)
        return

    if text == "/start":
        event_line = ""
        if get_today_event() != "normal":
            event_line = f"\n\n{get_today_event_desc()}"
        send_message(chat_id,
                     f"🍔 سلام {first_name}!\n━━━━━━━━━━━━━━━\n"
                     f"خوش اومدی!\n\n"
                     f"🎮 بازی: من رو به گروه اضافه کن و `/game` بزن!{event_line}\n\n"
                     f"از منوی پایین شروع کن 👇", PRIVATE_KB(uid), safe=False)
        return

    if text == "/help" or text == "📖 راهنما":
        send_message(chat_id,
                     "📖 *راهنما*\n"
                     "🎮 بازی توی گروه: `/game`\n"
                     "🛒 توی این بات: فروشگاه، بانک، کازینو، اسلات، لاتاری، مهارت، پت، الماس\n"
                     "📋 دستورات کامل: توی گروه `راهنما`",
                     PRIVATE_KB(uid), safe=False)
        return

    # دکمه‌های منو
    if text in ("🏦 بانک", "/bank"):
        do_bank(uid, chat_id, first_name); return
    if text == "📊 راهنما":
        send_message(chat_id,
                     "📊 *راهنمای بانک*\n`بانک واریز ۵۰۰۰`\n`بانک برداشت ۵۰۰۰`\n"
                     "`بانک سرمایه ۵۰۰۰`\n`بانک پایان ۵۰۰۰`\n`بانک جمع`\n\n📊 سود: ۲۰٪ روزانه",
                     BANK_KB(), safe=False)
        return
    if text == "🎰 کازینو":
        send_message(chat_id, "🎰 `کازینو ۵۰۰۰ شیر` / `خط`", PRIVATE_KB(uid)); return
    if text == "🎰 اسلات":
        send_message(chat_id, "🎰 `اسلات ۵۰۰۰` — ۳ ریل، شانس جکپات!", PRIVATE_KB(uid)); return
    if text == "🎁 جعبه":
        do_mystery_box(uid, chat_id); return
    if text == "⚡ بوستر":
        do_booster(uid, chat_id); return
    if text == "🎫 لاتاری":
        do_lottery_panel(uid, chat_id); return
    if text == "🎓 مهارت‌ها":
        do_skills_panel(uid, chat_id); return
    if text == "🐔 پت":
        do_pet_panel(uid, chat_id); return
    if text == "💎 الماس":
        do_gem_shop(uid, chat_id); return
    if text == "🔔 یادآور":
        send_message(chat_id, "🔔 `یادآور ۱۰m جلسه` | `یادآور لیست`", PRIVATE_KB(uid)); return
    if text == "💳 کارت به کارت":
        send_message(chat_id,
                     "💳 *کارت به کارت*\n"
                     "روش ۱: `کارت به کارت ID مبلغ`\n"
                     "روش ۲: روی پیام کاربر ریپلای کن و بنویس `انتقال ۵۰۰۰`\n\n"
                     "💸 کمیسیون ۲٪ | بین ۵۰۰ تا ۵۰,۰۰۰",
                     PRIVATE_KB(uid), safe=False)
        return
    if text in ("👤 پروفایل من", "/profile"):
        do_profile(uid, chat_id, first_name); return
    if text in ("🛒 فروشگاه", "/shop"):
        rows = []
        for key, pkg in SHOP_PACKAGES.items():
            rows.append([{"text": f"{pkg['name']} — {pkg['coins']:,} / {pkg['price']:,}",
                          "callback_data": f"shop:{key}"}])
        send_message(chat_id,
                     "🛒 *فروشگاه*\n1️⃣ انتخاب\n2️⃣ واریز\n3️⃣ رسید\n4️⃣ رهگیری\n5️⃣ تایید ادمین\n\n👇",
                     {"inline_keyboard": rows}, safe=False)
        return
    if text == "💳 خریدهای من":
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"SELECT id, package_key, coins, status FROM shop_orders WHERE user_id={ph()} ORDER BY created_at DESC LIMIT 10", (uid,))
            rows = c.fetchall()
        finally:
            close(conn)
        if not rows:
            send_message(chat_id, "خریدی نداری.", PRIVATE_KB(uid)); return
        statuses = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
        txt = "💳 *خریدها*\n"
        for r in rows:
            pkg = SHOP_PACKAGES.get(r["package_key"], {"name": r["package_key"]})
            txt += f"• {pkg['name']} — {r['coins']:,} — {statuses.get(r['status'], r['status'])}\n"
        send_message(chat_id, txt, PRIVATE_KB(uid), safe=False)
        return
    if text == "🔙 بازگشت":
        send_message(chat_id, "منوی اصلی:", PRIVATE_KB(uid)); return

    if is_admin(uid) and handle_admin_text(chat_id, uid, text):
        return

    state, data = get_state(uid)
    if state and handle_shop_state(chat_id, uid, first_name, text, msg, state, data):
        return

    # 🆕 خرید چندتایی
    if "\n" in text:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 2:
            handled = 0
            for line in lines:
                if parse_text_command(uid, chat_id, first_name, username, line):
                    handled += 1
            if handled >= 2:
                return

    if parse_text_command(uid, chat_id, first_name, username, text):
        return

    send_message(chat_id, "از منوی پایین استفاده کن 👇", PRIVATE_KB(uid))


def show_admin_panel(chat_id, uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT COUNT(*) c FROM shop_orders WHERE status={ph()}", ("pending",))
        pending = c.fetchone()["c"]
        c.execute("SELECT COUNT(*) c FROM players")
        tp = c.fetchone()["c"]
        c.execute("SELECT SUM(money) s FROM players")
        total_money = c.fetchone()["s"] or 0
        c.execute("SELECT SUM(total_earned) s FROM players")
        total_earned = c.fetchone()["s"] or 0
    finally:
        close(conn)
    send_message(chat_id,
                 f"👑 *پنل ادمین* ({'PostgreSQL' if USE_POSTGRES else 'SQLite'})\n"
                 f"━━━━━━━━━━━━━━━\n"
                 f"📥 سفارشات: {pending}\n"
                 f"👥 بازیکن‌ها: {tp}\n"
                 f"💰 مجموع پول: {format_money(total_money)}\n"
                 f"📈 مجموع درآمد: {format_money(total_earned)}\n\n"
                 f"💡 *دستورات:*\n"
                 f"`ADDMONEY ID مبلغ` — افزودن پول\n"
                 f"`CARD ID مبلغ` — کارت به کارت\n"
                 f"`SUB ID مبلغ` — کم کردن\n"
                 f"`RESET ID` | `RESETALL`\n"
                 f"`ALL متن` | `GIFT مبلغ`\n"
                 f"`کد بساز CODE مبلغ تعداد` | `کد لیست`\n"
                 f"`SEARCH نام` | `ADMINLOG ID` | `UNDO ID`",
                 ADMIN_KB(), safe=False)


def show_pending_orders(chat_id, uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute(f"SELECT * FROM shop_orders WHERE status={ph()} ORDER BY created_at DESC LIMIT 10", ("pending",))
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "📥 سفارشی نیست.", ADMIN_KB()); return
    for r in rows:
        pkg = SHOP_PACKAGES.get(r["package_key"], {"name": r["package_key"]})
        user = get_player(r["user_id"]) or {}
        txt = (f"📥 *سفارش #{r['id']}*\n👤 {user.get('first_name', '?')} (`{r['user_id']}`)\n"
               f"📦 {pkg['name']}\n💰 {format_money(r['price'])}\n🪙 {format_money(r['coins'])}\n"
               f"🔢 `{r['tracking_code'] or 'ندارد'}`")
        ikb = {"inline_keyboard": [
            [{"text": "✅ تایید", "callback_data": f"appr:{r['id']}"},
             {"text": "❌ رد", "callback_data": f"rej:{r['id']}"}]
        ]}
        if r["receipt_file_id"]:
            api("sendPhoto", {"chat_id": chat_id, "photo": r["receipt_file_id"],
                              "caption": txt, "parse_mode": "Markdown",
                              "reply_markup": json.dumps(ikb)})
        else:
            send_message(chat_id, txt, ikb, safe=False)


def handle_admin_text(chat_id, uid, text):
    if not is_admin(uid):
        return False
    if text in ("📥 سفارشات", "📥 خریدهای در انتظار"):
        show_pending_orders(chat_id, uid); return True
    if text == "📊 آمار کل":
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) c FROM players")
            t = c.fetchone()["c"]
            c.execute("SELECT SUM(total_earned) s FROM players")
            earned = c.fetchone()["s"] or 0
            c.execute("SELECT COUNT(*) c FROM duels")
            duels = c.fetchone()["c"]
            c.execute("SELECT COUNT(*) c FROM clans")
            clans = c.fetchone()["c"]
            c.execute("SELECT COUNT(*) c FROM discount_codes")
            codes = c.fetchone()["c"]
        finally:
            close(conn)
        send_message(chat_id,
                     f"📊 *آمار کل*\n👥 {t}\n📈 درآمد: {format_money(earned)}\n"
                     f"⚔️ دوئل: {duels}\n🏰 کلن: {clans}\n🎟 کد: {codes}",
                     ADMIN_KB(), safe=False)
        return True
    if text == "💰 افزودن پول":
        send_message(chat_id, "`ADDMONEY ID مبلغ` (تا ۱۰۰,۰۰۰)", ADMIN_KB(), safe=False); return True
    if text == "💳 کارت به کارت ادمین":
        send_message(chat_id, "`CARD ID مبلغ` (تا ۱۰۰,۰۰۰)", ADMIN_KB(), safe=False); return True
    if text == "🎟 کد تخفیف":
        send_message(chat_id, "`کد بساز CODE مبلغ تعداد` | `کد لیست`", ADMIN_KB(), safe=False); return True
    if text == "🗑 ریست کلی":
        send_message(chat_id, "⚠️ تایید: `RESETALL`", ADMIN_KB(), safe=False); return True
    if text == "🎁 هدیه همگانی":
        send_message(chat_id, "`GIFT مبلغ`", ADMIN_KB(), safe=False); return True
    if text == "📢 پیام همگانی":
        send_message(chat_id, "`ALL متن`", ADMIN_KB(), safe=False); return True
    if text == "🔙 بازگشت":
        send_message(chat_id, "منوی اصلی:", PRIVATE_KB(uid)); return True

    parts = text.split()
    if not parts:
        return False

    if parts[0].upper() == "ADDMONEY" and len(parts) >= 3 and parts[1].isdigit():
        try:
            amt = int(parts[2])
        except Exception:
            return True
        do_admin_add_money(uid, chat_id, int(parts[1]), amt); return True

    if parts[0].upper() == "CARD" and len(parts) >= 3 and parts[1].isdigit():
        try:
            amt = int(parts[2])
        except Exception:
            return True
        do_admin_transfer(uid, chat_id, int(parts[1]), amt); return True

    if parts[0].upper() == "SUB" and len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
        amt = int(parts[2])
        tp = get_player(int(parts[1]))
        if tp and tp["money"] >= amt:
            update_player(int(parts[1]), money=tp["money"] - amt)
            send_message(chat_id, f"✅ از `{parts[1]}` {format_money(amt)} کم شد.", ADMIN_KB(), safe=False)
        return True

    if parts[0].upper() == "UNDO" and len(parts) >= 2 and parts[1].isdigit():
        do_admin_undo(int(parts[1]), uid, chat_id); return True

    if parts[0].upper() == "SEARCH" and len(parts) >= 2:
        q = " ".join(parts[1:])
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"SELECT user_id, first_name, money FROM players WHERE first_name LIKE {ph()} LIMIT 10", (f"%{q}%",))
            rows = c.fetchall()
        finally:
            close(conn)
        if not rows:
            send_message(chat_id, "❌ نیست.", ADMIN_KB()); return True
        txt = "🔍 *نتایج*\n"
        for r in rows:
            txt += f"• {r['first_name']} (`{r['user_id']}`) — {format_money(r['money'])}\n"
        send_message(chat_id, txt, ADMIN_KB(), safe=False); return True

    if parts[0].upper() == "RESET" and len(parts) >= 2 and parts[1].isdigit():
        tid = int(parts[1])
        conn = db()
        try:
            c = conn.cursor()
            for table, col in [("players", "user_id"), ("achievements", "user_id"),
                               ("transactions", "user_id"), ("daily_missions", "user_id"),
                               ("clan_members", "user_id"), ("user_states", "user_id"),
                               ("banks", "user_id"), ("boosters", "user_id"),
                               ("reminders", "user_id"), ("lottery", "user_id"),
                               ("gems_log", "user_id")]:
                try:
                    c.execute(f"DELETE FROM {table} WHERE {col}={ph()}", (tid,))
                except Exception:
                    pass
            try:
                c.execute(f"DELETE FROM duels WHERE challenger_id={ph()} OR opponent_id={ph()}", (tid, tid))
                c.execute(f"DELETE FROM admin_txns WHERE target_id={ph()}", (tid,))
                c.execute(f"DELETE FROM card_transfers WHERE sender_id={ph()} OR receiver_id={ph()}", (tid, tid))
            except Exception:
                pass
            conn.commit()
        finally:
            close(conn)
        send_message(chat_id, f"✅ `{tid}` ریست شد.", ADMIN_KB(), safe=False); return True

    if text.upper() == "RESETALL":
        do_reset_all(uid, chat_id); return True

    if parts[0].upper() == "ALL" and len(text) > 4:
        msg_text = text[4:].strip()
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT user_id FROM players")
            ids = [r["user_id"] for r in c.fetchall()]
        finally:
            close(conn)
        sent = 0
        for x in ids:
            if send_message(x, f"📢 *پیام ادمین:*\n\n{msg_text}").get("ok"):
                sent += 1
            time.sleep(0.05)
        send_message(chat_id, f"✅ به {sent} نفر.", ADMIN_KB()); return True

    if parts[0].upper() == "GIFT" and len(parts) >= 2 and parts[1].isdigit():
        amt = int(parts[1])
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT user_id FROM players")
            ids = [r["user_id"] for r in c.fetchall()]
        finally:
            close(conn)
        cnt = 0
        for x in ids:
            tp = get_player(x)
            if tp:
                update_player(x, money=tp["money"] + amt)
                cnt += 1
            time.sleep(0.05)
        send_message(chat_id, f"✅ به {cnt} نفر.", ADMIN_KB()); return True

    return False


def handle_shop_state(chat_id, uid, first_name, text, msg, state, data):
    if state == "await_receipt":
        photos = msg.get("photo")
        if not photos:
            send_message(chat_id, "❌ عکس رسید بفرست.", PRIVATE_KB(uid)); return True
        file_id = photos[-1].get("file_id") if isinstance(photos, list) else photos.get("file_id")
        pkg = SHOP_PACKAGES.get(data.get("pkg", ""), {})
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"INSERT INTO shop_orders (user_id, package_key, coins, price, receipt_file_id, created_at) VALUES ({ph()},{ph()},{ph()},{ph()},{ph()},{ph()})",
                      (uid, data.get("pkg"), pkg.get("coins", 0), pkg.get("price", 0), file_id, time.time()))
            c.execute(f"SELECT id FROM shop_orders WHERE user_id={ph()} ORDER BY id DESC LIMIT 1", (uid,))
            oid = c.fetchone()["id"]
            conn.commit()
        finally:
            close(conn)
        set_state(uid, "await_tracking", {"order_id": oid})
        send_message(chat_id, "✅ رسید! حالا *شماره رهگیری* رو بفرست:", PRIVATE_KB(uid)); return True
    if state == "await_tracking":
        if not text or text.startswith("/"):
            send_message(chat_id, "❌ شماره رهگیری رو بفرست."); return True
        oid = data.get("order_id")
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"UPDATE shop_orders SET tracking_code={ph()} WHERE id={ph()}", (text.strip(), oid))
            c.execute(f"SELECT * FROM shop_orders WHERE id={ph()}", (oid,))
            order = dict(c.fetchone())
            conn.commit()
        finally:
            close(conn)
        clear_state(uid)
        send_message(chat_id, f"✅ ثبت شد! #{oid}", PRIVATE_KB(uid))
        notify_admins_order(order, uid, first_name)
        return True
    return False


def notify_admins_order(order, uid, first_name):
    pkg = SHOP_PACKAGES.get(order["package_key"], {"name": order["package_key"]})
    txt = (f"📥 *سفارش!*\n🆔 #{order['id']}\n👤 {first_name} (`{uid}`)\n"
           f"📦 {pkg['name']}\n💰 {format_money(order['price'])}\n"
           f"🪙 {format_money(order['coins'])}\n🔢 `{order['tracking_code']}`")
    ikb = {"inline_keyboard": [
        [{"text": "✅ تایید", "callback_data": f"appr:{order['id']}"},
         {"text": "❌ رد", "callback_data": f"rej:{order['id']}"}]
    ]}
    for adm in ADMIN_IDS:
        if order.get("receipt_file_id"):
            api("sendPhoto", {"chat_id": adm, "photo": order["receipt_file_id"],
                              "caption": txt, "parse_mode": "Markdown",
                              "reply_markup": json.dumps(ikb)})
        else:
            send_message(adm, txt, ikb, safe=False)


# ==================== Group Handler ====================
def handle_group(msg, uid, chat_id, first_name, username, text):
    if not is_joined(uid):
        send_join_pm(uid, first_name); return
    if not get_player(uid):
        create_player(uid, first_name, username)
    if text in ("/game", "/play"):
        p = get_player(uid)
        send_message(chat_id,
                     f"🎮 *منوی فلافل*\n💰 {format_money(p['money'])} | ⭐ {p['level']}\n"
                     f"🍽 {count_falafel(p)} فلافل\n\nروی دکمه بزن 👇",
                     GROUP_KB(), safe=False)
        return
    if text.startswith("/"):
        if text == "/version":
            send_message(chat_id, f"📦 `{VERSION}`", safe=False); return
        if text == "/help":
            send_message(chat_id, "📋 `راهنما` رو بزن.", safe=False); return
        return

    if text.startswith("دوئل") or text.startswith("مبارزه"):
        reply = msg.get("reply_to_message")
        if not reply:
            send_message(chat_id, "❌ روی پیام حریف ریپلای کن و بنویس `دوئل ۵۰۰۰`"); return
        op_id = (reply.get("from") or {}).get("id")
        if not op_id:
            send_message(chat_id, "❌ حریف نیست."); return
        nums = re.findall(r'\d+', normalize_numbers(text))
        if not nums:
            send_message(chat_id, "❌ مبلغ رو بنویس."); return
        do_duel(uid, chat_id, op_id, int(nums[0])); return

    if text.startswith("انتقال") or text.startswith("کارت به کارت"):
        reply = msg.get("reply_to_message")
        nums = re.findall(r'\d+', normalize_numbers(text))
        if not nums:
            send_message(chat_id, "❌ مبلغ رو بنویس (مثال: `انتقال ۵۰۰۰`)"); return
        amount = int(nums[0])
        if reply:
            target_id = (reply.get("from") or {}).get("id")
        elif len(nums) >= 2:
            if int(nums[0]) > 99999:
                target_id = int(nums[0]); amount = int(nums[1])
            else:
                amount = int(nums[0]); target_id = int(nums[1])
        else:
            send_message(chat_id, "❌ روی پیام کاربر ریپلای کن یا ID بنویس.")
            return
        if target_id:
            do_transfer(uid, chat_id, target_id, amount, first_name)
        return

    if parse_text_command(uid, chat_id, first_name, username, text):
        return


# ==================== Callback ====================
def handle_callback(cb):
    data = cb.get("data") or ""
    msg = cb.get("message") or {}
    m_chat = (msg.get("chat") or {}).get("id")
    m_id = msg.get("message_id")
    u = cb.get("from") or {}
    uid = u.get("id")
    fn = u.get("first_name", "کاربر")
    un = u.get("username", "")
    if not uid:
        return

    if data == "check_join":
        clear_join_cache(uid)
        if is_joined(uid, use_cache=False):
            try:
                api("deleteMessage", {"chat_id": m_chat, "message_id": m_id})
            except Exception:
                pass
            send_message(uid, "✅ تایید شد!", PRIVATE_KB(uid))
        else:
            answer_callback(cb["id"], "❌ هنوز عضو نشدی!", True)
        return

    if data.startswith("appr:") or data.startswith("rej:"):
        if not is_admin(uid):
            answer_callback(cb["id"], "⛔", True); return
        is_appr = data.startswith("appr:")
        oid = int(data.split(":")[1])
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"SELECT * FROM shop_orders WHERE id={ph()}", (oid,))
            r = c.fetchone()
            if not r:
                answer_callback(cb["id"], "❌", True); return
            order = dict(r)
            if order["status"] != "pending":
                answer_callback(cb["id"], "قبلاً بررسی شد.", True); return
            new_status = "approved" if is_appr else "rejected"
            c.execute(f"UPDATE shop_orders SET status={ph()}, reviewed_by={ph()}, reviewed_at={ph()} WHERE id={ph()}",
                      (new_status, uid, time.time(), oid))
            conn.commit()
        finally:
            close(conn)
        if is_appr:
            tp = get_player(order["user_id"])
            if tp:
                update_player(order["user_id"], money=tp["money"] + order["coins"])
            try:
                send_message(order["user_id"], f"✅ سفارش #{oid} تایید شد!", PRIVATE_KB(order["user_id"]))
            except Exception:
                pass
            answer_callback(cb["id"], "✅ تایید", True)
        else:
            try:
                send_message(order["user_id"], f"❌ سفارش #{oid} رد شد.")
            except Exception:
                pass
            answer_callback(cb["id"], "❌ رد", True)
        try:
            api("deleteMessage", {"chat_id": m_chat, "message_id": m_id})
        except Exception:
            pass
        return

    if data.startswith("g:"):
        if not is_joined(uid):
            send_join_pm(uid, fn)
            answer_callback(cb["id"], "🔒 اول عضو شو", True); return
        if not get_player(uid):
            create_player(uid, fn, un)
        sub = data.split(":")[1]
        if sub == "close":
            try:
                api("deleteMessage", {"chat_id": m_chat, "message_id": m_id})
            except Exception:
                pass
            answer_callback(cb["id"]); return
        if sub == "mission":
            answer_callback(cb["id"]); do_missions(uid, m_chat); return
        if sub == "clan":
            answer_callback(cb["id"]); do_clan_info(uid, m_chat); return
        if sub == "bank":
            answer_callback(cb["id"]); do_bank(uid, m_chat, fn); return
        if sub == "lottery":
            answer_callback(cb["id"]); do_lottery_panel(uid, m_chat); return
        if sub == "casino":
            answer_callback(cb["id"])
            send_message(m_chat, "🎰 `کازینو ۵۰۰۰ شیر` / `خط`", safe=False); return
        if sub == "slot":
            answer_callback(cb["id"])
            send_message(m_chat, "🎰 `اسلات ۵۰۰۰`", safe=False); return
        if sub == "boost":
            answer_callback(cb["id"])
            send_message(m_chat, "⚡ `بوستر بخر` — ۵,۰۰۰", safe=False); return
        if sub in GUIDES:
            answer_callback(cb["id"]); send_message(m_chat, GUIDES[sub], safe=False); return
        answer_callback(cb["id"]); return

    if data.startswith("shop:"):
        if not is_joined(uid):
            send_join_pm(uid, fn)
            answer_callback(cb["id"], "🔒", True); return
        pkg_key = data.split(":")[1]
        pkg = SHOP_PACKAGES.get(pkg_key)
        if not pkg:
            answer_callback(cb["id"], "❌", True); return
        set_state(uid, "await_receipt", {"pkg": pkg_key})
        answer_callback(cb["id"])
        send_message(uid,
                     f"🛒 *{pkg['name']}*\n🪙 {format_money(pkg['coins'])} سکه\n💰 {format_money(pkg['price'])}\n\n"
                     f"💳 `{CARD_NUMBER}`\n{CARD_OWNER}\n\n"
                     f"1️⃣ واریز\n2️⃣ عکس رسید\n3️⃣ رهگیری\n\n📸 رسید:",
                     {"inline_keyboard": [[{"text": "❌ انصراف", "callback_data": "cancel_shop"}]]}, safe=False)
        return

    if data == "cancel_shop":
        clear_state(uid)
        try:
            api("deleteMessage", {"chat_id": m_chat, "message_id": m_id})
        except Exception:
            pass
        answer_callback(cb["id"], "لغو")
        send_message(uid, "لغو شد.", PRIVATE_KB(uid))
        return

    answer_callback(cb["id"])


# ==================== Helpers ====================
def is_message_too_old(msg, max_age=MAX_MESSAGE_AGE):
    msg_date = msg.get("date")
    if not msg_date:
        return False
    try:
        return (time.time() - int(msg_date)) > max_age
    except Exception:
        return False


def skip_old_updates():
    if not SKIP_OLD_UPDATES:
        return None
    try:
        r = api("getUpdates", {"offset": -1, "timeout": 0, "limit": 1}, req_timeout=(10, 15))
        if r.get("ok"):
            updates = r.get("result", [])
            if updates:
                last_id = updates[-1]["update_id"]
                try:
                    api("getUpdates", {"offset": last_id + 1, "timeout": 0, "limit": 1}, req_timeout=(10, 15))
                except Exception:
                    pass
                return last_id + 1
        return None
    except Exception as e:
        log(f"⚠️ skip failed: {e}")
        return None


def handle_message(msg):
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    u = msg.get("from") or {}
    uid = u.get("id")
    fn = u.get("first_name", "کاربر")
    un = u.get("username", "")
    text = (msg.get("text") or "").strip()
    if not chat_id or not uid:
        return
    if is_message_too_old(msg):
        return
    if chat_type == "private":
        handle_private(msg, uid, chat_id, fn, un, text)
    elif chat_type in ("group", "supergroup"):
        handle_group(msg, uid, chat_id, fn, un, text)


def process_update(update):
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback(update["callback_query"])
    except Exception:
        log_err()


def background_tasks():
    try:
        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"SELECT user_id FROM players WHERE (active_customer={ph()} OR customer_expire < {ph()}) AND last_daily > {ph()} LIMIT 5",
                      ("", time.time(), time.time() - 3600))
            candidates = [r["user_id"] for r in c.fetchall()]
        finally:
            close(conn)
        for x in candidates:
            if is_joined(x) and random.random() < 0.15:
                cust = spawn_customer(x)
                if cust:
                    send_message(x, customer_text(cust), safe=False)

        conn = db()
        try:
            c = conn.cursor()
            c.execute(f"SELECT id, chat_id, text FROM reminders WHERE remind_at <= {ph()}", (time.time(),))
            for r in c.fetchall():
                try:
                    send_message(r["chat_id"], f"🔔 *یادآور:*\n{r['text']}")
                except Exception:
                    pass
                c.execute(f"DELETE FROM reminders WHERE id={ph()}", (r["id"],))
            try:
                c.execute(f"UPDATE players SET pet_hunger=pet_hunger-1 WHERE pet_level>0 AND pet_hunger>0")
            except Exception:
                pass
            conn.commit()
        finally:
            close(conn)
        try:
            draw_lottery()
        except Exception:
            pass
    except Exception:
        log_err()


def run():
    init_db()
    print("━" * 55, flush=True)
    print("  بات زیر مجموعه نوین سازان bolight", flush=True)
    print("━" * 55, flush=True)
    print(f"  {SOURCE_NAME}", flush=True)
    print(f"  📦 نسخه: {VERSION}", flush=True)
    print(f"  🗄 دیتابیس: {'PostgreSQL' if USE_POSTGRES else 'SQLite'}", flush=True)
    print(f"  🛠 حالت: {'Debug' if DEBUG else 'Production'}", flush=True)
    print("━" * 55, flush=True)
    log(f"👑 ادمین‌ها: {ADMIN_IDS}")
    log(f"🔒 کانال: {get_forced_channel()}")

    threading.Thread(target=run_web, daemon=True).start()

    offset = None
    try:
        offset = skip_old_updates()
    except Exception as e:
        log(f"⚠️ skip failed: {e}")

    log("✅ ربات با موفقیت اجرا شد. منتظر پیام‌ها...")
    last_bg = 0
    while True:
        try:
            updates = get_updates(offset, timeout=POLLING_TIMEOUT)
            if not updates.get("ok"):
                time.sleep(2); continue
            for x in updates.get("result", []):
                offset = x["update_id"] + 1
                process_update(x)
            if time.time() - last_bg > 60:
                background_tasks()
                last_bg = time.time()
        except KeyboardInterrupt:
            log("🛑 خروج")
            sys.exit(0)
        except Exception:
            log_err()
            time.sleep(2)


if __name__ == "__main__":
    run()
