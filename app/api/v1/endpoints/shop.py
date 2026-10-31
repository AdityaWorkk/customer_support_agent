from fastapi import APIRouter, Depends

from app.api.v1.schemas.shop_schemas import AddItemIn, CheckoutIn, QtyIn
from app.core import ratelimit
from app.core.deps import current_user
from app.services import catalog, shop_service as svc

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get("/products")
async def products(_: dict = Depends(current_user)):
    return await catalog.list_products()


@router.get("/cart")
async def cart(user: dict = Depends(current_user)):
    return await svc.get_cart(user["_id"])


@router.post("/cart/items")
async def add(body: AddItemIn, user: dict = Depends(current_user)):
    return await svc.add_item(user["_id"], body.sku, body.qty)


@router.put("/cart/items/{sku}")
async def set_qty(sku: str, body: QtyIn, user: dict = Depends(current_user)):
    return await svc.set_quantity(user["_id"], sku, body.qty)


@router.delete("/cart/items/{sku}")
async def remove(sku: str, user: dict = Depends(current_user)):
    return await svc.remove_item(user["_id"], sku)


@router.delete("/cart")
async def clear(user: dict = Depends(current_user)):
    return await svc.clear_cart(user["_id"])


@router.post("/checkout", status_code=201)
async def checkout(body: CheckoutIn, user: dict = Depends(current_user)):
    ratelimit.check(f"checkout:{user['_id']}", 6)
    return await svc.checkout(user, body.address, body.city, body.state, body.pincode, body.idempotency_key)
