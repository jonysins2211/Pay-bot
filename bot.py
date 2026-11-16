import asyncio
import logging
import os
from aiohttp import web
from pyrogram import idle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)

from info import *
from client import PayBot
from utils import ping_server, subscription_expiry_checker

# ── Web health check server ───────────────────────────────────
async def health_check(request):
    return web.Response(text="OK", status=200)

async def web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    return app

# ── Main startup ──────────────────────────────────────────────
async def start():
    print("\n")
    print("🚀 Starting ML Payment Bot...")

    # Start bot
    await PayBot.start()
    me = await PayBot.get_me()
    print(f"✅ BOT RUNNING: @{me.username}")
    logging.info(f"✅ BOT RUNNING: @{me.username}")

    # Start background tasks
    PayBot.loop.create_task(subscription_expiry_checker(PayBot))
    logging.info("✅ Expiry checker started")

    if ON_HEROKU:
        PayBot.loop.create_task(ping_server())
        logging.info("✅ Ping task started")

    # Start web server for health checks
    runner = web.AppRunner(await web_server())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"✅ Web server on port {PORT}")

    # Send restart notification
    try:
        await PayBot.send_message(
            LOGS_CHANNEL,
            f"<b>🤖 Bot Started!</b>\n<b>@{me.username} is now online ✅</b>"
        )
    except Exception:
        pass

    logging.info("✅ Listening for messages...")
    await idle()

    await PayBot.stop()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start())
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
