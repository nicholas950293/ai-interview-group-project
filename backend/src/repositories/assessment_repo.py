"""考核資料存取。

所有查詢皆透過套用了 RLS 的 store——本層**不**做任何權限判斷。
「他部門看不到」這件事是政策的結果，不是這裡的 if 判斷的結果
（憲章原則 IV）。因此 `get` 找不到列時，「不存在」與「無權存取」
在這一層本來就無從區分，也正是 API 回傳 404 而非 403 的原因。
"""

from __future__ import annotations

from typing import Any

from backend.src.models.assessment import AssessmentStatus
from backend.src.repositories.base import DataStore

# 「進行中」的定義：尚未走到終態，也尚未逾期（FR-009 重複邀請判定）
ACTIVE_STATUSES = (
    AssessmentStatus.PENDING_ASSIGN,
    AssessmentStatus.PENDING_CANDIDATE,
    AssessmentStatus.COMPLETED_AWAITING_REVIEW,
)

# HR 讀取一律經限定欄位的 view，使受限欄位不會進入回應（FR-008）
HR_VIEW = "hr_assessments"
TABLE = "assessments"


class AssessmentRepository:
    def __init__(self, store: DataStore) -> None:
        self._store = store

    @property
    def store(self) -> DataStore:
        return self._store

    def create(self, row: dict[str, Any]) -> dict[str, Any]:
        return self._store.insert(TABLE, row)

    def get(self, assessment_id: str) -> dict[str, Any] | None:
        rows = self._store.select(TABLE, filters={"id": assessment_id}, limit=1)
        return rows[0] if rows else None

    def get_for_hr(self, assessment_id: str) -> dict[str, Any] | None:
        rows = self._store.select(HR_VIEW, filters={"id": assessment_id}, limit=1)
        return rows[0] if rows else None

    def list(
        self,
        *,
        view: str = TABLE,
        dept_id: str | None = None,
        status: AssessmentStatus | None = None,
        job_title: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if dept_id:
            filters["dept_id"] = dept_id
        if status:
            filters["status"] = str(status)
        if job_title:
            filters["job_title"] = ("ilike", f"%{job_title}%")
        return self._store.select(view, filters=filters, order_by="created_at", descending=True)

    def find_active_duplicates(self, *, email: str, job_title: str) -> list[dict[str, Any]]:
        return self._store.select(
            TABLE,
            filters={
                "email": email,
                "job_title": job_title,
                "status": ("in", [str(status) for status in ACTIVE_STATUSES]),
            },
        )

    def update(self, assessment_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        rows = self._store.update(TABLE, values, filters={"id": assessment_id})
        return rows[0] if rows else None

    # ── 關聯資料 ──────────────────────────────────────────────────────

    def department(self, dept_id: str) -> dict[str, Any] | None:
        rows = self._store.select("departments", filters={"id": dept_id}, limit=1)
        return rows[0] if rows else None

    def active_manager_of(self, dept_id: str) -> dict[str, Any] | None:
        """該部門唯一的 active 主管（「一人一主管」假設，由部分唯一索引保證）。"""
        rows = self._store.select(
            "internal_users",
            filters={"dept_id": dept_id, "role": "MANAGER", "is_active": True},
            limit=1,
        )
        return rows[0] if rows else None

    def internal_user(self, user_id: str | None) -> dict[str, Any] | None:
        if not user_id:
            return None
        rows = self._store.select("internal_users", filters={"id": user_id}, limit=1)
        return rows[0] if rows else None

    def manager_names(self) -> dict[str, str]:
        """主管識別碼 → 姓名。用於總覽頁顯示責任主管（FR-013）。"""
        return {
            row["id"]: row.get("name", "")
            for row in self._store.select("internal_users", filters={"role": "MANAGER"})
        }

    def executions(self, assessment_id: str) -> list[dict[str, Any]]:
        return self._store.select(
            "execution_records", filters={"assessment_id": assessment_id}, order_by="created_at"
        )

    def latest_report(self, assessment_id: str) -> dict[str, Any] | None:
        rows = self._store.select(
            "ai_reports",
            filters={"assessment_id": assessment_id},
            order_by="attempt_no",
            descending=True,
            limit=1,
        )
        return rows[0] if rows else None

    def has_report(self, assessment_id: str) -> bool:
        return bool(
            self._store.select(
                "ai_reports", filters={"assessment_id": assessment_id, "status": "SUCCESS"}, limit=1
            )
        )
