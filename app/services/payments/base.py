from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PaymentResult:
    id: str
    amount: int
    currency: str
    status: str            # succeeded | pending | failed
    amount_refunded: int = 0
    provider: str = ""
    receipt_url: str | None = None


@dataclass
class RefundResult:
    id: str
    payment_id: str
    amount: int
    status: str            # pending | succeeded | failed
    provider: str = ""


@dataclass
class PaymentEvent:
    id: str
    type: str              # refund.succeeded | refund.failed
    refund_id: str
    payment_id: str
    amount: int
    metadata: dict = field(default_factory=dict)


class PaymentProvider(Protocol):
    name: str

    async def create_payment(self, amount: int, currency: str, order_id: str, idempotency_key: str) -> PaymentResult: ...
    async def refund(self, payment_id: str, amount: int, idempotency_key: str, metadata: dict) -> RefundResult: ...
    async def get_payment(self, payment_id: str) -> PaymentResult: ...
    def parse_webhook(self, payload: bytes, headers: dict) -> PaymentEvent | None: ...
