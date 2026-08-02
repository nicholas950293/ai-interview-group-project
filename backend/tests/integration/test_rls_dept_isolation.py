"""RLS 跨部門隔離（FR-003、FR-006、SC-008）。

斷言的是資料存取層的拒絕行為，而非 API 層的過濾——憲章「權限關卡」要求
越權測試驗證的必須是資料存取層。
"""

from __future__ import annotations

import pytest

from backend.tests.conftest_postgres import DESIGN_MANAGER_CLAIMS, ENG_MANAGER_CLAIMS

pytestmark = pytest.mark.postgres


def test_manager_sees_only_own_department_assessments(as_role, eng_assessment_id):
    eng = as_role(ENG_MANAGER_CLAIMS)
    rows = eng.execute("SELECT id FROM assessments WHERE id = %s", (eng_assessment_id,)).fetchall()
    assert len(rows) == 1, "同部門主管必須看得到本部門考核"

    design = as_role(DESIGN_MANAGER_CLAIMS)
    rows = design.execute(
        "SELECT id FROM assessments WHERE id = %s", (eng_assessment_id,)
    ).fetchall()
    assert rows == [], "他部門主管查詢必須回傳空集合，而非受限內容"


def test_manager_cannot_read_other_department_question_bank(as_role):
    design = as_role(DESIGN_MANAGER_CLAIMS)
    rows = design.execute("SELECT id FROM question_banks WHERE dept_id = 'ENG'").fetchall()
    assert rows == [], "題庫必須依部門隔離（FR-003）"

    eng = as_role(ENG_MANAGER_CLAIMS)
    rows = eng.execute("SELECT id FROM question_banks WHERE dept_id = 'ENG'").fetchall()
    assert rows, "同部門主管必須讀得到本部門題庫"


def test_manager_cannot_write_into_other_department(as_role, eng_assessment_id):
    """跨部門的寫入必須被拒絕，而非僅被隱藏。"""
    design = as_role(DESIGN_MANAGER_CLAIMS)

    design.execute(
        "UPDATE assessments SET job_title = '越權寫入' WHERE id = %s", (eng_assessment_id,)
    )
    rows = design.execute(
        "SELECT job_title FROM assessments WHERE id = %s", (eng_assessment_id,)
    ).fetchall()
    assert rows == [], "他部門的列在 UPDATE 的 USING 子句下即不可見，更新影響 0 列"

    eng = as_role(ENG_MANAGER_CLAIMS)
    (job_title,) = eng.execute(
        "SELECT job_title FROM assessments WHERE id = %s", (eng_assessment_id,)
    ).fetchone()
    assert job_title == "後端工程師", "原值必須未被他部門主管改動"


def test_manager_cannot_read_other_department_reports_and_decisions(as_role, eng_assessment_id):
    design = as_role(DESIGN_MANAGER_CLAIMS)

    assert (
        design.execute(
            "SELECT id FROM ai_reports WHERE assessment_id = %s", (eng_assessment_id,)
        ).fetchall()
        == []
    )
    assert (
        design.execute(
            "SELECT id FROM manager_decisions WHERE assessment_id = %s", (eng_assessment_id,)
        ).fetchall()
        == []
    )
    assert (
        design.execute(
            "SELECT id FROM execution_records WHERE assessment_id = %s", (eng_assessment_id,)
        ).fetchall()
        == []
    )


def test_anon_role_has_no_direct_table_access(psycopg, migrated_schema, eng_assessment_id):
    """應徵者路徑不得直連資料表，只能經 SECURITY DEFINER 函式（research.md R-002）。"""
    with psycopg.connect(migrated_schema, autocommit=True) as conn:
        conn.execute("SET ROLE anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM assessments")
