"""契約：AI 評測報告的形狀（FR-055～FR-058；憲章原則 V）。

最重要的斷言是**否定的**：回應中不得存在任何加權總分、綜合評價或錄取建議
欄位（FR-057）。這不是「不要顯示」，而是「不存在」——系統不得自動產生
綜合判斷，綜合判斷必須由主管做出。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.src.models.report import DIMENSION_NAMES, AiReport, Dimension

# 任何形式的整體判斷都不得出現
FORBIDDEN_KEYS = (
    "total_score",
    "total",
    "overall",
    "overall_score",
    "overall_comment",
    "weighted_score",
    "recommendation",
    "hiring_recommendation",
    "verdict",
    "final_score",
    "summary",
)


@pytest.fixture
def submitted(client, make_assessment, question_snapshot, fake_sandbox):
    from backend.src.models.report import ExecutionResult, TerminationReason

    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    fake_sandbox.register_for_stdin(
        "3 5\n",
        "python",
        ExecutionResult(stdout="8\n", exit_code=0, termination_reason=TerminationReason.COMPLETED),
    )
    fake_sandbox.register_for_stdin(
        "0 0\n",
        "python",
        ExecutionResult(stdout="0\n", exit_code=0, termination_reason=TerminationReason.COMPLETED),
    )
    client.post(
        f"/candidate/session/{assessment['token']}/submit",
        json={"answer": "print(sum(map(int, input().split())))", "language": "python"},
    )
    return assessment


def test_report_contains_all_four_dimensions(client, eng_manager_headers, submitted):
    detail = client.get(
        f"/manager/assessments/{submitted['id']}", headers=eng_manager_headers
    ).json()
    report = detail["ai_report"]

    assert report["status"] == "SUCCESS"
    assert set(report["dimensions"]) == set(DIMENSION_NAMES)
    for name in DIMENSION_NAMES:
        dimension = report["dimensions"][name]
        assert set(dimension) == {"score", "comment"}
        assert 0 <= dimension["score"] <= 100
        assert dimension["comment"]


def test_report_carries_advisory_notice(client, eng_manager_headers, submitted):
    """報告必須在所有呈現位置明確標示為 AI 輔助建議（FR-058）。"""
    detail = client.get(
        f"/manager/assessments/{submitted['id']}", headers=eng_manager_headers
    ).json()
    notice = detail["ai_report"]["advisory_notice"]
    assert notice
    assert "僅供參考" in notice
    assert "主管" in notice


def test_report_has_no_aggregate_judgement(client, eng_manager_headers, submitted):
    response = client.get(f"/manager/assessments/{submitted['id']}", headers=eng_manager_headers)
    report = response.json()["ai_report"]
    for key in FORBIDDEN_KEYS:
        assert key not in report, f"報告不得含 {key}（FR-057）"


def test_report_model_cannot_express_an_aggregate_score():
    """型別層防線：即使有人試圖塞入總分，模型也會拒絕（憲章原則 V）。"""
    dimensions = {name: Dimension(score=80, comment="說明") for name in DIMENSION_NAMES}
    report = AiReport(dimensions=dimensions, status="SUCCESS")
    assert report.has_all_dimensions()

    with pytest.raises(PydanticValidationError):
        AiReport(dimensions=dimensions, status="SUCCESS", total_score=80)


def test_report_records_the_model_id(client, eng_manager_headers, submitted):
    """實際使用的模型必須可追溯（research.md R-005）。"""
    detail = client.get(
        f"/manager/assessments/{submitted['id']}", headers=eng_manager_headers
    ).json()
    assert detail["ai_report"]["model_id"]
