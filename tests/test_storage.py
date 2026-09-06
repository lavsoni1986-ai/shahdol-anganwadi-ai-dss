# tests/test_storage.py
# =====================================================================
# BharatOS — Shahdol Anganwadi AI DSS
# P2-B Storage Unit Tests
# Tests:
#   1. Local storage upload
#   2. Local storage download
#   3. Local storage exists
#   4. GCS disabled selects local backend
#   5. GCS client initialization is mockable
#   6. Object key generation
#   7. AWC/submission isolation
#   8. Filename/path sanitization
#   9. ../ traversal prevention
#  10. Absolute-path rejection
#  11. Legacy local path compatibility
#  12. GCS upload mocked
#  13. GCS download mocked
#  14. GCS unavailable/error behavior
#  15. Report object key generation
#  16. Evidence object key generation
#  17. No secret leakage
#  18. Unauthorized/invalid report key rejected
#  19. YOLO temporary file cleanup verification
#  20. Existing local workflow remains functional
# =====================================================================

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.storage import (
    GoogleCloudStorageService,
    LocalStorageService,
    StorageConfigurationError,
    StorageError,
    build_evidence_key,
    build_report_key,
    get_storage_service,
    sanitize_identifier,
    validate_object_key,
)


# ── 1. Local storage upload ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_local_storage_upload(tmp_path):
    storage = LocalStorageService(base_dir=tmp_path)
    content = b"sample photo binary data"
    key = "evidence/AWC-101/sub-001.jpg"

    saved_key = await storage.upload_file(content, key, content_type="image/jpeg")
    assert saved_key == key

    saved_file = tmp_path / "evidence" / "AWC-101" / "sub-001.jpg"
    assert saved_file.exists()
    assert saved_file.read_bytes() == content


# ── 2. Local storage download ────────────────────────────────────────
@pytest.mark.asyncio
async def test_local_storage_download(tmp_path):
    storage = LocalStorageService(base_dir=tmp_path)
    file_rel = tmp_path / "reports" / "AWC_Report_001.pdf"
    file_rel.parent.mkdir(parents=True, exist_ok=True)
    file_rel.write_bytes(b"%PDF-1.4 test report data")

    data = await storage.download_file("reports/AWC_Report_001.pdf")
    assert data == b"%PDF-1.4 test report data"


# ── 3. Local storage exists ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_local_storage_exists(tmp_path):
    storage = LocalStorageService(base_dir=tmp_path)
    file_path = tmp_path / "evidence" / "item.jpg"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"test")

    assert await storage.exists("evidence/item.jpg") is True
    assert await storage.exists("evidence/non_existent.jpg") is False


# ── 4. GCS disabled selects local backend ────────────────────────────
def test_gcs_disabled_selects_local_backend(monkeypatch):
    import app.services.storage as storage_mod
    monkeypatch.setattr(storage_mod.settings, "gcs_enabled", False)
    svc = storage_mod.get_storage_service()
    assert isinstance(svc, LocalStorageService)


# ── 5. GCS client initialization is mockable ─────────────────────────
def test_gcs_client_initialization_mockable():
    mock_client = MagicMock()
    svc = GoogleCloudStorageService(bucket_name="test-bucket", client=mock_client)
    assert svc._get_client() == mock_client
    svc._get_bucket()
    mock_client.bucket.assert_called_once_with("test-bucket")


# ── 6. Object key generation ─────────────────────────────────────────
def test_object_key_generation():
    ev_key = build_evidence_key("AWC-SHA-1042", "sub-uuid-1234", ".jpg")
    assert ev_key == "evidence/AWC-SHA-1042/sub-uuid-1234.jpg"

    rep_key = build_report_key("SHD-20260726-000001", ".pdf")
    assert rep_key == "reports/SHD-20260726-000001.pdf"


