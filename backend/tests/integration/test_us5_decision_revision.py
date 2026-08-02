"""US5：決策修訂為唯附加（FR-064、quickstart.md 情境 8）。

「決策後又需修改」是招募流程的常態。憲章原則 V 要求更正以新增紀錄呈現，
不得改寫或刪除既有紀錄——一個會被覆寫的欄位不是歷程，是最新值。
"""

from __future__ import annotations

import pytest


@pytest.fixture
def decided(client, eng_manager_headers, make_assessment, question_snapshot):
    assessment = make_assessment(
        status="COMPLETED_AWAITING_REVIEW",
        question_snapshot=question_snapshot,
        candidate_answer="print(1)",
        code_language="python",
        submitted=True,
    )
    client.post(
        f"/manager/assessments/{assessment['id']}/decision",
        json={"result": "PASS", "internal_comment": "第一次評語"},
        headers=eng_manager_headers,
    )
    return assessment


def test_second_decision_creates_revision_two(client, eng_manager_headers, decided, db):
    response = client.post(
        f"/manager/assessments/{decided['id']}/decision",
        json={"result": "FAIL", "internal_comment": "修訂後評語"},
        headers=eng_manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["revision_no"] == 2

    decisions = sorted(
        (d for d in db.tables["manager_decisions"] if d["assessment_id"] == decided["id"]),
        key=lambda d: d["revision_no"],
    )
    assert [d["revision_no"] for d in decisions] == [1, 2]


def test_original_decision_is_preserved(client, eng_manager_headers, decided, db):
    client.post(
        f"/manager/assessments/{decided['id']}/decision",
        json={"result": "FAIL", "internal_comment": "修訂後評語"},
        headers=eng_manager_headers,
    )
    first = next(
        d
        for d in db.tables["manager_decisions"]
        if d["assessment_id"] == decided["id"] and d["revision_no"] == 1
    )
    assert first["result"] == "PASS"
    assert first["internal_comment"] == "第一次評語"


def test_final_decision_reflects_the_latest_revision(client, eng_manager_headers, decided, db):
    client.post(
        f"/manager/assessments/{decided['id']}/decision",
        json={"result": "FAIL"},
        headers=eng_manager_headers,
    )
    assert db.find("assessments", id=decided["id"])["final_decision"] == "FAIL"


def test_revision_is_audited_as_revised_not_recorded(client, eng_manager_headers, decided, db):
    client.post(
        f"/manager/assessments/{decided['id']}/decision",
        json={"result": "FAIL"},
        headers=eng_manager_headers,
    )
    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == decided["id"]
    ]
    assert actions.count("DECISION_RECORDED") == 1
    assert actions.count("DECISION_REVISED") == 1


def test_revision_does_not_change_status(client, eng_manager_headers, decided, db):
    """決策修訂只新增列，不改變狀態（data-model.md 狀態機）。"""
    client.post(
        f"/manager/assessments/{decided['id']}/decision",
        json={"result": "FAIL"},
        headers=eng_manager_headers,
    )
    assert db.find("assessments", id=decided["id"])["status"] == "DECIDED"


def test_all_revisions_are_visible_to_the_manager(client, eng_manager_headers, decided):
    client.post(
        f"/manager/assessments/{decided['id']}/decision",
        json={"result": "FAIL", "internal_comment": "修訂後評語"},
        headers=eng_manager_headers,
    )
    detail = client.get(f"/manager/assessments/{decided['id']}", headers=eng_manager_headers).json()
    assert [d["revision_no"] for d in detail["decisions"]] == [1, 2]
    assert detail["decisions"][0]["internal_comment"] == "第一次評語"


def test_hr_sees_only_the_result_never_the_comment(client, hr_headers, decided):
    """SC-012 的關鍵驗證：HR 完全取不到內部評語。"""
    rows = client.get("/hr/assessments", headers=hr_headers).json()
    row = next(r for r in rows if r["id"] == decided["id"])
    assert row["final_decision"] == "PASS"
    assert "internal_comment" not in row
    assert "第一次評語" not in str(rows)
