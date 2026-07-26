# tests/test_recovery.py
# =====================================================================
# Unit tests for recovered modules (Phase 2)
# =====================================================================

import pytest
import numpy as np
from PIL import Image
from pathlib import Path

from app.services.ai_vision import (
    check_image_brightness,
    check_image_blur,
    extract_exif_metadata,
)
from app.services.whatsapp import (
    download_and_save_whatsapp_media,
    send_whatsapp_document,
    virtual_broadcast_document,
)
from app.utils.audit import generate_audit_id


def test_brightness_detection():
    # Normal bright image
    bright_arr = np.ones((100, 100, 3), dtype=np.uint8) * 200
    bright_img = Image.fromarray(bright_arr)
    cat_b, score_b = check_image_brightness(bright_img)
    assert cat_b == "Normal"
    assert score_b >= 80.0

    # Dark image
    dark_arr = np.ones((100, 100, 3), dtype=np.uint8) * 50
    dark_img = Image.fromarray(dark_arr)
    cat_d, score_d = check_image_brightness(dark_img)
    assert cat_d == "Dark"

    # Very Dark image
    vdark_arr = np.ones((100, 100, 3), dtype=np.uint8) * 20
    vdark_img = Image.fromarray(vdark_arr)
    cat_vd, score_vd = check_image_brightness(vdark_img)
    assert cat_vd == "Very Dark"


def test_exif_extraction_safe_missing_metadata():
    img = Image.new("RGB", (50, 50), color="red")
    meta = extract_exif_metadata(img)
    assert isinstance(meta, dict)
    assert meta["camera_make"] is None
    assert meta["camera_model"] is None
    assert meta["device_timestamp"] is None


@pytest.mark.asyncio
async def test_audit_id_format(async_session):
    audit_id = await generate_audit_id(async_session)
    assert audit_id.startswith("SHD-")
    assert len(audit_id) == 19  # SHD-YYYYMMDD-000001


@pytest.mark.asyncio
async def test_dashboard_submissions_endpoint(async_session):
    from app.routers.dashboard import list_submissions
    res = await list_submissions(db=async_session, page=1, page_size=15)
    assert res.total >= 0
    assert isinstance(res.items, list)

