import asyncio
import logging
import time
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.types import Message

from info import BOTS, ADMIN_GROUP, OWNER_USERNAME
from keyboards import home_kb, admin_kb
from utils import (
    user_state, pending_pays, nudge_tasks, approval_nudge_timer,
    cancel_expiry_by_pid, log, reply_if_banned, esc, apply_promo_code,
)

logger = logging.getLogger(__name__)

COMMANDS = ["start", "myplan", "myhistory", "mypayments", "stats", "createlink", "addpromo", "delpromo", "promos", "report", "owner_cmd", "pending", "cancel", "broadcast", "ban", "unban", "bans"]

# ── "Use /start" fallback spam guard ──────────────────────────
# After a redeploy the bot can receive the same update again
# (pending-updates replay) or a user can tap /start repeatedly while
# the bot is still starting — either way the fallback below used to
# fire once per update and spam the same message in a loop. Two guards:
#   1. ignore stale updates (a message older than 2 min is a replay,
#      not a live user action), and
#   2. one fallback reply per user per 30 s.
_FALLBACK_COOLDOWN_S = 30
_FALLBACK_MAX_AGE_S = 120
_fallback_last_sent: dict[int, float] = {}


def _should_send_fallback(message: Message) -> bool:
    """True only if this fallback reply should actually be sent."""
    try:
        age = (datetime.now(timezone.utc) - message.date).total_seconds()
    except Exception:
        age = 0
    if age > _FALLBACK_MAX_AGE_S:
        return False
    now = time.monotonic()
    user_id = message.from_user.id
    last = _fallback_last_sent.get(user_id, 0)
    if now - last < _FALLBACK_COOLDOWN_S:
        return False
    _fallback_last_sent[user_id] = now
    return True


@Client.on_message(filters.private & (filters.photo | filters.document))
async def screenshot_handler(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user  = message.from_user
    state = user_state.get(user.id, {})

    if not state.get("awaiting_screenshot"):
        await message.reply_text("<b>Please use /start to begin a subscription.</b>")
        return

    pid     = state.get("pending_id")
    payment = pending_pays.get(pid) if pid else None
    if not pid or not payment:
        await message.reply_text("<b>⚠️ Session expired. Please /start again.</b>")
        return

    cancel_expiry_by_pid(pid)

    bot_key  = payment["bot_key"]
    plan_key = payment["plan_key"]
    bot      = BOTS[bot_key]
    plan     = bot["plans"][plan_key]
    uname    = f"@{user.username}" if user.username else "No username"

    admin_caption = (
        f"<b>📸 PAYMENT SCREENSHOT</b>\n\n"
        f"<b>👤 User:</b> <a href=\"tg://user?id={user.id}\">{esc(user.first_name)}</a>\n"
        f"<b>🔗 Username:</b> {esc(uname)}\n"
        f"<b>🆔 User ID:</b> <code>{user.id}</code>\n"
        f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
        f"<b>📅 Plan:</b> {esc(plan['label'])}\n"
        f"<b>💰 Amount:</b> ₹{payment.get('amount', plan['price'])}\n"
        f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>\n"
        f"<b>🔑 ID:</b> <code>{esc(pid)}</code>"
    )

    if not ADMIN_GROUP:
        await message.reply_text("<b>❌ Admin group not configured. Contact owner.</b>")
        return

    try:
        if message.photo:
            await client.send_photo(
                ADMIN_GROUP,
                photo=message.photo.file_id,
                caption=admin_caption,
                reply_markup=admin_kb(pid),
            )
        elif message.document:
            await client.send_document(
                ADMIN_GROUP,
                document=message.document.file_id,
                caption=admin_caption,
                reply_markup=admin_kb(pid),
            )
    except Exception as e:
        logger.error(f"Forward to admin: {e}")
        await message.reply_text("<b>❌ Error sending to admin. Try again.</b>")
        return

    # Remind the admin once if this screenshot waits 30 min for approval.
    nudge_tasks[pid] = asyncio.create_task(approval_nudge_timer(client, pid))

    user_state.pop(user.id, None)
    await message.reply_text(
        "<b>✅ SCREENSHOT RECEIVED!</b>\n\n"
        "<blockquote><b>⏳ Your payment is under review.\n"
        "You'll be notified once approved.</b></blockquote>\n\n"
        "<b>⚡ Approvals usually take just a few minutes!</b>",
    )

    await log(client,
        f"<b>📸 SCREENSHOT RECEIVED</b>\n\n"
        f"<b>👤 User:</b> <a href=\"tg://user?id={user.id}\">{esc(user.first_name)}</a>\n"
        f"<b>🔗 Username:</b> {esc(uname)}\n"
        f"<b>🆔 User ID:</b> <code>{user.id}</code>\n"
        f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
        f"<b>📅 Plan:</b> {esc(plan['label'])}\n"
        f"<b>💰 Amount:</b> ₹{plan['price']}\n"
        f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>\n"
        f"<b>⏳ Awaiting Admin Approval</b>"
    )


@Client.on_message(filters.private & filters.text & ~filters.command(COMMANDS))
async def text_handler(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user  = message.from_user
    state = user_state.get(user.id, {})

    if state.get("awaiting_promo"):
        # The user tapped "Apply Promo Code" — this text is the code.
        # On success awaiting_promo is cleared; on failure it stays
        # set so the user can try another code (or /cancel to skip).
        ok, reply = await apply_promo_code(client, user.id, message.text)
        await message.reply_text(reply)

    elif state.get("action") == "report":
        try:
            await client.send_message(
                ADMIN_GROUP,
                f"<b>⚠️ USER REPORT</b>\n\n"
                f"<b>👤</b> <a href=\"tg://user?id={user.id}\">{esc(user.first_name)}</a> (<code>@{esc(user.username or 'N/A')}</code>)\n"
                f"<b>🆔</b> <code>{user.id}</code>\n\n"
                f"<blockquote><b>{esc(message.text)}</b></blockquote>"
            )
            await message.reply_text(
                f"<b>✅ Report sent to admin.</b>\n"
                f"<b>They'll contact you via {esc(OWNER_USERNAME)}</b>",
                reply_markup=home_kb(),
            )
        except Exception:
            await message.reply_text("<b>❌ Error. Try again later.</b>")
        user_state.pop(user.id, None)
    else:
        # Guarded: a replayed/duplicate update (or rapid re-taps) can no
        # longer spam this same message in a loop after a redeploy.
        if _should_send_fallback(message):
            await message.reply_text("<b>👋 Use /start to navigate the bot.</b>", reply_markup=home_kb())
