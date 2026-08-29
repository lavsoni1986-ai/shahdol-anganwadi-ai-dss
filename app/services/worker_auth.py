# app/services/worker_auth.py
# =====================================================================
# BharatOS — Shahdol Anganwadi Digital Verification System
# Worker Authentication Service
# Looks up sender phone number against the registered AnganwadiMaster.
# =====================================================================

import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.models import AnganwadiMaster
from app.schemas import WorkerAuthResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# Phone Number Normalization Helper
# ─────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """
    Normalizes a phone number to standard format.
    Removes spaces, dashes, leading '+', and extra characters.

    Args:
        phone: Raw phone string from WhatsApp API or input

    Returns:
        Cleaned, digit-only phone string
    """
    if not phone:
        return ""
    # Remove all non-digit characters
    digits_only = "".join(c for c in phone if c.isdigit())
    return digits_only[-10:] if len(digits_only) >= 10 else digits_only


# ─────────────────────────────────────────────
# Main Authentication Function
# ─────────────────────────────────────────────

async def authenticate_worker(phone_number: str, db: AsyncSession) -> WorkerAuthResult:
    """
    Authenticates a WhatsApp sender by checking their phone number
    against the AnganwadiMaster table.

    Args:
        phone_number: The sender's phone number from WhatsApp (e.g. "919876543210")
        db: Database session

    Returns:
        WorkerAuthResult with is_authorized=True and worker details if found,
        or is_authorized=False with rejection_reason if not found.
    """
    normalized_phone = _normalize_phone(phone_number)

    logger.info(
        "worker_auth_lookup",
        raw_phone=phone_number,
        normalized_phone=normalized_phone,
    )

    result = await db.execute(
        select(AnganwadiMaster).where(
            AnganwadiMaster.worker_mobile.like(f"%{normalized_phone}")
        )
    )
    workers = result.scalars().all()
    
    worker = None
    for w in workers:
        if w.worker_mobile and _normalize_phone(w.worker_mobile) == normalized_phone:
            worker = w
            break

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
    if not worker.active_status:
        logger.warning(
            "worker_auth_inactive",
            phone=normalized_phone,
            worker_name=worker.worker_name,
        )
        return WorkerAuthResult(
            is_authorized=False,
            phone=normalized_phone,
            worker_name=worker.worker_name,
            rejection_reason="Worker account is deactivated. Contact supervisor.",
        )

    # ✅ Authorized worker
    logger.info(
        "worker_auth_success",
        phone=normalized_phone,
        worker_name=worker.worker_name,
        awc_id=worker.awc_code,
        center_name=worker.center_name,
    )

    return WorkerAuthResult(
        is_authorized=True,
        phone=normalized_phone,
        worker_name=worker.worker_name,
        awc_id=worker.awc_code,
        center_name=worker.center_name,
        block_name=worker.block_name,
        district=worker.district,
        role="worker",
        rejection_reason=None,
    )


def reload_workers() -> None:
    """
    Deprecated. Kept for API compatibility. Cache is no longer used.
    """
    logger.info("worker_master_data_reloaded (no-op with DB)")
