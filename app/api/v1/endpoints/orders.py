from fastapi import APIRouter, Depends

from app.api.v1.schemas.order_schemas import CancelIn
from app.core.deps import current_user
from app.services import order_service as svc

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def list_orders(user: dict = Depends(current_user)):
    return await svc.list_orders(user["_id"], limit=50)


@router.get("/{order_id}")
async def get_order(order_id: str, user: dict = Depends(current_user)):
    return svc.public(await svc.get_order(user["_id"], order_id))


@router.get("/{order_id}/cost-breakdown")
async def cost(order_id: str, user: dict = Depends(current_user)):
    return await svc.cost_breakdown(user["_id"], order_id)


@router.get("/{order_id}/cancel-preview")
async def preview(order_id: str, user: dict = Depends(current_user)):
    return await svc.cancel_preview(user["_id"], order_id)


@router.post("/{order_id}/cancel")
async def cancel(order_id: str, _: CancelIn, user: dict = Depends(current_user)):
    return await svc.cancel_order(user["_id"], order_id)
