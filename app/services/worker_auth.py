# app/services/worker_auth.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Worker Authentication Service
# Looks up sender phone number against the registered workers master list.
# Day 1: In-memory lookup from mock_workers.json
# Future: Database lookup from NIC / WCD PostgreSQL registry
# =====================================================================

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import settings
from app.schemas import WorkerAuthResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Path to mock workers master data file
_MOCK_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "mock_workers.json"


# ─────────────────────────────────────────────
# Worker Master Data Loader
# ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_workers_from_file() -> dict[str, dict]:
    """
    Loads worker master data from mock_workers.json into an in-memory dict.
    Keyed by phone number (string, with country code prefix).

    Uses @lru_cache so the file is read only ONCE per process lifetime.
    In production, replace this with a database query.

    Returns:
        dict mapping phone number → worker record dict
    """
    data_path = _MOCK_DATA_PATH

    if not data_path.exists():
        logger.error(
            "mock_workers_file_not_found",
            path=str(data_path),
        )
        return {}

    try:
        with open(data_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        workers = raw_data.get("registered_workers", [])

        # Build lookup dict keyed by phone number
        # Normalize: strip spaces, ensure string
        worker_map: dict[str, dict] = {}
        for worker in workers:
            phone = str(worker.get("phone", "")).strip()
            if phone:
                worker_map[phone] = worker

        logger.info(
            "worker_master_data_loaded",
            total_workers=len(worker_map),
            source=str(data_path.name),
        )
        return worker_map

    except (json.JSONDecodeError, OSError) as e:
        logger.error(
            "worker_master_data_load_failed",
            error=str(e),
            path=str(data_path),
        )
        return {}


def reload_workers() -> None:
    """
    Clears the cache and reloads worker data from disk.
    Call this if the mock_workers.json file is updated at runtime.
    """
    _load_workers_from_file.cache_clear()
    _load_workers_from_file()
    logger.info("worker_master_data_reloaded")


# ─────────────────────────────────────────────
# Main Authentication Function
# ─────────────────────────────────────────────

def authenticate_worker(phone_number: str) -> WorkerAuthResult:
    """
    Authenticates a WhatsApp sender by checking their phone number
    against the registered workers master list.

    Phone number normalization rules:
    - Incoming phone from Meta API: "919876543210" (country code + number, no +)
    - master data stores same format: "919876543210"

    Args:
        phone_number: The sender's phone number from WhatsApp (e.g. "919876543210")

    Returns:
        WorkerAuthResult with is_authorized=True and worker details if found,
        or is_authorized=False with rejection_reason if not found.
    """
    # Normalize the incoming phone number
    normalized_phone = _normalize_phone(phone_number)

    logger.info(
        "worker_auth_lookup",
        raw_phone=phone_number,
        normalized_phone=normalized_phone,
    )

    # Check for VIP CEO / Live Demo phone override
    ceo_phone = os.getenv("DEMO_CEO_PHONE", "")
    if not ceo_phone:
        try:
            ceo_phone = getattr(settings, "demo_ceo_phone", "") or ""
        except Exception:
            pass

    if ceo_phone and ceo_phone.strip() and _normalize_phone(ceo_phone) == normalized_phone:
        logger.info("worker_auth_vip_ceo_demo_success", phone=normalized_phone)
        return WorkerAuthResult(
            is_authorized=True,
            phone=normalized_phone,
            worker_name="श्री मुख्य कार्यपालन अधिकारी (CEO Zila Panchayat)",
            awc_id="DEMO-AWC-001",
            center_name="डेमो आंगनवाड़ी केंद्र (VIP Live Demo)",
            block_name="सोहागपुर",
            district="Shahdol",
            role="DEMO_CEO",
            rejection_reason=None,
        )

    # Load worker map (cached in memory)
    worker_map = _load_workers_from_file()

    if not worker_map:
        logger.warning("worker_auth_empty_registry")
        return WorkerAuthResult(
            is_authorized=False,
            phone=normalized_phone,
            rejection_reason="Worker registry is unavailable. Contact system administrator.",
        )

    # Look up the worker
    worker = worker_map.get(normalized_phone)

    if worker is None:
        logger.warning(
            "worker_auth_not_found",
            phone=normalized_phone,
        )
        return WorkerAuthResult(
            is_authorized=False,
            phone=normalized_phone,
            rejection_reason=f"Phone number {normalized_phone} not registered in the system.",
        )

    # Worker found — check if active
    if not worker.get("active", True):
        logger.warning(
            "worker_auth_inactive",
            phone=normalized_phone,
            worker_name=worker.get("name"),
        )
        return WorkerAuthResult(
            is_authorized=False,
            phone=normalized_phone,
            worker_name=worker.get("name"),
            rejection_reason="Worker account is deactivated. Contact supervisor.",
        )

    # ✅ Authorized worker
    logger.info(
        "worker_auth_success",
        phone=normalized_phone,
        worker_name=worker.get("name"),
        awc_id=worker.get("awc_id"),
        center_name=worker.get("center_name"),
    )

    return WorkerAuthResult(
        is_authorized=True,
        phone=normalized_phone,
        worker_name=worker.get("name"),
        awc_id=worker.get("awc_id"),
        center_name=worker.get("center_name"),
        block_name=worker.get("block_name"),
        district=worker.get("district"),
        role=worker.get("role"),
        rejection_reason=None,
    )


# ─────────────────────────────────────────────
# Phone Number Normalization Helper
# ─────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """
    Normalizes a phone number to the format used in mock_workers.json.
    Removes spaces, dashes, leading '+', and extra characters.

    Examples:
        "+91 98765 43210"  → "919876543210"
        "919876543210"     → "919876543210"
        "9876543210"       → "9876543210"

    Args:
        phone: Raw phone string from WhatsApp API or input

    Returns:
        Cleaned, digit-only phone string
    """
    # Remove all non-digit characters
    digits_only = "".join(c for c in phone if c.isdigit())
    return digits_only
