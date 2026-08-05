import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.models import DailySubmission, SubmissionStatus
from app.services.pdf_generator import generate_submission_pdf

def build_mock_submission(sub_id: str, audit_id: str, is_groq_429: bool = False) -> DailySubmission:
    if is_groq_429:
        ai_json = '{"status": "VISION_UNAVAILABLE", "reason": "Vision AI Provider (Groq) unavailable or rate-limited.", "fallback": "OpenCV or Manual Verification Required", "yolo_results": {"children_count": 16, "worker_count": 1, "confidence": 75.4, "visualized_image_path": "data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg"}}'
        status = SubmissionStatus.FLAGGED
    else:
        ai_json = '{"status": "SUCCESS", "is_valid_anganwadi_scene": true, "meal_visible": true, "worker_present": true, "remarks": "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं।", "yolo_results": {"children_count": 16, "worker_count": 1, "confidence": 75.4, "visualized_image_path": "data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg"}}'
        status = SubmissionStatus.APPROVED

    return DailySubmission(
        submission_id=sub_id,
        audit_id=audit_id,
        worker_phone="916263302625",
        worker_name="Bhagwati Baiga",
        awc_id="23460060604",
        center_name="Pongri 1",
        block_name="Sohagpur",
        district="Shahdol",
        status=status,
        local_media_path="data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg",
        ai_result_json=ai_json
    )

def test_a_single_submission():
    print("\n--- TEST A: SINGLE NORMAL IMAGE SUBMISSION ---")
    sub = build_mock_submission("sub_test_a", "SHD-TEST-A0001")
    t0 = time.time()
    pdf_bytes = generate_submission_pdf(sub)
    elapsed = round(time.time() - t0, 2)
    assert len(pdf_bytes) > 10000, f"PDF bytes length {len(pdf_bytes)} too small"
    print(f"PASSED TEST A: Generated PDF ({len(pdf_bytes)} bytes) in {elapsed}s")

async def test_b_concurrency_3_submissions():
    print("\n--- TEST B: 3 NEAR-SIMULTANEOUS SUBMISSIONS ---")
    async def task_render(sub_id, audit_id, delay):
        if delay > 0:
            await asyncio.sleep(delay)
        sub = build_mock_submission(sub_id, audit_id)
        t0 = time.time()
        pdf = await asyncio.to_thread(generate_submission_pdf, sub)
        el = round(time.time() - t0, 2)
        print(f"  [{audit_id}] Generated {len(pdf)} bytes in {el}s")
        return len(pdf)

    t0 = time.time()
    res = await asyncio.gather(
        task_render("sub_b1", "SHD-TEST-B0001", 0.0),
        task_render("sub_b2", "SHD-TEST-B0002", 0.5),
        task_render("sub_b3", "SHD-TEST-B0003", 1.0),
    )
    total_el = round(time.time() - t0, 2)
    assert all(r > 10000 for r in res), "One or more PDFs failed in concurrency test"
    print(f"PASSED TEST B: All 3 concurrent PDFs rendered successfully in {total_el}s total")

def test_c_groq_429_fallback():
    print("\n--- TEST C: GROQ RETURNS 429 (VISION_UNAVAILABLE FALLBACK) ---")
    sub = build_mock_submission("sub_test_c", "SHD-TEST-C0001", is_groq_429=True)
    t0 = time.time()
    pdf_bytes = generate_submission_pdf(sub)
    elapsed = round(time.time() - t0, 2)
    assert len(pdf_bytes) > 10000, "PDF generation failed during Groq 429 fallback"
    print(f"PASSED TEST C: Fallback PDF generated ({len(pdf_bytes)} bytes) in {elapsed}s with VISION_UNAVAILABLE status")

def test_d_renderer_failure_isolation():
    print("\n--- TEST D: PDF RENDERER INTENTIONAL FAILURE ISOLATION ---")
    from app.services.pdf_generator import _run_playwright_in_process
    t0 = time.time()
    failed = False
    try:
        _run_playwright_in_process("<html><head><script>throw new Error('boom');</script></head><body>Bad</body></html>")
    except Exception as e:
        failed = True
        print(f"  Handled expected failure gracefully: {e}")
    
    # Verify subsequent valid render still works without crash
    sub = build_mock_submission("sub_test_d", "SHD-TEST-D0001")
    pdf_bytes = generate_submission_pdf(sub)
    elapsed = round(time.time() - t0, 2)
    assert len(pdf_bytes) > 10000, "Subsequent PDF failed after previous error"
    print(f"PASSED TEST D: Error handled cleanly and subsequent PDF generated successfully in {elapsed}s")

def test_e_repeated_renders(count=5):
    print(f"\n--- TEST E: REPEATED PDF GENERATION ({count} CONSECUTIVE RENDERS) ---")
    timings = []
    sub = build_mock_submission("sub_test_e", "SHD-TEST-E0001")
    for i in range(count):
        t0 = time.time()
        pdf = generate_submission_pdf(sub)
        el = round(time.time() - t0, 2)
        timings.append(el)
        print(f"  Run #{i+1}: {el}s ({len(pdf)} bytes)")
    
    print(f"  Timings: {timings}")
    assert max(timings) < 25.0, f"Latency spike detected in repeated renders: {timings}"
    print(f"PASSED TEST E: All {count} consecutive renders completed within stable performance boundaries")

async def run_all_tests():
    print("=" * 80)
    print("RUNNING COMPREHENSIVE PRODUCTION REGRESSION & STABILITY TEST SUITE")
    print("=" * 80)
    test_a_single_submission()
    await test_b_concurrency_3_submissions()
    test_c_groq_429_fallback()
    test_d_renderer_failure_isolation()
    test_e_repeated_renders(count=5)
    print("\n" + "=" * 80)
    print("ALL 5 TESTS (TEST A, TEST B, TEST C, TEST D, TEST E) PASSED PERFECTLY!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
