import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import admin, auth, chat, complaints, orders, shop, webhooks
from app.core import database
from app.core.config import settings
from app.core.exceptions import install_handlers

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("app")


def _setup_langsmith() -> None:
    if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT


@asynccontextmanager
async def lifespan(_: FastAPI):
    _setup_langsmith()
    if settings.is_prod and settings.JWT_SECRET_KEY.startswith(("dev-only", "change-me")):
        raise RuntimeError("Set a strong JWT_SECRET_KEY in production.")
    await database.init_indexes()
    from app.services import catalog
    await catalog.ensure_seeded()
    from app.agents.graph import get_chat_graph
    await run_in_threadpool(get_chat_graph)  # builds graph + checkpointer indexes before first request
    log.info("startup complete provider=%s storage=%s", settings.PAYMENT_PROVIDER, settings.STORAGE_BACKEND)
    yield
    await database.close()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan, docs_url=None if settings.is_prod else "/docs",
              redoc_url=None, openapi_url=None if settings.is_prod else "/openapi.json")
install_handlers(app)

CSP = ("default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; "
       "style-src 'self' https://fonts.googleapis.com https://accounts.google.com/gsi/style; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: blob: https:; "
       "connect-src 'self' https://accounts.google.com/gsi/; frame-src https://accounts.google.com/gsi/; "
       "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


# @app.middleware("http")
# async def headers_and_request_id(request: Request, call_next):
#     rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
#     resp = await call_next(request)
#     resp.headers["X-Request-ID"] = rid
#     resp.headers["X-Content-Type-Options"] = "nosniff"
#     resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
#     if not request.url.path.startswith(("/docs", "/openapi")):
#         resp.headers["Content-Security-Policy"] = CSP
#     if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
#         resp.headers["Cache-Control"] = "no-cache"
#     return resp

@app.middleware("http")
async def headers_and_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not request.url.path.startswith(("/docs", "/openapi")):
        resp.headers["Content-Security-Policy"] = CSP
    if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
        resp.headers["Cache-Control"] = "no-cache"   # always revalidate frontend files
    return resp

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/deep")
async def health_deep():
    await database.db().command("ping")
    return {"status": "ok", "db": "up"}


@app.get(f"{settings.API_V1_STR}/config")
async def public_config():
    return {"google_client_id": settings.GOOGLE_CLIENT_ID, "app_name": settings.PROJECT_NAME}


for r in (auth.router, chat.router, orders.router, complaints.router, shop.router, admin.router, admin.jobs, webhooks.router):
    app.include_router(r, prefix=settings.API_V1_STR)

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
