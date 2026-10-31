from pymongo.errors import DuplicateKeyError
from app.core.database import db
from app.core.deps import now
from app.services.payments.base import PaymentEvent


async def handle_event(event: PaymentEvent) -> bool:
    """Idempotent: the same event delivered twice is applied once."""
    from app.services import order_service
    try:
        await db().processed_events.insert_one({"event_id": event.id, "at": now()})
    except DuplicateKeyError:
        return False
    status = "succeeded" if event.type == "refund.succeeded" else "failed"
    await order_service.apply_refund_result(refund_id=event.refund_id, status=status,
                                            order_id=event.metadata.get("order_id"))
    return True
