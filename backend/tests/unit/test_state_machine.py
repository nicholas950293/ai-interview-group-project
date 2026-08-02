"""狀態機（FR-074、FR-075）。

FR-074 的要求是「其餘轉換必須被拒絕」，因此本測試枚舉**全部** 25 種
(來源, 目標) 組合，逐一斷言——只測合法路徑無法證明非法路徑被擋下。
"""

from __future__ import annotations

import itertools

import pytest

from backend.src.audit.logger import AuditAction
from backend.src.models.assessment import AssessmentStatus as S
from backend.src.services.state_machine import (
    TRANSITIONS,
    InvalidTransitionError,
    UnknownStatusError,
    assert_transition,
    audit_action_for,
    can_transition,
    parse_status,
)

LEGAL = {
    (S.PENDING_ASSIGN, S.PENDING_CANDIDATE),
    (S.PENDING_CANDIDATE, S.COMPLETED_AWAITING_REVIEW),
    (S.COMPLETED_AWAITING_REVIEW, S.DECIDED),
    (S.PENDING_ASSIGN, S.EXPIRED),
    (S.PENDING_CANDIDATE, S.EXPIRED),
    (S.EXPIRED, S.PENDING_CANDIDATE),
}

ALL_PAIRS = list(itertools.product(list(S), list(S)))
ILLEGAL = [pair for pair in ALL_PAIRS if pair not in LEGAL]


def test_transition_table_matches_data_model():
    assert set(TRANSITIONS) == LEGAL


@pytest.mark.parametrize(("source", "target"), sorted(LEGAL, key=str))
def test_legal_transitions_are_allowed(source, target):
    assert can_transition(source, target) is True
    assert_transition(source, target)
    assert isinstance(audit_action_for(source, target), AuditAction)


@pytest.mark.parametrize(("source", "target"), ILLEGAL, ids=lambda p: str(p))
def test_every_other_transition_is_rejected(source, target):
    assert can_transition(source, target) is False
    with pytest.raises(InvalidTransitionError):
        assert_transition(source, target)


def test_decided_is_terminal():
    """SECOND_ROUND 決策不建立新考核，狀態停留於 DECIDED（FR-065）。"""
    for target in S:
        assert can_transition(S.DECIDED, target) is False


def test_second_round_does_not_reopen_candidate_stage():
    assert can_transition(S.DECIDED, S.PENDING_CANDIDATE) is False


def test_unknown_status_value_is_rejected():
    """系統必須拒絕任何未定義的狀態值（FR-075）。"""
    with pytest.raises(UnknownStatusError):
        parse_status("待審核")
    with pytest.raises(UnknownStatusError):
        parse_status("")


def test_known_status_value_is_parsed():
    assert parse_status("PENDING_ASSIGN") is S.PENDING_ASSIGN
