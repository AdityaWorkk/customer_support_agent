from typing import Literal
from pydantic import BaseModel, Field


class CancelIn(BaseModel):
    confirm: Literal[True]


class ComplaintIn(BaseModel):
    category: Literal["late_delivery", "wrong_item", "staff_misconduct", "website_performance", "billing_issue", "other"]
    description: str = Field(min_length=5, max_length=2000)
    order_id: str | None = Field(default=None, max_length=32)


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "resolve"]
    note: str = Field(default="", max_length=500)
