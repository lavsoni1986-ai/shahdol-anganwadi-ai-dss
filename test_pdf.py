from app.services.pdf_generator import generate_submission_pdf
from datetime import datetime
import json
import os

class MockSubmission:
    def __init__(self):
        self.submission_id = "SUB-TEST-12345"
        self.audit_id = "AUD-12345"
        self.status = "PROCESSED"
        self.is_authorized = True
        self.flag_reason = None
        self.awc_id = "AWC-1001"
        self.center_name = "पोंगड़ी केंद्र"
        self.worker_name = "सुनीता पटेल"
        self.submission_timestamp = datetime.now()
        self.latitude = 23.3015
        self.longitude = 81.3533
        
        self.ai_result_json = json.dumps({
            "is_valid_anganwadi_scene": True,
            "remarks": "आंगनवाड़ी केंद्र में भोजन वितरण का दृश्य स्पष्ट रूप से दिखाई दे रहा है।",
            "confidence_score": 98,
            "image_quality": "CLEAR",
            "yolo_results": {
                "children_count": 16,
                "worker_count": 1,
                "persons_detected": 17,
                "confidence": 69.2,
                "processing_time_ms": 1800,
                "visualized_image_path": "data/processed/pongri_yolo11m_final.jpg"
            }
        })
        self.local_image_path = "data/uploads/2ffe02b1-4014-4eb3-9de5-718714480ddf.jpg"

if __name__ == "__main__":
    sub = MockSubmission()
    pdf_bytes = generate_submission_pdf(sub)
    with open("test_submission.pdf", "wb") as f:
        f.write(pdf_bytes)
    print("PDF generated successfully: test_submission.pdf")
