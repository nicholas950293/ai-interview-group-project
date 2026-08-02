"""考核狀態機（FR-073～FR-075）。

合法轉換表來自 data-model.md。表以外的一切轉換必須被拒絕——包含「原地不動」
（同狀態轉換）與跳階（例如 PENDING_ASSIGN → DECIDED）。

`DECIDED` 為終態：決策為 SECOND_ROUND 時不自動建立新考核，狀態停留於
DECIDED（FR-065）；決策修訂只新增 manager_decisions 列，不改變狀態。
"""

from __future__ import annotations

from backend.src.audit.logger import AuditAction
from backend.src.models.assessment import AssessmentStatus

S = AssessmentStatus

# (來源, 目標) → 對應的稽核操作類型
TRANSITIONS: dict[tuple[AssessmentStatus, AssessmentStatus], AuditAction] = {
    (S.PENDING_ASSIGN, S.PENDING_CANDIDATE): AuditAction.QUESTION_ASSIGNED,
    (S.PENDING_CANDIDATE, S.COMPLETED_AWAITING_REVIEW): AuditAction.ANSWER_SUBMITTED,
    (S.COMPLETED_AWAITING_REVIEW, S.DECIDED): AuditAction.DECISION_RECORDED,
    (S.PENDING_ASSIGN, S.EXPIRED): AuditAction.STATUS_EXPIRED,
    (S.PENDING_CANDIDATE, S.EXPIRED): AuditAction.STATUS_EXPIRED,
    (S.EXPIRED, S.PENDING_CANDIDATE): AuditAction.TOKEN_REGENERATED,
}

TERMINAL_STATUSES = frozenset({S.DECIDED})


class InvalidTransitionError(ValueError):
    """狀態轉換不在合法轉換表中（FR-074）。"""


class UnknownStatusError(ValueError):
    """未定義的狀態值（FR-075）。"""


def parse_status(value: str) -> AssessmentStatus:
    """將外部輸入轉為狀態列舉；未定義的值一律拒絕（FR-075）。"""
    try:
        return AssessmentStatus(value)
    except ValueError as exc:
        raise UnknownStatusError(f"未定義的考核狀態：{value!r}") from exc


def can_transition(source: AssessmentStatus, target: AssessmentStatus) -> bool:
    return (source, target) in TRANSITIONS


def audit_action_for(source: AssessmentStatus, target: AssessmentStatus) -> AuditAction:
    assert_transition(source, target)
    return TRANSITIONS[(source, target)]


def assert_transition(source: AssessmentStatus, target: AssessmentStatus) -> None:
    if not can_transition(source, target):
        raise InvalidTransitionError(f"不允許的狀態轉換：{source} → {target}")
