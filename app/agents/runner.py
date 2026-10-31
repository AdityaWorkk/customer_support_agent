"""Streams a graph run as SSE events and persists the visible transcript."""
import json
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import Command

from app.agents.graph import get_chat_graph
from app.agents.llm import text_of
from app.core.config import settings
from app.core.database import db
from app.services import chat_service


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _friendly(e: Exception) -> str:
    s = str(e)
    if "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower():
        return "We're getting a lot of requests right now. Please try again in a minute."
    if "API key" in s or "403" in s or "PERMISSION" in s:
        return "The assistant is not configured correctly. Please contact support."
    return "Something went wrong while answering. Please try again."


async def stream_run(session_id: str, user: dict, graph_input, attachment_id: str | None = None) -> AsyncIterator[str]:
    graph = get_chat_graph()
    config = {
        "configurable": {"thread_id": session_id, "user_id": user["_id"], "session_id": session_id,
                         "attachment_id": attachment_id},
        "metadata": {"user_id": user["_id"], "session_id": session_id},
        "tags": ["support-chat"], "recursion_limit": 25,
    }
    text_parts: list[str] = []
    cards: list[dict] = []
    interrupted = False
    try:
        async for mode, data in graph.astream(graph_input, config, stream_mode=["messages", "updates"]):
            if mode == "messages":
                chunk, meta = data
                if meta.get("langgraph_node") == "agent" and isinstance(chunk, AIMessageChunk):
                    t = text_of(chunk.content)
                    if t:
                        text_parts.append(t)
                        yield sse("token", {"text": t})
            else:
                if "__interrupt__" in data:
                    payload = data["__interrupt__"][0].value
                    interrupted = True
                    await db().sessions.update_one({"_id": session_id}, {"$set": {"pending_confirmation": payload}})
                    yield sse("confirm", payload)
                    continue
                for node, upd in data.items():
                    for m in (upd or {}).get("messages", []):
                        if node == "out_of_scope" and isinstance(m, AIMessage):
                            text_parts.append(text_of(m.content))
                            yield sse("token", {"text": text_of(m.content)})
                        elif isinstance(m, ToolMessage):
                            try:
                                ui = json.loads(m.content).get("ui") if isinstance(m.content, str) else None
                            except ValueError:
                                ui = None
                            if ui:
                                cards.append(ui)
                                yield sse("card", ui)
    except Exception as e:  # noqa: BLE001
        msg = _friendly(e)
        await chat_service.add_message(session_id, "assistant", msg, author="system")
        yield sse("error", {"message": msg})
        return
    final = "".join(text_parts).strip()
    if final or cards:
        await chat_service.add_message(session_id, "assistant", final, cards=cards, author="bot")
    if not interrupted:
        await db().sessions.update_one({"_id": session_id}, {"$unset": {"pending_confirmation": ""}})
    yield sse("done", {"interrupted": interrupted})


def resume_input(approved: bool) -> Command:
    return Command(resume={"approved": approved})
