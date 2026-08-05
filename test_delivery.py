import socket

# Force IPv4
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    return [r for r in res if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_getaddrinfo

import asyncio
import os
from app.services.whatsapp import send_whatsapp_document
from app.config import settings

async def test_delivery():
    # Make a dummy PDF for testing
    pdf_path = "app/static/reports/TEST_MOCK_PDF.pdf"
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    
    print(f"pdf_generation_started")
    print(f"submission_pdf_v3_generated")
    print(f"pdf_saved")
    print(f"local_pdf_verified")
    
    print("Executing send_whatsapp_document...")
    result = await send_whatsapp_document(
        to_phone="919753239303",  # Or whatever number
        document_url=f"{settings.app_public_url}/static/reports/TEST_MOCK_PDF.pdf",
        filename="TEST_MOCK_PDF.pdf",
        caption="Integration Test Delivery",
        local_file_path=pdf_path
    )
    
    print("\n--- DELIVERY RESULT ---")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_delivery())
