"""US4：評測失敗不得阻擋提交（FR-059、quickstart.md 情境 10）。

「AI 掛了，應徵者的提交就消失」是本系統最不可接受的失敗模式之一——
應徵者無法重來，而失敗的原因與他完全無關。
"""

from __future__ import annotations

ANSWER = "print(1)"


def _submit(client, assessment):
    return client.post(
        f"/candidate/session/{assessment['token']}/submit",
        json={"answer": ANSWER, "language": "python"},
    )


def test_submission_succeeds_when_ai_is_unavailable(
    client, make_assessment, question_snapshot, fake_ai, db
):
    fake_ai.set_unavailable("evaluate")
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)

    response = _submit(client, assessment)
    assert response.status_code == 200

    stored = db.find("assessments", id=assessment["id"])
    assert stored["status"] == "COMPLETED_AWAITING_REVIEW"
    assert stored["candidate_answer"] == ANSWER


def test_failed_evaluation_is_recorded_not_lost(
    client, make_assessment, question_snapshot, fake_ai, db
):
    fake_ai.set_unavailable("evaluate")
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    _submit(client, assessment)

    report = next(r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"])
    assert report["status"] == "FAILED"
    assert report["error_message"]
    assert report["dimensions"] is None

    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]
    ]
    assert "EVALUATION_FAILED" in actions


def test_manager_can_still_review_and_decide_without_a_report(
    client, eng_manager_headers, make_assessment, question_snapshot, fake_ai, db
):
    """主管仍可在無 AI 報告的情況下自行審閱決策（spec.md 驗收情境 4.5）。"""
    fake_ai.set_unavailable("evaluate")
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    _submit(client, assessment)

    detail = client.get(
        f"/manager/assessments/{assessment['id']}", headers=eng_manager_headers
    ).json()
    assert detail["candidate_answer"] == ANSWER
    assert detail["ai_report"]["status"] == "FAILED"

    decision = client.post(
        f"/manager/assessments/{assessment['id']}/decision",
        json={"result": "PASS", "internal_comment": "AI 報告缺席，依人工審閱決定"},
        headers=eng_manager_headers,
    )
    assert decision.status_code == 200
    assert db.find("assessments", id=assessment["id"])["status"] == "DECIDED"


def test_retry_keeps_the_failed_attempt(
    client, eng_manager_headers, make_assessment, question_snapshot, fake_ai, db
):
    """重試不得覆寫失敗紀錄——ai_reports 為唯附加（FR-059、FR-078）。"""
    fake_ai.set_unavailable("evaluate")
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    _submit(client, assessment)

    fake_ai.unavailable_for.clear()
    client.post(f"/manager/assessments/{assessment['id']}/reevaluate", headers=eng_manager_headers)

    reports = sorted(
        (r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"]),
        key=lambda r: r["attempt_no"],
    )
    assert [r["attempt_no"] for r in reports] == [1, 2]
    assert reports[0]["status"] == "FAILED"
    assert reports[1]["status"] == "SUCCESS"


def test_latest_attempt_is_the_one_shown(
    client, eng_manager_headers, make_assessment, question_snapshot, fake_ai
):
    fake_ai.set_unavailable("evaluate")
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    _submit(client, assessment)

    fake_ai.unavailable_for.clear()
    client.post(f"/manager/assessments/{assessment['id']}/reevaluate", headers=eng_manager_headers)

    detail = client.get(
        f"/manager/assessments/{assessment['id']}", headers=eng_manager_headers
    ).json()
    assert detail["ai_report"]["attempt_no"] == 2
    assert detail["ai_report"]["status"] == "SUCCESS"
