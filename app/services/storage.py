# app/services/storage.py
# =====================================================================
# BharatOS — Shahdol Anganwadi AI DSS
# Object Storage Abstraction Layer (P2-B)
# Backends:
#   1. LocalFileSystemStorage (Local Development & Fallback)
#   2. GoogleCloudStorage (Cloud Run Production with ADC)
# =====================================================================

import asyncio
import os
import re
from abc import ABC, abstractmethod
from datetime import timedelta
from pathlib import Path
from typing import Optional

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Repository root directory
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _REPO_ROOT / "data"

# Safe identifier regex: alphanumeric, hyphens, underscores, dots
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class StorageConfigurationError(StorageError):
    """Raised when storage configuration is invalid or missing."""
    pass


# ─────────────────────────────────────────────
# Path & Key Utilities (Security & Traversal Prevention)
# ─────────────────────────────────────────────

def sanitize_identifier(value: str) -> str:
    """
    Sanitizes an identifier (e.g. AWC ID, submission ID, audit ID) for safe use
    in storage object keys and directory names.

    Raises:
        ValueError: If value is empty or contains path traversal sequences.
    """
    if not value or not isinstance(value, str):
        raise ValueError("Identifier must be a non-empty string.")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Identifier cannot be empty or whitespace.")

    # Reject traversal characters and separators
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        raise ValueError(f"Path traversal sequence detected in identifier: {cleaned!r}")

    # Remove any character not matching safe alphanumeric, hyphen, underscore, dot
    sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", cleaned)
    if not sanitized or sanitized in (".", ".."):
        raise ValueError(f"Identifier could not be safely sanitized: {cleaned!r}")

    return sanitized


def validate_object_key(key: str) -> str:
    """
    Validates that an object key is safe and relative.

    Rejects:
      - Traversal (..)
      - Leading slash (/ or \\)
      - Backslashes (\\)
      - Absolute paths (C:\\, /etc, etc.)
    """
    if not key or not isinstance(key, str):
        raise ValueError("Object key must be a non-empty string.")

    normalized = key.strip()
    if not normalized:
        raise ValueError("Object key cannot be empty.")

    if "\\" in normalized:
        raise ValueError(f"Object key contains forbidden backslash: {normalized!r}")

    if normalized.startswith("/"):
        raise ValueError(f"Object key must be relative, not absolute: {normalized!r}")

    # Check for drive letters like C:
    if len(normalized) > 1 and normalized[1] == ":":
        raise ValueError(f"Object key cannot contain drive specification: {normalized!r}")

    parts = normalized.split("/")
    for part in parts:
        if part in ("..", ""):
            if part == "..":
                raise ValueError(f"Object key contains path traversal '..': {normalized!r}")
            # Empty part means consecutive slashes e.g. a//b
            raise ValueError(f"Object key contains consecutive slashes: {normalized!r}")

    return normalized


def build_evidence_key(awc_id: Optional[str], submission_id: str, ext: str = ".jpg") -> str:
    """
    Builds a deterministic, isolated object key for permanent evidence photos:
        evidence/{sanitized_awc_id}/{sanitized_submission_id}{ext}
    """
    safe_awc = sanitize_identifier(awc_id or "UNKNOWN")
    safe_sub = sanitize_identifier(submission_id)

    if not ext.startswith("."):
        ext = f".{ext}"
    clean_ext = ext.lower()
    if clean_ext not in (".jpg", ".jpeg", ".png", ".webp"):
        clean_ext = ".jpg"

    key = f"evidence/{safe_awc}/{safe_sub}{clean_ext}"
    return validate_object_key(key)


def build_report_key(audit_or_sub_id: str, ext: str = ".pdf") -> str:
    """
    Builds a deterministic object key for generated verification reports:
        reports/{sanitized_id}{ext}
    """
    safe_id = sanitize_identifier(audit_or_sub_id)
    if not ext.startswith("."):
        ext = f".{ext}"
    clean_ext = ext.lower()
    if clean_ext != ".pdf":
        clean_ext = ".pdf"

    key = f"reports/{safe_id}{clean_ext}"
    return validate_object_key(key)


# ─────────────────────────────────────────────
# Base Storage Interface
# ─────────────────────────────────────────────

