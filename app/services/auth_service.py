from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.core.database import db
from app.core.deps import now
from app.core.exceptions import AuthError, ConflictError
from app.core.security import (create_access_token, create_refresh_token, decode_token, hash_password,
                               random_id, sha256, verify_google_token, verify_password, verify_google_access_token)

DUMMY_HASH = hash_password("timing-equalizer")


def user_public(u: dict) -> dict:
    return {"id": u["_id"], "email": u["email"], "name": u.get("name", ""), "phone": u.get("phone", ""),
            "address": u.get("address", ""), "role": u["role"], "has_password": bool(u.get("password_hash")),
            "google_linked": bool(u.get("google_sub")), "picture": u.get("picture")}


async def _issue_tokens(user: dict) -> tuple[str, str]:
    access = create_access_token(user["_id"], user["role"])
    refresh, jti, exp = create_refresh_token(user["_id"])
    await db().refresh_tokens.insert_one({"jti": jti, "user_id": user["_id"], "hash": sha256(refresh),
                                          "expires_at": exp, "created_at": now()})
    return access, refresh


async def register(email: str, password: str, name: str) -> tuple[dict, str, str]:
    doc = {"_id": random_id("usr_"), "email": email.lower(), "name": name.strip(), "role": "user",
           "password_hash": hash_password(password), "is_active": True, "created_at": now()}
    try:
        await db().users.insert_one(doc)
    except DuplicateKeyError:
        raise ConflictError("An account with this email already exists. Sign in instead.")
    access, refresh = await _issue_tokens(doc)
    return doc, access, refresh


async def login(email: str, password: str) -> tuple[dict, str, str]:
    u = await db().users.find_one({"email": email.lower(), "is_active": True})
    ok = verify_password(password, u["password_hash"] if u and u.get("password_hash") else DUMMY_HASH)
    if not u or not u.get("password_hash") or not ok:
        raise AuthError("Email or password is incorrect.", code="bad_credentials")
    access, refresh = await _issue_tokens(u)
    return u, access, refresh


# async def google_login(credential: str) -> tuple[dict, str, str]:
#     c = await verify_google_token(credential)
#     sub, email = c["sub"], c["email"].lower()
#     u = await db().users.find_one({"google_sub": sub})
#     if not u:
#         # Linking policy: Google verified this email, so attach to an existing account with it.
#         u = await db().users.find_one({"email": email})
#         if u:
#             await db().users.update_one({"_id": u["_id"]}, {"$set": {"google_sub": sub, "picture": c.get("picture")}})
#         else:
#             u = {"_id": random_id("usr_"), "email": email, "name": c.get("name", ""), "role": "user",
#                  "google_sub": sub, "picture": c.get("picture"), "is_active": True, "created_at": now()}
#             await db().users.insert_one(u)
#     if not u.get("is_active", True):
#         raise AuthError("Account disabled.")
#     access, refresh = await _issue_tokens(u)
#     return u, access, refresh

async def google_login(credential: str) -> tuple[dict, str, str]:
    return await _login_with_google_claims(await verify_google_token(credential))


async def google_login_token(access_token: str) -> tuple[dict, str, str]:
    return await _login_with_google_claims(await verify_google_access_token(access_token))


async def _login_with_google_claims(c: dict) -> tuple[dict, str, str]:
    sub, email = c["sub"], c["email"].lower()
    u = await db().users.find_one({"google_sub": sub})
    if not u:
        # Linking policy: Google verified this email, so attach to an existing account with it.
        u = await db().users.find_one({"email": email})
        if u:
            await db().users.update_one({"_id": u["_id"]}, {"$set": {"google_sub": sub, "picture": c.get("picture")}})
        else:
            u = {"_id": random_id("usr_"), "email": email, "name": c.get("name", ""), "role": "user",
                 "google_sub": sub, "picture": c.get("picture"), "is_active": True, "created_at": now()}
            await db().users.insert_one(u)
    if not u.get("is_active", True):
        raise AuthError("Account disabled.")
    access, refresh = await _issue_tokens(u)
    return u, access, refresh


async def refresh(refresh_token: str) -> tuple[dict, str, str]:
    p = decode_token(refresh_token, "refresh")
    rec = await db().refresh_tokens.find_one_and_delete({"jti": p["jti"], "hash": sha256(refresh_token)})
    if not rec:  # reused or revoked token: kill every session for this user
        await db().refresh_tokens.delete_many({"user_id": p["sub"]})
        raise AuthError("Session is no longer valid. Sign in again.", code="refresh_reuse")
    u = await db().users.find_one({"_id": p["sub"], "is_active": True})
    if not u:
        raise AuthError("Account not found.")
    access, new_refresh = await _issue_tokens(u)
    return u, access, new_refresh


async def logout(refresh_token: str | None) -> None:
    if not refresh_token:
        return
    try:
        p = decode_token(refresh_token, "refresh")
        await db().refresh_tokens.delete_one({"jti": p["jti"]})
    except AuthError:
        pass


async def update_profile(user_id: str, fields: dict) -> dict:
    fields = {k: v.strip() for k, v in fields.items() if v is not None}
    if fields:
        await db().users.update_one({"_id": user_id}, {"$set": fields})
    return await db().users.find_one({"_id": user_id})


async def change_password(user: dict, current: str | None, new: str) -> None:
    if user.get("password_hash") and not verify_password(current or "", user["password_hash"]):
        raise AuthError("Current password is incorrect.", code="bad_credentials")
    await db().users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(new)}})
    await db().refresh_tokens.delete_many({"user_id": user["_id"]})
