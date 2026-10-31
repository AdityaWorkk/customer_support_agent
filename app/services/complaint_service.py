import secrets

from app.core.database import db
from app.core.deps import now
from app.core.exceptions import ConflictError, NotFoundError
from app.services import order_rules as rules


def _public(c: dict) -> dict:
    d = {k: v for k, v in c.items() if k not in ("user_id_internal",)}
    d["id"] = d.pop("_id")
    for k in ("created_at", "updated_at", "sla_due_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    d["escalation_label"] = rules.ESCALATION_LEVELS.get(d.get("escalation_level", 1))
    for h in d.get("history", []):
        h["at"] = h["at"].isoformat() if hasattr(h["at"], "isoformat") else h["at"]
    return d


async def create(user_id: str, category: str, description: str, order_id: str | None = None,
                 attachment: dict | None = None) -> dict:
    if category not in rules.CATEGORIES:
        category = "other"
    priority, sla = rules.CATEGORIES[category]
    if order_id:  # ownership check: complaints can only reference the user's own orders
        if not await db().orders.find_one({"_id": order_id.upper(), "user_id": user_id}):
            raise NotFoundError("I couldn't find that order on your account.")
        order_id = order_id.upper()
    t = now()
    from datetime import timedelta
    doc = {"_id": "CMP-" + secrets.token_hex(3).upper(), "user_id": user_id, "category": category,
           "description": description[:2000], "order_id": order_id, "priority": priority,
           "priority_rank": rules.PRIORITY_RANK[priority], "sla_hours": sla, "sla_due_at": t + timedelta(hours=sla),
           "escalation_level": 1, "status": "pending_review" if attachment else "open",
           "attachment": attachment, "created_at": t, "updated_at": t,
           "history": [{"at": t, "event": "created", "by": user_id}]}
    await db().complaints.insert_one(doc)
    return _public(doc)


async def list_for_user(user_id: str) -> list[dict]:
    cur = db().complaints.find({"user_id": user_id}).sort("created_at", -1).limit(50)
    return [await _escalate(c) async for c in cur]


async def get(complaint_id: str, user_id: str | None = None) -> dict:
    q = {"_id": complaint_id}
    if user_id:
        q["user_id"] = user_id
    c = await db().complaints.find_one(q)
    if not c:
        raise NotFoundError("Complaint not found.")
    return await _escalate(c)


async def list_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    q = {"status": status} if status else {"status": {"$in": ["open", "pending_review"]}}
    cur = db().complaints.find(q).sort([("priority_rank", 1), ("created_at", 1)]).limit(limit)
    return [await _escalate(c) async for c in cur]


async def _escalate(c: dict) -> dict:
    """Escalation is evaluated lazily on read (Render free has no background workers)."""
    if c["status"] in ("open", "pending_review"):
        level = rules.escalation_level(c["created_at"], now(), c["sla_hours"])
        if level > c.get("escalation_level", 1):
            ev = {"at": now(), "event": f"escalated to level {level}", "by": "system"}
            await db().complaints.update_one({"_id": c["_id"]}, {"$set": {"escalation_level": level}, "$push": {"history": ev}})
            c["escalation_level"] = level
            c.setdefault("history", []).append(ev)
    return _public(c)


async def escalate_all() -> int:
    n = 0
    async for c in db().complaints.find({"status": {"$in": ["open", "pending_review"]}}):
        before = c.get("escalation_level", 1)
        after = (await _escalate(c))["escalation_level"]
        n += after > before
    return n


async def set_status(complaint_id: str, status: str, by: str, note: str = "") -> None:
    res = await db().complaints.update_one(
        {"_id": complaint_id, "status": {"$in": ["open", "pending_review"]}},
        {"$set": {"status": status, "updated_at": now(), "resolution_note": note},
         "$push": {"history": {"at": now(), "event": status, "by": by, "note": note}}})
    if not res.matched_count:
        raise ConflictError("This complaint was already resolved.")
