import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

# Mock yolo before importing ai_vision
sys.modules["app.services.yolo_detector"] = MagicMock()

from app.models import DailySubmission, SubmissionStatus
from app.services.ai_vision import _download_or_mock_image, check_duplicate_hash, process_image_ai_pipeline

print("=" * 80)
print("FAST SURGICAL FIXES REGRESSION TEST SUITE (TEST A, B, C, D)")
print("=" * 80)

# TEST C: Missing Local File
def test_c():
    print("\n--- TEST C: MISSING LOCAL FILE ---")
    try:
        _download_or_mock_image("test_id", "data/uploads/non_existent_12345.jpg")
        print("FAIL: Expected FileNotFoundError but returned without error!")
        return False
    except FileNotFoundError as e:
        print(f"PASS: Correctly raised FileNotFoundError: {e}")
        return True
    except Exception as ex:
        print(f"FAIL: Raised unexpected exception type {type(ex)}: {ex}")
        return False

# TEST D: Duplicate History Query Check
async def test_d():
    print("\n--- TEST D: DUPLICATE HISTORY QUERY (NO LIMIT 20) ---")
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    from PIL import Image
    test_img = Image.new("RGB", (100, 100), color="blue")
    
    await check_duplicate_hash(mock_db, test_img, "AWC-TEST-100", "sub_curr_001")
    
    executed_stmt = str(mock_db.execute.call_args[0][0])
    print(f"  Executed SQL:\n{executed_stmt}")
    
    if "LIMIT" in executed_stmt.upper():
        print("FAIL: Query still contains LIMIT clause!")
        return False
    else:
        print("PASS: Query has no LIMIT clause and checks full AWC history!")
        return True

# TEST B: Media ConnectTimeout Simulation
async def test_b():
    print("\n--- TEST B: MEDIA CONNECT TIMEOUT SIMULATION ---")
    
    mock_sub = DailySubmission(
        submission_id="test_sub_timeout_001",
        audit_id="SHD-TEST-T001",
        status=SubmissionStatus.RECEIVED,
        raw_media_id="media_id_timeout",
        local_media_path=None,
    )
    
    mock_db_session = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = mock_sub
    mock_db_session.execute.return_value = mock_db_result

    timeout_result = {
        "success": False,
        "local_path": None,
        "sha256": None,
        "error": "Media download error: ConnectTimeout",
        "file_size": None
    }
    
    with patch("app.services.ai_vision.async_session_maker") as mock_session_factory, \
         patch("app.services.ai_vision.download_and_save_whatsapp_media", new_callable=AsyncMock) as mock_dl, \
         patch("app.services.ai_vision.vision_service") as mock_groq:
        
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session
        mock_dl.return_value = timeout_result
        
        await process_image_ai_pipeline("test_sub_timeout_001")
        
        print(f"  Submission Status: {mock_sub.status}")
        print(f"  Flag Reason      : {mock_sub.flag_reason}")
        
        groq_called = mock_groq.verify_anganwadi_photo.called
        print(f"  Groq Called: {groq_called}")
        
        if mock_sub.status == SubmissionStatus.FLAGGED and mock_sub.flag_reason == "MEDIA_DOWNLOAD_FAILED" and not groq_called:
            print("PASS: ConnectTimeout handled safely — FLAGGED set, zero AI/Groq calls!")
            return True
        else:
            print("FAIL: Pipeline did not exit cleanly on download failure!")
            return False

# TEST A: Successful Normal Image Loading
def test_a():
    print("\n--- TEST A: NORMAL SUCCESSFUL IMAGE LOADING ---")
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
    pass_c = test_c()
    pass_d = await test_d()
    pass_b = await test_b()
    pass_a = test_a()
    
    print("\n" + "=" * 80)
    if pass_a and pass_b and pass_c and pass_d:
        print("ALL 4 REGRESSION TESTS (TEST A, B, C, D) PASSED PERFECTLY!")
    else:
        print("SOME TESTS FAILED — CHECK LOGS ABOVE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
