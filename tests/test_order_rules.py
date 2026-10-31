from datetime import datetime, timedelta, timezone

import pytest
from app.services import order_rules as r


def order(status="placed", total=100000, fee=6900, refund="none"):
    return {"status": status, "total": total, "delivery_charge": fee, "refund": {"status": refund}}


def test_full_refund_before_dispatch():
    c = r.compute_cancel_refund(order("placed"))
    assert c["eligible"] and c["refund_amount"] == 100000 and c["retained_delivery_fee"] == 0


def test_delivery_fee_kept_after_dispatch():
    c = r.compute_cancel_refund(order("shipped"))
    assert c["eligible"] and c["refund_amount"] == 93100 and c["retained_delivery_fee"] == 6900


def test_out_for_delivery_is_cancellable_with_fee_kept():
    assert r.compute_cancel_refund(order("out_for_delivery"))["refund_amount"] == 93100


def test_fee_larger_than_total_never_goes_negative():
    c = r.compute_cancel_refund(order("shipped", total=5000, fee=9900))
    assert c["refund_amount"] == 0 and c["retained_delivery_fee"] == 5000


@pytest.mark.parametrize("status", ["delivered", "cancelled", "cancel_requested", "refunded"])
def test_terminal_states_not_cancellable(status):
    c = r.compute_cancel_refund(order(status))
    assert not c["eligible"] and c["refund_amount"] == 0 and c["reason"]


@pytest.mark.parametrize("state", ["requested", "pending", "succeeded", "failed"])
def test_no_second_refund_when_one_exists(state):
    assert not r.compute_cancel_refund(order("placed", refund=state))["eligible"]


def test_defect_refund_is_remaining_balance():
    o = {"total": 50000, "refund": {"refunded_amount": 0}}
    assert r.compute_defect_refund(o) == 50000
    o["refund"]["refunded_amount"] = 20000
    assert r.compute_defect_refund(o) == 30000


def test_totals_use_integer_math():
    items = [{"unit_price": 249900, "qty": 1}, {"unit_price": 79900, "qty": 2}]
    t = r.compute_totals(items, 6900)
    assert t["subtotal"] == 409700 and t["tax"] == 73746 and t["total"] == 409700 + 73746 + 6900
    assert all(isinstance(v, int) for v in t.values())


def test_state_machine():
    assert r.can_transition("placed", "packed") and not r.can_transition("delivered", "placed")
    assert r.next_logistics_state("shipped") == "out_for_delivery" and r.next_logistics_state("delivered") is None


def test_escalation_levels_cap_at_three():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert r.escalation_level(t0, t0 + timedelta(hours=1), 24) == 1
    assert r.escalation_level(t0, t0 + timedelta(hours=25), 24) == 2
    assert r.escalation_level(t0, t0 + timedelta(hours=500), 24) == 3


def test_priority_matrix():
    assert r.CATEGORIES["defective_product"] == ("high", 24)
    assert r.CATEGORIES["website_performance"][0] == "low"


def test_fmt_money():
    assert r.fmt_money(93100, "INR") == "₹931.00"


def test_delivery_charge_free_over_threshold():
    assert r.delivery_charge_for(149999) == 6900
    assert r.delivery_charge_for(150000) == 0


def test_catalogue_is_consistent():
    from app.services import catalog
    skus = [p["sku"] for p in catalog.PRODUCTS]
    assert len(skus) == len(set(skus))
    assert all(isinstance(p["price"], int) and p["price"] > 0 and p["stock"] >= 0 for p in catalog.PRODUCTS)
