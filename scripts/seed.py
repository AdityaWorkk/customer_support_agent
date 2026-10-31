"""Seeds demo users and orders. Run:  python -m scripts.seed
Accounts:  user@example.com / UserPass123   admin@example.com / AdminPass123
Uses the configured PAYMENT_PROVIDER, so every order gets a real (Stripe test) or fake payment id."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core import database
from app.core.config import settings
from app.core.database import db
from app.core.security import hash_password
from app.services import catalog, order_rules as rules
from app.services.payments.factory import get_provider

NOW = datetime.now(timezone.utc)
_KEYS = {"headphones": "SKU-HP-201", "kettle": "SKU-KT-044", "backpack": "SKU-BP-310",
         "lamp": "SKU-LM-087", "mug": "SKU-MG-012", "keyboard": "SKU-KB-150"}
CATALOG = {k: (sku, catalog.BY_SKU[sku]["name"], catalog.BY_SKU[sku]["price"]) for k, sku in _KEYS.items()}
# (order id, items, delivery charge, final status, days ago, city, state)
ORDERS = [
    ("ORD-10001", [("headphones", 1)], 6900, "placed", 0, "Mangaluru", "Karnataka"),
    ("ORD-10002", [("kettle", 1), ("mug", 1)], 6900, "packed", 1, "Udupi", "Karnataka"),
    ("ORD-10003", [("backpack", 1)], 9900, "shipped", 2, "Bengaluru", "Karnataka"),
    ("ORD-10004", [("lamp", 2)], 4900, "out_for_delivery", 4, "Mangaluru", "Karnataka"),
    ("ORD-10005", [("keyboard", 1)], 9900, "delivered", 9, "Mysuru", "Karnataka"),
    ("ORD-10006", [("mug", 3)], 4900, "delivered", 12, "Mangaluru", "Karnataka"),
]


async def main() -> None:
    await database.init_indexes()
    await catalog.ensure_seeded(reset_stock=True)
    d, provider = db(), get_provider()
    for email, name, role, pw in [("user@example.com", "Priya Shenoy", "user", "UserPass123"),
                                  ("admin@example.com", "Support Admin", "admin", "AdminPass123")]:
        await d.users.update_one({"email": email}, {"$setOnInsert": {
            "_id": f"usr_seed_{role}", "email": email, "name": name, "role": role, "is_active": True,
            "password_hash": hash_password(pw), "created_at": NOW, "phone": "", "address": ""}}, upsert=True)
    user = await d.users.find_one({"email": "user@example.com"})
    for oid, lines, fee, status, days, city, state in ORDERS:
        items = [{"sku": CATALOG[k][0], "name": CATALOG[k][1], "unit_price": CATALOG[k][2], "qty": q} for k, q in lines]
        totals = rules.compute_totals(items, fee)
        pay = await provider.create_payment(totals["total"], "INR", oid, f"seed-pay-{oid}-{provider.name}")
        path = rules.LOGISTICS_ORDER[: rules.LOGISTICS_ORDER.index(status) + 1]
        start = NOW - timedelta(days=days)
        doc = {"_id": oid, "user_id": user["_id"], "items": items, **totals, "currency": "INR", "status": status,
               "status_history": [{"status": s, "at": start + timedelta(hours=8 * i)} for i, s in enumerate(path)],
               "ordered_at": start, "estimated_delivery": start + timedelta(days=5),
               "order_location": {"city": city, "state": state, "country": "India"},
               "shipping_address": f"14, Lighthouse Road, {city}, {state} 575001",
               "payment": {"provider": provider.name, "payment_id": pay.id},
               "refund": {"status": "none", "refunded_amount": 0}}
        await d.orders.replace_one({"_id": oid}, doc, upsert=True)
    print(f"Seeded {len(ORDERS)} orders using payment provider '{provider.name}'.")
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
