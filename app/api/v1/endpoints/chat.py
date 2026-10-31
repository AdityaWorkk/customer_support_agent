from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.agents.runner import resume_input, sse, stream_run
from app.api.v1.schemas.chat_schemas import ConfirmIn, MessageIn
from app.core import ratelimit
from app.core.config import settings
from app.core.database import db
from app.core.deps import current_user
from app.core.exceptions import ConflictError
from app.services import chat_service, storage_service

router = APIRouter(prefix="/chat", tags=["chat"])
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


@router.post("/sessions", status_code=201)
async def new_session(user: dict = Depends(current_user)):
    return await chat_service.create_session(user["_id"])


@router.get("/sessions")
async def sessions(user: dict = Depends(current_user)):
    return await chat_service.list_sessions(user["_id"])


@router.get("/sessions/{sid}")
async def session(sid: str, user: dict = Depends(current_user)):
    s = await chat_service.get_session(sid, user["_id"])
    return {"session": chat_service._s(s), "messages": await chat_service.messages(sid)}


@router.get("/sessions/{sid}/messages")
async def poll(sid: str, after: str | None = None, user: dict = Depends(current_user)):
    s = await chat_service.get_session(sid, user["_id"])
    return {"handled_by": s.get("handled_by", "bot"), "messages": await chat_service.messages(sid, after)}


@router.delete("/sessions/{sid}", status_code=204)
async def delete(sid: str, user: dict = Depends(current_user)):
    await chat_service.delete_session(sid, user["_id"])


@router.post("/sessions/{sid}/messages")
async def send(sid: str, body: MessageIn, user: dict = Depends(current_user)):
    ratelimit.check(f"chat:{user['_id']}", settings.RATE_LIMIT_MESSAGES_PER_MINUTE)
    s = await chat_service.get_session(sid, user["_id"])
    if s.get("pending_confirmation"):
        raise ConflictError("Please confirm or keep your order first.", code="confirmation_pending")
    cards, llm_text = [], body.content
    if body.attachment_id:
        att = await storage_service.get_attachment(body.attachment_id, user["_id"])
        cards = [{"type": "attachment", "url": att["url"]}]
        llm_text += "\n[The customer attached a photo.]"
    await chat_service.add_message(sid, "user", body.content, cards=cards)
    await chat_service.set_title_if_new(sid, body.content)

    if s.get("handled_by") == "human":  # admin has taken over: the bot stays silent
        async def handoff():
            yield sse("handoff", {"message": "A support agent is handling this chat and will reply here."})
            yield sse("done", {"interrupted": False})
        return StreamingResponse(handoff(), media_type="text/event-stream", headers=SSE_HEADERS)

    gen = stream_run(sid, user, {"messages": [HumanMessage(content=llm_text)]}, body.attachment_id)
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/sessions/{sid}/confirm")
async def confirm(sid: str, body: ConfirmIn, user: dict = Depends(current_user)):
    s = await chat_service.get_session(sid, user["_id"])
    if not s.get("pending_confirmation"):
        raise ConflictError("Nothing is waiting for confirmation.")
    claimed = await db().sessions.find_one_and_update(  # atomic: a double click resumes once
        {"_id": sid, "pending_confirmation": {"$exists": True}}, {"$unset": {"pending_confirmation": ""}})
    if not claimed:
        raise ConflictError("Already handled.")
    await chat_service.add_message(sid, "user", "Yes, cancel it." if body.approved else "Keep my order.", author="ui")
    gen = stream_run(sid, user, resume_input(body.approved))
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)
