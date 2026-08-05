import asyncio
from app.database import AsyncSessionLocal
from app.services.worker_auth import authenticate_worker
from test_e2e import test_webhook_pongri_1, test_webhook_chapa_1, create_payload, client
import traceback

async def test_auth():
    print("--- AUTHENTICATION TEST ---")
    async with AsyncSessionLocal() as session:
        # 1. 6263302625
        res1 = await authenticate_worker("6263302625", session)
        print(f"1. 6263302625: {'Success' if res1.is_authorized else 'Rejected'} (Expected: Success)")
        
        # 2. 6261756298
        res2 = await authenticate_worker("6261756298", session)
        print(f"2. 6261756298: {'Success' if res2.is_authorized else 'Rejected'} (Expected: Success)")
        
        # 3. 9753239303 (Demo)
        res3 = await authenticate_worker("9753239303", session)
        print(f"3. 9753239303 (Demo): {'Success' if res3.is_authorized else 'Rejected'} (Expected: Success)")
        
        # 4. Unknown
        res4 = await authenticate_worker("9999999999", session)
        print(f"4. 9999999999: {'Success' if res4.is_authorized else 'Rejected'} (Expected: Rejected)")

def test_e2e():
    print("--- END TO END TEST ---")
    # Existing authorized workers
    test_webhook_pongri_1()
    test_webhook_chapa_1()
    
    # Demo Worker E2E
    print("Testing Demo Worker...")
    payload = create_payload("919753239303", "msg_demo_1")
    response = client.post("/webhook", json=payload)
    print("Response:", response.status_code)
    
    # Unknown Worker E2E
    print("Testing Unknown Worker...")
    payload = create_payload("919999999999", "msg_unknown_1")
    response = client.post("/webhook", json=payload)
    print("Response:", response.status_code)

if __name__ == "__main__":
    try:
        asyncio.run(test_auth())
    except Exception as e:
        traceback.print_exc()
