import base64
import html
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
    add_history, get_ban, get_promo, use_promo,
)

logger = logging.getLogger(__name__)

# ── In-memory (runtime only) ──────────────────────────────────
user_state:   dict = {}
expiry_tasks: dict = {}
nudge_tasks:  dict = {}
pending_pays: dict = {}   # mirrors DB for quick access

# A payment screenshot waiting this long for admin approval triggers
# one reminder to the admin group (with Approve/Reject buttons).
APPROVAL_NUDGE_SECONDS = 1800  # 30 minutes


def esc(value) -> str:
    """Escape user-provided text for the bot's HTML parse mode."""
    return html.escape(str(value), quote=False)


def ban_message(reason: str) -> str:
    return (
        "<b>🚫 You are banned.</b>\n\n"
        f"<blockquote><b>Reason: {esc(reason)}</b></blockquote>"
    )


def ban_alert(reason: str) -> str:
    """Plain-text version for the callback alert (alerts render no HTML)."""
    return f"🚫 You are banned.\n\nReason: {reason}"


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
    await query.answer(ban_alert(ban.get("reason", "No reason provided.")), show_alert=True)
    try:
        await query.message.reply_text(text)
    except Exception:
        pass
    return True


def upi_pay_url(amount: int, note: str) -> str:
    """UPI deep link: tapping it opens the UPI app with payee + amount pre-filled.

    This is the same URL the QR code encodes — the QR is just this link
    drawn as a picture. Sending it as a button/link skips the scan step.
    """
    return (
        f"upi://pay?pa={UPI_ID}&pn={UPI_NAME.replace(' ', '%20')}"
        f"&am={amount}&cu=INR&tn={note.replace(' ', '%20')}"
    )


def _public_base_url() -> str:
    """Public base URL of this bot's web server.

    Set PUBLIC_URL (e.g. https://my-bot.koyeb.app) where the bot is hosted.
    The scheme may be left off (careful-lilly-movieloverzzz.koyeb.app) —
    https:// is added then, because Telegram rejects a button/WebApp URL
    without a scheme (BUTTON_URL_INVALID).
    Falls back to the Heroku-style URL from APP_NAME.
    """
    base = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")
    if base:
        if not base.startswith(("http://", "https://")):
            base = "https://" + base
        return base
    return f"https://{APP_NAME}.herokuapp.com"


def payment_link(pid: str) -> str:
    """Shareable https payment link for a pending payment.

    Served by this bot's own web server (/pay/<pid>) — the page shows the
    amount and a Pay button that opens the UPI app. No third-party service.
    """
    return f"{_public_base_url()}/pay/{pid}"


def make_qr(amount: int, note: str) -> BytesIO:
    qr = qrcode.QRCode(box_size=12, border=4)
    qr.add_data(upi_pay_url(amount, note))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def payment_caption(amount: int, label: str, link: str,
                    promo_code: str | None = None,
                    original_amount: int | None = None) -> str:
    """Caption for the payment message (used by plan select and resend).

    When a promo code was applied, the caption shows the discounted
    amount, the original price, and the code used.
    """
    if promo_code and original_amount is not None and original_amount > amount:
        amount_line = (
            f"• PAY ₹{amount} <s>₹{original_amount}</s> — PREMIUM TIME: {esc(label)}\n"
            f"• 🎟️ PROMO {esc(promo_code)} APPLIED — YOU SAVE ₹{original_amount - amount}"
        )
    else:
        amount_line = f"• PAY ₹{amount} — PREMIUM TIME: {esc(label)}"
    return (
        f"<b>🧾 PAYMENT DETAILS:</b>\n\n"
        f"<blockquote><b>{amount_line}\n"
        f"• PAYMENT LINK VALID FOR 5 MINUTES</b></blockquote>\n\n"
        f"<b>💳 TAP “PAY NOW” BELOW TO OPEN THE PAYMENT PAGE</b>\n"
        f"<b>🔗 Payment Link:</b> <a href=\"{link}\">{link}</a>\n\n"
        f"<b>⚠️ AFTER PAYMENT:</b>\n"
        f"<b>📸 SEND THE PAYMENT SCREENSHOT HERE</b>"
    )


