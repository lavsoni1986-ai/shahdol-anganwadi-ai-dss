"""
Test qwen/qwen3.6-27b with max_tokens=2048 to see if it completes thinking AND produces JSON.
Also test assistant prefill trick to force immediate JSON output.
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
MODEL = "qwen/qwen3.6-27b"
headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}

UPLOAD_DIR = Path("data/uploads")
image_files = sorted(UPLOAD_DIR.glob("*.jpg"))
IMAGE_PATH = image_files[0]
with open(IMAGE_PATH, "rb") as f:
    image_bytes = f.read()
b64_image = base64.b64encode(image_bytes).decode("utf-8")

print("=" * 70)
print("QWEN THINKING BYPASS TESTS")
print("=" * 70)
print(f"Image: {IMAGE_PATH.name} ({len(image_bytes)//1024} KB)\n")

COMPACT_SYSTEM = (
    "You are an AI audit assistant. "
    "Reply ONLY with valid compact JSON. No thinking, no preamble. "
    "'remarks' must be pure Devanagari Hindi."
)
COMPACT_USER = """Analyze this Anganwadi photo. Return ONLY this JSON (start with '{'):
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

def try_parse_json(text):
    # Try to find JSON after any <think>...</think> block
    import re
    # Remove thinking block first
    text_no_think = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    for candidate in [text_no_think, text]:
        start = candidate.find('{')
        end = candidate.rfind('}') + 1
        if start != -1:
            try:
                parsed = json.loads(candidate[start:end])
                if isinstance(parsed, dict) and "schema_version" in parsed:
                    return parsed, True
            except Exception:
                pass
    return {}, False

def run_test(label, payload):
    print(f"\n{'-'*60}")
    print(f"TEST: {label}")
    print(f"{'-'*60}")
    t0 = time.time()
    resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=60.0)
    latency = round(time.time() - t0, 2)
    print(f"  HTTP Status   : {resp.status_code}")
    print(f"  Latency       : {latency}s")
    if resp.status_code == 200:
        data = resp.json()
        usage = data.get("usage", {})
        content = data["choices"][0]["message"]["content"]
        finish_reason = data["choices"][0].get("finish_reason", "?")
        has_think = "<think>" in content
        parsed, valid = try_parse_json(content)
        print(f"  Finish reason : {finish_reason}")
        print(f"  Prompt tok    : {usage.get('prompt_tokens', 'N/A')}")
        print(f"  Completion tok: {usage.get('completion_tokens', 'N/A')}")
        print(f"  Total tokens  : {usage.get('total_tokens', 'N/A')}")
        print(f"  Has <think>   : {has_think}")
        print(f"  JSON Valid    : {'YES' if valid else 'NO'}")
        if valid:
            print(f"  schema_version: {parsed.get('schema_version')}")
            print(f"  is_valid_scene: {parsed.get('is_valid_anganwadi_scene')}")
            print(f"  image_quality : {parsed.get('image_quality')}")
            print(f"  remarks       : {parsed.get('remarks', '')[:80]}")
        else:
            print(f"  Last 300 chars: ...{content[-300:]}")
        return {"valid": valid, "tokens": usage.get("total_tokens"), "latency": latency, "finish": finish_reason}
    elif resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "15")
        print(f"  429 Rate Limit (Retry-After: {retry_after}s)")
        print(f"  Body: {resp.text[:200]}")
        return {"valid": False, "error": "429"}
    else:
        print(f"  Error: {resp.text[:300]}")
        return {"valid": False, "error": resp.status_code}

# ── TEST A: max_tokens=2048 (enough room for thinking + JSON) ─────────────────
result_a = run_test("qwen + max_tokens=2048 (no response_format)", {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": COMPACT_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": COMPACT_USER},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
        ]}
    ],
    "temperature": 0.0,
    "max_tokens": 2048,
})

print("\n  Waiting 15s...")
time.sleep(15)

# ── TEST B: Assistant prefill with '{' to bypass thinking ─────────────────────
result_b = run_test("qwen + assistant prefill '{' (force immediate JSON)", {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": COMPACT_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": COMPACT_USER},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
        ]},
        {"role": "assistant", "content": "{"},
    ],
    "temperature": 0.0,
    "max_tokens": 512,
})

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"[A] max_tokens=2048  : JSON={result_a.get('valid')}, tokens={result_a.get('tokens')}, finish={result_a.get('finish')}")
print(f"[B] assistant prefill: JSON={result_b.get('valid')}, tokens={result_b.get('tokens')}, finish={result_b.get('finish')}")
print()

if result_b.get("valid"):
    print("RECOMMENDATION: Use ASSISTANT PREFILL trick with max_tokens=512")
    print("  This bypasses <think> entirely — model continues from '{' directly to JSON")
elif result_a.get("valid"):
    print("RECOMMENDATION: Use max_tokens=2048 — allows thinking to complete + JSON to follow")
else:
    print("RECOMMENDATION: Neither approach worked. Check output details above.")
print("\nDone.")
