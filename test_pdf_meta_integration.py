import asyncio
import os
from app.database import AsyncSessionLocal
from app.models import DailySubmission
from sqlalchemy.future import select
from app.services.pdf_generator import generate_submission_pdf
from app.services.whatsapp import send_whatsapp_document
from pathlib import Path

async def run_integration_test():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DailySubmission).filter(DailySubmission.audit_id == "SHD-20260801-000004"))
        submission = result.scalars().first()
        
        if not submission:
            print("Submission SHD-20260801-000004 not found in DB")
            result = await db.execute(select(DailySubmission))
            submission = result.scalars().first()
            if not submission:
                print("No submissions found.")
                return

    print(f"Testing with submission: {submission.audit_id}, phone: {submission.worker_phone}")

    print("Generating PDF...")
    try:
        pdf_bytes = generate_submission_pdf(submission)
    except Exception as e:
        print(f"PDF Generation failed: {e}")
        return

    reports_dir = Path("app/static/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"test_v5.pdf"
    pdf_path = reports_dir / pdf_filename
    
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
        f.flush()
        os.fsync(f.fileno())

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        print("PDF file is empty or missing.")
        return

    print(f"PDF generated successfully at {pdf_path}, size: {pdf_path.stat().st_size} bytes")

    # Send document
    print("Sending WhatsApp Document...")
    try:
        response = await send_whatsapp_document(
            to_phone=submission.worker_phone,
            document_url=f"https://api.bharatosdemo24.com/static/reports/{pdf_filename}",
            filename=pdf_filename,
            caption="AWC Verification Report (Test)",
            local_file_path=str(pdf_path.absolute())
        )
        if response and response.get("success"):
            print("WhatsApp delivery successful!")
            print(response)
        else:
            print(f"WhatsApp delivery failed: {response}")
    except Exception as e:
        print(f"WhatsApp delivery failed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(run_integration_test())
