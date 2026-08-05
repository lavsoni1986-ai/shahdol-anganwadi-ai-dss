# app/main.py
# =====================================================================
# BharatOS — District Shahdol Anganwadi Digital Verification MVP
# FastAPI Application Entry Point
# Handles: Webhook verification, Incoming WhatsApp messages,
#          Worker authentication, Data persistence, Auto-acknowledgement
# =====================================================================

import socket

# Force IPv4 socket resolution globally at process startup
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in res if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_getaddrinfo

import json
import pathlib
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import check_db_health, get_db, init_db
from app.models import DailySubmission, SubmissionStatus, WebhookLog
from app.routers import dashboard as dashboard_router
from app.routers import reports as reports_router
from app.services.ai_vision import process_image_ai_pipeline
from app.schemas import (
    HealthResponse,
    ParsedSubmission,
    SubmissionResponse,
    WhatsAppWebhookPayload,
    WorkerAuthResult,
)
from app.services.whatsapp import (
    send_acknowledgement,
    send_unauthorized_rejection,
    send_system_error_notice,
)
from app.services.worker_auth import authenticate_worker, reload_workers
from app.utils.audit import generate_audit_id
from app.utils.logger import configure_logging, get_logger

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
_APP_DIR = pathlib.Path(__file__).parent
_TEMPLATES_DIR = _APP_DIR / "templates"
_STATIC_DIR = _APP_DIR / "static"
_TEMPLATES_DIR.mkdir(exist_ok=True)
_STATIC_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ─────────────────────────────────────────────
# Application Lifespan (Startup / Shutdown)
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Runs startup logic before serving requests,
    and cleanup logic on server shutdown.
    """
    # ── STARTUP ──────────────────────────────
    configure_logging()
    logger = get_logger("app.lifespan")

    logger.info(
        "app_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        database_url=settings.database_url.split("///")[-1],
        whatsapp_configured=settings.is_whatsapp_configured,
    )

    # Initialize database (create tables if not exist)
    await init_db()
    logger.info("app_ready", message="BharatOS Shahdol AWC backend is running!")

    yield  # Application serves requests here

    # ── SHUTDOWN ─────────────────────────────
    logger.info("app_shutting_down", app_name=settings.app_name)


# ─────────────────────────────────────────────
# FastAPI App Instance
# ─────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description=(
        "🇮🇳 BharatOS — District Shahdol Anganwadi Digital Verification "
        "& Decision Support System. "
        "Day 1: WhatsApp webhook ingestion & auto-acknowledgement. "
        "Day 2: Admin Dashboard APIs & Web Review Panel for District Officers."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── Mount static files (CSS, JS for dashboard) ────────────────────
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── Register API Routers ──────────────────────────────────────────
app.include_router(dashboard_router.router)
app.include_router(reports_router.router)

# Logger instance (after configure_logging is called in lifespan)
logger = get_logger("app.main")


# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],   # Restrict in production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Logs every HTTP request with timing info.
    Adds X-Request-ID header to each response for tracing.
    Provides prominent WEBHOOK HIT logging with Cloudflare & Meta headers for /webhook requests.
    """
    request_id = str(uuid.uuid4())[:8]
    start_time = time.monotonic()

    # Enhanced entry log for Webhook endpoints
    if request.url.path.startswith("/webhook"):
        cf_ip = request.headers.get("cf-connecting-ip")
        x_forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = cf_ip or (x_forwarded_for.split(",")[0].strip() if x_forwarded_for else (request.client.host if request.client else "unknown"))
        logger.info(
            "WEBHOOK HIT",
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            cf_ray=request.headers.get("cf-ray"),
            user_agent=request.headers.get("user-agent"),
            content_type=request.headers.get("content-type"),
            meta_signature=request.headers.get("x-hub-signature-256"),
            request_id=request_id,
        )

    response = await call_next(request)

    duration_ms = (time.monotonic() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
        request_id=request_id,
        client_host=request.client.host if request.client else "unknown",
    )

    return response


# ─────────────────────────────────────────────
# Helper: Parse WhatsApp Webhook Payload
# ─────────────────────────────────────────────

