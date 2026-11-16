import asyncio
import base64
import html as html_lib
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
from database.db import get_pending
from utils import ping_server, subscription_expiry_checker, upi_pay_url, make_qr

# ── Web health check server ───────────────────────────────────
async def health_check(request):
    return web.Response(text="OK", status=200)


# ── UPI payment link page ─────────────────────────────────────
# GET /pay/<pid> — the shareable https payment link sent by the bot.
# Looks the pending payment up in MongoDB, then shows the amount and a
# Pay button that opens the UPI app (same upi:// link the QR encodes).
# The pid expires with the QR (5 min); after that the link shows expired.
PAY_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pay {amount} — ML Payment Bot</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f172a;color:#f1f5f9;
margin:0;display:flex;justify-content:center;padding:24px 12px}}
.card{{background:#1e293b;border-radius:16px;padding:28px 22px;max-width:380px;
width:100%;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.4)}}
h1{{font-size:20px;margin:0 0 6px}}
.amount{{font-size:44px;font-weight:800;color:#38bdf8;margin:14px 0 4px}}
.plan{{color:#cbd5e1;margin:0 0 20px}}
.pay{{display:block;background:#22c55e;color:#fff;font-weight:700;font-size:19px;
text-decoration:none;padding:15px 10px;border-radius:12px;margin:6px 0 14px}}
.hint{{font-size:13px;color:#94a3b8;line-height:1.5}}
img{{width:200px;height:200px;background:#fff;border-radius:12px;padding:8px;margin-top:8px}}
</style></head><body><div class="card">
<h1>💳 ML Payment Bot</h1>
<p><b>{bot_name}</b> is requesting a payment of</p>
<div class="amount">₹{amount}</div>
<p class="plan">📅 Plan: {label}</p>
<a class="pay" href="{upi}">💳 Pay ₹{amount} via UPI</a>
<p class="hint">Tap Pay — your UPI app opens with the amount already filled.
After paying, send the payment screenshot to the bot.</p>
<img src="data:image/png;base64,{qr_b64}" alt="Scan to pay">
<p class="hint">Or scan the QR with any UPI app.</p>
</div></body></html>"""

EXPIRED_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Link expired — ML Payment Bot</title>
<style>body{font-family:system-ui,sans-serif;background:#0f172a;color:#f1f5f9;
margin:0;display:flex;justify-content:center;padding:40px 16px;text-align:center}
p{color:#94a3b8;line-height:1.6}</style></head>
<body><div><h1>⏳ Payment link expired</h1>
<p>This payment link is no longer valid (QR codes are valid for 5 minutes).<br>
Open the bot and select your plan again to get a fresh link.</p></div></body></html>"""


async def pay_page(request):
    pid = request.match_info.get("pid", "")
    payment = await get_pending(pid)
    if not payment:
        return web.Response(text=EXPIRED_PAGE, status=404, content_type="text/html")

    bot = BOTS.get(payment["bot_key"], {})
    plan = bot.get("plans", {}).get(payment["plan_key"], {})
    amount = payment["amount"]
    note = f"Premium {bot.get('username', '')} {plan.get('label', '')}"
    upi = upi_pay_url(amount, note)
    qr_b64 = base64.b64encode(make_qr(amount, note).getvalue()).decode()
    page = PAY_PAGE.format(
        amount=amount,
        bot_name=html_lib.escape(str(bot.get("name", "Premium"))),
        label=html_lib.escape(str(plan.get("label", ""))),
        upi=html_lib.escape(upi, quote=True),
        qr_b64=qr_b64,
    )
    return web.Response(text=page, content_type="text/html")


async def web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/pay/{pid}", pay_page)
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
