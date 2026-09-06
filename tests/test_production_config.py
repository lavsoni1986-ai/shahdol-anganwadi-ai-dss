# tests/test_production_config.py
# P0 production-hardening tests: PORT, CORS, security headers,
# WhatsApp Meta signature, and Firestore rules/config files.
import hashlib
import hmac
import pathlib

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ── 1. PORT configuration ─────────────────────────────────────────
def test_port_defaults_to_8000_when_absent(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    from app.config import Settings
    s = Settings()
    assert s.port == 8000


def test_port_respects_env(monkeypatch):
    monkeypatch.setenv("PORT", "9090")
    from app.config import Settings
    s = Settings()
    assert s.port == 9090


# ── 2. Production CORS ─────────────────────────────────────────────
def test_cors_wildcard_never_with_credentials():
    from app.main import _resolve_cors

    # debug + no explicit origins -> wildcard WITHOUT credentials
    origins, wildcard, credentials = _resolve_cors(True, "", "")
    assert origins == ["*"]
    assert wildcard is True
    assert credentials is False  # never "*" + credentials

    # production + explicit origin -> allowlist WITH credentials
    origins, wildcard, credentials = _resolve_cors(False, "https://app.example.com", "https://api.example.com")
    assert wildcard is False
    assert credentials is True
    assert "https://app.example.com" in origins
    assert "https://api.example.com" in origins

    # production + only APP_PUBLIC_URL -> allowlist includes it
    origins, wildcard, credentials = _resolve_cors(False, "", "https://dss.example.com")
    assert wildcard is False
    assert "https://dss.example.com" in origins


# ── 3. Security headers on the live app ────────────────────────────
def test_security_headers_present():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp


# ── 4. WhatsApp Meta signature verification ────────────────────────
def _sig(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def test_meta_signature_valid_accepted():
    from app.services.whatsapp import verify_meta_signature

    secret = "test_app_secret"
    raw = b'{"object":"whatsapp_business_account"}'
    assert verify_meta_signature(raw, _sig(raw, secret), secret) is True


def test_meta_signature_invalid_rejected():
    from app.services.whatsapp import verify_meta_signature

    secret = "test_app_secret"
    raw = b'{"object":"whatsapp_business_account"}'
    wrong = _sig(raw, "wrong_secret")
    assert verify_meta_signature(raw, wrong, secret) is False


def test_meta_signature_missing_rejected():
    from app.services.whatsapp import verify_meta_signature

    assert verify_meta_signature(b"{}", "", "test_app_secret") is False
    assert verify_meta_signature(b"{}", "sha256=abc", "") is False


# ── 5. Firebase / Firestore rules & config files ───────────────────
def test_firestore_rules_file_exists_and_denies_clients():
    rules = (REPO_ROOT / "firestore.rules").read_text(encoding="utf-8")
    assert "service cloud.firestore" in rules
    assert "allow read, write: if false" in rules  # deny-by-default for clients


def test_firebase_config_files_exist():
    assert (REPO_ROOT / "firebase.json").exists()
    assert (REPO_ROOT / "firestore.indexes.json").exists()
    fb = (REPO_ROOT / "firebase.json").read_text(encoding="utf-8")
    assert "firestore.rules" in fb


# ── 6. YOLO model path configuration ───────────────────────────────
def test_yolo_model_path_default():
    from app.config import Settings
    s = Settings()
    assert s.yolo_model_path == "app/models/yolo11m.pt"


def test_yolo_model_path_respects_env(monkeypatch):
    monkeypatch.setenv("YOLO_MODEL_PATH", "/app/app/models/yolo11m.pt")
    from app.config import Settings
    s = Settings()
    assert s.yolo_model_path == "/app/app/models/yolo11m.pt"


def test_yolo_model_file_present_locally():
    assert (REPO_ROOT / "app" / "models" / "yolo11m.pt").exists()


# ── 7. Docker configuration files exist ────────────────────────────
def test_dockerfiles_present():
    assert (REPO_ROOT / "Dockerfile").exists()
    assert (REPO_ROOT / ".dockerignore").exists()
    assert (REPO_ROOT / "docker" / "entrypoint.sh").exists()
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "mcr.microsoft.com/playwright/python:v1.62.0-noble" in dockerfile
    assert "YOLO_MODEL_PATH" in dockerfile
    # No secrets should be baked via ENV
    assert "GEMINI_API_KEY" not in dockerfile
    assert "FIREBASE" not in dockerfile.upper() or "FIREBASE_CREDENTIALS" not in dockerfile


def test_dockerignore_excludes_secrets_but_keeps_assets():
    di = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in di
    assert "*service-account*.json" in di
    assert "*firebase-adminsdk*.json" in di
    assert "app/static/reports/" in di
    # required runtime assets are NOT excluded
    assert "app/static/fonts" not in di
    assert "app/static/images" not in di
