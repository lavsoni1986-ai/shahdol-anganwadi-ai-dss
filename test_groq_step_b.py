"""
Step B: Complex real Anganwadi image test.
Uses the actual 166 KB live WhatsApp image that failed previously (1bc48092...).
Calls GroqVisionService.verify_anganwadi_photo() with the full strict_prompt + EXIF block.
Reports: finish_reason, prompt_tokens, completion_tokens, </think> present, JSON valid.
"""
import os
import sys
import time
import json
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

# Use the REAL live WhatsApp image that previously caused failure
REAL_IMAGE = Path("data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg")
if not REAL_IMAGE.exists():
    # Fall back to any upload image larger than 100 KB
    candidates = sorted(Path("data/uploads").glob("*.jpg"), key=lambda p: p.stat().st_size, reverse=True)
    REAL_IMAGE = candidates[0] if candidates else None

if not REAL_IMAGE:
    print("ERROR: No image found in data/uploads/")
    sys.exit(1)

print("=" * 70)
print("STEP B: COMPLEX REAL ANGANWADI IMAGE TEST (live WhatsApp image)")
print("=" * 70)
print(f"Image: {REAL_IMAGE.name}")
print(f"Size : {REAL_IMAGE.stat().st_size} bytes ({REAL_IMAGE.stat().st_size//1024} KB)")
print()

# --- Call via production service (full path) ---
from app.services.groq_vision import GroqVisionService

with open(REAL_IMAGE, "rb") as f:
    image_bytes = f.read()

# Simulate realistic EXIF (as ai_vision.py extracts from a real WhatsApp image)
sample_exif = {
    "device_timestamp": "2026-08-03 10:15:00",
    "camera_make": "Xiaomi",
    "camera_model": "Redmi Note 12",
    "gps_latitude": None,
    "gps_longitude": None,
}
sample_yolo = {
    "children_count": 8,
    "worker_count": 1,
    "confidence": 0.82,
    "processing_time_ms": 1240,
}

service = GroqVisionService()

# Also intercept raw API response to get finish_reason and token counts
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_orig_post = requests.post
_call_count = [0]
_last_resp_data = [None]

def _patched_post(url, **kwargs):
    if "groq.com" in str(url):
        _call_count[0] += 1
        print(f"  [API INTERCEPTOR] Groq call #{_call_count[0]} to {url}")
    resp = _orig_post(url, **kwargs)
    if "groq.com" in str(url) and resp.status_code == 200:
        try:
            d = resp.json()
            _last_resp_data[0] = d
        except Exception:
            pass
    return resp

requests.post = _patched_post

print("Calling verify_anganwadi_photo() with real image + EXIF + YOLO...")
print("-" * 70)
t0 = time.time()
result = service.verify_anganwadi_photo(
    image_bytes=image_bytes,
    exif_info=sample_exif,
    yolo_results=sample_yolo,
)
elapsed = round(time.time() - t0, 2)

requests.post = _orig_post  # restore

# Extract raw metrics from last intercepted response
finish_reason = "N/A"
prompt_tokens = "N/A"
completion_tokens = "N/A"
total_tokens = "N/A"
think_present = "N/A"
think_closed = "N/A"

if _last_resp_data[0]:
    d = _last_resp_data[0]
    choice = d.get("choices", [{}])[0]
    finish_reason = choice.get("finish_reason", "N/A")
    content = choice.get("message", {}).get("content", "")
    usage = d.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", "N/A")
    completion_tokens = usage.get("completion_tokens", "N/A")
    total_tokens = usage.get("total_tokens", "N/A")
    think_present = "<think>" in content
    think_closed = "</think>" in content

print()
print("=" * 70)
print("STEP B RESULT")
print("=" * 70)
print(f"  Groq API call count       : {_call_count[0]}")
print(f"  HTTP status               : 200 OK" if result.get("status") == "SUCCESS" else f"  HTTP status               : FAIL")
print(f"  finish_reason             : {finish_reason}")
print(f"  Prompt tokens             : {prompt_tokens}")
print(f"  Completion tokens         : {completion_tokens}")
print(f"  Total tokens              : {total_tokens}")
print(f"  <think> present           : {think_present}")
print(f"  </think> closed           : {think_closed}")
print(f"  Groq status               : {result.get('status')}")
print(f"  JSON valid                : {'YES' if result.get('is_valid_anganwadi_scene') is not None else 'NO (missing key)'}")
print(f"  is_valid_anganwadi_scene  : {result.get('is_valid_anganwadi_scene')}")
print(f"  children_visible          : {result.get('children_visible')}")
print(f"  worker_present            : {result.get('worker_present')}")
print(f"  image_quality             : {result.get('image_quality')}")
print(f"  remarks (Hindi)           : {result.get('remarks', '')[:80]}")
print(f"  Total elapsed             : {elapsed}s")

success = (
    result.get("status") == "SUCCESS"
    and _call_count[0] == 1
    and finish_reason in ("stop", "length")
    and result.get("is_valid_anganwadi_scene") is not None
)

print()
print(f"  Groq call count = 1       : {'PASS' if _call_count[0] == 1 else 'FAIL'}")
print(f"  JSON valid                : {'PASS' if result.get('is_valid_anganwadi_scene') is not None else 'FAIL'}")
print(f"  No follow-up invoked      : {'PASS' if _call_count[0] == 1 else 'FAIL (follow-up was triggered)'}")
print(f"  finish_reason=stop        : {'PASS' if finish_reason == 'stop' else 'WARN (' + str(finish_reason) + ')'}")
print()
print(f"STEP B OVERALL: {'PASS' if success else 'FAIL'}")
print()
print("Done.")
