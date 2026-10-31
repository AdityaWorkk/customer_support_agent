"""Stripe-shaped fake. Same ids, integer minor units, idempotency, async refund
lifecycle (pending -> succeeded) and webhook-style events routed through the SAME
handler the real Stripe webhook uses."""
import asyncio
import json
import secrets
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import db
from app.core.exceptions import PaymentError
from app.services.payments.base import PaymentEvent, PaymentResult, RefundResult


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


class FakeProvider:
    name = "fake"

    async def create_payment(self, amount, currency, order_id, idempotency_key) -> PaymentResult:
        existing = await db().fake_payments.find_one({"idem_key": idempotency_key})
        if existing:
            return self._pay(existing)
        doc = {"_id": _id("pi"), "amount": amount, "currency": currency, "status": "succeeded",
               "refunded": 0, "idem_key": idempotency_key, "order_id": order_id,
               "created_at": datetime.now(timezone.utc)}
        await db().fake_payments.insert_one(doc)
        return self._pay(doc)

    async def refund(self, payment_id, amount, idempotency_key, metadata) -> RefundResult:
        prior = await db().fake_refunds.find_one({"idem_key": idempotency_key})
        if prior:
            return self._ref(prior)
        if amount <= 0:
            raise PaymentError("Refund amount must be positive.")
        # Atomic over-refund guard: only increments if the total stays <= amount charged.
        pay = await db().fake_payments.find_one_and_update(
            {"_id": payment_id, "$expr": {"$lte": [{"$add": ["$refunded", amount]}, "$amount"]}},
            {"$inc": {"refunded": amount}},
        )
        if not pay:
            raise PaymentError("Refund exceeds the amount available to refund.")
        doc = {"_id": _id("re"), "payment_id": payment_id, "amount": amount, "status": "pending",
               "idem_key": idempotency_key, "metadata": metadata, "created_at": datetime.now(timezone.utc)}
        await db().fake_refunds.insert_one(doc)
        asyncio.create_task(self._settle(doc["_id"]))
        return self._ref(doc)

    async def get_payment(self, payment_id) -> PaymentResult:
        doc = await db().fake_payments.find_one({"_id": payment_id})
        if not doc:
            raise PaymentError("Payment not found.")
        return self._pay(doc)

    def parse_webhook(self, payload: bytes, headers: dict) -> PaymentEvent | None:
        d = json.loads(payload)
        return PaymentEvent(**d)

    async def _settle(self, refund_id: str) -> None:
        from app.services.payment_events import handle_event  # lazy: avoid import cycle
        await asyncio.sleep(settings.FAKE_WEBHOOK_DELAY_SECONDS)
        ref = await db().fake_refunds.find_one_and_update({"_id": refund_id}, {"$set": {"status": "succeeded"}})
        if ref:
            await handle_event(PaymentEvent(
                id=_id("evt"), type="refund.succeeded", refund_id=refund_id,
                payment_id=ref["payment_id"], amount=ref["amount"], metadata=ref.get("metadata", {})))

    def _pay(self, d) -> PaymentResult:
        return PaymentResult(id=d["_id"], amount=d["amount"], currency=d["currency"], status=d["status"],
                             amount_refunded=d["refunded"], provider="fake")

    def _ref(self, d) -> RefundResult:
        return RefundResult(id=d["_id"], payment_id=d["payment_id"], amount=d["amount"],
                            status=d["status"], provider="fake")
