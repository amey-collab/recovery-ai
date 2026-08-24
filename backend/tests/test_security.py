import sys
from pathlib import Path
import pytest
import uuid
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.main import Register, Settings, User, SessionLocal, app, pwd, settings


def test_production_missing_jwt_secret_fails_safely():
    with pytest.raises(ValueError, match='SECRET_KEY'):
        Settings(_env_file=None, app_env='production', secret_key='', database_url='sqlite:///./security-test.db')


def test_production_wildcard_cors_fails_safely():
    with pytest.raises(ValueError, match='CORS'):
        Settings(_env_file=None, app_env='production', secret_key='x'*48, cors_origins='*', database_url='sqlite:///./security-test.db')


def test_registration_cannot_self_assign_privileged_role():
    assert 'role' not in Register.model_fields


def test_registration_and_password_verification():
    email=f'password-test-{uuid.uuid4().hex}@example.com'
    password='RecoverAI-normal-password-2026!'
    with TestClient(app) as client:
        response=client.post('/api/auth/register',json={'email':email,'password':password})
        assert response.status_code==200
        login=client.post('/api/auth/login',json={'email':email,'password':password})
        assert login.status_code==200
        assert login.json().get('access_token')
    s=SessionLocal()
    try:
        user=s.query(User).filter(User.email==email).one()
        assert pwd.verify(password,user.password_hash)
    finally:
        s.delete(user);s.commit();s.close()


def test_password_over_bcrypt_byte_limit_is_rejected_without_truncation():
    with TestClient(app) as client:
        response=client.post('/api/auth/register',json={'email':f'long-{uuid.uuid4().hex}@example.com','password':'x'*73})
    assert response.status_code==422
    assert '72 UTF-8 bytes' in response.text


def test_sensitive_endpoint_requires_authentication():
    with TestClient(app) as client:
        assert client.post('/api/recovery/1/execute').status_code == 401


def test_health_response_does_not_expose_credentials():
    with TestClient(app) as client:
        payload=client.get('/health').json()
        assert not any(secret_name in payload for secret_name in ('secret_key','database_url','razorpay_key_secret','razorpay_webhook_secret'))


def test_razorpay_service_rejects_live_mode(monkeypatch):
    from app.main import RazorpayService
    monkeypatch.setattr(settings, 'razorpay_mode', 'live')
    with pytest.raises(Exception, match='Test Mode'):
        RazorpayService().client()
