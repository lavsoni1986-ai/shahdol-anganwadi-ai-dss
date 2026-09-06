# tests/test_assistant.py
# Phase 5 tests — AI Officer Copilot / Personal Journal
# Multi-turn Gemini assistant: auth, UID isolation, multi-turn context,
# summarization, action plan, and failure handling (all mocked).
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.assistant import router as assistant_router


# ── Minimal app with the assistant router only ─────────────────────
@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(assistant_router)

    # Prevent any real Firebase/Firestore side effects during tests
    monkeypatch.setattr("app.services.firestore_service._get_client", lambda: None)
    monkeypatch.setattr("app.services.firebase_auth._ensure_initialized", lambda: None)

    return TestClient(app)


def _set_identity(monkeypatch, uid, role="officer", email="officer@example.com"):
    """Makes get_current_officer return this verified identity."""
    def _fake_verify(token):
        return {"uid": uid, "email": email, "role": role, "name": "Officer"}
    monkeypatch.setattr("app.services.firebase_auth._verify_id_token", _fake_verify)


def _set_no_identity(monkeypatch):
    def _raise(token):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase ID token")
    monkeypatch.setattr("app.services.firebase_auth._verify_id_token", _raise)


# ── In-memory fakes for Firestore conversation functions ──────────
class FakeStore:
    def __init__(self):
        self.convs = {}   # uid -> {conversation_id -> dict}
        self.msgs = {}    # uid -> {conversation_id -> [message dicts]}

    def create_conversation(self, uid, title=""):
        import uuid
        cid = "cid-" + uuid.uuid4().hex[:8]
        self.convs.setdefault(uid, {})[cid] = {
            "conversation_id": cid, "uid": uid, "title": title or "नई चर्चा",
            "status": "active", "message_count": 0, "summary": "", "created_at": "2026-08-30T00:00:00+00:00",
        }
        self.msgs.setdefault(uid, {})[cid] = []
        return cid

    def add_message(self, uid, cid, role, content):
        self.msgs.setdefault(uid, {}).setdefault(cid, []).append(
            {"role": role, "content": content, "created_at": "2026-08-30T00:00:00+00:00"})
        c = self.convs.setdefault(uid, {}).get(cid)
        if c:
            c["message_count"] = c.get("message_count", 0) + 1
        return True

    def get_conversation(self, uid, cid):
        return self.convs.get(uid, {}).get(cid)

    def get_conversation_messages(self, uid, cid):
        return self.msgs.get(uid, {}).get(cid, [])

    def list_conversations(self, uid, max_results=20):
        return list(self.convs.get(uid, {}).values())

    def update_conversation(self, uid, cid, data):
        c = self.convs.get(uid, {}).get(cid)
        if c:
            c.update(data)
            return True
        return False


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr("app.routers.assistant.create_conversation", s.create_conversation)
    monkeypatch.setattr("app.routers.assistant.add_message", s.add_message)
    monkeypatch.setattr("app.routers.assistant.get_conversation", s.get_conversation)
    monkeypatch.setattr("app.routers.assistant.get_conversation_messages", s.get_conversation_messages)
    monkeypatch.setattr("app.routers.assistant.list_conversations", s.list_conversations)
    monkeypatch.setattr("app.routers.assistant.update_conversation", s.update_conversation)
    return s


def _fake_gemini(monkeypatch, responses=None, summarize="Test summary", action_plan=None):
    """Mocks gemini_assistant singleton methods."""
    calls = {"history": []}
    from app.services.gemini_assistant import gemini_assistant

    def _gen(history, user_message, system_prompt=None):
        calls["history"].append(list(history))
        if responses:
            resp = responses.pop(0) if responses else {"success": False, "error": "fail"}
            return resp
        return {"success": True, "content": "AI reply to: " + user_message, "latency_ms": 5}

    monkeypatch.setattr(gemini_assistant, "generate_response", _gen)
    monkeypatch.setattr(gemini_assistant, "summarize", lambda history: summarize)
    monkeypatch.setattr(gemini_assistant, "generate_action_plan", lambda history: action_plan or {})
    return calls


