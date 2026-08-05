import asyncio
import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def create_payload(phone: str, msg_id: str, is_media: bool = True):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "123456789"
                            },
                            "contacts": [{"profile": {"name": "Test Worker"}, "wa_id": phone}],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": msg_id,
                                    "timestamp": "1690000000",
                                    "type": "image" if is_media else "text",
                                    "location": {
                                        "latitude": 23.3,
                                        "longitude": 81.3,
                                        "address": "Shahdol, MP"
                                    } if is_media else None,
                                    "image": {
                                        "mime_type": "image/jpeg",
                                        "sha256": "abcdef",
                                        "id": "media_" + msg_id
                                    } if is_media else None,
                                    "text": {"body": "test"} if not is_media else None
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
    return payload

def test_webhook_pongri_1():
    print("Testing Pongri 1...")
    payload = create_payload("916263302625", "msg_pongri_1")
    response = client.post("/webhook", json=payload)
    print("Response:", response.status_code)

def test_webhook_chapa_1():
    print("Testing Chapa 1...")
    payload = create_payload("916261756298", "msg_chapa_1")
    response = client.post("/webhook", json=payload)
    print("Response:", response.status_code)

def test_stats():
    print("Testing stats...")
    response = client.get("/api/v1/dashboard/stats")
    print("Response:", response.status_code)

def test_submissions():
    print("Testing submissions...")
    response = client.get("/api/v1/dashboard/submissions")
    print("Response:", response.status_code)

def test_pdf():
    print("Testing PDF generation...")
    response = client.get("/api/v1/reports/pdf")
    print("Response:", response.status_code)

def test_excel():
    print("Testing Excel generation...")
    response = client.get("/api/v1/reports/excel")
    print("Response:", response.status_code)

if __name__ == "__main__":
    test_webhook_pongri_1()
    test_webhook_chapa_1()
    test_stats()
    test_submissions()
    test_pdf()
    test_excel()

