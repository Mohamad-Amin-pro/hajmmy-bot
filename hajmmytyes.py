# -*- coding: utf-8 -*-
"""
🍔 ربات فلافل فروشی - نسخه Ultimate
نسخه: 0.1.0
"""

import requests, sqlite3, time, random, json, sys, traceback, re
import threading, os
from datetime import datetime, date, timedelta
from flask import Flask

# ==================== منطقه زمانی ====================
try:
    import zoneinfo
    TEHRAN_TZ = zoneinfo.ZoneInfo("Asia/Tehran")
except Exception:
    TEHRAN_TZ = None


def now_local():
    if TEHRAN_TZ:
        return datetime.now(TEHRAN_TZ)
    return datetime.now()


def today_local():
    return now_local().date()


def is_weekend():
    return now_local().weekday() in (3, 4)


# ==================== Flask برای Render ====================
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


# ==================== نسخه ====================
VERSION = "0.1.0"
SOURCE_NAME = "🍔 ربات فلافل فروشی"

# ==================== تنظیمات ====================
TOKEN = ""
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}/"
DB_PATH = "falafel_game.db"
DEBUG = True

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60
POLLING_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 3

ADMIN_IDS = [
    1355544502,
    201919317,
]

FORCED_CHANNEL = "@falaflihajmmy"
FORCED_CHANNEL_TITLE = "کانال ما"

FORCED_CHANNEL_NORM = None
_join_cache = {}
JOIN_CACHE_TTL = 300
_join_pm_sent = {}
JOIN_PM_COOLDOWN = 300

CARD_NUMBER = "6037-XXXX-XXXX-XXXX"
CARD_OWNER = "نام صاحب کارت"

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
ADMIN_MONEY_LIMIT = 10000

TRANSFER_MIN = 500
TRANSFER_MAX = 50000
TRANSFER_COMMISSION = 0.02

WEEKEND_MULTIPLIER = 2.0
BOOSTER_PRICE = 5000
BOOSTER_MULTIPLIER = 2.0
BOOSTER_DURATION = 3600

LOTTERY_PRICE = 1000
LOTTERY_DAYS = 7

PET_FEED_PRICE = 500
PET_MAX_LEVEL = 10

SKIP_OLD_UPDATES = False

NUMERIC_FIELDS = [
    "money", "flour", "chickpeas", "oil", "cheese", "spice",
    "falafel_simple", "falafel_special", "falafel_sandwich",
    "falafel_cheese", "falafel_spicy", "falafel_deluxe",
    "level", "exp", "oven_level", "mixer_level", "counter_level",
    "total_sold", "total_earned", "total_cooked", "daily_streak",
    "gems", "skill_cook", "skill_trade", "skill_luck", "skill_charm",
    "pet_level", "pet_exp", "pet_hunger",
]

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_numbers(text):
    if not text:
        return text
    text = text.translate(PERSIAN_DIGITS)
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return text


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
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(BASE_URL + method, data=params, timeout=req_timeout)
            return r.json()
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout: {e}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except requests.exceptions.ConnectionError as e:
            last_error = f"ConnectionError: {e}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            log(f"⚠️ API error [{method}]: {e}")
            return {"ok": False}
    log(f"❌ API failed [{method}]: {last_error}")
    return {"ok": False}


def get_updates(offset=None, timeout=POLLING_TIMEOUT):
    p = {"timeout": timeout}
    if offset:
        p["offset"] = offset
    req_timeout = (CONNECT_TIMEOUT, timeout + READ_TIMEOUT)
    return api("getUpdates", p, req_timeout=req_timeout)


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


# ==================== کیبوردها ====================
def kb(rows):
    return {"keyboard": [[{"text": t} for t in row] for row in rows],
            "resize_keyboard": True}


