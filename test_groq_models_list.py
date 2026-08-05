"""
List all available Groq models + test vision-capable ones.
"""
import os
import sys
import json
import base64
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}

# Load a small test image
UPLOAD_DIR = Path("data/uploads")
image_files = sorted(UPLOAD_DIR.glob("*.jpg"))
IMAGE_PATH = image_files[0]
with open(IMAGE_PATH, "rb") as f:
    image_bytes = f.read()
b64_image = base64.b64encode(image_bytes).decode("utf-8")

print("=" * 70)
print("ALL AVAILABLE GROQ MODELS")
print("=" * 70)
r = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
if r.status_code != 200:
    print(f"FAIL: {r.text}")
    sys.exit(1)

models = sorted([m["id"] for m in r.json().get("data", [])])
print(f"Total: {len(models)} models\n")
for i, m in enumerate(models, 1):
    print(f"  {i:2}. {m}")

print()
print("=" * 70)
print("VISION MODEL CANDIDATES (to test)")
print("=" * 70)

# Known vision-capable models on Groq (as of 2026)
VISION_CANDIDATES = [
    m for m in models
    if any(kw in m.lower() for kw in ["vision", "llama-4", "scout", "maverick", "qwen"])
]
print("Vision candidates found:")
for m in VISION_CANDIDATES:
    print(f"  - {m}")
print()

# Simple compact prompt - no response_format, max_tokens=512
COMPACT_SYSTEM = (
    "You are an AI audit assistant. "
    "Reply ONLY with valid compact JSON. No thinking, no preamble. "
    "'remarks' must be pure Devanagari Hindi."
)
COMPACT_USER = """Analyze this photo. Return ONLY this JSON (start with '{'):
{
  "schema_version": "1.0",
  "is_valid_anganwadi_scene": true,
  "children_visible": true,
  "visible_children_count": null,
  "worker_present": true,
  "meal_visible": false,
  "environment_type": "outdoor",
  "image_quality": "CLEAR",
  "evidence_consistency": "CONSISTENT",
  "confidence_score": 80,
  "remarks": "आंगनवाड़ी केंद्र का दृश्य।"
}"""

print("=" * 70)
print("TESTING EACH VISION CANDIDATE")
print("=" * 70)

results = {}
for i, model in enumerate(VISION_CANDIDATES):
    print(f"\n[{i+1}/{len(VISION_CANDIDATES)}] Testing: {model}")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": COMPACT_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": COMPACT_USER},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }
        ],
        "temperature": 0.0,
        "max_tokens": 512,
    }
    try:
        t0 = time.time()
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=45.0)
        latency = round(time.time() - t0, 2)

        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            content = data["choices"][0]["message"]["content"]
            has_think = "<think>" in content

            # Try parse JSON
            try:
                start = content.find('{')
                end = content.rfind('}') + 1
                parsed = json.loads(content[start:end]) if start != -1 else {}
                valid = bool(parsed) and "schema_version" in parsed
            except Exception:
                parsed = {}
                valid = False

            print(f"  Status      : HTTP 200 OK")
            print(f"  Latency     : {latency}s")
            print(f"  Prompt tok  : {usage.get('prompt_tokens', 'N/A')}")
            print(f"  Completion  : {usage.get('completion_tokens', 'N/A')}")
            print(f"  Total tok   : {usage.get('total_tokens', 'N/A')}")
            print(f"  Has <think> : {has_think}")
            print(f"  JSON Valid  : {'YES' if valid else 'NO'}")
            if valid:
                print(f"  remarks     : {parsed.get('remarks', '')[:60]}")
            else:
                print(f"  Raw preview : {content[:200]}")
            results[model] = {"status": 200, "valid": valid, "tokens": usage.get("total_tokens"), "latency": latency, "has_think": has_think}

        elif resp.status_code == 400 and "decommissioned" in resp.text:
            print(f"  Status      : DECOMMISSIONED")
            results[model] = {"status": "decommissioned"}
        elif resp.status_code == 400 and "does not support" in resp.text.lower():
            print(f"  Status      : HTTP 400 - No vision support")
            print(f"  Body        : {resp.text[:150]}")
            results[model] = {"status": "no_vision"}
        elif resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "15")
            print(f"  Status      : HTTP 429 Rate Limited (Retry-After: {retry_after}s)")
            results[model] = {"status": 429}
        else:
            print(f"  Status      : HTTP {resp.status_code}")
            print(f"  Body        : {resp.text[:200]}")
            results[model] = {"status": resp.status_code}

    except Exception as e:
        print(f"  Exception   : {e}")
        results[model] = {"status": "exception", "error": str(e)}

    if i < len(VISION_CANDIDATES) - 1:
        print("  (waiting 10s...)")
        time.sleep(10)

print()
print("=" * 70)
print("FINAL RESULTS")
print("=" * 70)
for model, r in results.items():
    status = r.get("status")
    valid = r.get("valid", False)
    tokens = r.get("total_tokens") or r.get("tokens", "N/A")
    latency = r.get("latency", "N/A")
    has_think = r.get("has_think", "?")
    marker = "*** PASS ***" if valid else "    FAIL    "
    print(f"  [{marker}] {model}")
    print(f"             Status={status}, JSON={valid}, tokens={tokens}, latency={latency}s, think={has_think}")

# Best recommendation
passing = [m for m, r in results.items() if r.get("valid")]
if passing:
    best = passing[0]
    print(f"\nRECOMMENDATION: Use model '{best}'")
    print(f"  Set in .env: GROQ_VISION_MODEL={best}")
else:
    print("\nNo model produced valid JSON with current prompt. Consider:")
    print("  1. Larger max_tokens for qwen (to allow thinking to complete)")
    print("  2. Different prompt approach")
print("\nDone.")
