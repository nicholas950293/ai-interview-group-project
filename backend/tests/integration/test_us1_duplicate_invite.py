"""US1 邊界情況：重複邀請（spec.md 驗收情境 1.4、FR-009）。

同一 Email 與同一職缺已有進行中的考核時，系統必須要求明確確認後才建立新紀錄。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

PAYLOAD = {
    "name": "合成應徵者",
    "email": "duplicate@example.com",
    "job_title": "後端工程師",
    "dept_id": "ENG",
}


def test_duplicate_invite_returns_409(client, hr_headers):
    assert client.post("/hr/assessments", json=PAYLOAD, headers=hr_headers).status_code == 201

    second = client.post("/hr/assessments", json=PAYLOAD, headers=hr_headers)
    assert second.status_code == 409
    body = second.json()
    assert set(body) >= {"code", "message"}
    assert body["code"] == "DUPLICATE_ASSESSMENT"


def test_confirm_duplicate_creates_a_second_record(client, hr_headers):
    first = client.post("/hr/assessments", json=PAYLOAD, headers=hr_headers).json()
    second = client.post(
        "/hr/assessments", json={**PAYLOAD, "confirm_duplicate": True}, headers=hr_headers
    )
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]

    rows = client.get("/hr/assessments", headers=hr_headers).json()
    assert len(rows) == 2, "同一人重複邀請產生多筆獨立紀錄，以 Email 關聯"


def test_different_job_title_is_not_a_duplicate(client, hr_headers):
    client.post("/hr/assessments", json=PAYLOAD, headers=hr_headers)
    other = client.post(
        "/hr/assessments", json={**PAYLOAD, "job_title": "資料工程師"}, headers=hr_headers
    )
    assert other.status_code == 201


def test_email_comparison_is_case_insensitive(client, hr_headers):
    client.post("/hr/assessments", json=PAYLOAD, headers=hr_headers)
    upper = client.post(
        "/hr/assessments", json={**PAYLOAD, "email": "DUPLICATE@example.com"}, headers=hr_headers
    )
    assert upper.status_code == 409


@pytest.mark.parametrize("closed_status", ["DECIDED", "EXPIRED"])
def test_closed_assessments_do_not_block_new_invites(client, hr_headers, db, closed_status):
    """「進行中」才構成重複；已決策或已逾期的紀錄不應阻擋重新邀請。"""
    db.insert_raw(
        "assessments",
        {
            "name": "合成應徵者",
            "email": PAYLOAD["email"],
            "job_title": PAYLOAD["job_title"],
            "dept_id": "ENG",
            "assigned_manager_id": "22222222-2222-4222-8222-222222222222",
            "status": closed_status,
            "token": f"closed-token-{closed_status}-000000000000",
            "token_expires_at": datetime.now(UTC) - timedelta(days=1),
        },
    )
    response = client.post("/hr/assessments", json=PAYLOAD, headers=hr_headers)
    assert response.status_code == 201
