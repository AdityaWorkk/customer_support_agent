import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.exceptions import AuthError


def test_password_hash_roundtrip():
    h = security.hash_password("correct horse")
    assert security.verify_password("correct horse", h) and not security.verify_password("nope", h)


def test_token_types_are_not_interchangeable():
    access = security.create_access_token("u1", "user")
    refresh, jti, _ = security.create_refresh_token("u1")
    assert security.decode_token(access, "access")["sub"] == "u1"
    with pytest.raises(AuthError):
        security.decode_token(refresh, "access")
    with pytest.raises(AuthError):
        security.decode_token("garbage", "access")


def test_static_and_unauthenticated_api():
    from app.main import app
    c = TestClient(app)  # lifespan not started: no database needed
    assert c.get("/health").json() == {"status": "ok"}
    assert "google_client_id" in c.get("/api/v1/config").json()
    r = c.get("/")
    assert r.status_code == 200 and "Content-Security-Policy" in r.headers
    assert c.get("/api/v1/orders").status_code == 401
    assert c.get("/api/v1/admin/stats").status_code == 401
    assert c.post("/api/v1/auth/register", json={"email": "bad", "password": "x", "name": ""}).status_code == 422
