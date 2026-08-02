"""契約：POST /manager/assessments/{id}/assign-question（FR-023、FR-026、FR-028）。"""

from __future__ import annotations

QUESTION = {
    "source": "BANK",
    "title": "兩數相加",
    "category": "基礎",
    "difficulty": "EASY",
    "language": "python",
    "description": "讀取兩個整數並輸出其和。",
    "constraints": "整數範圍 -10^9 至 10^9。",
    "test_cases": [
        {"name": "基本案例", "stdin": "3 5\n", "expected_stdout": "8\n", "is_hidden": False},
        {"name": "隱藏邊界", "stdin": "0 0\n", "expected_stdout": "0\n", "is_hidden": True},
    ],
}


def test_assign_transitions_to_pending_candidate(client, eng_manager_headers, make_assessment, db):
    assessment = make_assessment(dept_id="ENG")
    response = client.post(
        f"/manager/assessments/{assessment['id']}/assign-question",
        json={"question": QUESTION},
        headers=eng_manager_headers,
    )
    assert response.status_code == 200, response.text

    stored = db.find("assessments", id=assessment["id"])
    assert stored["status"] == "PENDING_CANDIDATE"

    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]
    ]
    assert "QUESTION_ASSIGNED" in actions


def test_assign_writes_a_snapshot(client, eng_manager_headers, make_assessment, db):
    """指派時寫入快照，使題庫後續變更不影響已指派的考核（FR-028）。"""
    assessment = make_assessment(dept_id="ENG")
    client.post(
        f"/manager/assessments/{assessment['id']}/assign-question",
        json={"question": QUESTION},
        headers=eng_manager_headers,
    )

    snapshot = db.find("assessments", id=assessment["id"])["question_snapshot"]
    assert snapshot["title"] == "兩數相加"
    assert len(snapshot["test_cases"]) == 2
    assert snapshot["assigned_by"] == "22222222-2222-4222-8222-222222222222"
    assert "assigned_at" in snapshot

    # 題庫變更後，快照不動
    bank = db.find("question_banks", id="aa000000-0000-4000-8000-000000000001")
    bank["title"] = "改過的題目"
    bank["test_cases"] = []
    assert db.find("assessments", id=assessment["id"])["question_snapshot"]["title"] == "兩數相加"


def test_assign_on_wrong_status_returns_409(client, eng_manager_headers, make_assessment):
    assessment = make_assessment(dept_id="ENG", status="COMPLETED_AWAITING_REVIEW", submitted=True)
    response = client.post(
        f"/manager/assessments/{assessment['id']}/assign-question",
        json={"question": QUESTION},
        headers=eng_manager_headers,
    )
    assert response.status_code == 409


def test_assign_to_other_department_returns_404(client, design_manager_headers, make_assessment):
    """不存在與無權存取不區分，避免資訊外洩。"""
    assessment = make_assessment(dept_id="ENG")
    response = client.post(
        f"/manager/assessments/{assessment['id']}/assign-question",
        json={"question": QUESTION},
        headers=design_manager_headers,
    )
    assert response.status_code == 404


def test_malformed_question_returns_422(client, eng_manager_headers, make_assessment):
    assessment = make_assessment(dept_id="ENG")
    broken = {**QUESTION, "difficulty": "IMPOSSIBLE"}
    response = client.post(
        f"/manager/assessments/{assessment['id']}/assign-question",
        json={"question": broken},
        headers=eng_manager_headers,
    )
    assert response.status_code == 422
