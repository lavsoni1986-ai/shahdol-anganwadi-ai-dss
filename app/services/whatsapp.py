# app/services/whatsapp.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Meta WhatsApp Cloud API — Message Sending Service
# Handles: Auto-acknowledgements, Unauthorized rejection messages,
#          and future notification sending.
# Official API Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/messages
# =====================================================================

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo  # Python 3.9+ stdlib

import httpx

from app.config import settings
from app.schemas import WorkerAuthResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# IST timezone for displaying local time in Hindi messages
IST = ZoneInfo("Asia/Kolkata")

# HTTP timeout for WhatsApp API calls
_API_TIMEOUT_SECONDS = 10.0


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
