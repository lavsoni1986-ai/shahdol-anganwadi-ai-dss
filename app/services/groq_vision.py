# app/services/groq_vision.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Production-Grade Vision AI Analysis Service
# Provider: Groq Vision (llama-3.2-11b-vision-preview REST)
# IPv4 Socket Override & Standard Requests REST Transport
# Fixed: Uses app.utils.logger (structlog) for consistent structured logging
# =====================================================================

import socket

# Global IPv4 socket resolution override for Windows SSL handshake stability
_original_getaddrinfo = socket.getaddrinfo

def _ipv4_only_getaddrinfo(*args, **kwargs):
    responses = _original_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]

socket.getaddrinfo = _ipv4_only_getaddrinfo

import base64
import io
import json
import logging
import os
import time
from typing import Literal, Optional

import httpx
import requests
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.utils.logger import get_logger

# Explicitly load .env environment variables at module load time
load_dotenv()

# Application-wide structured Logger
logger = get_logger(__name__)


# Strict Pydantic Response Model
class VisionResponse(BaseModel):
    schema_version: str = "1.0"  # Schema Versioning
    is_valid_anganwadi_scene: Optional[bool] = None
    children_visible: Optional[bool] = None
    visible_children_count: Optional[int] = None  # Exact count
    worker_present: Optional[bool] = None
    meal_visible: Optional[bool] = None
    environment_type: Literal["indoor", "outdoor", "unknown"] = "unknown"
    image_quality: Literal["CLEAR", "BLURRY", "DARK", "POOR"] = "CLEAR"
    remarks: Optional[str] = None  # Output in Hindi


