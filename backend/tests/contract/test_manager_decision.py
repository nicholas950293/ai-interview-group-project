"""契約：POST /manager/assessments/{id}/decision（FR-061～FR-064）。"""

from __future__ import annotations

import pytest


@pytest.fixture
def awaiting_review(make_assessment, question_snapshot):
    return make_assessment(
        status="COMPLETED_AWAITING_REVIEW",
        question_snapshot=question_snapshot,
        candidate_answer="print(1)",
        code_language="python",
        submitted=True,
    )


@pytest.mark.parametrize("result", ["PASS", "SECOND_ROUND", "FAIL"])
def test_decision_is_recorded(client, eng_manager_headers, awaiting_review, db, result):
    response = client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": result, "internal_comment": "內部評語"},
        headers=eng_manager_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision_no"] == 1

    stored = db.find("assessments", id=awaiting_review["id"])
    assert stored["status"] == "DECIDED"
    assert stored["final_decision"] == result


def test_decision_records_who_and_when(client, eng_manager_headers, awaiting_review, db):
    """每筆決策必須記錄決策者身分與決策時間（FR-063）。"""
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "PASS", "internal_comment": "評語"},
        headers=eng_manager_headers,
    )
    decision = next(
        d for d in db.tables["manager_decisions"] if d["assessment_id"] == awaiting_review["id"]
    )
    assert decision["decided_by"] == "22222222-2222-4222-8222-222222222222"
    assert decision["decided_at"] is not None


def test_internal_comment_is_optional(client, eng_manager_headers, awaiting_review):
    response = client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "FAIL"},
        headers=eng_manager_headers,
    )
    assert response.status_code == 200


def test_invalid_result_returns_422(client, eng_manager_headers, awaiting_review):
    response = client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "MAYBE"},
        headers=eng_manager_headers,
    )
    assert response.status_code == 422


def test_decision_before_submission_is_rejected(client, eng_manager_headers, make_assessment):
    assessment = make_assessment(status="PENDING_CANDIDATE")
    response = client.post(
        f"/manager/assessments/{assessment['id']}/decision",
        json={"result": "PASS"},
        headers=eng_manager_headers,
    )
    assert response.status_code == 409


def test_other_department_manager_gets_404(client, design_manager_headers, awaiting_review):
    response = client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "PASS"},
        headers=design_manager_headers,
    )
    assert response.status_code == 404


def test_hr_cannot_record_a_decision(client, hr_headers, awaiting_review):
    response = client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "PASS"},
        headers=hr_headers,
    )
    assert response.status_code == 403


def test_decision_is_audited(client, eng_manager_headers, awaiting_review, db):
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "PASS", "internal_comment": "不得進入稽核的評語"},
        headers=eng_manager_headers,
    )
    logs = [log for log in db.tables["audit_logs"] if log["assessment_id"] == awaiting_review["id"]]
    recorded = [log for log in logs if log["action"] == "DECISION_RECORDED"]
    assert len(recorded) == 1
    assert recorded[0]["from_status"] == "COMPLETED_AWAITING_REVIEW"
    assert recorded[0]["to_status"] == "DECIDED"
    assert "不得進入稽核的評語" not in str(logs)
