from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.src.config import load_settings
from backend.src.main import create_app


@pytest.fixture
def demo_settings(monkeypatch):
    monkeypatch.setenv("LOCAL_DEMO_MODE", "1")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    return load_settings()


def _token(user_id: str, role: str, dept_id: str | None = None) -> str:
    claims = {"sub": user_id, "app_role": role}
    if dept_id:
        claims["dept_id"] = dept_id
    return jwt.encode(claims, "demo-jwt-secret", algorithm="HS256")


def test_demo_mode_bootstraps_in_memory_store_and_seed_data(demo_settings):
    app = create_app(settings=demo_settings)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    api_health = client.get("/api/health")
    assert api_health.status_code == 200
    assert api_health.json() == {"status": "ok"}

    candidate = client.get("/candidate/session/demo-candidate-001")
    assert candidate.status_code == 200
    payload = candidate.json()
    assert payload["job_title"] == "後端工程師"
    assert payload["status"] == "PENDING_CANDIDATE"

    hr_headers = {"Authorization": f"Bearer {_token('demo-hr-user', 'HR')}"}
    hr = client.get("/hr/assessments", headers=hr_headers)
    assert hr.status_code == 200
    assert len(hr.json()) >= 1

    manager_headers = {"Authorization": f"Bearer {_token('demo-manager-user', 'MANAGER', 'ENG')}"}
    manager = client.get("/manager/assessments", headers=manager_headers)
    assert manager.status_code == 200
    assert len(manager.json()) >= 1

    index = client.get("/")
    assert index.status_code == 200
    assert "考核總覽" in index.text

    manager_page = client.get("/manager.html")
    assert manager_page.status_code == 200
    assert "主管 Hub" in manager_page.text

    assessment_page = client.get("/assessment.html")
    assert assessment_page.status_code == 200
    assert "線上測驗" in assessment_page.text
