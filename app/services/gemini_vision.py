# app/services/gemini_vision.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Production-Grade Multi-Provider Vision AI Analysis Service
# Providers: Groq Vision (llama-3.2-11b-vision-preview REST) + Gemini Vision
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
from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError
from PIL import Image
from pydantic import BaseModel, ValidationError

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


class GeminiVisionService:
    def __init__(self):
        load_dotenv()

        # Read GEMINI_API_KEY and GROQ_API_KEY
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")

        if not self.api_key or not self.groq_api_key:
            try:
                from app.config import settings
                if not self.api_key:
                    self.api_key = getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY")
                if not self.groq_api_key:
                    self.groq_api_key = getattr(settings, "groq_api_key", None) or os.getenv("GROQ_API_KEY")
            except Exception as ex:
                logger.debug("app_config_settings_fallback_notice", error=str(ex))

        # Initialize GenAI Client if Gemini key available
        self.client = None
        if self.api_key and self.api_key.strip():
            try:
                custom_http_client = httpx.Client(
                    http2=False,
                    trust_env=False,
                    timeout=httpx.Timeout(30.0, connect=10.0),
                    verify=True,
                )
                self.client = genai.Client(
                    api_key=self.api_key.strip(),
                    http_options=types.HttpOptions(httpx_client=custom_http_client)
                )
                logger.info("gemini_client_initialized", mode="http_1_1")
            except Exception as e:
                logger.error("gemini_client_init_failed", error=str(e))
                self.client = None

        if self.groq_api_key and self.groq_api_key.strip():
            logger.info("groq_provider_initialized", status="ready")

        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.groq_model = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

    def _call_groq_vision_rest(self, image_bytes: bytes, prompt: str) -> dict:
        """
        Calls Groq Cloud Vision API via standard requests REST endpoint.
        Fast, reliable, and bypasses Windows httpx issues.
        """
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not groq_key:
            try:
                from app.config import settings
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
                "You must respond in valid JSON format only. "
                "All 'remarks' text MUST be written strictly in pure Devanagari Hindi script (शुद्ध देवनागरी हिंदी). "
                "NEVER write in Roman Hindi or Hinglish. "
                "Do not output any markdown code blocks or thinking text before or after the JSON."
            )

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
                "response_format": {"type": "json_object"}
            }
            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=15.0
            )

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

    def verify_anganwadi_photo(self, image_bytes: bytes, exif_info: Optional[dict] = None, max_retries: int = 2) -> dict:
        """
        Processes Anganwadi site photo and returns strictly validated verification results.
        Tries Groq Cloud Vision REST API first (if GROQ_API_KEY configured), then Gemini Vision.
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

        strict_prompt = f"""
        You are an official AI Audit Assistant for District Shahdol Anganwadi Digital Decision Support System (DSS).
        Analyze this photograph carefully and evaluate the scene directly observable.
        {exif_prompt_block}

        CRITICAL AUDIT RULES:
        1. Report ONLY directly observable facts. DO NOT guess, estimate, or infer facts not clearly visible.
        2. Evaluate whether visual lighting (daylight vs night) matches the reported timestamp.
        3. Check for any timestamp/scene mismatch, screen re-capture, or photo tampering indications.
        4. 'remarks' MUST BE WRITTEN EXCLUSIVELY IN PURE DEVANAGARI HINDI SCRIPT (शुद्ध देवनागरी हिंदी).
           - DO NOT use Roman Hindi / Hinglish (e.g. NEVER write "Is pratima mein...", "Yeh photo...").
           - Use official administrative tone suitable for District Collector, Zila Panchayat CEO, and CDPO Supervisors.

        EXECUTIVE REMARKS GUIDELINES:
        - If NOT an Anganwadi scene (e.g. personal selfie, unrelated room/object):
          Write: "यह फोटो आंगनवाड़ी गतिविधि की प्रतीत नहीं होती। बच्चे या भोजन वितरण दिखाई नहीं दे रहा। कृपया केंद्र की वास्तविक उपस्थिति फोटो भेजें।"
        - If Anganwadi scene with children and meal:
          Write: "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।"
        - If Anganwadi scene with worker/room but no children/meal:
          Write: "आंगनवाड़ी केंद्र का परिसर दिखाई दे रहा है, परंतु बच्चों की उपस्थिति या भोजन वितरण का दृश्य स्पष्ट नहीं है।"

        - For 'visible_children_count', return an exact integer ONLY if clearly countable. Otherwise return null.
        - For 'confidence_score', return an integer percentage between 50 and 99.

        Return strictly valid JSON matching this schema:
        {{
          "schema_version": "1.0",
          "is_valid_anganwadi_scene": true/false/null,
          "children_visible": true/false/null,
          "visible_children_count": integer or null,
          "worker_present": true/false/null,
          "meal_visible": true/false/null,
          "environment_type": "indoor" / "outdoor" / "unknown",
          "image_quality": "CLEAR" / "BLURRY" / "DARK" / "POOR",
          "evidence_consistency": "CONSISTENT" / "SUSPICIOUS" / "INCONSISTENT",
          "confidence_score": 95,
          "remarks": "केवल शुद्ध देवनागरी हिंदी में शासकीय एवं आधिकारिक विवरण"
        }}
        """

        # ── 1. TRY GROQ VISION REST PROVIDER FIRST (FASTEST) ──────────────
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if groq_key and groq_key.strip():
            logger.info("trying_groq_vision_rest_api")
            groq_res = self._call_groq_vision_rest(image_bytes, strict_prompt)
            if groq_res.get("success"):
                try:
                    raw_dict = json.loads(self._clean_json_markdown(groq_res["raw_text"]))
                    validated_data = VisionResponse.model_validate(raw_dict)
                    result_dict = validated_data.model_dump()
                    result_dict["status"] = "SUCCESS"
                    result_dict["provider"] = "GROQ_VISION"
                    result_dict["remarks"] = self._synthesize_executive_remarks(validated_data)
                    result_dict["suspicious_flag"] = self._compute_suspicious_flag(validated_data)
                    logger.info("groq_vision_verification_successful", provider="GROQ_VISION")
                    return result_dict
                except Exception as parse_err:
                    logger.warning(
                        "groq_json_parsing_failed",
                        error=str(parse_err),
                        raw=groq_res.get("raw_text")
                    )
            else:
                logger.warning(
                    "groq_vision_failed_proceeding_to_gemini",
                    reason=groq_res.get("reason")
                )

        # ── 2. TRY GEMINI VISION PROVIDER ─────────────────────────────────
        if not self.client:
            load_dotenv()
            self.api_key = os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                try:
                    from app.config import settings
                    self.api_key = getattr(settings, "gemini_api_key", None)
                except Exception:
                    pass

            if self.api_key and self.api_key.strip():
                try:
                    custom_http_client = httpx.Client(
                        http2=False,
                        trust_env=False,
                        timeout=httpx.Timeout(30.0, connect=10.0),
                        verify=True,
                    )
                    self.client = genai.Client(
                        api_key=self.api_key.strip(),
                        http_options=types.HttpOptions(httpx_client=custom_http_client)
                    )
                except Exception as ex:
                    logger.error("dynamic_genai_client_init_failed", error=str(ex))

        if self.client:
            for attempt in range(max_retries + 1):
                try:
                    logger.info("processing_gemini_vision_verification", attempt=attempt + 1)
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=[image, strict_prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.0,
                            http_options=types.HttpOptions(timeout=60.0)
                        )
                    )

                    clean_json_str = self._clean_json_markdown(response.text)
                    raw_dict = json.loads(clean_json_str)
                    validated_data = VisionResponse.model_validate(raw_dict)
                    result_dict = validated_data.model_dump()
                    result_dict["status"] = "SUCCESS"
                    result_dict["provider"] = "GEMINI_VISION"
                    result_dict["remarks"] = self._synthesize_executive_remarks(validated_data)
                    result_dict["suspicious_flag"] = self._compute_suspicious_flag(validated_data)
                    logger.info("gemini_vision_verification_successful", provider="GEMINI_VISION")
                    return result_dict

                except ValidationError as val_err:
                    logger.error("pydantic_validation_error", error=str(val_err))
                    return {
                        "status": "SCHEMA_VALIDATION_FAILED",
                        "reason": f"AI response did not match expected Pydantic schema: {val_err}",
                        "raw_response": response.text if 'response' in locals() else None,
                        "fallback": "Manual Review Required"
                    }

                except (httpx.ConnectTimeout, httpx.TimeoutException) as timeout_err:
                    logger.warning("gemini_httpx_timeout", attempt=attempt + 1, error=str(timeout_err))
                    if attempt < max_retries:
                        time.sleep(2)
                        continue
                    break

                except ClientError as ce:
                    logger.warning("gemini_client_error", attempt=attempt + 1, error=str(ce))
                    if attempt < max_retries:
                        time.sleep(2)
                        continue
                    break

                except Exception as gen_err:
                    logger.exception("gemini_verify_exception", error=str(gen_err))
                    break

        return {
            "status": "VISION_UNAVAILABLE",
            "reason": "Vision AI Providers (Groq/Gemini) unavailable or rate-limited.",
            "fallback": "OpenCV or Manual Verification Required"
        }

    def _clean_json_markdown(self, text: str) -> str:
        """Strips markdown syntax wrapper if present."""
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return clean.strip()

    def _synthesize_executive_remarks(self, data: VisionResponse) -> str:
        """
        Synthesizes 100% deterministic, official administrative Devanagari Hindi remarks
        from raw visual facts provided by AI providers (Groq/Gemini).
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
vision_service = GeminiVisionService()
