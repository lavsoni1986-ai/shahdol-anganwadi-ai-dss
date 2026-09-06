# app/services/firestore_service.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Firestore additive layer (Ideathon: "User-isolated Firestore document storage").
#
# Firestore is NOT the system of record — SQLite/PostgreSQL remains the source
# of truth for operational Anganwadi data. This layer stores only:
#   - users/{firebase_uid}            -> minimal officer profile (UID-isolated)
#   - verification_audits/{audit_id}  -> officer review audit (officer_uid from token)
#
# All writes are BEST-EFFORT: a Firestore failure is logged and the operation
# never fails the underlying SQL workflow. Credentials and ID tokens are never
# logged. Firebase must be initialized through app.services.firebase_auth.
# =====================================================================

import datetime

from app.services.firebase_auth import _ensure_initialized
from app.utils.logger import get_logger

logger = get_logger(__name__)

# In-process dedup for user-profile writes (idempotent, avoids a Firestore
# round-trip on every authenticated request).
_seen_uids: set = set()


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_client():
    """Returns the Firestore client via the existing Firebase Admin app, or None."""
    app = _ensure_initialized()
    if app is None:
        return None
    try:
        from firebase_admin import firestore

        return firestore.client()
    except Exception as e:
        logger.warning("firestore_client_unavailable", error_type=type(e).__name__)
        return None


def _firestore_available() -> bool:
    return _get_client() is not None


def upsert_user_profile(officer: dict, force: bool = False) -> bool:
    """
    Idempotently writes users/{firebase_uid} with minimal, token-derived fields.
    officer MUST come from a verified Firebase token (get_current_officer), never
    from the browser. Returns True if written, False on config-missing/failure.
    """
    uid = (officer or {}).get("uid")
    if not uid:
        return False

    if not force and uid in _seen_uids:
        return True  # already upserted in this process

    client = _get_client()
    if client is None:
        logger.warning("firestore_user_profile_skipped", reason="firestore_not_configured")
        return False

    try:
        now = _utcnow_iso()
        payload = {
            "uid": uid,
            "email": officer.get("email"),
            "display_name": officer.get("name"),
            "role": officer.get("role", "officer"),
            "created_at": now,
            "last_seen_at": now,
        }
        # merge=True keeps created_at stable across upserts within a process.
        client.collection("users").document(uid).set(payload, merge=True)
        _seen_uids.add(uid)
        logger.info("firestore_user_profile_upserted", uid=uid, role=payload["role"])
        return True
    except Exception as e:
        logger.warning("firestore_user_profile_write_failed", error_type=type(e).__name__)
        return False


def create_verification_audit(audit_payload: dict) -> bool:
    """
    Writes verification_audits/{audit_id} with officer_uid derived from the
    verified Firebase token. Best-effort — never fails the SQL transaction.
    """
    audit_id = (audit_payload or {}).get("audit_id") or (audit_payload or {}).get("submission_id")
    if not audit_id:
        return False

    client = _get_client()
    if client is None:
        logger.warning("firestore_audit_skipped", reason="firestore_not_configured")
        return False

    try:
        client.collection("verification_audits").document(audit_id).set(audit_payload, merge=True)
        logger.info("firestore_audit_written", audit_id=audit_id)
        return True
    except Exception as e:
        logger.warning("firestore_audit_write_failed", audit_id=audit_id, error_type=type(e).__name__)
        return False


# ─────────────────────────────────────────────
# AI Conversation CRUD (UID-scoped, user-isolated)
# ─────────────────────────────────────────────

def _conversation_ref(uid: str, conversation_id: str):
    """Returns the Firestore document reference for a single conversation."""
    client = _get_client()
    if client is None:
        return None
    return client.collection("users").document(uid).collection("ai_conversations").document(conversation_id)


def _messages_ref(uid: str, conversation_id: str):
    """Returns the Firestore collection reference for conversation messages."""
    ref = _conversation_ref(uid, conversation_id)
    if ref is None:
        return None
    return ref.collection("messages")


def create_conversation(uid: str, title: str = "") -> str:
    """Creates a new conversation document under users/{uid}/ai_conversations/. Returns conversation_id."""
    client = _get_client()
    if client is None:
        return ""
    import uuid

    conversation_id = uuid.uuid4().hex[:16]
    now = _utcnow_iso()
    doc = client.collection("users").document(uid).collection("ai_conversations").document(conversation_id)
    doc.set({
        "conversation_id": conversation_id,
        "uid": uid,
        "title": title or "नई चर्चा",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
        "summary": "",
    })
    logger.info("conversation_created", uid=uid, conversation_id=conversation_id)
    return conversation_id


def add_message(uid: str, conversation_id: str, role: str, content: str) -> bool:
    """Appends a message to the conversation's messages subcollection."""
    msg_ref = _messages_ref(uid, conversation_id)
    if msg_ref is None:
        return False
    from firebase_admin import firestore as _firestore

    now = _utcnow_iso()
    message_id = msg_ref.document().id
    msg_ref.document(message_id).set({"message_id": message_id, "role": role, "content": content, "created_at": now})
    conv_ref = _conversation_ref(uid, conversation_id)
    if conv_ref:
        conv_ref.update({"message_count": _firestore.Increment(1), "updated_at": now})
    return True


def get_conversation(uid: str, conversation_id: str) -> dict:
    """Returns the conversation document, or None."""
    ref = _conversation_ref(uid, conversation_id)
    if ref is None:
        return None
    doc = ref.get()
    if not doc.exists:
        return None
    return doc.to_dict()


def list_conversations(uid: str, max_results: int = 20) -> list:
    """Lists the user's conversations, newest first."""
    client = _get_client()
    if client is None:
        return []
    from firebase_admin import firestore as _firestore

    docs = (
        client.collection("users").document(uid).collection("ai_conversations")
        .order_by("created_at", direction=_firestore.Query.DESCENDING)
        .limit(max_results)
        .stream()
    )
    return [d.to_dict() for d in docs]


def get_conversation_messages(uid: str, conversation_id: str) -> list:
    """Returns all messages for a conversation, oldest first."""
    msgs = _messages_ref(uid, conversation_id)
    if msgs is None:
        return []
    docs = msgs.order_by("created_at").stream()
    return [d.to_dict() for d in docs]


def update_conversation(uid: str, conversation_id: str, data: dict) -> bool:
    """Updates the conversation document with the given fields."""
    ref = _conversation_ref(uid, conversation_id)
    if ref is None:
        return False
    try:
        ref.update(data)
        return True
    except Exception as e:
        logger.warning("conversation_update_failed", conversation_id=conversation_id, error_type=type(e).__name__)
        return False
