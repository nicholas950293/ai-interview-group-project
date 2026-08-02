"""契約：POST /candidate/session/{token}/run（FR-031、FR-032、FR-045、FR-047）。"""

from __future__ import annotations

from backend.src.models.report import ExecutionResult, TerminationReason

CODE = "print(sum(map(int, input().split())))"
PAYLOAD = {"code": CODE, "language": "python", "stdin": "3 5\n"}


def test_run_returns_execution_result(client, make_assessment, question_snapshot, fake_sandbox):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    fake_sandbox.register(
        CODE,
        "python",
        ExecutionResult(
            stdout="8\n",
            stderr="",
            exit_code=0,
            duration_ms=42,
            termination_reason=TerminationReason.COMPLETED,
        ),
    )

    response = client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD)
    assert response.status_code == 200, response.text

    body = response.json()
    assert set(body) >= {"stdout", "stderr", "exit_code", "duration_ms", "termination_reason"}
    assert body["stdout"] == "8\n"
    assert body["termination_reason"] == "COMPLETED"


def test_run_does_not_return_test_case_comparison(client, make_assessment, question_snapshot):
    """試跑僅回傳執行結果，不回傳測資比對結果（contracts/openapi.yaml）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    body = client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD).json()
    assert "test_results" not in body
    assert "passed" not in body


def test_compile_error_is_not_a_system_failure(
    client, make_assessment, question_snapshot, fake_sandbox
):
    """編譯錯誤以錯誤訊息回傳，不得視為系統故障（FR-045）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    fake_sandbox.register(
        "broken",
        "go",
        ExecutionResult(
            stderr="syntax error: unexpected }",
            exit_code=None,
            termination_reason=TerminationReason.COMPILE_ERROR,
        ),
    )
    response = client.post(
        f"/candidate/session/{assessment['token']}/run",
        json={"code": "broken", "language": "go", "stdin": ""},
    )
    assert response.status_code == 200
    assert response.json()["termination_reason"] == "COMPILE_ERROR"
    assert "syntax error" in response.json()["stderr"]


def test_trial_run_limit_returns_429(client, make_assessment, question_snapshot):
    """達上限後停止提供試跑（FR-032）。"""
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, trial_run_count=20
    )
    response = client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD)
    assert response.status_code == 429
    assert set(response.json()) >= {"code", "message"}


def test_sandbox_unavailable_returns_503(client, make_assessment, question_snapshot, fake_sandbox):
    """沙箱不可用回傳 503；提交不受影響（FR-047）。"""
    fake_sandbox.healthy = False
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    response = client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD)
    assert response.status_code == 503


def test_expired_link_returns_410(client, make_assessment, question_snapshot):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
    )
    response = client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD)
    assert response.status_code == 410


def test_run_is_recorded_for_audit(client, make_assessment, question_snapshot, db):
    """所有沙箱執行必須留下稽核紀錄（FR-048）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD)

    records = [r for r in db.tables["execution_records"] if r["assessment_id"] == assessment["id"]]
    assert len(records) == 1
    assert records[0]["trigger"] == "TRIAL_RUN"

    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]
    ]
    assert "TRIAL_RUN" in actions
    assert db.find("assessments", id=assessment["id"])["trial_run_count"] == 1


def test_audit_detail_excludes_submitted_code(client, make_assessment, question_snapshot, db):
    """FR-080：作答內容不得寫入稽核紀錄。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(f"/candidate/session/{assessment['token']}/run", json=PAYLOAD)
    logs = [log for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]]
    assert CODE not in str(logs)


def test_unknown_token_returns_404(client):
    assert client.post("/candidate/session/nope/run", json=PAYLOAD).status_code == 404
