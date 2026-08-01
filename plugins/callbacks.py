import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from info import BOTS, ADMIN_IDS, LOGS_CHANNEL, SUPPORT_GROUP, OWNER_USERNAME, UPDATES_CHANNEL, QR_EXPIRY_SECONDS
from keyboards import (
    main_menu_kb, plan_kb, home_kb, expired_kb,
    help_kb, admin_kb, renew_kb, telegram_url
)
from utils import (
    user_state, pending_pays, expiry_tasks,
    make_qr, make_pending_id, fmt_dt, log,
    cancel_expiry_by_pid, qr_expiry_timer, clear_user_pending, answer_if_banned
)
from database.db import (
    add_pending, get_pending, del_pending,
    add_sub, get_subs, add_history
)

logger = logging.getLogger(__name__)


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
            f"👋 **Hello {user.first_name}!**\n\n"
            f"🚀 **Welcome to ML Payment Bot!**\n"
            f"💳 *Fast • Secure • Reliable Payments*\n\n"
            f"✨ **What you can do:**\n"
            f"• Access Premium Bots\n"
            f"• Premium Files to Link bots\n"
            f"• Get Combo Deals\n"
            f"• Instant Support\n\n"
            f"👇 **Use the buttons below to continue**"
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

        qr_buf = make_qr(amount, note)
        qr_msg = await query.message.reply_photo(
            photo=qr_buf,
            caption=(
                f"🧾 **PAYMENT DETAILS:**\n\n"
                f"• SCAN THE QR CODE AND PAY **₹{amount}**\n"
                f"• PREMIUM TIME: **{label}**\n"
                f"• QR CODE VALID FOR **5 MINUTES**\n\n"
                f"⚠️ **AFTER PAYMENT:**\n"
                f"📸 • SEND THE PAYMENT SCREENSHOT HERE"
            ),
        )
        proof_msg = await query.message.reply_text(
            "📸 **SEND A SCREENSHOT OF THE PAYMENT FOR VERIFICATION.**\n\n"
            "*USE* /cancel *TO CANCEL THE PROCESS.*"
        )
        user_state[user.id]["qr_message_id"] = qr_msg.id
        user_state[user.id]["proof_message_id"] = proof_msg.id
        await query.answer()

        uname = f"@{user.username}" if user.username else "No username"
        await log(client,
            f"🔔 **QR CODE GENERATED**\n\n"
            f"👤 **User:** [{user.first_name}](tg://user?id={user.id})\n"
            f"🔗 **Username:** {uname}\n"
            f"🆔 **User ID:** `{user.id}`\n"
            f"🤖 **Bot:** {bot['name']} (`{bot['username']}`)\n"
            f"📅 **Plan:** {label}\n"
            f"💰 **Amount:** ₹{amount}\n"
            f"🕐 `{datetime.now().strftime('%d %b %Y %H:%M:%S')}`\n"
            f"⏳ QR valid for 5 minutes"
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
            "🧾 **PREMIUM PROOF**\n\n"
            "✅ *All payments verified by admin.*\n\n"
            "💎 Hundreds of happy VIP members!\n"
            "📌 For Proofs You can contact Admin\n"
            f"Msg: {OWNER_USERNAME}"
        )
        try:
            await query.message.edit_text(text, reply_markup=home_kb())
        except Exception:
            await query.message.reply_text(text, reply_markup=home_kb())
        await query.answer()

    # ── TUTORIAL ──────────────────────────────────────────────
    elif data == "tutorial":
        text = (
            "🎓 **HOW TO BUY PREMIUM**\n\n"
            "**Step 1** — Click the bot you want\n"
            "**Step 2** — Select your plan\n"
            "**Step 3** — Pay via QR Code or UPI ID\n"
            "**Step 4** — Screenshot the confirmation\n"
            "**Step 5** — Send screenshot here\n"
            "**Step 6** — Wait for admin approval\n"
            "**Step 7** — 🎉 Premium Activated!"
        )
        try:
            await query.message.edit_text(text, reply_markup=home_kb())
        except Exception:
            await query.message.reply_text(text, reply_markup=home_kb())
        await query.answer()

    # ── HELP ──────────────────────────────────────────────────
    elif data == "help":
        text = (
            "👑 **PREMIUM SUPPORT & HELP DESK** 💎\n\n"
            "*FOR QUERIES RELATED TO SUBSCRIPTIONS, OUR TEAM IS HERE 24/7.* ⚡\n\n"
            "📋 **VIP TERMS & CONDITIONS:**\n"
            "◆ *SEND A CLEAR SCREENSHOT (FAKE = INSTANT BAN)*\n"
            "◆ *APPROVALS ARE QUICK BUT NEED VERIFICATION*\n"
            "◆ *ALL PURCHASES ARE FINAL & NON-REFUNDABLE*\n\n"
            f"💠 ADMIN: {OWNER_USERNAME}\n"
            f"💠 COMMUNITY: {SUPPORT_GROUP}\n\n"
            "*UPGRADE YOUR EXPERIENCE TODAY!* 💎"
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
            "┌── **[ Payment Bot ]** ──┐\n"
            "  ➤ 🤖 MY NAME : Payment Bot\n"
            "  ➤ 👑 OWNER : ML Owner\n"
            "  ➤ 📡 HOSTED ON : Heroku\n"
            "  ➤ 🌐 LANGUAGE : Python 3\n"
            "  ➤ 📚 LIBRARY : Pyrofork\n"
            "  ➤ 📋 VERSION : Advance v3.0\n"
            "└─────────────────────┘"
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
                f"🎉 **PREMIUM ACTIVATED!**\n\n"
                f"✅ *Payment approved by admin.*\n\n"
                f"🤖 Bot: **{bot['username']}**\n"
                f"📅 Plan: **{plan['label']}**\n"
                f"📆 Valid Until: **{expiry_str}**\n\n"
                f"Enjoy all premium features! 🚀\nJoin: {SUPPORT_GROUP}",
            )
        except Exception as e:
            logger.error(f"Notify user {uid}: {e}")

        await query.answer("✅ Approved!")
        try:
            orig = query.message.caption or query.message.text or ""
            new_text = orig + f"\n\n✅ **APPROVED** by @{user.username or user.first_name}"
            if query.message.caption:
                await query.message.edit_caption(new_text)
            else:
                await query.message.edit_text(new_text)
        except Exception:
            pass

        uname = f"@{payment['username']}" if payment['username'] != "N/A" else "No username"
        await log(client,
            f"✅ **PAYMENT APPROVED**\n\n"
            f"👤 **User:** [{payment['first_name']}](tg://user?id={uid})\n"
            f"🔗 **Username:** {uname}\n"
            f"🆔 **User ID:** `{uid}`\n"
            f"🤖 **Bot:** {bot['name']} (`{bot['username']}`)\n"
            f"📅 **Plan:** {plan['label']}\n"
            f"💰 **Amount:** ₹{plan['price']}\n"
            f"📆 **Valid Until:** {expiry_str}\n"
            f"👮 **Approved by:** @{user.username or user.first_name}\n"
            f"🕐 `{datetime.now().strftime('%d %b %Y %H:%M:%S')}`"
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
                f"❌ **PAYMENT REJECTED**\n\n"
                f"*Screenshot for **{bot['name']}** ({plan['label']}) not approved.*\n\n"
                f"Contact: {OWNER_USERNAME}\nOr /start to try again.",
            )
        except Exception as e:
            logger.error(f"Notify reject {uid}: {e}")

        await query.answer("❌ Rejected.")
        try:
            orig = query.message.caption or query.message.text or ""
            new_text = orig + f"\n\n❌ **REJECTED** by @{user.username or user.first_name}"
            if query.message.caption:
                await query.message.edit_caption(new_text)
            else:
                await query.message.edit_text(new_text)
        except Exception:
            pass

        uname = f"@{payment['username']}" if payment['username'] != "N/A" else "No username"
        await log(client,
            f"❌ **PAYMENT REJECTED**\n\n"
            f"👤 **User:** [{payment['first_name']}](tg://user?id={uid})\n"
            f"🔗 **Username:** {uname}\n"
            f"🆔 **User ID:** `{uid}`\n"
            f"🤖 **Bot:** {bot['name']} (`{bot['username']}`)\n"
            f"📅 **Plan:** {plan['label']}\n"
            f"💰 **Amount:** ₹{plan['price']}\n"
            f"👮 **Rejected by:** @{user.username or user.first_name}\n"
            f"🕐 `{datetime.now().strftime('%d %b %Y %H:%M:%S')}`"
        )
        pending_pays.pop(pid, None)
        await del_pending(pid)

    else:
        await query.answer()
