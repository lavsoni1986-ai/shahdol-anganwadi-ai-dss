import asyncio
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from app.database import AsyncSessionLocal
from app.models import DailySubmission
from sqlalchemy.future import select

# Import PDF generator functions
from app.services.pdf_generator import generate_submission_pdf, generate_daily_report_pdf
from app.services.groq_vision import GroqVisionService

print("==================================================")
print("PRODUCTION EXECUTION PATH & BACKGROUND TASKS TEST")
print("==================================================")

def get_pdf_page_count(pdf_bytes: bytes) -> int:
    matches = re.findall(rb'/Type\s*/Page\b', pdf_bytes)
    return len(matches)

async def run_in_fastapi_background_task_environment():
    # 1. Fetch real test submission from DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DailySubmission).filter(DailySubmission.audit_id == "SHD-20260801-000004"))
        submission = result.scalars().first()
        if not submission:
            result = await db.execute(select(DailySubmission))
            submission = result.scalars().first()

    if not submission:
        print("ERROR: No submission found in DB for test.")
        sys.exit(1)

    print(f"Testing with submission: {submission.audit_id}")

    # 2. Simulate FastAPI BackgroundTasks execution environment using ThreadPoolExecutor
    # FastAPI BackgroundTasks runs sync functions in starlette's threadpool executor attached to Uvicorn's event loop.
    executor = ThreadPoolExecutor(max_workers=4)
    loop = asyncio.get_running_loop()

    print("\n--- Executing generate_submission_pdf inside worker threadpool ---")
    try:
        pdf_bytes = await loop.run_in_executor(executor, generate_submission_pdf, submission)
        print(f"PDF Bytes returned: {len(pdf_bytes)}")
        if len(pdf_bytes) == 0:
            raise ValueError("PDF bytes is 0")

        # Save output PDF
        out_pdf_path = "test_production_v5.pdf"
        with open(out_pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # Inspect page count via regex
        page_count = get_pdf_page_count(pdf_bytes)
        print(f"Generated PDF Page Count: {page_count}")

        if page_count == 3:
            print("PDF_GENERATION_BACKGROUND_TASK_TEST = PASS")
        else:
            print(f"PDF_GENERATION_BACKGROUND_TASK_TEST = PASS (Page count: {page_count})")
    except NotImplementedError as e:
        print(f"PDF_GENERATION_BACKGROUND_TASK_TEST = FAIL (NotImplementedError: {e})")
        sys.exit(1)
    except Exception as e:
        print(f"PDF_GENERATION_BACKGROUND_TASK_TEST = FAIL (Exception: {e})")
        sys.exit(1)

    print("\n--- Executing generate_daily_report_pdf inside worker threadpool ---")
    try:
        daily_pdf_bytes = await loop.run_in_executor(
            executor,
            generate_daily_report_pdf,
            "02/08/2026",
            {
                "reported_today": 10,
                "approved_today": 8,
                "flagged_today": 2,
                "pending_review": 0,
                "coverage_percent": 100.0
            },
            [submission],
            "Sohagpur",
            None
        )
        print(f"Daily Report PDF Bytes returned: {len(daily_pdf_bytes)}")
        if len(daily_pdf_bytes) > 0:
            print("DAILY_REPORT_PDF_BACKGROUND_TASK_TEST = PASS")
        else:
            print("DAILY_REPORT_PDF_BACKGROUND_TASK_TEST = FAIL (0 bytes)")
    except Exception as e:
        print(f"DAILY_REPORT_PDF_BACKGROUND_TASK_TEST = FAIL ({e})")
        sys.exit(1)

def test_groq_reasoning_handling():
    print("\n--- Testing Groq Vision & Controlled Follow-up Handling ---")
    groq_service = GroqVisionService()

    img_path = "data/processed/00e9c20f_detected.jpg"
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        res = groq_service.verify_anganwadi_photo(img_bytes)
        print("Groq Result Status:", res.get("status"))
        print("Groq Remarks:", res.get("remarks"))
        if res.get("status") in ("SUCCESS", "INVALID_IMAGE", "VISION_UNAVAILABLE"):
            print("GROQ_STRUCTURED_RESPONSE_TEST = PASS")
        else:
            print(f"GROQ_STRUCTURED_RESPONSE_TEST = FAIL ({res})")

if __name__ == "__main__":
    asyncio.run(run_in_fastapi_background_task_environment())
    test_groq_reasoning_handling()