def _parse_webhook_payload(raw_body: dict) -> Optional[ParsedSubmission]:
    """
    Parses the raw WhatsApp webhook JSON body and extracts the first
    message's details into a normalized ParsedSubmission object.

    Returns None if the payload contains no actionable message
    (e.g., it's a status update, or the structure is unexpected).

    Args:
        raw_body: The raw parsed JSON dict from the webhook POST body

    Returns:
        ParsedSubmission if a message is found, else None
    """
    try:
        payload = WhatsAppWebhookPayload.model_validate(raw_body)

        if not payload.entry:
            return None

        for entry in payload.entry:
            if not entry.changes:
                continue

            for change in entry.changes:
                if not change.value:
                    continue

                value = change.value

                # Skip non-message payloads (e.g., message status updates)
                if not value.messages:
                    continue

                # Take the first message in this batch
                message = value.messages[0]

                # We need a sender phone number at minimum
                sender_phone = message.from_
                if not sender_phone:
                    continue

                # Extract media info based on message type
                media_payload = message.media_payload
                media_id = media_payload.id if media_payload else None
                media_mime = media_payload.mime_type if media_payload else None
                media_sha256 = media_payload.sha256 if media_payload else None
                caption = media_payload.caption if media_payload else None

                # Extract location if provided
                lat = message.location.latitude if message.location else None
                lon = message.location.longitude if message.location else None
                addr = message.location.address if message.location else None

                return ParsedSubmission(
                    sender_phone=sender_phone,
                    message_id=message.id,
                    whatsapp_timestamp=message.timestamp,
                    message_type=message.type,
                    media_id=media_id,
                    media_mime_type=media_mime,
                    media_sha256=media_sha256,
                    caption=caption,
                    latitude=lat,
                    longitude=lon,
                    address=addr,
                    raw_payload_json=json.dumps(raw_body, ensure_ascii=False),
                )

    except Exception as e:
        logger.error("webhook_payload_parse_error", error=str(e), exc_info=True)

    return None


# ═════════════════════════════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# GET /  — Health Check / Root
# ─────────────────────────────────────────────

@app.get(
    "/",
    summary="Root — System Info",
    tags=["System"],
    response_class=JSONResponse,
)
async def root():
    """
    Root endpoint. Returns basic system info and API status.
    """
    return {
        "system": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
        "pilot": {
            "district": settings.pilot_district,
            "awc_id": settings.pilot_awc_id,
            "center": settings.pilot_center_name,
            "block": settings.pilot_block_name,
        },
        "docs": "/docs",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "🇮🇳 BharatOS — Shahdol Anganwadi Digital Verification System is Running",
    }


# ─────────────────────────────────────────────
# GET /health — Detailed Health Check
# ─────────────────────────────────────────────

@app.get(
    "/health",
    summary="System Health Check",
    tags=["System"],
    response_class=JSONResponse,
)
async def health_check():
    """
    Detailed health check including database connectivity
    and WhatsApp API configuration status.
    """
    db_health = await check_db_health()

    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_health,
        "whatsapp_api": {
            "configured": settings.is_whatsapp_configured,
            "api_version": settings.whatsapp_api_version,
            "phone_number_id": (
                settings.whatsapp_phone_number_id[:6] + "***"
                if settings.whatsapp_phone_number_id
                else "NOT SET"
            ),
        },
        "pilot_config": {
            "district": settings.pilot_district,
            "awc_id": settings.pilot_awc_id,
            "center": settings.pilot_center_name,
            "block": settings.pilot_block_name,
        },
    }


@app.post(
    "/api/v1/reload-workers",
    summary="Reload Worker Master Data",
    tags=["System"],
)
async def api_reload_workers():
    """Clears in-memory worker auth cache and reloads mock_workers.json from disk."""
    reload_workers()
    return {"status": "success", "message": "Worker master data reloaded successfully."}



# ─────────────────────────────────────────────
# GET /webhook — Meta Webhook Verification
# ─────────────────────────────────────────────

