import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.models import DailySubmission, SubmissionStatus
from app.services.pdf_generator import generate_submission_pdf

print("=" * 60)
print("REAL SUBMISSION PDF RENDER TEST (STANDALONE)")
print("=" * 60)

sub = DailySubmission(
    submission_id="test_standalone_pdf_001",
    audit_id="SHD-20260803-999",
    worker_phone="916263302625",
    worker_name="Bhagwati Baiga",
    awc_id="23460060604",
    center_name="Pongri 1",
    block_name="Sohagpur",
    district="Shahdol",
    latitude="23.2845",
    longitude="81.3532",
    status=SubmissionStatus.PROCESSED,
    local_media_path="data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg",
    ai_result_json='{"status": "SUCCESS", "visible_children_count": 8, "meal_visible": true, "worker_present": true, "remarks": "आंगनवाड़ी में बच्चे उपस्थित हैं।"}'
)

t0 = time.time()
try:
    pdf_bytes = generate_submission_pdf(sub)
    elapsed = round(time.time() - t0, 2)
    print(f"SUCCESS: Generated real submission PDF ({len(pdf_bytes)} bytes) in {elapsed}s")
except Exception as e:
    elapsed = round(time.time() - t0, 2)
    print(f"ERROR after {elapsed}s: {e}")
