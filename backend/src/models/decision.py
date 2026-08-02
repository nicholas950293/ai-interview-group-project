"""主管決策（FR-061～FR-066）。

唯附加：修訂以新增紀錄呈現，原紀錄不得覆寫或刪除（data-model.md §7）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DecisionResult(StrEnum):
    PASS = "PASS"  # noqa: S105 - 決策結果，非憑證
    SECOND_ROUND = "SECOND_ROUND"
    FAIL = "FAIL"


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: DecisionResult
    # HR 不可讀（FR-007、FR-066）
    internal_comment: str | None = None


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_no: int = Field(ge=1)
    result: DecisionResult
    internal_comment: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
