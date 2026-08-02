"""SECURITY DEFINER 函式（FR-018、FR-032、FR-034、FR-051）。

四個函式皆須在內部重新驗證 token 與效期，不得信任呼叫端已驗證
（data-model.md「需要的 SECURITY DEFINER 函式」）。因此測試一律以 anon
角色呼叫——anon 對底層資料表沒有任何權限，函式是它唯一的入口。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.postgres

QUESTION_SNAPSHOT = {
    "source": "BANK",
    "title": "兩數相加",
    "description": "讀取兩個整數並輸出其和。",
    "constraints": "整數範圍 -10^9 至 10^9。",
    "language": "python",
    "test_cases": [
        {
            "name": "公開案例",
            "stdin": "3 5\n",
            "expected_stdout": "8\n",
            "is_hidden": False,
        },
        {
            "name": "隱藏案例",
            "stdin": "秘密輸入\n",
            "expected_stdout": "秘密輸出\n",
            "is_hidden": True,
        },
    ],
}


@pytest.fixture
def anon_conn(psycopg, migrated_schema):
    with psycopg.connect(migrated_schema, autocommit=True) as conn:
        conn.execute("SET ROLE anon")
        yield conn


@pytest.fixture
def active_token(owner_conn) -> str:
    token = "active-token-0000000000000000000000000000001"
    owner_conn.execute(
        """
        INSERT INTO assessments (name, email, job_title, dept_id, assigned_manager_id,
                                 status, token, token_expires_at, question_snapshot)
        VALUES ('合成應徵者', 'token.fn@example.com', '後端工程師', 'ENG',
                '22222222-2222-4222-8222-222222222222',
                'PENDING_CANDIDATE', %s, NOW() + INTERVAL '7 days', %s::jsonb)
        """,
        (token, json.dumps(QUESTION_SNAPSHOT)),
    )
    return token


@pytest.fixture
def expired_token(owner_conn) -> str:
    token = "expired-token-000000000000000000000000000002"
    owner_conn.execute(
        """
        INSERT INTO assessments (name, email, job_title, dept_id, assigned_manager_id,
                                 status, token, token_expires_at, question_snapshot)
        VALUES ('合成應徵者', 'token.exp@example.com', '後端工程師', 'ENG',
                '22222222-2222-4222-8222-222222222222',
                'PENDING_CANDIDATE', %s, NOW() - INTERVAL '1 day', %s::jsonb)
        """,
        (token, json.dumps(QUESTION_SNAPSHOT)),
    )
    return token


def _call(conn, sql, params):
    return conn.execute(sql, params).fetchone()[0]


def test_forged_token_returns_null(anon_conn):
    result = _call(anon_conn, "SELECT get_assessment_by_token(%s)", ("token-does-not-exist",))
    assert result is None, "偽造 token 必須不回傳任何考核資料"


def test_expired_token_is_rejected_and_hides_question(anon_conn, owner_conn, expired_token):
    result = _call(anon_conn, "SELECT get_assessment_by_token(%s)", (expired_token,))
    assert result["status"] == "EXPIRED"
    assert result["question"] is None, "逾期者必須拒絕提供題目內容（FR-018）"

    (status,) = owner_conn.execute(
        "SELECT status FROM assessments WHERE token = %s", (expired_token,)
    ).fetchone()
    assert status == "EXPIRED", "逾期於存取時惰性判定並持久化"

    actions = [
        row[0]
        for row in owner_conn.execute(
            """
            SELECT action FROM audit_logs
            WHERE assessment_id = (SELECT id FROM assessments WHERE token = %s)
            """,
            (expired_token,),
        ).fetchall()
    ]
    assert "STATUS_EXPIRED" in actions


def test_hidden_test_cases_are_never_returned(anon_conn, active_token):
    result = _call(anon_conn, "SELECT get_assessment_by_token(%s)", (active_token,))
    payload = json.dumps(result, ensure_ascii=False)

    assert "秘密輸入" not in payload
    assert "秘密輸出" not in payload
    assert [case["name"] for case in result["question"]["sample_cases"]] == ["公開案例"]


def test_expired_token_rejected_by_every_function(anon_conn, expired_token):
    """四個函式各自重新驗證效期，不得信任呼叫端。"""
    assert (
        _call(anon_conn, "SELECT append_chat_message(%s, 'candidate', '提問')", (expired_token,))[
            "reason"
        ]
        == "EXPIRED"
    )
    assert (
        _call(anon_conn, "SELECT record_trial_run(%s, '{}'::jsonb)", (expired_token,))["reason"]
        == "EXPIRED"
    )
    assert (
        _call(anon_conn, "SELECT submit_answer(%s, '作答', 'python')", (expired_token,))["reason"]
        == "EXPIRED"
    )


def test_trial_run_limit_blocks_run_but_not_submit(anon_conn, active_token):
    """達上限後停止試跑，但不阻擋提交（FR-032）。"""
    execution = json.dumps({"termination_reason": "COMPLETED", "duration_ms": 12})
    for _ in range(2):
        result = _call(
            anon_conn, "SELECT record_trial_run(%s, %s::jsonb, 2)", (active_token, execution)
        )
        assert result["ok"] is True

    blocked = _call(
        anon_conn, "SELECT record_trial_run(%s, %s::jsonb, 2)", (active_token, execution)
    )
    assert blocked["ok"] is False
    assert blocked["reason"] == "LIMIT_REACHED"

    submitted = _call(anon_conn, "SELECT submit_answer(%s, '作答內容', 'python')", (active_token,))
    assert submitted["ok"] is True


def test_submit_is_single_shot(anon_conn, active_token):
    first = _call(anon_conn, "SELECT submit_answer(%s, '第一次作答', 'python')", (active_token,))
    assert first["ok"] is True

    second = _call(anon_conn, "SELECT submit_answer(%s, '第二次作答', 'python')", (active_token,))
    assert second["ok"] is False
    assert second["reason"] == "ALREADY_SUBMITTED"


def test_submit_answer_is_not_modifiable_afterwards(anon_conn, owner_conn, active_token):
    _call(anon_conn, "SELECT submit_answer(%s, '定稿作答', 'python')", (active_token,))
    _call(anon_conn, "SELECT submit_answer(%s, '竄改作答', 'python')", (active_token,))
    (answer,) = owner_conn.execute(
        "SELECT candidate_answer FROM assessments WHERE token = %s", (active_token,)
    ).fetchone()
    assert answer == "定稿作答", "提交後作答內容不可變更（FR-034）"


def test_chat_message_is_appended_with_guardrail_flag(anon_conn, owner_conn, active_token):
    _call(anon_conn, "SELECT append_chat_message(%s, 'candidate', '這題怎麼想？')", (active_token,))
    _call(
        anon_conn,
        "SELECT append_chat_message(%s, 'assistant', '先想想邊界條件。', true)",
        (active_token,),
    )

    (history,) = owner_conn.execute(
        "SELECT ai_chat_history FROM assessments WHERE token = %s", (active_token,)
    ).fetchone()
    assert [m["role"] for m in history] == ["candidate", "assistant"]
    assert history[1]["guardrail_triggered"] is True


def test_anon_cannot_call_internal_helper(psycopg, anon_conn):
    """expire_if_due 是內部 helper，不得對 anon 開放。"""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        anon_conn.execute(
            "SELECT expire_if_due('00000000-0000-4000-8000-000000000000'::uuid)"
        ).fetchone()
