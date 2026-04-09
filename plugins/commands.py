import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from info import BOTS, ADMIN_IDS, ADMIN_GROUP, OWNER_USERNAME
from keyboards import home_kb, renew_kb
from utils import user_state, pending_pays
from database.db import get_subs, get_history, get_all_subs, get_all_pending

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(client: Client, message: Message):
    subs = await get_subs(message.from_user.id)
    if not subs:
        await message.reply_text(
            "🛍️ **YOUR ACTIVE VIP SUBSCRIPTIONS**\n\n"
            "❌ *You have no active subscriptions.*\n\nUse /start to buy a premium plan!",
            reply_markup=home_kb(),
        )
        return
    lines = ["🛍️ **YOUR ACTIVE VIP SUBSCRIPTIONS**\n"]
    for sub in subs:
        bot  = BOTS.get(sub["bot_key"], {})
        plan = bot.get("plans", {}).get(sub["plan_key"], {})
        lines.append(
            f"✅ **{bot.get('username', '?')}**\n"
            f"   📅 Plan: *{plan.get('label', '?')}*\n"
            f"   📆 Expires: *{sub.get('expiry', 'N/A')}*\n"
        )
    await message.reply_text("\n".join(lines), reply_markup=home_kb())


@Client.on_message(filters.command("myhistory") & filters.private)
async def myhistory_cmd(client: Client, message: Message):
    history = await get_history(message.from_user.id)
    if not history:
        await message.reply_text(
            "📋 **PAYMENT HISTORY**\n\n❌ *No transactions found.*",
            reply_markup=home_kb(),
        )
        return
    lines = ["📋 **YOUR PAYMENT HISTORY**\n"]
    for i, tx in enumerate(history[-10:], 1):
        lines.append(
            f"*{i}.* {tx.get('bot_name', '?')} — ₹{tx.get('amount', '?')}\n"
            f"    📅 {tx.get('plan', '?')} | 🕐 {tx.get('date', '?')} | {tx.get('status', '?')}\n"
        )
    await message.reply_text("\n".join(lines), reply_markup=home_kb())


@Client.on_message(filters.command("report") & filters.private)
async def report_cmd(client: Client, message: Message):
    user_state[message.from_user.id] = {"action": "report"}
    await message.reply_text(
        f"⚠️ **REPORT AN ISSUE**\n\nDescribe your issue and send it.\n"
        f"Or contact: {OWNER_USERNAME}",
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
        f"👑 **ADMIN PANEL**\n\n"
        f"📋 Pending: `{pending_count}`\n"
        f"✅ Active Subs: `{active_count}`\n\n"
        f"`/pending` — view pending payments\n"
        f"`/broadcast <msg>` — broadcast to all users",
    )


@Client.on_message(filters.command("pending") & filters.private)
async def pending_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    all_pending = await get_all_pending()
    if not all_pending:
        await message.reply_text("✅ No pending payments.")
        return
    lines = ["📋 **PENDING PAYMENTS:**\n"]
    for pid, p in all_pending.items():
        bot  = BOTS.get(p["bot_key"], {})
        plan = bot.get("plans", {}).get(p["plan_key"], {})
        lines.append(
            f"• **{p['username']}** (ID: `{p['user_id']}`)\n"
            f"  Bot: {bot.get('name', '?')} | {plan.get('label', '?')} | ₹{p['amount']}\n"
        )
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text.split(" ", 1)[1] if " " in message.text else ""
    if not text:
        await message.reply_text("Usage: /broadcast <message>")
        return
    all_subs = await get_all_subs()
    count = 0
    for user_id in list(all_subs.keys()):
        try:
            await client.send_message(user_id, text)
            count += 1
        except Exception as e:
            logger.warning(f"Broadcast failed {user_id}: {e}")
    await message.reply_text(f"✅ Sent to {count} users.")
