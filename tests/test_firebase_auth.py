# tests/test_firebase_auth.py
# Unit tests for Firebase Authentication dependency (get_current_officer / require_admin).
# Firebase token verification is mocked — no real Firebase project/users required.
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services.firebase_auth import get_current_officer, require_admin


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(officer: dict = Depends(get_current_officer)):
        return {"uid": officer["uid"], "role": officer["role"], "email": officer.get("email")}

    @app.get("/admin-only")
    async def admin_only(officer: dict = Depends(require_admin)):
        return {"uid": officer["uid"], "role": officer["role"]}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


def _fake_verify(claims):
    def _inner(token):
        return claims

    return _inner


# ── A. Missing Authorization header → 401 ─────────────────────────
def test_missing_authorization_header_401(client):
    resp = client.get("/protected")
    assert resp.status_code == 401


# ── B. Malformed token → 401 ───────────────────────────────────────
def test_malformed_authorization_header_401(client):
    resp = client.get("/protected", headers={"Authorization": "just-a-string"})
    assert resp.status_code == 401

    resp2 = client.get("/protected", headers={"Authorization": "Bearer "})
    assert resp2.status_code == 401


# ── C. Invalid/expired token → 401 ─────────────────────────────────
def test_invalid_or_expired_token_401(client, monkeypatch):
    def _bad(token):
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase ID token")

    monkeypatch.setattr("app.services.firebase_auth._verify_id_token", _bad)
    resp = client.get("/protected", headers={"Authorization": "Bearer invalid-token"})
    assert resp.status_code == 401


# ── D. Valid Firebase token → authenticated identity ───────────────
def test_valid_token_returns_identity(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.firebase_auth._verify_id_token",
        _fake_verify({"uid": "firebase-uid-123", "email": "officer@example.com", "role": "officer"}),
    )
    resp = client.get("/protected", headers={"Authorization": "Bearer valid-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == "firebase-uid-123"
    assert body["email"] == "officer@example.com"
    assert body["role"] == "officer"


def test_no_role_claim_defaults_to_officer(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.firebase_auth._verify_id_token",
        _fake_verify({"uid": "uid-no-role", "email": "a@b.c"}),
    )
    resp = client.get("/protected", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "officer"


# ── E. Insufficient role → 403 ─────────────────────────────────────
def test_officer_cannot_access_admin_route_403(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.firebase_auth._verify_id_token",
        _fake_verify({"uid": "uid-officer", "role": "officer"}),
    )
    resp = client.get("/admin-only", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 403


# ── F. Valid auth → protected route works ──────────────────────────
def test_admin_can_access_admin_route(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.firebase_auth._verify_id_token",
        _fake_verify({"uid": "uid-admin", "role": "admin"}),
    )
    resp = client.get("/admin-only", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
