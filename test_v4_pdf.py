import os
import asyncio
import json
from app.database import get_db
from app.models import DailySubmission
from app.services.pdf_generator import generate_submission_pdf
from sqlalchemy.orm import Session
from sqlalchemy import select

async def main():
    async for db in get_db():
        result = await db.execute(select(DailySubmission).where(DailySubmission.audit_id == "SHD-20260801-000003"))
        submission = result.scalars().first()
        
        if submission:
            print("Found submission. Generating PDF...")
            pdf_bytes = generate_submission_pdf(submission)
            
            output_path = "test_v4.pdf"
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"PDF saved to {output_path}")
        else:
            print("Submission not found!")
        break

if __name__ == "__main__":
    asyncio.run(main())
