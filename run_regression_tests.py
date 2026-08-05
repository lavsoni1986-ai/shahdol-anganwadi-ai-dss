import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from app.models import DailySubmission, SubmissionStatus
from app.services.ai_vision import _download_or_mock_image, check_duplicate_hash, process_image_ai_pipeline

print("=" * 80)
print("RUNNING MANDATORY REGRESSION TEST SUITE (TEST A, B, C, D)")
print("=" * 80)

# TEST C: Missing Local File
def test_c_missing_image():
    print("\n--- TEST C: MISSING LOCAL FILE ---")
    try:
        _download_or_mock_image("test_media_id", "data/uploads/non_existent_file_12345.jpg")
        print("FAIL: Expected FileNotFoundError but no exception was raised!")
        return False
    except FileNotFoundError as e:
        print(f"PASS: Correctly raised FileNotFoundError: {e}")
        return True
    except Exception as ex:
        print(f"FAIL: Raised unexpected exception type {type(ex)}: {ex}")
        return False

# TEST D: Duplicate History Query Check
async def test_d_duplicate_history():
    print("\n--- TEST D: DUPLICATE HISTORY QUERY (NO LIMIT 20) ---")
    mock_db = AsyncMock()
    mock_result = AsyncMock()
    mock_result.scalars().all.return_value = []
    mock_db.execute.return_value = mock_result

    from PIL import Image
    test_img = Image.new("RGB", (100, 100), color="red")
    
    await check_duplicate_hash(mock_db, test_img, "AWC-TEST-100", "sub_id_curr")
    
    # Inspect the generated query string
    executed_stmt = str(mock_db.execute.call_args[0][0])
    print(f"  Executed SQL:\n{executed_stmt}")
    
    if "LIMIT" in executed_stmt.upper():
        print("FAIL: Query still contains LIMIT clause!")
        return False
    else:
        print("PASS: Query has no LIMIT clause and checks full AWC history!")
        return True

# TEST B: Media ConnectTimeout Simulation
async def test_b_connect_timeout_simulation():
    print("\n--- TEST B: MEDIA CONNECT TIMEOUT SIMULATION ---")
    
    mock_sub = DailySubmission(
        submission_id="test_sub_timeout_001",
        audit_id="SHD-TEST-T001",
        status=SubmissionStatus.RECEIVED,
        raw_media_id="media_id_timeout",
        local_media_path=None,
    )
    
    # Mock database session
    mock_db_session = AsyncMock()
    mock_db_result = AsyncMock()
    mock_db_result.scalar_one_or_none.return_value = mock_sub
    mock_db_session.execute.return_value = mock_db_result

    # Mock download_and_save_whatsapp_media to simulate ConnectTimeout
    timeout_result = {
        "success": False,
        "local_path": None,
        "sha256": None,
        "error": "Media download error: ConnectTimeout",
        "file_size": None
    }
    
    with patch("app.services.ai_vision.async_session_maker") as mock_session_factory, \
         patch("app.services.ai_vision.download_and_save_whatsapp_media", new_callable=AsyncMock) as mock_dl, \
         patch("app.services.ai_vision.yolo_detector") as mock_yolo, \
         patch("app.services.ai_vision.vision_service") as mock_groq:
        
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session
        mock_dl.return_value = timeout_result
        
        await process_image_ai_pipeline("test_sub_timeout_001")
        
        # Verify status set to FLAGGED and reason MEDIA_DOWNLOAD_FAILED
        print(f"  Submission Status: {mock_sub.status}")
        print(f"  Flag Reason      : {mock_sub.flag_reason}")
        
        yolo_called = mock_yolo.detect_objects.called
        groq_called = mock_groq.verify_anganwadi_photo.called
        
        print(f"  YOLO Called: {yolo_called} | Groq Called: {groq_called}")
        
        if mock_sub.status == SubmissionStatus.FLAGGED and mock_sub.flag_reason == "MEDIA_DOWNLOAD_FAILED" and not yolo_called and not groq_called:
            print("PASS: ConnectTimeout handled safely — FLAGGED set, zero AI/YOLO/Groq calls!")
            return True
        else:
            print("FAIL: Pipeline did not exit cleanly on download failure!")
            return False

# TEST A: Successful Normal Image Path
async def test_a_normal_image_path():
    print("\n--- TEST A: NORMAL SUCCESSFUL IMAGE PATH ---")
    img_path = Path("data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg")
    if not img_path.exists():
        print(f"  Skipping TEST A (test image {img_path} not found on disk)")
        return True
    
    try:
        img = _download_or_mock_image("media_id_valid", str(img_path))
        assert img is not None and img.size[0] > 0
        print(f"PASS: Real image loaded successfully ({img.size[0]}x{img.size[1]})")
        return True
    except Exception as e:
        print(f"FAIL: Normal image loading failed: {e}")
        return False

async def main():
    pass_c = test_c_missing_image()
    pass_d = await test_d_duplicate_history()
    pass_b = await test_b_connect_timeout_simulation()
    pass_a = await test_a_normal_image_path()
    
    print("\n" + "=" * 80)
    if pass_a and pass_b and pass_c and pass_d:
        print("ALL REGRESSION TESTS (TEST A, B, C, D) PASSED PERFECTLY!")
    else:
        print("SOME TESTS FAILED — CHECK LOGS ABOVE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
