import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message

from info import BOTS, ADMIN_GROUP, OWNER_USERNAME
from keyboards import home_kb, admin_kb
from utils import user_state, pending_pays, cancel_expiry_by_pid, log, reply_if_banned

logger = logging.getLogger(__name__)

COMMANDS = ["start", "myplan", "myhistory", "report", "owner_cmd", "pending", "cancel", "broadcast", "ban", "unban", "bans"]


@Client.on_message(filters.private & (filters.photo | filters.document))
async def screenshot_handler(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user  = message.from_user
    state = user_state.get(user.id, {})

    if not state.get("awaiting_screenshot"):
        await message.reply_text("Please use /start to begin a subscription.")
        return

    pid     = state.get("pending_id")
    payment = pending_pays.get(pid) if pid else None
    if not pid or not payment:
        await message.reply_text("⚠️ Session expired. Please /start again.")
        return

    cancel_expiry_by_pid(pid)

    bot_key  = payment["bot_key"]
    plan_key = payment["plan_key"]
    bot      = BOTS[bot_key]
    plan     = bot["plans"][plan_key]
    uname    = f"@{user.username}" if user.username else "No username"

    admin_caption = (
        f"📸 **PAYMENT SCREENSHOT**\n\n"
        f"👤 **User:** [{user.first_name}](tg://user?id={user.id})\n"
        f"🔗 **Username:** {uname}\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"🤖 **Bot:** {bot['name']} (`{bot['username']}`)\n"
        f"📅 **Plan:** {plan['label']}\n"
        f"💰 **Amount:** ₹{plan['price']}\n"
        f"🕐 `{datetime.now().strftime('%d %b %Y %H:%M:%S')}`\n"
        f"🔑 ID: `{pid}`"
    )

    if not ADMIN_GROUP:
        await message.reply_text("❌ Admin group not configured. Contact owner.")
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
        await message.reply_text("❌ Error sending to admin. Try again.")
        return

    user_state.pop(user.id, None)
    await message.reply_text(
        "✅ **SCREENSHOT RECEIVED!**\n\n"
        "⏳ *Your payment is under review.*\n"
        "You'll be notified once approved.\n\n"
        "⚡ *Approvals usually take just a few minutes!*",
    )

    await log(client,
        f"📸 **SCREENSHOT RECEIVED**\n\n"
        f"👤 **User:** [{user.first_name}](tg://user?id={user.id})\n"
        f"🔗 **Username:** {uname}\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"🤖 **Bot:** {bot['name']} (`{bot['username']}`)\n"
        f"📅 **Plan:** {plan['label']}\n"
        f"💰 **Amount:** ₹{plan['price']}\n"
        f"🕐 `{datetime.now().strftime('%d %b %Y %H:%M:%S')}`\n"
        f"⏳ **Awaiting Admin Approval**"
    )


@Client.on_message(filters.private & filters.text & ~filters.command(COMMANDS))
async def text_handler(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user  = message.from_user
    state = user_state.get(user.id, {})

    if state.get("action") == "report":
        try:
            await client.send_message(
                ADMIN_GROUP,
                f"⚠️ **USER REPORT**\n\n"
                f"👤 [{user.first_name}](tg://user?id={user.id}) (`@{user.username or 'N/A'}`)\n"
                f"🆔 `{user.id}`\n\n"
                f"📝 {message.text}"
            )
            await message.reply_text(
                f"✅ *Report sent to admin.*\nThey'll contact you via {OWNER_USERNAME}",
                reply_markup=home_kb(),
            )
        except Exception:
            await message.reply_text("❌ Error. Try again later.")
        user_state.pop(user.id, None)
    else:
        await message.reply_text("👋 Use /start to navigate the bot.", reply_markup=home_kb())