def PRIVATE_KB(uid=None):
    rows = [
        ["🛒 فروشگاه", "🏦 بانک"],
        ["🎰 کازینو", "🎫 لاتاری"],
        ["🎓 مهارت‌ها", "🐔 پت"],
        ["⚡ بوستر", "🔔 یادآور"],
        ["💳 کارت به کارت", "💰 دونیت"],
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
    return kb([
        ["🏦 موجودی", "📊 راهنما"],
        ["🔙 بازگشت"]
    ])


def GROUP_KB():
    return {"inline_keyboard": [
        [{"text": "🛒 خرید", "callback_data": "g:buy"}, {"text": "🍳 آشپزی", "callback_data": "g:cook"}],
        [{"text": "💰 فروش", "callback_data": "g:sell"}, {"text": "🎁 جایزه", "callback_data": "g:daily"}],
        [{"text": "🎰 گردونه", "callback_data": "g:spin"}, {"text": "⚙️ آپگرید", "callback_data": "g:up"}],
        [{"text": "🏰 کلن", "callback_data": "g:clan"}, {"text": "⚔️ دوئل", "callback_data": "g:duel"}],
        [{"text": "🎯 ماموریت", "callback_data": "g:mission"}, {"text": "🏦 بانک", "callback_data": "g:bank"}],
        [{"text": "🎰 کازینو", "callback_data": "g:casino"}, {"text": "🎫 لاتاری", "callback_data": "g:lottery"}],
        [{"text": "👤 پروفایل", "callback_data": "g:me"}, {"text": "🏆 رتبه", "callback_data": "g:top"}],
        [{"text": "❌ بستن", "callback_data": "g:close"}],
    ]}


GUIDES = {
    "buy": "🛒 *خرید مواد اولیه*\n━━━━━━━━━━━━━━━\n\n`خرید آرد ۵`\n`خرید نخود ۳`\n`خرید روغن ۲`\n`خرید پنیر ۳`\n`خرید ادویه ۳`\n\n💡 عدد آخر تعداد هست.",
    "cook": "🍳 *آشپزی*\n━━━━━━━━━━━━━━━\n\n`آشپزی ساده` 🟡\n`آشپزی حرفه‌ای` 🟠\n`آشپزی ساندویچ` 🥙\n`آشپزی پنیری` 🧀\n`آشپزی تند` 🌶\n`آشپزی دلوکس` 👑",
    "sell": "💰 *فروش*\n━━━━━━━━━━━━━━━\n\n`فروش همه`\n`فروش ساده` | `فروش مخصوص`\n`فروش ساندویچ` | `فروش پنیری`\n`فروش تند` | `فروش دلوکس`",
    "daily": "🎁 *جایزه روزانه*\n━━━━━━━━━━━━━━━\n\n`جایزه روزانه`\n\n💡 هر ۲۴ ساعت!",
    "spin": "🎰 *گردونه شانس*\n━━━━━━━━━━━━━━━\n\n`گردونه شانس`\n\n💡 یه بار در روز!",
    "up": "⚙️ *آپگرید*\n━━━━━━━━━━━━━━━\n\n`آپگرید تنور` 🔥\n`آپگرید مخلوط‌کن` 🥣\n`آپگرید پیشخوان` 🏪",
    "me": "👤 *پروفایل*\n━━━━━━━━━━━━━━━\n\n`پروفایل`",
    "top": "🏆 *رتبه‌بندی*\n━━━━━━━━━━━━━━━\n\n`رتبه`",
    "cust": "🔔 *مشتری*\n━━━━━━━━━━━━━━━\n\n`مشتری` | `تحویل بده`",
    "clan": "🏰 *کلن*\n━━━━━━━━━━━━━━━\n\n`کلن بساز [اسم]`\n`کلن عضو شو [اسم]`\n`کلن من`\n`کلن لیست`\n`کلن اهدا ۵۰۰۰`\n`کلن خروج`",
    "duel": "⚔️ *دوئل*\n━━━━━━━━━━━━━━━\n\nروی پیام حریف ریپلای کن:\n`دوئل ۵۰۰۰`",
    "mission": "🎯 *ماموریت*\n━━━━━━━━━━━━━━━\n\n`ماموریت`",
    "bank": "🏦 *بانک*\n━━━━━━━━━━━━━━━\n\n`بانک` — پنل\n`بانک واریز ۵۰۰۰`\n`بانک برداشت ۵۰۰۰`\n`بانک سرمایه ۵۰۰۰`\n`بانک جمع`\n\n📊 سود: *۲۰٪ روزانه*",
    "casino": "🎰 *کازینو*\n━━━━━━━━━━━━━━━\n\n`کازینو ۵۰۰۰ شیر`\n`کازینو ۵۰۰۰ خط`",
    "boost": "⚡ *بوستر*\n━━━━━━━━━━━━━━━\n\n`بوستر بخر` — ۵,۰۰۰ تومان\n\n💡 درآمد ۲ برابر برای ۱ ساعت!",
    "lottery": "🎫 *لاتاری*\n━━━━━━━━━━━━━━━\n\n`لاتاری` — پنل\n`لاتاری بخر` — ۱,۰۰۰ تومان\n`لاتاری شانس` — شانس‌های من\n\n💡 هر هفته یه برنده!",
    "skills": "🎓 *مهارت‌ها*\n━━━━━━━━━━━━━━━\n\n`مهارت‌ها` — پنل\n`مهارت بخر [نام]`\n\n💡 با الماس ارتقا می‌دن!",
    "pet": "🐔 *حیوان خانگی*\n━━━━━━━━━━━━━━━\n\n`پت` — پنل\n`پت غذا بده` — ۵۰۰ تومان\n`پت وضعیت`\n\n💡 هر لول درآمد بیشتر!",
}


# ==================== DB ====================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def close(conn):
    try:
        conn.close()
    except Exception:
        pass


def init_db():
    conn = db()
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
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
            pet_level INTEGER DEFAULT 0, pet_exp INTEGER DEFAULT 0,
            pet_hunger INTEGER DEFAULT 100,
            total_sold INTEGER DEFAULT 0, total_earned INTEGER DEFAULT 0,
            total_cooked INTEGER DEFAULT 0, last_daily REAL DEFAULT 0,
            daily_streak INTEGER DEFAULT 0, last_spin REAL DEFAULT 0,
            active_customer TEXT DEFAULT '', customer_expire REAL DEFAULT 0,
            customer_order TEXT DEFAULT '', customer_reward INTEGER DEFAULT 0,
            created_at REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS achievements (
            user_id INTEGER, achievement_id TEXT, unlocked_at REAL,
            PRIMARY KEY (user_id, achievement_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT,
            amount INTEGER, description TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS shop_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, package_key TEXT, coins INTEGER, price INTEGER,
            receipt_file_id TEXT DEFAULT '', tracking_code TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', created_at REAL,
            reviewed_by INTEGER DEFAULT 0, reviewed_at REAL, note TEXT DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY, state TEXT, data TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS clans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE, owner_id INTEGER, treasury INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0, created_at REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS clan_members (
            clan_id INTEGER, user_id INTEGER PRIMARY KEY, joined_at REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS duels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id INTEGER, opponent_id INTEGER, amount INTEGER,
            winner_id INTEGER, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_missions (
            user_id INTEGER, day TEXT, missions TEXT, completed TEXT,
            PRIMARY KEY (user_id, day))""")
        c.execute("""CREATE TABLE IF NOT EXISTS admin_txns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER, admin_id INTEGER, amount INTEGER,
            note TEXT, reversed INTEGER DEFAULT 0, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS banks (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            invested INTEGER DEFAULT 0,
            last_collect REAL DEFAULT 0,
            total_profit INTEGER DEFAULT 0,
            last_invest REAL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS casino_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount INTEGER, result TEXT,
            bet_type TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS card_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER, receiver_id INTEGER, amount INTEGER,
            commission INTEGER, note TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS discount_codes (
            code TEXT PRIMARY KEY, amount INTEGER,
            max_uses INTEGER DEFAULT 1, uses INTEGER DEFAULT 0,
            created_by INTEGER, created_at REAL, used_by TEXT DEFAULT '[]')""")
        c.execute("""CREATE TABLE IF NOT EXISTS boosters (
            user_id INTEGER PRIMARY KEY, multiplier REAL DEFAULT 2.0,
            expires_at REAL DEFAULT 0, bought_at REAL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, chat_id INTEGER, text TEXT,
            remind_at REAL, created_at REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS lottery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, tickets INTEGER DEFAULT 0,
            week TEXT, joined_at REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS lottery_winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week TEXT, user_id INTEGER, tickets INTEGER,
            prize INTEGER, paid INTEGER DEFAULT 0, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_events (
            day TEXT PRIMARY KEY, event_type TEXT, description TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS gems_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount INTEGER, reason TEXT, ts REAL)""")
        conn.commit()

        # مهاجرت: اضافه کردن ستون‌های جدید اگه نبود
        migrations = [
            ("players", "gems", "INTEGER DEFAULT 0"),
            ("players", "skill_cook", "INTEGER DEFAULT 0"),
            ("players", "skill_trade", "INTEGER DEFAULT 0"),
            ("players", "skill_luck", "INTEGER DEFAULT 0"),
            ("players", "skill_charm", "INTEGER DEFAULT 0"),
            ("players", "pet_level", "INTEGER DEFAULT 0"),
            ("players", "pet_exp", "INTEGER DEFAULT 0"),
            ("players", "pet_hunger", "INTEGER DEFAULT 100"),
            ("banks", "last_invest", "REAL DEFAULT 0"),
        ]
        for table, col, dtype in migrations:
            try:
                c.execute(f"SELECT {col} FROM {table} LIMIT 1")
            except Exception:
                try:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
                    conn.commit()
                    log(f"✅ ستون {col} به {table} اضافه شد")
                except Exception as e:
                    log(f"⚠️ migrate error {table}.{col}: {e}")

        # تبدیل NULL به 0
        try:
            for field in NUMERIC_FIELDS:
                try:
                    c.execute(f"UPDATE players SET {field}=0 WHERE {field} IS NULL")
                except Exception:
                    pass
            for field in ["balance", "invested", "last_collect", "total_profit", "last_invest"]:
                try:
                    c.execute(f"UPDATE banks SET {field}=0 WHERE {field} IS NULL")
                except Exception:
                    pass
            conn.commit()
        except Exception as e:
            log(f"⚠️ migrate NULL: {e}")

    finally:
        close(conn)


# ==================== بازی ====================
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
    "cook":   {"name": "🍳 آشپزی",      "desc": "هر لول ۳٪ شانس پخت دوتایی", "max": 5, "cost": 5},
    "trade":  {"name": "💼 تجارت",      "desc": "هر لول ۳٪ تخفیف مواد", "max": 5, "cost": 5},
    "luck":   {"name": "🍀 شانس",       "desc": "هر لول ۳٪ شانس برد کازینو", "max": 5, "cost": 8},
    "charm":  {"name": "😊 جذابیت",      "desc": "هر لول ۳٪ پاداش بیشتر از مشتری", "max": 5, "cost": 10},
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
}

CUSTOMER_TYPES = [
    {"name": "عادی",     "emoji": "👤", "mult": 1.0, "patience": 15},
    {"name": "خوش‌شانس", "emoji": "😊", "mult": 1.5, "patience": 20},
    {"name": "عجول",     "emoji": "🏃", "mult": 1.8, "patience": 5},
    {"name": "VIP",      "emoji": "🎩", "mult": 2.5, "patience": 10},
    {"name": "تورگرد",   "emoji": "🧑‍🦱", "mult": 1.3, "patience": 25},
]

BOX_PRIZES = [
    ("💰 پول کم", "money", 500, 30),
    ("💰 پول متوسط", "money", 2000, 25),
    ("💰 پول زیاد", "money", 8000, 10),
    ("💰 جکپات", "money", 25000, 2),
    ("🌾 آرد x5", "flour", 5, 10),
    ("🫘 نخود x5", "chickpeas", 5, 10),
    ("🛢 روغن x5", "oil", 5, 10),
    ("🧀 پنیر x3", "cheese", 3, 5),
    ("🌶 ادویه x3", "spice", 3, 5),
    ("😢 خالی", "none", 0, 3),
]

DAILY_EVENTS = [
    ("double_money", "💰 *امروز روز پول دوبرابر!*\nهمه فروش‌ها ۱.۵ برابر"),
    ("cheap_ingredients", "🛒 *امروز مواد ارزونن!*\n۲۵٪ تخفیف روی همه مواد"),
    ("lucky_casino", "🎰 *امروز شانس کازینو بالاست!*\nشانس بردت بیشتره"),
    ("cook_bonus", "🍳 *امروز روز آشپزها!*\n۲ برابر تجربه می‌گیری"),
    ("normal", "🌟 *امروز روز عادیه*\nیه روز معمولی!"),
]


# ==================== Player helpers ====================
def get_player(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        r = c.fetchone()
        if not r:
            return None
        d = dict(r)
        for k in NUMERIC_FIELDS:
            if d.get(k) is None:
                d[k] = 0
        for k in ["last_daily", "last_spin", "customer_expire"]:
            if d.get(k) is None:
                d[k] = 0
        if d.get("active_customer") is None:
            d["active_customer"] = ""
        if d.get("customer_order") is None:
            d["customer_order"] = ""
        return d
    finally:
        close(conn)


def create_player(uid, fn="کاربر", un=""):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO players (user_id, first_name, username, created_at) VALUES (?,?,?,?)",
                  (uid, fn, un, time.time()))
        conn.commit()
    finally:
        close(conn)


def update_player(uid, **kw):
    if not kw:
        return
    conn = db()
    try:
        c = conn.cursor()
        fields = ", ".join([f"{k}=?" for k in kw.keys()])
        vals = list(kw.values()) + [uid]
        c.execute(f"UPDATE players SET {fields} WHERE user_id=?", vals)
        conn.commit()
    finally:
        close(conn)


def log_txn(uid, type_, amount, desc):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, description, ts) VALUES (?,?,?,?,?)",
                  (uid, type_, amount, desc, time.time()))
        conn.commit()
    finally:
        close(conn)


def add_gems(uid, amount, reason=""):
    p = get_player(uid)
    if not p:
        return
    new_gems = max(0, (p.get("gems", 0) or 0) + amount)
    update_player(uid, gems=new_gems)
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO gems_log (user_id, amount, reason, ts) VALUES (?,?,?,?)",
                  (uid, amount, reason, time.time()))
        conn.commit()
    finally:
        close(conn)


def add_exp(uid, amount):
    p = get_player(uid)
    if not p:
        return None
    # 🆕 مهارت آشپزی روی exp تأثیر داره
    cook_skill = p.get("skill_cook", 0) or 0
    if cook_skill > 0:
        amount = int(amount * (1 + cook_skill * 0.03))
    new_exp = p["exp"] + amount
    new_level = p["level"]
    while new_exp >= 100:
        new_exp -= 100
        new_level += 1
    update_player(uid, exp=new_exp, level=new_level)
    if new_level > p["level"]:
        # 🆕 هر لول ۱ الماس جایزه
        add_gems(uid, 1, f"سطح {new_level}")
        return new_level
    return None


def ing_price(item, mixer, player=None):
    if mixer is None:
        mixer = 0
    base = INGREDIENTS[item]["base_price"]
    discount = min(mixer * 0.03, 0.15)
    # 🆕 مهارت تجارت
    if player:
        trade_skill = player.get("skill_trade", 0) or 0
        discount += trade_skill * 0.03
    # 🆕 رویداد روزانه
    if get_today_event() == "cheap_ingredients":
        discount += 0.25
    return max(1, int(base * (1 - min(discount, 0.5))))


def sell_price(key, counter, player=None):
    if counter is None:
        counter = 0
    base = RECIPES[key]["base_price"]
    bonus = counter * 0.05
    # 🆕 مهارت جذابیت
    if player:
        charm = player.get("skill_charm", 0) or 0
        bonus += charm * 0.03
    # 🆕 رویداد روزانه
    if get_today_event() == "double_money":
        bonus += 0.5
    # 🆕 پت
    if player:
        pet_level = player.get("pet_level", 0) or 0
        bonus += pet_level * 0.02
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
        c.execute("SELECT multiplier, expires_at FROM boosters WHERE user_id=?", (uid,))
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


# ==================== رویداد روزانه ====================
def get_today_event():
    today = today_local().isoformat()
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT event_type FROM daily_events WHERE day=?", (today,))
        r = c.fetchone()
        if r:
            return r["event_type"]
        # انتخاب رویداد رندوم برای امروز
        event = random.choices(DAILY_EVENTS, weights=[15, 15, 15, 15, 40])[0]
        c.execute("INSERT OR REPLACE INTO daily_events (day, event_type, description) VALUES (?,?,?)",
                  (today, event[0], event[1]))
        conn.commit()
        return event[0]
    finally:
        close(conn)


def get_today_event_desc():
    event = get_today_event()
    for e in DAILY_EVENTS:
        if e[0] == event:
            return e[1]
    return ""


# ==================== بانک ====================
def get_bank(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM banks WHERE user_id=?", (uid,))
        r = c.fetchone()
        if r:
            d = dict(r)
            for k in ["balance", "invested", "total_profit", "last_collect", "last_invest"]:
                if d.get(k) is None:
                    d[k] = 0
            return d
        c.execute("INSERT OR IGNORE INTO banks (user_id) VALUES (?)", (uid,))
        conn.commit()
        return {"user_id": uid, "balance": 0, "invested": 0,
                "last_collect": 0, "total_profit": 0, "last_invest": 0}
    finally:
        close(conn)


def update_bank(uid, **kw):
    if not kw:
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO banks (user_id) VALUES (?)", (uid,))
        fields = ", ".join([f"{k}=?" for k in kw.keys()])
        vals = list(kw.values()) + [uid]
        c.execute(f"UPDATE banks SET {fields} WHERE user_id=?", vals)
        conn.commit()
    finally:
        close(conn)


def collect_bank_profit(uid):
    b = get_bank(uid)
    if b["invested"] <= 0:
        return 0
    now = time.time()
    if b["last_collect"] and b["last_collect"] > 0:
        reference = b["last_collect"]
    elif b["last_invest"] and b["last_invest"] > 0:
        reference = b["last_invest"]
    else:
        reference = now
    elapsed = now - reference
    if elapsed < 86400:
        return 0
    days = int(elapsed // 86400)
    profit = int(b["invested"] * BANK_DAILY_PROFIT * days)
    new_balance = min(b["balance"] + profit, BANK_MAX_BALANCE)
    new_total = b["total_profit"] + profit
    new_collect = reference + days * 86400
    update_bank(uid, balance=new_balance, last_collect=new_collect, total_profit=new_total)
    return profit


def do_bank(uid, chat_id, first_name):
    profit = collect_bank_profit(uid)
    b = get_bank(uid)
    text = (
        f"🏦 *بانک فلافل*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 {first_name}\n\n"
        f"💰 موجودی: {format_money(b['balance'])} تومان\n"
        f"📈 سرمایه‌گذاری: {format_money(b['invested'])} تومان\n"
        f"💵 سود کل: {format_money(b['total_profit'])} تومان\n\n"
    )
    if profit > 0:
        text += f"🎉 *سود جدید:* +{format_money(profit)} تومان\n\n"
    text += (
        f"📊 *سود روزانه:* ۲۰٪\n\n"
        f"💡 *دستورات:*\n"
        f"`بانک واریز ۵۰۰۰`\n"
        f"`بانک برداشت ۵۰۰۰`\n"
        f"`بانک سرمایه ۵۰۰۰`\n"
        f"`بانک پایان ۵۰۰۰`\n"
        f"`بانک جمع`"
    )
    send_message(chat_id, text, BANK_KB(), safe=False)


def do_bank_deposit(uid, chat_id, amount):
    p = get_player(uid)
    if amount <= 0:
        send_message(chat_id, "❌ مبلغ نامعتبر.")
        return
    if p["money"] < amount:
        send_message(chat_id, f"❌ پول کافی نداری!\nداری: {format_money(p['money'])}")
        return
    b = get_bank(uid)
    if b["balance"] + amount > BANK_MAX_BALANCE:
        send_message(chat_id, f"❌ سقف حساب {format_money(BANK_MAX_BALANCE)} تومانه.")
        return
    update_player(uid, money=p["money"] - amount)
    update_bank(uid, balance=b["balance"] + amount)
    log_txn(uid, "bank_deposit", -amount, "واریز به بانک")
    send_message(chat_id, f"✅ {format_money(amount)} تومان واریز شد.\n💰 حساب بانک: {format_money(b['balance'] + amount)}")


def do_bank_withdraw(uid, chat_id, amount):
    b = get_bank(uid)
    if amount <= 0:
        send_message(chat_id, "❌ مبلغ نامعتبر.")
        return
    if b["balance"] < amount:
        send_message(chat_id, f"❌ حساب بانک کافی نیست!\nداری: {format_money(b['balance'])}")
        return
    p = get_player(uid)
    update_player(uid, money=p["money"] + amount)
    update_bank(uid, balance=b["balance"] - amount)
    log_txn(uid, "bank_withdraw", amount, "برداشت از بانک")
    send_message(chat_id, f"✅ {format_money(amount)} تومان برداشت شد.\n💰 جیب: {format_money(p['money'] + amount)}")


def do_bank_invest(uid, chat_id, amount):
    p = get_player(uid)
    if amount < BANK_MIN_INVEST:
        send_message(chat_id, f"❌ حداقل سرمایه‌گذاری {format_money(BANK_MIN_INVEST)} تومانه.")
        return
    if p["money"] < amount:
        send_message(chat_id, f"❌ پول کافی نداری!\nداری: {format_money(p['money'])}")
        return
    collect_bank_profit(uid)
    b = get_bank(uid)
    now = time.time()
    update_player(uid, money=p["money"] - amount)
    new_last_collect = b["last_collect"] if b["last_collect"] > 0 else now
    update_bank(uid, invested=b["invested"] + amount,
                last_invest=now, last_collect=new_last_collect)
    log_txn(uid, "bank_invest", -amount, "سرمایه‌گذاری در بانک")
    send_message(chat_id,
                 f"📈 {format_money(amount)} تومان سرمایه‌گذاری شد!\n"
                 f"💰 کل سرمایه: {format_money(b['invested'] + amount)}\n"
                 f"📊 سود روزانه: ۲۰٪\n"
                 f"⏰ هر ۲۴ ساعت سود بگیر: `بانک جمع`")


def do_bank_end_invest(uid, chat_id, amount):
    b = get_bank(uid)
    if amount <= 0:
        send_message(chat_id, "❌ مبلغ نامعتبر.")
        return
    if b["invested"] < amount:
        send_message(chat_id, f"❌ سرمایه کافی نداری!\nسرمایه: {format_money(b['invested'])}")
        return
    collect_bank_profit(uid)
    b = get_bank(uid)
    update_bank(uid, invested=b["invested"] - amount, balance=b["balance"] + amount)
    send_message(chat_id,
                 f"✅ {format_money(amount)} تومان از سرمایه به حساب بانک برگشت.\n"
                 f"📈 سرمایه باقی: {format_money(b['invested'] - amount)}")


def do_bank_collect(uid, chat_id):
    profit = collect_bank_profit(uid)
    if profit > 0:
        send_message(chat_id, f"🎉 *سود جمع شد!*\n💰 +{format_money(profit)} تومان")
    else:
        b = get_bank(uid)
        if b["invested"] <= 0:
            send_message(chat_id, "❌ سرمایه‌ای نداری!\nاول: `بانک سرمایه ۵۰۰۰`")
        else:
            ref = b["last_collect"] if b["last_collect"] > 0 else b["last_invest"]
            if ref <= 0:
                ref = time.time()
            left = 86400 - (time.time() - ref)
            if left < 0:
                left = 0
            h = int(left // 3600)
            m = int((left % 3600) // 60)
            send_message(chat_id, f"⏰ هنوز ۲۴ ساعت نگذشته!\nبعدی: {h}س {m}د")


# ==================== کازینو ====================
def do_casino(uid, chat_id, amount, bet_type):
    if amount < 500:
        send_message(chat_id, "❌ حداقل شرط ۵۰۰ تومانه.")
        return
    if amount > 100000:
        send_message(chat_id, "❌ حداکثر شرط ۱۰۰,۰۰۰ تومانه.")
        return
    p = get_player(uid)
    if p["money"] < amount:
        send_message(chat_id, f"❌ پول کافی نداری!\nداری: {format_money(p['money'])}")
        return

    # 🆕 مهارت شانس + رویداد روزانه
    luck = p.get("skill_luck", 0) or 0
    win_chance = 0.5 + luck * 0.03
    if get_today_event() == "lucky_casino":
        win_chance += 0.15
    win_chance = min(win_chance, 0.85)

    result = random.choice(["شیر", "خط"])
    correct = (result == bet_type)
    # اگه شانس بالا داشت، می‌تونه برنده بشه حتی اگه حروف عوض شه
    if not correct and random.random() < (win_chance - 0.5) * 2:
        correct = True
        result = bet_type

    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO casino_log (user_id, amount, result, bet_type, ts) VALUES (?,?,?,?,?)",
                  (uid, amount, result, bet_type, time.time()))
        conn.commit()
    finally:
        close(conn)

    if correct:
        update_player(uid, money=p["money"] + amount)
        log_txn(uid, "casino_win", amount, "برد کازینو")
        send_message(chat_id,
                     f"🎰 *کازینو*\n━━━━━━━━━━━━━━━\n"
                     f"💰 شرط: {format_money(amount)} — {bet_type}\n"
                     f"🎲 نتیجه: *{result}*\n\n"
                     f"🎉 *بردی!*\n💰 +{format_money(amount)} سود\n"
                     f"💵 جیب: {format_money(p['money'] + amount)}", safe=False)
    else:
        update_player(uid, money=p["money"] - amount)
        log_txn(uid, "casino_lose", -amount, "باخت کازینو")
        send_message(chat_id,
                     f"🎰 *کازینو*\n━━━━━━━━━━━━━━━\n"
                     f"💰 شرط: {format_money(amount)} — {bet_type}\n"
                     f"🎲 نتیجه: *{result}*\n\n"
                     f"😢 *باختی!*\n💵 جیب: {format_money(p['money'] - amount)}", safe=False)


# ==================== جعبه شانس ====================
def do_mystery_box(uid, chat_id):
    p = get_player(uid)
    if p["money"] < BOX_PRICE:
        send_message(chat_id, f"❌ پول کافی نداری!\nقیمت جعبه: {format_money(BOX_PRICE)}")
        return
    weights = [b[3] for b in BOX_PRIZES]
    prize = random.choices(BOX_PRIZES, weights=weights)[0]
    name, kind, amount, _ = prize
    update_player(uid, money=p["money"] - BOX_PRICE)
    msg = f"🎁 *جعبه شانس*\n━━━━━━━━━━━━━━━\n💰 هزینه: {format_money(BOX_PRICE)}\n\n"
    if kind == "money":
        np = get_player(uid)
        update_player(uid, money=np["money"] + amount)
        log_txn(uid, "box_win", amount, "جایزه جعبه")
        msg += f"🎉 {name}\n💰 +{format_money(amount)} تومان"
    elif kind == "none":
        msg += "😢 خالی بود! دفعه بعد شانست رو امتحان کن."
    else:
        np = get_player(uid)
        update_player(uid, **{kind: (np.get(kind, 0) or 0) + amount})
        msg += f"🎉 {name}\n{INGREDIENTS[kind]['emoji']} +{amount} {INGREDIENTS[kind]['name']}"
    send_message(chat_id, msg, safe=False)


# ==================== بوستر ====================
def do_booster(uid, chat_id):
    p = get_player(uid)
    if p["money"] < BOOSTER_PRICE:
        send_message(chat_id, f"❌ پول کافی نداری!\nقیمت: {format_money(BOOSTER_PRICE)}")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT expires_at FROM boosters WHERE user_id=?", (uid,))
        r = c.fetchone()
        if r and r["expires_at"] and time.time() < r["expires_at"]:
            left = int((r["expires_at"] - time.time()) // 60)
            send_message(chat_id, f"⚡ بوستر فعالت {left} دقیقه دیگه تموم می‌شه!")
            return
        new_expires = time.time() + BOOSTER_DURATION
        c.execute("INSERT OR REPLACE INTO boosters (user_id, multiplier, expires_at, bought_at) VALUES (?,?,?,?)",
                  (uid, BOOSTER_MULTIPLIER, new_expires, time.time()))
        conn.commit()
    finally:
        close(conn)
    update_player(uid, money=p["money"] - BOOSTER_PRICE)
    log_txn(uid, "booster", -BOOSTER_PRICE, "خرید بوستر")
    check_ach(uid, chat_id)
    send_message(chat_id,
                 f"⚡ *بوستر فعال شد!*\n━━━━━━━━━━━━━━━\n"
                 f"💰 هزینه: {format_money(BOOSTER_PRICE)}\n"
                 f"🎁 ضریب: {BOOSTER_MULTIPLIER}x\n"
                 f"⏰ زمان: ۱ ساعت\n\n"
                 f"💡 الان هر فروش ۲ برابر درآمد داره!")


def booster_status(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT expires_at, multiplier FROM boosters WHERE user_id=?", (uid,))
        r = c.fetchone()
        if r and r["expires_at"] and time.time() < r["expires_at"]:
            left = int((r["expires_at"] - time.time()) // 60)
            return f"⚡ بوستر فعال: {left} دقیقه ({r['multiplier']}x)"
        return "⚡ بوستری فعال نیست"
    finally:
        close(conn)


# ==================== یادآور ====================
def do_reminder_set(uid, chat_id, text_body, seconds):
    if not text_body.strip():
        send_message(chat_id, "مثال: `یادآور ۱۰m جلسه`", safe=False)
        return
    if seconds < 60:
        send_message(chat_id, "❌ حداقل زمان ۱ دقیقه.")
        return
    if seconds > 86400:
        send_message(chat_id, "❌ حداکثر زمان ۲۴ ساعت.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO reminders (user_id, chat_id, text, remind_at, created_at) VALUES (?,?,?,?,?)",
                  (uid, chat_id, text_body, time.time() + seconds, time.time()))
        conn.commit()
    finally:
        close(conn)
    mins = seconds // 60
    send_message(chat_id, f"🔔 یادآور ثبت شد!\n⏰ بعد از {mins} دقیقه بهت پیام می‌دم.")


def do_reminder_list(uid, chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT id, text, remind_at FROM reminders WHERE user_id=? ORDER BY remind_at ASC LIMIT 10", (uid,))
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "🔕 هیچ یادآوری نداری.")
        return
    txt = "🔔 *یادآورهای من*\n━━━━━━━━━━━━━━━\n"
    for r in rows:
        left = int((r["remind_at"] - time.time()) // 60)
        txt += f"• {r['text']} (بعد از {left} دقیقه)\n"
    send_message(chat_id, txt, safe=False)


# ==================== لاتاری ====================
def get_week_key():
    """کلید هفته (شنبه)."""
    today = today_local()
    days_since_sat = (today.weekday() - 5) % 7
    week_start = today - timedelta(days=days_since_sat)
    return week_start.isoformat()


def get_lottery_tickets(uid):
    week = get_week_key()
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT tickets FROM lottery WHERE user_id=? AND week=?", (uid, week))
        r = c.fetchone()
        return r["tickets"] if r else 0
    finally:
        close(conn)


def do_lottery_buy(uid, chat_id):
    p = get_player(uid)
    if p["money"] < LOTTERY_PRICE:
        send_message(chat_id, f"❌ پول کافی نداری!\nقیمت بلیط: {format_money(LOTTERY_PRICE)}")
        return
    week = get_week_key()
    update_player(uid, money=p["money"] - LOTTERY_PRICE)
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM lottery WHERE user_id=? AND week=?", (uid, week))
        r = c.fetchone()
        if r:
            c.execute("UPDATE lottery SET tickets=tickets+1 WHERE user_id=? AND week=?", (uid, week))
        else:
            c.execute("INSERT INTO lottery (user_id, tickets, week, joined_at) VALUES (?,?,?,?)",
                      (uid, 1, week, time.time()))
        conn.commit()
        c.execute("SELECT tickets FROM lottery WHERE user_id=? AND week=?", (uid, week))
        total = c.fetchone()["tickets"]
    finally:
        close(conn)
    log_txn(uid, "lottery_buy", -LOTTERY_PRICE, "خرید بلیط لاتاری")
    send_message(chat_id,
                 f"🎫 *بلیط خریداری شد!*\n"
                 f"💰 هزینه: {format_money(LOTTERY_PRICE)}\n"
                 f"🎯 تعداد بلیط‌های تو: *{total}*\n\n"
                 f"💡 قرعه‌کشی آخر هفته!")


def do_lottery_panel(uid, chat_id):
    tickets = get_lottery_tickets(uid)
    conn = db()
    try:
        c = conn.cursor()
        week = get_week_key()
        c.execute("SELECT SUM(tickets) s FROM lottery WHERE week=?", (week,))
        total = c.fetchone()["s"] or 0
        c.execute("SELECT COUNT(DISTINCT user_id) c FROM lottery WHERE week=?", (week,))
        players = c.fetchone()["c"] or 0
    finally:
        close(conn)
    prize = total * LOTTERY_PRICE * 80 // 100
    send_message(chat_id,
                 f"🎫 *لاتاری هفتگی*\n"
                 f"━━━━━━━━━━━━━━━\n"
                 f"🎯 بلیط‌های تو: *{tickets}*\n"
                 f"📊 کل بلیط‌ها: {total}\n"
                 f"👥 شرکت‌کننده‌ها: {players}\n"
                 f"💰 جایزه فعلی: {format_money(prize)} تومان\n\n"
                 f"💡 *دستورات:*\n"
                 f"`لاتاری بخر` — {format_money(LOTTERY_PRICE)} تومان",
                 safe=False)


def draw_lottery():
    """قرعه‌کشی هفته قبل."""
    week = get_week_key()
    conn = db()
    try:
        c = conn.cursor()
        # چک کن برنده هفته قبل داده شده یا نه
        c.execute("SELECT week FROM lottery_winners ORDER BY week DESC LIMIT 1")
        r = c.fetchone()
        # آخرین هفته قبل
        today = today_local()
        days_since_sat = (today.weekday() - 5) % 7
        prev_week = (today - timedelta(days=days_since_sat + 7)).isoformat()
        if r and r["week"] == prev_week:
            return  # قبلاً داده شده

        # همه شرکت‌کننده‌های هفته قبل
        c.execute("SELECT user_id, tickets FROM lottery WHERE week=?", (prev_week,))
        participants = c.fetchall()
        if not participants:
            return

        # قرعه‌کشی بر اساس تعداد بلیط
        pool = []
        for p in participants:
            pool.extend([p["user_id"]] * (p["tickets"] or 1))
        winner = random.choice(pool)

        # جایزه
        c.execute("SELECT SUM(tickets) s FROM lottery WHERE week=?", (prev_week,))
        total_tickets = c.fetchone()["s"] or 0
        prize = total_tickets * LOTTERY_PRICE * 80 // 100

        c.execute("INSERT INTO lottery_winners (week, user_id, tickets, prize, paid, ts) VALUES (?,?,?,?,?,?)",
                  (prev_week, winner, total_tickets, prize, 1, time.time()))
        conn.commit()
    finally:
        close(conn)
    # جایزه
    wp = get_player(winner)
    if wp:
        update_player(winner, money=wp["money"] + prize)
        log_txn(winner, "lottery_win", prize, "برنده لاتاری")
        try:
            send_message(winner, f"🎉 *تبریک! برنده لاتاری شدی!*\n💰 +{format_money(prize)} تومان")
        except Exception:
            pass


# ==================== مهارت‌ها ====================
def do_skills_panel(uid, chat_id):
    p = get_player(uid)
    gems = p.get("gems", 0) or 0
    txt = f"🎓 *مهارت‌ها*\n━━━━━━━━━━━━━━━\n💎 الماس: {gems}\n\n"
    for key, s in SKILLS.items():
        lvl = p.get(f"skill_{key}", 0) or 0
        bar = "█" * lvl + "░" * (s["max"] - lvl)
        txt += f"{s['name']}: {bar} ({lvl}/{s['max']})\n  {s['desc']}\n  💎 هزینه: {s['cost']} الماس\n\n"
    txt += "💡 `مهارت بخر [نام]`\nمثال: `مهارت بخر cook`"
    send_message(chat_id, txt, safe=False)


def do_skill_buy(uid, chat_id, key):
    if key not in SKILLS:
        send_message(chat_id, "❌ مهارت نامعتبر.\nموجود: cook, trade, luck, charm")
        return
    p = get_player(uid)
    s = SKILLS[key]
    lvl = p.get(f"skill_{key}", 0) or 0
    if lvl >= s["max"]:
        send_message(chat_id, f"✅ {s['name']} قبلاً مکس شده!")
        return
    gems = p.get("gems", 0) or 0
    if gems < s["cost"]:
        send_message(chat_id, f"❌ الماس کافی نداری!\nنیاز: {s['cost']} 💎\nداری: {gems} 💎")
        return
    add_gems(uid, -s["cost"], f"خرید مهارت {key}")
    update_player(uid, **{f"skill_{key}": lvl + 1})
    send_message(chat_id, f"✅ {s['name']} → سطح {lvl + 1}!")


# ==================== پت ====================
def do_pet_panel(uid, chat_id):
    p = get_player(uid)
    lvl = p.get("pet_level", 0) or 0
    exp = p.get("pet_exp", 0) or 0
    hunger = p.get("pet_hunger", 100) or 100
    if lvl == 0:
        send_message(chat_id,
                     "🐔 *پت نداری!*\n\n"
                     "برای خرید پت: `پت بخر`\n"
                     "💰 هزینه: ۱۰,۰۰۰ تومان\n\n"
                     "💡 با پت، درآمدت بیشتر می‌شه!",
                     safe=False)
        return
    bar_lvl = "█" * lvl + "░" * (PET_MAX_LEVEL - lvl)
    txt = (
        f"🐔 *پت تو*\n━━━━━━━━━━━━━━━\n"
        f"⭐ سطح: {bar_lvl} ({lvl}/{PET_MAX_LEVEL})\n"
        f"⭐ تجربه: {exp}/100\n"
        f"🍖 سیری: {hunger}%\n\n"
        f"💡 هر لول پت = ۲٪ درآمد بیشتر\n\n"
        f"`پت غذا بده` — {format_money(PET_FEED_PRICE)} تومان"
    )
    send_message(chat_id, txt, safe=False)


def do_pet_buy(uid, chat_id):
    p = get_player(uid)
    if (p.get("pet_level", 0) or 0) > 0:
        send_message(chat_id, "❌ تو الان پت داری!")
        return
    if p["money"] < 10000:
        send_message(chat_id, f"❌ پول کافی نداری!\nنیاز: 10,000\nداری: {format_money(p['money'])}")
        return
    update_player(uid, money=p["money"] - 10000, pet_level=1, pet_exp=0, pet_hunger=100)
    check_ach(uid, chat_id)
    send_message(chat_id, "🎉 *پت جدید!*\n🐔 سطح ۱\n\n💡 غذا بده تا بزرگ شه!")


def do_pet_feed(uid, chat_id):
    p = get_player(uid)
    if (p.get("pet_level", 0) or 0) == 0:
        send_message(chat_id, "❌ اول پت بخر: `پت بخر`")
        return
    if p["money"] < PET_FEED_PRICE:
        send_message(chat_id, f"❌ پول کافی نداری! نیاز: {format_money(PET_FEED_PRICE)}")
        return
    lvl = p.get("pet_level", 0) or 0
    exp = (p.get("pet_exp", 0) or 0) + 30
    hunger = min(100, (p.get("pet_hunger", 100) or 100) + 20)
    update_player(uid, money=p["money"] - PET_FEED_PRICE, pet_hunger=hunger)
    if exp >= 100:
        if lvl >= PET_MAX_LEVEL:
            exp = 99
        else:
            lvl += 1
            exp -= 100
            send_message(chat_id, f"🎉 *پت‌ت لول آپ شد!*\n⭐ سطح {lvl}")
    update_player(uid, pet_level=lvl, pet_exp=exp)
    send_message(chat_id, f"🍖 پت غذا خورد!\n⭐ تجربه: {exp}/100\n🍖 سیری: {hunger}%")


# ==================== دستاورد ====================
def check_ach(uid, chat_id):
    p = get_player(uid)
    if not p:
        return
    b = get_bank(uid)
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT achievement_id FROM achievements WHERE user_id=?", (uid,))
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
        ]
        for aid, cond in checks:
            if cond and aid not in have:
                c.execute("INSERT INTO achievements VALUES (?,?,?)", (uid, aid, time.time()))
                conn.commit()
                reward = ACHIEVEMENTS[aid]["reward"]
                p2 = get_player(uid)
                update_player(uid, money=p2["money"] + reward)
                add_gems(uid, 2, f"دستاورد {aid}")
                send_message(chat_id, f"🎉 *دستاورد!*\n{ACHIEVEMENTS[aid]['name']}\n💵 +{reward:,} تومان\n💎 +۲ الماس", safe=False)
    finally:
        close(conn)


# ==================== State ====================
def set_state(uid, state, data=""):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO user_states VALUES (?,?,?)", (uid, state, json.dumps(data)))
        conn.commit()
    finally:
        close(conn)


def get_state(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT state, data FROM user_states WHERE user_id=?", (uid,))
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
        c.execute("DELETE FROM user_states WHERE user_id=?", (uid,))
        conn.commit()
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
    if ch.startswith("@"):
        url = f"https://ble.ir/{ch[1:]}"
    else:
        url = f"https://ble.ir/{ch.lstrip('-')}"
    title = FORCED_CHANNEL_TITLE or ch
    text = (f"🔒 سلام {first_name}!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"برای استفاده از ربات ابتدا در کانال زیر عضو شو:\n\n"
            f"📢 *{title}*\n\n"
            f"بعد از عضویت روی «✅ عضو شدم» بزن.")
    jk = {"inline_keyboard": [
        [{"text": f"📢 عضویت در {title}", "url": url}],
        [{"text": "✅ عضو شدم، بررسی کن", "callback_data": "check_join"}],
    ]}
    send_message(uid, text, jk, safe=False)


# ==================== مشتری ====================
def spawn_customer(uid):
    p = get_player(uid)
    if not p:
        return None
    if p["active_customer"] and time.time() < (p["customer_expire"] or 0):
        return None
    ctype = random.choices(CUSTOMER_TYPES, weights=[40, 30, 15, 8, 7])[0]
    recipe = random.choice(list(RECIPES.keys()))
    qty = random.randint(1, 3)
    base = RECIPES[recipe]["base_price"] * qty
    reward = int(base * ctype["mult"])
    expire = time.time() + ctype["patience"] * 60
    update_player(uid, active_customer=ctype["name"], customer_expire=expire,
                  customer_order=f"{recipe}:{qty}", customer_reward=reward)
    return {"type": ctype, "recipe": recipe, "qty": qty, "reward": reward, "expire": expire}


def customer_text(cust):
    r = RECIPES[cust["recipe"]]
    mins = int((cust["expire"] - time.time()) / 60)
    return (f"🔔 *مشتری اومد!*\n━━━━━━━━━━━━━━━\n"
            f"{cust['type']['emoji']} {cust['type']['name']}\n"
            f"📋 سفارش: {cust['qty']} {r['emoji']} {r['name']}\n"
            f"⏰ زمان: {mins} دقیقه\n💰 پاداش: {format_money(cust['reward'])} تومان\n\n"
            f"برای تحویل تایپ کن: `تحویل بده`")


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
    reward = p["customer_reward"] or 0
    mult = get_total_multiplier(uid)
    reward = int(reward * mult)
    update_player(uid, **{field: have - qty}, money=p["money"] + reward,
                  total_earned=p["total_earned"] + reward, total_sold=p["total_sold"] + qty,
                  active_customer="", customer_order="", customer_reward=0, customer_expire=0)
    add_exp(uid, 10 * qty)
    log_txn(uid, "customer", reward, f"مشتری {recipe}")
    check_ach(uid, chat_id)
    return ("ok", reward, qty, recipe)


# ==================== Action Helpers ====================
def do_buy(uid, chat_id, item, qty):
    p = get_player(uid)
    if item not in INGREDIENTS:
        send_message(chat_id, "❌ آیتم نامعتبر.")
        return
    price = ing_price(item, p["mixer_level"], p) * qty
    if p["money"] < price:
        send_message(chat_id, f"❌ پول کافی نداری!\nنیاز: {format_money(price)}\nداری: {format_money(p['money'])}")
        return
    have = p.get(item, 0) or 0
    update_player(uid, money=p["money"] - price, **{item: have + qty})
    log_txn(uid, "buy", -price, f"خرید {qty} {INGREDIENTS[item]['name']}")
    track_mission(uid, "buy", 1, chat_id)
    send_message(chat_id, f"✅ {qty} {INGREDIENTS[item]['emoji']} {INGREDIENTS[item]['name']} خریدی\n💵 هزینه: {format_money(price)}\n💰 موجودی: {format_money(p['money'] - price)}\n📦 انبار: {have + qty}")


def do_cook(uid, chat_id, recipe):
    p = get_player(uid)
    if recipe not in RECIPES:
        send_message(chat_id, "❌ دستور پخت نامعتبر.")
        return
    r = RECIPES[recipe]
    missing = []
    for item, need in r["ing"].items():
        have = p.get(item, 0) or 0
        if have < need:
            missing.append(f"{INGREDIENTS[item]['emoji']} {INGREDIENTS[item]['name']}: {have}/{need}")
    if missing:
        send_message(chat_id,
                     "❌ مواد اولیه کم داری!\n\n" + "\n".join(missing) +
                     "\n\n💡 بخر: `خرید پنیر ۵` یا `خرید ادویه ۵`")
        return
    # 🆕 شانس پخت دوتایی با تنور + مهارت آشپزی
    double_chance = (p["oven_level"] or 0) * 0.05
    double_chance += (p.get("skill_cook", 0) or 0) * 0.03
    qty_prod = 2 if random.random() < double_chance else 1
    field = f"falafel_{recipe}"
    have_f = p.get(field, 0) or 0
    up = {field: have_f + qty_prod,
          "total_cooked": (p["total_cooked"] or 0) + qty_prod}
    for item, need in r["ing"].items():
        up[item] = (p.get(item, 0) or 0) - need
    update_player(uid, **up)
    exp_gain = r["exp"] * qty_prod
    if get_today_event() == "cook_bonus":
        exp_gain *= 2
    lvl = add_exp(uid, exp_gain)
    msg = f"✅ {qty_prod}x {r['emoji']} {r['name']} پختی!"
    if qty_prod == 2:
        msg += "\n🔥 تنور دوتایی پخت!"
    msg += f"\n⭐ +{exp_gain} تجربه"
    if lvl:
        msg += f"\n🎉 سطح {lvl} شدی! (+۱ 💎)"
    check_ach(uid, chat_id)
    track_mission(uid, "cook", qty_prod, chat_id)
    send_message(chat_id, msg)


def do_sell(uid, chat_id, target):
    p = get_player(uid)
    mult = get_total_multiplier(uid)
    extra_msg = ""
    if is_weekend():
        extra_msg += "\n🎉 آخر هفته!"
    if get_active_booster(uid) > 1.0:
        extra_msg += "\n⚡ بوستر!"
    if (p.get("pet_level", 0) or 0) > 0:
        extra_msg += f"\n🐔 پت سطح {p['pet_level']}"

    if target == "all":
        total = 0
        qty = 0
        up = {}
        for k in RECIPES:
            h = p.get(f"falafel_{k}", 0) or 0
            if h:
                total += sell_price(k, p["counter_level"], p) * h
                qty += h
                up[f"falafel_{k}"] = 0
        if qty == 0:
            send_message(chat_id, "❌ چیزی برای فروش نداری! اول آشپزی کن.")
            return
        total = int(total * mult)
        update_player(uid, money=p["money"] + total, total_sold=(p["total_sold"] or 0) + qty,
                      total_earned=(p["total_earned"] or 0) + total, **up)
        add_exp(uid, qty * 3)
        check_ach(uid, chat_id)
        track_mission(uid, "sell", total, chat_id)
        send_message(chat_id, f"💰 {qty} فلافل فروختی!\n💵 +{format_money(total)} تومان{extra_msg}", safe=False)
        return
    h = p.get(f"falafel_{target}", 0) or 0
    if h == 0:
        send_message(chat_id, f"❌ {RECIPES[target]['name']} نداری!")
        return
    total = int(sell_price(target, p["counter_level"], p) * h * mult)
    update_player(uid, money=p["money"] + total, total_sold=(p["total_sold"] or 0) + h,
                  total_earned=(p["total_earned"] or 0) + total, **{f"falafel_{target}": 0})
    add_exp(uid, h * 3)
    check_ach(uid, chat_id)
    track_mission(uid, "sell", total, chat_id)
    send_message(chat_id, f"💰 {h}x {RECIPES[target]['emoji']} {RECIPES[target]['name']} فروختی!\n💵 +{format_money(total)} تومان{extra_msg}", safe=False)


def do_daily(uid, chat_id):
    p = get_player(uid)
    now = time.time()
    last_daily = p["last_daily"] or 0
    if now - last_daily < 86400:
        h = int((86400 - (now - last_daily)) // 3600)
        m = int(((86400 - (now - last_daily)) % 3600) // 60)
        send_message(chat_id, f"⏰ هنوز زوده!\nبعدی: {h}س {m}د")
        return
    streak = (p["daily_streak"] or 0) + 1 if now - last_daily < 172800 else 1
    reward = 500 + min(streak * 200, 3000)
    gems_reward = min(streak // 3, 3)
    up = {"last_daily": now, "daily_streak": streak, "money": p["money"] + reward}
    extra_msg = ""
    if streak % 3 == 0:
        up["flour"] = (p.get("flour", 0) or 0) + 3
        up["chickpeas"] = (p.get("chickpeas", 0) or 0) + 3
        up["oil"] = (p.get("oil", 0) or 0) + 2
        extra_msg = "\n🎉 بونوس:\n🌾 +۳ | 🫘 +۳ | 🛢 +۲"
    update_player(uid, **up)
    if gems_reward > 0:
        add_gems(uid, gems_reward, "جایزه روزانه")
        extra_msg += f"\n💎 +{gems_reward} الماس"
    log_txn(uid, "daily", reward, "جایزه روزانه")
    check_ach(uid, chat_id)
    send_message(chat_id, f"🎁 جایزه روزانه!\n💰 +{format_money(reward)} تومان\n🔥 Streak: {streak} روز{extra_msg}")


def do_spin(uid, chat_id):
    p = get_player(uid)
    now = time.time()
    if now - (p["last_spin"] or 0) < 86400:
        h = int((86400 - (now - (p["last_spin"] or 0))) // 3600)
        send_message(chat_id, f"⏰ امروز شانست رو امتحان کردی!\nبعدی: {h} ساعت")
        return
    prizes = [
        ("💰 پول کم", 300, "m_300"), ("💰 پول متوسط", 1000, "m_1000"),
        ("💰 پول زیاد", 3000, "m_3000"), ("🌾 آرد", 5, "f_5"),
        ("🫘 نخود", 5, "c_5"), ("🛢 روغن", 5, "o_5"),
        ("💎 الماس", 2, "g_2"),
        ("💎 جکپات الماس!", 5, "g_5"),
        ("💰 جکپات پول", 10000, "m_10000"), ("😢 خالی", 0, "x"),
    ]
    pr = random.choices(prizes, weights=[22, 18, 8, 10, 10, 10, 8, 3, 3, 8])[0]
    up = {"last_spin": now}
    if pr[2].startswith("m_"):
        up["money"] = p["money"] + pr[1]
        msg_ = f"💵 +{format_money(pr[1])} تومان"
    elif pr[2].startswith("f_"):
        up["flour"] = (p.get("flour", 0) or 0) + pr[1]
        msg_ = f"🌾 +{pr[1]} آرد"
    elif pr[2].startswith("c_"):
        up["chickpeas"] = (p.get("chickpeas", 0) or 0) + pr[1]
        msg_ = f"🫘 +{pr[1]} نخود"
    elif pr[2].startswith("o_"):
        up["oil"] = (p.get("oil", 0) or 0) + pr[1]
        msg_ = f"🛢 +{pr[1]} روغن"
    elif pr[2].startswith("g_"):
        add_gems(uid, pr[1], "گردونه")
        msg_ = f"💎 +{pr[1]} الماس"
    else:
        msg_ = "😢 خالی!"
    update_player(uid, **up)
    send_message(chat_id, f"🎰 *گردونه شانس!*\n━━━━━━━━━━━━━━━\n🎉 {pr[0]}\n{msg_}", safe=False)


def do_upgrade(uid, chat_id, key):
    p = get_player(uid)
    cost = upgrade_cost(uid, key)
    if cost is None:
        send_message(chat_id, f"✅ {UPGRADES[key]['name']} قبلاً مکس شده!")
        return
    if p["money"] < cost:
        send_message(chat_id, f"❌ پول کافی نداری!\nنیاز: {format_money(cost)}\nداری: {format_money(p['money'])}")
        return
    new_lvl = (p.get(f"{key}_level", 0) or 0) + 1
    update_player(uid, money=p["money"] - cost, **{f"{key}_level": new_lvl})
    check_ach(uid, chat_id)
    send_message(chat_id, f"✅ {UPGRADES[key]['name']} → سطح {new_lvl}!\n💵 -{format_money(cost)} تومان")


def do_profile(uid, chat_id, first_name):
    p = get_player(uid)
    b = get_bank(uid)
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) c FROM achievements WHERE user_id=?", (uid,))
        ach = c.fetchone()["c"]
    finally:
        close(conn)
    weekend_line = "🎉 آخر هفته: ۲ برابر!" if is_weekend() else ""
    booster_line = booster_status(uid)
    pet_line = f"🐔 پت سطح {p.get('pet_level', 0) or 0}" if (p.get("pet_level", 0) or 0) > 0 else "🐔 پت نداری"
    lottery_tickets = get_lottery_tickets(uid)
    send_message(chat_id,
                 f"👤 *پروفایل {first_name}*\n━━━━━━━━━━━━━━━\n"
                 f"⭐ سطح {p['level']} ({p['exp']}/100)\n"
                 f"💰 جیب: {format_money(p['money'])} تومان\n"
                 f"💎 الماس: {p.get('gems', 0) or 0}\n"
                 f"🏦 بانک: {format_money(b['balance'])} تومان\n"
                 f"📈 سرمایه: {format_money(b['invested'])} تومان\n\n"
                 f"🌾{p.get('flour',0)} 🫘{p.get('chickpeas',0)} 🛢{p.get('oil',0)} 🧀{p.get('cheese',0)} 🌶{p.get('spice',0)}\n"
                 f"🍽 {count_falafel(p)} فلافل آماده\n"
                 f"📦 فروش: {p['total_sold']}\n"
                 f"💵 درآمد: {format_money(p['total_earned'])}\n"
                 f"🍳 پخت: {p['total_cooked']}\n"
                 f"🎯 دستاورد: {ach}/{len(ACHIEVEMENTS)}\n"
                 f"🔥 Streak: {p['daily_streak']} روز\n"
                 f"{pet_line}\n"
                 f"🎫 بلیط لاتاری: {lottery_tickets}\n"
                 f"{booster_line}\n{weekend_line}", safe=False)


def do_top(chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT first_name, total_earned, level FROM players ORDER BY total_earned DESC LIMIT 10")
        rows = c.fetchall()
    finally:
        close(conn)
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    txt = "🏆 *رتبه‌بندی کل*\n━━━━━━━━━━━━━━━\n"
    for i, r in enumerate(rows):
        txt += f"{medals[i]} {r['first_name']} — سطح {r['level']} — {format_money(r['total_earned'] or 0)}\n"
    send_message(chat_id, txt, safe=False)


def do_customer(uid, chat_id):
    p = get_player(uid)
    if not p["active_customer"] or time.time() > (p["customer_expire"] or 0):
        if random.random() < 0.4:
            c = spawn_customer(uid)
            if c:
                send_message(chat_id, customer_text(c), safe=False)
                return
        send_message(chat_id, "🔕 الان مشتری نداری!\nبعداً امتحان کن.")
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
        send_message(chat_id,
                     f"❌ {r[2]} عدد {RECIPES[r[1]]['name']} کم داری!\n"
                     f"اول این رو بپز: `آشپزی {'حرفه‌ای' if r[1] == 'special' else 'ساندویچ' if r[1] == 'sandwich' else 'ساده'}`")
        return
    _, reward, qty, recipe = r
    extra = ""
    if is_weekend():
        extra += "\n🎉 آخر هفته!"
    if get_active_booster(uid) > 1.0:
        extra += "\n⚡ بوستر!"
    send_message(chat_id, f"🎉 {qty}x {RECIPES[recipe]['emoji']} {RECIPES[recipe]['name']} تحویل دادی!\n💰 +{format_money(reward)} تومان{extra}", safe=False)


# ==================== کلن ====================
def get_clan_by_name(name):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM clans WHERE name=?", (name,))
        r = c.fetchone()
        return dict(r) if r else None
    finally:
        close(conn)


def get_user_clan(uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT c.* FROM clans c JOIN clan_members m ON c.id=m.clan_id WHERE m.user_id=?", (uid,))
        r = c.fetchone()
        return dict(r) if r else None
    finally:
        close(conn)


def get_clan_members(clan_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT user_id FROM clan_members WHERE clan_id=?", (clan_id,))
        return [r["user_id"] for r in c.fetchall()]
    finally:
        close(conn)


def do_clan_create(uid, chat_id, name):
    name = name.strip()
    if not name or len(name) > 20:
        send_message(chat_id, "❌ اسم کلن باید بین ۱ تا ۲۰ کاراکتر باشه.")
        return
    if get_user_clan(uid):
        send_message(chat_id, "❌ تو الان توی یه کلنی! اول خارج شو.")
        return
    if get_clan_by_name(name):
        send_message(chat_id, f"❌ کلنی با اسم «{name}» وجود داره.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO clans (name, owner_id, created_at) VALUES (?,?,?)",
                  (name, uid, time.time()))
        cid = c.lastrowid
        c.execute("INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?,?,?)",
                  (cid, uid, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"🏰 کلن «{name}» ساخته شد!\n👑 تو مالکش هستی.")


def do_clan_join(uid, chat_id, name):
    if get_user_clan(uid):
        send_message(chat_id, "❌ تو الان توی یه کلنی!")
        return
    clan = get_clan_by_name(name)
    if not clan:
        send_message(chat_id, f"❌ کلن «{name}» پیدا نشد.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?,?,?)",
                  (clan["id"], uid, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"✅ عضویتت توی کلن «{name}» تایید شد!")


def do_clan_leave(uid, chat_id):
    clan = get_user_clan(uid)
    if not clan:
        send_message(chat_id, "❌ تو توی هیچ کلنی نیستی.")
        return
    if clan["owner_id"] == uid:
        send_message(chat_id, "❌ مالک کلن نمی‌تونه خارج شه.")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM clan_members WHERE user_id=?", (uid,))
        c.execute("SELECT COUNT(*) as cnt FROM clan_members WHERE clan_id=?", (clan["id"],))
        remaining = c.fetchone()["cnt"]
        if remaining == 0:
            c.execute("DELETE FROM clans WHERE id=?", (clan["id"],))
            send_message(chat_id, f"✅ از کلن «{clan['name']}» خارج شدی.\n⚠️ کلن چون خالی شد، حذف شد.")
        else:
            send_message(chat_id, f"✅ از کلن «{clan['name']}» خارج شدی.")
        conn.commit()
    finally:
        close(conn)


def do_clan_info(uid, chat_id):
    clan = get_user_clan(uid)
    if not clan:
        send_message(chat_id, "❌ تو توی هیچ کلنی نیستی.\nساخت: `کلن بساز [اسم]`", safe=False)
        return
    members = get_clan_members(clan["id"])
    send_message(chat_id,
                 f"🏰 *کلن {clan['name']}*\n━━━━━━━━━━━━━━━\n"
                 f"👑 مالک: `{clan['owner_id']}`\n"
                 f"👥 اعضا: {len(members)}\n"
                 f"💰 گنجینه: {format_money(clan['treasury'] or 0)} تومان\n"
                 f"⭐ امتیاز: {clan['points'] or 0}", safe=False)


def do_clan_donate(uid, chat_id, amount):
    clan = get_user_clan(uid)
    if not clan:
        send_message(chat_id, "❌ اول عضو یه کلن شو.")
        return
    p = get_player(uid)
    if amount <= 0:
        send_message(chat_id, "❌ مبلغ نامعتبر.")
        return
    if p["money"] < amount:
        send_message(chat_id, f"❌ پول کافی نداری! داری: {format_money(p['money'])}")
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("UPDATE clans SET treasury=treasury+?, points=points+? WHERE id=?",
                  (amount, amount // 100, clan["id"]))
        conn.commit()
    finally:
        close(conn)
    update_player(uid, money=p["money"] - amount)
    log_txn(uid, "clan_donate", -amount, f"اهدای {amount} به کلن")
    send_message(chat_id, f"✅ {format_money(amount)} تومان به گنجینه کلن «{clan['name']}» اضافه شد!")


def do_clan_top(chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT name, treasury, points FROM clans ORDER BY points DESC, treasury DESC LIMIT 10")
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "هنوز کلنی ساخته نشده.")
        return
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    txt = "🏆 *رتبه‌بندی کلن‌ها*\n━━━━━━━━━━━━━━━\n"
    for i, r in enumerate(rows):
        txt += f"{medals[i]} {r['name']} — ⭐{r['points'] or 0} — 💰{format_money(r['treasury'] or 0)}\n"
    send_message(chat_id, txt, safe=False)


# ==================== دوئل ====================
def do_duel(challenger_id, chat_id, opponent_id, amount):
    if challenger_id == opponent_id:
        send_message(chat_id, "❌ نمی‌تونی با خودت دوئل کنی!")
        return
    if amount < 1000:
        send_message(chat_id, "❌ حداقل مبلغ دوئل ۱,۰۰۰ تومانه.")
        return
    cp = get_player(challenger_id)
    op = get_player(opponent_id)
    if not cp or not op:
        send_message(chat_id, "❌ یکی از بازیکن‌ها توی بازی نیست.")
        return
    if cp["money"] < amount:
        send_message(chat_id, f"❌ تو پول کافی نداری! داری: {format_money(cp['money'])}")
        return
    if op["money"] < amount:
        send_message(chat_id, "❌ حریف پول کافی نداره!")
        return
    winner_id = random.choice([challenger_id, opponent_id])
    loser_id = opponent_id if winner_id == challenger_id else challenger_id
    tax = amount * 2 // 20
    wp = get_player(winner_id)
    lp = get_player(loser_id)
    if not wp or not lp:
        send_message(chat_id, "❌ خطا در پردازش.")
        return
    if lp["money"] < amount:
        send_message(chat_id, "❌ حریف دیگه پول کافی نداره!")
        return
    update_player(winner_id, money=wp["money"] + amount - tax,
                  total_earned=(wp["total_earned"] or 0) + amount - tax)
    update_player(loser_id, money=lp["money"] - amount)
    log_txn(winner_id, "duel_win", amount - tax, "برد دوئل")
    log_txn(loser_id, "duel_lose", -amount, "باخت دوئل")
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO duels (challenger_id, opponent_id, amount, winner_id, ts) VALUES (?,?,?,?,?)",
                  (challenger_id, opponent_id, amount, winner_id, time.time()))
        conn.commit()
    finally:
        close(conn)
    wname = wp["first_name"]
    send_message(chat_id,
                 f"⚔️ *دوئل!*\n━━━━━━━━━━━━━━━\n"
                 f"💰 مبلغ: {format_money(amount)} هر نفر\n"
                 f"🎲 کمیسیون: {format_money(tax)}\n\n"
                 f"🏆 برنده: {wname}\n"
                 f"💰 سود برنده: {format_money(amount - tax)}", safe=False)


# ==================== ماموریت روزانه ====================
def get_missions(uid):
    today = today_local().isoformat()
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT missions, completed FROM daily_missions WHERE user_id=? AND day=?", (uid, today))
        r = c.fetchone()
        if r:
            return json.loads(r["missions"]), json.loads(r["completed"])
        missions = [
            {"id": "cook", "title": "🍳 بپز",       "target": random.randint(3, 8),       "reward": random.randint(500, 1500),  "progress": 0},
            {"id": "sell", "title": "💰 فروش بگیر", "target": random.randint(3000, 12000), "reward": random.randint(1000, 2500), "progress": 0},
            {"id": "buy",  "title": "🛒 مواد بخر",  "target": random.randint(3, 10),       "reward": random.randint(500, 1000),  "progress": 0},
        ]
        completed = []
        c.execute("INSERT OR REPLACE INTO daily_missions VALUES (?,?,?,?)",
                  (uid, today, json.dumps(missions), json.dumps(completed)))
        conn.commit()
        return missions, completed
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
                    log_txn(uid, "mission", m["reward"], f"ماموریت {m['title']}")
                    send_message(chat_id, f"🎯 ماموریت انجام شد!\n{m['title']} ✅\n💰 +{format_money(m['reward'])}")
                changed = True
        if changed:
            conn = db()
            try:
                c = conn.cursor()
                c.execute("UPDATE daily_missions SET missions=?, completed=? WHERE user_id=? AND day=?",
                          (json.dumps(missions), json.dumps(completed), uid, today))
                conn.commit()
            finally:
                close(conn)
    except Exception:
        pass


def do_missions(uid, chat_id):
    missions, completed = get_missions(uid)
    txt = "🎯 *ماموریت‌های امروز*\n━━━━━━━━━━━━━━━\n"
    for m in missions:
        done = "✅" if m["id"] in completed else "⏳"
        bar_len = min(int((m["progress"] / m["target"]) * 10), 10) if m["target"] else 0
        bar = "█" * bar_len + "░" * (10 - bar_len)
        txt += f"{done} {m['title']}: {m['progress']}/{m['target']}\n   {bar} 💰{format_money(m['reward'])}\n"
    send_message(chat_id, txt, safe=False)


# ==================== کارت به کارت ====================
def do_transfer(sender_id, chat_id, receiver_id, amount, sender_name="کاربر"):
    if sender_id == receiver_id:
        send_message(chat_id, "❌ نمی‌تونی به خودت پول بفرستی!")
        return
    if amount < TRANSFER_MIN:
        send_message(chat_id, f"❌ حداقل مبلغ انتقال {format_money(TRANSFER_MIN)} تومانه.")
        return
    if amount > TRANSFER_MAX:
        send_message(chat_id, f"❌ حداکثر مبلغ انتقال {format_money(TRANSFER_MAX)} تومانه.")
        return
    sp = get_player(sender_id)
    rp = get_player(receiver_id)
    if not sp:
        send_message(chat_id, "❌ حساب فرستنده پیدا نشد.")
        return
    if not rp:
        send_message(chat_id, f"❌ گیرنده `{receiver_id}` توی بازی نیست!", safe=False)
        return
    commission = int(amount * TRANSFER_COMMISSION)
    total_needed = amount + commission
    if sp["money"] < total_needed:
        send_message(chat_id,
                     f"❌ پول کافی نداری!\n"
                     f"💰 مبلغ: {format_money(amount)}\n"
                     f"💸 کمیسیون ۲٪: {format_money(commission)}\n"
                     f"💵 نیاز کل: {format_money(total_needed)}\n"
                     f"💰 داری: {format_money(sp['money'])}")
        return
    update_player(sender_id, money=sp["money"] - total_needed)
    update_player(receiver_id, money=rp["money"] + amount)
    log_txn(sender_id, "transfer_out", -total_needed, f"انتقال به {receiver_id}")
    log_txn(receiver_id, "transfer_in", amount, f"دریافت از {sender_id}")
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO card_transfers (sender_id, receiver_id, amount, commission, ts) VALUES (?,?,?,?,?)",
                  (sender_id, receiver_id, amount, commission, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id,
                 f"💳 *کارت به کارت موفق!*\n"
                 f"━━━━━━━━━━━━━━━\n"
                 f"👤 به: {rp['first_name']}\n"
                 f"💰 مبلغ: {format_money(amount)} تومان\n"
                 f"💸 کمیسیون ۲٪: {format_money(commission)}\n"
                 f"💵 کسر شده: {format_money(total_needed)}\n\n"
                 f"💰 موجودی: {format_money(sp['money'] - total_needed)}", safe=False)
    try:
        send_message(receiver_id,
                     f"💳 *پول دریافت کردی!*\n"
                     f"👤 از: {sender_name}\n"
                     f"💰 مبلغ: {format_money(amount)} تومان\n"
                     f"💰 موجودی: {format_money(rp['money'] + amount)}", safe=False)
    except Exception:
        pass


def do_admin_transfer(admin_id, chat_id, receiver_id, amount, note=""):
    if not is_admin(admin_id):
        return
    if amount <= 0:
        send_message(chat_id, "❌ مبلغ باید مثبت باشه.", ADMIN_KB()); return
    if amount > ADMIN_MONEY_LIMIT:
        send_message(chat_id, f"❌ حداکثر مبلغ {format_money(ADMIN_MONEY_LIMIT)} تومانه.", ADMIN_KB()); return
    rp = get_player(receiver_id)
    if not rp:
        send_message(chat_id, f"❌ بازیکن `{receiver_id}` پیدا نشد.", ADMIN_KB(), safe=False); return
    update_player(receiver_id, money=rp["money"] + amount)
    log_txn(receiver_id, "admin_transfer", amount, "کارت به کارت ادمینی")
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO admin_txns (target_id, admin_id, amount, note, ts) VALUES (?,?,?,?,?)",
                  (receiver_id, admin_id, amount, note or "کارت به کارت ادمینی", time.time()))
        txn_id = c.lastrowid
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id,
                 f"✅ *کارت به کارت ادمینی*\n"
                 f"👤 به: {rp['first_name']} (`{receiver_id}`)\n"
                 f"💰 مبلغ: {format_money(amount)}\n"
                 f"🆔 کد برگشت: `{txn_id}`", ADMIN_KB(), safe=False)
    try:
        send_message(receiver_id, f"💳 ادمین {format_money(amount)} تومان بهت داد!")
    except Exception:
        pass


def do_transfer_history(uid, chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("""SELECT sender_id, receiver_id, amount, commission, ts FROM card_transfers
                     WHERE sender_id=? OR receiver_id=? ORDER BY ts DESC LIMIT 10""", (uid, uid))
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "📭 هنوز کارت به کارتی نکردی.")
        return
    txt = "💳 *تاریخچه کارت به کارت*\n━━━━━━━━━━━━━━━\n"
    for r in rows:
        when = datetime.fromtimestamp(r["ts"]).strftime("%m/%d %H:%M")
        if r["sender_id"] == uid:
            txt += f"📤 به `{r['receiver_id']}` — {format_money(r['amount'])} ({when})\n"
        else:
            txt += f"📥 از `{r['sender_id']}` — {format_money(r['amount'])} ({when})\n"
    send_message(chat_id, txt, safe=False)


# ==================== هدیه ====================
def do_gift(sender_id, chat_id, receiver_id, amount, sender_name="کاربر"):
    if sender_id == receiver_id:
        send_message(chat_id, "❌ به خودت نمی‌تونی هدیه بدی!")
        return
    if amount < 100:
        send_message(chat_id, "❌ حداقل هدیه ۱۰۰ تومانه.")
        return
    sp = get_player(sender_id)
    rp = get_player(receiver_id)
    if not sp or not rp:
        send_message(chat_id, "❌ یکیش پیدا نشد.")
        return
    if sp["money"] < amount:
        send_message(chat_id, f"❌ پول کافی نداری! داری: {format_money(sp['money'])}")
        return
    update_player(sender_id, money=sp["money"] - amount)
    update_player(receiver_id, money=rp["money"] + amount)
    log_txn(sender_id, "gift_out", -amount, f"هدیه به {receiver_id}")
    log_txn(receiver_id, "gift_in", amount, f"هدیه از {sender_id}")
    send_message(chat_id, f"🎁 به {rp['first_name']} {format_money(amount)} تومان هدیه دادی!")
    try:
        send_message(receiver_id, f"🎁 از {sender_name} {format_money(amount)} تومان هدیه گرفتی!")
    except Exception:
        pass


# ==================== ادمین پیشرفته ====================
def do_admin_add(target_id, amount, admin_id, chat_id, note=""):
    tp = get_player(target_id)
    if not tp:
        send_message(chat_id, f"❌ `{target_id}` پیدا نشد.", ADMIN_KB(), safe=False)
        return
    update_player(target_id, money=tp["money"] + amount)
    conn = db()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO admin_txns (target_id, admin_id, amount, note, ts) VALUES (?,?,?,?,?)",
                  (target_id, admin_id, amount, note, time.time()))
        txn_id = c.lastrowid
        conn.commit()
    finally:
        close(conn)
    sign = "+" if amount > 0 else ""
    send_message(chat_id, f"✅ `{target_id}` {sign}{format_money(amount)} تومان\n🆔 کد برگشت: `{txn_id}`", ADMIN_KB(), safe=False)


def do_admin_undo(txn_id, admin_id, chat_id):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM admin_txns WHERE id=?", (txn_id,))
        r = c.fetchone()
        if not r:
            send_message(chat_id, "❌ تراکنش پیدا نشد.", ADMIN_KB())
            return
        txn = dict(r)
        if txn["reversed"]:
            send_message(chat_id, "❌ قبلاً برگشت داده شده.", ADMIN_KB())
            return
        tp = get_player(txn["target_id"])
        if not tp:
            send_message(chat_id, "❌ کاربر پیدا نشد.", ADMIN_KB())
            return
        update_player(txn["target_id"], money=tp["money"] - txn["amount"])
        c.execute("UPDATE admin_txns SET reversed=1 WHERE id=?", (txn_id,))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, f"✅ تراکنش `{txn_id}` برگشت داده شد.", ADMIN_KB(), safe=False)


def do_reset_all(uid, chat_id):
    if not is_admin(uid):
        return
    conn = db()
    try:
        c = conn.cursor()
        for t in ["players", "achievements", "transactions", "shop_orders",
                  "clans", "clan_members", "duels", "daily_missions",
                  "admin_txns", "banks", "user_states", "casino_log",
                  "card_transfers", "discount_codes", "boosters", "reminders",
                  "lottery", "lottery_winners", "daily_events", "gems_log"]:
            c.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id, "✅ *ریست کلی انجام شد!*", ADMIN_KB(), safe=False)


def do_admin_add_money(uid, chat_id, target_id, amount):
    if not is_admin(uid):
        return
    if amount <= 0:
        send_message(chat_id, "❌ مبلغ باید مثبت باشه.")
        return
    if amount > ADMIN_MONEY_LIMIT:
        send_message(chat_id, f"❌ حداکثر {format_money(ADMIN_MONEY_LIMIT)} تومانه.")
        return
    tp = get_player(target_id)
    if not tp:
        send_message(chat_id, f"❌ بازیکن `{target_id}` پیدا نشد.", ADMIN_KB(), safe=False)
        return
    update_player(target_id, money=tp["money"] + amount)
    log_txn(target_id, "admin_add_money", amount, "افزودن توسط ادمین")
    send_message(chat_id, f"✅ به `{target_id}` {format_money(amount)} تومان اضافه شد.", ADMIN_KB(), safe=False)


# ==================== کد تخفیف ====================
def do_redeem_code(uid, chat_id, code):
    code = code.strip().upper()
    if not code:
        send_message(chat_id, "مثال: `کد WELCOME`", safe=False)
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM discount_codes WHERE code=?", (code,))
        r = c.fetchone()
        if not r:
            send_message(chat_id, "❌ کد پیدا نشد!")
            return
        d = dict(r)
        if d["uses"] >= d["max_uses"]:
            send_message(chat_id, "❌ ظرفیت کد پر شده!")
            return
        try:
            used_by = json.loads(d["used_by"] or "[]")
        except Exception:
            used_by = []
        if uid in used_by:
            send_message(chat_id, "❌ قبلاً استفاده کردی!")
            return
        p = get_player(uid)
        amount = d["amount"] or 0
        update_player(uid, money=p["money"] + amount)
        log_txn(uid, "discount_code", amount, f"کد {code}")
        used_by.append(uid)
        c.execute("UPDATE discount_codes SET uses=uses+1, used_by=? WHERE code=?",
                  (json.dumps(used_by), code))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id,
                 f"✅ *کد فعال شد!*\n💰 +{format_money(amount)} تومان\n"
                 f"📊 باقی: {d['max_uses'] - d['uses'] - 1}", safe=False)


def do_admin_create_code(uid, chat_id, code, amount, max_uses=1):
    if not is_admin(uid):
        return
    code = code.strip().upper()
    if not code or amount <= 0 or amount > 100000:
        send_message(chat_id, "فرمت: `کد بساز WELCOME 5000 10`", safe=False)
        return
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT code FROM discount_codes WHERE code=?", (code,))
        if c.fetchone():
            send_message(chat_id, f"❌ کد `{code}` وجود داره.", ADMIN_KB(), safe=False)
            return
        c.execute("INSERT INTO discount_codes (code, amount, max_uses, created_by, created_at, used_by) VALUES (?,?,?,?,?,'[]')",
                  (code, amount, max_uses, uid, time.time()))
        conn.commit()
    finally:
        close(conn)
    send_message(chat_id,
                 f"✅ *کد ساخته شد!*\n🎟 `{code}`\n💰 {format_money(amount)}\n📊 {max_uses} نفر",
                 ADMIN_KB(), safe=False)


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
        send_message(chat_id, "🎟 هیچ کدی نیست.", ADMIN_KB())
        return
    txt = "🎟 *کدهای تخفیف*\n━━━━━━━━━━━━━━━\n"
    for r in rows:
        txt += f"• `{r['code']}` — {format_money(r['amount'])} ({r['uses']}/{r['max_uses']})\n"
    send_message(chat_id, txt, ADMIN_KB(), safe=False)


# ==================== Parser ====================
def parse_text_command(uid, chat_id, first_name, username, text):
    text = normalize_numbers(text)

    if text.startswith(("خرید", "بخر", "آشپزی", "بپز", "فروش", "بفروش",
                        "جایزه", "گردونه", "آپگرید", "مشتری", "تحویل",
                        "کازینو", "جعبه", "کارت", "انتقال", "بوستر",
                        "کد", "لاتاری", "مهارت", "پت", "هدیه")):
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

    # ========== خرید ==========
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
        send_message(chat_id,
                     "🛒 *راهنمای خرید:*\n\n"
                     "`خرید آرد ۵`\n`خرید نخود ۳`\n`خرید روغن ۲`\n"
                     "`خرید پنیر ۳`\n`خرید ادویه ۳`", safe=False)
        return True

    # ========== آشپزی ==========
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
        send_message(chat_id,
                     "🍳 *راهنمای آشپزی:*\n\n"
                     "`آشپزی ساده` 🟡\n`آشپزی حرفه‌ای` 🟠\n"
                     "`آشپزی ساندویچ` 🥙\n`آشپزی پنیری` 🧀\n"
                     "`آشپزی تند` 🌶\n`آشپزی دلوکس` 👑", safe=False)
        return True

    # ========== فروش ==========
    if t.startswith("فروش") or t.startswith("بفروش"):
        if "همه" in t or "کل" in t or "تمام" in t:
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
        send_message(chat_id,
                     "💰 *راهنمای فروش:*\n\n"
                     "`فروش همه`\n`فروش ساده` | `فروش مخصوص`\n"
                     "`فروش ساندویچ` | `فروش پنیری`\n"
                     "`فروش تند` | `فروش دلوکس`", safe=False)
        return True

    if t.startswith("جایزه") or t.startswith("پاداش"):
        do_daily(uid, chat_id); return True

    if t.startswith("گردونه") or t.startswith("شانس") or "گردونه" in t:
        do_spin(uid, chat_id); return True

    if t.startswith("آپگرید") or t.startswith("ارتقا") or t.startswith("قوی"):
        if "تنور" in t:
            do_upgrade(uid, chat_id, "oven"); return True
        if "مخلوط" in t:
            do_upgrade(uid, chat_id, "mixer"); return True
        if "پیشخوان" in t or "کانتر" in t:
            do_upgrade(uid, chat_id, "counter"); return True
        send_message(chat_id,
                     "⚙️ *راهنمای آپگرید:*\n\n"
                     "`آپگرید تنور` 🔥\n`آپگرید مخلوط‌کن` 🥣\n`آپگرید پیشخوان` 🏪", safe=False)
        return True

    if t.startswith("پروفایل") or t == "من" or t.startswith("حساب من"):
        do_profile(uid, chat_id, first_name); return True

    if t.startswith("رتبه") or t.startswith("تاپ") or t.startswith("برترین") or "رتبه‌بندی" in t:
        do_top(chat_id); return True

    if t.startswith("مشتری") or t.startswith("سفارش"):
        do_customer(uid, chat_id); return True

    if t.startswith("تحویل") or t.startswith("سرویس") or t.startswith("بده") or "تحویل بده" in t:
        do_serve(uid, chat_id); return True

    if t.startswith("ماموریت") or t.startswith("کوئست"):
        do_missions(uid, chat_id); return True

    # ========== بانک ==========
    if t.startswith("بانک"):
        body = t[4:].strip()
        nums_bank = re.findall(r'\d+', body)
        amt_bank = int(nums_bank[0]) if nums_bank else 0
        if body.startswith("واریز"):
            if amt_bank <= 0:
                send_message(chat_id, "مثال: `بانک واریز ۵۰۰۰`", safe=False); return True
            do_bank_deposit(uid, chat_id, amt_bank); return True
        if body.startswith("برداشت"):
            if amt_bank <= 0:
                send_message(chat_id, "مثال: `بانک برداشت ۵۰۰۰`", safe=False); return True
            do_bank_withdraw(uid, chat_id, amt_bank); return True
        if body.startswith("سرمایه"):
            if amt_bank <= 0:
                send_message(chat_id, "مثال: `بانک سرمایه ۵۰۰۰`", safe=False); return True
            do_bank_invest(uid, chat_id, amt_bank); return True
        if body.startswith("پایان"):
            if amt_bank <= 0:
                send_message(chat_id, "مثال: `بانک پایان ۵۰۰۰`", safe=False); return True
            do_bank_end_invest(uid, chat_id, amt_bank); return True
        if body.startswith("جمع") or body.startswith("سود"):
            do_bank_collect(uid, chat_id); return True
        do_bank(uid, chat_id, first_name); return True

    # ========== کازینو ==========
    if t.startswith("کازینو"):
        body = t[6:].strip()
        nums_c = re.findall(r'\d+', body)
        if not nums_c:
            send_message(chat_id,
                         "🎰 *کازینو*\n━━━━━━━━━━━━━━━\n\n"
                         "`کازینو ۵۰۰۰ شیر`\n"
                         "`کازینو ۵۰۰۰ خط`\n\n"
                         "💡 برد = ۲ برابر!", safe=False)
            return True
        amount = int(nums_c[0])
        if "شیر" in body:
            do_casino(uid, chat_id, amount, "شیر"); return True
        if "خط" in body:
            do_casino(uid, chat_id, amount, "خط"); return True
        send_message(chat_id, "❌ بنویس: `کازینو ۵۰۰۰ شیر` یا `کازینو ۵۰۰۰ خط`", safe=False)
        return True

    if t.startswith("جعبه") or t.startswith("شانس جعبه"):
        do_mystery_box(uid, chat_id); return True

    # ========== بوستر ==========
    if t.startswith("بوستر"):
        if "وضعیت" in t or "چک" in t:
            send_message(chat_id, booster_status(uid))
            return True
        if "بخر" in t or "خرید" in t or t == "بوستر":
            do_booster(uid, chat_id); return True
        send_message(chat_id,
                     "⚡ *بوستر*\n━━━━━━━━━━━━━━━\n\n"
                     "`بوستر بخر` — ۵,۰۰۰ تومان\n"
                     "`بوستر وضعیت`", safe=False)
        return True

    # ========== لاتاری ==========
    if t.startswith("لاتاری") or t.startswith("lottery"):
        body = t.replace("لاتاری", "").replace("lottery", "").strip()
        if body.startswith("بخر") or body.startswith("خرید"):
            do_lottery_buy(uid, chat_id); return True
        do_lottery_panel(uid, chat_id); return True

    # ========== مهارت ==========
    if t.startswith("مهارت"):
        body = t[5:].strip()
        if body.startswith("بخر") or body.startswith("خرید"):
            parts = body.replace("بخر", "").replace("خرید", "").strip().split()
            if not parts:
                send_message(chat_id, "مثال: `مهارت بخر cook`", safe=False); return True
            do_skill_buy(uid, chat_id, parts[0].lower()); return True
        do_skills_panel(uid, chat_id); return True

    # ========== پت ==========
    if t.startswith("پت"):
        body = t[2:].strip()
        if body.startswith("بخر") or body.startswith("خرید"):
            do_pet_buy(uid, chat_id); return True
        if body.startswith("غذا") or body.startswith("food"):
            do_pet_feed(uid, chat_id); return True
        do_pet_panel(uid, chat_id); return True

    # ========== هدیه ==========
    if t.startswith("هدیه"):
        nums_h = re.findall(r'\d+', t)
        if len(nums_h) >= 2:
            receiver_id = int(nums_h[0]) if int(nums_h[0]) > 99999 else int(nums_h[1])
            amount = int(nums_h[1]) if int(nums_h[0]) > 99999 else int(nums_h[0])
            do_gift(uid, chat_id, receiver_id, amount, first_name); return True
        send_message(chat_id, "مثال: `هدیه 123456789 5000`", safe=False)
        return True

    # ========== یادآور ==========
    if t.startswith("یادآور") or t.startswith("reminder"):
        body = t.replace("یادآور", "").replace("reminder", "").strip()
        if body.startswith("لیست") or body == "ها" or body == "":
            do_reminder_list(uid, chat_id); return True
        parts = body.split(maxsplit=1)
        if len(parts) < 2:
            send_message(chat_id,
                         "🔔 *یادآور*\n\n"
                         "`یادآور ۱۰m جلسه`\n"
                         "`یادآور ۱h تماس`\n"
                         "`یادآور لیست`\n\n"
                         "واحدها: s | m | h", safe=False)
            return True
        dur_str, reminder_text = parts
        m = re.match(r'^(\d+)([smh])$', dur_str.lower())
        if not m:
            send_message(chat_id, "❌ فرمت اشتباه. مثال: `۱۰m` یا `۱h`", safe=False); return True
        n = int(m.group(1))
        unit = m.group(2)
        sec = n * {"s": 1, "m": 60, "h": 3600}[unit]
        do_reminder_set(uid, chat_id, reminder_text, sec)
        return True

    # ========== کد تخفیف ==========
    if t.startswith("کد"):
        body = t[2:].strip()
        if not body:
            send_message(chat_id, "مثال: `کد WELCOME`", safe=False); return True
        if is_admin(uid) and ("بساز" in body or "ساخت" in body):
            parts = body.replace("بساز", "").replace("ساخت", "").strip().split()
            if len(parts) < 2:
                send_message(chat_id, "فرمت: `کد بساز WELCOME 5000 10`", safe=False); return True
            code = parts[0]
            amount = int(parts[1]) if parts[1].isdigit() else 0
            max_uses = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
            do_admin_create_code(uid, chat_id, code, amount, max_uses)
            return True
        if is_admin(uid) and body.startswith("لیست"):
            do_admin_list_codes(uid, chat_id); return True
        do_redeem_code(uid, chat_id, body.split()[0])
        return True

    # ========== کارت به کارت ==========
    if t.startswith("کارت") or t.startswith("انتقال"):
        nums_ct = re.findall(r'\d+', t)
        if len(nums_ct) >= 2:
            if int(nums_ct[0]) > 99999:
                receiver_id = int(nums_ct[0])
                amount = int(nums_ct[1])
            else:
                amount = int(nums_ct[0])
                receiver_id = int(nums_ct[1])
            do_transfer(uid, chat_id, receiver_id, amount, first_name)
            return True
        if len(nums_ct) == 1:
            send_message(chat_id,
                         "❌ ID گیرنده رو هم بنویس:\n"
                         "`کارت به کارت 123456789 5000`", safe=False)
            return True
        send_message(chat_id,
                     "💳 *کارت به کارت*\n━━━━━━━━━━━━━━━\n\n"
                     "`کارت به کارت ID مبلغ`\n\n"
                     "💸 کمیسیون: ۲٪\n"
                     "⚠️ حداقل: ۵۰۰ | حداکثر: ۵۰,۰۰۰", safe=False)
        return True

    if t.startswith("تاریخچه کارت"):
        do_transfer_history(uid, chat_id); return True

    # ========== کلن ==========
    if t.startswith("کلن"):
        body = t[3:].strip()
        if body.startswith("بساز") or body.startswith("ساخت"):
            name = body.replace("بساز", "").replace("ساخت", "").strip()
            if not name:
                send_message(chat_id, "مثال: `کلن بساز آتش‌نشانان`", safe=False); return True
            do_clan_create(uid, chat_id, name); return True
        if body.startswith("عضو شو"):
            name = body.replace("عضو شو", "").strip()
            if not name:
                send_message(chat_id, "مثال: `کلن عضو شو آتش‌نشانان`", safe=False); return True
            do_clan_join(uid, chat_id, name); return True
        if body.startswith("خروج") or body.startswith("ترک"):
            do_clan_leave(uid, chat_id); return True
        if body.startswith("من") or body.startswith("اطلاعات") or body == "":
            do_clan_info(uid, chat_id); return True
        if body.startswith("لیست") or body.startswith("رتبه"):
            do_clan_top(chat_id); return True
        if body.startswith("اهدا") or body.startswith("کمک"):
            nums2 = re.findall(r'\d+', body)
            if not nums2:
                send_message(chat_id, "مثال: `کلن اهدا ۵۰۰۰`", safe=False); return True
            do_clan_donate(uid, chat_id, int(nums2[0])); return True
        send_message(chat_id,
                     "🏰 *کلن:*\n\n"
                     "`کلن بساز [اسم]`\n`کلن عضو شو [اسم]`\n"
                     "`کلن من`\n`کلن لیست`\n`کلن اهدا ۵۰۰۰`\n`کلن خروج`", safe=False)
        return True

    # ========== راهنما ==========
    if t.startswith("راهنما") or t == "کمک":
        send_message(chat_id,
                     "📋 *دستورات بازی*\n━━━━━━━━━━━━━━━\n\n"
                     "🛒 `خرید آرد ۵` | `خرید پنیر ۳` | `خرید ادویه ۳`\n"
                     "🍳 `آشپزی ساده` | `آشپزی پنیری` | `آشپزی دلوکس`\n"
                     "💰 `فروش همه`\n"
                     "🎁 `جایزه روزانه`\n"
                     "🎰 `گردونه شانس`\n"
                     "⚙️ `آپگرید تنور`\n"
                     "👤 `پروفایل` | `رتبه`\n"
                     "🔔 `مشتری` | `تحویل بده`\n"
                     "🎯 `ماموریت`\n\n"
                     "🏦 *بانک:* `بانک` | `بانک سرمایه ۵۰۰۰`\n"
                     "🎰 *کازینو:* `کازینو ۵۰۰۰ شیر`\n"
                     "🎁 *جعبه:* `جعبه` (۲۰۰۰)\n"
                     "⚡ *بوستر:* `بوستر بخر`\n"
                     "🎫 *لاتاری:* `لاتاری` | `لاتاری بخر`\n"
                     "🎓 *مهارت:* `مهارت‌ها` | `مهارت بخر cook`\n"
                     "🐔 *پت:* `پت` | `پت بخر` | `پت غذا بده`\n"
                     "🎁 *هدیه:* `هدیه ID مبلغ`\n"
                     "🔔 *یادآور:* `یادآور ۱۰m جلسه`\n"
                     "🎟 *کد:* `کد WELCOME`\n"
                     "💳 *کارت:* `کارت به کارت ID مبلغ`\n\n"
                     "🏰 `کلن بساز [اسم]` | `کلن من` | `کلن لیست`\n\n"
                     "⚔️ *دوئل:* روی حریف ریپلای کن: `دوئل ۵۰۰۰`", safe=False)
        return True

    return False


# ==================== پیوی ====================
def handle_private(msg, uid, chat_id, first_name, username, text):
    if text == "/start":
        clear_join_cache(uid)
    if text == "/cancel":
        clear_state(uid)
        send_message(chat_id, "✅ لغو شد.", PRIVATE_KB(uid))
        return
    if text == "/check":
        clear_join_cache(uid)
        if is_joined(uid, use_cache=False):
            send_message(chat_id, "✅ عضویتت تایید شد!", PRIVATE_KB(uid))
        else:
            send_join_pm(uid, first_name, force=True)
        return
    if not is_joined(uid):
        send_join_pm(uid, first_name, force=(text == "/start"))
        return
    if not get_player(uid):
        create_player(uid, first_name, username)
    p = get_player(uid)

    if text == "/start":
        event_line = ""
        if get_today_event() != "normal":
            event_line = f"\n\n{get_today_event_desc()}"
        send_message(chat_id,
                     f"🍔 سلام {first_name}!\n━━━━━━━━━━━━━━━\n"
                     f"خوش اومدی به ربات *فلافل فروشی*\n\n"
                     f"📌 *بخش‌ها:*\n"
                     f"🛒 فروشگاه | 🏦 بانک | 🎰 کازینو\n"
                     f"🎫 لاتاری | 🎓 مهارت | 🐔 پت\n"
                     f"⚡ بوستر | 💳 کارت به کارت\n\n"
                     f"🎮 *بازی:* من رو به گروه اضافه کن و `/game` بزن!{event_line}\n\n"
                     f"از منوی پایین شروع کن 👇", PRIVATE_KB(uid), safe=False)
        return

    if text == "/help" or text == "📖 راهنما":
        send_message(chat_id,
                     "📖 *راهنمای کامل*\n━━━━━━━━━━━━━━━\n\n"
                     "🎮 *بازی توی گروه:*\n"
                     "من رو به گروه اضافه کن، ادمین کن، بعد `/game` بزن.\n\n"
                     "دستورات: `راهنما` رو بزن توی گروه.\n\n"
                     "🛒 *توی این بات:* فروشگاه، بانک، کازینو، لاتاری، مهارت، پت",
                     PRIVATE_KB(uid), safe=False)
        return

    if text == "/myid":
        send_message(chat_id, f"🆔 آیدی شما: `{uid}`", PRIVATE_KB(uid), safe=False)
        return

    if text == "/version" or text == "نسخه":
        send_message(chat_id,
                     f"📦 *{SOURCE_NAME}*\n"
                     f"🔢 نسخه: `{VERSION}`\n"
                     f"🛠 حالت: {'Debug' if DEBUG else 'Production'}",
                     PRIVATE_KB(uid), safe=False)
        return

    if text in ("💰 دونیت", "/donate"):
        send_message(chat_id,
                     f"💰 *دونیت*\n━━━━━━━━━━━━━━━\n\n"
                     f"شماره کارت:\n`{CARD_NUMBER}`\n\n"
                     f"به نام: *{CARD_OWNER}*\n\n❤️ ممنون!", PRIVATE_KB(uid), safe=False)
        return

    if text in ("🏦 بانک", "/bank", "🏦 موجودی"):
        do_bank(uid, chat_id, first_name); return

    if text == "📊 راهنما":
        send_message(chat_id,
                     "📊 *راهنمای بانک*\n━━━━━━━━━━━━━━━\n\n"
                     "💰 `بانک واریز ۵۰۰۰`\n"
                     "💵 `بانک برداشت ۵۰۰۰`\n"
                     "📈 `بانک سرمایه ۵۰۰۰`\n"
                     "🔙 `بانک پایان ۵۰۰۰`\n"
                     "🎁 `بانک جمع`\n\n"
                     "📊 سود روزانه: *۲۰٪*", BANK_KB(), safe=False)
        return

    if text == "🎰 کازینو":
        send_message(chat_id,
                     "🎰 *کازینو*\n━━━━━━━━━━━━━━━\n\n"
                     "`کازینو ۵۰۰۰ شیر`\n"
                     "`کازینو ۵۰۰۰ خط`\n\n"
                     "💡 برد = ۲ برابر!", PRIVATE_KB(uid), safe=False)
        return

    if text == "🎁 جعبه شانس":
        do_mystery_box(uid, chat_id); return

    if text == "⚡ بوستر":
        do_booster(uid, chat_id); return

    if text == "🎫 لاتاری":
        do_lottery_panel(uid, chat_id); return

    if text == "🎓 مهارت‌ها":
        do_skills_panel(uid, chat_id); return

    if text == "🐔 پت":
        do_pet_panel(uid, chat_id); return

    if text == "🔔 یادآور":
        send_message(chat_id,
                     "🔔 *یادآور*\n━━━━━━━━━━━━━━━\n\n"
                     "`یادآور ۱۰m جلسه`\n"
                     "`یادآور ۱h تماس`\n"
                     "`یادآور لیست`",
                     PRIVATE_KB(uid), safe=False)
        return

    if text == "💳 کارت به کارت" or text == "/transfer":
        send_message(chat_id,
                     "💳 *کارت به کارت*\n━━━━━━━━━━━━━━━\n\n"
                     "`کارت به کارت ID مبلغ`\n"
                     "مثال: `کارت به کارت 1355544502 5000`\n\n"
                     "💸 کمیسیون: ۲٪\n"
                     "⚠️ حداقل: ۵۰۰ | حداکثر: ۵۰,۰۰۰\n\n"
                     "📜 `تاریخچه کارت`", PRIVATE_KB(uid), safe=False)
        return

    if text in ("👤 پروفایل من", "/profile"):
        do_profile(uid, chat_id, first_name); return

    if text in ("🛒 فروشگاه", "/shop"):
        rows = []
        for key, pkg in SHOP_PACKAGES.items():
            rows.append([{"text": f"{pkg['name']} — {pkg['coins']:,} سکه / {pkg['price']:,} تومان",
                          "callback_data": f"shop:{key}"}])
        send_message(chat_id,
                     "🛒 *فروشگاه*\n━━━━━━━━━━━━━━━\n\n"
                     "پکیج‌های سکه:\n\n"
                     "1️⃣ انتخاب\n2️⃣ واریز\n3️⃣ رسید\n"
                     "4️⃣ رهگیری\n5️⃣ تایید ادمین\n\n👇",
                     {"inline_keyboard": rows}, safe=False)
        return

    if text == "💳 خریدهای من":
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT id, package_key, coins, price, status FROM shop_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (uid,))
            rows = c.fetchall()
        finally:
            close(conn)
        if not rows:
            send_message(chat_id, "هنوز خریدی نداری.", PRIVATE_KB(uid)); return
        statuses = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
        txt = "💳 *خریدهای من*\n━━━━━━━━━━━━━━━\n"
        for r in rows:
            pkg = SHOP_PACKAGES.get(r["package_key"], {"name": r["package_key"]})
            txt += f"• {pkg['name']} — {r['coins']:,} — {statuses.get(r['status'], r['status'])}\n"
        send_message(chat_id, txt, PRIVATE_KB(uid), safe=False)
        return

    if (text in ("👑 پنل ادمین", "/admin")) and is_admin(uid):
        show_admin_panel(chat_id, uid); return

    if text == "🔙 بازگشت":
        send_message(chat_id, "منوی اصلی:", PRIVATE_KB(uid)); return

    if is_admin(uid) and handle_admin_text(chat_id, uid, text):
        return

    state, data = get_state(uid)
    if state and handle_shop_state(chat_id, uid, first_name, text, msg, state, data):
        return

    if parse_text_command(uid, chat_id, first_name, username, text):
        return

    send_message(chat_id, "از منوی پایین استفاده کن 👇", PRIVATE_KB(uid))


# ==================== ادمین ====================
def show_admin_panel(chat_id, uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) c FROM shop_orders WHERE status='pending'")
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
                 f"👑 *پنل ادمین*\n━━━━━━━━━━━━━━━\n"
                 f"📥 سفارشات: {pending}\n"
                 f"👥 بازیکن‌ها: {tp}\n"
                 f"💰 مجموع پول: {format_money(total_money)}\n"
                 f"📈 مجموع درآمد: {format_money(total_earned)}\n\n"
                 f"💡 `ADDMONEY ID مبلغ` | `CARD ID مبلغ`\n"
                 f"`SUB ID مبلغ` | `RESET ID` | `RESETALL`\n"
                 f"`ALL متن` | `کد بساز CODE مبلغ تعداد`",
                 ADMIN_KB(), safe=False)


def show_pending_orders(chat_id, uid):
    conn = db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM shop_orders WHERE status='pending' ORDER BY created_at DESC LIMIT 10")
        rows = c.fetchall()
    finally:
        close(conn)
    if not rows:
        send_message(chat_id, "📥 هیچ سفارشی نیست.", ADMIN_KB()); return
    for r in rows:
        pkg = SHOP_PACKAGES.get(r["package_key"], {"name": r["package_key"]})
        user = get_player(r["user_id"]) or {}
        txt = (f"📥 *سفارش #{r['id']}*\n"
               f"👤 {user.get('first_name', '?')} (`{r['user_id']}`)\n"
               f"📦 {pkg['name']}\n💰 {format_money(r['price'])}\n"
               f"🪙 {format_money(r['coins'])}\n"
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
            c.execute("SELECT COUNT(*) c FROM banks WHERE invested > 0")
            investors = c.fetchone()["c"]
            c.execute("SELECT COUNT(*) c FROM discount_codes")
            codes = c.fetchone()["c"]
            c.execute("SELECT COUNT(*) c FROM boosters WHERE expires_at > ?", (time.time(),))
            boosts = c.fetchone()["c"]
            c.execute("SELECT COUNT(*) c FROM lottery WHERE week=?", (get_week_key(),))
            lottery_p = c.fetchone()["c"]
        finally:
            close(conn)
        send_message(chat_id,
                     f"📊 *آمار کل*\n━━━━━━━━━━━━━━━\n"
                     f"👥 بازیکن‌ها: {t}\n"
                     f"📈 درآمد کل: {format_money(earned)}\n"
                     f"⚔️ دوئل: {duels}\n"
                     f"🏰 کلن: {clans}\n"
                     f"📈 سرمایه‌گذار: {investors}\n"
                     f"🎟 کد: {codes}\n"
                     f"⚡ بوستر: {boosts}\n"
                     f"🎫 لاتاری: {lottery_p}",
                     ADMIN_KB(), safe=False)
        return True

    if text == "💰 افزودن پول":
        send_message(chat_id, "`ADDMONEY ID مبلغ` (سقف ۱۰,۰۰۰)", ADMIN_KB(), safe=False); return True
    if text == "💳 کارت به کارت ادمین":
        send_message(chat_id, "`CARD ID مبلغ` (سقف ۱۰,۰۰۰)", ADMIN_KB(), safe=False); return True
    if text == "🎟 کد تخفیف":
        send_message(chat_id, "`کد بساز CODE مبلغ تعداد`", ADMIN_KB(), safe=False); return True
    if text == "🗑 ریست کلی":
        send_message(chat_id, "⚠️ برای تایید: `RESETALL`", ADMIN_KB(), safe=False); return True
    if text == "🎁 هدیه همگانی":
        send_message(chat_id, "`GIFT مبلغ`", ADMIN_KB(), safe=False); return True
    if text == "📢 پیام همگانی":
        send_message(chat_id, "`ALL متن`", ADMIN_KB(), safe=False); return True

    parts = text.split()
    if not parts:
        return False

    if parts[0].upper() == "ADD" and len(parts) >= 3 and parts[1].isdigit():
        try:
            amt = int(parts[2])
        except Exception:
            return True
        do_admin_add(int(parts[1]), amt, uid, chat_id, "اضافه توسط ادمین")
        return True

    if parts[0].upper() == "SUB" and len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
        do_admin_add(int(parts[1]), -int(parts[2]), uid, chat_id, "کم کردن")
        return True

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

    if parts[0].upper() == "UNDO" and len(parts) >= 2 and parts[1].isdigit():
        do_admin_undo(int(parts[1]), uid, chat_id); return True

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
                    c.execute(f"DELETE FROM {table} WHERE {col}=?", (tid,))
                except Exception:
                    pass
            try:
                c.execute("DELETE FROM duels WHERE challenger_id=? OR opponent_id=?", (tid, tid))
                c.execute("DELETE FROM admin_txns WHERE target_id=?", (tid,))
                c.execute("DELETE FROM card_transfers WHERE sender_id=? OR receiver_id=?", (tid, tid))
            except Exception:
                pass
            conn.commit()
        finally:
            close(conn)
        send_message(chat_id, f"✅ `{tid}` ریست شد.", ADMIN_KB(), safe=False)
        return True

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
        send_message(chat_id, f"✅ به {sent} نفر ارسال شد.", ADMIN_KB()); return True

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
                log_txn(x, "admin_gift", amt, "هدیه همگانی")
                cnt += 1
            time.sleep(0.05)
        send_message(chat_id, f"✅ به {cnt} نفر هدیه داده شد.", ADMIN_KB()); return True

    return False


# ==================== Shop State ====================
def handle_shop_state(chat_id, uid, first_name, text, msg, state, data):
    if state == "await_receipt":
        photos = msg.get("photo")
        if not photos:
            send_message(chat_id, "❌ *عکس رسید* رو بفرست.", PRIVATE_KB(uid))
            return True
        file_id = photos[-1].get("file_id") if isinstance(photos, list) else photos.get("file_id")
        pkg = SHOP_PACKAGES.get(data.get("pkg", ""), {})
        conn = db()
        try:
            c = conn.cursor()
            c.execute("INSERT INTO shop_orders (user_id, package_key, coins, price, receipt_file_id, created_at) VALUES (?,?,?,?,?,?)",
                      (uid, data.get("pkg"), pkg.get("coins", 0), pkg.get("price", 0), file_id, time.time()))
            oid = c.lastrowid
            conn.commit()
        finally:
            close(conn)
        set_state(uid, "await_tracking", {"order_id": oid})
        send_message(chat_id, "✅ رسید دریافت شد.\n\n🔢 حالا *شماره رهگیری* رو بفرست:", PRIVATE_KB(uid))
        return True

    if state == "await_tracking":
        if not text or text.startswith("/"):
            send_message(chat_id, "❌ شماره رهگیری رو به صورت متن بفرست.")
            return True
        oid = data.get("order_id")
        conn = db()
        try:
            c = conn.cursor()
            c.execute("UPDATE shop_orders SET tracking_code=? WHERE id=?", (text.strip(), oid))
            c.execute("SELECT * FROM shop_orders WHERE id=?", (oid,))
            order = dict(c.fetchone())
            conn.commit()
        finally:
            close(conn)
        clear_state(uid)
        send_message(chat_id,
                     f"✅ *سفارش ثبت شد!*\n🆔 #{oid}\n"
                     f"📦 {SHOP_PACKAGES.get(order['package_key'], {}).get('name', '?')}\n"
                     f"💰 {format_money(order['price'])}\n\n⏳ منتظر تایید ادمین.", PRIVATE_KB(uid), safe=False)
        notify_admins_order(order, uid, first_name)
        return True
    return False


def notify_admins_order(order, uid, first_name):
    pkg = SHOP_PACKAGES.get(order["package_key"], {"name": order["package_key"]})
    txt = (f"📥 *سفارش جدید!*\n🆔 #{order['id']}\n"
           f"👤 {first_name} (`{uid}`)\n"
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


# ==================== گروه ====================
def handle_group(msg, uid, chat_id, first_name, username, text):
    if not is_joined(uid):
        send_join_pm(uid, first_name)
        return

    if not get_player(uid):
        create_player(uid, first_name, username)

    if text in ("/game", "/play"):
        p = get_player(uid)
        send_message(chat_id,
                     f"🎮 *منوی بازی فلافل*\n━━━━━━━━━━━━━━━\n"
                     f"💰 {format_money(p['money'])} | ⭐ {p['level']}\n"
                     f"🍽 {count_falafel(p)} فلافل\n\n"
                     f"روی هر دکمه بزن 👇", GROUP_KB(), safe=False)
        return

    if text.startswith("/"):
        if text == "/version":
            send_message(chat_id, f"📦 نسخه: `{VERSION}`", safe=False); return
        if text == "/help":
            send_message(chat_id,
                         "📋 *دستورات:*\n\n"
                         "`خرید آرد ۵` | `آشپزی ساده` | `فروش همه`\n"
                         "`جایزه روزانه` | `گردونه شانس` | `آپگرید تنور`\n"
                         "`پروفایل` | `رتبه` | `مشتری` | `تحویل بده`\n"
                         "`ماموریت` | `کلن بساز [اسم]`\n"
                         "`بانک` | `کازینو ۵۰۰۰ شیر` | `بوستر بخر`\n"
                         "`لاتاری` | `مهارت‌ها` | `پت`\n"
                         "`کارت به کارت ID مبلغ`\n\n"
                         "برای منو: `/game`", safe=False)
            return
        return

    if text.startswith("دوئل") or text.startswith("مبارزه"):
        reply = msg.get("reply_to_message")
        if not reply:
            send_message(chat_id, "❌ روی پیام حریف ریپلای کن و بنویس: `دوئل ۵۰۰۰`", safe=False)
            return
        opponent = reply.get("from") or {}
        op_id = opponent.get("id")
        if not op_id:
            send_message(chat_id, "❌ حریف پیدا نشد."); return
        nums = re.findall(r'\d+', text)
        if not nums:
            send_message(chat_id, "❌ مبلغ رو بنویس. مثال: `دوئل ۵۰۰۰`", safe=False)
            return
        amount = int(nums[0])
        do_duel(uid, chat_id, op_id, amount)
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
            send_message(uid, "✅ عضویت تایید شد!\nحالا /start بزن.", PRIVATE_KB(uid))
        else:
            answer_callback(cb["id"], "❌ هنوز عضو نشدی!", True)
        return

    if data.startswith("appr:") or data.startswith("rej:"):
        if not is_admin(uid):
            answer_callback(cb["id"], "⛔ دسترسی نداری.", True); return
        is_appr = data.startswith("appr:")
        oid = int(data.split(":")[1])
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM shop_orders WHERE id=?", (oid,))
            r = c.fetchone()
            if not r:
                answer_callback(cb["id"], "❌ سفارش نیست.", True); return
            order = dict(r)
            if order["status"] != "pending":
                answer_callback(cb["id"], "قبلاً بررسی شده.", True); return
            new_status = "approved" if is_appr else "rejected"
            c.execute("UPDATE shop_orders SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
                      (new_status, uid, time.time(), oid))
            conn.commit()
        finally:
            close(conn)
        if is_appr:
            tp = get_player(order["user_id"])
            if tp:
                update_player(order["user_id"], money=tp["money"] + order["coins"])
                log_txn(order["user_id"], "shop", order["coins"], "خرید")
            try:
                send_message(order["user_id"],
                             f"✅ *سفارش #{oid} تایید شد!*\n🪙 {format_money(order['coins'])} سکه اضافه شد.",
                             PRIVATE_KB(order["user_id"]), safe=False)
            except Exception:
                pass
            answer_callback(cb["id"], "✅ تایید شد", True)
        else:
            try:
                send_message(order["user_id"], f"❌ *سفارش #{oid} رد شد.*", safe=False)
            except Exception:
                pass
            answer_callback(cb["id"], "❌ رد شد", True)
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
            send_message(m_chat, "🎰 *کازینو*\n\n`کازینو ۵۰۰۰ شیر`\n`کازینو ۵۰۰۰ خط`", safe=False); return
        if sub == "boost":
            answer_callback(cb["id"])
            send_message(m_chat, "⚡ *بوستر*\n\n`بوستر بخر` — ۵,۰۰۰ تومان", safe=False); return
        if sub in GUIDES:
            answer_callback(cb["id"]); send_message(m_chat, GUIDES[sub], safe=False); return
        answer_callback(cb["id"]); return

    if data.startswith("shop:"):
        if not is_joined(uid):
            send_join_pm(uid, fn)
            answer_callback(cb["id"], "🔒 اول عضو شو", True); return
        pkg_key = data.split(":")[1]
        pkg = SHOP_PACKAGES.get(pkg_key)
        if not pkg:
            answer_callback(cb["id"], "❌ نامعتبر", True); return
        set_state(uid, "await_receipt", {"pkg": pkg_key})
        answer_callback(cb["id"])
        send_message(uid,
                     f"🛒 *خرید {pkg['name']}*\n━━━━━━━━━━━━━━━\n"
                     f"🪙 {format_money(pkg['coins'])} سکه\n💰 {format_money(pkg['price'])} تومان\n\n"
                     f"💳 *کارت:*\n`{CARD_NUMBER}`\n"
                     f"به نام: *{CARD_OWNER}*\n\n"
                     f"1️⃣ واریز کن\n2️⃣ عکس رسید بفرست\n3️⃣ شماره رهگیری بفرست\n\n"
                     f"📸 *عکس رسید:*",
                     {"inline_keyboard": [[{"text": "❌ انصراف", "callback_data": "cancel_shop"}]]}, safe=False)
        return

    if data == "cancel_shop":
        clear_state(uid)
        try:
            api("deleteMessage", {"chat_id": m_chat, "message_id": m_id})
        except Exception:
            pass
        answer_callback(cb["id"], "لغو شد")
        send_message(uid, "لغو شد.", PRIVATE_KB(uid))
        return

    answer_callback(cb["id"])


# ==================== Skip & Router ====================
def skip_old_updates():
    """پاک کردن پیام‌های قدیمی — با timeout کوتاه و try/except."""
    if not SKIP_OLD_UPDATES:
        return None
    log("🧹 پاک‌سازی پیام‌های قدیمی...")
    try:
        r = api("getUpdates", {"offset": -1, "timeout": 0, "limit": 1},
                req_timeout=(10, 15))
        if r.get("ok"):
            updates = r.get("result", [])
            if updates:
                last_id = updates[-1]["update_id"]
                log(f"🧹 آخرین update ID: {last_id}")
                return last_id + 1
        else:
            log(f"⚠️ skip response: {str(r)[:100]}")
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
        # مشتری تصادفی
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT user_id FROM players WHERE (active_customer='' OR customer_expire < ?) AND last_daily > ? LIMIT 5",
                      (time.time(), time.time() - 3600))
            candidates = [r["user_id"] for r in c.fetchall()]
        finally:
            close(conn)
        for x in candidates:
            if is_joined(x) and random.random() < 0.15:
                cust = spawn_customer(x)
                if cust:
                    send_message(x, customer_text(cust), safe=False)

        # یادآورها
        conn = db()
        try:
            c = conn.cursor()
            c.execute("SELECT id, user_id, chat_id, text FROM reminders WHERE remind_at <= ?", (time.time(),))
            rms = c.fetchall()
            for r in rms:
                try:
                    send_message(r["chat_id"], f"🔔 *یادآور:*\n{r['text']}")
                except Exception:
                    pass
                c.execute("DELETE FROM reminders WHERE id=?", (r["id"],))
            conn.commit()
        finally:
            close(conn)

        # قرعه‌کشی لاتاری
        try:
            draw_lottery()
        except Exception:
            pass

        # پت گرسنه
        conn = db()
        try:
            c = conn.cursor()
            c.execute("UPDATE players SET pet_hunger=MAX(0, pet_hunger-1) WHERE pet_level>0")
            conn.commit()
        finally:
            close(conn)
    except Exception:
        log_err()


def run():
    init_db()
    print("━" * 55, flush=True)
    print("  بات زیر مجموعه نوین سازان bolight", flush=True)
    print("━" * 55, flush=True)
    print(f"  {SOURCE_NAME}", flush=True)
    print(f"  📦 نسخه: {VERSION}", flush=True)
    print(f"  🛠 حالت: {'Debug' if DEBUG else 'Production'}", flush=True)
    print("━" * 55, flush=True)
    log(f"👑 ادمین‌ها: {ADMIN_IDS}")
    log(f"🔒 کانال: {get_forced_channel()}")

    # 🆕 اجرای وب‌سرور در thread جدا
    threading.Thread(target=run_web, daemon=True).start()

    # 🆕 skip با try/except
    offset = None
    try:
        offset = skip_old_updates()
    except Exception as e:
        log(f"⚠️ skip_old_updates failed: {e}")

    log("✅ ربات با موفقیت اجرا شد. منتظر پیام‌ها...")
    last_bg = 0
    while True:
        try:
            updates = get_updates(offset, timeout=POLLING_TIMEOUT)
            if not updates.get("ok"):
                time.sleep(2)
                continue
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