def _fake_intelligence(monkeypatch, bundle=None, error=None):
    """Mocks gemini_assistant.generate_intelligence for Phase 5B structured output."""
    from app.services.gemini_assistant import (
        gemini_assistant,
        SummaryBundle,
        ConversationSummary,
        FieldInsight,
        ActionPlanItem,
    )

    if error is not None:
        def _intel(history):
            return {"success": False, "error": error}
    elif bundle is not None:
        def _intel(history):
            return {"success": True, "bundle": bundle}
    else:
        default_bundle = SummaryBundle(
            summary=ConversationSummary(
                summary="Concise summary of the field observations.",
                key_observations=["Sohagpur block flagged"],
                important_issues=["Meal not visible"],
                conclusions=["Needs supervisor visit"],
                priority_items=["High"],
                relevant_context="Sohagpur",
            ),
            field_insights=[
                FieldInsight(
                    issue="Meal distribution not visible",
                    evidence_or_context="Officer noted meal absent in photo",
                    priority="HIGH",
                    affected_location="Sohagpur",
                    why_it_matters="Affects nutrition monitoring",
                )
            ],
            action_plan=[
                ActionPlanItem(
                    recommended_action="Send supervisor to AWC",
                    priority="HIGH",
                    responsible_level="Supervisor",
                    next_step="Visit within 48h",
                    rationale="Meal visibility gap",
                )
            ],
        )

        def _intel(history):
            return {"success": True, "bundle": default_bundle}

    monkeypatch.setattr(gemini_assistant, "generate_intelligence", _intel)
    return _intel


# ── A. Unauthenticated -> 401 ─────────────────────────────────────
def test_unauthenticated_assistant_401(client, monkeypatch):
    _set_no_identity(monkeypatch)
    r = client.get("/api/v1/assistant/conversations")
    assert r.status_code == 401
    r2 = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    assert r2.status_code == 401


