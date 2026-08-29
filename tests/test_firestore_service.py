# tests/test_firestore_service.py
# Unit tests for the additive Firestore layer (user profiles + verification audits).
# Firestore is mocked — no real cloud credentials are required.
import pytest

from app.services import firestore_service


# ── Minimal recording fakes ────────────────────────────────────────

class FakeDoc:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.set_calls = []

    def set(self, payload, merge=True):
        self.set_calls.append({"payload": dict(payload), "merge": merge})
        return self


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.docs = {}

    def document(self, doc_id):
        return self.docs.setdefault(doc_id, FakeDoc(doc_id))


class FakeClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection(name))


class RaisingClient:
    def collection(self, name):
        return self

    def document(self, doc_id):
        return self

    def set(self, *args, **kwargs):
        raise RuntimeError("firestore unavailable")


@pytest.fixture(autouse=True)
def _clear_dedup():
    firestore_service._seen_uids.clear()
    yield
    firestore_service._seen_uids.clear()


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(firestore_service, "_get_client", lambda: client)
    return client


# ── 1. Missing configuration → controlled behavior (no crash) ──────
def test_missing_firebase_config_returns_false(monkeypatch):
    monkeypatch.setattr(firestore_service, "_ensure_initialized", lambda: None)
    assert firestore_service.upsert_user_profile({"uid": "u1", "email": "a@b.c"}) is False
    assert firestore_service.create_verification_audit({"audit_id": "A1"}) is False


# ── 2. User document creation ──────────────────────────────────────
def test_upsert_user_profile_writes_users_doc(fake_client):
    officer = {"uid": "uid-officer-1", "email": "officer@example.com", "name": "A Officer", "role": "officer"}
    assert firestore_service.upsert_user_profile(officer) is True

    doc = fake_client.collections["users"].docs["uid-officer-1"]
    assert len(doc.set_calls) == 1
    payload = doc.set_calls[0]["payload"]
    assert payload["uid"] == "uid-officer-1"
    assert payload["email"] == "officer@example.com"
    assert payload["display_name"] == "A Officer"
    assert payload["role"] == "officer"
    assert payload.get("created_at")
    assert payload.get("last_seen_at")


# ── 3. Idempotent upsert (in-process dedup) ────────────────────────
def test_upsert_user_profile_is_idempotent(fake_client):
    officer = {"uid": "uid-dup", "email": "d@x.io", "role": "officer"}
    assert firestore_service.upsert_user_profile(officer) is True
    assert firestore_service.upsert_user_profile(officer) is True  # deduped, no second write
    doc = fake_client.collections["users"].docs["uid-dup"]
    assert len(doc.set_calls) == 1
    # force=True performs an explicit re-write
    assert firestore_service.upsert_user_profile(officer, force=True) is True
    assert len(doc.set_calls) == 2


def test_upsert_user_profile_no_uid_returns_false(fake_client):
    assert firestore_service.upsert_user_profile({}) is False


# ── 4. Audit document creation + UID isolation ─────────────────────
def test_audit_writes_verification_audits_doc_with_uid(fake_client):
    payload = {
        "audit_id": "SHD-20260829-000001",
        "submission_id": "sub-123",
        "officer_uid": "uid-from-verified-token",
        "officer_email": "officer@example.com",
        "action": "APPROVED",
        "status": "APPROVED",
        "ai_score": "YOLO (बच्चे: 12)",
        "awc_id": "AWC-1042",
        "reviewed_at": "2026-08-29T09:00:00+00:00",
    }
    assert firestore_service.create_verification_audit(payload) is True

    doc = fake_client.collections["verification_audits"].docs["SHD-20260829-000001"]
    assert len(doc.set_calls) == 1
    written = doc.set_calls[0]["payload"]
    assert written["officer_uid"] == "uid-from-verified-token"  # derived from token, not browser
    assert written["submission_id"] == "sub-123"


def test_audit_without_audit_id_returns_false(fake_client):
    assert firestore_service.create_verification_audit({"submission_id": ""}) is False
    assert firestore_service.create_verification_audit({}) is False


# ── 5. Firestore exception handling ────────────────────────────────
def test_firestore_write_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(firestore_service, "_get_client", lambda: RaisingClient())
    # Neither should raise — they return False and log a non-sensitive warning.
    assert firestore_service.upsert_user_profile({"uid": "u-ex", "role": "officer"}) is False
    assert firestore_service.create_verification_audit({"audit_id": "A-ex"}) is False
