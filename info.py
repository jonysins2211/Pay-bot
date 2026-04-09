from os import environ

# ── Bot Credentials ───────────────────────────────────────────
SESSION   = environ.get("SESSION", "PaymentBot")
API_ID    = int(environ.get("API_ID", "29961422"))
API_HASH  = environ.get("API_HASH", "cba915c79809dc0806676db7052b2a83")
BOT_TOKEN = environ.get("BOT_TOKEN", "8793787645:AAGdIG2WGA_15lzNqn34xlqFoZKWfzl8ZMg")

# ── Admin & Channels ──────────────────────────────────────────
OWNER_ID     = int(environ.get("OWNER_ID", "949657126"))
ADMIN_IDS    = list(map(int, environ.get("ADMIN_IDS", "949657126").split()))
LOGS_CHANNEL = int(environ.get("LOGS_CHANNEL", "-1003703572230"))
ADMIN_GROUP  = int(environ.get("ADMIN_GROUP", "-1002077293491"))

# ── Links & Usernames ─────────────────────────────────────────
OWNER_USERNAME  = environ.get("OWNER_USERNAME", "@Mladminbot")
SUPPORT_GROUP   = environ.get("SUPPORT_GROUP", "@ML_FILES")
UPDATES_CHANNEL = environ.get("UPDATES_CHANNEL", "@Movie_loverzz")

# ── UPI Payment ───────────────────────────────────────────────
UPI_ID   = environ.get("UPI_ID", "movieloverz11220@okaxis")
UPI_NAME = environ.get("UPI_NAME", "Sree")

# ── Optional ──────────────────────────────────────────────────
BANNER_IMAGE      = environ.get("BANNER_IMAGE", "https://i.ibb.co/Nn79HCNL/photo-2026-04-08-15-43-37-7626414616796463132.jpg")
MONGO_URL         = environ.get("MONGO_URL", "mongodb+srv://johnwick:NO5VzwVgSrJ9KBtC@cluster0.5iie9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster")
PORT              = int(environ.get("PORT", "8080"))
QR_EXPIRY_SECONDS = 300   # 5 minutes

# ── Heroku detection ─────────────────────────────────────────
import os
ON_HEROKU = "DYNO" in os.environ
APP_NAME  = os.environ.get("APP_NAME", "payment-bott")
PING_INTERVAL = int(os.environ.get("PING_INTERVAL", "1200"))

