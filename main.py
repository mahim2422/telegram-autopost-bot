import os
import asyncio
import sqlite3
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup

# ================== CONFIG ==================
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

# ================== BOT ==================
app = Client(
    "schedule_poster",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================== DATABASE ==================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    expire_at TEXT
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
    chat_id TEXT,
    schedule_type TEXT,
    run_at TEXT
)
""")

db.commit()

# ================== KEYBOARD ==================
MENU = ReplyKeyboardMarkup(
    [
        ["➕ Add Post", "📄 My Posts"],
        ["⏰ Add Schedule", "📆 My Schedules"],
        ["🗑 Delete Schedule"]
    ],
    resize_keyboard=True
)

# ================== HELPERS ==================
def is_active(uid):
    row = cur.execute(
        "SELECT expire_at FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if not row:
        return False
    return datetime.fromisoformat(row[0]) > datetime.utcnow()

# ================== START ==================
@app.on_message(filters.command("start"))
async def start(_, m):
    uid = m.from_user.id

    if uid == ADMIN_ID:
        await m.reply(f"👑 Admin\nID: `{uid}`", reply_markup=MENU)
        return

    if not is_active(uid):
        await m.reply("❌ Access denied")
        return

    await m.reply(
        f"✅ Bot is alive!\nYour ID: `{uid}`",
        reply_markup=MENU
    )

# ================== ADD POST ==================
@app.on_message(filters.regex("^➕ Add Post$"))
async def ask_post(_, m):
    await m.reply("Send post text now")

@app.on_message(filters.text & ~filters.command("start"))
async def save_post(_, m):
    if m.reply_to_message and "Send post text" in m.reply_to_message.text:
        cur.execute(
            "INSERT INTO posts (user_id, text) VALUES (?, ?)",
            (m.from_user.id, m.text)
        )
        db.commit()
        await m.reply("✅ Post saved", reply_markup=MENU)

# ================== LIST POSTS ==================
@app.on_message(filters.regex("^📄 My Posts$"))
async def list_posts(_, m):
    rows = cur.execute(
        "SELECT id, text FROM posts WHERE user_id=?",
        (m.from_user.id,)
    ).fetchall()

    if not rows:
        await m.reply("No posts found")
        return

    msg = "📄 Posts:\n\n"
    for pid, text in rows:
        msg += f"{pid}. {text[:40]}\n"

    await m.reply(msg)

# ================== ADD SCHEDULE ==================
@app.on_message(filters.regex("^⏰ Add Schedule$"))
async def sch_help(_, m):
    await m.reply(
        "Format:\n"
        "`POST_ID | CHAT_ID | once/daily/weekly | YYYY-MM-DD HH:MM`\n\n"
        "Example:\n"
        "`1 | -100xxxx | once | 2026-02-01 10:00`"
    )

@app.on_message(filters.text & filters.regex(r"\|"))
async def save_schedule(_, m):
    try:
        post_id, chat, stype, run_at = [x.strip() for x in m.text.split("|")]
        datetime.fromisoformat(run_at)

        cur.execute("""
        INSERT INTO schedules
        (user_id, post_id, chat_id, schedule_type, run_at)
        VALUES (?, ?, ?, ?, ?)
        """, (m.from_user.id, int(post_id), chat, stype, run_at))

        db.commit()
        await m.reply("✅ Schedule added")

    except:
        await m.reply("❌ Invalid format")

# ================== LIST SCHEDULES ==================
@app.on_message(filters.regex("^📆 My Schedules$"))
async def list_sch(_, m):
    rows = cur.execute(
        "SELECT id, post_id, schedule_type, run_at FROM schedules WHERE user_id=?",
        (m.from_user.id,)
    ).fetchall()

    if not rows:
        await m.reply("No schedules")
        return

    msg = "📆 Schedules:\n\n"
    for sid, pid, st, rt in rows:
        msg += f"{sid}. Post {pid} | {st} | {rt}\n"

    await m.reply(msg)

# ================== DELETE ==================
@app.on_message(filters.regex("^🗑 Delete Schedule$"))
async def del_help(_, m):
    await m.reply("Send schedule ID")

@app.on_message(filters.text & filters.regex(r"^\d+$"))
async def del_sch(_, m):
    cur.execute(
        "DELETE FROM schedules WHERE id=? AND user_id=?",
        (int(m.text), m.from_user.id)
    )
    db.commit()
    await m.reply("🗑 Deleted")

# ================== SCHEDULER ==================
async def scheduler():
    while True:
        now = datetime.utcnow()
        rows = cur.execute(
            "SELECT id, post_id, chat_id, schedule_type, run_at FROM schedules"
        ).fetchall()

        for sid, pid, chat, stype, run_at in rows:
            run_time = datetime.fromisoformat(run_at)
            if now >= run_time:
                post = cur.execute(
                    "SELECT text FROM posts WHERE id=?",
                    (pid,)
                ).fetchone()

                if post:
                    try:
                        await app.send_message(int(chat), post[0])
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

# ================== RUN ==================
async def main():
    await app.start()
    asyncio.create_task(scheduler())
    print("✅ BOT RUNNING (POLLING MODE)")
    await idle()

from pyrogram import idle
asyncio.run(main())