# ── B. Authenticated endpoint works with verified identity ────────
def test_authenticated_create_and_message(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    _fake_gemini(monkeypatch)
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    assert c.status_code == 201
    cid = c.json()["conversation_id"]

    m = client.post(
        f"/api/v1/assistant/conversations/{cid}/messages",
        headers={"Authorization": "Bearer t"},
        json={"content": "Hello"},
    )
    assert m.status_code == 200
    assert m.json()["response"].startswith("AI reply")


# ── C. Browser-supplied UID cannot override verified UID ───────────
def test_browser_uid_cannot_override(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    c = client.post("/api/v1/assistant/conversations",
                    headers={"Authorization": "Bearer t"},
                    json={"uid": "uid-MALLICIOUS"})
    assert c.status_code == 201
    cid = c.json()["conversation_id"]
    assert cid in store.convs["uid-A"]
    assert cid not in store.convs.get("uid-MALLICIOUS", {})


# ── D. User A cannot retrieve user B conversation ─────────────────
def test_user_a_cannot_read_user_b(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-B")
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid_b = c.json()["conversation_id"]
    _set_identity(monkeypatch, "uid-A")
    r = client.get(f"/api/v1/assistant/conversations/{cid_b}", headers={"Authorization": "Bearer t"})
    assert r.status_code == 404


# ── E. Conversation ownership enforced on message/end ──────────────
def test_ownership_enforced_on_message(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-B")
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid_b = c.json()["conversation_id"]
    _set_identity(monkeypatch, "uid-A")
    r = client.post(f"/api/v1/assistant/conversations/{cid_b}/messages",
                    headers={"Authorization": "Bearer t"}, json={"content": "hi"})
    assert r.status_code == 404
    r2 = client.post(f"/api/v1/assistant/conversations/{cid_b}/end",
                     headers={"Authorization": "Bearer t"})
    assert r2.status_code == 404


# ── F. Multi-turn context preserved ────────────────────────────────
def test_multi_turn_context_preserved(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    calls = _fake_gemini(monkeypatch)
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid = c.json()["conversation_id"]
    h = {"Authorization": "Bearer t"}
    client.post(f"/api/v1/assistant/conversations/{cid}/messages", headers=h, json={"content": "Turn 1: how many centres?"})
    client.post(f"/api/v1/assistant/conversations/{cid}/messages", headers=h, json={"content": "Turn 2: which is the most critical?"})
    assert len(calls["history"]) == 2
    history_text = " ".join(m.get("content", "") for m in calls["history"][1])
    assert "Turn 1" in history_text


# ── G. Summary generated and stored (Phase 5B structured) ──────────
def test_summary_generated_and_stored(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    _fake_intelligence(monkeypatch)
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid = c.json()["conversation_id"]
    h = {"Authorization": "Bearer t"}
    client.post(f"/api/v1/assistant/conversations/{cid}/messages", headers=h, json={"content": "There is an issue at Rampur AWC."})
    r = client.post(f"/api/v1/assistant/conversations/{cid}/end", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["summary_status"] == "success"
    assert data["summary"]["summary"] == "Concise summary of the field observations."
    assert store.convs["uid-A"][cid]["status"] == "completed"
    assert store.convs["uid-A"][cid]["summary"]["summary"] == "Concise summary of the field observations."
    assert len(store.convs["uid-A"][cid]["field_insights"]) == 1
    assert store.convs["uid-A"][cid]["field_insights"][0]["issue"] == "Meal distribution not visible"
    assert len(store.convs["uid-A"][cid]["action_plan"]) == 1
    assert store.convs["uid-A"][cid]["action_plan"][0]["recommended_action"] == "Send supervisor to AWC"


# ── H. Field insights persisted ────────────────────────────────────
def test_field_insights_persisted(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    from app.services.gemini_assistant import SummaryBundle, ConversationSummary, FieldInsight, ActionPlanItem
    bundle = SummaryBundle(
        summary=ConversationSummary(summary="test"),
        field_insights=[
            FieldInsight(issue="Issue 1", priority="HIGH"),
            FieldInsight(issue="Issue 2", priority="LOW"),
        ],
    )
    _fake_intelligence(monkeypatch, bundle=bundle)
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid = c.json()["conversation_id"]
    h = {"Authorization": "Bearer t"}
    client.post(f"/api/v1/assistant/conversations/{cid}/messages", headers=h, json={"content": "msg"})
    r = client.post(f"/api/v1/assistant/conversations/{cid}/end", headers=h)
    assert r.status_code == 200
    persisted = store.convs["uid-A"][cid]
    assert len(persisted["field_insights"]) == 2
    assert persisted["field_insights"][0]["issue"] == "Issue 1"
    assert persisted["field_insights"][1]["issue"] == "Issue 2"


# ── I. Action plan persisted ───────────────────────────────────────
def test_action_plan_persisted(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    from app.services.gemini_assistant import SummaryBundle, ConversationSummary, FieldInsight, ActionPlanItem
    bundle = SummaryBundle(
        summary=ConversationSummary(summary="test"),
        action_plan=[
            ActionPlanItem(recommended_action="Action A", priority="HIGH"),
            ActionPlanItem(recommended_action="Action B", priority="MEDIUM"),
        ],
    )
    _fake_intelligence(monkeypatch, bundle=bundle)
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid = c.json()["conversation_id"]
    h = {"Authorization": "Bearer t"}
    client.post(f"/api/v1/assistant/conversations/{cid}/messages", headers=h, json={"content": "msg"})
    r = client.post(f"/api/v1/assistant/conversations/{cid}/end", headers=h)
    assert r.status_code == 200
    persisted = store.convs["uid-A"][cid]
    assert len(persisted["action_plan"]) == 2
    assert persisted["action_plan"][0]["recommended_action"] == "Action A"
    assert persisted["action_plan"][1]["recommended_action"] == "Action B"


# ── J. Gemini structured response validated (generate_intelligence) ─
def test_intelligence_validation_accepts_valid(monkeypatch):
    import json
    from app.services import gemini_assistant as ga
    valid_json = json.dumps({
        "summary": {"summary": "s", "key_observations": ["o1"]},
        "field_insights": [{"issue": "i1", "priority": "HIGH"}],
        "action_plan": [{"recommended_action": "a1", "priority": "LOW"}],
    })
    def _gen(history, user_message, system_prompt=None):
        return {"success": True, "content": valid_json, "latency_ms": 1}
    monkeypatch.setattr(ga.gemini_assistant, "generate_response", _gen)
    result = ga.gemini_assistant.generate_intelligence([{"role": "user", "content": "hello"}])
    assert result.get("success") is True
    assert result["bundle"].summary.summary == "s"
    assert len(result["bundle"].field_insights) == 1
    assert result["bundle"].field_insights[0].issue == "i1"
    assert len(result["bundle"].action_plan) == 1


def test_intelligence_validation_rejects_malformed(monkeypatch):
    from app.services import gemini_assistant as ga
    def _gen(history, user_message, system_prompt=None):
        return {"success": True, "content": "not valid json at all", "latency_ms": 1}
    monkeypatch.setattr(ga.gemini_assistant, "generate_response", _gen)
    result = ga.gemini_assistant.generate_intelligence([{"role": "user", "content": "hello"}])
    assert result.get("success") is False


# ── K. Gemini failure does not expose secrets ─────────────────────
def test_gemini_intelligence_failure_no_secrets(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    _fake_intelligence(monkeypatch, error="AI service error")
    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid = c.json()["conversation_id"]
    h = {"Authorization": "Bearer t"}
    client.post(f"/api/v1/assistant/conversations/{cid}/messages", headers=h, json={"content": "msg"})
    r = client.post(f"/api/v1/assistant/conversations/{cid}/end", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["summary_status"] == "error"
    # Ensure no API key or credential appears in the error message
    assert "AIza" not in str(data.get("message", ""))
    assert "gemini" not in str(data.get("message", "")).lower()
    assert "secret" not in str(data.get("message", "")).lower()
    assert "key" not in str(data.get("message", "")).lower()


# ── I. Secret Manager failure handled safely ───────────────────────
def test_secret_manager_failure_is_graceful(monkeypatch):
    from app.services import secret_manager
    monkeypatch.setattr(secret_manager, "_get_access_token", lambda: None)
    assert secret_manager.get_secret("GEMINI_API_KEY") is None
    monkeypatch.setenv("GEMINI_API_KEY", "")
    key = secret_manager.resolve_gemini_api_key()
    assert isinstance(key, str)


# ── J. No secret appears in errors/responses ───────────────────────
def test_no_secret_in_error_path(client, store, monkeypatch):
    _set_identity(monkeypatch, "uid-A")
    fake_key = "SECRET-KEY-XYZ-1234"
    from app.services.gemini_assistant import gemini_assistant

    def _gen(history, user_message, system_prompt=None):
        return {"success": False, "content": "", "error": "AI request failed"}
    monkeypatch.setattr(gemini_assistant, "generate_response", _gen)

    c = client.post("/api/v1/assistant/conversations", headers={"Authorization": "Bearer t"})
    cid = c.json()["conversation_id"]
    r = client.post(f"/api/v1/assistant/conversations/{cid}/messages",
                    headers={"Authorization": "Bearer t"}, json={"content": "hello"})
    body = r.json().get("response", "")
    assert fake_key not in body


# ── K. Secret Manager get_secret failure on HTTP error ─────────────
def test_secret_manager_http_error_returns_none(monkeypatch):
    from app.services import secret_manager
    monkeypatch.setattr(secret_manager, "_get_project_id", lambda: "test-project")
    monkeypatch.setattr(secret_manager, "_get_access_token", lambda: "token")
    import urllib.request, urllib.error

    def _open(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    assert secret_manager.get_secret("GEMINI_API_KEY") is None
