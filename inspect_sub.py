import asyncio
import json
from app.database import AsyncSessionLocal
from app.models import DailySubmission
from sqlalchemy.future import select

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(DailySubmission))
        subs = res.scalars().all()
        print(f"Total submissions in DB: {len(subs)}")
        for sub in subs[:5]:
            print("------------------------------------------")
            print("ID:", sub.id)
            print("Submission ID:", sub.submission_id)
            print("Audit ID:", sub.audit_id)
            print("Submission Timestamp:", repr(sub.submission_timestamp))
            print("WhatsApp Timestamp:", repr(sub.whatsapp_timestamp))
            print("Created At:", repr(sub.created_at))
            print("Latitude:", repr(sub.latitude))
            print("Longitude:", repr(sub.longitude))
            print("Status:", repr(sub.status))
            print("Flag Reason:", repr(sub.flag_reason))
            print("AI Result JSON:", sub.ai_result_json)

if __name__ == "__main__":
    asyncio.run(check())
