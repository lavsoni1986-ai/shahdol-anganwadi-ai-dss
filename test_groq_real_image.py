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
You are an official AI Audit Assistant for District Shahdol Anganwadi Digital Verification & Decision Support System.
Analyze this photograph carefully.

CRITICAL INSTRUCTIONS:
- DO NOT INCLUDE ANY THINKING TAGS, <think> BLOCKS, OR PREAMBLE TEXT.
- YOUR RESPONSE MUST BE VALID JSON AND MUST START IMMEDIATELY WITH THE OPENING BRACE '{'.
- 'remarks' MUST BE WRITTEN EXCLUSIVELY IN PURE DEVANAGARI HINDI SCRIPT (शुद्ध देवनागरी हिंदी).

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
  "remarks": "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं तथा भोजन वितरण का दृश्य स्पष्ट है।"
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
    "max_tokens": 1024,
    "response_format": {"type": "json_object"}
}

print("Executing Groq request with response_format=json_object...")
res1 = requests.post(endpoint_chat, headers=headers, json=payload)
print("Response 1 Status:", res1.status_code)
print("Response 1 Body:", res1.text[:500])

if res1.status_code == 400:
    print("\nGot HTTP 400, waiting 10s before retry without response_format...")
    time.sleep(10)
    del payload["response_format"]
    
    # Add explicit instructions for fallback retry
    payload["messages"][0]["content"][0]["text"] += "\nIMPORTANT FALLBACK INSTRUCTION: DO NOT OUTPUT ANY THINKING TAGS OR REASONING. OUTPUT ONLY THE JSON OBJECT."
    
    res2 = requests.post(endpoint_chat, headers=headers, json=payload)
    print("Response 2 Status:", res2.status_code)
    print("Response 2 Body:", res2.text[:1000])