class GroqVisionService:
    def __init__(self):
        load_dotenv()

        # Read GROQ_API_KEY
        self.groq_api_key = os.getenv("GROQ_API_KEY")

        if not self.groq_api_key:
            try:
                self.groq_api_key = getattr(settings, "groq_api_key", None) or os.getenv("GROQ_API_KEY")
            except Exception as ex:
                logger.debug("app_config_settings_fallback_notice", error=str(ex))

        if self.groq_api_key and self.groq_api_key.strip():
            logger.info("groq_provider_initialized", status="ready")

        self.groq_model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

    def _call_groq_vision_rest(self, image_bytes: bytes, prompt: str) -> dict:
        """
        Calls Groq Cloud Vision API via standard requests REST endpoint.
        Fast, reliable, and bypasses Windows httpx issues.
        """
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not groq_key:
            try:
                groq_key = getattr(settings, "groq_api_key", None)
            except Exception:
                pass

        if not groq_key or not groq_key.strip():
            logger.warning("groq_request_skipped", reason="GROQ_API_KEY missing or empty")
            return {"success": False, "reason": "GROQ_API_KEY missing"}

        try:
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            logger.info(
                "groq_request_started",
                model=self.groq_model,
                endpoint=endpoint,
                image_bytes_len=len(image_bytes),
            )

            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            headers = {
                "Authorization": f"Bearer {groq_key.strip()}",
                "Content-Type": "application/json",
            }
            system_prompt = (
                "You are an official AI Audit Assistant for District Shahdol Anganwadi DSS. "
                "Respond ONLY with a compact JSON matching the required schema. "
                "'remarks' must be pure Devanagari Hindi. "
                "No markdown, no explanations, no <think> tags."
            )
            # NOTE: response_format=json_object is intentionally omitted.
            # qwen/qwen3.6-27b always rejects it with HTTP 400 json_validate_failed,
            # which previously caused a second API call on every request (doubling token usage).
            payload = {
                "model": self.groq_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.0,
                # 4096 tokens: live WhatsApp images trigger longer qwen reasoning than the
                # simple test image (complex scene: children, food, GPS, camera context).
                # With full strict_prompt + EXIF block, prompt is ~1400–1500 tokens.
                # qwen thinking on real Anganwadi images: ~2100–2200 tokens.
                # 2048 cap was hit mid-thinking on live images → </think> absent → JSON missed.
                # Budget: ~1500 prompt + 4096 completion = ~5596 tokens (< 8000 TPM limit).
                "max_tokens": 4096,
            }

            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=45.0
            )
            # Handle rate limiting (429) with Retry-After header
            if resp.status_code == 429:
                retry_after = resp.headers.get('Retry-After')
                wait_seconds = float(retry_after) if retry_after and retry_after.replace('.', '', 1).isdigit() else 15.0
                logger.warning("groq_rate_limit_detected", retry_after_seconds=wait_seconds, attempt=0)
                time.sleep(wait_seconds + 2)  # safety margin above retry-after
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=45.0)
                logger.info("groq_retry_attempt", status_code=resp.status_code)


            logger.info(
                "groq_response",
                status_code=resp.status_code,
                body=resp.text[:500]
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return {"success": True, "raw_text": content}
            else:
                logger.warning(
                    "groq_response_error",
                    status_code=resp.status_code,
                    response=resp.text[:300]
                )
                return {"success": False, "reason": f"Groq HTTP {resp.status_code}: {resp.text[:150]}"}
        except Exception as err:
            logger.exception("groq_exception", error=str(err))
            return {"success": False, "reason": f"Groq REST Exception: {str(err)}"}

    def _call_groq_followup_for_json(self, reasoning_text: str) -> dict:
        """
        Cheap text-only follow-up call to extract JSON from a qwen reasoning response.
        Called when the main vision call returns <think> blocks without a final JSON.
        Does NOT send the image again — only the trimmed reasoning snippet.
        response_format is intentionally omitted (qwen rejects it with HTTP 400).
        """
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not groq_key or not groq_key.strip():
            return {"success": False, "reason": "GROQ_API_KEY missing for followup"}
        try:
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            followup_headers = {
                "Authorization": f"Bearer {groq_key.strip()}",
                "Content-Type": "application/json",
            }
            # Trim reasoning snippet to save token budget
            reasoning_snippet = reasoning_text[:1500] if len(reasoning_text) > 1500 else reasoning_text
            payload = {
                "model": self.groq_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an official AI Audit Assistant. "
                            "Output ONLY valid JSON matching the schema. "
                            "Do NOT output any thinking tags, <think> blocks, or commentary."
                        )
                    },
                    {
                        "role": "user",
                        "content": "Analyze the image and return JSON format."
                    },
                    {
                        "role": "assistant",
                        "content": reasoning_snippet
                    },
                    {
                        "role": "user",
                        "content": (
                            "Based on your analysis above, respond NOW with ONLY the valid JSON object. "
                            "Start immediately with '{'. No thinking tags, no preamble."
                        )
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 512,
            }
            resp = requests.post(endpoint, headers=followup_headers, json=payload, timeout=30.0)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                logger.info("groq_followup_success")
                return {"success": True, "raw_text": content}
            elif resp.status_code == 429:
                retry_after = resp.headers.get('Retry-After')
                wait_seconds = float(retry_after) if retry_after and retry_after.replace('.', '', 1).isdigit() else 15.0
                logger.warning("groq_followup_rate_limit", retry_after_seconds=wait_seconds)
                time.sleep(wait_seconds + 2)
                resp2 = requests.post(endpoint, headers=followup_headers, json=payload, timeout=30.0)
                if resp2.status_code == 200:
                    content2 = resp2.json()["choices"][0]["message"]["content"]
                    return {"success": True, "raw_text": content2}
                return {"success": False, "reason": f"Followup rate-limited, retry HTTP {resp2.status_code}"}
            else:
                logger.warning("groq_followup_failed", status_code=resp.status_code, body=resp.text[:200])
                return {"success": False, "reason": f"Followup HTTP {resp.status_code}"}
        except Exception as e:
            logger.exception("groq_followup_exception", error=str(e))
            return {"success": False, "reason": str(e)}

    def verify_anganwadi_photo(self, image_bytes: bytes, exif_info: Optional[dict] = None, yolo_results: Optional[dict] = None, max_retries: int = 2) -> dict:
        """
        Processes Anganwadi site photo and returns strictly validated verification results.
        Tries Groq Cloud Vision REST API.
        Incorporates EXIF metadata (Device Time, GPS, Camera) for AI cross-validation.
        """
        # Validate image integrity and corrupt files
        try:
            image_stream = io.BytesIO(image_bytes)
            image = Image.open(image_stream)
            image.verify()  # Validates image format and header without decoding fully
            image = Image.open(io.BytesIO(image_bytes))  # Re-open for actual processing
        except Exception as img_err:
            logger.error("corrupt_or_invalid_image_file", error=str(img_err))
            return {
                "status": "INVALID_IMAGE",
                "reason": f"Corrupt or unreadable image file: {img_err}",
                "fallback": "Manual Review Required"
            }

        exif_prompt_block = ""
        if exif_info and isinstance(exif_info, dict):
            device_ts = exif_info.get("device_timestamp") or "Unavailable"
            camera = f"{exif_info.get('camera_make', '')} {exif_info.get('camera_model', '')}".strip() or "Unavailable"
            lat = exif_info.get("gps_latitude")
            lon = exif_info.get("gps_longitude")
            gps_str = f"Lat {lat}, Lon {lon}" if (lat and lon) else "Unavailable (No EXIF GPS)"

            exif_prompt_block = f"""
            SUBMITTED IMAGE EXIF METADATA FOR EVIDENCE CROSS-CHECK:
            - Extracted Device Timestamp: {device_ts}
            - Camera / Device Model: {camera}
            - EXIF GPS Coordinates: {gps_str}
            """

        yolo_prompt_block = ""
        if yolo_results and isinstance(yolo_results, dict):
            y_child = yolo_results.get("children_count", 0)
            y_worker = yolo_results.get("worker_count", 0)
            yolo_prompt_block = f"""
            AUTHORITATIVE LOCAL YOLO11m DETECTION RESULT:
            - Detected Children Count: {y_child} (AUTHORITATIVE - DO NOT RECOUNT OR ENUMERATE)
            - Detected Worker Count: {y_worker}
            """

        strict_prompt = f"""
        You are an official AI Audit Assistant for District Shahdol Anganwadi Digital Decision Support System (DSS).
        Act EXCLUSIVELY as a high-level semantic verifier for overall scene context, meal presence, and photo authenticity.
        {yolo_prompt_block}
        {exif_prompt_block}

        CRITICAL AUDIT RULES:
        1. TRUST YOLO DETECTION: YOLO11m is the authoritative child counting engine. NEVER recount children, never estimate counts, and NEVER describe individual children (clothing, seating, or positions).
        2. NO STEP-BY-STEP THINKING / NO ENUMERATION: Do NOT write chain-of-thought, do NOT list objects one by one, and do NOT output reasoning commentary.
        3. VERIFICATION SCOPE: Verify only if the scene represents an Anganwadi environment, if meal distribution is visible, and if worker is present.
        4. REMARKS FORMAT: 'remarks' MUST be EXACTLY one short sentence in PURE DEVANAGARI HINDI SCRIPT (शुद्ध देवनागरी हिंदी). No Hinglish, no Roman script.
        5. For 'visible_children_count', ALWAYS return null (handled by local YOLO).

        Return strictly valid JSON matching this schema:
        {{
          "schema_version": "1.0",
          "is_valid_anganwadi_scene": true/false/null,
          "children_visible": true/false/null,
          "visible_children_count": null,
          "worker_present": true/false/null,
          "meal_visible": true/false/null,
          "environment_type": "indoor" / "outdoor" / "unknown",
          "image_quality": "CLEAR" / "BLURRY" / "DARK" / "POOR",
          "evidence_consistency": "CONSISTENT" / "SUSPICIOUS" / "INCONSISTENT",
          "confidence_score": 95,
          "remarks": "केवल शुद्ध देवनागरी हिंदी में शासकीय एवं आधिकारिक विवरण"
        }}
        """

        # ── 1. TRY GROQ VISION REST PROVIDER ──────────────
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if groq_key and groq_key.strip():
            logger.info("trying_groq_vision_rest_api")
            groq_res = self._call_groq_vision_rest(image_bytes, strict_prompt)
            if groq_res.get("success"):
                raw_text = groq_res["raw_text"]
                raw_dict = self._extract_json_dict(raw_text)
                # Follow-up should NOT be triggered after the max_tokens=4096 fix.
                # If it fires, it means the real image is still consuming the full 4096-token
                # completion budget without producing JSON — a genuine capacity issue.
                if not raw_dict and ("<think>" in raw_text or "think" in raw_text):
                    logger.warning(
                        "groq_followup_triggered_UNEXPECTED",
                        reason="Primary 4096-token response contained <think> but no parseable JSON.",
                        raw_len=len(raw_text),
                        hint="Consider increasing max_tokens further or shortening the prompt.",
                    )
                    followup_res = self._call_groq_followup_for_json(raw_text)
                    if followup_res.get("success"):
                        raw_text = followup_res["raw_text"]
                        raw_dict = self._extract_json_dict(raw_text)
                if raw_dict:
                    try:
                        validated_data = VisionResponse.model_validate(raw_dict)
                        result_dict = validated_data.model_dump()
                        # Add required fields for downstream consumers
                        result_dict["status"] = "SUCCESS"
                        result_dict["provider"] = "GROQ_VISION"
                        result_dict["remarks"] = self._synthesize_executive_remarks(validated_data)
                        result_dict["suspicious_flag"] = self._compute_suspicious_flag(validated_data)
                        logger.info("groq_vision_verification_successful", provider="GROQ_VISION")
                        return result_dict
                    except ValidationError as val_err:
                        logger.error("pydantic_validation_error", error=str(val_err))
                        return {
                            "status": "SCHEMA_VALIDATION_FAILED",
                            "reason": f"AI response did not match expected Pydantic schema: {val_err}",
                            "raw_response": raw_text,
                            "fallback": "Manual Review Required",
                        }
                else:
                    logger.warning("groq_json_parsing_failed", raw=raw_text)

            else:
                logger.warning(
                    "groq_vision_failed",
                    reason=groq_res.get("reason")
                )

        return {
            "status": "VISION_UNAVAILABLE",
            "reason": "Vision AI Provider (Groq) unavailable or rate-limited.",
            "fallback": "OpenCV or Manual Verification Required"
        }

    def _extract_json_dict(self, text: str) -> dict:
        """Extracts the largest valid JSON object from the text.
        First strips any <think>...</think> blocks (qwen reasoning output)
        before searching, so reasoning content cannot shadow the final JSON.
        Falls back to searching the original text if no JSON found after stripping.
        """
        import re
        # 1. Strip <think>...</think> blocks (qwen3 reasoning output).
        # The pattern handles both closed (</think> present) and unclosed blocks (truncated
        # at max_tokens cap). (?:</think>|$) matches closing tag OR end-of-string.
        # IMPORTANT: Defensive hardening only — if the model was truncated BEFORE generating
        # any JSON, text_stripped will be empty and extraction will still correctly return {}.
        text_stripped = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL).strip()

        def _search_json(source: str) -> dict:
            best_dict = {}
            for i in range(len(source)):
                if source[i] == '{':
                    nesting = 0
                    in_string = False
                    escape = False
                    for j in range(i, len(source)):
                        char = source[j]
                        if escape:
                            escape = False
                            continue
                        if char == '\\':
                            escape = True
                            continue
                        if char == '"':
                            in_string = not in_string
                            continue
                        if not in_string:
                            if char == '{':
                                nesting += 1
                            elif char == '}':
                                nesting -= 1
                                if nesting == 0:
                                    candidate = source[i:j+1]
                                    try:
                                        parsed = json.loads(candidate)
                                        if isinstance(parsed, dict):
                                            if "schema_version" in parsed and "is_valid_anganwadi_scene" in parsed:
                                                return parsed  # Best match found
                                            best_dict.update(parsed)  # Fallback
                                    except Exception:
                                        pass
                                    break
            return best_dict

        # Try stripped text first (preferred — avoids think-block false matches)
        result = _search_json(text_stripped)
        if result:
            return result
        # Fallback: search original text (handles edge case where strip removed too much)
        return _search_json(text)

    def _synthesize_executive_remarks(self, data: VisionResponse) -> str:
        """
        Synthesizes 100% deterministic, official administrative Devanagari Hindi remarks
        from raw visual facts provided by AI providers (Groq).
        Ensures consistent government reporting across all models.
        """
        # 1. Invalid Anganwadi Scene (Selfie, unrelated room/object)
        if data.is_valid_anganwadi_scene is False:
            return "यह फोटो आंगनवाड़ी गतिविधि की प्रतीत नहीं होती। बच्चे या भोजन वितरण दिखाई नहीं दे रहा। कृपया केंद्र की वास्तविक उपस्थिति फोटो भेजें।"

        count = data.visible_children_count
        meal = data.meal_visible

        # 2. Valid Scene with Countable Children and Meal
        if data.children_visible and count is not None and count > 0:
            if meal is True:
                return f"आंगनवाड़ी केंद्र में लगभग {count} बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।"
            elif meal is False:
                return f"आंगनवाड़ी केंद्र में लगभग {count} बच्चे उपस्थित हैं, परंतु भोजन वितरण का दृश्य स्पष्ट नहीं है।"
            else:
                return f"आंगनवाड़ी केंद्र में लगभग {count} बच्चे उपस्थित दिखाई दे रहे हैं।"

        # 3. Children Visible but count not clear
        if data.children_visible:
            if meal is True:
                return "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।"
            else:
                return "आंगनवाड़ी केंद्र में बच्चे उपस्थित दिखाई दे रहे हैं।"

        # 4. Valid Scene / Worker present but no children
        if data.is_valid_anganwadi_scene or data.worker_present:
            return "आंगनवाड़ी केंद्र का परिसर दिखाई दे रहा है, परंतु बच्चों की उपस्थिति या भोजन वितरण का दृश्य स्पष्ट नहीं है।"

        # 5. Fallback to raw remarks or general statement
        if data.remarks and len(data.remarks.strip()) > 5:
            return data.remarks.strip()

        return "आंगनवाड़ी उपस्थिति सत्यापन प्रक्रिया पूर्ण हुई।"

    def _compute_suspicious_flag(self, data: VisionResponse) -> bool:
        """
        Business Logic for Suspicious Determination (Kept out of LLM).
        """
        if data.image_quality in ["BLURRY", "DARK", "POOR"]:
            return True
        if data.is_valid_anganwadi_scene is False:
            return True
        return False


# Singleton Instance
vision_service = GroqVisionService()
