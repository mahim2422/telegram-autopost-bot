# =========================================================
# Telegram Auto Post Scheduler Bot
# FINAL – ALL IN ONE – Railway Stable (Webhook)
# =========================================================

import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from aiohttp import web

from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup

# =========================================================
# ENV CONFIG
# =========================================================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

PORT = int(os.environ.get("PORT", 8080))

# =========================================================
# PYROGRAM CLIENT
# =========================================================
app = Client(
    "schedule_poster",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1
)

# =========================================================
# DATABASE
# =========================================================
db = sqlite3.connect("bot.db", check_same_thread=False)
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
    schedule_type TEXT,
    run_at TEXT
)
""")

db.commit()

# =========================================================
# KEYBOARDS
# =========================================================
USER_MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add Post", "📄 My Posts"],
        ["⏰ Add Schedule", "📆 My Schedules"],
        ["🗑 Delete Schedule"]
    ],
    resize_keyboard=True
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add User", "📋 User List"]
    ],
    resize_keyboard=True
)

# =========================================================
# HELPERS
# =========================================================
def is_active(uid):
    row = cur.execute(
        "SELECT expire_at, status FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if not row:
        return False
    expire, status = row
    if status != "active":
        return False
    return datetime.fromisoformat(expire) > datetime.utcnow()

def add_user(uid, days):
    expire = datetime.utcnow() + timedelta(days=days)
    cur.execute(
        "REPLACE INTO users VALUES (?, ?, ?)",
        (uid, expire.isoformat(), "active")
    )
    db.commit()

# =========================================================
# START
# =========================================================
@app.on_message(filters.command("start"))
async def start(_, m):
    uid = m.from_user.id

    if uid == ADMIN_ID:
        await m.reply(
            f"👑 Admin Panel\nID: `{uid}`",
            reply_markup=ADMIN_MENU
        )
        return

    if not is_active(uid):
        await m.reply(
            "❌ Access Denied\nContact admin for access."
        )
        return

    await m.reply(
        f"✅ Bot Active\nYour ID: `{uid}`",
        reply_markup=USER_MENU
    )

# =========================================================
# ADD POST
# =========================================================
@app.on_message(filters.regex("^➕ Add Post$"))
async def ask_post(_, m):
    await m.reply("Send post text now.")

@app.on_message(filters.text & ~filters.command("start"))
async def save_post(_, m):
    uid = m.from_user.id

    if uid != ADMIN_ID and not is_active(uid):
        return

    if m.reply_to_message and "Send post text" in m.reply_to_message.text:
        cur.execute(
            "INSERT INTO posts (user_id, text) VALUES (?, ?)",
            (uid, m.text)
        )
        db.commit()
        await m.reply("✅ Post saved", reply_markup=USER_MENU)

# =========================================================
# LIST POSTS
# =========================================================
@app.on_message(filters.regex("^📄 My Posts$"))
async def my_posts(_, m):
    rows = cur.execute(
        "SELECT id, text FROM posts WHERE user_id=?",
        (m.from_user.id,)
    ).fetchall()

    if not rows:
        await m.reply("No posts found.")
        return

    msg = "📄 Your Posts:\n\n"
    for pid, text in rows:
        msg += f"{pid} → {text[:40]}...\n"

    await m.reply(msg)

# =========================================================
# ADD SCHEDULE
# =========================================================
@app.on_message(filters.regex("^⏰ Add Schedule$"))
async def schedule_help(_, m):
    await m.reply(
        "Format:\n\n"
        "`POST_ID | chat_ids | once/daily/weekly | YYYY-MM-DD HH:MM`\n\n"
        "Example:\n"
        "`1 | -100xxxx | daily | 2026-02-01 10:00`"
    )

@app.on_message(filters.text & filters.regex(r"\|"))
async def save_schedule(_, m):
    uid = m.from_user.id
    if uid != ADMIN_ID and not is_active(uid):
        return

    try:
        post_id, chats, stype, run_at = [x.strip() for x in m.text.split("|")]
        datetime.fromisoformat(run_at)

        cur.execute("""
        INSERT INTO schedules 
        (user_id, post_id, chat_ids, schedule_type, run_at)
        VALUES (?, ?, ?, ?, ?)
        """, (uid, int(post_id), chats, stype, run_at))

        db.commit()
        await m.reply("✅ Schedule added")

    except:
        await m.reply("❌ Invalid format")

# =========================================================
# LIST SCHEDULES
# =========================================================
@app.on_message(filters.regex("^📆 My Schedules$"))
async def list_schedules(_, m):
    rows = cur.execute(
        "SELECT id, post_id, schedule_type, run_at FROM schedules WHERE user_id=?",
        (m.from_user.id,)
    ).fetchall()

    if not rows:
        await m.reply("No schedules.")
        return

    msg = "📆 Schedules:\n\n"
    for sid, pid, st, rt in rows:
        msg += f"{sid} → Post {pid} | {st} | {rt}\n"

    await m.reply(msg)

# =========================================================
# DELETE SCHEDULE
# =========================================================
@app.on_message(filters.regex("^🗑 Delete Schedule$"))
async def del_help(_, m):
    await m.reply("Send Schedule ID to delete")

@app.on_message(filters.text & filters.regex(r"^\d+$"))
async def delete_schedule(_, m):
    sid = int(m.text)
    cur.execute(
        "DELETE FROM schedules WHERE id=? AND user_id=?",
        (sid, m.from_user.id)
    )
    db.commit()
    await m.reply("🗑 Schedule deleted")

# =========================================================
# SCHEDULER LOOP
# =========================================================
async def scheduler_loop():
    while True:
        now = datetime.utcnow()

        rows = cur.execute(
            "SELECT id, post_id, chat_ids, schedule_type, run_at FROM schedules"
        ).fetchall()

        for sid, pid, chats, stype, run_at in rows:
            run_time = datetime.fromisoformat(run_at)
            if now >= run_time:
                text = cur.execute(
                    "SELECT text FROM posts WHERE id=?",
                    (pid,)
                ).fetchone()

                if text:
                    for chat in chats.split(","):
                        try:
                            await app.send_message(int(chat), text[0])
                            await asyncio.sleep(1)
                        except:
                            pass

                if stype == "once":
                    cur.execute("DELETE FROM schedules WHERE id=?", (sid,))
                elif stype == "daily":
                    cur.execute(
                        "UPDATE schedules SET run_at=? WHERE id=?",
                        ((run_time + timedelta(days=1)).isoformat(), sid)
                    )
                elif stype == "weekly":
                    cur.execute(
                        "UPDATE schedules SET run_at=? WHERE id=?",
                        ((run_time + timedelta(days=7)).isoformat(), sid)
                    )
                db.commit()

        await asyncio.sleep(30)

# =========================================================
# WEBHOOK
# =========================================================
async def webhook_handler(request):
    data = await request.json()
    await app.process_update(data)
    return web.Response(text="ok")

# =========================================================
# MAIN
# =========================================================
async def main():
    await app.start()

    railway_url = os.environ["RAILWAY_STATIC_URL"]
    webhook_url = f"https://{railway_url}/webhook"
    await app.bot.set_webhook(webhook_url)

    web_app = web.Application()
    web_app.router.add_post("/webhook", webhook_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    asyncio.create_task(scheduler_loop())

    print("🚀 FULL BOT RUNNING (Railway Stable)")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
