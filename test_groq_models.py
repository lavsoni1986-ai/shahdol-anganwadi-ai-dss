import os
import requests
import json
import base64
from dotenv import load_dotenv

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
print(f"Key present: {bool(groq_key)}")

# 1. List available models from Groq
endpoint_models = "https://api.groq.com/openai/v1/models"
headers = {"Authorization": f"Bearer {groq_key.strip()}"}
r = requests.get(endpoint_models, headers=headers)
if r.status_code == 200:
    models = [m["id"] for m in r.json().get("data", [])]
    print("Available Groq Models:", models)
    vision_models = [m for m in models if "vision" in m.lower() or "qwen" in m.lower() or "llama-3.2" in m.lower()]
    print("Vision/Qwen Candidate Models:", vision_models)
else:
    print("Failed to list models:", r.status_code, r.text)

# 2. Test small dummy image with qwen/qwen3.6-27b and response_format/prompts
test_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xff\xff\x3f\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
b64_img = base64.b64encode(test_img).decode("utf-8")

prompt = """Return JSON matching: {"status": "SUCCESS", "remarks": "सत्यापित"}"""

# Test 2a: response_format with qwen
payload = {
    "model": "qwen/qwen3.6-27b",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
        ]}
    ],
    "response_format": {"type": "json_object"}
}

endpoint_chat = "https://api.groq.com/openai/v1/chat/completions"
res = requests.post(endpoint_chat, headers=headers, json=payload)
print("\n--- Test qwen with json_object ---")
print("Status:", res.status_code)
print("Response:", res.text[:300])

# Test 2b: qwen without json_object
del payload["response_format"]
res2 = requests.post(endpoint_chat, headers=headers, json=payload)
print("\n--- Test qwen without json_object ---")
print("Status:", res2.status_code)
print("Response:", res2.text[:500])
