"""US1 端到端：建案 → 連結 → 總覽（quickstart.md 情境 1、SC-001）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def test_create_link_and_overview(client, hr_headers, db):
    # 1-2. HR 新增考核
    created = client.post(
        "/hr/assessments",
        json={
            "name": "合成應徵者甲",
            "email": "flow.a@example.com",
            "phone": "0900-111-222",
            "job_title": "後端工程師",
            "dept_id": "ENG",
        },
        headers=hr_headers,
    )
    assert created.status_code == 201
    body = created.json()

    # 3. 效期為當下 + 7 天；狀態為 PENDING_ASSIGN；自動填入該部門主管
    assert body["status"] == "PENDING_ASSIGN"
    assert body["assigned_manager"] == "合成工程主管"
    assert datetime.fromisoformat(body["token_expires_at"]) > datetime.now(UTC) + timedelta(days=6)
    assert body["candidate_url"].endswith(body["token"])

    # 4. 總覽頁可見該筆資料
    rows = client.get("/hr/assessments", headers=hr_headers).json()
    assert [row["id"] for row in rows] == [body["id"]]
    assert rows[0]["status"] == "PENDING_ASSIGN"
    assert rows[0]["email_status"] == "NOT_SENT"

    # 稽核歷程：建立即留下紀錄（FR-076）
    logs = [log for log in db.tables["audit_logs"] if log["assessment_id"] == body["id"]]
    assert [log["action"] for log in logs] == ["ASSESSMENT_CREATED"]
    assert logs[0]["actor_role"] == "HR"
    assert logs[0]["actor_id"] == "11111111-1111-4111-8111-111111111111"


def test_audit_detail_carries_no_personal_data(client, hr_headers, db):
    """FR-079：稽核紀錄的 detail 不得含姓名、Email 或電話。"""
    body = client.post(
        "/hr/assessments",
        json={
            "name": "王小明",
            "email": "ming@example.com",
            "phone": "0912-345-678",
            "job_title": "後端工程師",
            "dept_id": "ENG",
        },
        headers=hr_headers,
    ).json()

    logs = [log for log in db.tables["audit_logs"] if log["assessment_id"] == body["id"]]
    serialized = str(logs)
    assert "王小明" not in serialized
    assert "ming@example.com" not in serialized
    assert "0912-345-678" not in serialized


def test_reassign_manager_records_audit(client, hr_headers, make_assessment, db):
    """FR-012：重新指派須留下稽核紀錄。"""
    assessment = make_assessment(dept_id="ENG")
    response = client.post(
        f"/hr/assessments/{assessment['id']}/reassign-manager",
        json={"manager_id": "33333333-3333-4333-8333-333333333333"},
        headers=hr_headers,
    )
    assert response.status_code == 200

    stored = db.find("assessments", id=assessment["id"])
    assert stored["assigned_manager_id"] == "33333333-3333-4333-8333-333333333333"

    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]
    ]
    assert "MANAGER_REASSIGNED" in actions


def test_regenerate_token_invalidates_the_old_one(client, hr_headers, make_assessment, db):
    """FR-019：重新產生後舊連結必須立即失效。"""
    assessment = make_assessment(status="EXPIRED", expires_in_days=-1)
    old_token = assessment["token"]

    response = client.post(
        f"/hr/assessments/{assessment['id']}/regenerate-token", headers=hr_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token"] != old_token
    assert datetime.fromisoformat(body["token_expires_at"]) > datetime.now(UTC) + timedelta(days=6)

    # 舊 token 立即失效
    assert client.get(f"/candidate/session/{old_token}").status_code == 404

    # EXPIRED 回到 PENDING_CANDIDATE（FR-074 的合法轉換）
    stored = db.find("assessments", id=assessment["id"])
    assert stored["status"] == "PENDING_CANDIDATE"

    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]
    ]
    assert "TOKEN_REGENERATED" in actions


def test_regenerate_token_on_unknown_assessment_returns_404(client, hr_headers):
    response = client.post(
        "/hr/assessments/00000000-0000-4000-8000-000000000000/regenerate-token",
        headers=hr_headers,
    )
    assert response.status_code == 404
