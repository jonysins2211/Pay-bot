"""
MongoDB Database Layer for ML Payment Bot
Collections:
  - active_subs   : { _id: user_id, subs: [ {bot_key, plan_key, expiry, expiry_raw} ] }
  - user_history  : { _id: user_id, history: [ {bot_name, plan, amount, date, status} ] }
  - pending_pays  : { _id: pid, user_id, username, first_name, bot_key, plan_key, amount, ts, chat_id }
  - banned_users  : { _id: user_id, reason: str, banned_at: str, banned_by: int }
"""

import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from info import MONGO_URL

logger = logging.getLogger(__name__)

# ── Connect ───────────────────────────────────────────────────
_client = AsyncIOMotorClient(MONGO_URL)
_db     = _client["PaymentBot"]

subs_col    = _db["active_subs"]
history_col = _db["user_history"]
pending_col = _db["pending_pays"]
banned_col  = _db["banned_users"]

logger.info("✅ MongoDB connected")


# ══════════════════════════════════════════════════════════════
#  PENDING PAYMENTS
# ══════════════════════════════════════════════════════════════

async def add_pending(pid: str, data: dict):
    await pending_col.update_one(
        {"_id": pid},
        {"$set": data},
        upsert=True
    )

async def get_pending(pid: str) -> dict | None:
    doc = await pending_col.find_one({"_id": pid})
    if doc:
        doc.pop("_id", None)
    return doc

async def del_pending(pid: str):
    await pending_col.delete_one({"_id": pid})

async def get_all_pending() -> dict:
    result = {}
    async for doc in pending_col.find():
        pid = doc.pop("_id")
        result[pid] = doc
    return result


# ══════════════════════════════════════════════════════════════
#  ACTIVE SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════

async def get_subs(user_id: int) -> list:
    doc = await subs_col.find_one({"_id": user_id})
    return doc.get("subs", []) if doc else []

async def set_subs(user_id: int, subs: list):
    await subs_col.update_one(
        {"_id": user_id},
        {"$set": {"subs": subs}},
        upsert=True
    )

async def add_sub(user_id: int, sub: dict):
    subs = await get_subs(user_id)
    subs.append(sub)
    await set_subs(user_id, subs)

async def get_all_subs() -> dict:
    result = {}
    async for doc in subs_col.find():
        uid = doc.pop("_id")
        result[uid] = doc.get("subs", [])
    return result


# ══════════════════════════════════════════════════════════════
#  USER HISTORY
# ══════════════════════════════════════════════════════════════

async def get_history(user_id: int) -> list:
    doc = await history_col.find_one({"_id": user_id})
    return doc.get("history", []) if doc else []

async def get_all_history() -> dict:
    result = {}
    async for doc in history_col.find():
        uid = doc.pop("_id")
        result[uid] = doc.get("history", [])
    return result

async def add_history(user_id: int, tx: dict):
    await history_col.update_one(
        {"_id": user_id},
        {"$push": {"history": tx}},
        upsert=True
    )


# ══════════════════════════════════════════════════════════════
#  BANNED USERS
# ══════════════════════════════════════════════════════════════

async def ban_user(user_id: int, reason: str, banned_by: int):
    await banned_col.update_one(
        {"_id": user_id},
        {"$set": {
            "reason": reason,
            "banned_by": banned_by,
            "banned_at": datetime.now().isoformat(),
        }},
        upsert=True
    )

async def unban_user(user_id: int):
    await banned_col.delete_one({"_id": user_id})

async def get_ban(user_id: int) -> dict | None:
    doc = await banned_col.find_one({"_id": user_id})
    if doc:
        doc.pop("_id", None)
    return doc

async def get_all_bans() -> dict:
    result = {}
    async for doc in banned_col.find():
        uid = doc.pop("_id")
        result[uid] = doc
    return result
