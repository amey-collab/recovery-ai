import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient
from jose import jwt

from app.main import Role, SessionLocal, User, app, pwd, settings


def test_audit_logs_are_available_to_authenticated_viewer():
    email = f"audit-viewer-{uuid.uuid4().hex}@example.test"
    session = SessionLocal()
    user = User(email=email, password_hash=pwd.hash("Audit-test-password-2026!"), role=Role.VIEWER.value)
    session.add(user)
    session.commit()
    token = jwt.encode(
        {"sub": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm="HS256",
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    finally:
        session.delete(user)
        session.commit()
        session.close()