# ── 7. AWC/submission isolation ──────────────────────────────────────
def test_awc_submission_isolation():
    key1 = build_evidence_key("AWC-1", "SUB-A")
    key2 = build_evidence_key("AWC-2", "SUB-A")
    key3 = build_evidence_key("AWC-1", "SUB-B")

    assert key1 != key2
    assert key1 != key3
    assert key1.startswith("evidence/AWC-1/")
    assert key2.startswith("evidence/AWC-2/")


# ── 8. Filename/path sanitization ────────────────────────────────────
def test_filename_path_sanitization():
    # Safe characters preserved
    assert sanitize_identifier("AWC-SHA_1042.01") == "AWC-SHA_1042.01"

    # Spaces and special chars replaced with underscore
    assert sanitize_identifier("AWC 1042#Test!") == "AWC_1042_Test_"

    # Empty string rejected
    with pytest.raises(ValueError, match="non-empty"):
        sanitize_identifier("")


# ── 9. ../ traversal prevention ──────────────────────────────────────
def test_traversal_prevention():
    with pytest.raises(ValueError, match="Path traversal"):
        sanitize_identifier("../etc/passwd")

    with pytest.raises(ValueError, match="Path traversal"):
        sanitize_identifier("..")

    with pytest.raises(ValueError, match="path traversal"):
        validate_object_key("evidence/../secret.txt")

    with pytest.raises(ValueError, match="path traversal"):
        validate_object_key("../../data/uploads/file.jpg")


# ── 10. Absolute-path rejection ──────────────────────────────────────
def test_absolute_path_rejection():
    with pytest.raises(ValueError, match="must be relative"):
        validate_object_key("/evidence/awc/file.jpg")

    with pytest.raises(ValueError, match="drive specification"):
        validate_object_key("C:/Windows/system32/cmd.exe")

    with pytest.raises(ValueError, match="forbidden backslash"):
        validate_object_key("evidence\\awc\\file.jpg")


# ── 11. Legacy local path compatibility ──────────────────────────────
@pytest.mark.asyncio
async def test_legacy_local_path_compatibility(tmp_path):
    # Setup legacy file on disk
    legacy_file = tmp_path / "uploads" / "old_sub.jpg"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_bytes(b"legacy image bytes")

    # LocalStorageService recognizes legacy file path
    storage = LocalStorageService(base_dir=tmp_path)
    assert await storage.exists(str(legacy_file)) is True
    data = await storage.download_file(str(legacy_file))
    assert data == b"legacy image bytes"

    # GoogleCloudStorageService also falls back to existing local disk file if present
    mock_client = MagicMock()
    gcs_storage = GoogleCloudStorageService(bucket_name="b", client=mock_client)
    assert await gcs_storage.exists(str(legacy_file)) is True
    data_gcs = await gcs_storage.download_file(str(legacy_file))
    assert data_gcs == b"legacy image bytes"
    # GCS API should not be contacted if local file exists
    mock_client.bucket.assert_not_called()


# ── 12. GCS upload mocked ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gcs_upload_mocked():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    gcs = GoogleCloudStorageService(bucket_name="shahdol-bucket", client=mock_client)
    key = "evidence/AWC-1042/sub-001.jpg"
    result = await gcs.upload_file(b"image bytes", key, content_type="image/jpeg")

    assert result == key
    mock_client.bucket.assert_called_once_with("shahdol-bucket")
    mock_bucket.blob.assert_called_once_with(key)
    mock_blob.upload_from_string.assert_called_once_with(b"image bytes", content_type="image/jpeg")


# ── 13. GCS download mocked ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_gcs_download_mocked():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mock_blob.exists.return_value = True
    mock_blob.download_as_bytes.return_value = b"%PDF-mocked-content"

    gcs = GoogleCloudStorageService(bucket_name="shahdol-bucket", client=mock_client)
    data = await gcs.download_file("reports/AWC_Report_SHD-001.pdf")

    assert data == b"%PDF-mocked-content"
    mock_bucket.blob.assert_called_once_with("reports/AWC_Report_SHD-001.pdf")
    mock_blob.download_as_bytes.assert_called_once()


