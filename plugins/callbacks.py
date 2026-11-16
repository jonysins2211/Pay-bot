import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from info import BOTS, ADMIN_IDS, LOGS_CHANNEL, SUPPORT_GROUP, OWNER_USERNAME, UPDATES_CHANNEL, QR_EXPIRY_SECONDS
from keyboards import (
    main_menu_kb, plan_kb, home_kb, expired_kb,
    help_kb, admin_kb, pay_kb, telegram_url, BONUS_DAYS
)
from utils import (
    user_state, pending_pays, expiry_tasks,
    payment_link, make_pending_id, fmt_dt, log,
    cancel_expiry_by_pid, cancel_nudge_by_pid, qr_expiry_timer,
    clear_user_pending, answer_if_banned, esc,
    payment_caption, start_payment,
)
from database.db import (
    add_pending, get_pending, del_pending,
    add_sub, get_subs, add_history
)

logger = logging.getLogger(__name__)


async def _approve_payment(client, query, pid: str, bonus_days: int) -> bool:
    """Approve a pending payment (shared by APPROVE and APPROVE +BONUS).

    Adds the subscription (plan days + bonus_days), records the history
    entry (with receipt_id), sends the user the activation + receipt
    messages, and clears the pending payment. Returns False if the
    payment was already processed or the user is not an admin.
    """
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.answer("⛔ Not authorized!", show_alert=True)
        return False

    # Check memory first, then DB
    payment = pending_pays.get(pid) or await get_pending(pid)
    if not payment:
        await query.answer("⚠️ Already processed.", show_alert=True)
        return False

    bot_key   = payment["bot_key"]
    plan_key  = payment["plan_key"]
    bot       = BOTS[bot_key]
    plan      = bot["plans"][plan_key]
    uid       = payment["user_id"]
    amount    = payment.get("amount", plan["price"])
    expiry_dt  = datetime.now() + timedelta(days=plan["days"] + bonus_days)
    expiry_str = fmt_dt(expiry_dt)
    bonus_line = f"\n🎁 Bonus: +{bonus_days} days" if bonus_days else ""

    cancel_expiry_by_pid(pid)
    cancel_nudge_by_pid(pid)

    # Save subscription to MongoDB
    sub = {
        "bot_key":    bot_key,
        "plan_key":   plan_key,
        "expiry":     expiry_str,
        "expiry_raw": expiry_dt.strftime("%Y-%m-%d"),
        "reminders_sent": [],
    }
    await add_sub(uid, sub)

    # Save history to MongoDB
    await add_history(uid, {
        "bot_name": bot["name"],
        "plan":     plan["label"],
        "amount":   amount,
        "date":     datetime.now().strftime("%d %b %Y"),
        "status":   "✅ Approved",
        "receipt_id": pid,
    })

    try:
        await client.send_message(
            uid,
            f"<b>🎉 PREMIUM ACTIVATED!</b>\n\n"
            f"<blockquote><b>✅ Payment approved by admin.\n"
            f"🤖 Bot: {esc(bot['username'])}\n"
            f"📅 Plan: {esc(plan['label'])}{bonus_line}\n"
            f"📆 Valid Until: {esc(expiry_str)}</b></blockquote>\n\n"
            f"<b>Enjoy all premium features! 🚀</b>\n"
            f"<b>Join: {esc(SUPPORT_GROUP)}</b>",
        )
    except Exception as e:
        logger.error(f"Notify user {uid}: {e}")

    # Payment receipt — a keepable record of the purchase.
    try:
        await client.send_message(
            uid,
            f"<b>🧾 PAYMENT RECEIPT</b>\n\n"
            f"<blockquote><b>🧾 Receipt ID: <code>{esc(pid)}</code>\n"
            f"🤖 Bot: {esc(bot['username'])}\n"
            f"📅 Plan: {esc(plan['label'])}{bonus_line}\n"
            f"💰 Amount Paid: ₹{amount}\n"
            f"📆 Paid On: {datetime.now().strftime('%d %b %Y')}\n"
            f"📆 Valid Until: {esc(expiry_str)}\n"
            f"✅ Status: Approved</b></blockquote>\n\n"
            f"<b>Keep this receipt for your records.</b>",
        )
    except Exception as e:
        logger.error(f"Receipt to user {uid}: {e}")

    await query.answer("✅ Approved!" + (f" (+{bonus_days} days bonus)" if bonus_days else ""))
    try:
        orig = query.message.caption or query.message.text or ""
        approved_tag = f"<b>✅ APPROVED</b> by @{esc(user.username or user.first_name)}"
        if bonus_days:
            approved_tag += f" <b>(+{bonus_days} DAYS BONUS)</b>"
        new_text = orig + f"\n\n{approved_tag}"
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
        f"<b>📅 Plan:</b> {esc(plan['label'])}{bonus_line}\n"
        f"<b>💰 Amount:</b> ₹{amount}\n"
        f"<b>📆 Valid Until:</b> {esc(expiry_str)}\n"
        f"<b>👮 Approved by:</b> @{esc(user.username or user.first_name)}\n"
        f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>"
    )
    pending_pays.pop(pid, None)
    await del_pending(pid)
    return True


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

        # Shared payment flow (also used by /createlink): creates the
        # pending payment, sends the payment message + screenshot
        # prompt, and starts the 5-minute expiry timer.
        await start_payment(
            client, user.id, bot_key, plan_key,
            username=user.username or "N/A", first_name=user.first_name,
        )
        await query.answer()

    # ── RESEND PAYMENT LINK ───────────────────────────────────
    # Fresh 5-minute link for the same payment, in place — the user
    # does not have to start over. Only while still awaiting the
    # screenshot; once the screenshot is sent the payment is under
    # review and a new link makes no sense.
    elif data.startswith("resend:"):
        old_pid = data.split(":", 1)[1]
        payment = pending_pays.get(old_pid) or await get_pending(old_pid)
        if not payment:
            await query.answer("⚠️ This payment link has expired. Please /start again.", show_alert=True)
            return
        state = user_state.get(user.id, {})
        if not state.get("awaiting_screenshot") or state.get("pending_id") != old_pid:
            await query.answer("⚠️ This payment is already under review.", show_alert=True)
            return

        bot_key  = payment["bot_key"]
        plan_key = payment["plan_key"]
        bot      = BOTS[bot_key]
        plan     = bot["plans"][plan_key]
        amount   = payment["amount"]
        label    = plan["label"]
        new_pid  = make_pending_id(user.id, bot_key, plan_key)

        # Retire the old pid (and its expiry timer), start the new one.
        cancel_expiry_by_pid(old_pid)
        pending_pays.pop(old_pid, None)
        await del_pending(old_pid)

        new_data = dict(payment)
        new_data["ts"] = datetime.now().isoformat()
        pending_pays[new_pid] = new_data
        await add_pending(new_pid, new_data)
        user_state[user.id]["pending_id"] = new_pid

        new_link = payment_link(new_pid)
        caption = payment_caption(amount, label, new_link)
        try:
            if query.message.photo:
                await query.message.edit_caption(
                    caption=caption, reply_markup=pay_kb(new_link, new_pid))
            else:
                await query.message.edit_text(
                    text=caption, reply_markup=pay_kb(new_link, new_pid))
        except Exception as e:
            logger.warning(f"Resend edit {old_pid}: {e}")
        await query.answer("✅ Fresh link sent! Valid for 5 minutes.")

        task = asyncio.create_task(
            qr_expiry_timer(client, user.id, new_pid, bot_key, plan_key, query.message.chat.id)
        )
        expiry_tasks[new_pid] = task
        await log(client,
            f"<b>🔄 PAYMENT LINK RESENT</b>\n\n"
            f"<b>👤 User:</b> <a href=\"tg://user?id={user.id}\">{esc(user.first_name)}</a>\n"
            f"<b>🆔 User ID:</b> <code>{user.id}</code>\n"
            f"<b>🤖 Bot:</b> {esc(bot['name'])} (<code>{esc(bot['username'])}</code>)\n"
            f"<b>📅 Plan:</b> {esc(label)} | ₹{amount}\n"
            f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>"
        )

    # ── APPLY PROMO CODE ──────────────────────────────────────
    # Asks the user to send their promo code as a text message.
    # The code is validated and applied by the text handler (which
    # sees user_state["awaiting_promo"]). Only while still awaiting
    # the screenshot; once sent, the payment is under review.
    elif data.startswith("promo:"):
        pid = data.split(":", 1)[1]
        payment = pending_pays.get(pid) or await get_pending(pid)
        if not payment:
            await query.answer("⚠️ This payment link has expired. Please /start again.", show_alert=True)
            return
        state = user_state.get(user.id, {})
        if not state.get("awaiting_screenshot") or state.get("pending_id") != pid:
            await query.answer("⚠️ This payment is already under review.", show_alert=True)
            return
        user_state[user.id]["awaiting_promo"] = pid
        await query.message.reply_text(
            "<b>🎟️ APPLY PROMO CODE</b>\n\n"
            "<blockquote><b>Send your promo code now.</b></blockquote>\n\n"
            "<b>Or /cancel to skip the promo and pay the full price.</b>",
        )
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
        pid = data.split(":", 1)[1]
        await _approve_payment(client, query, pid, bonus_days=0)

    # ── ADMIN APPROVE + BONUS DAYS ────────────────────────────
    # Same as APPROVE, but the subscription gets BONUS_DAYS extra
    # (loyal-user bonus). Note: "approve_bonus:..." does NOT start
    # with "approve:" (it is "approve_..."), so the branch above
    # never catches it.
    elif data.startswith("approve_bonus:"):
        pid = data.split(":", 1)[1]
        await _approve_payment(client, query, pid, bonus_days=BONUS_DAYS)

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
        amount   = payment.get("amount", plan["price"])

        cancel_expiry_by_pid(pid)
        cancel_nudge_by_pid(pid)

        await add_history(uid, {
            "bot_name": bot["name"],
            "plan":     plan["label"],
            "amount":   amount,
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
            f"<b>💰 Amount:</b> ₹{amount}\n"
            f"<b>👮 Rejected by:</b> @{esc(user.username or user.first_name)}\n"
            f"<code>{datetime.now().strftime('%d %b %Y %H:%M:%S')}</code>"
        )
        pending_pays.pop(pid, None)
        await del_pending(pid)

    else:
        await query.answer()
