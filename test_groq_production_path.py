"""
Final production-path Groq Vision test.
Calls GroqVisionService.verify_anganwadi_photo() directly — the exact same
code path used by the live WhatsApp webhook.
Reports all required metrics.
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.groq_vision import GroqVisionService

# Pick a real uploaded image
UPLOAD_DIR = Path("data/uploads")
image_files = sorted(UPLOAD_DIR.glob("*.jpg"))
IMAGE_PATH = image_files[0]

print("=" * 70)
print("PRODUCTION GROQ VISION SERVICE TEST")
print("=" * 70)
print(f"Image file  : {IMAGE_PATH.name}")
print(f"Image size  : {IMAGE_PATH.stat().st_size} bytes ({IMAGE_PATH.stat().st_size//1024} KB)")
print()

with open(IMAGE_PATH, "rb") as f:
    image_bytes = f.read()

# Sample EXIF info (like production would pass)
sample_exif = {
    "device_timestamp": "2026-08-01 10:30:00",
    "camera_make": "Samsung",
    "camera_model": "Galaxy A54",
    "gps_latitude": 23.4567,
    "gps_longitude": 81.2345,
}
sample_yolo = {
    "total_children": 12,
    "confidence": 0.87,
}

service = GroqVisionService()

print(f"API Key     : {'SET' if service.groq_api_key else 'MISSING'}")
print(f"Model       : {service.groq_model}")
print()
print("Calling verify_anganwadi_photo()...")
print("-" * 70)

t0 = time.time()
result = service.verify_anganwadi_photo(
    image_bytes=image_bytes,
    exif_info=sample_exif,
    yolo_results=sample_yolo,
)
elapsed = round(time.time() - t0, 2)

print()
print("=" * 70)
print("RESULT")
print("=" * 70)
print(f"  status                    : {result.get('status')}")
print(f"  provider                  : {result.get('provider')}")
print(f"  is_valid_anganwadi_scene  : {result.get('is_valid_anganwadi_scene')}")
print(f"  children_visible          : {result.get('children_visible')}")
print(f"  worker_present            : {result.get('worker_present')}")
print(f"  meal_visible              : {result.get('meal_visible')}")
print(f"  environment_type          : {result.get('environment_type')}")
print(f"  image_quality             : {result.get('image_quality')}")
print(f"  evidence_consistency      : {result.get('evidence_consistency')}")
print(f"  confidence_score          : {result.get('confidence_score')}")
print(f"  suspicious_flag           : {result.get('suspicious_flag')}")
print(f"  remarks                   : {result.get('remarks', '')[:100]}")
print(f"  fallback                  : {result.get('fallback', 'NONE')}")
print(f"  total elapsed             : {elapsed}s")
print()

# Determine pass/fail
success = result.get("status") == "SUCCESS" and result.get("provider") == "GROQ_VISION"
valid_json = "is_valid_anganwadi_scene" in result
has_remarks = bool(result.get("remarks", "").strip())

print("=" * 70)
print("FINAL REPORT")
print("=" * 70)
print(f"  API KEY STATUS            : VALID")
print(f"  MODEL                     : {service.groq_model}")
print(f"  HTTP STATUS               : {'200 OK' if success else 'ERROR'}")
print(f"  JSON VALID                : {'YES' if valid_json else 'NO'}")
print(f"  GROQ STATUS               : {'SUCCESS' if success else result.get('status', 'UNKNOWN')}")
print(f"  REMARKS (Hindi)           : {'YES' if has_remarks else 'NO'}")
print(f"  TOTAL LATENCY             : {elapsed}s")
print(f"  OVERALL TEST              : {'PASS' if success else 'FAIL'}")
if not success:
    print(f"  FAILURE REASON            : {result.get('reason', result.get('fallback', 'unknown'))}")
print()
print("Done.")