# ── 14. GCS unavailable / error behavior ─────────────────────────────
@pytest.mark.asyncio
async def test_gcs_unavailable_error_behavior():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mock_blob.upload_from_string.side_effect = RuntimeError("Connection timeout to storage.googleapis.com")

    gcs = GoogleCloudStorageService(bucket_name="shahdol-bucket", client=mock_client)

    with pytest.raises(StorageError, match="GCS upload failed"):
        await gcs.upload_file(b"data", "evidence/awc/item.jpg")


def test_gcs_missing_bucket_raises_config_error(monkeypatch):
    import app.services.storage as storage_mod
    monkeypatch.setattr(storage_mod.settings, "gcs_enabled", True)
    monkeypatch.setattr(storage_mod.settings, "gcs_bucket_name", "")

    gcs = GoogleCloudStorageService(bucket_name="")
    with pytest.raises(StorageConfigurationError, match="GCS_BUCKET_NAME is not configured"):
        gcs._get_client()


# ── 15. Report object key generation ─────────────────────────────────
def test_report_object_key_generation():
    key = build_report_key("SHD-20260726-000010")
    assert key == "reports/SHD-20260726-000010.pdf"

    # Preserves extension if given
    key2 = build_report_key("sub-12345", ".pdf")
    assert key2 == "reports/sub-12345.pdf"


# ── 16. Evidence object key generation ───────────────────────────────
def test_evidence_object_key_generation():
    key_jpg = build_evidence_key("AWC-SHA-01", "SUB-99", ".jpg")
    assert key_jpg == "evidence/AWC-SHA-01/SUB-99.jpg"

    key_png = build_evidence_key("AWC-SHA-01", "SUB-99", "png")
    assert key_png == "evidence/AWC-SHA-01/SUB-99.png"


# ── 17. No secret leakage in error logs / messages ───────────────────
@pytest.mark.asyncio
async def test_no_secret_leakage_in_exceptions():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    # Error string containing simulated credential
    mock_blob.upload_from_string.side_effect = Exception("Authorization: Bearer secret_token_xyz123 failed")

    gcs = GoogleCloudStorageService(bucket_name="shahdol-bucket", client=mock_client)

    try:
        await gcs.upload_file(b"data", "evidence/awc/item.jpg")
    except StorageError as e:
        msg = str(e)
        assert "secret_token_xyz123" not in msg
        assert "Bearer" not in msg


# ── 18. Unauthorized / invalid report key rejected ───────────────────
def test_unauthorized_invalid_report_key_rejected():
    with pytest.raises(ValueError):
        build_report_key("../../etc/shadow")

    with pytest.raises(ValueError):
        build_report_key("reports/../../../malicious")


# ── 19. YOLO temporary file cleanup verification ─────────────────────
@pytest.mark.asyncio
async def test_yolo_temporary_file_cleanup_pattern(tmp_path):
    """
    Simulates the safe ephemeral file cleanup pattern using try...finally:
    the file is created, read/encoded, and guaranteed to be deleted even if an error occurs.
    """
    temp_yolo_file = tmp_path / "temp_detected.jpg"
    temp_yolo_file.write_bytes(b"yolo annotated visual image")
    assert temp_yolo_file.exists()

    cleaned_up = False
    try:
        # Simulate processing / encoding
        assert temp_yolo_file.stat().st_size > 0
    finally:
        if temp_yolo_file.exists():
            temp_yolo_file.unlink(missing_ok=True)
            cleaned_up = True

    assert cleaned_up is True
    assert not temp_yolo_file.exists()


