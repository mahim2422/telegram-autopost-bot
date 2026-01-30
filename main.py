from pyrogram import Client, filters
import os

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

app = Client(
    "test_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(
        f"✅ Bot is alive!\n\n"
        f"Your ID: `{m.from_user.id}`",
        quote=True
    )

app.run()
