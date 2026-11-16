import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from info import BANNER_IMAGE
from keyboards import main_menu_kb, home_kb
from utils import user_state, clear_user_pending, reply_if_banned, esc

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user = message.from_user
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

    if BANNER_IMAGE:
        await message.reply_photo(
            photo=BANNER_IMAGE,
            caption=welcome,
            reply_markup=main_menu_kb()
        )
    else:
        await message.reply_text(welcome, reply_markup=main_menu_kb())


@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client: Client, message: Message):
    if await reply_if_banned(message):
        return

    user  = message.from_user
    await clear_user_pending(user.id, client)
    user_state.pop(user.id, None)
    await message.reply_text(
        "<b>❌ Process cancelled.</b>\n"
        "<b>Use /start to begin again.</b>",
        reply_markup=home_kb(),
    )