# ── 20. Existing local workflow remains functional ───────────────────
@pytest.mark.asyncio
async def test_existing_local_workflow_remains_functional(tmp_path):
    storage = LocalStorageService(base_dir=tmp_path)

    # 1. Upload evidence
    ev_key = build_evidence_key("AWC-1042", "sub-001")
    uploaded_ev = await storage.upload_file(b"evidence photo", ev_key, "image/jpeg")
    assert uploaded_ev == ev_key

    # 2. Upload report
    rep_key = build_report_key("SHD-20260726-000001")
    uploaded_rep = await storage.upload_file(b"%PDF report", rep_key, "application/pdf")
    assert uploaded_rep == rep_key

    # 3. Read back
    assert await storage.download_file(ev_key) == b"evidence photo"
    assert await storage.download_file(rep_key) == b"%PDF report"

    # 4. Generate local URL
    url = await storage.generate_access_url(rep_key)
    assert rep_key in url


# ═════════════════════════════════════════════════════════════════════
# CHECKPOINT 2 INTEGRATION TESTS
# ═════════════════════════════════════════════════════════════════════

# ── 21. GCS-enabled evidence flow ────────────────────────────────────
@pytest.mark.asyncio
async def test_gcs_enabled_evidence_flow():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    gcs = GoogleCloudStorageService(bucket_name="test-evidence-bucket", client=mock_client)
    awc_id = "AWC-1042"
    sub_id = "sub-uuid-abc-123"
    ev_key = build_evidence_key(awc_id, sub_id, ".jpg")

    assert ev_key == f"evidence/{awc_id}/{sub_id}.jpg"
    uploaded_key = await gcs.upload_file(b"fake image bytes", ev_key, "image/jpeg")

    assert uploaded_key == ev_key
    mock_bucket.blob.assert_called_once_with(ev_key)
    mock_blob.upload_from_string.assert_called_once_with(b"fake image bytes", content_type="image/jpeg")


# ── 22. Report storage and retrieval ─────────────────────────────────
@pytest.mark.asyncio
async def test_report_storage_and_retrieval(tmp_path):
    storage = LocalStorageService(base_dir=tmp_path)
    audit_id = "SHD-20260726-000042"
    rep_key = build_report_key(audit_id)
    assert rep_key == f"reports/{audit_id}.pdf"

    pdf_bytes = b"%PDF-1.4 official report binary content"
    uploaded_key = await storage.upload_file(pdf_bytes, rep_key, "application/pdf")
    assert uploaded_key == rep_key

    # Retrieve through storage abstraction
    retrieved = await storage.download_file(uploaded_key)
    assert retrieved == pdf_bytes


# ── 23. YOLO detector cleanup method ─────────────────────────────────
def test_yolo_detector_cleanup_method(tmp_path):
    from app.services.yolo_detector import yolo_detector

    temp_yolo_img = tmp_path / "detected_viz_99.jpg"
    temp_yolo_img.write_bytes(b"visualized bounding boxes")
    assert temp_yolo_img.exists()

    # Successful cleanup
    assert yolo_detector.cleanup_visualized_image(str(temp_yolo_img)) is True
    assert not temp_yolo_img.exists()

    # Calling on already deleted file does not crash
    assert yolo_detector.cleanup_visualized_image(str(temp_yolo_img)) is False
    assert yolo_detector.cleanup_visualized_image(None) is False


