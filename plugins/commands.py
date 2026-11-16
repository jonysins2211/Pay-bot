import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from info import BOTS, ADMIN_IDS, ADMIN_GROUP, OWNER_USERNAME
from keyboards import home_kb, myplan_kb
from utils import (
    user_state, pending_pays, reply_if_banned, ban_message, esc,
    start_payment,
)
from database.db import (
    get_subs, get_history, get_all_subs, get_all_pending, get_all_history,
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
    # One Renew button per subscription — renews the same plan in one tap.
    await message.reply_text("\n".join(lines), reply_markup=myplan_kb(subs))


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


@Client.on_message(filters.command("mypayments") & filters.private)
async def mypayments_cmd(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    uid = message.from_user.id
    lines = ["<b>💳 YOUR PAYMENTS</b>\n"]

    # Currently pending payments (started, not yet approved/rejected).
    all_pending = await get_all_pending()
    mine = [(pid, p) for pid, p in all_pending.items() if p.get("user_id") == uid]
    for pid, p in mine:
        bot  = BOTS.get(p["bot_key"], {})
        plan = bot.get("plans", {}).get(p["plan_key"], {})
        state = user_state.get(uid, {})
        if state.get("awaiting_screenshot") and state.get("pending_id") == pid:
            status = "⏳ Awaiting screenshot"
        else:
            status = "⏳ Under review"
        lines.append(
            f"<b>• {esc(bot.get('name', '?'))} — ₹{esc(p['amount'])}</b>\n"
            f"<blockquote><b>📅 {esc(plan.get('label', '?'))} | {esc(status)}</b></blockquote>\n"
        )

    # Past payments (approved / rejected), latest 10.
    history = await get_history(uid)
    for i, tx in enumerate(history[-10:], 1):
        lines.append(
            f"<b>{i}. {esc(tx.get('bot_name', '?'))} — ₹{esc(tx.get('amount', '?'))}</b>\n"
            f"<blockquote><b>📅 {esc(tx.get('plan', '?'))} | 🕐 {esc(tx.get('date', '?'))} | {esc(tx.get('status', '?'))}</b></blockquote>\n"
        )

    if not mine and not history:
        await message.reply_text(
            "<b>💳 YOUR PAYMENTS</b>\n\n"
            "<blockquote><b>❌ No payments found.</b></blockquote>\n\n"
            "<b>Use /start to buy a premium plan!</b>",
            reply_markup=home_kb(),
        )
        return
    await message.reply_text("\n".join(lines), reply_markup=home_kb())


@Client.on_message(filters.command("stats") & filters.private)
async def stats_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    today = datetime.now().date()
    all_subs = await get_all_subs()
    active_subs = 0
    active_users = 0
    for subs in all_subs.values():
        has_active = False
        for sub in subs:
            raw = sub.get("expiry_raw")
            if not raw:
                active_subs += 1
                has_active = True
                continue
            try:
                if datetime.strptime(raw, "%Y-%m-%d").date() >= today:
                    active_subs += 1
                    has_active = True
            except Exception:
                continue
        if has_active:
            active_users += 1

    pending_count = len(await get_all_pending())

    # Revenue from approved payments (history dates are "%d %b %Y").
    month_revenue = 0
    total_revenue = 0
    approved_count = 0
    all_history = await get_all_history()
    for txs in all_history.values():
        for tx in txs:
            if tx.get("status") != "✅ Approved":
                continue
            try:
                amount = int(tx.get("amount", 0))
            except Exception:
                continue
            approved_count += 1
            total_revenue += amount
            try:
                d = datetime.strptime(tx.get("date", ""), "%d %b %Y").date()
                if d.year == today.year and d.month == today.month:
                    month_revenue += amount
            except Exception:
                continue

    await message.reply_text(
        f"<b>📊 BOT STATS</b>\n\n"
        f"<blockquote><b>👥 Premium users: <code>{active_users}</code>\n"
        f"✅ Active subscriptions: <code>{active_subs}</code>\n"
        f"⏳ Pending verifications: <code>{pending_count}</code>\n"
        f"🧾 Approved payments: <code>{approved_count}</code></b></blockquote>\n\n"
        f"<blockquote><b>💰 Revenue this month: ₹{month_revenue}\n"
        f"💰 Total revenue: ₹{total_revenue}</b></blockquote>",
    )


@Client.on_message(filters.command("createlink") & filters.private)
async def createlink_cmd(client: Client, message: Message):
    """Create a payment link for a specific user (admin, custom deals).

    Usage: /createlink <user_id> <bot_key> <plan_key> [amount]
    The payment message is sent straight to that user (Pay Now +
    Resend Link + screenshot prompt), at the plan price or the custom
    amount if one is given. The user does not have to /start first.
    """
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 4:
        await message.reply_text(
            "<b>Usage: <code>/createlink &lt;user_id&gt; &lt;bot_key&gt; &lt;plan_key&gt; [amount]</code></b>\n\n"
            f"<b>Bot keys:</b> <code>{esc(', '.join(BOTS.keys()))}</code>\n"
            "<b>Plan keys:</b> <code>1m, 2m, 3m, 6m, 12m</code>\n"
            "<b>Amount is optional — without it the plan price is used.</b>",
        )
        return

    _, user_id_s, bot_key, plan_key = parts[:4]
    amount = None
    if len(parts) > 4:
        try:
            amount = int(parts[4])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("<b>❌ Amount must be a positive number.</b>")
            return

    if not user_id_s.isdigit():
        await message.reply_text("<b>❌ user_id must be a number.</b>")
        return
    target_id = int(user_id_s)

    bot  = BOTS.get(bot_key)
    plan = bot["plans"].get(plan_key) if bot else None
    if not bot or not plan:
        await message.reply_text("<b>❌ Unknown bot or plan. Check the keys and try again.</b>")
        return

    # Best-effort: fetch the user's name for the payment record.
    username, first_name = "N/A", "User"
    try:
        target = await client.get_users(target_id)
        username = target.username or "N/A"
        first_name = target.first_name or "User"
    except Exception:
        pass

    try:
        pid, link = await start_payment(
            client, target_id, bot_key, plan_key,
            amount=amount, username=username, first_name=first_name,
        )
    except Exception as e:
        logger.warning(f"createlink to {target_id}: {e}")
        await message.reply_text(
            f"<b>❌ Could not send the payment to <code>{target_id}</code>.</b>\n"
            "<b>They may not have started the bot yet.</b>",
        )
        return

    price = amount if amount is not None else plan["price"]
    await message.reply_text(
        f"<b>✅ PAYMENT LINK SENT</b>\n\n"
        f"<blockquote><b>👤 User ID: <code>{target_id}</code>\n"
        f"🤖 Bot: {esc(bot['name'])}\n"
        f"📅 Plan: {esc(plan['label'])}\n"
        f"💰 Amount: ₹{price}\n"
        f"🔗 Link: <a href=\"{link}\">{link}</a></b></blockquote>\n\n"
        f"<b>🔑 Payment ID: <code>{esc(pid)}</code></b>",
    )


@Client.on_message(filters.command("addpromo") & filters.private)
async def addpromo_cmd(client: Client, message: Message):
    """Create a promo / discount code (admin).

    Usage: /addpromo <CODE> <discount> [max_uses]
    discount: 50% = 50 percent off, 10 = flat ₹10 off.
    max_uses is optional (no limit if omitted).
    """
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text(
            "<b>Usage: <code>/addpromo &lt;CODE&gt; &lt;discount&gt; [max_uses]</code></b>\n\n"
            "<b>discount: <code>50%</code> = 50% off, <code>10</code> = flat ₹10 off.</b>\n"
            "<b>Example: <code>/addpromo DIWALI50 50%</code></b>",
        )
        return

    code = parts[1].strip().upper()
    disc = parts[2].strip()
    if disc.endswith("%"):
        try:
            value = int(disc[:-1])
        except ValueError:
            await message.reply_text("<b>❌ Discount must be a number, e.g. <code>50%</code> or <code>10</code>.</b>")
            return
        if not 1 <= value <= 100:
            await message.reply_text("<b>❌ Percent must be between 1 and 100.</b>")
            return
        dtype = "percent"
    else:
        try:
            value = int(disc)
        except ValueError:
            await message.reply_text("<b>❌ Discount must be a number, e.g. <code>50%</code> or <code>10</code>.</b>")
            return
        if value < 1:
            await message.reply_text("<b>❌ Flat discount must be at least ₹1.</b>")
            return
        dtype = "flat"

    max_uses = None
    if len(parts) > 3:
        try:
            max_uses = int(parts[3])
            if max_uses < 1:
                raise ValueError
        except ValueError:
            await message.reply_text("<b>❌ max_uses must be a positive number.</b>")
            return

    from database.db import add_promo
    await add_promo(code, {
        "type": dtype,
        "value": value,
        "max_uses": max_uses,
        "uses": 0,
        "created_at": datetime.now().strftime("%d %b %Y"),
        "created_by": message.from_user.id,
    })
    disc_text = f"{value}% off" if dtype == "percent" else f"₹{value} off"
    uses_text = f" (max {max_uses} uses)" if max_uses else " (unlimited uses)"
    await message.reply_text(
        f"<b>✅ PROMO CODE CREATED</b>\n\n"
        f"<blockquote><b>🎟️ Code: <code>{esc(code)}</code>\n"
        f"💰 Discount: {esc(disc_text)}{esc(uses_text)}</b></blockquote>\n\n"
        f"<b>Users tap “Apply Promo Code” on the payment message and send this code.</b>",
    )


@Client.on_message(filters.command("delpromo") & filters.private)
async def delpromo_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("<b>Usage: <code>/delpromo &lt;CODE&gt;</code></b>")
        return
    code = parts[1].strip().upper()
    from database.db import del_promo, get_promo
    if not await get_promo(code):
        await message.reply_text(f"<b>❌ No promo code <code>{esc(code)}</code> found.</b>")
        return
    await del_promo(code)
    await message.reply_text(f"<b>✅ Promo code <code>{esc(code)}</code> deleted.</b>")


@Client.on_message(filters.command("promos") & filters.private)
async def promos_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    from database.db import get_all_promos
    promos = await get_all_promos()
    if not promos:
        await message.reply_text("<b>🎟️ No promo codes yet.</b>\n<b>Create one with <code>/addpromo</code>.</b>")
        return
    lines = ["<b>🎟️ PROMO CODES:</b>\n"]
    for code, p in promos.items():
        disc = f"{p['value']}% off" if p.get("type") == "percent" else f"₹{p.get('value')} off"
        max_uses = p.get("max_uses")
        uses = p.get("uses", 0)
        status = "❌ exhausted" if max_uses is not None and uses >= max_uses else "✅ active"
        uses_text = f"{uses}/{max_uses}" if max_uses else f"{uses}/∞"
        lines.append(
            f"<blockquote><b>• <code>{esc(code)}</code> — {esc(disc)} | uses: {esc(uses_text)} | {status}</b></blockquote>\n"
        )
    await message.reply_text("\n".join(lines))


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
        f"<b><code>/stats</code> — users, active subs, pending &amp; revenue</b>\n"
        f"<b><code>/createlink &lt;user_id&gt; &lt;bot&gt; &lt;plan&gt; [amount]</code> — send a payment link to a user</b>\n"
        f"<b><code>/addpromo &lt;CODE&gt; &lt;discount&gt; [max_uses]</code> — create a promo code</b>\n"
        f"<b><code>/promos</code> — list promo codes, <code>/delpromo &lt;CODE&gt;</code> — delete one</b>\n"
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
