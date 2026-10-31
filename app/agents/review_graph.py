"""Defect-photo review workflow. Runs on its own thread (review-<complaint_id>) so the
customer's chat never blocks: the graph pauses at interrupt() until an admin decides,
then resumes via Command(resume=...) and triggers the refund."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.graph import get_checkpointer
from app.services import chat_service, complaint_service, order_rules as rules, order_service


class ReviewState(TypedDict, total=False):
    complaint_id: str
    order_id: str
    user_id: str
    session_id: str | None
    decision: dict
    outcome: str


def await_decision(state: ReviewState):
    decision = interrupt({"type": "defect_review", "complaint_id": state["complaint_id"], "order_id": state["order_id"]})
    return {"decision": decision}


async def apply_decision(state: ReviewState):
    d = state["decision"]
    cid, oid = state["complaint_id"], state["order_id"]
    note = d.get("note", "")
    if d["decision"] == "approve":
        await complaint_service.set_status(cid, "approved", d["admin_id"], note)
        res = await order_service.refund_for_defect(oid, cid)
        text = (f"Good news: your defect report {cid} was approved. A refund of "
                f"{rules.fmt_money(res['amount'])} for order {oid} is {'complete' if res['refund_status'] == 'succeeded' else 'on its way'}.")
        if res["refund_status"] == "failed":
            text = f"Your defect report {cid} was approved, but the refund hit a problem. Our team will retry it and update you."
        outcome = "approved"
    else:
        await complaint_service.set_status(cid, "rejected", d["admin_id"], note)
        text = f"Your defect report {cid} was reviewed and could not be approved." + (f" Reviewer note: {note}" if note else "") + " You can reply here to raise a complaint."
        outcome = "rejected"
    if state.get("session_id"):
        await chat_service.add_message(state["session_id"], "assistant", text, author="system")
    return {"outcome": outcome}


def build_review_graph():
    g = StateGraph(ReviewState)
    g.add_node("await_decision", await_decision)
    g.add_node("apply_decision", apply_decision)
    g.add_edge(START, "await_decision")
    g.add_edge("await_decision", "apply_decision")
    g.add_edge("apply_decision", END)
    return g.compile(checkpointer=get_checkpointer())


_graph = None


def _g():
    global _graph
    if _graph is None:
        _graph = build_review_graph()
    return _graph


def _cfg(cid: str) -> dict:
    return {"configurable": {"thread_id": f"review-{cid}"}}


async def start_review(complaint_id: str, order_id: str, user_id: str, session_id: str | None) -> None:
    await _g().ainvoke({"complaint_id": complaint_id, "order_id": order_id, "user_id": user_id,
                        "session_id": session_id}, _cfg(complaint_id))


async def resolve_review(complaint_id: str, decision: dict) -> dict:
    return await _g().ainvoke(Command(resume=decision), _cfg(complaint_id))
