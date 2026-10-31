from fastapi import APIRouter, Depends, Header

from app.agents.review_graph import resolve_review
from app.api.v1.schemas.chat_schemas import AdminMessageIn
from app.api.v1.schemas.order_schemas import DecisionIn
from app.core.config import settings
from app.core.database import db
from app.core.deps import admin_user, now
from app.core.exceptions import AuthError, ConflictError
from app.core.security import random_id
from app.services import chat_service, complaint_service, order_service

router = APIRouter(prefix="/admin", tags=["admin"])
jobs = APIRouter(prefix="/jobs", tags=["jobs"])


async def audit(admin: dict, action: str, target: str, detail: dict | None = None) -> None:
    await db().audit_logs.insert_one({"_id": random_id("aud_"), "admin_id": admin["_id"], "admin_email": admin["email"],
                                      "action": action, "target": target, "detail": detail or {}, "at": now()})


@router.get("/stats")
async def stats(_: dict = Depends(admin_user)):
    d = db()
    return {"open_complaints": await d.complaints.count_documents({"status": {"$in": ["open", "pending_review"]}}),
            "pending_reviews": await d.complaints.count_documents({"status": "pending_review"}),
            "human_chats": await d.sessions.count_documents({"handled_by": "human"}),
            "failed_refunds": await d.orders.count_documents({"refund.status": "failed"})}


@router.get("/sessions")
async def sessions(handled_by: str | None = None, _: dict = Depends(admin_user)):
    q = {"handled_by": handled_by} if handled_by else {}
    out = []
    async for s in db().sessions.find(q).sort("updated_at", -1).limit(60):
        u = await db().users.find_one({"_id": s["user_id"]}, {"email": 1, "name": 1})
        out.append({**chat_service._s(s), "user_email": (u or {}).get("email"), "user_name": (u or {}).get("name")})
    return out


@router.get("/sessions/{sid}")
async def session(sid: str, _: dict = Depends(admin_user)):
    s = await chat_service.get_session(sid)
    return {"session": chat_service._s(s), "messages": await chat_service.messages(sid)}


@router.get("/sessions/{sid}/messages")
async def poll(sid: str, after: str | None = None, _: dict = Depends(admin_user)):
    return {"messages": await chat_service.messages(sid, after)}


@router.post("/sessions/{sid}/takeover")
async def takeover(sid: str, admin: dict = Depends(admin_user)):
    await chat_service.get_session(sid)
    await db().sessions.update_one({"_id": sid}, {"$set": {"handled_by": "human", "handled_by_admin": admin["_id"]}})
    await chat_service.add_message(sid, "assistant", "A support agent has joined this chat.", author="system")
    await audit(admin, "takeover", sid)
    return {"ok": True}


@router.post("/sessions/{sid}/release")
async def release(sid: str, admin: dict = Depends(admin_user)):
    await db().sessions.update_one({"_id": sid}, {"$set": {"handled_by": "bot"}})
    await chat_service.add_message(sid, "assistant", "The support agent has left. The assistant can help with anything else.", author="system")
    await audit(admin, "release", sid)
    return {"ok": True}


@router.post("/sessions/{sid}/messages", status_code=201)
async def admin_message(sid: str, body: AdminMessageIn, admin: dict = Depends(admin_user)):
    await chat_service.get_session(sid)
    m = await chat_service.add_message(sid, "assistant", body.content, author="admin")
    await audit(admin, "admin_message", sid)
    return m


@router.get("/complaints")
async def complaints(status: str | None = None, _: dict = Depends(admin_user)):
    items = await complaint_service.list_queue(status)
    for c in items:
        u = await db().users.find_one({"_id": c["user_id"]}, {"email": 1})
        c["user_email"] = (u or {}).get("email")
    return items


@router.get("/complaints/{cid}")
async def complaint(cid: str, _: dict = Depends(admin_user)):
    c = await complaint_service.get(cid)
    if c.get("order_id"):
        o = await db().orders.find_one({"_id": c["order_id"]})
        c["order"] = order_service.public(o) if o else None
    u = await db().users.find_one({"_id": c["user_id"]}, {"email": 1, "name": 1})
    c["user"] = {"email": (u or {}).get("email"), "name": (u or {}).get("name")}
    return c


@router.post("/complaints/{cid}/decision")
async def decide(cid: str, body: DecisionIn, admin: dict = Depends(admin_user)):
    c = await complaint_service.get(cid)
    if c["status"] not in ("open", "pending_review"):
        raise ConflictError("This complaint was already resolved.")
    if c["status"] == "pending_review":
        if body.decision == "resolve":
            raise ConflictError("Defect reviews must be approved or rejected.")
        await resolve_review(cid, {"decision": body.decision, "note": body.note, "admin_id": admin["_id"]})
    else:
        await complaint_service.set_status(cid, "resolved" if body.decision != "reject" else "rejected", admin["_id"], body.note)
    await audit(admin, f"complaint_{body.decision}", cid, {"note": body.note})
    return await complaint_service.get(cid)


@router.get("/orders")
async def all_orders(_: dict = Depends(admin_user)):
    return [{**order_service.public(o), "user_id": o["user_id"]} async for o in db().orders.find().sort("ordered_at", -1).limit(50)]


@router.post("/orders/{oid}/advance")
async def advance(oid: str, admin: dict = Depends(admin_user)):
    r = await order_service.advance_status(oid)
    await audit(admin, "advance_order", oid, r)
    return r


@router.post("/orders/{oid}/retry-refund")
async def retry(oid: str, admin: dict = Depends(admin_user)):
    r = await order_service.retry_refund(oid)
    await audit(admin, "retry_refund", oid, r)
    return r


@router.get("/audit")
async def audit_log(_: dict = Depends(admin_user)):
    return [{"id": a["_id"], "admin": a["admin_email"], "action": a["action"], "target": a["target"],
             "at": a["at"].isoformat()} async for a in db().audit_logs.find().sort("at", -1).limit(100)]


@jobs.post("/escalate")
async def escalate(x_cron_secret: str = Header(default="")):
    """Hit this from a free external scheduler (e.g. cron-job.org) every ~15 minutes."""
    if x_cron_secret != settings.CRON_SECRET:
        raise AuthError("Invalid cron secret.")
    return {"escalated": await complaint_service.escalate_all()}
