# app/utils/audit.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Audit ID Generator Service
# Generates unique, sequential Audit IDs in format: SHD-YYYYMMDD-000001
# =====================================================================

import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logger import get_logger

logger = get_logger(__name__)


async def generate_audit_id(db: AsyncSession, max_retries: int = 3) -> str:
    """
    Generates a unique Audit ID in format: SHD-YYYYMMDD-000001.
    Retries up to 3 times in case of concurrency or collision.

    Args:
        db: AsyncSession database session
        max_retries: Maximum number of generation attempts (default: 3)

    Returns:
        Formatted Audit ID string (e.g. "SHD-20260723-000001")
    """
    from app.models import DailySubmission

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    prefix = f"SHD-{today_str}-"

    for attempt in range(1, max_retries + 1):
        try:
            # Query highest audit_id for today
            stmt = (
                select(DailySubmission.audit_id)
                .where(DailySubmission.audit_id.like(f"{prefix}%"))
                .order_by(DailySubmission.audit_id.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            latest_audit_id = result.scalar_one_or_none()

            if latest_audit_id:
                try:
                    seq_str = latest_audit_id.split("-")[-1]
                    seq_num = int(seq_str) + attempt  # Increment based on attempt
                except (ValueError, IndexError):
                    seq_num = 1
            else:
                seq_num = attempt

            candidate_audit_id = f"{prefix}{seq_num:06d}"

            # Verify uniqueness in DB
            chk_stmt = select(DailySubmission.id).where(
                DailySubmission.audit_id == candidate_audit_id
            )
            chk_res = await db.execute(chk_stmt)
            if chk_res.scalar_one_or_none() is None:
                logger.info("audit_id_generated", audit_id=candidate_audit_id, attempt=attempt)
                return candidate_audit_id

        except Exception as e:
            logger.warning(
                "audit_id_generation_retry", attempt=attempt, error=str(e)
            )

    # Fallback to timestamp-based suffix if retries fail
    fallback_seq = datetime.datetime.now(datetime.timezone.utc).strftime("%H%M%S")
    fallback_id = f"{prefix}{fallback_seq}"
    logger.info("audit_id_generated_fallback", audit_id=fallback_id)
    return fallback_id