class BaseStorageService(ABC):
    """Abstract interface for all storage backends."""

    @abstractmethod
    async def upload_file(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Uploads binary data and returns the canonical object key.
        """
        pass

    @abstractmethod
    async def download_file(self, object_name_or_path: str) -> bytes:
        """
        Downloads and returns binary data.
        Supports both canonical object keys and legacy local paths.
        """
        pass

    @abstractmethod
    async def exists(self, object_name_or_path: str) -> bool:
        """
        Checks whether the object or legacy local path exists.
        """
        pass

    @abstractmethod
    async def delete_file(self, object_name_or_path: str) -> bool:
        """
        Deletes the object if it exists. Returns True if deleted, False if not found.
        """
        pass

    @abstractmethod
    async def generate_access_url(
        self,
        object_name_or_path: str,
        expiration_seconds: int = 900,
    ) -> str:
        """
        Generates a temporary read access URL for authorized access.
        """
        pass


# ─────────────────────────────────────────────
# 1. Local Filesystem Backend
# ─────────────────────────────────────────────

class LocalStorageService(BaseStorageService):
    """
    Stores files on the local filesystem under the application data directory.
    Default backend for local development and testing.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or _DATA_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, object_name_or_path: str) -> Path:
        """
        Resolves an object name or legacy path.
        Preserves compatibility with:
          - Existing absolute paths (e.g. E:\\...\\data\\uploads\\x.jpg)
          - Existing relative paths (e.g. data/uploads/x.jpg, app/static/reports/x.pdf)
          - Canonical object keys (e.g. evidence/AWC-1042/x.jpg -> data/evidence/AWC-1042/x.jpg)
        """
        raw_path = Path(object_name_or_path)

        # 1. Check if it's already an existing path (absolute or relative to repo)
        if raw_path.exists():
            return raw_path.resolve()

        repo_relative = (_REPO_ROOT / raw_path).resolve()
        if repo_relative.exists():
            return repo_relative

        # 2. Treat as canonical object key under self.base_dir
        valid_key = validate_object_key(object_name_or_path)
        target = (self.base_dir / valid_key).resolve()

        # Prevent traversal outside base_dir
        try:
            target.relative_to(self.base_dir)
        except ValueError:
            raise ValueError(f"Path traversal blocked outside storage base: {object_name_or_path}")

        return target

    async def upload_file(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        valid_key = validate_object_key(object_name)
        target_path = (self.base_dir / valid_key).resolve()

        try:
            target_path.relative_to(self.base_dir)
        except ValueError:
            raise ValueError(f"Path traversal attempt blocked: {object_name}")

        def _write():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(data)

        await asyncio.to_thread(_write)
        logger.debug("local_storage_upload_success", key=valid_key, size_bytes=len(data))
        return valid_key

    async def download_file(self, object_name_or_path: str) -> bytes:
        path = self._resolve_path(object_name_or_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found in local storage: {object_name_or_path}")

        def _read():
            return path.read_bytes()

        return await asyncio.to_thread(_read)

    async def exists(self, object_name_or_path: str) -> bool:
        try:
            path = self._resolve_path(object_name_or_path)
            return path.exists() and path.is_file()
        except Exception:
            return False

    async def delete_file(self, object_name_or_path: str) -> bool:
        try:
            path = self._resolve_path(object_name_or_path)
            if path.exists() and path.is_file():
                await asyncio.to_thread(path.unlink, missing_ok=True)
                return True
            return False
        except Exception as e:
            logger.warning("local_storage_delete_failed", path=object_name_or_path, error=str(e))
            return False

    async def generate_access_url(
        self,
        object_name_or_path: str,
        expiration_seconds: int = 900,
    ) -> str:
        """
        In local mode, returns a relative API URL or static URL if applicable.
        """
        valid_key = validate_object_key(object_name_or_path) if not Path(object_name_or_path).exists() else object_name_or_path
        base_url = settings.app_public_url.rstrip("/") if settings.app_public_url else "http://localhost:8000"
        return f"{base_url}/storage/{valid_key}"


# ─────────────────────────────────────────────
# 2. Google Cloud Storage Backend (Production)
# ─────────────────────────────────────────────

class GoogleCloudStorageService(BaseStorageService):
    """
    Google Cloud Storage backend for Cloud Run production.
    Uses Google Application Default Credentials (ADC) without requiring
    service-account JSON files inside the container.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        project_id: Optional[str] = None,
        client: Optional[object] = None,
    ):
        self.bucket_name = (bucket_name or settings.gcs_bucket_name or "").strip()
        self.project_id = (project_id or settings.gcs_project_id or settings.gcp_project_id or "").strip()
        self._injected_client = client
        self._client = client

    def _get_client(self):
        """Lazy-initializes the GCS Client with Application Default Credentials."""
        if self._client is None:
            if not self.bucket_name:
                raise StorageConfigurationError(
                    "GCS_BUCKET_NAME is not configured. Please set GCS_BUCKET_NAME in environment."
                )
            try:
                from google.cloud import storage
                # Initialize storage client using ADC
                if self.project_id:
                    self._client = storage.Client(project=self.project_id)
                else:
                    self._client = storage.Client()
            except Exception as e:
                logger.error("gcs_client_init_failed", error=type(e).__name__)
                raise StorageError(f"Failed to initialize Google Cloud Storage client: {type(e).__name__}") from e

        return self._client

    def _get_bucket(self):
        client = self._get_client()
        return client.bucket(self.bucket_name)

    async def upload_file(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        valid_key = validate_object_key(object_name)

        def _sync_upload():
            bucket = self._get_bucket()
            blob = bucket.blob(valid_key)
            blob.upload_from_string(data, content_type=content_type)
            return valid_key

        try:
            res = await asyncio.to_thread(_sync_upload)
            logger.info("gcs_upload_success", bucket=self.bucket_name, key=valid_key, size_bytes=len(data))
            return res
        except Exception as e:
            logger.error("gcs_upload_failed", bucket=self.bucket_name, key=valid_key, error=type(e).__name__)
            raise StorageError(f"GCS upload failed for object '{valid_key}': {type(e).__name__}") from e

    async def download_file(self, object_name_or_path: str) -> bytes:
        # Legacy local fallback support: if the file exists on local disk, return it directly
        local_path = Path(object_name_or_path)
        if local_path.exists() and local_path.is_file():
            return await asyncio.to_thread(local_path.read_bytes)

        repo_rel = _REPO_ROOT / local_path
        if repo_rel.exists() and repo_rel.is_file():
            return await asyncio.to_thread(repo_rel.read_bytes)

        valid_key = validate_object_key(object_name_or_path)

        def _sync_download():
            bucket = self._get_bucket()
            blob = bucket.blob(valid_key)
            if not blob.exists():
                raise FileNotFoundError(f"GCS object not found: gs://{self.bucket_name}/{valid_key}")
            return blob.download_as_bytes()

        try:
            return await asyncio.to_thread(_sync_download)
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error("gcs_download_failed", bucket=self.bucket_name, key=valid_key, error=type(e).__name__)
            raise StorageError(f"GCS download failed for object '{valid_key}': {type(e).__name__}") from e

    async def exists(self, object_name_or_path: str) -> bool:
        # Check local legacy path first
        local_path = Path(object_name_or_path)
        if local_path.exists() and local_path.is_file():
            return True

        repo_rel = _REPO_ROOT / local_path
        if repo_rel.exists() and repo_rel.is_file():
            return True

        try:
            valid_key = validate_object_key(object_name_or_path)
        except ValueError:
            return False

        def _sync_exists():
            bucket = self._get_bucket()
            blob = bucket.blob(valid_key)
            return blob.exists()

        try:
            return await asyncio.to_thread(_sync_exists)
        except Exception as e:
            logger.warning("gcs_exists_check_failed", bucket=self.bucket_name, key=valid_key, error=type(e).__name__)
            return False

    async def delete_file(self, object_name_or_path: str) -> bool:
        # Legacy local path deletion if requested
        local_path = Path(object_name_or_path)
        if local_path.exists() and local_path.is_file():
            await asyncio.to_thread(local_path.unlink, missing_ok=True)
            return True

        try:
            valid_key = validate_object_key(object_name_or_path)
        except ValueError:
            return False

        def _sync_delete():
            bucket = self._get_bucket()
            blob = bucket.blob(valid_key)
            if blob.exists():
                blob.delete()
                return True
            return False

        try:
            return await asyncio.to_thread(_sync_delete)
        except Exception as e:
            logger.warning("gcs_delete_failed", bucket=self.bucket_name, key=valid_key, error=type(e).__name__)
            return False

    async def generate_access_url(
        self,
        object_name_or_path: str,
        expiration_seconds: int = 900,
    ) -> str:
        """
        Generates a temporary v4 signed URL for authenticated download.
        Default expiration: 15 minutes (900 seconds).
        """
        valid_key = validate_object_key(object_name_or_path)

        def _sync_sign():
            bucket = self._get_bucket()
            blob = bucket.blob(valid_key)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expiration_seconds),
                method="GET",
            )

        try:
            url = await asyncio.to_thread(_sync_sign)
            logger.info("gcs_signed_url_generated", bucket=self.bucket_name, key=valid_key, ttl_sec=expiration_seconds)
            return url
        except Exception as e:
            logger.error("gcs_signed_url_failed", bucket=self.bucket_name, key=valid_key, error=type(e).__name__)
            raise StorageError(f"Failed to generate signed URL for '{valid_key}': {type(e).__name__}") from e


# ─────────────────────────────────────────────
# Factory / Singleton Router
# ─────────────────────────────────────────────

def get_storage_service() -> BaseStorageService:
    """
    Returns the appropriate storage backend based on configuration.
    If GCS_ENABLED is true, returns GoogleCloudStorageService.
    Otherwise returns LocalStorageService.
    """
    if settings.gcs_enabled:
        return GoogleCloudStorageService()
    return LocalStorageService()


# Global convenient instance
storage_service: BaseStorageService = get_storage_service()
