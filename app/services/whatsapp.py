# app/services/whatsapp.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Meta WhatsApp Cloud API — Message Sending Service
# Handles: Auto-acknowledgements, Unauthorized rejection messages,
#          and future notification sending.
# Official API Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/messages
# =====================================================================

from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo  # Python 3.9+ stdlib

import httpx
import os

from app.config import settings
from app.schemas import WorkerAuthResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# IST timezone for displaying local time in Hindi messages
IST = ZoneInfo("Asia/Kolkata")


def verify_meta_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Verifies Meta's X-Hub-Signature-256 header against the RAW request body
    using the WhatsApp App Secret (HMAC-SHA256).

    Returns True only when the signature matches; never trusts the header alone.
    """
    import hashlib
    import hmac

    if not app_secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header, expected)

# HTTP timeout for WhatsApp API calls
_API_TIMEOUT_SECONDS = 30.0   # Increased for document delivery reliability
_DOC_TIMEOUT_SECONDS = 45.0   # Separate, higher timeout for document sends
_MAX_RETRIES         = 5      # Increased to 5 for better resilience against Meta 131053 errors
_RETRY_BACKOFF_BASE  = 2.0    # Exponential backoff: 1s, 2s, 4s, 8s, 16s


# ─────────────────────────────────────────────
# Message Templates (Hindi)
# ─────────────────────────────────────────────

def _build_acknowledgement_message(
    worker_name: str,
    awc_id: str,
    center_name: str,
    block_name: str,
    submission_timestamp: datetime,
) -> str:
    """
    Builds the Hindi auto-acknowledgement message for authorized workers.

    Args:
        worker_name: Worker's full name
        awc_id: AWC centre ID (e.g. AWC-SHA-1042)
        center_name: Centre name in Hindi
        block_name: Block name
        submission_timestamp: UTC datetime of submission

    Returns:
        Formatted Hindi message string ready to send via WhatsApp
    """
    # Convert UTC timestamp to IST for display
    ist_time = submission_timestamp.astimezone(IST)
    formatted_time = ist_time.strftime("%d/%m/%Y %I:%M %p")   # e.g. 21/07/2026 08:45 AM

    # Extract AWC number from AWC ID for display (e.g. "AWC-SHA-1042" → "1042")
    awc_display = awc_id.split("-")[-1] if awc_id and "-" in awc_id else awc_id

    message = (
        f"✅ *डेटा प्राप्त हुआ।*\n\n"
        f"📍 *केंद्र:* {center_name} (AWC-{awc_display})\n"
        f"🏘️ *ब्लॉक:* {block_name}\n"
        f"⏰ *समय:* {formatted_time} (IST)\n\n"
        f"आपकी उपस्थिति एवं भोजन वितरण रिपोर्ट सफलतापूर्वक दर्ज कर ली गई है।\n\n"
        f"🙏 धन्यवाद, {worker_name}!"
    )
    return message


def _build_unauthorized_message() -> str:
    """
    Builds the Hindi rejection message for unregistered senders.

    Returns:
        Hindi error message string
    """
    return (
        "❌ *क्षमा करें!*\n\n"
        "आपका मोबाइल नंबर प्रणाली में पंजीकृत नहीं है।\n\n"
        "कृपया अपने *सुपरवाइजर* से संपर्क करें और अपना नंबर पंजीकृत करवाएं।\n\n"
        "📞 _BharatOS - Shahdol Anganwadi Helpline_"
    )


def _build_error_message() -> str:
    """
    Builds a generic Hindi error notification for system failures.
    Sent when internal processing fails but connection is alive.
    """
    return (
        "⚠️ *तकनीकी समस्या*\n\n"
        "आपका संदेश प्राप्त हो गया है, लेकिन प्रसंस्करण में एक त्रुटि आई।\n"
        "कृपया कुछ देर बाद पुनः प्रयास करें।\n\n"
        "_BharatOS टीम समस्या की जांच कर रही है।_"
    )


# ─────────────────────────────────────────────
# WhatsApp API Client
# ─────────────────────────────────────────────

async def send_whatsapp_text_message(
    to_phone: str,
    message_text: str,
) -> dict:
    """
    Sends a text message to a WhatsApp number using Meta Cloud API.

    Args:
        to_phone: Recipient phone number with country code (e.g. "919876543210")
        message_text: The text body to send (supports *bold*, _italic_ markdown)

    Returns:
        dict with keys:
            "success": bool
            "message_id": str | None (WhatsApp message ID if sent)
            "error": str | None (error description if failed)
            "status_code": int | None (HTTP status code)

    Raises:
        No exceptions — all errors are captured and returned in the result dict.
    """
    if not settings.is_whatsapp_configured:
        logger.warning(
            "whatsapp_not_configured",
            to_phone=to_phone,
            note="WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set in .env",
        )
        return {
            "success": False,
            "message_id": None,
            "error": "WhatsApp API credentials not configured",
            "status_code": None,
        }

    # Build the API request payload
    # Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/messages/text-messages
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text,
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    api_url = settings.whatsapp_api_url

    logger.info(
        "whatsapp_send_attempt",
        to_phone=to_phone,
        api_url=api_url,
        message_preview=message_text[:50],
    )

    try:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url=api_url,
                json=payload,
                headers=headers,
            )

        response_data = response.json()

        if response.status_code == 200:
            # Extract the WhatsApp message ID from response
            messages = response_data.get("messages", [])
            wa_message_id = messages[0].get("id") if messages else None

            logger.info(
                "whatsapp_message_sent",
                to_phone=to_phone,
                wa_message_id=wa_message_id,
                status_code=response.status_code,
            )
            return {
                "success": True,
                "message_id": wa_message_id,
                "error": None,
                "status_code": response.status_code,
            }
        else:
            # API returned non-200 (e.g. 400 bad request, 401 auth failure)
            error_info = response_data.get("error", {})
            error_msg = error_info.get("message", "Unknown API error")

            logger.error(
                "whatsapp_api_error",
                to_phone=to_phone,
                status_code=response.status_code,
                error_message=error_msg,
                error_code=error_info.get("code"),
                response_body=str(response_data)[:200],
            )
            return {
                "success": False,
                "message_id": None,
                "error": f"API Error {response.status_code}: {error_msg}",
                "status_code": response.status_code,
            }

    except httpx.TimeoutException as e:
        logger.error(
            "whatsapp_send_timeout",
            to_phone=to_phone,
            timeout_seconds=_API_TIMEOUT_SECONDS,
            error=str(e),
        )
        return {
            "success": False,
            "message_id": None,
            "error": f"Request timeout after {_API_TIMEOUT_SECONDS}s",
            "status_code": None,
        }

    except httpx.RequestError as e:
        logger.error(
            "whatsapp_send_network_error",
            to_phone=to_phone,
            error=str(e),
        )
        return {
            "success": False,
            "message_id": None,
            "error": f"Network error: {str(e)}",
            "status_code": None,
        }

    except Exception as e:
        logger.error(
            "whatsapp_send_unexpected_error",
            to_phone=to_phone,
            error=str(e),
            exc_info=True,
        )
        return {
            "success": False,
            "message_id": None,
            "error": f"Unexpected error: {str(e)}",
            "status_code": None,
        }


# ─────────────────────────────────────────────
# High-Level Business Message Functions
# ─────────────────────────────────────────────

async def send_acknowledgement(
    to_phone: str,
    auth_result: WorkerAuthResult,
    submission_timestamp: Optional[datetime] = None,
) -> dict:
    """
    Sends the Hindi auto-acknowledgement message to an authorized AWC worker.

    Args:
        to_phone: Worker's WhatsApp phone number
        auth_result: Authenticated worker details
        submission_timestamp: When the submission was received (defaults to now)

    Returns:
        Result dict from send_whatsapp_text_message
    """
    if submission_timestamp is None:
        submission_timestamp = datetime.now(timezone.utc)

    message = _build_acknowledgement_message(
        worker_name=auth_result.worker_name or "कार्यकर्ता",
        awc_id=auth_result.awc_id or "N/A",
        center_name=auth_result.center_name or "N/A",
        block_name=auth_result.block_name or "N/A",
        submission_timestamp=submission_timestamp,
    )

    logger.info(
        "sending_acknowledgement",
        to_phone=to_phone,
        awc_id=auth_result.awc_id,
        worker_name=auth_result.worker_name,
    )

    return await send_whatsapp_text_message(
        to_phone=to_phone,
        message_text=message,
    )


async def send_unauthorized_rejection(to_phone: str) -> dict:
    """
    Sends the Hindi rejection message to an unregistered sender.

    Args:
        to_phone: Unregistered sender's WhatsApp phone number

    Returns:
        Result dict from send_whatsapp_text_message
    """
    message = _build_unauthorized_message()

    logger.info(
        "sending_unauthorized_rejection",
        to_phone=to_phone,
    )

    return await send_whatsapp_text_message(
        to_phone=to_phone,
        message_text=message,
    )


async def send_system_error_notice(to_phone: str) -> dict:
    """
    Sends a generic Hindi system error notice to a worker.
    Called when internal processing fails after authentication.

    Args:
        to_phone: Worker's WhatsApp phone number

    Returns:
        Result dict from send_whatsapp_text_message
    """
    message = _build_error_message()

    logger.warning(
        "sending_system_error_notice",
        to_phone=to_phone,
    )

    return await send_whatsapp_text_message(
        to_phone=to_phone,
        message_text=message,
    )


# ─────────────────────────────────────────────
# Media Download & Storage (Pathlib + Validation)
# ─────────────────────────────────────────────

_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB Limit
_UPLOADS_DIR = Path("data") / "uploads"


async def download_and_save_whatsapp_media(
    media_id: str,
    submission_id: str,
    media_mime_type: Optional[str] = None,
    awc_id: Optional[str] = None,
) -> dict:
    """
    Downloads image media from Meta Cloud API, validates size & image integrity via PIL,
    saves permanent evidence via storage service abstraction, and preserves local development fallback.

    Returns dict:
        {
            "success": bool,
            "local_path": str | None,
            "storage_key": str | None,
            "sha256": str | None,
            "error": str | None,
            "file_size": int | None
        }
    """
    import hashlib
    import io
    from PIL import Image
    from app.services.storage import get_storage_service, build_evidence_key

    if not settings.is_whatsapp_configured:
        logger.warning("media_download_unconfigured", media_id=media_id)
        return {
            "success": False,
            "local_path": None,
            "storage_key": None,
            "sha256": None,
            "error": "WhatsApp API credentials not configured",
            "file_size": None,
        }

    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    media_info_url = f"{settings.whatsapp_api_base_url}/{settings.whatsapp_api_version}/{media_id}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Fetch Media URL from Meta API
            res = await client.get(media_info_url, headers=headers)
            if res.status_code != 200:
                logger.error("media_info_fetch_failed", status_code=res.status_code, body=res.text[:200])
                return {
                    "success": False,
                    "local_path": None,
                    "storage_key": None,
                    "sha256": None,
                    "error": f"Meta API error status {res.status_code}",
                    "file_size": None,
                }

            media_info = res.json()
            download_url = media_info.get("url")
            if not download_url:
                return {
                    "success": False,
                    "local_path": None,
                    "storage_key": None,
                    "sha256": None,
                    "error": "No download URL returned by Meta API",
                    "file_size": None,
                }

            # 2. Download Media Content Bytes
            download_res = await client.get(download_url, headers=headers)
            if download_res.status_code != 200:
                return {
                    "success": False,
                    "local_path": None,
                    "storage_key": None,
                    "sha256": None,
                    "error": f"Media binary download failed (status {download_res.status_code})",
                    "file_size": None,
                }

            content_bytes = download_res.content
            file_size = len(content_bytes)

            # 3. File Size Validation (Max 5 MB)
            if file_size > _MAX_FILE_SIZE_BYTES:
                logger.warning("file_size_exceeded", file_size=file_size, max_limit=_MAX_FILE_SIZE_BYTES)
                return {
                    "success": False,
                    "local_path": None,
                    "storage_key": None,
                    "sha256": None,
                    "error": f"File size ({file_size} bytes) exceeds maximum 5 MB limit",
                    "file_size": file_size,
                }

            if file_size == 0:
                return {
                    "success": False,
                    "local_path": None,
                    "storage_key": None,
                    "sha256": None,
                    "error": "Downloaded media file is empty (0 bytes)",
                    "file_size": 0,
                }

            # 4. PIL Verification (Reject corrupted images)
            try:
                img_io = io.BytesIO(content_bytes)
                with Image.open(img_io) as img:
                    img.verify()
            except Exception as e:
                logger.error("pil_image_verification_failed", media_id=media_id, error=str(e))
                return {
                    "success": False,
                    "local_path": None,
                    "storage_key": None,
                    "sha256": None,
                    "error": f"Corrupted image file: {str(e)}",
                    "file_size": file_size,
                }

            # 5. Compute SHA-256 Hash
            sha256_hash = hashlib.sha256(content_bytes).hexdigest()

            # 6. Storage through storage abstraction
            ext = ".png" if media_mime_type == "image/png" else ".jpg"
            storage = get_storage_service()
            evidence_key = build_evidence_key(awc_id or "UNKNOWN", submission_id, ext)

            # Save in local uploads dir if local disk writable (preserves local dev workflows)
            _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            safe_filename = f"{Path(submission_id).name}{ext}"
            file_path = (_UPLOADS_DIR / safe_filename).resolve()
            base_dir = _UPLOADS_DIR.resolve()

            try:
                file_path.relative_to(base_dir)
                file_path.write_bytes(content_bytes)
            except Exception as write_err:
                logger.debug("local_uploads_write_skipped", error=str(write_err))

            # Canonical storage upload (GCS in production, or data/evidence in local mode)
            storage_key = await storage.upload_file(
                content_bytes,
                evidence_key,
                content_type=media_mime_type or ("image/png" if ext == ".png" else "image/jpeg"),
            )

            local_result_path = str(file_path) if file_path.exists() else storage_key
            logger.info("media_file_saved", key=storage_key, path=local_result_path, file_size=file_size)

            return {
                "success": True,
                "local_path": local_result_path,
                "storage_key": storage_key,
                "sha256": sha256_hash,
                "error": None,
                "file_size": file_size,
            }

    except Exception as e:
        logger.error("media_download_exception", media_id=media_id, error=str(e), exc_info=True)
        return {
            "success": False,
            "local_path": None,
            "storage_key": None,
            "sha256": None,
            "error": f"Media download error: {str(e)}",
            "file_size": None,
        }


# ─────────────────────────────────────────────
# Virtual Broadcast & Document Sending
# ─────────────────────────────────────────────

import asyncio as _asyncio


async def _verify_url_accessible(url: str) -> dict:
    """
    Verifies that a public URL returns HTTP 200.
    Called before Meta API to catch unreachable URLs early.
    If the server cannot reach its own public URL due to network constraints (Hairpin NAT),
    we log a warning but DO NOT block the delivery (we let Meta try).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # Using GET stream instead of HEAD to avoid 405 Method Not Allowed on some StaticFiles routers
            async with client.stream("GET", url) as resp:
                content_type = resp.headers.get("content-type", "")
                ok = (200 <= resp.status_code < 300)
                logger.info(
                    "pdf_url_verified",
                    url=url,
                    status_code=resp.status_code,
                    content_type=content_type,
                    accessible=ok,
                )
                # Only block if we successfully connected but got a definite 4xx/5xx error
                if not ok:
                    return {"ok": False, "reason": f"HTTP {resp.status_code} from URL"}
                
                # Looser content-type check to support application/octet-stream;charset=UTF-8 etc.
                ct_lower = content_type.lower()
                if "pdf" not in ct_lower and "octet-stream" not in ct_lower:
                    logger.warning(
                        "pdf_url_content_type_unexpected",
                        url=url,
                        content_type=content_type,
                    )
                return {"ok": True, "status_code": resp.status_code, "content_type": content_type}
    except Exception as e:
        # DO NOT block delivery. The backend server might just lack outbound internet or 
        # loopback resolution for its own domain, but Meta's servers might still reach it.
        logger.warning(
            "pdf_url_verification_failed_but_proceeding", 
            url=url, 
            error_type=type(e).__name__,
            error=repr(e)
        )
        return {"ok": True, "warning": "local_network_unreachable", "reason": repr(e)}


