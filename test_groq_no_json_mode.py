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

img_path = "data/processed/00e9c20f_detected.jpg"
with open(img_path, "rb") as f:
    img_bytes = f.read()

b64_img = base64.b64encode(img_bytes).decode("utf-8")

prompt = """
You are an official AI Audit Assistant for District Shahdol Anganwadi Digital Verification System.

CRITICAL OUTPUT REQUIREMENTS:
1. DO NOT OUTPUT ANY REASONING, THINKING, OR <think> TAGS.
2. DO NOT WRITE ANY INTRODUCTORY OR EXPLANATORY TEXT.
3. YOUR RESPONSE MUST START IMMEDIATELY WITH THE '{' CHARACTER AND CONTAIN ONLY VALID JSON.
4. 'remarks' MUST BE WRITTEN EXCLUSIVELY IN PURE DEVANAGARI HINDI SCRIPT (शुद्ध देवनागरी हिंदी).

Return strictly valid JSON matching this schema:
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

payload = {
    "model": "qwen/qwen3.6-27b",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
        ]}
    ],
    "temperature": 0.0,
    "max_tokens": 1024
    # NO response_format specified here!
}

print("Waiting 10s for TPM reset before testing no response_format...")
time.sleep(10)

res = requests.post(endpoint_chat, headers=headers, json=payload)
print("Status:", res.status_code)
print("Body:", res.text[:1000])