# ── Your Bots & Plans ─────────────────────────────────────────
BOTS = {
    "cinephiles_mawa": {
        "name": "🎬 Cinephiles + MawaMovies",
        "username": "@CinephilesRobot",
        "description": (
            "🎬 *Cinephiles + MawaMovies Bot — COMBO VIP*\n\n"
            "*GET THE BEST OF BOTH WORLDS!* 🍿🔥\n\n"
            "✨ *PREMIUM BENEFITS:*\n"
            "💎 *CINEPHILES: HD & LATEST TOLLYWOOD + HOLLYWOOD*\n"
            "💎 *MAWA MOVIES: EXCLUSIVE ALL REGIONAL CONTENT*\n"
            "💎 *ZERO ADS & LIGHTNING FAST ACCESS*\n"
            "💎 *EARLY DROPS & NEW RELEASES*\n\n"
            "👇 *SELECT YOUR PREMIUM PLAN BELOW:*"
        ),
        "plans": {
            "1m":  {"label": "1 Month",  "price": 25,  "days": 30},
            "2m":  {"label": "2 Months", "price": 50,  "days": 60},
            "3m":  {"label": "3 Months", "price": 75,  "days": 90},
            "6m":  {"label": "6 Months", "price": 150, "days": 180},
            "12m": {"label": "1 Year",   "price": 300, "days": 365},
        },
    },
    "ml_files": {
        "name": "🎞️ ML_Files 3.0 (DVD + HD)",
        "username": "@ML_FILES_ROBOT",
        "description": (
            "🎞️ *ML_Files 3.0 — DVD + HD VIP SUBSCRIPTION*\n\n"
            "*CRYSTAL CLEAR QUALITY. EVERY TIME.* 📀\n\n"
            "✨ *PREMIUM BENEFITS:*\n"
            "💎 *DVD & HD QUALITY FILES*\n"
            "💎 *MASSIVE LIBRARY — ALL GENRES*\n"
            "💎 *SUPER FAST DOWNLOADS*\n"
            "💎 *EXCLUSIVE CONTENT DROPS*\n\n"
            "👇 *SELECT YOUR PREMIUM PLAN BELOW:*"
        ),
        "plans": {
            "1m":  {"label": "1 Month",  "price": 25,  "days": 30},
            "2m":  {"label": "2 Months", "price": 50,  "days": 60},
            "3m":  {"label": "3 Months", "price": 75,  "days": 90},
            "6m":  {"label": "6 Months", "price": 150, "days": 180},
            "12m": {"label": "1 Year",   "price": 300, "days": 365},
        },
    },
    "file2link_v1": {
        "name": "🔗 File to Link Bot",
        "username": "@Mlfiletolinkbot",
        "description": (
            "🔗 *File to Link Bot — VIP SUBSCRIPTION*\n\n"
            "*UPLOAD ANY FILE. GET A DIRECT LINK INSTANTLY!* ⚡\n\n"
            "✨ *PREMIUM BENEFITS:*\n"
            "💎 *UNLIMITED FILE UPLOADS*\n"
            "💎 *NO SIZE LIMIT*\n"
            "💎 *PERMANENT SHAREABLE LINKS*\n"
            "💎 *BLAZING FAST SERVERS*\n\n"
            "👇 *SELECT YOUR PREMIUM PLAN BELOW:*"
        ),
        "plans": {
            "1m":  {"label": "1 Month",  "price": 25,  "days": 30},
            "2m":  {"label": "2 Months", "price": 50,  "days": 60},
            "3m":  {"label": "3 Months", "price": 75,  "days": 90},
            "6m":  {"label": "6 Months", "price": 150, "days": 180},
            "12m": {"label": "1 Year",   "price": 300, "days": 365},
        },
    },
    "file2link_v2": {
        "name": "🔗 File 2 Link Bot 2.0",
        "username": "@ML_File2Link_Bot",
        "description": (
            "🔗 *File 2 Link Bot 2.0 — VIP SUBSCRIPTION*\n\n"
            "*THE UPGRADED LINK GENERATOR IS HERE!* 🚀\n\n"
            "✨ *PREMIUM BENEFITS:*\n"
            "💎 *FASTER THAN EVER — 2.0 ENGINE*\n"
            "💎 *BULK FILE SUPPORT*\n"
            "💎 *CUSTOM LINK MANAGEMENT*\n"
            "💎 *PRIORITY ACCESS & UPTIME*\n\n"
            "👇 *SELECT YOUR PREMIUM PLAN BELOW:*"
        ),
        "plans": {
            "1m":  {"label": "1 Month",  "price": 25,  "days": 30},
            "2m":  {"label": "2 Months", "price": 50,  "days": 60},
            "3m":  {"label": "3 Months", "price": 75,  "days": 90},
            "6m":  {"label": "6 Months", "price": 150, "days": 180},
            "12m": {"label": "1 Year",   "price": 300, "days": 365},
        },
    },
    "all_bots": {
        "name": "👑 All Bots Premium (Combo)",
        "username": "AllBotsCombo",
        "description": (
            "👑 *ALL BOTS PREMIUM — ULTIMATE COMBO PLAN*\n\n"
            "*GET ACCESS TO EVERY SINGLE BOT IN ONE PLAN!* 🌟\n\n"
            "✅ *INCLUDES ALL OF THESE:*\n"
            "🎬 Cinephiles + Mawa Movies Bot\n"
            "🎞️ ML_Files 3.0 (DVD + HD)\n"
            "🔗 File to Link Bot\n"
            "🔗 File 2 Link Bot 2.0\n\n"
            "💎 *BEST VALUE — SAVE MORE WITH LONGER PLANS!*\n"
            "💎 *ONE PAYMENT — ALL ACCESS*\n\n"
            "👇 *SELECT YOUR PREMIUM PLAN BELOW:*"
        ),
        "plans": {
            "1m":  {"label": "1 Month",  "price": 80,   "days": 30},
            "2m":  {"label": "2 Months", "price": 160,  "days": 60},
            "3m":  {"label": "3 Months", "price": 320,  "days": 90},
            "6m":  {"label": "6 Months", "price": 640,  "days": 180},
            "12m": {"label": "1 Year",   "price": 1280, "days": 365},
        },
    },
}
