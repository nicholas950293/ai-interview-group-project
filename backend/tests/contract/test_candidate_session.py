"""契約：GET /candidate/session/{token}（FR-018、FR-029）。

最關鍵的斷言是**隱藏測資的內容不出現在回應中**。應徵者若能讀到隱藏測資，
自動評測的正確性維度就失去意義（FR-054）。
"""

from __future__ import annotations

HIDDEN_STDIN = "隱藏輸入-不得外洩"
HIDDEN_STDOUT = "隱藏輸出-不得外洩"


def _snapshot_with_hidden_case(base: dict) -> dict:
    snapshot = dict(base)
    snapshot["test_cases"] = [
        {
            "name": "公開案例",
            "stdin": "3 5\n",
            "expected_stdout": "8\n",
            "is_hidden": False,
            "timeout_seconds": 10,
        },
        {
            "name": "隱藏案例",
            "stdin": HIDDEN_STDIN,
            "expected_stdout": HIDDEN_STDOUT,
            "is_hidden": True,
            "timeout_seconds": 10,
        },
    ]
    return snapshot


def test_session_loads_without_authentication(client, make_assessment, question_snapshot):
    """應徵者無需帳號密碼登入（FR-029、spec.md 驗收情境 3.1）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    response = client.get(f"/candidate/session/{assessment['token']}")
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["job_title"] == "後端工程師"
    assert body["dept_type"] == "ENGINEERING"
    assert body["status"] == "PENDING_CANDIDATE"
    assert body["question"]["title"] == "兩數相加"


def test_hidden_test_cases_are_absent(client, make_assessment, question_snapshot):
    assessment = make_assessment(
        status="PENDING_CANDIDATE",
        question_snapshot=_snapshot_with_hidden_case(question_snapshot),
    )
    response = client.get(f"/candidate/session/{assessment['token']}")
    assert response.status_code == 200

    assert HIDDEN_STDIN not in response.text
    assert HIDDEN_STDOUT not in response.text
    assert "隱藏案例" not in response.text

    sample_cases = response.json()["question"]["sample_cases"]
    assert [case["name"] for case in sample_cases] == ["公開案例"]
    assert set(sample_cases[0]) == {"name", "stdin", "expected_stdout"}


def test_response_excludes_report_and_decision(client, make_assessment, question_snapshot, db):
    """應徵者不得存取 AI 報告或主管決策（FR-004）。"""
    assessment = make_assessment(
        status="COMPLETED_AWAITING_REVIEW", question_snapshot=question_snapshot, submitted=True
    )
    db.insert_raw(
        "ai_reports",
        {
            "assessment_id": assessment["id"],
            "attempt_no": 1,
            "status": "SUCCESS",
            "dimensions": {"correctness": {"score": 80, "comment": "報告內容不得外洩"}},
        },
    )
    db.insert_raw(
        "manager_decisions",
        {
            "assessment_id": assessment["id"],
            "revision_no": 1,
            "decided_by": "22222222-2222-4222-8222-222222222222",
            "result": "FAIL",
            "internal_comment": "內部評語不得外洩",
        },
    )

    response = client.get(f"/candidate/session/{assessment['token']}")
    assert "報告內容不得外洩" not in response.text
    assert "內部評語不得外洩" not in response.text
    assert "dimensions" not in response.text


def test_unknown_token_returns_404(client):
    assert client.get("/candidate/session/token-does-not-exist").status_code == 404


def test_pending_assign_shows_status_without_question(client, make_assessment):
    """未指派題目時，應徵者看到「題目準備中」而非空白頁面（spec.md 邊界情況）。"""
    assessment = make_assessment(status="PENDING_ASSIGN")
    body = client.get(f"/candidate/session/{assessment['token']}").json()
    assert body["status"] == "PENDING_ASSIGN"
    assert body["question"] is None


def test_submitted_session_reports_submission(client, make_assessment, question_snapshot):
    """已提交者再次開啟連結時，看到已完成提交（FR-034、spec.md 驗收情境 3.7）。"""
    assessment = make_assessment(
        status="COMPLETED_AWAITING_REVIEW", question_snapshot=question_snapshot, submitted=True
    )
    body = client.get(f"/candidate/session/{assessment['token']}").json()
    assert body["submitted_at"] is not None
    assert body["status"] == "COMPLETED_AWAITING_REVIEW"


def test_trial_runs_remaining_reflects_usage(client, make_assessment, question_snapshot):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, trial_run_count=3
    )
    body = client.get(f"/candidate/session/{assessment['token']}").json()
    assert body["trial_runs_remaining"] == 17
