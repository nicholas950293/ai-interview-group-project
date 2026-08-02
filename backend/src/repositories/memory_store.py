"""資料庫的記憶體替身（憲章原則 II：測試套件必須能在無外部服務下完整執行）。

本模組**鏡射**下列遷移檔的行為，使離線套件能斷言權限與應徵者路徑的實際結果：

- `0009_rls_policies.sql`——RLS 政策矩陣（角色與部門的可見性）
- `0010_security_definer_functions.sql`——應徵者與評測路徑的六個函式
- `0011_append_only.sql`——唯附加資料表拒絕 UPDATE 與 DELETE

鏡射不是取代：SQL 版本由 `-m postgres` 標記的測試對真實 PostgreSQL 驗證
（research.md R-008）。此處的目的是讓「他部門主管查不到資料」這類斷言
在沒有資料庫的環境中依然是一項真實的測試，而非被跳過。

**不得**在本模組加入任何正式環境才有的行為分支。
"""

from __future__ import annotations

import copy
import itertools
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.src.repositories.base import (
    APPEND_ONLY_TABLES,
    ROLE_CANDIDATE,
    ROLE_HR,
    ROLE_MANAGER,
    ROLE_SYSTEM,
    DataAccessError,
    RequestContext,
)

TABLES = (
    "departments",
    "internal_users",
    "question_banks",
    "assessments",
    "execution_records",
    "ai_reports",
    "manager_decisions",
    "audit_logs",
)

# hr_assessments view：刻意不含 candidate_answer 與 ai_chat_history
HR_ASSESSMENT_COLUMNS = (
    "id",
    "name",
    "email",
    "phone",
    "job_title",
    "dept_id",
    "assigned_manager_id",
    "status",
    "token",
    "token_expires_at",
    "final_decision",
    "email_status",
    "email_error",
    "submitted_at",
    "created_at",
)

_LAZY_EXPIRABLE = ("PENDING_ASSIGN", "PENDING_CANDIDATE")


def _now() -> datetime:
    return datetime.now(UTC)


