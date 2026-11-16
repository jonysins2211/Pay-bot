from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import BOTS, OWNER_USERNAME, UPDATES_CHANNEL, SUPPORT_GROUP


def telegram_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "https://t.me"
    if value.startswith(("http://", "https://")):
        return value
    return f"https://t.me/{value.lstrip('@')}"


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


def pay_kb(pay_url: str, pid: str = "") -> InlineKeyboardMarkup:
    """Pay Now button: opens the bot's payment page in the browser.

    The Mini App (WebApp button) version did not work — the UPI button
    inside the Mini App WebView would not open the UPI app — so the
    button is a plain https link again, which opens the page in the
    user's browser (Chrome), where the upi:// link opens the UPI app.

    A second button, Resend Link, gives the user a fresh 5-minute
    payment link (new pid) without starting over.
    """
    rows = [[InlineKeyboardButton("💳 Pay Now", url=pay_url)]]
    if pid:
        rows.append([InlineKeyboardButton(
            "🔄 Resend Link", callback_data=f"resend:{pid}"
        )])
    return InlineKeyboardMarkup(rows)


def home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 HOME", callback_data="home")
    ]])


def expired_kb(bot_key: str, plan_key: str) -> InlineKeyboardMarkup:
    """Shown when the 5-minute payment window closes.

    GET NEW LINK starts a fresh payment for the same plan in one tap
    (no plan list in between) — the old RESTART button only opened
    the plan list.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 MAIN MENU", callback_data="home"),
        InlineKeyboardButton("🔄 GET NEW LINK",
                             callback_data=f"plan:{bot_key}:{plan_key}"),
    ]])


def help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📣 JOIN UPDATES", url=telegram_url(UPDATES_CHANNEL)),
            InlineKeyboardButton("📋 OWNER",         url=telegram_url(OWNER_USERNAME)),
        ],
        [InlineKeyboardButton("🏠 HOME", callback_data="home")],
    ])


def admin_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ APPROVE", callback_data=f"approve:{pending_id}"),
        InlineKeyboardButton("❌ REJECT",  callback_data=f"reject:{pending_id}"),
    ]])


def renew_plan_kb(bot_key: str, plan_key: str) -> InlineKeyboardMarkup:
    """Renew the same plan in one tap (used by expiry reminders and /myplan).

    The button goes straight to the payment flow for this exact plan
    (callback plan:<bot>:<plan>) — no plan list in between.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🔄 RENEW {BOTS[bot_key]['name']}",
            callback_data=f"plan:{bot_key}:{plan_key}"
        )],
        [InlineKeyboardButton("🏠 MAIN MENU", callback_data="home")],
    ])


def myplan_kb(subs: list) -> InlineKeyboardMarkup:
    """Renew button per active subscription (used by /myplan)."""
    rows = []
    for sub in subs:
        bot_key  = sub.get("bot_key", "")
        plan_key = sub.get("plan_key", "")
        bot  = BOTS.get(bot_key, {})
        plan = bot.get("plans", {}).get(plan_key, {})
        if not bot or not plan:
            continue
        rows.append([InlineKeyboardButton(
            f"🔄 Renew {bot.get('username', bot_key)} — {plan.get('label', '')}",
            callback_data=f"plan:{bot_key}:{plan_key}"
        )])
    rows.append([InlineKeyboardButton("🏠 HOME", callback_data="home")])
    return InlineKeyboardMarkup(rows)
