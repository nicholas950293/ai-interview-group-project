"""契約：POST /hr/assessments（contracts/openapi.yaml）。

對應 FR-009～FR-011、FR-015～FR-017。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

VALID_PAYLOAD = {
    "name": "合成應徵者",
    "email": "new.candidate@example.com",
    "phone": "0900-000-999",
    "job_title": "後端工程師",
    "dept_id": "ENG",
}


def test_create_returns_201_with_contract_shape(client, hr_headers):
    response = client.post("/hr/assessments", json=VALID_PAYLOAD, headers=hr_headers)
    assert response.status_code == 201, response.text

    body = response.json()
    assert set(body) >= {"id", "token", "token_expires_at", "status", "assigned_manager"}
    assert body["status"] == "PENDING_ASSIGN"
    assert body["assigned_manager"] == "合成工程主管"


def test_token_expires_seven_days_from_creation(client, hr_headers):
    """FR-017：效期預設為建立時間起算 7 天。"""
    body = client.post("/hr/assessments", json=VALID_PAYLOAD, headers=hr_headers).json()
    expires_at = datetime.fromisoformat(body["token_expires_at"])
    delta = expires_at - datetime.now(UTC)
    assert 6.9 < delta.total_seconds() / 86400 < 7.1


def test_token_is_unguessable(client, hr_headers):
    """FR-016：以密碼學安全亂數產生，使其無法被猜測或列舉。"""
    tokens = {
        client.post(
            "/hr/assessments", json=VALID_PAYLOAD | {"confirm_duplicate": True}, headers=hr_headers
        ).json()["token"]
        for _ in range(5)
    }
    assert len(tokens) == 5, "每次建立的 token 必須互異"
    for token in tokens:
        assert len(token) >= 43, "至少 32 位元組的 URL-safe 編碼"
        assert token.replace("-", "").replace("_", "").isalnum()


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_PAYLOAD, "name": ""},
        {**VALID_PAYLOAD, "email": "not-an-email"},
        {k: v for k, v in VALID_PAYLOAD.items() if k != "job_title"},
        {k: v for k, v in VALID_PAYLOAD.items() if k != "dept_id"},
    ],
)
def test_invalid_payload_returns_422(client, hr_headers, payload):
    response = client.post("/hr/assessments", json=payload, headers=hr_headers)
    assert response.status_code == 422
    assert set(response.json()) >= {"code", "message"}


def test_unknown_department_is_rejected(client, hr_headers):
    response = client.post(
        "/hr/assessments", json={**VALID_PAYLOAD, "dept_id": "NO_SUCH_DEPT"}, headers=hr_headers
    )
    assert response.status_code in (404, 422)


def test_requires_authentication(client):
    assert client.post("/hr/assessments", json=VALID_PAYLOAD).status_code == 401


def test_manager_role_is_forbidden(client, eng_manager_headers):
    response = client.post("/hr/assessments", json=VALID_PAYLOAD, headers=eng_manager_headers)
    assert response.status_code == 403


def test_error_body_never_echoes_personal_data(client, hr_headers):
    """FR-079：錯誤訊息不得含個資。"""
    response = client.post(
        "/hr/assessments",
        json={**VALID_PAYLOAD, "email": "invalid", "name": "王小明"},
        headers=hr_headers,
    )
    assert response.status_code == 422
    assert "王小明" not in response.text
    assert "invalid" not in response.json()["message"]
