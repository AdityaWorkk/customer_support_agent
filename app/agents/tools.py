"""Tools the LLM can call. Security model:
  * user_id / session_id / attachment_id come from RunnableConfig (set by the API from the
    verified JWT), never from tool arguments, so the model cannot choose whose data to read.
  * Money rules, state checks and refunds are deterministic service code.
Tools are plain LangChain tools behind this module; they can be exposed through an MCP
server later without touching the graph."""
import json
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import interrupt

from app.core.exceptions import AppError
from app.services import complaint_service, order_rules as rules, order_service, storage_service

_FAQ = json.loads((Path(__file__).resolve().parents[2] / "prompts" / "company_faq.json").read_text())


def _uid(config: RunnableConfig) -> str:
    return config["configurable"]["user_id"]


def _out(summary: str, ui: dict | None = None, **extra) -> str:
    return json.dumps({"summary": summary, **({"ui": ui} if ui else {}), **extra}, default=str)


def _err(e: AppError) -> str:
    return json.dumps({"error": e.message})


def _brief(o: dict) -> dict:
    return {"id": o["id"], "status": o["status"], "ordered_at": o["ordered_at"], "total": o["total"], "currency": o["currency"],
            "items": [f'{i["qty"]} x {i["name"]}' for i in o["items"]]}


@tool
async def list_my_orders(config: RunnableConfig) -> str:
    """List the signed-in customer's recent orders (id, status, date, total). Use when the customer has not given an order id."""
    orders = await order_service.list_orders(_uid(config), limit=8)
    if not orders:
        return _out("The customer has no orders yet.")
    return _out(f"{len(orders)} recent orders.", ui={"type": "order_list", "orders": [_brief(o) for o in orders]},
                orders=[_brief(o) for o in orders])


@tool
async def get_order_details(order_id: str, config: RunnableConfig) -> str:
    """Get full details of ONE order: items, status and timeline, order date, ordering location, shipping address, estimated delivery, product ids. order_id looks like ORD-10001."""
    try:
        o = order_service.public(await order_service.get_order(_uid(config), order_id))
    except AppError as e:
        return _err(e)
    return _out(f"Order {o['id']} is {o['status']}.", ui={"type": "waybill", "order": o}, order=o)


@tool
async def get_cost_breakdown(order_id: str, config: RunnableConfig) -> str:
    """Itemised cost breakdown for ONE order (items, tax, delivery charge, total, payment and refund status). Amounts are in minor units (paise); quote them as returned."""
    try:
        b = await order_service.cost_breakdown(_uid(config), order_id)
    except AppError as e:
        return _err(e)
    return _out(f"Cost breakdown for {b['order_id']}.", ui={"type": "cost", "breakdown": b}, breakdown=b)


@tool
async def cancel_order(order_id: str, config: RunnableConfig) -> str:
    """Cancel ONE order and refund it. Checks eligibility, then shows the customer a confirmation card with the exact refund. Only call when the customer explicitly asked to cancel this order."""
    uid = _uid(config)
    try:
        prev = await order_service.cancel_preview(uid, order_id)
        if not prev["eligible"]:
            return _out(prev["reason"], eligible=False)
        # Human-in-the-loop: the graph pauses here until the customer taps Confirm or Keep order in the UI.
        answer = interrupt({"type": "confirm_cancel", **{k: prev[k] for k in (
            "order_id", "currency", "total", "delivery_charge", "refund_amount", "retained_delivery_fee")}})
        if not (isinstance(answer, dict) and answer.get("approved") is True):
            return _out("The customer chose to keep the order. Nothing was changed.", cancelled=False)
        res = await order_service.cancel_order(uid, order_id)
    except AppError as e:
        return _err(e)
    note = {"succeeded": "Refund completed.", "pending": "Refund started and will complete shortly.",
            "failed": "Cancellation recorded but the refund failed; support will retry it."}[res["refund_status"]]
    return _out(f"Order {res['order_id']} cancelled. {note} Refund amount: {rules.fmt_money(res['amount'], prev['currency'])}.",
                cancelled=True, refund_status=res["refund_status"])


@tool
async def file_complaint(category: str, description: str, config: RunnableConfig, order_id: str | None = None) -> str:
    """File a complaint. category must be one of: late_delivery, wrong_item, staff_misconduct, website_performance, billing_issue, other. order_id is optional. Do NOT use for broken or defective products; use report_defective_product."""
    if category == "defective_product":
        return _out("Use report_defective_product for defects; it needs a photo.")
    try:
        c = await complaint_service.create(_uid(config), category, description, order_id)
    except AppError as e:
        return _err(e)
    return _out(f"Complaint {c['id']} filed. Priority {c['priority']}, response within {c['sla_hours']} hours.",
                ui={"type": "ticket", "complaint": c}, complaint=c)


@tool
async def report_defective_product(order_id: str, description: str, config: RunnableConfig) -> str:
    """Report a damaged, broken or defective product for human review. Requires the customer to have attached a photo in the chat."""
    from app.agents.review_graph import start_review
    uid = _uid(config)
    att_id = config["configurable"].get("attachment_id")
    if not att_id:
        return _out("No photo attached yet. Ask the customer to attach a clear photo with the paperclip button, then call this again.",
                    needs_photo=True)
    try:
        att = await storage_service.get_attachment(att_id, uid)
        order = await order_service.get_order(uid, order_id)
        c = await complaint_service.create(uid, "defective_product", description, order["_id"],
                                           attachment={"id": att["_id"], "url": att["url"]})
        await start_review(c["id"], order["_id"], uid, config["configurable"].get("session_id"))
    except AppError as e:
        return _err(e)
    return _out(f"Defect report {c['id']} sent for human review (usually within 24 hours). No refund is promised yet.",
                ui={"type": "ticket", "complaint": c}, complaint=c)


@tool
async def list_my_complaints(config: RunnableConfig) -> str:
    """List the customer's complaints with status, priority and escalation level."""
    cs = await complaint_service.list_for_user(_uid(config))
    if not cs:
        return _out("The customer has no complaints.")
    return _out(f"{len(cs)} complaints.", ui={"type": "ticket", "complaint": cs[0]} if len(cs) == 1 else None,
                complaints=[{k: c[k] for k in ("id", "category", "status", "priority", "escalation_label", "order_id")} for c in cs[:8]])


@tool
async def get_company_info(topic: str, config: RunnableConfig) -> str:
    """Company policy information. topic is one of: shipping, cancellation, refunds, returns, contact, complaints."""
    key = topic.lower().strip()
    if key not in _FAQ:
        return _out("No policy found for that topic. Available: " + ", ".join(_FAQ))
    return _out(_FAQ[key])


ALL_TOOLS = [list_my_orders, get_order_details, get_cost_breakdown, cancel_order, file_complaint,
             report_defective_product, list_my_complaints, get_company_info]

TOOLSETS = {
    "orders": [list_my_orders, get_order_details, get_company_info],
    "billing": [list_my_orders, get_order_details, get_cost_breakdown, cancel_order, get_company_info],
    "complaint": [list_my_orders, get_order_details, file_complaint, report_defective_product, list_my_complaints],
    "general": [get_company_info, list_my_orders],
}
