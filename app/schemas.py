# app/schemas.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Pydantic v2 Schemas — Request/Response Validation & Serialization
# Used for: WhatsApp webhook payload parsing, API responses
# =====================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


# ═════════════════════════════════════════════════════════════════════
# WhatsApp Webhook Payload Schemas
# These mirror the exact structure of Meta WhatsApp Cloud API payloads.
# Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
# ═════════════════════════════════════════════════════════════════════


class WAProfile(BaseModel):
    """Sender's WhatsApp profile info."""
    name: Optional[str] = None


class WAContact(BaseModel):
    """Contact object inside WhatsApp webhook messages."""
    wa_id: Optional[str] = None
    profile: Optional[WAProfile] = None


class WAMediaPayload(BaseModel):
    """Image/Document/Audio/Video media object in WhatsApp message."""
    id: Optional[str] = Field(None, description="Meta Media ID for download")
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    caption: Optional[str] = None


class WALocationPayload(BaseModel):
    """Location object in WhatsApp message (optional)."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    name: Optional[str] = None
    address: Optional[str] = None


class WATextPayload(BaseModel):
    """Text body of a WhatsApp text message."""
    body: Optional[str] = None


class WAMessage(BaseModel):
    """
    A single WhatsApp message object within a webhook notification.
    Contains: sender info, message type, media/text payload, and timestamps.
    """
    id: Optional[str] = Field(None, description="WhatsApp Message ID (wamid)")
    from_: Optional[str] = Field(None, alias="from", description="Sender phone number")
    timestamp: Optional[str] = None
    type: Optional[str] = None       # "image", "text", "document", "audio", etc.

    # Message content — only one will be populated based on `type`
    image: Optional[WAMediaPayload] = None
    document: Optional[WAMediaPayload] = None
    audio: Optional[WAMediaPayload] = None
    video: Optional[WAMediaPayload] = None
    text: Optional[WATextPayload] = None
    location: Optional[WALocationPayload] = None

    class Config:
        populate_by_name = True     # Allow alias `from_` to be populated by "from"

    @property
    def sender_phone(self) -> Optional[str]:
        """Returns the sender's phone number."""
        return self.from_

    @property
    def media_payload(self) -> Optional[WAMediaPayload]:
        """Returns the media payload regardless of type (image/video/document)."""
        return self.image or self.document or self.audio or self.video


class WAValue(BaseModel):
    """
    The `value` object inside a webhook change entry.
    Contains messages, contacts, and metadata.
    """
    messaging_product: Optional[str] = None
    metadata: Optional[dict] = None
    contacts: Optional[List[WAContact]] = None
    messages: Optional[List[WAMessage]] = None
    statuses: Optional[List[dict]] = None  # Message status updates (sent/delivered/read)
    errors: Optional[List[dict]] = None


class WAChange(BaseModel):
    """A change entry in a webhook notification."""
    value: Optional[WAValue] = None
    field: Optional[str] = None


class WAEntry(BaseModel):
    """A single entry in the WhatsApp webhook payload."""
    id: Optional[str] = None
    changes: Optional[List[WAChange]] = None


class WhatsAppWebhookPayload(BaseModel):
    """
    Root schema for the full WhatsApp Cloud API webhook POST body.
    Ref: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
    """
    object: Optional[str] = None    # Always "whatsapp_business_account"
    entry: Optional[List[WAEntry]] = None


# ═════════════════════════════════════════════════════════════════════
# Internal Processing Schemas
# Used for transferring parsed data between service layers
# ═════════════════════════════════════════════════════════════════════


class ParsedSubmission(BaseModel):
    """
    Normalized, parsed submission data extracted from the raw webhook payload.
    Passed between the webhook handler and business logic services.
    """
    # Sender info
    sender_phone: str = Field(..., description="Sender's phone number with country code")
    message_id: Optional[str] = None
    whatsapp_timestamp: Optional[str] = None
    message_type: Optional[str] = None

    # Media info
    media_id: Optional[str] = None
    media_mime_type: Optional[str] = None
    media_sha256: Optional[str] = None
    caption: Optional[str] = None

    # Location info
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Raw payload for audit
    raw_payload_json: Optional[str] = None


class WorkerAuthResult(BaseModel):
    """
    Result of a worker authentication lookup.
    Returned by WorkerAuthService.
    """
    is_authorized: bool
    phone: Optional[str] = None
    worker_name: Optional[str] = None
    awc_id: Optional[str] = None
    center_name: Optional[str] = None
    block_name: Optional[str] = None
    district: Optional[str] = None
    role: Optional[str] = None

    # Reason for unauthorized (if applicable)
    rejection_reason: Optional[str] = None


# ═════════════════════════════════════════════════════════════════════
# API Response Schemas
# Used for structured API responses to clients / dashboard / monitoring
# ═════════════════════════════════════════════════════════════════════


class HealthResponse(BaseModel):
    """Response schema for the /health endpoint."""
    status: str
    app_name: str
    version: str
    timestamp: datetime
    database: dict
    whatsapp_api: dict


class SubmissionResponse(BaseModel):
    """Response schema representing a saved daily submission."""
    id: int
    submission_id: str
    awc_id: Optional[str]
    worker_phone: str
    worker_name: Optional[str]
    center_name: Optional[str]
    block_name: Optional[str]
    submission_timestamp: datetime
    status: str
    is_authorized: bool
    ack_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True      # Enable ORM mode (model → schema conversion)


class WebhookVerifyResponse(BaseModel):
    """Response returned when Meta successfully verifies the webhook."""
    challenge: str
    message: str = "Webhook verified successfully"


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
