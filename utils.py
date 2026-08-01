import os
import asyncio
import logging
import aiohttp
import qrcode
from io import BytesIO
from datetime import datetime, timedelta

from info import *
from database.db import (
    add_pending, get_pending, del_pending,
    add_sub, get_subs, set_subs, get_all_subs,
    add_history, get_ban
)

logger = logging.getLogger(__name__)

# ── In-memory (runtime only) ──────────────────────────────────
user_state:   dict = {}
expiry_tasks: dict = {}
pending_pays: dict = {}   # mirrors DB for quick access


def ban_message(reason: str) -> str:
    return (
        "🚫 **You are banned.**\n\n"
        f"Reason: {reason}"
    )


async def is_banned(user_id: int) -> dict | None:
    return await get_ban(user_id)


async def reply_if_banned(message) -> bool:
    ban = await is_banned(message.from_user.id)
    if not ban:
        return False
    await message.reply_text(ban_message(ban.get("reason", "No reason provided.")))
    return True


async def answer_if_banned(query) -> bool:
    ban = await is_banned(query.from_user.id)
    if not ban:
        return False
    text = ban_message(ban.get("reason", "No reason provided."))
    await query.answer(text.replace("**", ""), show_alert=True)
    try:
        await query.message.reply_text(text)
    except Exception:
        pass
    return True


def make_qr(amount: int, note: str) -> BytesIO:
    upi_url = (
        f"upi://pay?pa={UPI_ID}&pn={UPI_NAME.replace(' ', '%20')}"
        f"&am={amount}&cu=INR&tn={note.replace(' ', '%20')}"
    )
    qr = qrcode.QRCode(box_size=12, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def make_pending_id(user_id: int, bot_key: str, plan_key: str) -> str:
    return f"{user_id}_{bot_key}_{plan_key}_{int(datetime.now().timestamp())}"


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d %b %Y")


async def log(client, text: str):
    if not LOGS_CHANNEL:
        return
    try:
        await client.send_message(LOGS_CHANNEL, text, disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"Log error: {e}")


def cancel_expiry(user_id: int):
    state = user_state.get(user_id, {})
    pid = state.get("pending_id")
    if pid:
        cancel_expiry_by_pid(pid)

def cancel_expiry_by_pid(pid: str):
    task = expiry_tasks.pop(pid, None)
    if task and not task.done():
        task.cancel()

async def clear_user_pending(user_id: int, client=None):
    state = user_state.get(user_id, {})
    pid = state.get("pending_id")
    if not pid:
        return

    chat_id = state.get("chat_id")
    qr_message_id = state.get("qr_message_id")
    proof_message_id = state.get("proof_message_id")

    cancel_expiry_by_pid(pid)
    pending_pays.pop(pid, None)
    await del_pending(pid)

    if client and chat_id:
        for msg_id in (qr_message_id, proof_message_id):
            if not msg_id:
                continue
            try:
                await client.delete_messages(chat_id, msg_id)
            except Exception:
                pass


async def qr_expiry_timer(client, user_id: int, pid: str,
                           bot_key: str, plan_key: str, chat_id: int):
    from keyboards import expired_kb
    await asyncio.sleep(QR_EXPIRY_SECONDS)

    payment = await get_pending(pid)
    if not payment:
        return

    state = user_state.get(user_id, {})
    if not state.get("awaiting_screenshot") or state.get("pending_id") != pid:
        return

    qr_message_id = state.get("qr_message_id")
    proof_message_id = state.get("proof_message_id")

    user_state.pop(user_id, None)
    pending_pays.pop(pid, None)
    await del_pending(pid)

    for msg_id in (qr_message_id, proof_message_id):
        if not msg_id:
            continue
        try:
            await client.delete_messages(chat_id, msg_id)
        except Exception:
            pass

    bot  = BOTS.get(bot_key, {})
    plan = bot.get("plans", {}).get(plan_key, {})

    try:
        await client.send_message(
            chat_id,
            "⏳ **PAYMENT TIME EXPIRED!**\n\n"
            "*YOUR 5-MINUTE PAYMENT WINDOW HAS BEEN\n"
            "CLOSED. IF YOU WANT TO TRY AGAIN, CLICK\n"
            "RESTART BELOW.*",
            reply_markup=expired_kb(bot_key, plan_key),
        )
    except Exception as e:
        logger.error(f"Expiry msg error: {e}")

    await log(client,
        f"⏰ **QR EXPIRED**\n\n"
        f"🆔 User ID: `{user_id}`\n"
        f"🤖 Bot: **{bot.get('name', '?')}**\n"
        f"📅 Plan: **{plan.get('label', '?')}** | ₹{plan.get('price', '?')}\n"
        f"🕐 `{datetime.now().strftime('%d %b %Y %H:%M:%S')}`"
    )


async def subscription_expiry_checker(client):
    while True:
        await asyncio.sleep(86400)
        from keyboards import renew_kb
        now = datetime.now().date()
        all_subs = await get_all_subs()

        for user_id, subs in list(all_subs.items()):
            still_active = []
            for sub in subs:
                expiry_str = sub.get("expiry_raw")
                if not expiry_str:
                    still_active.append(sub)
                    continue

                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                bot_key   = sub.get("bot_key", "")
                bot_uname = BOTS.get(bot_key, {}).get("username", "")
                days_left = (expiry_date - now).days

                if days_left == 1:
                    try:
                        await client.send_message(
                            user_id,
                            f"⚠️ **SUBSCRIPTION EXPIRING TOMORROW!**\n\n"
                            f"🤖 Bot: **{bot_uname}**\n"
                            f"📆 Expires: **{sub.get('expiry', expiry_str)}**\n\n"
                            f"🔄 *Renew now to avoid losing access!*",
                            reply_markup=renew_kb(bot_key),
                        )
                    except Exception as e:
                        logger.warning(f"1-day notify {user_id}: {e}")
                    still_active.append(sub)

                elif days_left == 0:
                    try:
                        await client.send_message(
                            user_id,
                            f"❌ **SUBSCRIPTION EXPIRED!**\n\n"
                            f"🤖 Bot: **{bot_uname}**\n"
                            f"📆 Expired: **{sub.get('expiry', expiry_str)}**\n\n"
                            f"🔄 *Tap below to renew!*",
                            reply_markup=renew_kb(bot_key),
                        )
                    except Exception as e:
                        logger.warning(f"Expiry notify {user_id}: {e}")

                elif days_left > 1:
                    still_active.append(sub)

            await set_subs(user_id, still_active)


async def ping_server():
    url = f"https://{os.environ.get('APP_NAME', '')}.herokuapp.com/"
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    logger.info(f"✅ Pinged: {resp.status}")
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
