import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as g_requests
from google.oauth2 import id_token

from app.core.config import settings
from app.core.exceptions import AuthError

import httpx

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, role: str) -> str:
    exp = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "role": role, "type": "access", "exp": exp},
                      settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    exp = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    token = jwt.encode({"sub": user_id, "jti": jti, "type": "refresh", "exp": exp},
                       settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, exp


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired. Please sign in again.", code="token_expired")
    except jwt.PyJWTError:
        raise AuthError("Invalid token.", code="invalid_token")
    if payload.get("type") != expected_type:
        raise AuthError("Wrong token type.", code="invalid_token")
    return payload


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def random_id(prefix: str = "") -> str:
    return prefix + secrets.token_hex(8)


async def verify_google_token(credential: str) -> dict:
    """Verifies signature, expiry and audience of a Google ID token. Returns claims."""
    if not settings.GOOGLE_CLIENT_ID:
        raise AuthError("Google sign-in is not configured.", code="sso_disabled")

    def _verify():
        return id_token.verify_oauth2_token(credential, g_requests.Request(), settings.GOOGLE_CLIENT_ID)

    try:
        claims = await run_in_threadpool(_verify)
    except ValueError:
        raise AuthError("Google sign-in failed. Try again.", code="invalid_google_token")
    if not claims.get("email_verified"):
        raise AuthError("Your Google email is not verified.", code="email_unverified")
    return claims


async def verify_google_access_token(access_token: str) -> dict:
    """Popup flow: confirm the token was issued to OUR client id, then read the profile."""
    if not settings.GOOGLE_CLIENT_ID:
        raise AuthError("Google sign-in is not configured.", code="sso_disabled")
    bad = AuthError("Google sign-in failed. Try again.", code="invalid_google_token")
    async with httpx.AsyncClient(timeout=10) as c:
        ti = await c.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": access_token})
        if ti.status_code != 200 or ti.json().get("aud") != settings.GOOGLE_CLIENT_ID:
            raise bad
        ui = await c.get("https://openidconnect.googleapis.com/v1/userinfo",
                         headers={"Authorization": f"Bearer {access_token}"})
    if ui.status_code != 200:
        raise bad
    claims = ui.json()
    if claims.get("email_verified") not in (True, "true"):
        raise AuthError("Your Google email is not verified.", code="email_unverified")
    return claims
