"""契約：POST /candidate/session/{token}/submit（FR-033～FR-035、FR-053）。"""

from __future__ import annotations

PAYLOAD = {"answer": "print(sum(map(int, input().split())))", "language": "python"}


def test_submit_returns_submitted_at(client, make_assessment, question_snapshot, db):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    response = client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD)
    assert response.status_code == 200, response.text
    assert response.json()["submitted_at"] is not None

    stored = db.find("assessments", id=assessment["id"])
    assert stored["status"] == "COMPLETED_AWAITING_REVIEW"
    assert stored["candidate_answer"] == PAYLOAD["answer"]
    assert stored["code_language"] == "python"


def test_duplicate_submit_returns_409(client, make_assessment, question_snapshot):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    assert (
        client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD).status_code
        == 200
    )

    second = client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD)
    assert second.status_code == 409
    assert set(second.json()) >= {"code", "message"}


def test_submit_on_expired_link_returns_410(client, make_assessment, question_snapshot):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
    )
    assert (
        client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD).status_code
        == 410
    )


def test_submit_before_question_assigned_returns_409(client, make_assessment):
    assessment = make_assessment(status="PENDING_ASSIGN")
    assert (
        client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD).status_code
        == 409
    )


def test_submit_records_audit_without_answer_content(
    client, make_assessment, question_snapshot, db
):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD)

    logs = [log for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]]
    submitted = [log for log in logs if log["action"] == "ANSWER_SUBMITTED"]
    assert len(submitted) == 1
    assert submitted[0]["from_status"] == "PENDING_CANDIDATE"
    assert submitted[0]["to_status"] == "COMPLETED_AWAITING_REVIEW"
    assert submitted[0]["actor_role"] == "CANDIDATE"
    assert PAYLOAD["answer"] not in str(logs)


def test_submit_triggers_evaluation(client, make_assessment, question_snapshot, db):
    """提交後自動觸發評測，無需人工操作（FR-053）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(f"/candidate/session/{assessment['token']}/submit", json=PAYLOAD)

    reports = [r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"]]
    assert len(reports) == 1


def test_unknown_token_returns_404(client):
    assert client.post("/candidate/session/nope/submit", json=PAYLOAD).status_code == 404
