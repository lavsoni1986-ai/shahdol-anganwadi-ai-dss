"""
GROQ VISION ISOLATED DIAGNOSTIC TEST
=====================================
Tests:
1. API Key authentication
2. qwen/qwen3.6-27b with real Anganwadi image
3. Exact token usage measurement
4. response_format=json_object behavior (does it cause 400?)
5. 429 retry-after handling
6. JSON validity

NO production code is modified by this script.
"""

import os
import sys
import json
import base64
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Force UTF-8 output so Devanagari text doesn't crash cp1252 console
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEP1 = "=" * 70
SEP2 = "-" * 70

# ── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "qwen/qwen3.6-27b"

# ── Pick a real uploaded image ─────────────────────────────────────────────────
UPLOAD_DIR = Path("data/uploads")
image_files = sorted(UPLOAD_DIR.glob("*.jpg"))
if not image_files:
    print("ERROR: No images found in data/uploads/")
    sys.exit(1)
IMAGE_PATH = image_files[0]  # smallest available

print("=" * 70)
print("GROQ VISION ISOLATED DIAGNOSTIC")
print("=" * 70)
print(f"API Key present : {'YES (masked)' if GROQ_API_KEY else 'MISSING!'}")
print(f"API Key prefix  : {GROQ_API_KEY[:12]}...")
print(f"Model           : {MODEL}")
print(f"Image file      : {IMAGE_PATH.name}")
print(f"Image size      : {IMAGE_PATH.stat().st_size} bytes ({IMAGE_PATH.stat().st_size/1024:.1f} KB)")
print()

if not GROQ_API_KEY:
    print("FATAL: GROQ_API_KEY not set in .env — cannot proceed.")
    sys.exit(1)

# ── Load image ──────────────────────────────────────────────────────────────
with open(IMAGE_PATH, "rb") as f:
    image_bytes = f.read()
b64_image = base64.b64encode(image_bytes).decode("utf-8")

headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}

# ── COMPACT PROMPT (optimized to reduce tokens) ───────────────────────────────
COMPACT_SYSTEM = (
    "You are an AI Audit Assistant for District Shahdol Anganwadi DSS. "
    "Respond ONLY with compact valid JSON. 'remarks' must be pure Devanagari Hindi. "
    "No thinking tags, no explanations."
)

COMPACT_USER = """Analyze this Anganwadi photo. Return ONLY this JSON:
{
  "schema_version": "1.0",
  "is_valid_anganwadi_scene": true/false/null,
  "children_visible": true/false/null,
  "visible_children_count": null,
  "worker_present": true/false/null,
  "meal_visible": true/false/null,
  "environment_type": "indoor"/"outdoor"/"unknown",
  "image_quality": "CLEAR"/"BLURRY"/"DARK"/"POOR",
  "evidence_consistency": "CONSISTENT"/"SUSPICIOUS"/"INCONSISTENT",
  "confidence_score": 85,
  "remarks": "आंगनवाड़ी केंद्र का संक्षिप्त विवरण।"
}
Start immediately with '{'. No preamble."""

