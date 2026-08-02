"""題庫資料存取（FR-020、FR-023）。

部門隔離由 RLS 政策強制——`question_banks` 只對同部門主管開放。
本層不加任何 dept 條件，正是為了讓「他部門查詢回傳空集合」這件事
成為政策的結果而非程式碼的結果（憲章原則 IV）。
"""

from __future__ import annotations

from typing import Any

from backend.src.models.question import Question
from backend.src.repositories.base import DataStore

TABLE = "question_banks"


class QuestionRepository:
    def __init__(self, store: DataStore) -> None:
        self._store = store

    def list(self) -> list[dict[str, Any]]:
        return self._store.select(TABLE, order_by="created_at", descending=True)

    def get(self, question_id: str) -> dict[str, Any] | None:
        rows = self._store.select(TABLE, filters={"id": question_id}, limit=1)
        return rows[0] if rows else None

    def to_models(self, rows: list[dict[str, Any]]) -> list[Question]:
        return [Question.model_validate(row) for row in rows]
