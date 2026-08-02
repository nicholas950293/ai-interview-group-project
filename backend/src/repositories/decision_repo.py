"""主管決策資料存取（FR-061～FR-064）。

唯附加：本層**沒有** update 或 delete 方法。修訂以新增列呈現，
`revision_no` 遞增。資料庫層另以撤銷 UPDATE／DELETE 權限與觸發器強制
（0011_append_only.sql）——這裡少一個方法只是讓錯誤更早被發現。
"""

from __future__ import annotations

from typing import Any

from backend.src.repositories.base import DataStore

TABLE = "manager_decisions"


class DecisionRepository:
    def __init__(self, store: DataStore) -> None:
        self._store = store

    def list_for(self, assessment_id: str) -> list[dict[str, Any]]:
        return self._store.select(
            TABLE, filters={"assessment_id": assessment_id}, order_by="revision_no"
        )

    def next_revision_no(self, assessment_id: str) -> int:
        existing = self.list_for(assessment_id)
        return max((row["revision_no"] for row in existing), default=0) + 1

    def append(
        self,
        *,
        assessment_id: str,
        revision_no: int,
        decided_by: str | None,
        result: str,
        internal_comment: str | None,
    ) -> dict[str, Any]:
        return self._store.insert(
            TABLE,
            {
                "assessment_id": assessment_id,
                "revision_no": revision_no,
                "decided_by": decided_by,
                "result": result,
                "internal_comment": internal_comment,
            },
        )