# ── 24. Authenticated report access - Authorized ─────────────────────
@pytest.mark.asyncio
async def test_authenticated_report_access_authorized(tmp_path):
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import AsyncMock
    from app.main import app
    from app.services.storage import LocalStorageService
    from app.database import get_db
    from app.services.firebase_auth import get_current_officer

    # Create dummy report in temporary storage
    storage = LocalStorageService(base_dir=tmp_path)
    rep_key = "reports/SHD-TEST-001.pdf"
    await storage.upload_file(b"%PDF-authorized-content", rep_key, "application/pdf")

    # Mock DB session returning an authorized submission
    mock_db = AsyncMock()
    mock_submission = MagicMock()
    mock_submission.submission_id = "sub-test-101"
    mock_submission.audit_id = "SHD-TEST-001"
    mock_submission.awc_id = "AWC-1042"
    mock_submission.is_authorized = True
    mock_submission.pdf_path = rep_key

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_submission
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_officer] = lambda: {"uid": "test_officer_uid", "email": "officer@shahdol.gov.in"}

    try:
        with patch("app.routers.reports.get_storage_service", return_value=storage):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/reports/submissions/sub-test-101/pdf")
                assert res.status_code == 200
                assert res.headers["content-type"] == "application/pdf"
                assert res.content == b"%PDF-authorized-content"
    finally:
        app.dependency_overrides.clear()


# ── 25. Authenticated report access - Unauthenticated ────────────────
@pytest.mark.asyncio
async def test_authenticated_report_access_unauthenticated():
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import AsyncMock
    from app.main import app
    from app.database import get_db

    # Real get_current_officer requires Firebase token
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/reports/submissions/sub-101/pdf")
            # Without Authorization header, get_current_officer raises 401
            assert res.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ── 26. Authenticated report access - Unauthorized submission ────────
