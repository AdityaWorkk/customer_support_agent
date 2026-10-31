"""Cart and checkout. Prices, stock and totals always come from the database and
order_rules, never from the client. Checkout is idempotent and rolls stock back on failure."""
from datetime import timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import db
from app.core.deps import now
from app.core.exceptions import AppError, ConflictError, NotFoundError, PaymentError
from app.services import order_rules as rules, order_service
from app.services.payments.factory import get_provider

MAX_QTY = 10


async def _product(sku: str) -> dict:
    p = await db().products.find_one({"_id": sku})
    if not p:
        raise NotFoundError("That product doesn't exist.")
    return p


async def _raw(user_id: str) -> list[dict]:
    return (await db().carts.find_one({"_id": user_id}) or {}).get("items", [])


async def _save(user_id: str, items: list[dict]) -> None:
    await db().carts.update_one({"_id": user_id}, {"$set": {"items": items, "updated_at": now()}}, upsert=True)


async def get_cart(user_id: str) -> dict:
    raw = await _raw(user_id)
    prods = {p["_id"]: p async for p in db().products.find({"_id": {"$in": [i["sku"] for i in raw]}})}
    lines = []
    for i in raw:
        p = prods.get(i["sku"])
        if not p:
            continue
        qty = min(i["qty"], MAX_QTY)
        lines.append({"sku": p["_id"], "name": p["name"], "category": p["category"], "unit_price": p["price"],
                      "qty": qty, "line_total": p["price"] * qty, "stock": p["stock"], "in_stock": p["stock"] >= qty})
    delivery = rules.delivery_charge_for(sum(l["line_total"] for l in lines)) if lines else 0
    return {"items": lines, **rules.compute_totals(lines, delivery), "currency": "INR",
            "count": sum(l["qty"] for l in lines), "free_delivery_over": rules.FREE_DELIVERY_OVER}


async def set_quantity(user_id: str, sku: str, qty: int) -> dict:
    if qty <= 0:
        return await remove_item(user_id, sku)
    p = await _product(sku)
    if qty > MAX_QTY:
        raise AppError(f"You can order up to {MAX_QTY} of one item.", code="max_qty")
    if qty > p["stock"]:
        raise ConflictError("Sold out." if p["stock"] == 0 else f"Only {p['stock']} left in stock.", code="out_of_stock")
    items = await _raw(user_id)
    for i in items:
        if i["sku"] == sku:
            i["qty"] = qty
            break
    else:
        items.append({"sku": sku, "qty": qty})
    await _save(user_id, items)
    return await get_cart(user_id)


async def add_item(user_id: str, sku: str, qty: int = 1) -> dict:
    current = next((i["qty"] for i in await _raw(user_id) if i["sku"] == sku), 0)
    return await set_quantity(user_id, sku, current + qty)


async def remove_item(user_id: str, sku: str) -> dict:
    await _save(user_id, [i for i in await _raw(user_id) if i["sku"] != sku])
    return await get_cart(user_id)


async def clear_cart(user_id: str) -> dict:
    await db().carts.delete_one({"_id": user_id})
    return await get_cart(user_id)


async def _next_order_id() -> str:
    c = await db().counters.find_one_and_update({"_id": "order"}, {"$inc": {"seq": 1}}, upsert=True,
                                                return_document=ReturnDocument.AFTER)
    return f"ORD-{20000 + c['seq']}"


async def checkout(user: dict, address: str, city: str, state: str, pincode: str, idempotency_key: str) -> dict:
    uid = user["_id"]
    key = f"checkout:{uid}:{idempotency_key}"
    try:
        await db().idempotency.insert_one({"key": key, "at": now()})
    except DuplicateKeyError:
        rec = await db().idempotency.find_one({"key": key})
        if rec and rec.get("order_id"):  # double click or retry: return the order that was already created
            return order_service.public(await db().orders.find_one({"_id": rec["order_id"]}))
        raise ConflictError("This checkout is already being processed.", code="in_progress")

    reserved: list[dict] = []
    try:
        cart = await get_cart(uid)
        if not cart["items"]:
            raise ConflictError("Your cart is empty.", code="empty_cart")
        for line in cart["items"]:  # atomic per-item stock reservation
            r = await db().products.update_one({"_id": line["sku"], "stock": {"$gte": line["qty"]}},
                                               {"$inc": {"stock": -line["qty"]}})
            if not r.modified_count:
                raise ConflictError(f"{line['name']} is no longer available in that quantity. Update your cart and try again.", code="out_of_stock")
            reserved.append(line)

        order_id = await _next_order_id()
        provider = get_provider()
        pay = await provider.create_payment(cart["total"], "INR", order_id, f"pay-{order_id}")
        t = now()
        doc = {"_id": order_id, "user_id": uid, "currency": "INR", "status": "placed",
               "items": [{"sku": l["sku"], "name": l["name"], "unit_price": l["unit_price"], "qty": l["qty"]} for l in cart["items"]],
               "subtotal": cart["subtotal"], "tax": cart["tax"], "discount": cart["discount"],
               "delivery_charge": cart["delivery_charge"], "total": cart["total"],
               "status_history": [{"status": "placed", "at": t}], "ordered_at": t,
               "estimated_delivery": t + timedelta(days=5),
               "order_location": {"city": city, "state": state, "country": "India"},
               "shipping_address": f"{address}, {city}, {state} {pincode}",
               "payment": {"provider": provider.name, "payment_id": pay.id},
               "refund": {"status": "none", "refunded_amount": 0}}
        try:
            await db().orders.insert_one(doc)
        except Exception:
            try:  # charged but not recorded: give the money back
                await provider.refund(pay.id, cart["total"], f"refund-{order_id}-orphan", {"order_id": order_id})
            except PaymentError:
                pass
            raise
        await db().carts.delete_one({"_id": uid})
        await db().idempotency.update_one({"key": key}, {"$set": {"order_id": order_id}})
        return order_service.public(doc)
    except Exception:
        for l in reserved:
            await db().products.update_one({"_id": l["sku"]}, {"$inc": {"stock": l["qty"]}})
        await db().idempotency.delete_one({"key": key})
        raise
