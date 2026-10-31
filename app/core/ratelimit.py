"""Sliding-window limiter. In-memory: correct for a single instance (Render free).
Swap for Redis or a Mongo TTL collection before running more than one instance."""
import time
from collections import defaultdict, deque
from app.core.exceptions import RateLimitError

_hits: dict[str, deque] = defaultdict(deque)


def check(key: str, limit: int, window: int = 60) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise RateLimitError(f"Too many requests. Wait about {int(window - (now - q[0])) + 1}s and try again.")
    q.append(now)
