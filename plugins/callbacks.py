import asyncio
import base64
import logging
import os
from datetime import datetime, timedelta
from io import BytesIO
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from info import BOTS, ADMIN_IDS, LOGS_CHANNEL, SUPPORT_GROUP, OWNER_USERNAME, UPDATES_CHANNEL, QR_EXPIRY_SECONDS
from keyboards import (
    main_menu_kb, plan_kb, home_kb, expired_kb,
    help_kb, admin_kb, renew_kb, pay_kb, telegram_url
)
from utils import (
    user_state, pending_pays, expiry_tasks,
    payment_link, make_pending_id, fmt_dt, log,
    cancel_expiry_by_pid, qr_expiry_timer, clear_user_pending, answer_if_banned, esc
)
from database.db import (
    add_pending, get_pending, del_pending,
    add_sub, get_subs, add_history
)

logger = logging.getLogger(__name__)

# Payment banner shown instead of the QR code. Stored as base64 text
# (assets/pay_banner.b64) because the repo push carries text files only.
# The QR still lives on the payment-link page (/pay/<pid>).
PAY_BANNER_B64 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
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


@Client.on_callback_query()
async def callbacks(client: Client, query: CallbackQuery):
    data = query.data
    user = query.from_user

    if await answer_if_banned(query):
        return

    # ── HOME ──────────────────────────────────────────────────
    if data == "home":
        await clear_user_pending(user.id, client)
        user_state.pop(user.id, None)

        welcome = (
            f"<b>👋 Hello {esc(user.first_name)}!</b>\n\n"
            f"<b>🚀 Welcome to ML Payment Bot!</b>\n"
            f"<b>💳 Fast • Secure • Reliable Payments</b>\n\n"
            f"<b>✨ What you can do:</b>\n"
            f"<blockquote><b>• Access Premium Bots\n"
            f"• Premium Files to Link bots\n"
            f"• Get Combo Deals\n"
            f"• Instant Support</b></blockquote>\n\n"
            f"<b>👇 Use the buttons below to continue</b>"
        )
        try:
            await query.message.edit_text(welcome, reply_markup=main_menu_kb())
        except Exception:
            await query.message.reply_text(welcome, reply_markup=main_menu_kb())
        await query.answer()

    # ── SELECT BOT ────────────────────────────────────────────
    elif data.startswith("bot:"):
        bot_key = data.split(":")[1]
        bot = BOTS.get(bot_key)
        if not bot:
            await query.answer("Bot not found!", show_alert=True)
            return
        user_state[user.id] = {"bot_key": bot_key}
        try:
            await query.message.edit_text(bot["description"], reply_markup=plan_kb(bot_key))
        except Exception:
            await query.message.reply_text(bot["description"], reply_markup=plan_kb(bot_key))
        await query.answer()

    # ── SELECT PLAN ───────────────────────────────────────────
    elif data.startswith("plan:"):
        _, bot_key, plan_key = data.split(":")
        bot  = BOTS.get(bot_key)
        plan = bot["plans"].get(plan_key) if bot else None
        if not bot or not plan:
            await query.answer("Plan not found!", show_alert=True)
            return

        await clear_user_pending(user.id, client)

        amount = plan["price"]
        label  = plan["label"]
        note   = f"Premium {bot['username']} {label}"
        pid    = make_pending_id(user.id, bot_key, plan_key)

        pay_data = {
            "user_id":    user.id,
            "username":   user.username or "N/A",
            "first_name": user.first_name,
            "bot_key":    bot_key,
            "plan_key":   plan_key,
            "amount":     amount,
            "ts":         datetime.now().isoformat(),
            "chat_id":    query.message.chat.id,
        }
        # Save to memory + MongoDB
        pending_pays[pid] = pay_data
        await add_pending(pid, pay_data)

        user_state[user.id] = {
            "bot_key":             bot_key,
            "plan_key":            plan_key,
            "pending_id":          pid,
            "chat_id":             query.message.chat.id,
            "awaiting_screenshot": True,
        }

        # No QR in the bot any more — the banner image goes here instead.
        # The QR still lives on the payment-link page (/pay/<pid>) for anyone
        # who wants to scan it. The Pay Now button opens the payment page
        # (Telegram buttons only allow https links, not upi://) — the page
        # itself has the button that opens the UPI app.
        link = payment_link(pid)
        caption = (
            f"<b>🧾 PAYMENT DETAILS:</b>\n\n"
            f"<blockquote><b>• PAY ₹{amount} — PREMIUM TIME: {esc(label)}\n"
            f"• PAYMENT LINK VALID FOR 5 MINUTES</b></blockquote>\n\n"
            f"<b>💳 TAP “PAY NOW” BELOW TO OPEN THE PAYMENT PAGE</b>\n"
            f"<b>🔗 Payment Link:</b> <a href=\"{link}\">{link}</a>\n\n"
            f"<b>⚠️ AFTER PAYMENT:</b>\n"
            f"<b>📸 SEND THE PAYMENT SCREENSHOT HERE</b>"
        )
        banner = pay_banner_photo()
        if banner is not None:
            pay_msg = await query.message.reply_photo(
                photo=banner, caption=caption, reply_markup=pay_kb(link),
            )
        else:
            # Banner missing (e.g. fresh checkout without the asset) — text only.
            pay_msg = await query.message.reply_text(caption, reply_markup=pay_kb(link))
        proof_msg = await query.message.reply_text(
            "<b>📸 SEND A SCREENSHOT OF THE PAYMENT FOR VERIFICATION.</b>\n\n"
            "<b>Use /cancel to cancel the process.</b>"
        )
        user_state[user.id]["qr_message_id"] = pay_msg.id
        user_state[user.id]["proof_message_id"] = proof_msg.id
        await query.answer()

        uname = f"@{user.username}" if user.username else "No username"
        await log(client,
            f"<b>🔔 QR CODE GENERATED</b>\n\n"
            f"<b>👤 User:</b> <a href=\"tg://user?id={user.id}\">{esc(user.first_name)}</a>\n"
            f"<b>🔗 Username:</b> {esc(uname)}\n"
            f"<b>🆔 User ID:</b> <code>{user.id}</code>\n"
            f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
            f"<b>📅 Plan:</b> {esc(label)}\n"
            f"<b>💰 Amount:</b> ₹{amount}\n"
            f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>\n"
            f"<b>⏳ QR valid for 5 minutes</b>"
        )

        task = asyncio.create_task(
            qr_expiry_timer(client, user.id, pid, bot_key, plan_key, query.message.chat.id)
        )
        expiry_tasks[pid] = task

    # ── RESTART ───────────────────────────────────────────────
    elif data.startswith("restart:"):
        _, bot_key, plan_key = data.split(":")
        bot = BOTS.get(bot_key)
        if not bot:
            await query.answer()
            return
        try:
            await query.message.edit_text(bot["description"], reply_markup=plan_kb(bot_key))
        except Exception:
            await query.message.reply_text(bot["description"], reply_markup=plan_kb(bot_key))
        await query.answer()

    # ── PREMIUM PROOF ─────────────────────────────────────────
    elif data == "proof":
        text = (
            "<b>🧾 PREMIUM PROOF</b>\n\n"
            "<blockquote><b>✅ All payments verified by admin.\n"
            "💎 Hundreds of happy VIP members!\n"
            "📌 For proofs, contact Admin</b></blockquote>\n\n"
            f"<b>Msg: {esc(OWNER_USERNAME)}</b>"
        )
        try:
            await query.message.edit_text(text, reply_markup=home_kb())
        except Exception:
            await query.message.reply_text(text, reply_markup=home_kb())
        await query.answer()

    # ── TUTORIAL ──────────────────────────────────────────────
    elif data == "tutorial":
        text = (
            "<b>🎓 HOW TO BUY PREMIUM</b>\n\n"
            "<blockquote><b>Step 1 — Click the bot you want\n"
            "Step 2 — Select your plan\n"
            "Step 3 — Pay via QR Code or UPI ID\n"
            "Step 4 — Screenshot the confirmation\n"
            "Step 5 — Send screenshot here\n"
            "Step 6 — Wait for admin approval\n"
            "Step 7 — 🎉 Premium Activated!</b></blockquote>"
        )
        try:
            await query.message.edit_text(text, reply_markup=home_kb())
        except Exception:
            await query.message.reply_text(text, reply_markup=home_kb())
        await query.answer()

    # ── HELP ──────────────────────────────────────────────────
    elif data == "help":
        text = (
            "<b>👑 PREMIUM SUPPORT &amp; HELP DESK 💎</b>\n\n"
            "<blockquote><b>FOR QUERIES RELATED TO SUBSCRIPTIONS, OUR TEAM IS HERE 24/7. ⚡</b></blockquote>\n\n"
            "<b>📋 VIP TERMS &amp; CONDITIONS:</b>\n"
            "<blockquote><b>◆ SEND A CLEAR SCREENSHOT (FAKE = INSTANT BAN)\n"
            "◆ APPROVALS ARE QUICK BUT NEED VERIFICATION\n"
            "◆ ALL PURCHASES ARE FINAL &amp; NON-REFUNDABLE</b></blockquote>\n\n"
            f"<b>💠 ADMIN: {esc(OWNER_USERNAME)}</b>\n"
            f"<b>💠 COMMUNITY: {esc(SUPPORT_GROUP)}</b>\n\n"
            "<b>UPGRADE YOUR EXPERIENCE TODAY! 💎</b>"
        )
        try:
            await query.message.edit_text(text, reply_markup=help_kb())
        except Exception:
            await query.message.reply_text(text, reply_markup=help_kb())
        await query.answer()

    # ── ABOUT ──────────────────────────────────────────────────
    elif data == "about":
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        text = (
            "<b>┌── [ Payment Bot ] ──┐\n"
            "  ➤ 🤖 MY NAME : Payment Bot\n"
            "  ➤ 👑 OWNER : ML Owner\n"
            "  ➤ 📡 HOSTED ON : Heroku\n"
            "  ➤ 🌐 LANGUAGE : Python 3\n"
            "  ➤ 📚 LIBRARY : Pyrofork\n"
            "  ➤ 📋 VERSION : Advance v3.0\n"
            "└─────────────────────┘</b>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ℹ️ NEED HELP / SUPPORT",
                                  url=telegram_url(SUPPORT_GROUP))],
            [InlineKeyboardButton("🏠 HOME", callback_data="home"),
             InlineKeyboardButton("✖️ CLOSE", callback_data="close")],
        ])
        try:
            await query.message.edit_text(text, reply_markup=kb)
        except Exception:
            await query.message.reply_text(text, reply_markup=kb)
        await query.answer()

    # ── CLOSE ─────────────────────────────────────────────────
    elif data == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()

    # ── ADMIN APPROVE ─────────────────────────────────────────
    elif data.startswith("approve:"):
        if user.id not in ADMIN_IDS:
            await query.answer("⛔ Not authorized!", show_alert=True)
            return

        pid = data.split(":", 1)[1]
        # Check memory first, then DB
        payment = pending_pays.get(pid) or await get_pending(pid)
        if not payment:
            await query.answer("⚠️ Already processed.", show_alert=True)
            return

        bot_key   = payment["bot_key"]
        plan_key  = payment["plan_key"]
        bot       = BOTS[bot_key]
        plan      = bot["plans"][plan_key]
        uid       = payment["user_id"]
        expiry_dt  = datetime.now() + timedelta(days=plan["days"])
        expiry_str = fmt_dt(expiry_dt)

        cancel_expiry_by_pid(pid)

        # Save subscription to MongoDB
        sub = {
            "bot_key":    bot_key,
            "plan_key":   plan_key,
            "expiry":     expiry_str,
            "expiry_raw": expiry_dt.strftime("%Y-%m-%d"),
        }
        await add_sub(uid, sub)

        # Save history to MongoDB
        await add_history(uid, {
            "bot_name": bot["name"],
            "plan":     plan["label"],
            "amount":   plan["price"],
            "date":     datetime.now().strftime("%d %b %Y"),
            "status":   "✅ Approved",
        })

        try:
            await client.send_message(
                uid,
                f"<b>🎉 PREMIUM ACTIVATED!</b>\n\n"
                f"<blockquote><b>✅ Payment approved by admin.\n"
                f"🤖 Bot: {esc(bot['username'])}\n"
                f"📅 Plan: {esc(plan['label'])}\n"
                f"📆 Valid Until: {esc(expiry_str)}</b></blockquote>\n\n"
                f"<b>Enjoy all premium features! 🚀</b>\n"
                f"<b>Join: {esc(SUPPORT_GROUP)}</b>",
            )
        except Exception as e:
            logger.error(f"Notify user {uid}: {e}")

        await query.answer("✅ Approved!")
        try:
            orig = query.message.caption or query.message.text or ""
            new_text = orig + f"\n\n<b>✅ APPROVED</b> by @{esc(user.username or user.first_name)}"
            if query.message.caption:
                await query.message.edit_caption(new_text)
            else:
                await query.message.edit_text(new_text)
        except Exception:
            pass

        uname = f"@{payment['username']}" if payment['username'] != "N/A" else "No username"
        await log(client,
            f"<b>✅ PAYMENT APPROVED</b>\n\n"
            f"<b>👤 User:</b> <a href=\"tg://user?id={uid}\">{esc(payment['first_name'])}</a>\n"
            f"<b>🔗 Username:</b> {esc(uname)}\n"
            f"<b>🆔 User ID:</b> <code>{uid}</code>\n"
            f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
            f"<b>📅 Plan:</b> {esc(plan['label'])}\n"
            f"<b>💰 Amount:</b> ₹{plan['price']}\n"
            f"<b>📆 Valid Until:</b> {esc(expiry_str)}\n"
            f"<b>👮 Approved by:</b> @{esc(user.username or user.first_name)}\n"
            f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>"
        )
        pending_pays.pop(pid, None)
        await del_pending(pid)

    # ── ADMIN REJECT ──────────────────────────────────────────
    elif data.startswith("reject:"):
        if user.id not in ADMIN_IDS:
            await query.answer("⛔ Not authorized!", show_alert=True)
            return

        pid = data.split(":", 1)[1]
        payment = pending_pays.get(pid) or await get_pending(pid)
        if not payment:
            await query.answer("⚠️ Already processed.", show_alert=True)
            return

        bot_key  = payment["bot_key"]
        plan_key = payment["plan_key"]
        bot      = BOTS[bot_key]
        plan     = bot["plans"][plan_key]
        uid      = payment["user_id"]

        cancel_expiry_by_pid(pid)

        await add_history(uid, {
            "bot_name": bot["name"],
            "plan":     plan["label"],
            "amount":   plan["price"],
            "date":     datetime.now().strftime("%d %b %Y"),
            "status":   "❌ Rejected",
        })

        try:
            await client.send_message(
                uid,
                f"<b>❌ PAYMENT REJECTED</b>\n\n"
                f"<blockquote><b>Screenshot for {esc(bot['name'])} ({esc(plan['label'])}) not approved.</b></blockquote>\n\n"
                f"<b>Contact: {esc(OWNER_USERNAME)}</b>\n"
                f"<b>Or /start to try again.</b>",
            )
        except Exception as e:
            logger.error(f"Notify reject {uid}: {e}")

        await query.answer("❌ Rejected.")
        try:
            orig = query.message.caption or query.message.text or ""
            new_text = orig + f"\n\n<b>❌ REJECTED</b> by @{esc(user.username or user.first_name)}"
            if query.message.caption:
                await query.message.edit_caption(new_text)
            else:
                await query.message.edit_text(new_text)
        except Exception:
            pass

        uname = f"@{payment['username']}" if payment['username'] != "N/A" else "No username"
        await log(client,
            f"<b>❌ PAYMENT REJECTED</b>\n\n"
            f"<b>👤 User:</b> <a href=\"tg://user?id={uid}\">{esc(payment['first_name'])}</a>\n"
            f"<b>🔗 Username:</b> {esc(uname)}\n"
            f"<b>🆔 User ID:</b> <code>{uid}</code>\n"
            f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
            f"<b>📅 Plan:</b> {esc(plan['label'])}\n"
            f"<b>💰 Amount:</b> ₹{plan['price']}\n"
            f"<b>👮 Rejected by:</b> @{esc(user.username or user.first_name)}\n"
            f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>"
        )
        pending_pays.pop(pid, None)
        await del_pending(pid)

    else:
        await query.answer()
