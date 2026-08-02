"""US3：提交為單次動作（FR-034、quickstart.md 情境 6）。"""

from __future__ import annotations

FIRST = {"answer": "def solve(): return 1", "language": "python"}
SECOND = {"answer": "def solve(): return 2", "language": "go"}


def test_answer_is_immutable_after_submission(client, make_assessment, question_snapshot, db):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    token = assessment["token"]

    assert client.post(f"/candidate/session/{token}/submit", json=FIRST).status_code == 200
    assert client.post(f"/candidate/session/{token}/submit", json=SECOND).status_code == 409

    stored = db.find("assessments", id=assessment["id"])
    assert stored["candidate_answer"] == FIRST["answer"]
    assert stored["code_language"] == "python"


def test_trial_run_is_blocked_after_submission(client, make_assessment, question_snapshot, db):
    """提交後連結轉為唯讀（spec.md 邊界情況：重複提交）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    token = assessment["token"]
    client.post(f"/candidate/session/{token}/submit", json=FIRST)

    response = client.post(
        f"/candidate/session/{token}/run",
        json={"code": "print(1)", "language": "python", "stdin": ""},
    )
    assert response.status_code == 409

    records = [
        r
        for r in db.tables["execution_records"]
        if r["assessment_id"] == assessment["id"] and r["trigger"] == "TRIAL_RUN"
    ]
    assert records == []


def test_only_one_submission_audit_entry_exists(client, make_assessment, question_snapshot, db):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    token = assessment["token"]
    for _ in range(3):
        client.post(f"/candidate/session/{token}/submit", json=FIRST)

    submitted = [
        log
        for log in db.tables["audit_logs"]
        if log["assessment_id"] == assessment["id"] and log["action"] == "ANSWER_SUBMITTED"
    ]
    assert len(submitted) == 1


def test_repeated_submit_does_not_create_additional_reports(
    client, make_assessment, question_snapshot, db
):
    """重複提交不得重複觸發評測。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    token = assessment["token"]
    for _ in range(3):
        client.post(f"/candidate/session/{token}/submit", json=FIRST)

    reports = [r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"]]
    assert len(reports) == 1
