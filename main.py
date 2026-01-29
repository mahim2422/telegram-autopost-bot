# =========================
# Telegram Auto Post Bot
# FINAL - Single File
# =========================

import asyncio
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup

# =========================
# CONFIG
# =========================
API_ID = 36282843
API_HASH = "23cbadebadb91a0d5883ec428b8a174c"
BOT_TOKEN = "7816845254:AAE_8CxPYPW5koRWGEBDry9jYdwm5sLdrf4"

ADMIN_USERNAME = "mahim_2422"
ADMIN_IDS = {7176443600}  # your Telegram user id(s)

DB_NAME = "bot.db"

# =========================
# INIT
# =========================
app = Client(
    "auto_post_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

scheduler = AsyncIOScheduler()

# =========================
# DATABASE
# =========================
db = sqlite3.connect(DB_NAME, check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    expire_at TEXT,
    status TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    post_id INTEGER,
    targets TEXT,
    type TEXT,
    run_at TEXT
)
""")

db.commit()

# =========================
# KEYBOARDS
# =========================
USER_MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add Post", "📩 My Posts"],
        ["🗑️ Delete Post"],
        ["⏰ Schedule Post", "🚀 Send Now"],
        ["👥 My Groups", "📊 Status"],
        ["📞 Support", "🚪 Logout"]
    ],
    resize_keyboard=True
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add User", "⏳ Set Plan"],
        ["➕ Extend Access", "⛔ Ban User"],
        ["📋 User List", "📊 System Status"]
    ],
    resize_keyboard=True
)

# =========================
# HELPERS
# =========================
def is_active(uid: int) -> bool:
    row = cur.execute(
        "SELECT expire_at, status FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if not row:
        return False
    expire_at, status = row
    if status != "active":
        return False
    if datetime.fromisoformat(expire_at) < datetime.utcnow():
        return False
    return True


def add_user(uid: int, days: int):
    expire = datetime.utcnow() + timedelta(days=days)
    cur.execute(
        "REPLACE INTO users (user_id, expire_at, status) VALUES (?, ?, ?)",
        (uid, expire.isoformat(), "active")
    )
    db.commit()


# =========================
# START
# =========================
@app.on_message(filters.command("start"))
async def start(_, m):
    uid = m.from_user.id

    if uid not in ADMIN_IDS and not is_active(uid):
        await m.reply(
            "❌ Access Denied\n\n"
            "You don't have permission to use this bot.\n\n"
            "📩 Contact admin to buy access:\n"
            f"👉 @{ADMIN_USERNAME}"
        )
        return

    if uid in ADMIN_IDS:
        await m.reply("Welcome Admin 👑", reply_markup=ADMIN_MENU)
    else:
        await m.reply("Welcome 👋", reply_markup=USER_MENU)


# =========================
# USER FEATURES
# =========================
@app.on_message(filters.text & filters.regex("^➕ Add Post$"))
async def add_post(_, m):
    await m.reply("Send me the post text.")
    app.set_parse_mode("markdown")


@app.on_message(filters.text & ~filters.command("start"))
async def handle_text(_, m):
    uid = m.from_user.id

    if not is_active(uid) and uid not in ADMIN_IDS:
        return

    # save post
    if m.reply_to_message and "Send me the post text." in m.reply_to_message.text:
        cur.execute(
            "INSERT INTO posts (user_id, text) VALUES (?, ?)",
            (uid, m.text)
        )
        db.commit()
        await m.reply("✅ Post saved.", reply_markup=USER_MENU)


@app.on_message(filters.text & filters.regex("^📩 My Posts$"))
async def my_posts(_, m):
    uid = m.from_user.id
    rows = cur.execute(
        "SELECT id, text FROM posts WHERE user_id=?",
        (uid,)
    ).fetchall()

    if not rows:
        await m.reply("No posts found.")
        return

    msg = "📩 Your Posts:\n\n"
    for pid, text in rows:
        msg += f"ID {pid}: {text[:40]}...\n"

    await m.reply(msg)


@app.on_message(filters.text & filters.regex("^🚀 Send Now$"))
async def send_now(_, m):
    await m.reply(
        "Reply with:\n\n"
        "`POST_ID | chat_id1,chat_id2`\n\n"
        "Example:\n"
        "`1 | -100xxxxxx,-100yyyyyy`"
    )


@app.on_message(filters.text & filters.regex("^⏰ Schedule Post$"))
async def schedule_post(_, m):
    await m.reply(
        "Reply with:\n\n"
        "`POST_ID | chat_ids | type | datetime`\n\n"
        "type = once / daily / weekly\n"
        "datetime = YYYY-MM-DD HH:MM (UTC)\n\n"
        "Example:\n"
        "`1 | -100xxx | daily | 2026-02-01 10:00`"
    )


# =========================
# ADMIN FEATURES
# =========================
@app.on_message(filters.text & filters.regex("^➕ Add User$"))
async def admin_add_user(_, m):
    if m.from_user.id not in ADMIN_IDS:
        return
    await m.reply("Send user_id and days.\nExample:\n`123456789 30`")


@app.on_message(filters.text & filters.regex("^📋 User List$"))
async def user_list(_, m):
    if m.from_user.id not in ADMIN_IDS:
        return
    rows = cur.execute("SELECT user_id, expire_at, status FROM users").fetchall()
    if not rows:
        await m.reply("No users.")
        return
    msg = "👥 Users:\n\n"
    for u, e, s in rows:
        msg += f"{u} | {s} | {e}\n"
    await m.reply(msg)


# =========================
# SCHEDULER
# =========================
async def run_post(post_id, targets):
    row = cur.execute("SELECT text FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        return
    text = row[0]
    for chat_id in targets.split(","):
        try:
            await app.send_message(int(chat_id), text)
            await asyncio.sleep(2)
        except Exception as e:
            print("Send error:", e)


# =========================
# RUN
# =========================
async def main():
    scheduler.start()
    await app.start()
    print("Bot is running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())