import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from info import BOTS, ADMIN_IDS, ADMIN_GROUP, OWNER_USERNAME
from keyboards import home_kb, renew_kb
from utils import user_state, pending_pays, reply_if_banned, ban_message, esc
from database.db import (
    get_subs, get_history, get_all_subs, get_all_pending,
    ban_user, unban_user, get_all_bans
)

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    subs = await get_subs(message.from_user.id)
    if not subs:
        await message.reply_text(
            "<b>🛍️ YOUR ACTIVE VIP SUBSCRIPTIONS</b>\n\n"
            "<blockquote><b>❌ You have no active subscriptions.</b></blockquote>\n\n"
            "<b>Use /start to buy a premium plan!</b>",
            reply_markup=home_kb(),
        )
        return
    lines = ["<b>🛍️ YOUR ACTIVE VIP SUBSCRIPTIONS</b>\n"]
    for sub in subs:
        bot  = BOTS.get(sub["bot_key"], {})
        plan = bot.get("plans", {}).get(sub["plan_key"], {})
        lines.append(
            f"<blockquote><b>✅ {esc(bot.get('username', '?'))}\n"
            f"   📅 Plan: {esc(plan.get('label', '?'))}\n"
            f"   📆 Expires: {esc(sub.get('expiry', 'N/A'))}</b></blockquote>\n"
        )
    await message.reply_text("\n".join(lines), reply_markup=home_kb())


@Client.on_message(filters.command("myhistory") & filters.private)
async def myhistory_cmd(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    history = await get_history(message.from_user.id)
    if not history:
        await message.reply_text(
            "<b>📋 PAYMENT HISTORY</b>\n\n"
            "<blockquote><b>❌ No transactions found.</b></blockquote>",
            reply_markup=home_kb(),
        )
        return
    lines = ["<b>📋 YOUR PAYMENT HISTORY</b>\n"]
    for i, tx in enumerate(history[-10:], 1):
        lines.append(
            f"<b>{i}. {esc(tx.get('bot_name', '?'))} — ₹{esc(tx.get('amount', '?'))}</b>\n"
            f"<blockquote><b>📅 {esc(tx.get('plan', '?'))} | 🕐 {esc(tx.get('date', '?'))} | {esc(tx.get('status', '?'))}</b></blockquote>\n"
        )
    await message.reply_text("\n".join(lines), reply_markup=home_kb())


@Client.on_message(filters.command("report") & filters.private)
async def report_cmd(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user_state[message.from_user.id] = {"action": "report"}
    await message.reply_text(
        f"<b>⚠️ REPORT AN ISSUE</b>\n\n"
        f"<blockquote><b>Describe your issue and send it.</b></blockquote>\n"
        f"<b>Or contact: {esc(OWNER_USERNAME)}</b>",
        reply_markup=home_kb(),
    )


@Client.on_message(filters.command("owner_cmd") & filters.private)
async def owner_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    all_pending = await get_all_pending()
    all_subs    = await get_all_subs()
    pending_count = len(all_pending)
    active_count  = sum(len(v) for v in all_subs.values())
    await message.reply_text(
        f"<b>👑 ADMIN PANEL</b>\n\n"
        f"<blockquote><b>📋 Pending: <code>{pending_count}</code>\n"
        f"✅ Active Subs: <code>{active_count}</code></b></blockquote>\n\n"
        f"<b><code>/pending</code> — view pending payments</b>\n"
        f"<b><code>/broadcast &lt;msg&gt;</code> — broadcast to all users</b>\n"
        f"<b><code>/ban &lt;user_id&gt; &lt;reason&gt;</code> — block a user</b>\n"
        f"<b><code>/unban &lt;user_id&gt;</code> — unblock a user</b>\n"
        f"<b><code>/bans</code> — list banned users</b>",
    )


@Client.on_message(filters.command("pending") & filters.private)
async def pending_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    all_pending = await get_all_pending()
    if not all_pending:
        await message.reply_text("<b>✅ No pending payments.</b>")
        return
    lines = ["<b>📋 PENDING PAYMENTS:</b>\n"]
    for pid, p in all_pending.items():
        bot  = BOTS.get(p["bot_key"], {})
        plan = bot.get("plans", {}).get(p["plan_key"], {})
        lines.append(
            f"<blockquote><b>• {esc(p['username'])} (ID: <code>{esc(p['user_id'])}</code>)\n"
            f"  Bot: {esc(bot.get('name', '?'))} | {esc(plan.get('label', '?'))} | ₹{esc(p['amount'])}</b></blockquote>\n"
        )
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text.split(" ", 1)[1] if " " in message.text else ""
    if not text:
        await message.reply_text("<b>Usage: <code>/broadcast &lt;message&gt;</code></b>")
        return
    all_subs = await get_all_subs()
    count = 0
    for user_id in list(all_subs.keys()):
        try:
            # Plain text as written: no HTML parsing, so any < or & in the
            # admin's message can't break the send.
            await client.send_message(user_id, text, parse_mode=ParseMode.DISABLED)
            count += 1
        except Exception as e:
            logger.warning(f"Broadcast failed {user_id}: {e}")
    await message.reply_text(f"<b>✅ Sent to {count} users.</b>")


@Client.on_message(filters.command("ban") & filters.private)
async def ban_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split(" ", 2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.reply_text("<b>Usage: <code>/ban &lt;user_id&gt; &lt;reason&gt;</code></b>")
        return

    user_id = int(parts[1])
    reason = parts[2].strip()
    if not reason:
        await message.reply_text("<b>Usage: <code>/ban &lt;user_id&gt; &lt;reason&gt;</code></b>")
        return

    if user_id in ADMIN_IDS:
        await message.reply_text("<b>❌ Admin users cannot be banned.</b>")
        return

    await ban_user(user_id, reason, message.from_user.id)
    user_state.pop(user_id, None)
    await message.reply_text(f"<b>✅ Banned <code>{user_id}</code>.</b>\n<b>Reason: {esc(reason)}</b>")
    try:
        await client.send_message(user_id, ban_message(reason))
    except Exception as e:
        logger.warning(f"Ban notice failed {user_id}: {e}")


@Client.on_message(filters.command("unban") & filters.private)
async def unban_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("<b>Usage: <code>/unban &lt;user_id&gt;</code></b>")
        return

    user_id = int(parts[1])
    await unban_user(user_id)
    await message.reply_text(f"<b>✅ Unbanned <code>{user_id}</code>.</b>")


@Client.on_message(filters.command("bans") & filters.private)
async def bans_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    bans = await get_all_bans()
    if not bans:
        await message.reply_text("<b>✅ No banned users.</b>")
        return

    lines = ["<b>🚫 BANNED USERS:</b>\n"]
    for user_id, ban in bans.items():
        lines.append(f"<blockquote><b>• <code>{user_id}</code> — {esc(ban.get('reason', 'No reason provided.'))}</b></blockquote>")
    await message.reply_text("\n".join(lines))