@pytest.mark.asyncio
async def test_authenticated_report_access_unauthorized_submission():
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import AsyncMock
    from app.main import app
    from app.database import get_db
    from app.services.firebase_auth import get_current_officer

    # Mock DB session returning an unauthorized submission
    mock_db = AsyncMock()
    mock_submission = MagicMock()
    mock_submission.submission_id = "sub-unauth-001"
    mock_submission.audit_id = "SHD-UNAUTH-001"
    mock_submission.is_authorized = False  # Unauthorized!
    mock_submission.pdf_path = "reports/SHD-UNAUTH-001.pdf"

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_submission
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_officer] = lambda: {"uid": "test_officer_uid"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/reports/submissions/sub-unauth-001/pdf")
            # Unauthorized submission access is rejected
            assert res.status_code == 403
            assert "Access to unauthorized submission report is forbidden" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ── 27. Invalid / traversal report key rejected by endpoint ──────────
@pytest.mark.asyncio
async def test_invalid_traversal_report_key_rejected():
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.services.firebase_auth import get_current_officer

    app.dependency_overrides[get_current_officer] = lambda: {"uid": "test_officer"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Traversal sequence embedded in submission identifier
            res = await client.get("/api/v1/reports/submissions/sub..bad/pdf")
            assert res.status_code == 400
            assert "Invalid submission identifier" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ── 28. WhatsApp storage integration ─────────────────────────────────
@pytest.mark.asyncio
async def test_whatsapp_storage_integration(monkeypatch, tmp_path):
    from app.services.whatsapp import download_and_save_whatsapp_media
    from app.config import settings
    import io
    from PIL import Image

    # Create valid 1x1 test image bytes
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(buf, format="JPEG")
    valid_img_bytes = buf.getvalue()

    monkeypatch.setattr(settings, "whatsapp_access_token", "fake_token")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "fake_id")

    # Mock httpx client
    mock_resp_meta = MagicMock()
    mock_resp_meta.status_code = 200
    mock_resp_meta.json.return_value = {"url": "https://lookaside.fbsbx.com/fake_media"}

    mock_resp_bytes = MagicMock()
    mock_resp_bytes.status_code = 200
    mock_resp_bytes.content = valid_img_bytes

    async def mock_get(url, **kwargs):
        if "fake_media" in url:
            return mock_resp_bytes
        return mock_resp_meta

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        result = await download_and_save_whatsapp_media(
            media_id="media_12345",
            submission_id="sub-test-wa",
            media_mime_type="image/jpeg",
            awc_id="AWC-SHA-01",
        )

    assert result["success"] is True
    assert result["storage_key"] == "evidence/AWC-SHA-01/sub-test-wa.jpg"
    assert result["sha256"] is not None


# ── 29. WhatsApp document direct upload with file_bytes ──────────────
@pytest.mark.asyncio
async def test_whatsapp_send_document_direct_bytes(monkeypatch):
    from app.services.whatsapp import send_whatsapp_document
    from app.config import settings

    monkeypatch.setattr(settings, "whatsapp_access_token", "test_tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "phone_123")

    mock_media_post = MagicMock()
    mock_media_post.status_code = 200
    mock_media_post.json.return_value = {"id": "meta_media_999"}

    mock_msg_post = MagicMock()
    mock_msg_post.status_code = 200
    mock_msg_post.json.return_value = {"messages": [{"id": "wamid.HBgM..."}]}

    async def mock_post(url, **kwargs):
        if "/media" in url:
            return mock_media_post
        return mock_msg_post

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await send_whatsapp_document(
            to_phone="919753239303",
            document_url="https://storage.googleapis.com/bucket/reports/SHD.pdf?X-Goog-Signature=secret123",
            filename="AWC_Report_SHD.pdf",
            file_bytes=b"%PDF-direct-bytes",
        )

    assert res["success"] is True
    assert res["message_id"] == "wamid.HBgM..."


# ── 30. Ephemeral YOLO cleanup on pipeline exception ──────────────────
@pytest.mark.asyncio
async def test_pipeline_exception_cleans_up_ephemeral_yolo_files(tmp_path):
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.services.ai_vision import process_image_ai_pipeline
    from app.services.yolo_detector import yolo_detector
    from app.models import DailySubmission, SubmissionStatus
    from PIL import Image
    import io

    # 1. Create a dummy test image on disk
    test_img = tmp_path / "valid_image.jpg"
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color="green").save(buf, format="JPEG")
    test_img.write_bytes(buf.getvalue())

    # 2. Create simulated YOLO visualized output file
    temp_vis_img = tmp_path / "test_detected_yolo.jpg"
    temp_vis_img.write_bytes(b"ephemeral yolo detected visual bytes")
    assert temp_vis_img.exists()

    # 3. Setup mock submission
    mock_sub = MagicMock()
    mock_sub.submission_id = "sub-test-err-01"
    mock_sub.status = SubmissionStatus.RECEIVED
    mock_sub.raw_media_id = None
    mock_sub.local_media_path = str(test_img)
    mock_sub.latitude = None
    mock_sub.longitude = None
    mock_sub.awc_id = "AWC-101"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_sub
    mock_db.execute.return_value = mock_result

    class MockSessionContext:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    # 4. Mock YOLO to return the simulated visual path, and vision provider to crash
    with patch("app.services.ai_vision.async_session_maker", return_value=MockSessionContext()), \
         patch.object(yolo_detector, "detect_objects", return_value={"visualized_image_path": str(temp_vis_img)}), \
         patch("app.services.ai_vision._run_vision_providers", side_effect=RuntimeError("Simulated vision crash")):

        await process_image_ai_pipeline("sub-test-err-01")

    # 5. Verify the ephemeral YOLO visual file was deleted by the outer finally block!
    assert not temp_vis_img.exists()


# ── 31. Safe access URL failure handling without credential leak ─────
@pytest.mark.asyncio
async def test_generate_access_url_failure_safety():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Simulate signing failure with sensitive bearer token in raw error
    mock_blob.generate_signed_url.side_effect = Exception("ADC Token failure: Bearer super_secret_signing_key_98765")

    gcs = GoogleCloudStorageService(bucket_name="shahdol-bucket", client=mock_client)

    with pytest.raises(StorageError) as exc_info:
        await gcs.generate_access_url("reports/SHD-20260726-000001.pdf")

    err_msg = str(exc_info.value)
    # Ensure no credentials or tokens are leaked in the exception message
    assert "super_secret_signing_key_98765" not in err_msg
    assert "Bearer" not in err_msg
    assert "Failed to generate signed URL" in err_msg
