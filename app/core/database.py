"""Mongo access. One async client for the app (PyMongo's native async API, the
successor to Motor) and one sync client used only by the LangGraph checkpointer."""
from pymongo import AsyncMongoClient, MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure
from app.core.config import settings

_async_client: AsyncMongoClient | None = None
_sync_client: MongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _async_client
    if _async_client is None:
        _async_client = AsyncMongoClient(
            settings.MONGODB_URL, maxPoolSize=10, minPoolSize=1,
            serverSelectionTimeoutMS=8000, tz_aware=True,
        )
    return _async_client


def get_sync_client() -> MongoClient:
    global _sync_client
    if _sync_client is None:
        _sync_client = MongoClient(settings.MONGODB_URL, maxPoolSize=5, serverSelectionTimeoutMS=8000)
    return _sync_client


def db():
    return get_client()[settings.DATABASE_NAME]


async def init_indexes() -> None:
    d = db()
    await d.users.create_index("email", unique=True)
    await d.users.create_index("google_sub", unique=True, sparse=True)
    await d.refresh_tokens.create_index("jti", unique=True)
    await d.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
    await d.orders.create_index([("user_id", ASCENDING), ("ordered_at", DESCENDING)])
    await d.sessions.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
    await d.messages.create_index([("session_id", ASCENDING), ("created_at", ASCENDING)])
    await d.complaints.create_index([("status", ASCENDING), ("priority_rank", ASCENDING)])
    await d.complaints.create_index("user_id")
    await d.idempotency.create_index("key", unique=True)
    await d.idempotency.create_index("at", expireAfterSeconds=60 * 60 * 24 * 7)
    await d.fake_payments.create_index("_id")
    await d.processed_events.create_index("event_id", unique=True)
    await d.processed_events.create_index("at", expireAfterSeconds=60 * 60 * 24 * 14)


async def close() -> None:
    global _async_client, _sync_client
    if _async_client:
        await _async_client.close()
    if _sync_client:
        _sync_client.close()
    _async_client = _sync_client = None
