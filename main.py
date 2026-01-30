# =========================
# Telegram Auto Schedule Bot
# FINAL FULL VERSION
# =========================

import os
import asyncio
import sqlite3
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup

# =========================
# ENV CONFIG
# =========================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

ADMIN_IDS = {int(os.environ["ADMIN_ID"])}
ADMIN_USERNAME = "mahim_2422"

DB_NAME = "bot.db"

# =========================
# APP INIT
# =========================
app = Client(
    "schedule_bot",
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
    chat_ids TEXT,
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
        ["⏰ Schedule Post", "📋 My Schedules"],
        ["✏️ Edit Schedule", "❌ Delete Schedule"],
        ["🗑️ Delete Post", "🚀 Send Now"],
        ["📊 Status"]
    ],
    resize_keyboard=True
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add User", "⏳ Extend Plan"],
        ["⛔ Ban User", "📋 User List"]
    ],
    resize_keyboard=True
)

# =========================
# HELPERS
# =========================
def is_active(uid):
    row = cur.execute(
        "SELECT expire_at, status FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()

    if not row:
        return False

    expire, status = row
    return status == "active" and datetime.fromisoformat(expire) > datetime.utcnow()


def schedule_limit(uid):
    # simple plan logic
    if uid in ADMIN_IDS:
        return 999
    return 5


async def run_post(post_id, chat_ids):
    row = cur.execute("SELECT text FROM posts WHERE id=?", (post_id,)).fetchone()
    if not row:
        return

    text = row[0]
    for cid in chat_ids.split(","):
        try:
            await app.send_message(int(cid), text)
            await asyncio.sleep(1)
        except Exception as e:
            print("Send error:", e)


def load_schedules():
    rows = cur.execute(
        "SELECT id, post_id, chat_ids, run_at FROM schedules"
    ).fetchall()

    for sid, pid, chats, run_at in rows:
        scheduler.add_job(
            run_post,
            "date",
            run_date=datetime.fromisoformat(run_at),
            args=[pid, chats],
            id=str(sid),
            replace_existing=True
        )

# =========================
# START
# =========================
@app.on_message(filters.command("start"))
async def start(_, m):
    uid = m.from_user.id

    if uid not in ADMIN_IDS and not is_active(uid):
        await m.reply(
            "❌ Access Denied\n\n"
            f"Contact admin: @{ADMIN_USERNAME}"
        )
        return

    if uid in ADMIN_IDS:
        await m.reply("👑 Admin Panel", reply_markup=ADMIN_MENU)
    else:
        await m.reply("✅ Bot is alive!", reply_markup=USER_MENU)

# =========================
# USER: ADD POST
# =========================
@app.on_message(filters.regex("^➕ Add Post$"))
async def add_post(_, m):
    await m.reply("Send post text now.")

@app.on_message(filters.reply & filters.text)
async def save_post(_, m):
    if "Send post text" in m.reply_to_message.text:
        cur.execute(
            "INSERT INTO posts (user_id, text) VALUES (?, ?)",
            (m.from_user.id, m.text)
        )
        db.commit()
        await m.reply("✅ Post saved.", reply_markup=USER_MENU)

# =========================
# USER: MY POSTS
# =========================
@app.on_message(filters.regex("^📩 My Posts$"))
async def my_posts(_, m):
    rows = cur.execute(
        "SELECT id, text FROM posts WHERE user_id=?",
        (m.from_user.id,)
    ).fetchall()

    if not rows:
        await m.reply("No posts found.")
        return

    msg = "📩 Your Posts:\n\n"
    for i, t in rows:
        msg += f"{i}: {t[:40]}...\n"

    await m.reply(msg)

# =========================
# USER: SCHEDULE POST
# =========================
@app.on_message(filters.regex("^⏰ Schedule Post$"))
async def schedule_post(_, m):
    uid = m.from_user.id

    count = cur.execute(
        "SELECT COUNT(*) FROM schedules WHERE user_id=?",
        (uid,)
    ).fetchone()[0]

    if count >= schedule_limit(uid):
        await m.reply("❌ Schedule limit reached.")
        return

    await m.reply(
        "Format:\n"
        "`POST_ID | chat_id1,chat_id2 | YYYY-MM-DD HH:MM`\n"
        "Time must be UTC"
    )

@app.on_message(filters.text & filters.regex(r"\|"))
async def save_schedule(_, m):
    try:
        pid, chats, time_str = [x.strip() for x in m.text.split("|")]
        run_at = datetime.fromisoformat(time_str)

        cur.execute(
            "INSERT INTO schedules (user_id, post_id, chat_ids, run_at) VALUES (?, ?, ?, ?)",
            (m.from_user.id, int(pid), chats, run_at.isoformat())
        )
        db.commit()

        sid = cur.lastrowid

        scheduler.add_job(
            run_post,
            "date",
            run_date=run_at,
            args=[int(pid), chats],
            id=str(sid)
        )

        await m.reply("✅ Scheduled successfully.", reply_markup=USER_MENU)

    except Exception as e:
        await m.reply(f"❌ Error: {e}")

# =========================
# USER: MY SCHEDULES
# =========================
@app.on_message(filters.regex("^📋 My Schedules$"))
async def my_schedules(_, m):
    rows = cur.execute(
        "SELECT id, post_id, run_at FROM schedules WHERE user_id=?",
        (m.from_user.id,)
    ).fetchall()

    if not rows:
        await m.reply("No schedules.")
        return

    msg = "⏰ Your Schedules:\n\n"
    for sid, pid, t in rows:
        msg += f"ID {sid} | Post {pid} | {t}\n"

    await m.reply(msg)

# =========================
# USER: DELETE SCHEDULE
# =========================
@app.on_message(filters.regex("^❌ Delete Schedule$"))
async def delete_schedule(_, m):
    await m.reply("Send Schedule ID to delete.")

@app.on_message(filters.text & filters.regex("^[0-9]+$"))
async def confirm_delete(_, m):
    sid = m.text
    scheduler.remove_job(sid)

    cur.execute("DELETE FROM schedules WHERE id=?", (sid,))
    db.commit()

    await m.reply("✅ Schedule deleted.", reply_markup=USER_MENU)

# =========================
# ADMIN
# =========================
@app.on_message(filters.regex("^➕ Add User$"))
async def admin_add(_, m):
    await m.reply("Send: `user_id days`")

@app.on_message(filters.text & filters.regex(" "))
async def admin_save(_, m):
    if m.from_user.id not in ADMIN_IDS:
        return

    uid, days = m.text.split()
    expire = datetime.utcnow() + timedelta(days=int(days))

    cur.execute(
        "REPLACE INTO users VALUES (?, ?, ?)",
        (int(uid), expire.isoformat(), "active")
    )
    db.commit()

    await m.reply("✅ User added.")

# =========================
# RUN
# =========================
async def main():
    scheduler.start()
    load_schedules()
    await app.start()
    print("Bot is running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
