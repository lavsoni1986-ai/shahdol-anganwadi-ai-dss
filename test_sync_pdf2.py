import asyncio
from app.database import AsyncSessionLocal
from app.models import DailySubmission
from sqlalchemy.future import select
from app.services.pdf_generator import generate_submission_pdf

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DailySubmission).filter(DailySubmission.audit_id == "SHD-20260801-000004"))
        submission = result.scalars().first()
    
    print("Generating PDF...")
    try:
        # Calls the synchronous generate_submission_pdf which spawns a thread
        pdf_bytes = generate_submission_pdf(submission)
        with open("test_sync_v5.pdf", "wb") as f:
            f.write(pdf_bytes)
        print("Success! Size:", len(pdf_bytes))
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
