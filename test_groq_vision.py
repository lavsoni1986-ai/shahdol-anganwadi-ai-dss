import os
import asyncio
from dotenv import load_dotenv
load_dotenv()

# We need a small 1x1 image for testing
from PIL import Image
import io
import json

from app.services.groq_vision import vision_service

async def run_test():
    img = Image.new('RGB', (10, 10), color = 'red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_bytes = img_byte_arr.getvalue()
    
    print("Testing Groq Vision API...")
    res = vision_service.verify_anganwadi_photo(img_bytes, exif_info=None)
    
    print("Groq Vision Response:")
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(run_test())
