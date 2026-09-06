import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"AQ Key Loaded: {api_key[:15]}..." if api_key else "No API Key found")

# Initialize Client with new AQ Key
client = genai.Client(api_key=api_key)

if __name__ == "__main__":
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Reply with only: Gemini Connected Successfully"
    )
    print(response.text)
