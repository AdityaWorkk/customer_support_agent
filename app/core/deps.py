from datetime import datetime, timezone
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import db
from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_token

_bearer = HTTPBearer(auto_error=False)


async def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if not creds:
        raise AuthError("Sign in to continue.")
    payload = decode_token(creds.credentials, "access")
    user = await db().users.find_one({"_id": payload["sub"], "is_active": True})
    if not user:
        raise AuthError("Account not found or disabled.")
    return user


async def admin_user(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise ForbiddenError("Admin access required.")
    return user


def now() -> datetime:
    return datetime.now(timezone.utc)
