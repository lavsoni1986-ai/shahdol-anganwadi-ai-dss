# app/services/secret_manager.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Google Cloud Secret Manager provider (REST API, no SDK dependency)
#
# Core Ideathon requirement: "Secure API key retrieval via Google Cloud
# Secret Manager."
#
# Uses google-auth (already installed via firebase-admin) to obtain an
# access token, then calls the Secret Manager REST API directly.
# Avoids the protobuf version conflict between the Secret Manager SDK
# and the Gemini SDK.
#
# In production, retrieves secrets from Secret Manager. For local
# development, falls back to environment variables / .env (the existing
# configuration). The secret value is never logged, never returned by
# an API endpoint, and never stored in source code.
# =====================================================================

import json
import os
import urllib.request

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

SECRET_MANAGER_API = "https://secretmanager.googleapis.com/v1"


def _get_project_id() -> str:
    """Derives the GCP project ID from the available service account or settings."""
    try:
        import google.auth

        _, project = google.auth.default()
        if project:
            return project
    except Exception:
        pass
    return os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or ""


def _get_access_token() -> str | None:
    """Obtains an OAuth2 access token from the service account (Application Default Credentials)."""
    try:
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import Request as GoogleAuthRequest

        credentials, _ = google_auth_default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(GoogleAuthRequest())
        return credentials.token
    except Exception as e:
        logger.warning("secret_manager_auth_failed", error_type=type(e).__name__)
        return None


def get_secret(secret_name: str) -> str | None:
    """
    Retrieves a secret from Google Cloud Secret Manager via the REST API.

    Args:
        secret_name: The name of the secret (e.g. "GEMINI_API_KEY").

    Returns:
        The secret value as a string, or None if unavailable.

    Never logs the secret value. Never raises (logs a warning on failure).
    """
    project_id = settings.gcp_project_id or _get_project_id()
    if not project_id:
        logger.debug("secret_manager_no_project_id", secret_name=secret_name)
        return None

    token = _get_access_token()
    if not token:
        return None

    url = f"{SECRET_MANAGER_API}/projects/{project_id}/secrets/{secret_name}/versions/latest:access"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            value = data.get("payload", {}).get("data", "")
            if value:
                import base64
                value = base64.b64decode(value).decode("utf-8")
            logger.info("secret_manager_ok", secret_name=secret_name)
            return value
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.debug("secret_manager_secret_not_found", secret_name=secret_name)
        else:
            logger.warning("secret_manager_api_error", secret_name=secret_name, code=e.code)
        return None
    except Exception as e:
        logger.warning("secret_manager_unavailable", secret_name=secret_name, error_type=type(e).__name__)
        return None


def resolve_gemini_api_key() -> str:
    """
    Resolves the Gemini API key with the following priority:
    1. Google Cloud Secret Manager (production)
    2. GEMINI_API_KEY environment variable
    3. settings.gemini_api_key (.env / config)
    Never logs the key value.
    """
    key = get_secret("GEMINI_API_KEY")
    if key:
        return key
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    return settings.gemini_api_key or ""