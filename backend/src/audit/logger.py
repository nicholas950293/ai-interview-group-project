"""唯附加稽核寫入（FR-076～FR-080；憲章原則 V）。

每一次狀態轉換與關鍵操作都經由此處記錄。`detail` 在寫入前一律過濾——
應徵者姓名、Email、電話與作答內容不得進入稽核紀錄（FR-079、FR-080）。

過濾採白名單以外的**鍵名封鎖 + 值形態偵測**雙重機制：只擋鍵名會漏掉
`{"note": "請聯絡 someone@example.com"}` 這種把個資塞進自由文字的情形。
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from backend.src.repositories.base import DataStore, RequestContext

REDACTED = "[已遮蔽]"

# 鍵名一旦命中即整個值遮蔽，不論其型別
BLOCKED_KEY_FRAGMENTS = (
    "name",
    "email",
    "phone",
    "mobile",
    "tel",
    "answer",
    "code",
    "content",
    "message",
    "stdout",
    "stderr",
    "comment",
    "token",
    "password",
    "secret",
)

# 鍵名雖含被封鎖片語，但語意上不含個資的例外
ALLOWED_KEYS = frozenset(
    {
        "action_name",
        "case_name",
        "termination_reason",
        "model_id",
        "language",
        "dept_id",
        "attempt",
        "attempt_no",
        "revision_no",
        "answer_length",
        "duration_ms",
        "test_pass_ratio",
        "from_status",
        "to_status",
        "reason",
        "status",
        "result",
        "email_status",
    }
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# 涵蓋 09xx-xxx-xxx、+886…、(02)2345-6789 等常見形式
_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{7,}\d)")

MAX_DETAIL_TEXT = 200


class AuditAction(StrEnum):
    ASSESSMENT_CREATED = "ASSESSMENT_CREATED"
    MANAGER_REASSIGNED = "MANAGER_REASSIGNED"
    TOKEN_REGENERATED = "TOKEN_REGENERATED"  # noqa: S105 - 操作類型，非憑證
    QUESTION_ASSIGNED = "QUESTION_ASSIGNED"
    TRIAL_RUN = "TRIAL_RUN"
    ANSWER_SUBMITTED = "ANSWER_SUBMITTED"
    EVALUATION_STARTED = "EVALUATION_STARTED"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
    EVALUATION_FAILED = "EVALUATION_FAILED"
    DECISION_RECORDED = "DECISION_RECORDED"
    DECISION_REVISED = "DECISION_REVISED"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED"
    STATUS_EXPIRED = "STATUS_EXPIRED"
    PII_ERASED = "PII_ERASED"


def scrub_text(value: str) -> str:
    """自自由文字中移除 Email 與電話形態的內容。"""
    value = _EMAIL_RE.sub(REDACTED, value)
    value = _PHONE_RE.sub(REDACTED, value)
    if len(value) > MAX_DETAIL_TEXT:
        value = value[:MAX_DETAIL_TEXT] + "…"
    return value


def _is_blocked(key: str) -> bool:
    if key in ALLOWED_KEYS:
        return False
    lowered = key.lower()
    return any(fragment in lowered for fragment in BLOCKED_KEY_FRAGMENTS)


def sanitize_detail(detail: Any) -> Any:
    """遞迴過濾個資與作答內容（FR-079、FR-080）。"""
    if isinstance(detail, dict):
        return {
            key: REDACTED if _is_blocked(str(key)) else sanitize_detail(value)
            for key, value in detail.items()
        }
    if isinstance(detail, list | tuple):
        return [sanitize_detail(item) for item in detail]
    if isinstance(detail, str):
        return scrub_text(detail)
    return detail


class AuditLogger:
    """稽核寫入。

    唯附加由資料庫強制（0011_append_only.sql）；本類別只負責「一定要寫」
    與「不得寫入個資」兩件事。
    """

    def __init__(self, store: DataStore) -> None:
        self._store = store

    def record(
        self,
        *,
        assessment_id: str,
        action: AuditAction,
        context: RequestContext,
        from_status: str | None = None,
        to_status: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "assessment_id": assessment_id,
            "action": str(action),
            "from_status": from_status,
            "to_status": to_status,
            "actor_id": context.internal_user_id,
            "actor_role": context.role,
            "detail": sanitize_detail(detail) if detail else None,
        }
        return self._store.insert("audit_logs", row)