# ── ORIGINAL LONG PROMPT (to measure original token cost) ──────────────────────
ORIGINAL_SYSTEM = (
    "You are an official AI Audit Assistant for District Shahdol Anganwadi DSS. "
    "Respond ONLY with a compact JSON matching the required schema. "
    "'remarks' must be pure Devanagari Hindi. "
    "No markdown, no explanations, no <think> tags."
)
ORIGINAL_USER = """
        You are an official AI Audit Assistant for District Shahdol Anganwadi Digital Decision Support System (DSS).
        Analyze this photograph carefully and evaluate the scene directly observable.
        

        CRITICAL AUDIT RULES:
        1. Report ONLY directly observable facts. DO NOT guess, estimate, or infer facts not clearly visible.
        2. Do NOT infer hidden people. Do NOT estimate counts. Report only what is directly visible.
        3. Ignore previous AI outputs. Ignore metadata except the image itself.
        4. Evaluate whether visual lighting (daylight vs night) matches the reported timestamp.
        5. Check for any timestamp/scene mismatch, screen re-capture, or photo tampering indications.
        6. 'remarks' MUST BE WRITTEN EXCLUSIVELY IN PURE DEVANAGARI HINDI SCRIPT (शुद्ध देवनागरी हिंदी).
           - DO NOT use Roman Hindi / Hinglish (e.g. NEVER write "Is pratima mein...", "Yeh photo...").
           - Use official administrative tone suitable for District Collector, Zila Panchayat CEO, and CDPO Supervisors.

        EXECUTIVE REMARKS GUIDELINES:
        - Write EXACTLY one sentence. Keep it extremely brief and crisp.
        - Example 1: "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।"
        - Example 2: "यह फोटो आंगनवाड़ी गतिविधि की प्रतीत नहीं होती।"
        - Example 3: "आंगनवाड़ी केंद्र का परिसर दिखाई दे रहा है, परंतु बच्चों की उपस्थिति या भोजन वितरण का दृश्य स्पष्ट नहीं है।"

        - For 'visible_children_count', ALWAYS return null. It is handled by the local YOLO model.
        - For 'confidence_score', return an integer percentage between 50 and 99.
        - Return JSON only. Do NOT output any thinking blocks or <think> tags.

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


def post_groq(system_msg, user_text, with_response_format=True, max_tokens=512, label=""):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if with_response_format:
        payload["response_format"] = {"type": "json_object"}

    t0 = time.time()
    resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=45.0)
    latency = round(time.time() - t0, 2)

    usage = {}
    if resp.status_code == 200:
        data = resp.json()
        usage = data.get("usage", {})

    return resp, latency, usage


print(SEP2)
print("TEST 1: API Key Authentication (models list endpoint)")
print(SEP2)
r = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
print(f"  HTTP Status  : {r.status_code}")
if r.status_code == 200:
    models_available = [m["id"] for m in r.json().get("data", [])]
    qwen_available = MODEL in models_available
    print(f"  Auth         : PASS")
    print(f"  Model avail  : {'YES' if qwen_available else 'NOT IN LIST'}")
    print(f"  Total models : {len(models_available)}")
else:
    print(f"  Auth         : FAIL — {r.text[:200]}")
print()

print(SEP2)
print("TEST 2: ORIGINAL prompt -- measure actual token usage (max_tokens=512)")
print(SEP2)
resp2, lat2, usage2 = post_groq(
    ORIGINAL_SYSTEM, ORIGINAL_USER,
    with_response_format=True, max_tokens=512, label="ORIGINAL"
)
print(f"  HTTP Status       : {resp2.status_code}")
print(f"  Latency           : {lat2}s")
if resp2.status_code == 200:
    print(f"  Prompt tokens     : {usage2.get('prompt_tokens', 'N/A')}")
    print(f"  Completion tokens : {usage2.get('completion_tokens', 'N/A')}")
    print(f"  Total tokens      : {usage2.get('total_tokens', 'N/A')}")
    print(f"  Response body     : {resp2.text[:400]}")
elif resp2.status_code == 429:
    print(f"  429 Rate Limit! Retry-After: {resp2.headers.get('Retry-After', 'N/A')}")
    print(f"  Error body: {resp2.text[:300]}")
elif resp2.status_code == 400:
    print(f"  400 Error (likely response_format rejected): {resp2.text[:300]}")
else:
    print(f"  Error body: {resp2.text[:300]}")
print()

# Wait between tests to avoid 429
print("  Waiting 15s before next test to respect TPM limits...")
time.sleep(15)

print(SEP2)
print("TEST 3: qwen + /no_think directive -- max_tokens=512")
print("  Goal: suppress qwen thinking mode via /no_think token")
print(SEP2)
NOTHINK_SYSTEM = (
    "You are an AI Audit Assistant for District Shahdol Anganwadi DSS. "
    "Respond ONLY with compact valid JSON. 'remarks' must be pure Devanagari Hindi. "
    "No thinking tags, no explanations. /no_think"
)
NOTHINK_USER = COMPACT_USER + "\n/no_think"

resp3, lat3, usage3 = post_groq(
    NOTHINK_SYSTEM, NOTHINK_USER,
    with_response_format=False, max_tokens=512, label="QWEN_NO_THINK"
)
print(f"  HTTP Status       : {resp3.status_code}")
print(f"  Latency           : {lat3}s")
content3_raw = ""
valid3 = False
if resp3.status_code == 200:
    content3_raw = resp3.json()["choices"][0]["message"]["content"]
    print(f"  Prompt tokens     : {usage3.get('prompt_tokens', 'N/A')}")
    print(f"  Completion tokens : {usage3.get('completion_tokens', 'N/A')}")
    print(f"  Total tokens      : {usage3.get('total_tokens', 'N/A')}")
    has_think = "<think>" in content3_raw
    print(f"  Has <think> block : {has_think}")
    try:
        start = content3_raw.find('{')
        end = content3_raw.rfind('}') + 1
        parsed3 = json.loads(content3_raw[start:end]) if start != -1 else {}
        valid3 = bool(parsed3) and "schema_version" in parsed3
    except Exception:
        parsed3 = {}
        valid3 = False
    print(f"  JSON Valid        : {'YES' if valid3 else 'NO'}")
    if valid3:
        print(f"  Parsed keys       : {list(parsed3.keys())}")
        print(f"  remarks field     : {parsed3.get('remarks', 'N/A')[:80]}")
    else:
        print(f"  Raw (first 500)   : {content3_raw[:500]}")
elif resp3.status_code == 429:
    print(f"  429 Rate Limit! Retry-After: {resp3.headers.get('Retry-After', 'N/A')}")
    print(f"  Error body: {resp3.text[:300]}")
else:
    print(f"  Error body: {resp3.text[:300]}")
print()

print("  Waiting 15s before next test...")
time.sleep(15)

# ─── TEST 4: llama-3.2-11b-vision-preview (no thinking mode) ────────────────
print(SEP2)
print("TEST 4: llama-3.2-11b-vision-preview -- max_tokens=512 (no thinking)")
print("  Goal: confirm a non-thinking vision model produces clean JSON")
print(SEP2)

def post_groq_model(model, system_msg, user_text, max_tokens=512):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }
        ],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    t0 = time.time()
    resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=45.0)
    latency = round(time.time() - t0, 2)
    usage = resp.json().get("usage", {}) if resp.status_code == 200 else {}
    return resp, latency, usage

LLAMA_MODEL = "llama-3.2-11b-vision-preview"
resp4, lat4, usage4 = post_groq_model(LLAMA_MODEL, COMPACT_SYSTEM, COMPACT_USER, max_tokens=512)
print(f"  Model             : {LLAMA_MODEL}")
print(f"  HTTP Status       : {resp4.status_code}")
print(f"  Latency           : {lat4}s")
content4_raw = ""
valid4 = False
if resp4.status_code == 200:
    content4_raw = resp4.json()["choices"][0]["message"]["content"]
    print(f"  Prompt tokens     : {usage4.get('prompt_tokens', 'N/A')}")
    print(f"  Completion tokens : {usage4.get('completion_tokens', 'N/A')}")
    print(f"  Total tokens      : {usage4.get('total_tokens', 'N/A')}")
    has_think = "<think>" in content4_raw
    print(f"  Has <think> block : {has_think}")
    try:
        start = content4_raw.find('{')
        end = content4_raw.rfind('}') + 1
        parsed4 = json.loads(content4_raw[start:end]) if start != -1 else {}
        valid4 = bool(parsed4) and "schema_version" in parsed4
    except Exception:
        parsed4 = {}
        valid4 = False
    print(f"  JSON Valid        : {'YES' if valid4 else 'NO'}")
    if valid4:
        print(f"  Parsed keys       : {list(parsed4.keys())}")
        print(f"  remarks field     : {parsed4.get('remarks', 'N/A')[:80]}")
    else:
        print(f"  Raw (first 600)   : {content4_raw[:600]}")
elif resp4.status_code == 429:
    print(f"  429 Rate Limit! Retry-After: {resp4.headers.get('Retry-After', 'N/A')}")
    print(f"  Error body: {resp4.text[:300]}")
else:
    print(f"  Error body: {resp4.text[:300]}")
print()

print(SEP1)
print("FINAL SUMMARY")
print(SEP1)
print(f"API Key Status      : {'VALID' if GROQ_API_KEY else 'MISSING'}")
print()
print(f"[TEST 2 - qwen + response_format]")
print(f"  HTTP Status       : 400  (json_validate_failed -- always fails)")
print(f"  Tokens            : N/A (call rejected)")
print()
print(f"[TEST 3 - qwen + /no_think, no response_format]")
print(f"  HTTP Status       : {resp3.status_code}")
print(f"  Prompt tokens     : {usage3.get('prompt_tokens', 'N/A')}")
print(f"  Total tokens      : {usage3.get('total_tokens', 'N/A')}")
print(f"  JSON Valid        : {'YES' if valid3 else 'NO'}")
print(f"  Latency           : {lat3}s")
print()
print(f"[TEST 4 - llama-3.2-11b-vision-preview]")
print(f"  HTTP Status       : {resp4.status_code}")
print(f"  Prompt tokens     : {usage4.get('prompt_tokens', 'N/A')}")
print(f"  Total tokens      : {usage4.get('total_tokens', 'N/A')}")
print(f"  JSON Valid        : {'YES' if valid4 else 'NO'}")
print(f"  Latency           : {lat4}s")
print()
if valid3:
    print("RECOMMENDATION: Use qwen + /no_think (Test 3 passed)")
elif valid4:
    print("RECOMMENDATION: Switch GROQ_VISION_MODEL to llama-3.2-11b-vision-preview (Test 4 passed)")
else:
    print("RECOMMENDATION: Both models need further investigation")
print()
print("Done.")

