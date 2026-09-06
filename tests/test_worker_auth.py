# tests/test_worker_auth.py
import pytest

from app.models import AnganwadiMaster
from app.services.worker_auth import authenticate_worker


def _make_worker(
    phone="919753239303",
    name="Test Worker",
    awc_code="AWC-TEST-1",
    active=True,
):
    return AnganwadiMaster(
        district="Shahdol",
        block_name="Sohagpur",
        sector="Test Sector",
        supervisor_name="Supervisor",
        supervisor_mobile="919800000000",
        awc_code=awc_code,
        center_name="Test Centre",
        worker_name=name,
        worker_mobile=phone,
        registered_children=20,
        school_going_children=15,
        latitude=23.28,
        longitude=81.35,
        active_status=active,
        worker_type="AWW",
        is_demo=True,
    )


@pytest.mark.asyncio
async def test_authenticate_registered_user(async_session):
    async_session.add(_make_worker())
    await async_session.commit()
    result = await authenticate_worker("919753239303", async_session)
    assert result.is_authorized is True
    assert result.phone == "9753239303"  # normalized (last 10 digits)
    assert result.worker_name == "Test Worker"
    assert result.awc_id == "AWC-TEST-1"
    assert result.rejection_reason is None


@pytest.mark.asyncio
async def test_authenticate_unregistered_user(async_session):
    result = await authenticate_worker("910000000000", async_session)
    assert result.is_authorized is False
    assert "not registered" in result.rejection_reason.lower()
