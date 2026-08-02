"""US5：二輪面試不自動建立新考核（FR-065、quickstart.md 情境 8）。

這是規格明確確認過的決定：「僅通知應徵者並保存紀錄，系統不再有後續動作」。
"""

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


def test_second_round_does_not_create_a_new_assessment(
    client, eng_manager_headers, awaiting_review, db
):
    before = len(db.tables["assessments"])
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "SECOND_ROUND", "internal_comment": "安排二輪"},
        headers=eng_manager_headers,
    )
    assert len(db.tables["assessments"]) == before


def test_status_stays_at_decided(client, eng_manager_headers, awaiting_review, db):
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "SECOND_ROUND"},
        headers=eng_manager_headers,
    )
    stored = db.find("assessments", id=awaiting_review["id"])
    assert stored["status"] == "DECIDED"
    assert stored["final_decision"] == "SECOND_ROUND"


def test_no_new_token_is_issued(client, eng_manager_headers, awaiting_review, db):
    original_token = awaiting_review["token"]
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "SECOND_ROUND"},
        headers=eng_manager_headers,
    )
    assert db.find("assessments", id=awaiting_review["id"])["token"] == original_token


def test_no_follow_up_audit_actions_are_written(client, eng_manager_headers, awaiting_review, db):
    """不觸發任何後續系統流程（FR-065）。"""
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "SECOND_ROUND"},
        headers=eng_manager_headers,
    )
    actions = [
        log["action"]
        for log in db.tables["audit_logs"]
        if log["assessment_id"] == awaiting_review["id"]
    ]
    assert actions[-1] == "DECISION_RECORDED"
    assert "QUESTION_ASSIGNED" not in actions
    assert "TOKEN_REGENERATED" not in actions


def test_decided_assessment_rejects_further_state_transitions(
    client, eng_manager_headers, awaiting_review
):
    """DECIDED 為終態（FR-074）。"""
    client.post(
        f"/manager/assessments/{awaiting_review['id']}/decision",
        json={"result": "SECOND_ROUND"},
        headers=eng_manager_headers,
    )
    response = client.post(
        f"/manager/assessments/{awaiting_review['id']}/assign-question",
        json={
            "question": {
                "title": "新題目",
                "difficulty": "EASY",
                "language": "python",
                "description": "描述",
                "test_cases": [
                    {"name": "c", "stdin": "1\n", "expected_stdout": "1\n", "is_hidden": False}
                ],
            }
        },
        headers=eng_manager_headers,
    )
    assert response.status_code == 409
