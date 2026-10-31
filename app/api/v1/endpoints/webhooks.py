from fastapi import APIRouter, Request

from app.services.payment_events import handle_event
from app.services.payments.factory import get_provider

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(request: Request):
    provider = get_provider("stripe")
    event = provider.parse_webhook(await request.body(), dict(request.headers))  # verifies signature
    if event:
        await handle_event(event)
    return {"received": True}