# Payment banner shown instead of the QR code. Stored as base64 text
# (assets/pay_banner.b64) because the repo push carries text files only.
# The QR still lives on the payment-link page (/pay/<pid>).
PAY_BANNER_B64 = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets", "pay_banner.b64"
)
_BANNER_CACHE = None


def pay_banner_photo():
    """Banner image as a photo the bot can send (None if the asset is missing)."""
    global _BANNER_CACHE
    if _BANNER_CACHE is None:
        try:
            with open(PAY_BANNER_B64) as f:
                _BANNER_CACHE = base64.b64decode(f.read())
        except Exception:
            _BANNER_CACHE = False
    if not _BANNER_CACHE:
        return None
    buf = BytesIO(_BANNER_CACHE)
    buf.name = "pay_banner.jpg"
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

def cancel_nudge_by_pid(pid: str):
    task = nudge_tasks.pop(pid, None)
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


async def approval_nudge_timer(client, pid: str):
    """Remind the admin once if a payment screenshot waits too long.

    Started when the screenshot reaches the admin group. If the
    payment is still pending after APPROVAL_NUDGE_SECONDS, the admin
    group gets one reminder with the Approve/Reject buttons, so the
    approval can be done from the reminder itself. Cancelled as soon
    as the payment is approved or rejected.
    """
    from keyboards import admin_kb
    await asyncio.sleep(APPROVAL_NUDGE_SECONDS)

    payment = await get_pending(pid)
    if not payment:
        return

    bot  = BOTS.get(payment["bot_key"], {})
    plan = bot.get("plans", {}).get(payment["plan_key"], {})
    uname = f"@{payment['username']}" if payment.get("username") not in (None, "N/A") else "No username"

    try:
        await client.send_message(
            ADMIN_GROUP,
            f"<b>⏰ PAYMENT AWAITING APPROVAL (30 MIN)</b>\n\n"
            f"<blockquote><b>👤 User:</b> <a href=\"tg://user?id={payment['user_id']}\">{esc(payment.get('first_name', 'User'))}</a>\n"
            f"<b>🔗 Username:</b> {esc(uname)}\n"
            f"<b>🆔 User ID:</b> <code>{payment['user_id']}</code>\n"
            f"<b>🤖 Bot:</b> {esc(bot.get('name', '?'))}\n"
            f"<b>📅 Plan:</b> {esc(plan.get('label', '?'))}\n"
            f"<b>💰 Amount:</b> ₹{esc(payment.get('amount', plan.get('price', '?')))}</b></blockquote>\n\n"
            f"<b>👇 Approve or reject below.</b>",
            reply_markup=admin_kb(pid),
        )
    except Exception as e:
        logger.warning(f"Approval nudge {pid}: {e}")


