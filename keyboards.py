from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import BOTS, OWNER_USERNAME, UPDATES_CHANNEL, SUPPORT_GROUP


def main_menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, bot in BOTS.items():
        rows.append([InlineKeyboardButton(f"✨ {bot['name']} ✨", callback_data=f"bot:{key}")])
    rows.append([
        InlineKeyboardButton("🧾 PREMIUM PROOF", callback_data="proof"),
        InlineKeyboardButton("🎓 TUTORIAL",       callback_data="tutorial"),
    ])
    rows.append([
        InlineKeyboardButton("ℹ️ HELP",  callback_data="help"),
        InlineKeyboardButton("🧑 ABOUT", callback_data="about"),
    ])
    return InlineKeyboardMarkup(rows)


def plan_kb(bot_key: str) -> InlineKeyboardMarkup:
    bot = BOTS[bot_key]
    rows = []
    for plan_key, plan in bot["plans"].items():
        rows.append([InlineKeyboardButton(
            f"💳 {plan['label']} premium for ₹{plan['price']}",
            callback_data=f"plan:{bot_key}:{plan_key}"
        )])
    rows.append([InlineKeyboardButton("🏠 HOME", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 HOME", callback_data="home")
    ]])


def expired_kb(bot_key: str, plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 MAIN MENU", callback_data="home"),
        InlineKeyboardButton("🔄 RESTART",   callback_data=f"restart:{bot_key}:{plan_key}"),
    ]])


def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📣 JOIN UPDATES", url=f"https://t.me/{UPDATES_CHANNEL.lstrip('@')}"),
            InlineKeyboardButton("📋 OWNER",         url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}"),
        ],
        [InlineKeyboardButton("🏠 HOME", callback_data="home")],
    ])


def admin_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{pending_id}"),
        InlineKeyboardButton("❌ REJECT",  callback_data=f"reject:{pending_id}"),
    ]])


def renew_kb(bot_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🔄 RENEW {BOTS[bot_key]['name']}",
            callback_data=f"bot:{bot_key}"
        )],
        [InlineKeyboardButton("🏠 MAIN MENU", callback_data="home")],
    ])
