import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.models import DailySubmission, SubmissionStatus
from app.services.pdf_generator import generate_submission_pdf

def build_test_submission(sub_id: str, audit_id: str) -> DailySubmission:
    return DailySubmission(
        submission_id=sub_id,
        audit_id=audit_id,
        worker_phone="916263302625",
        worker_name="Bhagwati Baiga",
        awc_id="23460060604",
        center_name="Pongri 1",
        block_name="Sohagpur",
        district="Shahdol",
        status=SubmissionStatus.FLAGGED,
        local_media_path="data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg",
        ai_result_json='{"status": "SUCCESS", "yolo_results": {"children_count": 16, "worker_count": 1, "confidence": 75.4, "visualized_image_path": "data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg"}}'
    )

async def render_task(sub_id: str, audit_id: str, delay: float):
    if delay > 0:
        await asyncio.sleep(delay)
    sub = build_test_submission(sub_id, audit_id)
    print(f"[{time.strftime('%H:%M:%S')}] START PDF generation for {audit_id}")
    t0 = time.time()
    try:
        pdf_bytes = await asyncio.to_thread(generate_submission_pdf, sub)
        elapsed = round(time.time() - t0, 2)
        print(f"[{time.strftime('%H:%M:%S')}] SUCCESS PDF {audit_id}: {len(pdf_bytes)} bytes in {elapsed}s")
        return (audit_id, True, elapsed, len(pdf_bytes))
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        print(f"[{time.strftime('%H:%M:%S')}] FAILED PDF {audit_id} after {elapsed}s: {e}")
        return (audit_id, False, elapsed, str(e))

async def main():
    print("=" * 70)
    print("CONCURRENCY REPRODUCTION TEST — 3 SIMULTANEOUS PDF RENDERS")
    print("=" * 70)
    t_start = time.time()
    tasks = [
        render_task("sub_001", "SHD-TEST-000001", 0.0),
        render_task("sub_002", "SHD-TEST-000002", 1.0),
        render_task("sub_003", "SHD-TEST-000003", 2.0),
    ]
    results = await asyncio.gather(*tasks)
    total_elapsed = round(time.time() - t_start, 2)
    print("\n" + "=" * 70)
    print(f"TOTAL CONCURRENCY TEST TIME: {total_elapsed}s")
    for r in results:
        print(f"  Audit ID: {r[0]:<16} | Status: {'PASS' if r[1] else 'FAIL'} | Time: {r[2]}s | Result: {r[3]}")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
