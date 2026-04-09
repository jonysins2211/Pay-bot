import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from info import BOTS, BANNER_IMAGE
from keyboards import main_menu_kb, home_kb
from utils import user_state, cancel_expiry, pending_pays, cancel_expiry_by_pid

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user = message.from_user
    cancel_expiry(user.id)
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
    user  = message.from_user
    state = user_state.get(user.id, {})
    pid   = state.get("pending_id")
    if pid:
        pending_pays.pop(pid, None)
        cancel_expiry_by_pid(pid)
    user_state.pop(user.id, None)
    await message.reply_text(
        "❌ *Process cancelled.*\nUse /start to begin again.",
        reply_markup=home_kb(),
    )
