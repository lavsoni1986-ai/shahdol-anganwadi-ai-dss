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

# Step 1: Simulate getting a reasoning-only response without JSON
print("Waiting 5s for TPM reset...")
time.sleep(5)

initial_prompt = "Analyze this image and return JSON format."
payload1 = {
    "model": "qwen/qwen3.6-27b",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": initial_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
        ]}
    ],
    "temperature": 0.0,
    "max_tokens": 512 # Force reasoning truncation to simulate thinking without JSON
}

res1 = requests.post(endpoint_chat, headers=headers, json=payload1)
data1 = res1.json()
reasoning_content = data1["choices"][0]["message"]["content"]
print("\n--- Initial Response (Simulating Reasoning Output) ---")
print("Content snippet:", reasoning_content[:300])

# Step 2: Test Controlled Follow-up Retry (Requirement 6)
print("\nWaiting 10s before controlled follow-up retry...")
time.sleep(10)

followup_payload = {
    "model": "qwen/qwen3.6-27b",
    "messages": [
        {"role": "user", "content": [
            {"type": "text", "text": initial_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
        ]},
        {"role": "assistant", "content": reasoning_content},
        {"role": "user", "content": "Now provide ONLY the final valid JSON object matching the required schema. Start immediately with '{'."}
    ],
    "temperature": 0.0,
    "max_tokens": 1024
}

res2 = requests.post(endpoint_chat, headers=headers, json=followup_payload)
data2 = res2.json()
final_content = data2["choices"][0]["message"]["content"]
print("\n--- Controlled Follow-up Retry Response ---")
print("Status:", res2.status_code)
print("Final Content:", final_content)
