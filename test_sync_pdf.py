import sys
from app.database import SessionLocal
from app.models import DailySubmission
from app.services.pdf_generator import generate_submission_pdf
from pathlib import Path

def test_sync():
    print("Testing Playwright Generation...")
    db = SessionLocal()
    submission = db.query(DailySubmission).filter(DailySubmission.audit_id == "SHD-20260801-000004").first()
    if not submission:
        print("Not found")
        sys.exit(1)
    
    print("Found submission. Generating PDF...")
    try:
        pdf_bytes = generate_submission_pdf(submission)
        print("Success!")
        
        with open("test_sync_v5.pdf", "wb") as f:
            f.write(pdf_bytes)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_sync()
