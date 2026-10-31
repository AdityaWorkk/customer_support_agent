"""Stripe test-mode provider. Stripe's SDK is sync, so calls run in a thread pool."""
import stripe
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import PaymentError
from app.services.payments.base import PaymentEvent, PaymentResult, RefundResult


class StripeProvider:
    name = "stripe"

    def __init__(self):
        if not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
            raise PaymentError("Only Stripe test keys (sk_test_...) are allowed in this project.")
        self.client = stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=2)

    async def create_payment(self, amount, currency, order_id, idempotency_key) -> PaymentResult:
        def _go():
            return self.client.v1.payment_intents.create(
                params={"amount": amount, "currency": currency.lower(), "payment_method": "pm_card_visa",
                        "confirm": True, "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
                        "metadata": {"order_id": order_id}},
                options={"idempotency_key": idempotency_key})
        try:
            pi = await run_in_threadpool(_go)
        except stripe.StripeError as e:
            raise PaymentError(f"Stripe error: {e.user_message or str(e)}")
        return self._pay(pi)

    async def refund(self, payment_id, amount, idempotency_key, metadata) -> RefundResult:
        def _go():
            return self.client.v1.refunds.create(
                params={"payment_intent": payment_id, "amount": amount, "metadata": metadata},
                options={"idempotency_key": idempotency_key})
        try:
            r = await run_in_threadpool(_go)
        except stripe.StripeError as e:
            raise PaymentError(f"Stripe refund failed: {e.user_message or str(e)}")
        return RefundResult(id=r.id, payment_id=payment_id, amount=r.amount, status=r.status or "pending", provider="stripe")

    async def get_payment(self, payment_id) -> PaymentResult:
        def _go():
            return self.client.v1.payment_intents.retrieve(payment_id, params={"expand": ["latest_charge"]})
        try:
            pi = await run_in_threadpool(_go)
        except stripe.StripeError as e:
            raise PaymentError(f"Stripe error: {e.user_message or str(e)}")
        return self._pay(pi)

    def parse_webhook(self, payload: bytes, headers: dict) -> PaymentEvent | None:
        try:
            event = stripe.Webhook.construct_event(payload, headers.get("stripe-signature", ""),
                                                   settings.STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.SignatureVerificationError):
            raise PaymentError("Invalid webhook signature.", status_code=400, code="bad_signature")
        # Card refunds usually arrive as refund.created already 'succeeded'; refund.updated covers async ones.
        if event["type"] not in ("refund.created", "refund.updated"):
            return None
        r = event["data"]["object"]
        if r.get("status") not in ("succeeded", "failed"):
            return None
        return PaymentEvent(id=event["id"], type=f"refund.{r['status']}", refund_id=r["id"],
                            payment_id=r.get("payment_intent") or "", amount=r["amount"],
                            metadata=dict(r.get("metadata") or {}))

    def _pay(self, pi) -> PaymentResult:
        charge = getattr(pi, "latest_charge", None)
        refunded = getattr(charge, "amount_refunded", 0) if charge and not isinstance(charge, str) else 0
        receipt = getattr(charge, "receipt_url", None) if charge and not isinstance(charge, str) else None
        status = "succeeded" if pi.status == "succeeded" else ("failed" if pi.status == "canceled" else "pending")
        return PaymentResult(id=pi.id, amount=pi.amount, currency=pi.currency.upper(), status=status,
                             amount_refunded=refunded or 0, provider="stripe", receipt_url=receipt)