@app.get(
    "/webhook",
    summary="Meta WhatsApp Webhook Verification",
    tags=["Webhook"],
    response_class=PlainTextResponse,
)
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Handles the Meta WhatsApp webhook verification challenge.

    When you configure a webhook URL in Meta Developer Console,
    Meta sends a GET request with these parameters to verify ownership.

    Process:
    1. Check hub.mode == "subscribe"
    2. Check hub.verify_token matches our WHATSAPP_VERIFY_TOKEN
    3. Respond with hub.challenge as plain text (200 OK)

    Reference: https://developers.facebook.com/docs/graph-api/webhooks/getting-started
    """
    logger.info(
        "webhook_verification_attempt",
        hub_mode=hub_mode,
        token_match=(hub_verify_token == settings.whatsapp_verify_token),
    )

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info(
            "webhook_verification_success",
            challenge=hub_challenge,
        )
        # Return the challenge as plain text — Meta expects EXACTLY this
        return PlainTextResponse(content=hub_challenge, status_code=200)

    # Verification failed
    logger.warning(
        "webhook_verification_failed",
        hub_mode=hub_mode,
        expected_token_prefix=settings.whatsapp_verify_token[:6] + "***",
        received_token=(
            hub_verify_token[:6] + "***" if hub_verify_token else "None"
        ),
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed: invalid token or mode",
    )


# ─────────────────────────────────────────────
# POST /webhook — Incoming WhatsApp Message
# ─────────────────────────────────────────────

@app.post(
    "/webhook",
    summary="Incoming WhatsApp Message Handler",
    tags=["Webhook"],
    status_code=status.HTTP_200_OK,
)
@app.post(
    "/webhook/",
    include_in_schema=False,
    status_code=status.HTTP_200_OK,
)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Main webhook handler for incoming WhatsApp messages.

    Meta WhatsApp Cloud API delivers all incoming messages to this endpoint
    as HTTP POST requests with a JSON body.

    IMPORTANT: This endpoint MUST always return HTTP 200 quickly.
    Meta will retry delivery if it receives non-200 or a timeout.
    All heavy processing is done synchronously but efficiently.

    Business Logic:
    1. Parse the raw payload
    2. Log raw payload to webhook_logs table (audit trail)
    3. Extract sender phone and media info
    4. Authenticate the sender against worker master list
    5. Save submission record to daily_submissions table
    6. Send WhatsApp auto-reply (acknowledgement or rejection)

    Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks
    """
    received_at = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else None
    meta_signature = request.headers.get("x-hub-signature-256")

    # Diagnostic entry log (Step 6)
    logger.info(
        "WEBHOOK HIT",
        method=request.method,
        url=str(request.url),
        client_ip=client_ip,
        meta_signature=meta_signature,
        content_type=request.headers.get("content-type"),
    )

    # ── 1. Read raw body ─────────────────────
    try:
        raw_body: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("webhook_json_parse_failed", error=str(e))
        # Must return 200 to prevent Meta retries for malformed payloads
        return JSONResponse(
            status_code=200,
            content={"status": "error", "detail": "Invalid JSON body"},
        )

    logger.info(
        "webhook_received",
        object_type=raw_body.get("object"),
        received_at=received_at.isoformat(),
    )

    # ── 2. Save raw audit log ────────────────
    client_ip = request.client.host if request.client else None
    webhook_log = WebhookLog(
        received_at=received_at,
        source_ip=client_ip,
        payload=json.dumps(raw_body, ensure_ascii=False),
        processing_error=None,
    )
    db.add(webhook_log)

    # Skip non-WhatsApp payloads (status updates, etc.)
    if raw_body.get("object") != "whatsapp_business_account":
        logger.debug(
            "webhook_non_whatsapp_payload",
            object_type=raw_body.get("object"),
        )
        await db.commit()
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # ── 3. Parse the payload ─────────────────
    parsed = _parse_webhook_payload(raw_body)

    if parsed is None:
        # Could be a status update (sent/delivered/read) — safe to ignore
        logger.info("webhook_no_actionable_message", note="Likely a status update")
        await db.commit()
        return JSONResponse(status_code=200, content={"status": "no_message"})

    logger.info(
        "webhook_message_parsed",
        sender_phone=parsed.sender_phone,
        message_type=parsed.message_type,
        message_id=parsed.message_id,
        has_media=parsed.media_id is not None,
    )

    # ── 4. Authenticate worker & Validate MIME ─────
    auth_result: WorkerAuthResult = await authenticate_worker(parsed.sender_phone, db)

    # MIME Validation (Allow only image/jpeg, image/png, image/jpg)
    allowed_mimes = {"image/jpeg", "image/png", "image/jpg"}
    if parsed.media_id and parsed.media_mime_type:
        if parsed.media_mime_type.lower() not in allowed_mimes:
            logger.warning("invalid_mime_type_rejected", mime=parsed.media_mime_type, sender=parsed.sender_phone)
            auth_result.is_authorized = False
            auth_result.rejection_reason = f"Invalid file type ({parsed.media_mime_type}). Only JPEG and PNG images are allowed."

    # ── 5. Generate Audit ID & Persist submission to DB ──
    new_submission_id = str(uuid.uuid4())
    audit_id = await generate_audit_id(db)

    submission = DailySubmission(
        submission_id=new_submission_id,
        audit_id=audit_id,
        worker_phone=parsed.sender_phone,
        worker_name=auth_result.worker_name,
        awc_id=auth_result.awc_id,
        center_name=auth_result.center_name,
        block_name=auth_result.block_name,
        district=auth_result.district,
        submission_timestamp=received_at,
        whatsapp_timestamp=parsed.whatsapp_timestamp,
        raw_media_id=parsed.media_id,
        media_mime_type=parsed.media_mime_type,
        media_sha256=parsed.media_sha256,
        message_id=parsed.message_id,
        message_type=parsed.message_type,
        caption=parsed.caption,
        latitude=str(parsed.latitude) if parsed.latitude else None,
        longitude=str(parsed.longitude) if parsed.longitude else None,
        address=parsed.address,
        status=SubmissionStatus.RECEIVED if auth_result.is_authorized else SubmissionStatus.REJECTED,
        is_authorized=auth_result.is_authorized,
        rejection_reason=auth_result.rejection_reason,
        raw_payload=parsed.raw_payload_json,
        ack_sent=False,
    )

    db.add(submission)
    await db.flush()    # Flush to assign DB id without full commit

    logger.info(
        "submission_saved",
        submission_id=new_submission_id,
        audit_id=audit_id,
        awc_id=auth_result.awc_id,
        is_authorized=auth_result.is_authorized,
        status=submission.status,
    )

    # ── 6. Send WhatsApp auto-reply ──────────
    ack_result = {"success": False, "message_id": None}

    if auth_result.is_authorized:
        # Send Hindi acknowledgement message ✅
        ack_result = await send_acknowledgement(
            to_phone=parsed.sender_phone,
            auth_result=auth_result,
            submission_timestamp=received_at,
        )
    else:
        # Send Hindi unauthorized rejection message ❌
        ack_result = await send_unauthorized_rejection(
            to_phone=parsed.sender_phone,
        )

    # Update submission record with acknowledgement status
    submission.ack_sent = ack_result.get("success", False)
    if ack_result.get("success"):
        submission.ack_sent_at = datetime.now(timezone.utc)
        submission.ack_message_id = ack_result.get("message_id")

    # Also update the webhook log with any processing error
    if not ack_result.get("success") and ack_result.get("error"):
        webhook_log.processing_error = ack_result.get("error")

    # Final commit — persists both submission and webhook log
    await db.commit()

    # ── 7. Trigger AI Pipeline (Day 4) ───────
    if auth_result.is_authorized and parsed.media_id:
        background_tasks.add_task(process_image_ai_pipeline, new_submission_id)
        logger.info("ai_pipeline_queued", submission_id=new_submission_id)

    logger.info(
        "webhook_processing_complete",
        submission_id=new_submission_id,
        sender_phone=parsed.sender_phone,
        is_authorized=auth_result.is_authorized,
        ack_sent=submission.ack_sent,
        ack_message_id=submission.ack_message_id,
    )

    # Return 200 immediately — Meta requires this
    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
            "submission_id": new_submission_id,
            "authorized": auth_result.is_authorized,
            "ack_sent": submission.ack_sent,
        },
    )


