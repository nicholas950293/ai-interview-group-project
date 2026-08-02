"""個資刪除（FR-082、data-model.md「個資刪除流程」）。

不採實體刪除：`audit_logs` 的唯附加要求與稽核完整性優先於資料列的移除，
而去識別化已足以達成個資保護目的。因此本測試同時驗證「個資消失」與
「稽核歷程仍在」——兩者缺一都不算正確。
"""

from __future__ import annotations

import pytest

from backend.src.audit.logger import AuditLogger
from backend.src.repositories.assessment_repo import AssessmentRepository
from backend.src.repositories.base import ROLE_HR, RequestContext
from backend.src.repositories.memory_store import InMemoryDataStore
from backend.src.services.pii_service import PiiService

TARGET_EMAIL = "erase.me@example.com"


@pytest.fixture
def hr_context():
    return RequestContext(
        role=ROLE_HR,
        auth_user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
        internal_user_id="11111111-1111-4111-8111-111111111111",
    )


@pytest.fixture
def service(db, hr_context):
    store = InMemoryDataStore(db, hr_context)
    return PiiService(AssessmentRepository(store), AuditLogger(store), hr_context)


@pytest.fixture
def records(db, make_assessment, question_snapshot):
    created = []
    for _ in range(2):
        row = make_assessment(
            status="DECIDED",
            question_snapshot=question_snapshot,
            candidate_answer="print('作答內容')",
            code_language="python",
            submitted=True,
            final_decision="FAIL",
        )
        row = db.find("assessments", id=row["id"])
        row["email"] = TARGET_EMAIL
        row["name"] = "王小明"
        row["phone"] = "0912-345-678"
        row["ai_chat_history"] = [{"role": "candidate", "content": "提問內容"}]
        db.insert_raw(
            "audit_logs",
            {"assessment_id": row["id"], "action": "ASSESSMENT_CREATED", "actor_role": "HR"},
        )
        db.insert_raw(
            "ai_reports",
            {"assessment_id": row["id"], "attempt_no": 1, "status": "SUCCESS", "dimensions": {}},
        )
        created.append(row)
    return created


def test_all_assessments_of_the_same_email_are_processed(service, records, db):
    """同一 Email 的所有考核紀錄必須一併處理（FR-082）。"""
    result = service.erase(TARGET_EMAIL)
    assert result["erased"] == 2

    for record in records:
        stored = db.find("assessments", id=record["id"])
        assert stored["name"] != "王小明"
        assert stored["email"] != TARGET_EMAIL
        assert stored["phone"] is None
        assert stored["candidate_answer"] is None
        assert stored["ai_chat_history"] == []


def test_deidentified_placeholders_are_stable_and_non_reversible(service, records, db):
    service.erase(TARGET_EMAIL)
    stored = db.find("assessments", id=records[0]["id"])
    assert "王" not in stored["name"]
    assert "@example.com" not in stored["email"]
    assert stored["email"].endswith(".invalid"), "去識別化的 Email 必須無法寄達"


def test_audit_history_is_preserved(service, records, db):
    """稽核紀錄僅保留去識別化的考核識別碼（FR-082、FR-078）。"""
    service.erase(TARGET_EMAIL)
    for record in records:
        logs = [log for log in db.tables["audit_logs"] if log["assessment_id"] == record["id"]]
        assert any(log["action"] == "ASSESSMENT_CREATED" for log in logs)
        assert any(log["action"] == "PII_ERASED" for log in logs)


def test_reports_and_executions_are_kept(service, records, db):
    """關聯的 ai_reports 與 execution_records 保留——它們不含個資。"""
    service.erase(TARGET_EMAIL)
    reports = [r for r in db.tables["ai_reports"] if r["assessment_id"] == records[0]["id"]]
    assert reports


def test_pii_erased_audit_contains_no_personal_data(service, records, db):
    service.erase(TARGET_EMAIL)
    logs = [log for log in db.tables["audit_logs"] if log["action"] == "PII_ERASED"]
    serialized = str(logs)
    assert TARGET_EMAIL not in serialized
    assert "王小明" not in serialized
    assert "0912-345-678" not in serialized


def test_erasing_an_unknown_email_is_a_no_op(service, db):
    result = service.erase("nobody@example.com")
    assert result["erased"] == 0


def test_erasure_is_idempotent(service, records, db):
    service.erase(TARGET_EMAIL)
    second = service.erase(TARGET_EMAIL)
    assert second["erased"] == 0, "已去識別化的紀錄不應被重複處理"
