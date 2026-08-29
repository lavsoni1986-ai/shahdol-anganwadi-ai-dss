import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from app.database import async_session_maker, init_db
from app.models import DailySubmission, SubmissionStatus
from app.services.ai_vision import process_image_ai_pipeline

REAL_IMAGE = Path("data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg")

async def run_e2e():
    print("=" * 70)
    print("FULL WHATSAPP E2E PIPELINE TEST")
    print("=" * 70)
    
    await init_db()
    
    sub_id = str(uuid.uuid4())
    audit_id = f"SHD-E2E-{sub_id[:6].upper()}"
    
    # Copy real image to target upload location for this sub_id
    uploads_dir = Path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    target_img = uploads_dir / f"{sub_id}.jpg"
    target_img.write_bytes(REAL_IMAGE.read_bytes())
    
    async with async_session_maker() as db:
        submission = DailySubmission(
            submission_id=sub_id,
            audit_id=audit_id,
            worker_phone="916263302625",  # Demo registered worker
            worker_name="Bhagwati Baiga",
            awc_id="23460060604",
            center_name="Pongri 1",
            block_name="Sohagpur",
            district="Shahdol",
            submission_timestamp=datetime.now(timezone.utc),
            whatsapp_timestamp=str(int(time.time())),
            raw_media_id="local_test_media",
            local_media_path=str(target_img.absolute()),
            media_mime_type="image/jpeg",
            status=SubmissionStatus.RECEIVED,
            is_authorized=True,
            ack_sent=True,
        )
        db.add(submission)
        await db.commit()
    
    print(f"Created submission: {sub_id} (Audit ID: {audit_id})")
    print("Triggering process_image_ai_pipeline()...")
    print("-" * 70)
    
    t0 = time.time()
    await process_image_ai_pipeline(sub_id)
    total_elapsed = round(time.time() - t0, 2)
    
    print("-" * 70)
    async with async_session_maker() as db:
        from sqlalchemy import select
        res = await db.execute(select(DailySubmission).where(DailySubmission.submission_id == sub_id))
        sub = res.scalar_one_or_none()
        
        pdf_size = 0
        if sub and sub.pdf_path and Path(sub.pdf_path).exists():
            pdf_size = Path(sub.pdf_path).stat().st_size
            
        print("E2E RESULTS:")
        print(f"  Submission ID        : {sub_id}")
        print(f"  Final Status         : {sub.status if sub else 'N/A'}")
        print(f"  PDF Path             : {sub.pdf_path if sub else 'N/A'}")
        print(f"  PDF File Size        : {pdf_size} bytes ({pdf_size//1024} KB)")
        print(f"  Total E2E Time       : {total_elapsed}s")

if __name__ == "__main__":
    asyncio.run(run_e2e())
