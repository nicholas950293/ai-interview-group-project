"""契約：GET /manager/assessments/{id}（FR-060）。

主管必須能檢視完整作答內容、沙箱執行紀錄、測試案例通過情形與完整
AI 對話歷程——這是「決策必須由真人做出」在資料面的前提（憲章原則 V）。
"""

from __future__ import annotations

import pytest

ANSWER = "print(sum(map(int, input().split())))"


@pytest.fixture
def reviewed(client, make_assessment, question_snapshot, db):
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)
    token = assessment["token"]

    client.post(
        f"/candidate/session/{token}/chat", json={"message": "這題的時間複雜度要求是什麼意思？"}
    )
    client.post(
        f"/candidate/session/{token}/run",
        json={"code": ANSWER, "language": "python", "stdin": "3 5\n"},
    )
    client.post(f"/candidate/session/{token}/submit", json={"answer": ANSWER, "language": "python"})
    return assessment


def test_detail_contains_everything_needed_for_review(client, eng_manager_headers, reviewed):
    detail = client.get(
        f"/manager/assessments/{reviewed['id']}", headers=eng_manager_headers
    ).json()

    assert detail["candidate_answer"] == ANSWER
    assert detail["code_language"] == "python"
    assert detail["question_snapshot"]["title"] == "兩數相加"
    assert detail["executions"], "必須包含沙箱執行紀錄"
    assert detail["ai_report"]["dimensions"], "必須包含測資通過情形與評測結果"
    assert detail["decisions"] == []


def test_detail_contains_full_chat_history(client, eng_manager_headers, reviewed):
    """完整對話歷程隨作答一併保存，供主管審閱（FR-051、FR-060）。"""
    detail = client.get(
        f"/manager/assessments/{reviewed['id']}", headers=eng_manager_headers
    ).json()
    history = detail["ai_chat_history"]
    assert [m["role"] for m in history] == ["candidate", "assistant"]
    assert history[0]["content"] == "這題的時間複雜度要求是什麼意思？"
    assert "guardrail_triggered" in history[1]


def test_detail_includes_test_case_results(client, eng_manager_headers, reviewed):
    detail = client.get(
        f"/manager/assessments/{reviewed['id']}", headers=eng_manager_headers
    ).json()
    evaluation = [e for e in detail["executions"] if e["trigger"] == "EVALUATION"]
    assert evaluation
    assert evaluation[0]["test_results"]["total"] == 2


def test_hr_cannot_access_manager_detail(client, hr_headers, reviewed):
    """AssessmentDetail 為主管專用；HR 呼叫必須被拒絕（contracts/openapi.yaml）。"""
    assert (
        client.get(f"/manager/assessments/{reviewed['id']}", headers=hr_headers).status_code == 403
    )


def test_other_department_manager_gets_404(client, design_manager_headers, reviewed):
    assert (
        client.get(
            f"/manager/assessments/{reviewed['id']}", headers=design_manager_headers
        ).status_code
        == 404
    )


def test_unknown_id_returns_404(client, eng_manager_headers):
    assert (
        client.get(
            "/manager/assessments/00000000-0000-4000-8000-000000000000",
            headers=eng_manager_headers,
        ).status_code
        == 404
    )
