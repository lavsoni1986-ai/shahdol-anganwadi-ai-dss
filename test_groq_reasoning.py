import os
import requests
import json
import base64
import time
from dotenv import load_dotenv

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
headers = {"Authorization": f"Bearer {groq_key.strip()}"}
endpoint_chat = "https://api.groq.com/openai/v1/chat/completions"

test_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xff\xff\x3f\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
b64_img = base64.b64encode(test_img).decode("utf-8")

prompt = """
CRITICAL: DO NOT OUTPUT ANY THINKING OR <think> TAGS. DO NOT REASON OUT LOUD.
You MUST start your response immediately with the character '{' and output valid JSON only.

SCHEMA:
{
  "schema_version": "1.0",
  "is_valid_anganwadi_scene": true,
  "children_visible": true,
  "visible_children_count": null,
  "worker_present": true,
  "meal_visible": true,
  "environment_type": "indoor",
  "image_quality": "CLEAR",
  "evidence_consistency": "CONSISTENT",
  "confidence_score": 95,
  "remarks": "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं।"
}
"""

print("Waiting 10 seconds for TPM reset...")
time.sleep(10)

# Test 1: reasoning_format: "hidden"
payload = {
    "model": "qwen/qwen3.6-27b",
    "reasoning_format": "hidden",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
        ]}
    ],
    "temperature": 0.0,
    "max_tokens": 1024
}

res = requests.post(endpoint_chat, headers=headers, json=payload)
print("\n--- Test reasoning_format: hidden ---")
print("Status:", res.status_code)
print("Response:", res.text[:500])

print("\nWaiting 10 seconds for TPM reset...")
time.sleep(10)

# Test 2: strict prompt without reasoning_format param (if param rejected)
if res.status_code == 400:
    del payload["reasoning_format"]
    res2 = requests.post(endpoint_chat, headers=headers, json=payload)
    print("\n--- Test strict prompt without reasoning_format param ---")
    print("Status:", res2.status_code)
    print("Response:", res2.text[:500])
