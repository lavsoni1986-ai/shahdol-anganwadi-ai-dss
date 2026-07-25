import pytest
import asyncio
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, AsyncSessionLocal
from app.models import DailySubmission, WebhookLog
from sqlalchemy import select

def test_webhook_post_ingestion():
    # Initialize DB schema
    asyncio.run(init_db())
    
    client = TestClient(app)
    
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1160226573849828",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551848528",
                                "phone_number_id": "1160226573849828"
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Sarita Singh"},
                                    "wa_id": "919876543210"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": f"wamid.TEST_{uuid.uuid4().hex[:12]}",
                                    "timestamp": "1721810000",
                                    "type": "image",
                                    "image": {
                                        "caption": "रामपुर आँगनवाड़ी केंद्र दैनिक रिपोर्ट",
                                        "mime_type": "image/jpeg",
                                        "sha256": "abcdef1234567890",
                                        "id": "999888777"
                                    }
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }

    response = client.post("/webhook", json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    print("\n[OK] Webhook POST responded with 200 OK:", response.json())

    # Verify DB persistence
    async def verify_db():
        async with AsyncSessionLocal() as session:
            stmt = select(DailySubmission).where(DailySubmission.worker_phone == "919876543210")
            result = await session.execute(stmt)
            sub = result.scalars().first()
            assert sub is not None, "DailySubmission record not found in DB!"
            print(f"[OK] DailySubmission saved in DB: ID={sub.id}, AuditID={sub.audit_id}, Phone={sub.worker_phone}, Status={sub.status}, image_hash={sub.image_hash}")
            
            stmt_log = select(WebhookLog)
            result_log = await session.execute(stmt_log)
            log_item = result_log.scalars().first()
            assert log_item is not None, "WebhookLog record not found in DB!"
            print(f"[OK] WebhookLog saved in DB: LogID={log_item.id}, ReceivedAt={log_item.received_at}")

    asyncio.run(verify_db())

if __name__ == "__main__":
    test_webhook_post_ingestion()
