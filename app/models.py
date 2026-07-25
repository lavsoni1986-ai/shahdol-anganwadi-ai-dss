# app/models.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# SQLAlchemy ORM Models — Database Table Definitions
# =====================================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Boolean,
    Enum as SAEnum,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    """Returns the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    """Generates a new UUID4 string."""
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# Submission Status Enum
# ─────────────────────────────────────────────
class SubmissionStatus:
    RECEIVED   = "RECEIVED"     # Webhook received, record saved
    PROCESSING = "PROCESSING"   # Media download or OCR in progress
    PROCESSED  = "PROCESSED"    # AI/OCR processing complete
    APPROVED   = "APPROVED"     # Supervisor approved the submission
    FLAGGED    = "FLAGGED"      # Supervisor flagged for exception
    FAILED     = "FAILED"       # Processing failed after retries
    REJECTED   = "REJECTED"     # Unauthorized or invalid submission

    # All terminal statuses that a supervisor can see in dashboard
    DASHBOARD_VISIBLE = {RECEIVED, PROCESSED, APPROVED, FLAGGED}


# ─────────────────────────────────────────────
# DailySubmission — Core MVP Table
# Records every WhatsApp photo submission from an AWC worker
# ─────────────────────────────────────────────
class DailySubmission(Base):
    """
    Stores each photo submission received from an Anganwadi Worker (AWW)
    via WhatsApp. One record per incoming message.

    Table: daily_submissions
    """

    __tablename__ = "daily_submissions"

    # --- Primary Key ---
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Auto-increment integer primary key",
    )

    # --- Unique Submission Identifier ---
    submission_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        default=_new_uuid,
        comment="UUID4 unique identifier for this submission",
    )
    audit_id: Mapped[str | None] = mapped_column(
        String(30),
        unique=True,
        nullable=True,
        index=True,
        comment="Audit ID in format SHD-YYYYMMDD-000001",
    )

    # --- AWC Worker Identity ---
    worker_phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Sender's WhatsApp phone number with country code (e.g. 919876543210)",
    )
    worker_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Worker's full name from master data",
    )

    # --- AWC Centre Details ---
    awc_id: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
        comment="AWC centre identifier (e.g. AWC-SHA-1042)",
    )
    center_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="AWC centre name in Hindi (e.g. रामपुर)",
    )
    block_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Block name (e.g. सोहागपुर)",
    )
    district: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="District name",
    )

    # --- Submission Timing ---
    submission_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        comment="Timestamp when the WhatsApp message was received (UTC)",
    )
    whatsapp_timestamp: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Original timestamp from WhatsApp message payload (Unix epoch)",
    )

    # --- Media Details ---
    raw_media_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Media ID from Meta API payload (for future media download)",
    )
    media_mime_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="MIME type of media (e.g. image/jpeg)",
    )
    media_sha256: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="SHA256 hash of media file (from WhatsApp API)",
    )
    local_media_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Local file path where downloaded image is stored",
    )
    brightness_score: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Image brightness rating (Normal, Dark, Very Dark)",
    )
    camera_make: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Camera make extracted from EXIF",
    )
    camera_model: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Camera model extracted from EXIF",
    )
    device_timestamp: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Device timestamp extracted from EXIF",
    )

    # --- WhatsApp Message Details ---
    message_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        comment="WhatsApp Message ID (wamid) for deduplication",
    )
    message_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Message type: image, text, document, etc.",
    )
    caption: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional caption text sent with the image",
    )

    # --- Location (Future Use) ---
    latitude: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="GPS latitude if location shared"
    )
    longitude: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="GPS longitude if location shared"
    )

    # --- Processing Status ---
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SubmissionStatus.RECEIVED,
        index=True,
        comment="Current processing status of this submission",
    )
    is_authorized: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if the sender is a registered AWC worker",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Reason for rejection if status = REJECTED",
    )

    # --- Raw Payload (Audit Trail) ---
    raw_payload: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full raw JSON webhook payload for audit and debugging",
    )

    # --- Acknowledgement Tracking ---
    ack_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if acknowledgement WhatsApp reply was sent successfully",
    )
    ack_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when acknowledgement was sent",
    )
    ack_message_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="WhatsApp Message ID of the acknowledgement reply",
    )

    # --- Day 2: Supervisor Review Audit Fields ---
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when a supervisor reviewed this submission",
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Reviewer's officer ID or login (e.g. cdpo_shahdol)",
    )
    reviewer_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Full name of the reviewing officer",
    )
    review_action: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Action taken by reviewer: APPROVED | FLAGGED",
    )
    flag_reason: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Short reason code for flagging (e.g. Blur Image, Outside Geofence)",
    )
    reviewer_remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional long-form remarks from the reviewing officer",
    )
    # Day 4 placeholder — will be populated by AI/OCR pipeline
    ai_score: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="AI confidence score/summary text",
    )
    image_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Perceptual hash (pHash) of the submitted image for duplicate detection",
    )

    # --- Record Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        comment="Database record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        comment="Database record last update timestamp",
    )

    def __repr__(self) -> str:
        return (
            f"<DailySubmission("
            f"id={self.id}, "
            f"awc_id={self.awc_id!r}, "
            f"worker_phone={self.worker_phone!r}, "
            f"status={self.status!r}"
            f")>"
        )


# ─────────────────────────────────────────────
# WebhookLog — Audit Log for All Incoming Payloads
# ─────────────────────────────────────────────
class WebhookLog(Base):
    """
    Stores every raw incoming webhook payload for audit purposes.
    Provides a complete audit trail independent of business processing.

    Table: webhook_logs
    """

    __tablename__ = "webhook_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    source_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Raw JSON webhook payload"
    )
    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if payload processing failed",
    )

    def __repr__(self) -> str:
        return f"<WebhookLog(id={self.id}, received_at={self.received_at!r})>"
