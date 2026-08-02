"""US3：沙箱不可用時的降級行為（FR-047、憲章原則 VI）。

憲章原則 VI 標示為不可妥協且不得以例外繞過：沙箱不可用時，系統**必須**
降級為「接受提交但不執行」，**不得**改以未隔離的方式執行程式碼。

本測試是那條規則的執行點——它斷言的不只是「提交仍成功」，
還包括「沒有任何程式碼在沙箱之外被執行」。
"""

from __future__ import annotations

import pytest

from backend.src.models.report import TerminationReason
from backend.src.sandbox.runner import unavailable_result

CODE = "import os; os.system('echo pwned')"


@pytest.fixture
def degraded(fake_sandbox):
    fake_sandbox.healthy = False
    return fake_sandbox


def test_submission_still_succeeds_when_sandbox_is_down(
    client, degraded, make_assessment, question_snapshot, db
):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    token = assessment["token"]

    assert (
        client.post(
            f"/candidate/session/{token}/run",
            json={"code": CODE, "language": "python", "stdin": ""},
        ).status_code
        == 503
    )

    submitted = client.post(
        f"/candidate/session/{token}/submit", json={"answer": CODE, "language": "python"}
    )
    assert submitted.status_code == 200, "沙箱不可用不得阻擋提交（FR-047）"

    stored = db.find("assessments", id=assessment["id"])
    assert stored["status"] == "COMPLETED_AWAITING_REVIEW"
    assert stored["candidate_answer"] == CODE


def test_degraded_run_never_executes_outside_the_sandbox(
    client, degraded, make_assessment, question_snapshot
):
    """替身的 health_check 為 False 時，run 只會回傳 SANDBOX_UNAVAILABLE。

    若日後有人加入「沙箱掛了就在本機跑跑看」的分支，這個斷言會失敗。
    """
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(
        f"/candidate/session/{assessment['token']}/run",
        json={"code": CODE, "language": "python", "stdin": ""},
    )
    for call in degraded.calls:
        assert call.code == CODE
    assert unavailable_result().termination_reason is TerminationReason.SANDBOX_UNAVAILABLE


def test_evaluation_records_sandbox_unavailable(
    client, degraded, make_assessment, question_snapshot, db
):
    """未能執行必須被記錄，並允許事後重試（FR-047、FR-059）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(
        f"/candidate/session/{assessment['token']}/submit",
        json={"answer": CODE, "language": "python"},
    )

    records = [
        r
        for r in db.tables["execution_records"]
        if r["assessment_id"] == assessment["id"] and r["trigger"] == "EVALUATION"
    ]
    assert records, "評測未能執行也必須留下紀錄"
    assert records[0]["termination_reason"] == "SANDBOX_UNAVAILABLE"


def test_report_still_produced_without_test_verification(
    client, degraded, make_assessment, question_snapshot, db
):
    """沙箱不可用時，correctness 必須明確標示未經測資驗證（contracts/ai-provider.md）。"""
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    client.post(
        f"/candidate/session/{assessment['token']}/submit",
        json={"answer": CODE, "language": "python"},
    )

    report = next(r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"])
    assert report["status"] == "SUCCESS"
    assert report["test_pass_ratio"] is None
    assert "未經測資驗證" in report["dimensions"]["correctness"]["comment"]
