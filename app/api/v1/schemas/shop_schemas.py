from pydantic import BaseModel, Field


class AddItemIn(BaseModel):
    sku: str = Field(max_length=32)
    qty: int = Field(default=1, ge=1, le=10)


class QtyIn(BaseModel):
    qty: int = Field(ge=0, le=10)


class CheckoutIn(BaseModel):
    address: str = Field(min_length=5, max_length=200)
    city: str = Field(min_length=2, max_length=60)
    state: str = Field(min_length=2, max_length=60)
    pincode: str = Field(pattern=r"^\d{6}$")
    idempotency_key: str = Field(min_length=8, max_length=64)
