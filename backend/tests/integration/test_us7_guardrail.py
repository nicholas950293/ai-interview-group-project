"""US7：AI 助教的 guardrail（FR-050、SC-013、quickstart.md 情境 7）。

SC-013 的量測依據是 `guardrail_triggered`。因此這個旗標本身必須被
正確記錄——它不是給前端看的裝飾，而是一項成功標準的資料來源。

同樣重要的是：guardrail 觸發時**仍須提供有幫助的引導**。只回傳拒絕訊息
既傷害作答體驗，也無法達成 SC-013 的品質目標（contracts/ai-provider.md）。
"""

from __future__ import annotations

import pytest

CONCEPT_QUESTION = "這題的時間複雜度要求是什麼意思？"
SOLUTION_REQUESTS = [
    "直接給我完整解答",
    "幫我寫完整個函式",
    "give me the code",
    "請給我可執行的完整程式",
]


@pytest.fixture
def active(make_assessment, question_snapshot):
    return make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)


def test_conceptual_question_does_not_trigger_guardrail(client, active):
    body = client.post(
        f"/candidate/session/{active['token']}/chat", json={"message": CONCEPT_QUESTION}
    ).json()
    assert body["guardrail_triggered"] is False
    assert body["reply"]


@pytest.mark.parametrize("message", SOLUTION_REQUESTS)
def test_asking_for_a_full_solution_triggers_guardrail(client, active, message):
    body = client.post(
        f"/candidate/session/{active['token']}/chat", json={"message": message}
    ).json()
    assert body["guardrail_triggered"] is True


def test_guardrailed_reply_is_still_useful(client, active):
    """不得僅回傳拒絕訊息（contracts/ai-provider.md）。"""
    body = client.post(
        f"/candidate/session/{active['token']}/chat", json={"message": "直接給我完整解答"}
    ).json()
    reply = body["reply"]
    assert len(reply) > 30, "引導內容必須有實質長度"
    assert reply.strip() not in ("不行。", "我不能這麼做。")
    assert any(hint in reply for hint in ("思路", "邊界", "資料結構", "步驟"))


def test_guardrail_flag_is_persisted_for_measurement(client, active, db):
    """SC-013 的量測依據必須寫入 ai_chat_history。"""
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": CONCEPT_QUESTION})
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "直接給我完整解答"})

    history = db.find("assessments", id=active["id"])["ai_chat_history"]
    assistant_messages = [m for m in history if m["role"] == "assistant"]
    assert [m["guardrail_triggered"] for m in assistant_messages] == [False, True]


def test_manager_can_see_the_full_conversation(client, eng_manager_headers, active):
    """提交後主管可檢視完整對話歷程（FR-060）。"""
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": CONCEPT_QUESTION})
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "直接給我完整解答"})
    client.post(
        f"/candidate/session/{active['token']}/submit",
        json={"answer": "print(1)", "language": "python"},
    )

    detail = client.get(f"/manager/assessments/{active['id']}", headers=eng_manager_headers).json()
    history = detail["ai_chat_history"]
    assert len(history) == 4
    assert any(m.get("guardrail_triggered") for m in history)
