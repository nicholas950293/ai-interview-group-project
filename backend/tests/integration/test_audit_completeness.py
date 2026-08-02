"""稽核完整性（quickstart.md 情境 11、SC-014、FR-076～FR-080）。

SC-014 的目標是「所有已決策的考核，其完整狀態歷程與決策者身分皆可被
追溯，覆蓋率為 100%」。因此本測試走完一整條真實流程，再逐項比對歷程。
"""

from __future__ import annotations

import pytest

ANSWER = "print(sum(map(int, input().split())))"
CANDIDATE_NAME = "王小明"
CANDIDATE_EMAIL = "audit.trail@example.com"
CANDIDATE_PHONE = "0912-345-678"
INTERNAL_COMMENT = "內部評語：不得出現在稽核紀錄中"

EXPECTED_SEQUENCE = [
    "ASSESSMENT_CREATED",
    "QUESTION_ASSIGNED",
    "TRIAL_RUN",
    "ANSWER_SUBMITTED",
    "EVALUATION_STARTED",
    "EVALUATION_COMPLETED",
    "DECISION_RECORDED",
    "DECISION_REVISED",
    "NOTIFICATION_SENT",
]

QUESTION = {
    "source": "BANK",
    "title": "兩數相加",
    "difficulty": "EASY",
    "language": "python",
    "description": "讀取兩個整數並輸出其和。",
    "test_cases": [
        {"name": "公開", "stdin": "3 5\n", "expected_stdout": "8\n", "is_hidden": False},
        {"name": "隱藏", "stdin": "0 0\n", "expected_stdout": "0\n", "is_hidden": True},
    ],
}


@pytest.fixture
def full_flow(client, hr_headers, eng_manager_headers, db, fake_sandbox):
    from backend.src.models.report import ExecutionResult, TerminationReason

    for stdin, stdout in (("3 5\n", "8\n"), ("0 0\n", "0\n")):
        fake_sandbox.register_for_stdin(
            stdin,
            "python",
            ExecutionResult(
                stdout=stdout, exit_code=0, termination_reason=TerminationReason.COMPLETED
            ),
        )

    created = client.post(
        "/hr/assessments",
        json={
            "name": CANDIDATE_NAME,
            "email": CANDIDATE_EMAIL,
            "phone": CANDIDATE_PHONE,
            "job_title": "後端工程師",
            "dept_id": "ENG",
        },
        headers=hr_headers,
    ).json()
    assessment_id, token = created["id"], created["token"]

    client.post(
        f"/manager/assessments/{assessment_id}/assign-question",
        json={"question": QUESTION},
        headers=eng_manager_headers,
    )
    client.post(
        f"/candidate/session/{token}/run",
        json={"code": ANSWER, "language": "python", "stdin": "3 5\n"},
    )
    client.post(f"/candidate/session/{token}/submit", json={"answer": ANSWER, "language": "python"})
    client.post(
        f"/manager/assessments/{assessment_id}/decision",
        json={"result": "PASS", "internal_comment": INTERNAL_COMMENT},
        headers=eng_manager_headers,
    )
    client.post(
        f"/manager/assessments/{assessment_id}/decision",
        json={"result": "SECOND_ROUND", "internal_comment": INTERNAL_COMMENT},
        headers=eng_manager_headers,
    )
    draft = client.post(
        f"/hr/assessments/{assessment_id}/notification/preview", headers=hr_headers
    ).json()
    client.post(
        f"/hr/assessments/{assessment_id}/notification/send", json=draft, headers=hr_headers
    )
    return assessment_id


def _logs(db, assessment_id):
    return [log for log in db.tables["audit_logs"] if log["assessment_id"] == assessment_id]


def test_the_whole_chain_is_recorded(db, full_flow):
    actions = [log["action"] for log in _logs(db, full_flow)]
    assert actions == EXPECTED_SEQUENCE


def test_every_entry_has_actor_role_and_timestamp(db, full_flow):
    for log in _logs(db, full_flow):
        assert log["actor_role"] in {"HR", "MANAGER", "CANDIDATE", "SYSTEM"}
        assert log["created_at"] is not None


def test_actor_identity_is_recorded_for_internal_users(db, full_flow):
    """FR-063、SC-014：決策者身分必須可追溯。"""
    decisions = [log for log in _logs(db, full_flow) if log["action"].startswith("DECISION_")]
    assert decisions
    for log in decisions:
        assert log["actor_id"] == "22222222-2222-4222-8222-222222222222"
        assert log["actor_role"] == "MANAGER"


def test_candidate_actions_have_no_actor_id(db, full_flow):
    """應徵者沒有帳號，actor_id 為 NULL 是正確的（data-model.md §8）。"""
    for log in _logs(db, full_flow):
        if log["actor_role"] == "CANDIDATE":
            assert log["actor_id"] is None


def test_state_transitions_record_both_sides(db, full_flow):
    """FR-076：內容包含前後狀態。"""
    transitions = {
        log["action"]: (log["from_status"], log["to_status"])
        for log in _logs(db, full_flow)
        if log["from_status"] or log["to_status"]
    }
    assert transitions["QUESTION_ASSIGNED"] == ("PENDING_ASSIGN", "PENDING_CANDIDATE")
    assert transitions["ANSWER_SUBMITTED"] == ("PENDING_CANDIDATE", "COMPLETED_AWAITING_REVIEW")
    assert transitions["DECISION_RECORDED"] == ("COMPLETED_AWAITING_REVIEW", "DECIDED")


def test_audit_detail_contains_no_personal_data_or_answers(db, full_flow):
    """FR-079、FR-080：detail 不得含個資或作答內容。"""
    serialized = str(_logs(db, full_flow))
    for forbidden in (CANDIDATE_NAME, CANDIDATE_EMAIL, CANDIDATE_PHONE, ANSWER, INTERNAL_COMMENT):
        assert forbidden not in serialized


def test_audit_records_cannot_be_updated_or_deleted(db, full_flow, hr_headers):
    """FR-078：稽核紀錄不得被修改或刪除。"""
    from backend.src.repositories.base import ROLE_HR, DataAccessError, RequestContext
    from backend.src.repositories.memory_store import InMemoryDataStore

    store = InMemoryDataStore(db, RequestContext(role=ROLE_HR))
    with pytest.raises(DataAccessError):
        store.update("audit_logs", {"action": "TAMPERED"}, filters={"assessment_id": full_flow})


def test_decided_assessment_history_is_complete(db, full_flow):
    """SC-014：已決策的考核，其歷程覆蓋率必須是 100%。"""
    actions = {log["action"] for log in _logs(db, full_flow)}
    required = {
        "ASSESSMENT_CREATED",
        "QUESTION_ASSIGNED",
        "ANSWER_SUBMITTED",
        "DECISION_RECORDED",
    }
    assert required <= actions
