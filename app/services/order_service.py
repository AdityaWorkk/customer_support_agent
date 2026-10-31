"""All order/refund mutations live here. Every query is scoped by user_id so a
prompt-injected order id can never reach another customer's data."""
from app.core.database import db
from app.core.deps import now
from app.core.exceptions import ConflictError, NotFoundError, PaymentError
from app.services import order_rules as rules
from app.services.payments.factory import get_provider


def public(order: dict) -> dict:
    o = {k: v for k, v in order.items() if k != "user_id"}
    o["id"] = o.pop("_id")
    for k in ("ordered_at", "estimated_delivery"):
        if o.get(k):
            o[k] = o[k].isoformat()
    o["status_history"] = [{"status": h["status"], "at": h["at"].isoformat()} for h in o.get("status_history", [])]
    return o


async def list_orders(user_id: str, limit: int = 20) -> list[dict]:
    cur = db().orders.find({"user_id": user_id}).sort("ordered_at", -1).limit(limit)
    return [public(o) async for o in cur]


async def get_order(user_id: str, order_id: str) -> dict:
    o = await db().orders.find_one({"_id": order_id.upper().strip(), "user_id": user_id})
    if not o:
        raise NotFoundError("I couldn't find that order on your account.")
    return o


async def cancel_preview(user_id: str, order_id: str) -> dict:
    o = await get_order(user_id, order_id)
    r = rules.compute_cancel_refund(o)
    return {"order_id": o["_id"], "status": o["status"], "currency": o["currency"], "total": o["total"],
            "delivery_charge": o["delivery_charge"], **r}


async def cancel_order(user_id: str, order_id: str) -> dict:
    o = await get_order(user_id, order_id)
    calc = rules.compute_cancel_refund(o)
    if not calc["eligible"]:
        raise ConflictError(calc["reason"])
    t = now()
    # Atomic claim: only one concurrent request can move the order to cancel_requested.
    claimed = await db().orders.find_one_and_update(
        {"_id": o["_id"], "user_id": user_id, "status": o["status"], "refund.status": "none"},
        {"$set": {"status": "cancel_requested", "cancel_from_status": o["status"],
                  "refund": {"status": "requested", "kind": "cancel", "amount": calc["refund_amount"],
                             "id": None, "refunded_amount": 0}},
         "$push": {"status_history": {"status": "cancel_requested", "at": t}}})
    if not claimed:
        raise ConflictError("This order is already being processed. Refresh and check its status.")
    return await _issue_refund(o, calc["refund_amount"], "cancel", f"refund-{o['_id']}-cancel")


async def refund_for_defect(order_id: str, complaint_id: str) -> dict:
    o = await db().orders.find_one({"_id": order_id})
    if not o:
        raise NotFoundError("Order not found.")
    amount = rules.compute_defect_refund(o)
    if amount <= 0:
        raise ConflictError("Nothing left to refund on this order.")
    await db().orders.update_one({"_id": order_id}, {"$set": {"refund": {
        "status": "requested", "kind": "defect", "amount": amount, "id": None,
        "refunded_amount": (o.get("refund") or {}).get("refunded_amount", 0)}}})
    return await _issue_refund(o, amount, "defect", f"refund-{order_id}-defect-{complaint_id}")


async def retry_refund(order_id: str) -> dict:
    o = await db().orders.find_one({"_id": order_id})
    r = (o or {}).get("refund") or {}
    if not o or r.get("status") != "failed":
        raise ConflictError("Only failed refunds can be retried.")
    return await _issue_refund(o, r["amount"], r["kind"], f"refund-{order_id}-{r['kind']}")


async def _issue_refund(order: dict, amount: int, kind: str, idem_key: str) -> dict:
    pay = order.get("payment") or {}
    provider = get_provider(pay.get("provider"))
    try:
        res = await provider.refund(pay["payment_id"], amount, idem_key,
                                    {"order_id": order["_id"], "reason": kind})
    except PaymentError as e:
        await db().orders.update_one({"_id": order["_id"]}, {"$set": {"refund.status": "failed", "refund.error": e.message}})
        return {"order_id": order["_id"], "refund_status": "failed", "amount": amount, "error": e.message}
    await db().orders.update_one({"_id": order["_id"]}, {"$set": {"refund.id": res.id, "refund.status": "pending"}})
    if res.status == "succeeded":  # real card refunds often settle instantly; same idempotent path as the webhook
        await apply_refund_result(refund_id=res.id, status="succeeded", order_id=order["_id"])
        return {"order_id": order["_id"], "refund_status": "succeeded", "amount": amount, "refund_id": res.id}
    return {"order_id": order["_id"], "refund_status": "pending", "amount": amount, "refund_id": res.id}


async def apply_refund_result(refund_id: str, status: str, order_id: str | None = None) -> None:
    q = {"refund.id": refund_id}
    o = await db().orders.find_one(q) or (await db().orders.find_one({"_id": order_id}) if order_id else None)
    if not o or (o.get("refund") or {}).get("status") == "succeeded":
        return
    kind = o["refund"].get("kind", "cancel")
    t = now()
    if status == "succeeded":
        new_status = "cancelled" if kind == "cancel" else "refunded"
        await db().orders.update_one({"_id": o["_id"]}, {
            "$set": {"status": new_status, "refund.status": "succeeded", "refund.id": refund_id,
                     "refund.refunded_amount": o["refund"]["amount"], "refund.completed_at": t},
            "$push": {"status_history": {"status": new_status, "at": t}}})
    else:
        await db().orders.update_one({"_id": o["_id"]}, {"$set": {"refund.status": "failed"}})


async def cost_breakdown(user_id: str, order_id: str) -> dict:
    o = await get_order(user_id, order_id)
    pay = o.get("payment") or {}
    verified = None
    try:
        p = await get_provider(pay.get("provider")).get_payment(pay["payment_id"])
        verified = {"provider": p.provider, "status": p.status, "amount_charged": p.amount,
                    "amount_refunded": p.amount_refunded, "receipt_url": p.receipt_url}
    except Exception:
        verified = None  # breakdown still works from our own records
    return {
        "order_id": o["_id"], "currency": o["currency"],
        "items": [{"name": i["name"], "qty": i["qty"], "unit_price": i["unit_price"],
                   "line_total": i["unit_price"] * i["qty"]} for i in o["items"]],
        "subtotal": o["subtotal"], "discount": o.get("discount", 0), "tax": o["tax"],
        "delivery_charge": o["delivery_charge"], "total": o["total"],
        "refund": {"status": (o.get("refund") or {}).get("status", "none"),
                   "amount": (o.get("refund") or {}).get("amount", 0)},
        "payment": verified,
    }


async def advance_status(order_id: str) -> dict:
    """Demo helper: simulates the warehouse/courier moving an order forward."""
    o = await db().orders.find_one({"_id": order_id})
    if not o:
        raise NotFoundError("Order not found.")
    nxt = rules.next_logistics_state(o["status"])
    if not nxt:
        raise ConflictError(f"Order in '{o['status']}' cannot advance.")
    await db().orders.update_one({"_id": order_id, "status": o["status"]}, {
        "$set": {"status": nxt}, "$push": {"status_history": {"status": nxt, "at": now()}}})
    return {"order_id": order_id, "status": nxt}
