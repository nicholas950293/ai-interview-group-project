"""US4 端到端：提交 → 測資驗證 → 四維度報告（quickstart.md 情境 6、SC-005）。

FR-054 要求正確性維度以測資通過比例作為客觀依據。因此本測試的核心是
**correctness.score 與 test_pass_ratio 一致**——若兩者可以不一致，
「客觀評測」這個說法就不成立。
"""

from __future__ import annotations

import pytest

from backend.src.models.report import ExecutionResult, TerminationReason

ANSWER = "print(sum(map(int, input().split())))"


def _ok(stdout: str) -> ExecutionResult:
    return ExecutionResult(
        stdout=stdout, exit_code=0, duration_ms=12, termination_reason=TerminationReason.COMPLETED
    )


@pytest.fixture
def submit(client, make_assessment, question_snapshot, fake_sandbox):
    def _submit(outputs: dict[str, str]):
        assessment = make_assessment(
            status="PENDING_CANDIDATE", question_snapshot=question_snapshot
        )
        for stdin, stdout in outputs.items():
            fake_sandbox.register_for_stdin(stdin, "python", _ok(stdout))
        client.post(
            f"/candidate/session/{assessment['token']}/submit",
            json={"answer": ANSWER, "language": "python"},
        )
        return assessment

    return _submit


def test_all_cases_pass_yields_full_correctness(client, eng_manager_headers, submit, db):
    assessment = submit({"3 5\n": "8\n", "0 0\n": "0\n"})

    report = next(r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"])
    assert report["status"] == "SUCCESS"
    assert report["test_pass_ratio"] == 1.0
    assert report["dimensions"]["correctness"]["score"] == 100


def test_correctness_matches_pass_ratio(client, eng_manager_headers, submit, db):
    """一半測資通過 → pass_ratio 0.5 → correctness 50（FR-054）。"""
    assessment = submit({"3 5\n": "8\n", "0 0\n": "錯誤輸出\n"})

    report = next(r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"])
    assert report["test_pass_ratio"] == 0.5
    assert report["dimensions"]["correctness"]["score"] == 50


def test_hidden_cases_are_evaluated_too(client, submit, db):
    """隱藏測資僅用於評測——它必須真的被執行。"""
    assessment = submit({"3 5\n": "8\n", "0 0\n": "0\n"})
    records = [
        r
        for r in db.tables["execution_records"]
        if r["assessment_id"] == assessment["id"] and r["trigger"] == "EVALUATION"
    ]
    assert records
    results = records[0]["test_results"]
    assert results["total"] == 2
    assert [case["name"] for case in results["cases"]] == ["基本案例", "隱藏邊界"]


def test_execution_record_does_not_store_actual_output(client, submit, db):
    """cases[].actual_stdout 不予保存——避免隱藏測資的預期輸出經由紀錄外洩。"""
    assessment = submit({"3 5\n": "8\n", "0 0\n": "0\n"})
    records = [
        r
        for r in db.tables["execution_records"]
        if r["assessment_id"] == assessment["id"] and r["trigger"] == "EVALUATION"
    ]
    for case in records[0]["test_results"]["cases"]:
        assert "actual_stdout" not in case
        assert set(case) == {"name", "passed", "duration_ms", "termination_reason"}


def test_evaluation_is_audited(client, submit, db):
    assessment = submit({"3 5\n": "8\n", "0 0\n": "0\n"})
    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == assessment["id"]
    ]
    assert "EVALUATION_STARTED" in actions
    assert "EVALUATION_COMPLETED" in actions


def test_report_is_visible_to_manager_only(
    client, eng_manager_headers, design_manager_headers, submit
):
    assessment = submit({"3 5\n": "8\n", "0 0\n": "0\n"})
    assert (
        client.get(
            f"/manager/assessments/{assessment['id']}", headers=eng_manager_headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/manager/assessments/{assessment['id']}", headers=design_manager_headers
        ).status_code
        == 404
    )


def test_reevaluate_creates_a_new_attempt(client, eng_manager_headers, submit, db):
    """FR-059：重試產生新的 attempt_no，失敗紀錄保留。"""
    assessment = submit({"3 5\n": "8\n", "0 0\n": "0\n"})
    response = client.post(
        f"/manager/assessments/{assessment['id']}/reevaluate", headers=eng_manager_headers
    )
    assert response.status_code == 202

    reports = [r for r in db.tables["ai_reports"] if r["assessment_id"] == assessment["id"]]
    assert sorted(r["attempt_no"] for r in reports) == [1, 2]