async def qr_expiry_timer(client, user_id: int, pid: str,
                           bot_key: str, plan_key: str, chat_id: int):
    from keyboards import expired_kb

    # Reminder 2 minutes before the window closes, so a user who is
    # still paying gets one nudge to send the screenshot in time.
    # The timer is cancelled as soon as the screenshot arrives (or the
    # user cancels), so the reminder only fires while still waiting.
    reminder_at = max(60, QR_EXPIRY_SECONDS - 120)
    await asyncio.sleep(reminder_at)

    payment = await get_pending(pid)
    state = user_state.get(user_id, {})
    if payment and state.get("awaiting_screenshot") and state.get("pending_id") == pid:
        bot  = BOTS.get(bot_key, {})
        plan = bot.get("plans", {}).get(plan_key, {})
        try:
            await client.send_message(
                chat_id,
                f"<b>⏰ PAYMENT REMINDER</b>\n\n"
                f"<blockquote><b>🤖 Bot: {esc(bot.get('name', '?'))}\n"
                f"📅 Plan: {esc(plan.get('label', '?'))} — ₹{esc(plan.get('price', '?'))}\n"
                f"⏳ Your payment link expires in 2 minutes!</b></blockquote>\n\n"
                f"<b>📸 Paid already? Send the screenshot now.</b>\n"
                f"<b>🔄 Need a fresh link? Tap Resend Link on the payment message.</b>",
            )
        except Exception as e:
            logger.warning(f"Payment reminder {user_id}: {e}")

    await asyncio.sleep(QR_EXPIRY_SECONDS - reminder_at)

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
            "<b>⏳ PAYMENT TIME EXPIRED!</b>\n\n"
            "<blockquote><b>YOUR 5-MINUTE PAYMENT WINDOW HAS BEEN\n"
            "CLOSED. IF YOU WANT TO TRY AGAIN, CLICK\n"
            "RESTART BELOW.</b></blockquote>",
            reply_markup=expired_kb(bot_key, plan_key),
        )
    except Exception as e:
        logger.error(f"Expiry msg error: {e}")

    await log(client,
        f"<b>⏰ QR EXPIRED</b>\n\n"
        f"<b>🆔 User ID:</b> <code>{user_id}</code>\n"
        f"<b>🤖 Bot:</b> {esc(bot.get('name', '?'))}\n"
        f"<b>📅 Plan:</b> {esc(plan.get('label', '?'))} | ₹{esc(plan.get('price', '?'))}\n"
        f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>"
    )


async def start_payment(client, user_id: int, bot_key: str, plan_key: str,
                        amount: int | None = None,
                        username: str = "N/A", first_name: str = "User"):
    """Start a payment for a user (shared by plan select and /createlink).

    Creates the pending payment (custom amount if given, else the plan
    price), sends the user the payment message (banner + Pay Now /
    Resend Link buttons) and the screenshot prompt, and starts the
    5-minute expiry timer. Returns (pid, link). Raises if the messages
    cannot be delivered (e.g. the user never started the bot) — the
    pending payment is cleaned up first in that case.
    """
    from keyboards import pay_kb
    bot  = BOTS[bot_key]
    plan = bot["plans"][plan_key]
    amount = plan["price"] if amount is None else amount
    label  = plan["label"]
    pid    = make_pending_id(user_id, bot_key, plan_key)

    await clear_user_pending(user_id, client)

    pay_data = {
        "user_id":    user_id,
        "username":   username,
        "first_name": first_name,
        "bot_key":    bot_key,
        "plan_key":   plan_key,
        "amount":     amount,
        "ts":         datetime.now().isoformat(),
        "chat_id":    user_id,
    }
    # Save to memory + MongoDB
    pending_pays[pid] = pay_data
    await add_pending(pid, pay_data)

    user_state[user_id] = {
        "bot_key":             bot_key,
        "plan_key":            plan_key,
        "pending_id":          pid,
        "chat_id":             user_id,
        "awaiting_screenshot": True,
    }

    link = payment_link(pid)
    caption = payment_caption(amount, label, link)
    try:
        banner = pay_banner_photo()
        if banner is not None:
            pay_msg = await client.send_photo(
                user_id, photo=banner, caption=caption,
                reply_markup=pay_kb(link, pid),
            )
        else:
            # Banner missing — text only.
            pay_msg = await client.send_message(
                user_id, caption, reply_markup=pay_kb(link, pid))
        proof_msg = await client.send_message(
            user_id,
            "<b>📸 SEND A SCREENSHOT OF THE PAYMENT FOR VERIFICATION.</b>\n\n"
            "<b>Use /cancel to cancel the process.</b>",
        )
    except Exception:
        # Could not reach the user (never started the bot / blocked it) —
        # do not leave a dangling pending payment behind.
        pending_pays.pop(pid, None)
        await del_pending(pid)
        user_state.pop(user_id, None)
        raise

    user_state[user_id]["qr_message_id"] = pay_msg.id
    user_state[user_id]["proof_message_id"] = proof_msg.id

    uname = f"@{username}" if username != "N/A" else "No username"
    await log(client,
        f"<b>🔔 QR CODE GENERATED</b>\n\n"
        f"<b>👤 User:</b> <a href=\"tg://user?id={user_id}\">{esc(first_name)}</a>\n"
        f"<b>🔗 Username:</b> {esc(uname)}\n"
        f"<b>🆔 User ID:</b> <code>{user_id}</code>\n"
        f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
        f"<b>📅 Plan:</b> {esc(label)}\n"
        f"<b>💰 Amount:</b> ₹{amount}\n"
        f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>\n"
        f"<b>⏳ QR valid for 5 minutes</b>"
    )

    task = asyncio.create_task(
        qr_expiry_timer(client, user_id, pid, bot_key, plan_key, user_id)
    )
    expiry_tasks[pid] = task
    return pid, link


