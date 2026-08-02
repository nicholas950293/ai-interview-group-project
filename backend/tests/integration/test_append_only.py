"""唯附加資料表（FR-064、FR-078；憲章原則 V）。

斷言 UPDATE 與 DELETE 由資料庫拒絕。以資料表擁有者身分連線時 GRANT 不生效，
因此 0011 另以觸發器構成第二道防線——本測試同時涵蓋兩者。
"""

from __future__ import annotations

import pytest

from backend.tests.conftest_postgres import ENG_MANAGER_CLAIMS

pytestmark = pytest.mark.postgres

APPEND_ONLY_TABLES = ("execution_records", "ai_reports", "manager_decisions", "audit_logs")


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_authenticated_role_has_no_update_or_delete_grant(as_role, table):
    manager = as_role(ENG_MANAGER_CLAIMS)
    rows = manager.execute(
        """
        SELECT privilege_type FROM information_schema.role_table_grants
        WHERE table_name = %s AND grantee IN ('authenticated', 'anon', 'PUBLIC')
        """,
        (table,),
    ).fetchall()
    granted = {row[0] for row in rows}
    assert "UPDATE" not in granted, f"{table} 不得對使用者角色開放 UPDATE（FR-078）"
    assert "DELETE" not in granted, f"{table} 不得對使用者角色開放 DELETE（FR-078）"


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_owner_update_is_rejected_by_trigger(psycopg, owner_conn, eng_assessment_id, table):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute(
            f"UPDATE {table} SET created_at = NOW() WHERE assessment_id = %s",  # noqa: S608
            (eng_assessment_id,),
        )


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_owner_delete_is_rejected_by_trigger(psycopg, owner_conn, eng_assessment_id, table):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute(
            f"DELETE FROM {table} WHERE assessment_id = %s",  # noqa: S608
            (eng_assessment_id,),
        )


def test_ai_report_pending_to_terminal_is_the_only_permitted_update(
    psycopg, owner_conn, eng_assessment_id
):
    """ai_reports 的唯一例外：status 由 PENDING 轉為終態（data-model.md §6）。"""
    owner_conn.execute(
        "INSERT INTO ai_reports (assessment_id, attempt_no, status) VALUES (%s, 2, 'PENDING')",
        (eng_assessment_id,),
    )
    owner_conn.execute(
        "UPDATE ai_reports SET status = 'SUCCESS' WHERE assessment_id = %s AND attempt_no = 2",
        (eng_assessment_id,),
    )
    (status,) = owner_conn.execute(
        "SELECT status FROM ai_reports WHERE assessment_id = %s AND attempt_no = 2",
        (eng_assessment_id,),
    ).fetchone()
    assert status == "SUCCESS"

    # 終態之後不得再變更
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner_conn.execute(
            "UPDATE ai_reports SET status = 'FAILED' WHERE assessment_id = %s AND attempt_no = 2",
            (eng_assessment_id,),
        )


def test_decision_revision_is_append_not_overwrite(owner_conn, eng_assessment_id):
    """修訂以新增列呈現，原紀錄仍存在（FR-064）。"""
    owner_conn.execute(
        """
        INSERT INTO manager_decisions
            (assessment_id, revision_no, decided_by, result, internal_comment)
        VALUES (%s, 2, '22222222-2222-4222-8222-222222222222', 'FAIL', '修訂後評語')
        """,
        (eng_assessment_id,),
    )
    rows = owner_conn.execute(
        "SELECT revision_no, result FROM manager_decisions"
        " WHERE assessment_id = %s ORDER BY revision_no",
        (eng_assessment_id,),
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2]
    assert rows[0][1] == "PASS", "原始決策不得被覆寫"
