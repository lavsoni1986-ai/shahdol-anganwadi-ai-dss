# app/services/firebase_auth.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Firebase Authentication for OFFICERS/ADMINS (dashboard access).
#
# This is a SEPARATE authentication domain from the WhatsApp worker
# authentication (app/services/worker_auth.py). Workers are identified by
# WhatsApp phone number; officers/admins are identified by a Firebase ID
# token verified by the Firebase Admin SDK.
#
# Never logs token contents or credentials.
# =====================================================================

import os

from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Firebase Admin app cache (one default app per process).
_firebase_app = None
_init_attempted = False


def _resolve_credentials_path() -> str:
    """
    Resolves the Firebase Admin service-account JSON path for local dev.
    Order: FIREBASE_CREDENTIALS_PATH (config) -> env -> GOOGLE_APPLICATION_CREDENTIALS.
    Returns '' if none is set (Application Default Credentials will be attempted).
    """
    return (
        (settings.firebase_credentials_path or "").strip()
        or os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    )


def _ensure_initialized():
    """
    Lazily initializes the Firebase Admin SDK (safe to import the app without
    credentials). Never retries after a failed init to avoid repeated errors;
    a failed init degrades verification to HTTP 401.
    """
    global _firebase_app, _init_attempted
    if _init_attempted:
        return _firebase_app
    _init_attempted = True
    try:
        from firebase_admin import credentials, initialize_app

        cred_path = _resolve_credentials_path()
        if cred_path:
            cred = credentials.Certificate(cred_path)
        else:
            cred = credentials.ApplicationDefault()
        _firebase_app = initialize_app(credential=cred)
        logger.info("firebase_admin_initialized", source="path" if cred_path else "application_default")
    except Exception as e:
        _firebase_app = None
        logger.warning("firebase_admin_init_failed", error_type=type(e).__name__)
    return _firebase_app


def _extract_bearer_token(request: Request) -> str:
    """Extracts and validates the Authorization: Bearer <token> header."""
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Authorization header (expected 'Bearer <token>')",
        )
    return parts[1].strip()


def _verify_id_token(id_token: str) -> dict:
    """
    Verifies a Firebase ID token and returns its decoded claims.
    Raises HTTPException(401) on any verification failure.
    The token value itself is never logged.
    """
    if _ensure_initialized() is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase authentication is not configured on this server",
        )
    try:
        from firebase_admin import auth as firebase_auth

        decoded = firebase_auth.verify_id_token(id_token)
        if not isinstance(decoded, dict):
            raise ValueError("verify_id_token returned unexpected type")
        return decoded
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("firebase_token_verification_failed", error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase ID token",
        )


def get_current_officer(request: Request) -> dict:
    """
    FastAPI dependency. Verifies the Firebase ID token and returns the
    authenticated officer identity:
        { "uid", "email", "name", "role" }
    Role is read from Firebase custom claims only (never from the request body).
    """
    token = _extract_bearer_token(request)
    claims = _verify_id_token(token)

    uid = claims.get("uid") or claims.get("sub") or "unknown"
    role = claims.get("role") or "officer"
    if role not in ("officer", "admin"):
        role = "officer"

    officer = {
        "uid": uid,
        "email": claims.get("email"),
        "name": claims.get("name"),
        "role": role,
    }

    # Best-effort user-isolated Firestore profile upsert (users/{uid}).
    # Never fails authentication; Firestore unavailability is logged only.
    try:
        from app.services.firestore_service import upsert_user_profile

        upsert_user_profile(officer)
    except Exception as e:
        logger.warning("firestore_user_profile_best_effort_failed", error_type=type(e).__name__)

    return officer


def require_admin(officer: dict = Depends(get_current_officer)) -> dict:
    """
    FastAPI dependency. Requires an authenticated officer with the 'admin' role.
    Raises HTTPException(403) otherwise.
    """
    if officer.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return officer