def discounted_amount(amount: int, promo: dict) -> int:
    """Price after a promo code (never below ₹1)."""
    if promo["type"] == "percent":
        return max(1, round(amount * (1 - promo["value"] / 100)))
    return max(1, amount - promo["value"])


async def apply_promo_code(client, user_id: int, code_str: str):
    """Apply a promo code to the user's pending payment.

    Returns (ok, reply_text). On success the pending payment's amount
    is lowered (memory + MongoDB), one use of the code is consumed,
    and the payment message is updated to show the discount (the promo
    button is removed — one code per payment). The /pay page reads the
    amount live, so the same link now shows the discounted price + QR.
    """
    from keyboards import pay_kb
    code = (code_str or "").strip().upper()
    if not code:
        return False, "<b>❌ Send a promo code.</b>"

    promo = await get_promo(code)
    if not promo:
        return False, "<b>❌ Invalid promo code.</b>\n<b>Check the code and try again, or /cancel to skip.</b>"
    max_uses = promo.get("max_uses")
    if max_uses is not None and promo.get("uses", 0) >= max_uses:
        return False, "<b>❌ This promo code has reached its usage limit.</b>"

    state = user_state.get(user_id, {})
    pid = state.get("pending_id")
    payment = pending_pays.get(pid) if pid else None
    if not pid or not payment:
        payment = await get_pending(pid) if pid else None
    if not pid or not payment:
        return False, "<b>⚠️ No active payment found. Please /start again.</b>"
    if not state.get("awaiting_screenshot") or state.get("pending_id") != pid:
        return False, "<b>⚠️ This payment is already under review.</b>"

    original = payment["amount"]
    new_amount = discounted_amount(original, promo)
    if new_amount >= original:
        return False, "<b>❌ This code gives no discount on this plan.</b>"

    # Consume one use first (atomic) — if the last use was just taken
    # by someone else, nothing is changed and the user is told so.
    if not await use_promo(code):
        return False, "<b>❌ This promo code has just reached its usage limit.</b>"

    payment = dict(payment)
    payment["amount"] = new_amount
    payment["promo_code"] = code
    payment["original_amount"] = original
    pending_pays[pid] = payment
    await add_pending(pid, payment)

    bot  = BOTS.get(payment["bot_key"], {})
    plan = bot.get("plans", {}).get(payment["plan_key"], {})
    link = payment_link(pid)
    caption = payment_caption(
        new_amount, plan.get("label", ""), link,
        promo_code=code, original_amount=original,
    )
    chat_id = state.get("chat_id", user_id)
    qr_message_id = state.get("qr_message_id")
    if qr_message_id:
        try:
            await client.edit_message_caption(
                chat_id, qr_message_id, caption=caption,
                reply_markup=pay_kb(link, pid, show_promo=False),
            )
        except Exception:
            try:
                await client.edit_message_text(
                    chat_id, qr_message_id, caption,
                    reply_markup=pay_kb(link, pid, show_promo=False),
                )
            except Exception as e:
                logger.warning(f"Promo edit {pid}: {e}")

    user_state[user_id].pop("awaiting_promo", None)
    saved = original - new_amount
    return True, (
        f"<b>✅ PROMO APPLIED!</b>\n\n"
        f"<blockquote><b>🎟️ Code: {esc(code)}\n"
        f"💰 You save ₹{saved} — new amount: ₹{new_amount}</b></blockquote>\n\n"
        f"<b>Pay ₹{new_amount} via the payment link, then send the screenshot.</b>"
    )


