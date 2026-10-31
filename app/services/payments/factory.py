from app.core.config import settings
from app.core.exceptions import PaymentError
from app.services.payments.base import PaymentProvider

_cache: dict[str, PaymentProvider] = {}


def get_provider(name: str | None = None) -> PaymentProvider:
    """Providers are chosen by config only, never by runtime fallback: a failed Stripe
    refund must surface as failed, not silently succeed on the fake."""
    name = name or settings.PAYMENT_PROVIDER
    if name not in _cache:
        if name == "stripe":
            from app.services.payments.stripe_provider import StripeProvider
            _cache[name] = StripeProvider()
        elif name == "fake":
            from app.services.payments.fake_provider import FakeProvider
            _cache[name] = FakeProvider()
        else:
            raise PaymentError(f"Unknown payment provider '{name}'.")
    return _cache[name]
