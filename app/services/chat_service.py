from app.core.database import db
from app.core.deps import now
from app.core.exceptions import NotFoundError
from app.core.security import random_id


def _s(s: dict) -> dict:
    return {"id": s["_id"], "title": s.get("title", "New chat"), "handled_by": s.get("handled_by", "bot"),
            "updated_at": s["updated_at"].isoformat(), "pending_confirmation": s.get("pending_confirmation")}


def _m(m: dict) -> dict:
    return {"id": m["_id"], "role": m["role"], "content": m["content"], "cards": m.get("cards", []),
            "created_at": m["created_at"].isoformat(), "author": m.get("author")}


async def create_session(user_id: str) -> dict:
    t = now()
    s = {"_id": random_id("ses_"), "user_id": user_id, "title": "New chat", "handled_by": "bot",
         "created_at": t, "updated_at": t}
    await db().sessions.insert_one(s)
    return _s(s)


async def list_sessions(user_id: str) -> list[dict]:
    cur = db().sessions.find({"user_id": user_id}).sort("updated_at", -1).limit(50)
    return [_s(s) async for s in cur]


async def get_session(session_id: str, user_id: str | None = None) -> dict:
    q = {"_id": session_id}
    if user_id:
        q["user_id"] = user_id
    s = await db().sessions.find_one(q)
    if not s:
        raise NotFoundError("Chat not found.")
    return s


async def add_message(session_id: str, role: str, content: str, cards: list | None = None,
                      author: str | None = None) -> dict:
    m = {"_id": random_id("msg_"), "session_id": session_id, "role": role, "content": content,
         "cards": cards or [], "author": author, "created_at": now()}
    await db().messages.insert_one(m)
    await db().sessions.update_one({"_id": session_id}, {"$set": {"updated_at": m["created_at"]}})
    return _m(m)


async def messages(session_id: str, after: str | None = None, limit: int = 200) -> list[dict]:
    q: dict = {"session_id": session_id}
    if after:
        ref = await db().messages.find_one({"_id": after})
        if ref:
            q["created_at"] = {"$gt": ref["created_at"]}
    cur = db().messages.find(q).sort("created_at", 1).limit(limit)
    return [_m(m) async for m in cur]


async def set_title_if_new(session_id: str, text: str) -> None:
    await db().sessions.update_one({"_id": session_id, "title": "New chat"},
                                   {"$set": {"title": text.strip()[:48] or "New chat"}})


async def delete_session(session_id: str, user_id: str) -> None:
    await get_session(session_id, user_id)
    await db().messages.delete_many({"session_id": session_id})
    await db().sessions.delete_one({"_id": session_id})
