"""Pure business rules: no I/O, trivially testable. The LLM never touches these."""
from datetime import datetime

STATES = ["placed", "packed", "shipped", "out_for_delivery", "delivered",
          "cancel_requested", "cancelled", "refunded"]

# Forward-only logistics path + terminal/cancel branches.
TRANSITIONS: dict[str, set[str]] = {
    "placed": {"packed", "cancel_requested"},
    "packed": {"shipped", "cancel_requested"},
    "shipped": {"out_for_delivery", "cancel_requested"},
    "out_for_delivery": {"delivered", "cancel_requested"},
    "delivered": {"refunded"},
    "cancel_requested": {"cancelled", "placed", "packed", "shipped", "out_for_delivery"},
    "cancelled": set(),
    "refunded": set(),
}

CANCELLABLE = {"placed", "packed", "shipped", "out_for_delivery"}
# Before the parcel leaves the warehouse the delivery fee is returned too.
DELIVERY_FEE_REFUNDABLE = {"placed", "packed"}

LOGISTICS_ORDER = ["placed", "packed", "shipped", "out_for_delivery", "delivered"]


def can_transition(src: str, dst: str) -> bool:
    return dst in TRANSITIONS.get(src, set())


def next_logistics_state(status: str) -> str | None:
    if status in LOGISTICS_ORDER and status != "delivered":
        return LOGISTICS_ORDER[LOGISTICS_ORDER.index(status) + 1]
    return None


def compute_cancel_refund(order: dict) -> dict:
    """Returns eligibility and exact refund (integer minor units)."""
    status = order["status"]
    refund_state = (order.get("refund") or {}).get("status", "none")
    if refund_state != "none":
        return {"eligible": False, "reason": "A refund is already in progress or completed for this order.",
                "refund_amount": 0, "retained_delivery_fee": 0}
    if status not in CANCELLABLE:
        reasons = {
            "delivered": "This order was already delivered and can no longer be cancelled. You can report a problem with it instead.",
            "cancelled": "This order is already cancelled.",
            "cancel_requested": "A cancellation is already in progress.",
            "refunded": "This order was already refunded.",
        }
        return {"eligible": False, "reason": reasons.get(status, "This order cannot be cancelled right now."),
                "refund_amount": 0, "retained_delivery_fee": 0}
    total, fee = int(order["total"]), int(order.get("delivery_charge", 0))
    retained = 0 if status in DELIVERY_FEE_REFUNDABLE else min(fee, total)
    return {"eligible": True, "reason": "", "refund_amount": max(total - retained, 0),
            "retained_delivery_fee": retained}


def compute_defect_refund(order: dict) -> int:
    """Approved defect claims refund everything not already refunded."""
    return max(int(order["total"]) - int((order.get("refund") or {}).get("refunded_amount", 0)), 0)


def fmt_money(minor: int, currency: str = "INR") -> str:
    symbols = {"INR": "₹", "USD": "$", "EUR": "€"}
    return f"{symbols.get(currency, currency + ' ')}{minor / 100:,.2f}"


FREE_DELIVERY_OVER = 150000   # subtotal (paise) at or above which delivery is free
STANDARD_DELIVERY = 6900


def delivery_charge_for(subtotal: int) -> int:
    return 0 if subtotal >= FREE_DELIVERY_OVER else STANDARD_DELIVERY


def compute_totals(items: list[dict], delivery_charge: int, tax_rate_bp: int = 1800, discount: int = 0) -> dict:
    """tax_rate_bp is basis points (1800 = 18%). Integer math only."""
    subtotal = sum(i["unit_price"] * i["qty"] for i in items)
    tax = (max(subtotal - discount, 0) * tax_rate_bp) // 10000
    total = max(subtotal - discount, 0) + tax + delivery_charge
    return {"subtotal": subtotal, "tax": tax, "discount": discount,
            "delivery_charge": delivery_charge, "total": total}


# ---- complaints ----
CATEGORIES = {
    # category: (priority, sla_hours)
    "defective_product": ("high", 24),
    "staff_misconduct": ("high", 24),
    "billing_issue": ("high", 24),
    "late_delivery": ("medium", 48),
    "wrong_item": ("medium", 48),
    "website_performance": ("low", 120),
    "other": ("low", 120),
}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
ESCALATION_LEVELS = {1: "Support agent", 2: "Team lead", 3: "Operations manager"}


def escalation_level(created_at: datetime, now: datetime, sla_hours: int) -> int:
    elapsed_h = (now - created_at).total_seconds() / 3600
    return min(1 + int(elapsed_h // sla_hours), 3) if elapsed_h >= 0 else 1
