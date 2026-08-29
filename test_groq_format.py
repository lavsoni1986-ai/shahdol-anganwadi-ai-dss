import os
import requests
from dotenv import load_dotenv

load_dotenv()
groq_key = os.getenv("GROQ_API_KEY")

if not groq_key:
    print("No GROQ_API_KEY")
    exit(1)

endpoint = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {groq_key.strip()}",
    "Content-Type": "application/json",
}

# Test with response_format
payload = {
    "model": "llama-3.2-11b-vision-preview",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "response_format": {"type": "json_object"}
}

try:
    resp = requests.post(endpoint, headers=headers, json=payload)
    print("Status:", resp.status_code)
    print("Response:", resp.text[:500])
except Exception as e:
    print("Error:", e)
