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

reasoning_sample = "<think>The user wants a JSON analysis of the image. I see a worker in an indoor setting.</think>"

print("Waiting 10s before text-only follow-up retry...")
time.sleep(10)

schema_instruction = """
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

followup_payload = {
    "model": "qwen/qwen3.6-27b",
    "messages": [
        {"role": "user", "content": "You are an official AI Audit Assistant for District Shahdol Anganwadi Digital Verification System."},
        {"role": "assistant", "content": reasoning_sample},
        {"role": "user", "content": f"Based on your analysis, respond NOW with ONLY the valid JSON object starting with '{{'. Do not output any thinking tags.\n{schema_instruction}"}
    ],
    "temperature": 0.0,
    "max_tokens": 1024
}

res2 = requests.post(endpoint_chat, headers=headers, json=followup_payload)
print("Status:", res2.status_code)
print("Response text:", res2.text[:1000])