# ─────────────────────────────────────────────
# GET /dashboard — HTML Admin Review Panel
# ─────────────────────────────────────────────

@app.get(
    "/dashboard",
    summary="Admin Dashboard — Web Review Panel",
    tags=["Dashboard"],
    response_class=HTMLResponse,
    include_in_schema=False,   # Don't show in Swagger (it's a UI, not an API)
)
async def dashboard_panel(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Serves the full-featured Admin Dashboard HTML panel.
    Built with Tailwind CSS + Vanilla JS — zero build step required.
    Access at: http://localhost:8000/dashboard
    """
    from sqlalchemy.future import select
    from app.models import DistrictSettings
    result = await db.execute(select(DistrictSettings))
    ds = result.scalars().first()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "district": ds.district_name if ds else "Shahdol",
            "cdpo_name": ds.cdpo_name if ds else "N/A",
            "app_version": settings.app_version,
        },
    )


# ─────────────────────────────────────────────
# Global Exception Handler
# ─────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exception and returns a structured 500 response.
    Also logs the full traceback for debugging.

    IMPORTANT: Webhook endpoints still return 200 to prevent Meta retries.
    """
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True,
    )

    # For webhook endpoints, always return 200 to prevent Meta from retrying
    if request.url.path == "/webhook" and request.method == "POST":
        return JSONResponse(
            status_code=200,
            content={"status": "error", "detail": "Internal processing error"},
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