async def subscription_expiry_checker(client):
    """Check subscription expiries once a day, starting right away.

    Reminders (each sent once per subscription, tracked in the sub's
    reminders_sent list so a restart never re-sends one):
      • 3 days left — "expiring in 3 days" + Renew button
      • 1 day left  — "expiring tomorrow" + Renew button
      • 0 days left — "expired" + Renew button, subscription removed
    A sub already past its date (e.g. the bot was down) counts as
    expired too. The Renew button goes straight to the payment flow
    for the same plan — no plan list in between.
    """
    from keyboards import renew_plan_kb

    async def _check_once():
        now = datetime.now().date()
        all_subs = await get_all_subs()

        for user_id, subs in list(all_subs.items()):
            still_active = []
            changed = False
            for sub in subs:
                expiry_str = sub.get("expiry_raw")
                if not expiry_str:
                    still_active.append(sub)
                    continue

                try:
                    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                except Exception:
                    still_active.append(sub)
                    continue
                bot_key   = sub.get("bot_key", "")
                plan_key  = sub.get("plan_key", "")
                bot_uname = BOTS.get(bot_key, {}).get("username", "")
                days_left = (expiry_date - now).days
                sent = sub.get("reminders_sent", []) or []

                if days_left == 3 and 3 not in sent:
                    try:
                        await client.send_message(
                            user_id,
                            f"<b>⏰ SUBSCRIPTION EXPIRING IN 3 DAYS!</b>\n\n"
                            f"<blockquote><b>🤖 Bot: {esc(bot_uname)}\n"
                            f"📆 Expires: {esc(sub.get('expiry', expiry_str))}</b></blockquote>\n\n"
                            f"<b>🔄 Renew now to keep your premium access!</b>",
                            reply_markup=renew_plan_kb(bot_key, plan_key),
                        )
                    except Exception as e:
                        logger.warning(f"3-day notify {user_id}: {e}")
                    sub["reminders_sent"] = sent + [3]
                    changed = True
                    still_active.append(sub)

                elif days_left == 1 and 1 not in sent:
                    try:
                        await client.send_message(
                            user_id,
                            f"<b>⚠️ SUBSCRIPTION EXPIRING TOMORROW!</b>\n\n"
                            f"<blockquote><b>🤖 Bot: {esc(bot_uname)}\n"
                            f"📆 Expires: {esc(sub.get('expiry', expiry_str))}</b></blockquote>\n\n"
                            f"<b>🔄 Renew now to avoid losing access!</b>",
                            reply_markup=renew_plan_kb(bot_key, plan_key),
                        )
                    except Exception as e:
                        logger.warning(f"1-day notify {user_id}: {e}")
                    sub["reminders_sent"] = sent + [1]
                    changed = True
                    still_active.append(sub)

                elif days_left <= 0:
                    try:
                        await client.send_message(
                            user_id,
                            f"<b>❌ SUBSCRIPTION EXPIRED!</b>\n\n"
                            f"<blockquote><b>🤖 Bot: {esc(bot_uname)}\n"
                            f"📆 Expired: {esc(sub.get('expiry', expiry_str))}</b></blockquote>\n\n"
                            f"<b>🔄 Tap below to renew!</b>",
                            reply_markup=renew_plan_kb(bot_key, plan_key),
                        )
                    except Exception as e:
                        logger.warning(f"Expiry notify {user_id}: {e}")
                    changed = True  # sub dropped from still_active

                else:
                    still_active.append(sub)

            if changed:
                await set_subs(user_id, still_active)

    while True:
        await _check_once()
        await asyncio.sleep(86400)


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
