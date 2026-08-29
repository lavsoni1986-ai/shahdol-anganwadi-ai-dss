import asyncio
import os
import sys

# Test 1: Import tests
print("--- TEST 1: IMPORTS ---")
try:
    from app.services.pdf_generator import generate_submission_pdf, generate_daily_report_pdf
    print("generate_submission_pdf import: PASS")
    print("generate_daily_report_pdf import: PASS")
except Exception as e:
    print(f"generate_submission_pdf import: FAIL ({e})")
    print(f"generate_daily_report_pdf import: FAIL ({e})")
    sys.exit(1)

# Test 2: FastAPI Startup
print("\n--- TEST 2: FASTAPI STARTUP ---")
try:
    from app.main import app
    print("FastAPI app import: PASS")
except Exception as e:
    print(f"FastAPI app import: FAIL ({e})")
    sys.exit(1)

# Test 3: Submission PDF & Test 4: Daily PDF
print("\n--- TEST 3: SUBMISSION PDF & TEST 4: DAILY PDF ---")
from app.database import AsyncSessionLocal
from app.models import DailySubmission
from sqlalchemy.future import select

async def test_pdfs():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DailySubmission).filter(DailySubmission.audit_id == "SHD-20260801-000004"))
        submission = result.scalars().first()
        if not submission:
            result = await db.execute(select(DailySubmission))
            submission = result.scalars().first()

    if not submission:
        print("No submission found for testing PDF.")
        return

    # Submission PDF
    print(f"Testing generate_submission_pdf with submission: {submission.audit_id}")
    try:
        pdf_bytes = generate_submission_pdf(submission)
        if len(pdf_bytes) > 0:
            print(f"generate_submission_pdf: PASS ({len(pdf_bytes)} bytes)")
            with open("test_submission.pdf", "wb") as f:
                f.write(pdf_bytes)
        else:
            print("generate_submission_pdf: FAIL (0 bytes)")
    except Exception as e:
        print(f"generate_submission_pdf: FAIL ({e})")

    # Daily PDF
    print("\nTesting generate_daily_report_pdf")
    try:
        daily_pdf_bytes = generate_daily_report_pdf(
            report_date="02/08/2026",
            stats={
                "reported_today": 10,
                "approved_today": 8,
                "flagged_today": 2,
                "pending_review": 0,
                "coverage_percent": 100.0
            },
            submissions=[submission],
            block_name="Sohagpur",
            status_filter=None
        )
        if len(daily_pdf_bytes) > 0:
            print(f"generate_daily_report_pdf: PASS ({len(daily_pdf_bytes)} bytes)")
            with open("test_daily.pdf", "wb") as f:
                f.write(daily_pdf_bytes)
        else:
            print("generate_daily_report_pdf: FAIL (0 bytes)")
    except Exception as e:
        print(f"generate_daily_report_pdf: FAIL ({e})")

# Test 5: Groq JSON validation retry
print("\n--- TEST 5: GROQ RETRY LOGIC ---")
from app.services.groq_vision import GroqVisionService

def test_groq():
    service = GroqVisionService()
    # Mock requests.post to first return 400 with json_validate_failed, then 200 on retry
    import requests
    original_post = requests.post
    
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text
        def json(self):
            import json
            return json.loads(self.text)

    call_count = 0
    def mock_post(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockResponse(400, '{"error": {"code": "json_validate_failed"}}')
        else:
            return MockResponse(200, '{"choices": [{"message": {"content": "{\\"schema_version\\": \\"1.0\\", \\"is_valid_anganwadi_scene\\": true}"}}]}')
    
    requests.post = mock_post
    try:
        res = service._call_groq_vision_rest(b"dummy", "prompt")
        if res.get("success") and call_count == 2:
            print("Groq Retry Logic: PASS")
        else:
            print(f"Groq Retry Logic: FAIL (success={res.get('success')}, call_count={call_count})")
    except Exception as e:
        print(f"Groq Retry Logic: FAIL ({e})")
    finally:
        requests.post = original_post

if __name__ == "__main__":
    asyncio.run(test_pdfs())
    test_groq()