class InMemoryDatabase:
    """共用的資料容器。相當於一個 PostgreSQL 實例，與請求身分無關。"""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLES}
        self._audit_seq = itertools.count(1)

    # ── 供測試建立前置資料；不套用任何政策，相當於以擁有者身分寫入 ──
    def insert_raw(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        stored = _with_defaults(self, table, row)
        self.tables[table].append(stored)
        return copy.deepcopy(stored)

    def next_audit_id(self) -> int:
        return next(self._audit_seq)

    def find(self, table: str, **criteria: Any) -> dict[str, Any] | None:
        for row in self.tables[table]:
            if all(row.get(key) == value for key, value in criteria.items()):
                return row
        return None


def _with_defaults(db: InMemoryDatabase, table: str, row: dict[str, Any]) -> dict[str, Any]:
    stored = copy.deepcopy(row)
    if table == "audit_logs":
        stored.setdefault("id", db.next_audit_id())
    else:
        stored.setdefault("id", str(uuid.uuid4()))

    # manager_decisions 的時間欄位名為 decided_at，且沒有 created_at（見 0007 DDL）
    if table == "manager_decisions":
        stored.setdefault("decided_at", _now())
    else:
        stored.setdefault("created_at", _now())

    if table == "audit_logs":
        # 真實資料表的欄位一律存在（值可為 NULL）；替身必須一致，
        # 否則「欄位不存在」與「值為 NULL」會在測試中被混為一談。
        for column in ("from_status", "to_status", "actor_id", "detail"):
            stored.setdefault(column, None)
    elif table == "assessments":
        stored.setdefault("status", "PENDING_ASSIGN")
        stored.setdefault("email_status", "NOT_SENT")
        stored.setdefault("email_error", None)
        stored.setdefault("trial_run_count", 0)
        stored.setdefault("ai_chat_history", [])
        stored.setdefault("question_snapshot", None)
        stored.setdefault("candidate_answer", None)
        stored.setdefault("code_language", None)
        stored.setdefault("final_decision", None)
        stored.setdefault("submitted_at", None)
    elif table == "internal_users":
        stored.setdefault("is_active", True)
        stored.setdefault("dept_id", None)
    elif table == "question_banks":
        stored.setdefault("test_cases", [])
    return stored


def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    for column, condition in (filters or {}).items():
        operator, value = (
            (str(condition[0]), condition[1])
            if isinstance(condition, tuple) and len(condition) == 2
            else ("eq", condition)
        )
        actual = row.get(column)
        if operator == "eq" and actual != value:
            return False
        if operator == "neq" and actual == value:
            return False
        if operator == "in" and actual not in value:
            return False
        if operator == "is" and actual is not value:
            return False
        if operator == "lt" and not (actual is not None and actual < value):
            return False
        if operator == "gt" and not (actual is not None and actual > value):
            return False
        if operator == "ilike":
            pattern = str(value).replace("%", "").lower()
            if pattern not in str(actual or "").lower():
                return False
    return True


class InMemoryDataStore:
    """套用 RLS 政策矩陣的存取層。每個請求身分各持有一個實例。"""

    def __init__(self, db: InMemoryDatabase, context: RequestContext) -> None:
        self._db = db
        self._context = context

    @property
    def context(self) -> RequestContext:
        return self._context

    @property
    def db(self) -> InMemoryDatabase:
        return self._db

    # ────────────────────────── RLS 政策 ──────────────────────────

    def _assessment_dept(self, assessment_id: Any) -> str | None:
        row = self._db.find("assessments", id=assessment_id)
        return row.get("dept_id") if row else None

    def _can_read(self, table: str, row: dict[str, Any]) -> bool:
        ctx = self._context
        role = ctx.role

        # 應徵者與系統角色對底層資料表沒有任何權限（0009 REVOKE ALL ... FROM anon）
        if role not in (ROLE_HR, ROLE_MANAGER):
            return False

        if table == "departments":
            return True
        if table == "internal_users":
            if role == ROLE_HR:
                return True
            return row.get("auth_user_id") == ctx.auth_user_id
        if table == "question_banks":
            return role == ROLE_MANAGER and row.get("dept_id") == ctx.dept_id
        if table == "assessments":
            if role == ROLE_HR:
                return True
            return row.get("dept_id") == ctx.dept_id
        if table in ("execution_records", "ai_reports", "manager_decisions"):
            # HR 在 ai_reports 與 manager_decisions 上沒有任何政策（FR-007、FR-008）
            if role != ROLE_MANAGER:
                return False
            return self._assessment_dept(row.get("assessment_id")) == ctx.dept_id
        if table == "audit_logs":
            if role == ROLE_HR:
                return True
            return self._assessment_dept(row.get("assessment_id")) == ctx.dept_id
        return False

    def _can_write(self, table: str, row: dict[str, Any]) -> bool:
        ctx = self._context
        role = ctx.role
        if role not in (ROLE_HR, ROLE_MANAGER):
            return False
        if table == "question_banks":
            return role == ROLE_MANAGER and row.get("dept_id") == ctx.dept_id
        if table == "assessments":
            return role == ROLE_HR or row.get("dept_id") == ctx.dept_id
        if table == "manager_decisions":
            return (
                role == ROLE_MANAGER
                and self._assessment_dept(row.get("assessment_id")) == ctx.dept_id
            )
        if table == "audit_logs":
            return True
        if table in ("execution_records", "ai_reports"):
            return False
        return False

    # ────────────────────────── DataStore 介面 ──────────────────────────

    def select(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        projection: tuple[str, ...] | None = None
        if table == "hr_assessments":
            table, projection = "assessments", HR_ASSESSMENT_COLUMNS

        rows = [
            copy.deepcopy(row)
            for row in self._db.tables[table]
            if self._can_read(table, row) and _matches(row, filters)
        ]
        if order_by:
            rows.sort(key=lambda r: (r.get(order_by) is None, r.get(order_by)), reverse=descending)
        if limit is not None:
            rows = rows[:limit]
        if projection:
            rows = [{key: row.get(key) for key in projection} for row in rows]
        return rows

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        if not self._can_write(table, row):
            raise DataAccessError(f"RLS 政策拒絕對 {table} 的寫入")
        return self._db.insert_raw(table, row)

    def update(
        self, table: str, values: dict[str, Any], *, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if table in APPEND_ONLY_TABLES:
            raise DataAccessError(f"{table} 為唯附加資料表，不接受 UPDATE（FR-078）")

        updated: list[dict[str, Any]] = []
        for row in self._db.tables[table]:
            if not (self._can_read(table, row) and _matches(row, filters)):
                continue
            if not self._can_write(table, row):
                continue
            row.update(copy.deepcopy(values))
            updated.append(copy.deepcopy(row))
        return updated

    # ────────────────────── SECURITY DEFINER 函式 ──────────────────────
    # 以下鏡射 0010。函式以擁有者身分執行，因此不套用上方的政策檢查——
    # 這正是應徵者能在 anon 角色下存取單筆考核的機制（research.md R-002）。

    def rpc(self, function: str, params: dict[str, Any]) -> Any:
        handler = getattr(self, f"_fn_{function}", None)
        if handler is None:
            raise DataAccessError(f"未定義的資料庫函式：{function}")
        return handler(**params)

    def _expire_if_due(self, row: dict[str, Any]) -> dict[str, Any]:
        expires_at = row.get("token_expires_at")
        if expires_at and expires_at < _now() and row.get("status") in _LAZY_EXPIRABLE:
            previous = row["status"]
            row["status"] = "EXPIRED"
            self._db.insert_raw(
                "audit_logs",
                {
                    "assessment_id": row["id"],
                    "action": "STATUS_EXPIRED",
                    "from_status": previous,
                    "to_status": "EXPIRED",
                    "actor_role": ROLE_SYSTEM,
                    "detail": {"reason": "TOKEN_EXPIRED"},
                },
            )
        return row

    def _by_token(self, token: str) -> dict[str, Any] | None:
        return self._db.find("assessments", token=token)

    def _fn_get_assessment_by_token(
        self, p_token: str, p_max_trial_runs: int = 20
    ) -> dict[str, Any] | None:
        row = self._by_token(p_token)
        if row is None:
            return None
        row = self._expire_if_due(row)

        dept = self._db.find("departments", id=row["dept_id"]) or {}
        if row["status"] == "EXPIRED":
            return {
                "status": "EXPIRED",
                "job_title": row["job_title"],
                "dept_type": dept.get("type"),
                "token_expires_at": row["token_expires_at"],
                "question": None,
            }

        question = None
        snapshot = row.get("question_snapshot")
        if snapshot:
            question = {
                "title": snapshot.get("title"),
                "description": snapshot.get("description"),
                "constraints": snapshot.get("constraints"),
                "language": snapshot.get("language"),
                "sample_cases": [
                    {
                        "name": case.get("name"),
                        "stdin": case.get("stdin"),
                        "expected_stdout": case.get("expected_stdout"),
                    }
                    for case in snapshot.get("test_cases", [])
                    if not case.get("is_hidden", False)
                ],
            }

        return {
            "assessment_id": row["id"],
            "job_title": row["job_title"],
            "dept_type": dept.get("type"),
            "status": row["status"],
            "token_expires_at": row["token_expires_at"],
            "question": question,
            "code_language": row.get("code_language"),
            "trial_runs_remaining": max(p_max_trial_runs - row.get("trial_run_count", 0), 0),
            "submitted_at": row.get("submitted_at"),
            "chat_history": copy.deepcopy(row.get("ai_chat_history") or []),
        }

    def _fn_append_chat_message(
        self,
        p_token: str,
        p_role: str,
        p_content: str,
        p_guardrail: bool | None = None,
    ) -> dict[str, Any]:
        if p_role not in ("candidate", "assistant"):
            return {"ok": False, "reason": "INVALID_ROLE"}
        row = self._by_token(p_token)
        if row is None:
            return {"ok": False, "reason": "NOT_FOUND"}
        row = self._expire_if_due(row)
        if row["status"] == "EXPIRED":
            return {"ok": False, "reason": "EXPIRED"}

        message: dict[str, Any] = {
            "role": p_role,
            "content": p_content,
            "created_at": _now(),
        }
        if p_guardrail is not None:
            message["guardrail_triggered"] = p_guardrail
        row.setdefault("ai_chat_history", []).append(message)
        return {"ok": True, "message": copy.deepcopy(message)}

    def _fn_record_trial_run(
        self, p_token: str, p_execution: dict[str, Any], p_max_trial_runs: int = 20
    ) -> dict[str, Any]:
        row = self._by_token(p_token)
        if row is None:
            return {"ok": False, "reason": "NOT_FOUND"}
        row = self._expire_if_due(row)
        if row["status"] == "EXPIRED":
            return {"ok": False, "reason": "EXPIRED"}
        if row.get("submitted_at") is not None:
            return {"ok": False, "reason": "ALREADY_SUBMITTED"}
        if row.get("trial_run_count", 0) >= p_max_trial_runs:
            return {"ok": False, "reason": "LIMIT_REACHED", "trial_runs_remaining": 0}

        execution = p_execution or {}
        self._db.insert_raw(
            "execution_records",
            {
                "assessment_id": row["id"],
                "trigger": "TRIAL_RUN",
                "language": execution.get("language") or row.get("code_language") or "unknown",
                "stdout": execution.get("stdout"),
                "stderr": execution.get("stderr"),
                "exit_code": execution.get("exit_code"),
                "duration_ms": execution.get("duration_ms"),
                "peak_memory_kb": execution.get("peak_memory_kb"),
                "termination_reason": execution.get("termination_reason", "COMPLETED"),
                "test_results": None,
            },
        )
        row["trial_run_count"] = row.get("trial_run_count", 0) + 1
        self._db.insert_raw(
            "audit_logs",
            {
                "assessment_id": row["id"],
                "action": "TRIAL_RUN",
                "actor_role": ROLE_CANDIDATE,
                "detail": {
                    "termination_reason": execution.get("termination_reason", "COMPLETED"),
                    "duration_ms": execution.get("duration_ms"),
                    "attempt": row["trial_run_count"],
                },
            },
        )
        return {
            "ok": True,
            "trial_runs_remaining": max(p_max_trial_runs - row["trial_run_count"], 0),
        }

    def _fn_submit_answer(
        self, p_token: str, p_answer: str, p_language: str | None = None
    ) -> dict[str, Any]:
        row = self._by_token(p_token)
        if row is None:
            return {"ok": False, "reason": "NOT_FOUND"}
        row = self._expire_if_due(row)
        if row["status"] == "EXPIRED":
            return {"ok": False, "reason": "EXPIRED"}
        if row.get("submitted_at") is not None:
            return {"ok": False, "reason": "ALREADY_SUBMITTED"}
        if row["status"] != "PENDING_CANDIDATE":
            return {"ok": False, "reason": "INVALID_STATUS", "status": row["status"]}

        previous = row["status"]
        row["candidate_answer"] = p_answer
        row["code_language"] = p_language or row.get("code_language")
        row["status"] = "COMPLETED_AWAITING_REVIEW"
        row["submitted_at"] = _now()

        self._db.insert_raw(
            "audit_logs",
            {
                "assessment_id": row["id"],
                "action": "ANSWER_SUBMITTED",
                "from_status": previous,
                "to_status": "COMPLETED_AWAITING_REVIEW",
                "actor_role": ROLE_CANDIDATE,
                "detail": {
                    "language": row["code_language"],
                    "answer_length": len(p_answer or ""),
                },
            },
        )
        return {"ok": True, "submitted_at": row["submitted_at"]}

    def _fn_record_evaluation_start(self, p_token: str) -> dict[str, Any]:
        row = self._by_token(p_token)
        if row is None:
            return {"ok": False, "reason": "NOT_FOUND"}
        if row.get("submitted_at") is None:
            return {"ok": False, "reason": "NOT_SUBMITTED"}

        attempts = [
            report["attempt_no"]
            for report in self._db.tables["ai_reports"]
            if report["assessment_id"] == row["id"]
        ]
        attempt_no = (max(attempts) if attempts else 0) + 1

        self._db.insert_raw(
            "ai_reports",
            {"assessment_id": row["id"], "attempt_no": attempt_no, "status": "PENDING"},
        )
        self._db.insert_raw(
            "audit_logs",
            {
                "assessment_id": row["id"],
                "action": "EVALUATION_STARTED",
                "actor_role": ROLE_SYSTEM,
                "detail": {"attempt_no": attempt_no},
            },
        )
        return {
            "ok": True,
            "assessment_id": row["id"],
            "attempt_no": attempt_no,
            "question_snapshot": copy.deepcopy(row.get("question_snapshot")),
            "answer": row.get("candidate_answer"),
            "language": row.get("code_language"),
            "chat_history": copy.deepcopy(row.get("ai_chat_history") or []),
        }

    def _fn_record_evaluation_result(
        self,
        p_token: str,
        p_attempt_no: int,
        p_status: str,
        p_dimensions: dict[str, Any] | None = None,
        p_test_pass_ratio: float | None = None,
        p_model_id: str | None = None,
        p_error_message: str | None = None,
        p_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if p_status not in ("SUCCESS", "FAILED"):
            return {"ok": False, "reason": "INVALID_STATUS"}
        row = self._by_token(p_token)
        if row is None:
            return {"ok": False, "reason": "NOT_FOUND"}

        if p_execution is not None:
            self._db.insert_raw(
                "execution_records",
                {
                    "assessment_id": row["id"],
                    "trigger": "EVALUATION",
                    "language": p_execution.get("language")
                    or row.get("code_language")
                    or "unknown",
                    "stdout": p_execution.get("stdout"),
                    "stderr": p_execution.get("stderr"),
                    "exit_code": p_execution.get("exit_code"),
                    "duration_ms": p_execution.get("duration_ms"),
                    "peak_memory_kb": p_execution.get("peak_memory_kb"),
                    "termination_reason": p_execution.get("termination_reason", "COMPLETED"),
                    "test_results": copy.deepcopy(p_execution.get("test_results")),
                },
            )

        report = None
        for candidate in self._db.tables["ai_reports"]:
            if (
                candidate["assessment_id"] == row["id"]
                and candidate["attempt_no"] == p_attempt_no
                and candidate["status"] == "PENDING"
            ):
                report = candidate
                break
        if report is None:
            return {"ok": False, "reason": "NO_PENDING_REPORT"}

        report.update(
            {
                "status": p_status,
                "dimensions": copy.deepcopy(p_dimensions),
                "test_pass_ratio": p_test_pass_ratio,
                "model_id": p_model_id,
                "error_message": p_error_message,
            }
        )
        self._db.insert_raw(
            "audit_logs",
            {
                "assessment_id": row["id"],
                "action": (
                    "EVALUATION_COMPLETED" if p_status == "SUCCESS" else "EVALUATION_FAILED"
                ),
                "actor_role": ROLE_SYSTEM,
                "detail": {
                    "attempt_no": p_attempt_no,
                    "model_id": p_model_id,
                    "test_pass_ratio": p_test_pass_ratio,
                },
            },
        )
        return {"ok": True}