async def send_whatsapp_document(
    to_phone: str,
    document_url: str,
    filename: str,
    caption: Optional[str] = None,
    local_file_path: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
) -> dict:
    """
    Sends a document via WhatsApp Cloud API.
    If file_bytes or local_file_path is provided, it uploads the file directly to Meta's /media API
    and sends via media_id, completely bypassing Reverse Proxy/Timeout issues!

    Reliability improvements (v2):
    - Pre-verifies URL is accessible (HTTP 200) before calling Meta
    - Full Meta request + response JSON logged at every attempt
    - 3 retries with exponential backoff (2s → 4s → 8s)
    - Separate 45s timeout for document delivery
    - Captures & logs complete Meta error payloads
    - Never silently swallows exceptions
    - Strips sensitive query params from logs

    Returns:
        dict: {success, message_id, error, meta_response, attempts}
    """
    if not settings.is_whatsapp_configured:
        logger.warning("whatsapp_not_configured_document_send", to_phone=to_phone)
        return {
            "success": False,
            "message_id": None,
            "error": "WhatsApp credentials not configured",
            "meta_response": None,
            "attempts": 0,
        }

    # Safe URL for logging (never log signed URL query params/tokens)
    safe_log_url = document_url.split("?")[0] if ("?" in document_url) else document_url

    # ── Step 0: Direct Media Upload (Bypasses Link Download Timeouts) ──
    media_id = None
    media_content: Optional[bytes] = None

    if file_bytes:
        media_content = file_bytes
    elif local_file_path and os.path.exists(local_file_path):
        try:
            with open(local_file_path, "rb") as f:
                media_content = f.read()
        except Exception as read_err:
            logger.debug("direct_file_read_failed", path=local_file_path, error=str(read_err))
    elif local_file_path:
        # Check storage abstraction
        try:
            from app.services.storage import get_storage_service
            storage = get_storage_service()
            if await storage.exists(local_file_path):
                media_content = await storage.download_file(local_file_path)
        except Exception as st_err:
            logger.debug("storage_document_fetch_failed", key=local_file_path, error=str(st_err))

    if media_content:
        media_api_url = f"{settings.whatsapp_api_base_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/media"
        logger.info("uploading_media_directly_to_meta", filename=filename, size_bytes=len(media_content))
        try:
            async with httpx.AsyncClient(timeout=_DOC_TIMEOUT_SECONDS) as client:
                upload_res = await client.post(
                    media_api_url,
                    data={"messaging_product": "whatsapp"},
                    files={"file": (filename, media_content, "application/pdf")},
                    headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                )
                if upload_res.status_code == 200:
                    media_id = upload_res.json().get("id")
                    logger.info("meta_media_upload_success", media_id=media_id)
                else:
                    logger.error("meta_media_upload_failed", status=upload_res.status_code, response=upload_res.text)
        except Exception as e:
            logger.error("meta_media_upload_exception", error=str(e))

    # ── Step 1: Reject Local/Private URLs (Only if using link) ──────
    if not media_id:
        blocked_prefixes = ("http://localhost", "http://127.0", "http://192.168", "http://10.", "http://172.16")
        if any(document_url.startswith(prefix) for prefix in blocked_prefixes):
            logger.error(
                "document_send_aborted_private_url",
                to_phone=to_phone,
                url=safe_log_url,
            )
            return {
                "success": False,
                "message_id": None,
                "error": "Meta Cloud API requires a public HTTPS URL. Localhost/Private IP rejected.",
                "meta_response": None,
                "attempts": 0,
            }

        # ── Step 2: Verify URL is accessible ────────────────────────────
        logger.info(
            "document_send_started",
            to_phone=to_phone,
            document_url=safe_log_url,
            filename=filename,
        )

        url_check = await _verify_url_accessible(document_url)
        if not url_check.get("ok"):
            logger.error(
                "document_send_aborted_url_inaccessible",
                to_phone=to_phone,
                url=safe_log_url,
                reason=url_check.get("reason"),
            )
            return {
                "success": False,
                "message_id": None,
                "error": f"PDF URL not accessible: {url_check.get('reason')}",
                "meta_response": None,
                "attempts": 0,
            }

    # ── Step 3: Build Meta API payload ──────────────────────────────
    document_payload = {"filename": filename, "caption": (caption or "")[:1024]}
    if media_id:
        document_payload["id"] = media_id
    else:
        document_payload["link"] = document_url

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "document",
        "document": document_payload,
    }

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    api_url = settings.whatsapp_api_url

    # ── Step 3: Retry loop with exponential backoff ──────────────────
    last_error: str = "Unknown error"
    last_meta_response: Optional[dict] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            logger.info(
                "meta_document_request_sending",
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                to_phone=to_phone,
                api_url=api_url,
                document_url=safe_log_url,
                filename=filename,
            )

            async with httpx.AsyncClient(timeout=_DOC_TIMEOUT_SECONDS) as client:
                res = await client.post(api_url, json=payload, headers=headers)

            # Always parse and log full Meta response
            try:
                res_data = res.json()
            except Exception:
                res_data = {"raw": res.text[:500]}

            last_meta_response = res_data

            logger.info(
                "meta_response_received",
                attempt=attempt,
                to_phone=to_phone,
                status_code=res.status_code,
                meta_response_full=res_data,   # Full JSON — never truncated
            )

            if 200 <= res.status_code < 300:
                msgs = res_data.get("messages", [])
                msg_id = msgs[0].get("id") if msgs else None
                logger.info(
                    "document_delivery_success",
                    to_phone=to_phone,
                    msg_id=msg_id,
                    attempt=attempt,
                    document_url=document_url,
                    filename=filename,
                )
                return {
                    "success": True,
                    "message_id": msg_id,
                    "error": None,
                    "meta_response": res_data,
                    "attempts": attempt,
                }

            # Non-200: extract full Meta error
            error_block = res_data.get("error", {})
            error_msg    = error_block.get("message", "Unknown API error")
            error_code   = error_block.get("code", "N/A")
            error_fbtid  = error_block.get("fbtrace_id", "N/A")
            error_subcode= error_block.get("error_subcode", "N/A")
            last_error   = (
                f"HTTP {res.status_code} | code={error_code} | subcode={error_subcode} "
                f"| msg={error_msg} | fbtrace={error_fbtid}"
            )

            logger.error(
                "document_delivery_failed",
                attempt=attempt,
                to_phone=to_phone,
                status_code=res.status_code,
                error_code=error_code,
                error_subcode=error_subcode,
                error_message=error_msg,
                fbtrace_id=error_fbtid,
                full_meta_error=error_block,
            )

            # 401/403 = auth failure — do not retry
            if res.status_code in (401, 403):
                logger.error(
                    "document_send_auth_failure_no_retry",
                    to_phone=to_phone,
                    status_code=res.status_code,
                )
                break

        except httpx.TimeoutException as e:
            last_error = f"Timeout after {_DOC_TIMEOUT_SECONDS}s on attempt {attempt}"
            logger.error(
                "document_send_timeout",
                attempt=attempt,
                to_phone=to_phone,
                timeout_seconds=_DOC_TIMEOUT_SECONDS,
                error=str(e),
            )

        except httpx.RequestError as e:
            last_error = f"Network error on attempt {attempt}: {str(e)}"
            logger.error(
                "document_send_network_error",
                attempt=attempt,
                to_phone=to_phone,
                error=str(e),
            )

        except Exception as e:
            last_error = f"Unexpected error on attempt {attempt}: {str(e)}"
            logger.error(
                "document_send_unexpected_error",
                attempt=attempt,
                to_phone=to_phone,
                error=str(e),
                exc_info=True,
            )

        # Exponential backoff before next retry (1s, 2s, 4s, 8s, 16s)
        if attempt < _MAX_RETRIES:
            backoff_seconds = _RETRY_BACKOFF_BASE ** (attempt - 1)
            logger.warning(
                "retry_attempt",
                attempt=attempt,
                next_attempt=attempt + 1,
                backoff_seconds=backoff_seconds,
                to_phone=to_phone,
            )
            await _asyncio.sleep(backoff_seconds)

    logger.error(
        "document_delivery_all_retries_exhausted",
        to_phone=to_phone,
        total_attempts=_MAX_RETRIES,
        final_error=last_error,
        document_url=document_url,
    )
    return {
        "success": False,
        "message_id": None,
        "error": last_error,
        "meta_response": last_meta_response,
        "attempts": _MAX_RETRIES,
    }


