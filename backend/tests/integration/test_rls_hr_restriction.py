"""HR 受限資料表（FR-007、FR-008、SC-012）。

FR-008 要求「HR 角色的查詢結果本身即不包含受限欄位」。因此斷言的是
**回傳空集合**，而非「回傳了內容但被上層過濾」。
"""

from __future__ import annotations

import pytest

from backend.tests.conftest_postgres import ENG_MANAGER_CLAIMS, HR_CLAIMS

pytestmark = pytest.mark.postgres


def test_hr_query_on_ai_reports_returns_empty(as_role, eng_assessment_id):
    hr = as_role(HR_CLAIMS)
    rows = hr.execute(
        "SELECT id, dimensions FROM ai_reports WHERE assessment_id = %s", (eng_assessment_id,)
    ).fetchall()
    assert rows == [], "HR 在 ai_reports 上沒有任何政策，查詢必須回傳空集合（FR-008）"


def test_hr_query_on_manager_decisions_returns_empty(as_role, eng_assessment_id):
    hr = as_role(HR_CLAIMS)
    rows = hr.execute(
        "SELECT id, internal_comment FROM manager_decisions WHERE assessment_id = %s",
        (eng_assessment_id,),
    ).fetchall()
    assert rows == [], "HR 在 manager_decisions 上沒有任何政策，查詢必須回傳空集合（FR-007）"


def test_manager_of_same_department_can_read_both(as_role, eng_assessment_id):
    """對照組：同一份資料對同部門主管必須可讀，證明上面的空集合來自政策而非資料不存在。"""
    manager = as_role(ENG_MANAGER_CLAIMS)
    assert (
        manager.execute(
            "SELECT id FROM ai_reports WHERE assessment_id = %s", (eng_assessment_id,)
        ).fetchall()
        != []
    )
    assert (
        manager.execute(
            "SELECT internal_comment FROM manager_decisions WHERE assessment_id = %s",
            (eng_assessment_id,),
        ).fetchall()
        != []
    )


def test_hr_can_read_final_decision_but_not_comment(as_role, owner_conn, eng_assessment_id):
    """HR 取得決策結果的唯一來源是 assessments.final_decision（R-003）。"""
    owner_conn.execute(
        "UPDATE assessments SET final_decision = 'PASS' WHERE id = %s", (eng_assessment_id,)
    )
    hr = as_role(HR_CLAIMS)
    (final_decision,) = hr.execute(
        "SELECT final_decision FROM assessments WHERE id = %s", (eng_assessment_id,)
    ).fetchone()
    assert final_decision == "PASS"


def test_hr_view_excludes_answer_and_chat_history(as_role, eng_assessment_id):
    """HR 讀取的 view 不含 candidate_answer 與 ai_chat_history（data-model.md RLS 矩陣註 1）。"""
    hr = as_role(HR_CLAIMS)
    columns = {
        row[0]
        for row in hr.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'hr_assessments'"
        ).fetchall()
    }
    assert "candidate_answer" not in columns
    assert "ai_chat_history" not in columns
    assert {"id", "name", "job_title", "status", "final_decision", "email_status"} <= columns
