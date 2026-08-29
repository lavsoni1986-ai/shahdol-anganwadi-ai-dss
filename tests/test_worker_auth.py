# tests/test_worker_auth.py
from app.services.worker_auth import authenticate_worker, reload_workers

def test_authenticate_registered_user():
    reload_workers()
    result = authenticate_worker("919753239303")
    assert result.is_authorized is True
    assert result.phone == "919753239303"
    assert result.worker_name == "Lav Soni"
    assert result.awc_id == "AWC-SHA-1001"
    assert result.rejection_reason is None

def test_authenticate_unregistered_user():
    reload_workers()
    result = authenticate_worker("910000000000")
    assert result.is_authorized is False
    assert "not registered" in result.rejection_reason.lower()