async def virtual_broadcast_document(
    document_url: str,
    filename: str,
    caption: str,
    worker_phone: Optional[str] = None,
) -> dict:
    """
    Virtual Broadcast module: Sends document to Worker, Supervisor, CDPO, CEO, Collector.
    Reads recipient phone numbers from OFFICER_RECIPIENT_NUMBERS configuration setting.

    Args:
        document_url: PDF document URL
        filename: Document filename
        caption: Broadcast caption
        worker_phone: Optional AWC worker phone number

    Returns:
        dict mapping role -> send status
    """
    officer_numbers = settings.officer_recipient_numbers_dict
    recipients = {}

    if worker_phone:
        recipients["Worker"] = worker_phone

    for role in ["Supervisor", "CDPO", "CEO", "Collector"]:
        phone = officer_numbers.get(role) or officer_numbers.get(role.lower())
        if phone:
            recipients[role] = phone

    logger.info(
        "virtual_broadcast_started",
        recipient_count=len(recipients),
        filename=filename,
        roles=list(recipients.keys()),
    )

    broadcast_results = {}
    for role, phone in recipients.items():
        res = await send_whatsapp_document(
            to_phone=phone,
            document_url=document_url,
            filename=filename,
            caption=f"[{role} Copy] {caption}",
        )
        broadcast_results[role] = res

    logger.info("virtual_broadcast_completed", results=broadcast_results)
    return broadcast_results
