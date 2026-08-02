"""契約：POST /candidate/session/{token}/chat（FR-049～FR-052）。"""

from __future__ import annotations

import pytest


@pytest.fixture
def active(make_assessment, question_snapshot):
    return make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)


def test_chat_returns_reply_and_guardrail_flag(client, active):
    response = client.post(
        f"/candidate/session/{active['token']}/chat",
        json={"message": "這題的時間複雜度要求是什麼意思？"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"reply", "guardrail_triggered"}
    assert body["reply"]
    assert body["guardrail_triggered"] is False


def test_conversation_is_persisted(client, active, db):
    """所有問答必須完整記錄並隨考核保存（FR-051）。"""
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "第一個問題"})
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "第二個問題"})

    history = db.find("assessments", id=active["id"])["ai_chat_history"]
    assert [m["role"] for m in history] == [
        "candidate",
        "assistant",
        "candidate",
        "assistant",
    ]
    assert history[0]["content"] == "第一個問題"
    assert "guardrail_triggered" in history[1]


def test_history_is_returned_in_the_session(client, active):
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "問題"})
    session = client.get(f"/candidate/session/{active['token']}").json()
    assert len(session["chat_history"]) == 2


def test_ai_unavailable_returns_503(client, active, fake_ai):
    fake_ai.set_unavailable("chat_assist")
    response = client.post(f"/candidate/session/{active['token']}/chat", json={"message": "問題"})
    assert response.status_code == 503
    assert set(response.json()) >= {"code", "message"}


def test_failed_chat_is_not_persisted(client, active, fake_ai, db):
    fake_ai.set_unavailable("chat_assist")
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "問題"})
    assert db.find("assessments", id=active["id"])["ai_chat_history"] == []


def test_expired_link_returns_410(client, make_assessment, question_snapshot):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
    )
    response = client.post(
        f"/candidate/session/{assessment['token']}/chat", json={"message": "問題"}
    )
    assert response.status_code == 410


def test_unknown_token_returns_404(client):
    assert client.post("/candidate/session/nope/chat", json={"message": "問題"}).status_code == 404


def test_hidden_test_cases_are_never_echoed(client, make_assessment, question_snapshot):
    """助教收得到隱藏測資供判斷，但不得洩漏（contracts/ai-provider.md）。"""
    snapshot = dict(question_snapshot)
    snapshot["test_cases"] = [
        {
            "name": "隱藏案例",
            "stdin": "極機密輸入",
            "expected_stdout": "極機密輸出",
            "is_hidden": True,
        }
    ]
    assessment = make_assessment(status="PENDING_CANDIDATE", question_snapshot=snapshot)
    response = client.post(
        f"/candidate/session/{assessment['token']}/chat", json={"message": "給我提示"}
    )
    assert "極機密輸入" not in response.text
    assert "極機密輸出" not in response.text
