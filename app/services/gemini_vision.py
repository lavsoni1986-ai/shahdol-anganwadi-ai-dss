# app/services/gemini_vision.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Gemini Vision Provider — official Google Gen AI Python SDK
#
# Mirrors the GroqVisionService interface so the AI pipeline can route
# to either provider without changing downstream logic.
# Provider: Gemini via GEMINI_MODEL (default gemini-2.5-flash)
# API key: GEMINI_API_KEY (read from config/.env — never hardcoded, never logged)
# =====================================================================

import io
import json

from PIL import Image
from pydantic import ValidationError

from app.config import settings
from app.utils.logger import get_logger
from app.services.groq_vision import VisionResponse

logger = get_logger(__name__)


class GeminiVisionService:
    """Gemini (Google Gen AI) vision verification provider.

    Exposes the same `verify_anganwadi_photo()` contract as GroqVisionService:
        verify_anganwadi_photo(image_bytes, exif_info=None, yolo_results=None) -> dict
    """

    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self._client = None

    # ─────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────

    def _get_client(self):
        """Lazily builds the google-genai client. Never logs the API key."""
        if self._client is None:
            if not self.api_key or not self.api_key.strip():
                raise RuntimeError("GEMINI_API_KEY is not configured")
            from google import genai

            self._client = genai.Client(api_key=self.api_key.strip())
        return self._client

    @staticmethod
    def _detect_mime_type(image_bytes: bytes) -> str:
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if image_bytes[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        return "image/jpeg"

    def _build_prompt(self, exif_info, yolo_results) -> str:
        """Builds the Gemini prompt preserving the existing Groq verification intent."""
        exif_prompt_block = ""
        if exif_info and isinstance(exif_info, dict):
            device_ts = exif_info.get("device_timestamp") or "Unavailable"
            camera = (
                f"{exif_info.get('camera_make', '')} {exif_info.get('camera_model', '')}".strip()
                or "Unavailable"
            )
            lat = exif_info.get("gps_latitude")
            lon = exif_info.get("gps_longitude")
            gps_str = f"Lat {lat}, Lon {lon}" if (lat and lon) else "Unavailable (No EXIF GPS)"
            exif_prompt_block = (
                "\nSUBMITTED IMAGE EXIF METADATA FOR EVIDENCE CROSS-CHECK:\n"
                f"- Extracted Device Timestamp: {device_ts}\n"
                f"- Camera / Device Model: {camera}\n"
                f"- EXIF GPS Coordinates: {gps_str}\n"
            )

        yolo_prompt_block = ""
        if yolo_results and isinstance(yolo_results, dict):
            y_child = yolo_results.get("children_count", 0)
            y_worker = yolo_results.get("worker_count", 0)
            yolo_prompt_block = (
                "\nAUTHORITATIVE LOCAL YOLO11m DETECTION RESULT:\n"
                f"- Detected Children Count: {y_child} (AUTHORITATIVE - DO NOT RECOUNT OR ENUMERATE)\n"
                f"- Detected Worker Count: {y_worker}\n"
            )

        return f"""
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

    def _call_gemini(self, image_bytes: bytes, prompt: str) -> dict:
        """Calls Gemini via the official google-genai SDK. Returns success/failure dict."""
        client = self._get_client()
        from google.genai import types

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=self._detect_mime_type(image_bytes))
        import time

        start = time.monotonic()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=[prompt, image_part],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            text = response.text if response is not None else ""
            if not text or not text.strip():
                logger.warning("gemini_response_empty", model=self.model)
                return {"success": False, "reason": "Gemini returned an empty response"}
            logger.info(
                "gemini_response",
                model=self.model,
                latency_ms=latency_ms,
                text_len=len(text),
            )
            return {"success": True, "raw_text": text, "latency_ms": latency_ms}
        except Exception as e:
            logger.warning("gemini_call_failed", error=str(e))
            return {"success": False, "reason": f"Gemini API error: {e}"}

    @staticmethod
    def _extract_json_dict(text: str) -> dict:
        """Defensively extracts the largest valid JSON object from the model output."""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        for i in range(len(text)):
            if text[i] == "{":
                nesting = 0
                in_string = False
                escape = False
                for j in range(i, len(text)):
                    ch = text[j]
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
                        continue
                    if ch == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if ch == "{":
                            nesting += 1
                        elif ch == "}":
                            nesting -= 1
                            if nesting == 0:
                                candidate = text[i : j + 1]
                                try:
                                    parsed = json.loads(candidate)
                                    if isinstance(parsed, dict):
                                        return parsed
                                except Exception:
                                    pass
                                break
        return {}

    def _synthesize_executive_remarks(self, data: VisionResponse) -> str:
        """Deterministic official Devanagari remarks (mirrors Groq provider behavior)."""
        if data.is_valid_anganwadi_scene is False:
            return "यह फोटो आंगनवाड़ी गतिविधि की प्रतीत नहीं होती। बच्चे या भोजन वितरण दिखाई नहीं दे रहा। कृपया केंद्र की वास्तविक उपस्थिति फोटो भेजें।"

        count = data.visible_children_count
        meal = data.meal_visible

        if data.children_visible and count is not None and count > 0:
            if meal is True:
                return f"आंगनवाड़ी केंद्र में लगभग {count} बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।"
            elif meal is False:
                return f"आंगनवाड़ी केंद्र में लगभग {count} बच्चे उपस्थित हैं, परंतु भोजन वितरण का दृश्य स्पष्ट नहीं है।"
            else:
                return f"आंगनवाड़ी केंद्र में लगभग {count} बच्चे उपस्थित दिखाई दे रहे हैं।"

        if data.children_visible:
            if meal is True:
                return "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।"
            else:
                return "आंगनवाड़ी केंद्र में बच्चे उपस्थित दिखाई दे रहे हैं।"

        if data.is_valid_anganwadi_scene or data.worker_present:
            return "आंगनवाड़ी केंद्र का परिसर दिखाई दे रहा है, परंतु बच्चों की उपस्थिति या भोजन वितरण का दृश्य स्पष्ट नहीं है।"

        if data.remarks and len(data.remarks.strip()) > 5:
            return data.remarks.strip()

        return "आंगनवाड़ी उपस्थिति सत्यापन प्रक्रिया पूर्ण हुई।"

    def _compute_suspicious_flag(self, data: VisionResponse) -> bool:
        """Business logic for suspicious determination (kept out of the LLM)."""
        if data.image_quality in ["BLURRY", "DARK", "POOR"]:
            return True
        if data.is_valid_anganwadi_scene is False:
            return True
        return False

    # ─────────────────────────────────────────────
    # Public interface (mirrors GroqVisionService)
    # ─────────────────────────────────────────────

    def verify_anganwadi_photo(self, image_bytes: bytes, exif_info=None, yolo_results=None) -> dict:
        """Processes an Anganwadi site photo via Gemini and returns validated results.

        Returned dict is compatible with `app/services/ai_vision.py` downstream logic:
            status, is_valid_anganwadi_scene, children_visible, visible_children_count,
            worker_present, meal_visible, environment_type, image_quality,
            evidence_consistency, confidence_score, remarks, suspicious_flag, provider.
        """
        try:
            image_stream = io.BytesIO(image_bytes)
            image = Image.open(image_stream)
            image.verify()
            Image.open(io.BytesIO(image_bytes))
        except Exception as img_err:
            logger.error("corrupt_or_invalid_image_file", error=str(img_err))
            return {
                "status": "INVALID_IMAGE",
                "reason": f"Corrupt or unreadable image file: {img_err}",
                "fallback": "Manual Review Required",
            }

        if not self.api_key or not self.api_key.strip():
            logger.warning("gemini_request_skipped", reason="GEMINI_API_KEY missing or empty")
            return {
                "status": "VISION_UNAVAILABLE",
                "reason": "GEMINI_API_KEY missing",
                "fallback": "Manual Review Required",
            }

        prompt = self._build_prompt(exif_info, yolo_results)
        res = self._call_gemini(image_bytes, prompt)

        if not res.get("success"):
            return {
                "status": "VISION_UNAVAILABLE",
                "reason": res.get("reason", "Gemini unavailable"),
                "fallback": "Manual Review Required",
            }

        raw_text = res["raw_text"]
        raw_dict = self._extract_json_dict(raw_text)
        if not raw_dict:
            logger.warning("gemini_json_parsing_failed", raw=raw_text[:300])
            return {
                "status": "SCHEMA_VALIDATION_FAILED",
                "reason": "Gemini response did not contain valid JSON",
                "raw_response": raw_text[:500],
                "fallback": "Manual Review Required",
            }

        try:
            validated_data = VisionResponse.model_validate(raw_dict)
        except ValidationError as val_err:
            logger.error("gemini_pydantic_validation_error", error=str(val_err))
            return {
                "status": "SCHEMA_VALIDATION_FAILED",
                "reason": f"AI response did not match expected Pydantic schema: {val_err}",
                "raw_response": raw_text[:500],
                "fallback": "Manual Review Required",
            }

        result_dict = validated_data.model_dump()
        result_dict["status"] = "SUCCESS"
        result_dict["provider"] = "GEMINI_VISION"
        result_dict["remarks"] = self._synthesize_executive_remarks(validated_data)
        result_dict["suspicious_flag"] = self._compute_suspicious_flag(validated_data)
        if res.get("latency_ms") is not None:
            result_dict["latency_ms"] = res["latency_ms"]

        logger.info("gemini_vision_verification_successful", provider="GEMINI_VISION")
        return result_dict


# Singleton instance
gemini_vision = GeminiVisionService()
