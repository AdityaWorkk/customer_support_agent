from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.api.v1.schemas.user_schemas import GoogleIn, LoginIn, PasswordIn, ProfileIn, RegisterIn, GoogleTokenIn
from app.core import ratelimit
from app.core.config import settings
from app.core.deps import current_user
from app.services import auth_service as svc

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "refresh_token"


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, secure=settings.COOKIE_SECURE, samesite="lax",
                    max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path=f"{settings.API_V1_STR}/auth")


def _reply(resp: Response, user: dict, access: str, refresh: str) -> dict:
    _set_cookie(resp, refresh)
    return {"access_token": access, "user": svc.user_public(user)}


def _ip(req: Request) -> str:
    return (req.headers.get("x-forwarded-for") or (req.client.host if req.client else "?")).split(",")[0].strip()


@router.post("/register", status_code=201)
async def register(body: RegisterIn, req: Request, resp: Response):
    ratelimit.check(f"auth:{_ip(req)}", 10)
    return _reply(resp, *await svc.register(body.email, body.password, body.name))


@router.post("/login")
async def login(body: LoginIn, req: Request, resp: Response):
    ratelimit.check(f"auth:{_ip(req)}", 10)
    return _reply(resp, *await svc.login(body.email, body.password))


@router.post("/google")
async def google(body: GoogleIn, req: Request, resp: Response):
    ratelimit.check(f"auth:{_ip(req)}", 10)
    return _reply(resp, *await svc.google_login(body.credential))

@router.post("/google/token")
async def google_token(body: GoogleTokenIn, req: Request, resp: Response):
    ratelimit.check(f"auth:{_ip(req)}", 10)
    return _reply(resp, *await svc.google_login_token(body.access_token))


@router.post("/refresh")
async def refresh(resp: Response, refresh_token: str | None = Cookie(default=None)):
    from app.core.exceptions import AuthError
    if not refresh_token:
        raise AuthError("Not signed in.", code="no_session")
    return _reply(resp, *await svc.refresh(refresh_token))


@router.post("/logout", status_code=204)
async def logout(resp: Response, refresh_token: str | None = Cookie(default=None)):
    await svc.logout(refresh_token)
    resp.delete_cookie(COOKIE, path=f"{settings.API_V1_STR}/auth")


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return svc.user_public(user)


@router.patch("/me")
async def update_me(body: ProfileIn, user: dict = Depends(current_user)):
    return svc.user_public(await svc.update_profile(user["_id"], body.model_dump(exclude_unset=True)))


@router.post("/change-password", status_code=204)
async def change_password(body: PasswordIn, user: dict = Depends(current_user)):
    await svc.change_password(user, body.current_password, body.new_password)
