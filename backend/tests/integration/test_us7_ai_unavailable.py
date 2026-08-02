"""US7：AI 助教不可用時核心流程不受影響（FR-052、quickstart.md 情境 10）。

助教是體驗加強功能。它掛掉時，應徵者仍必須能完成整場考核——
否則一個 P3 功能就成了整條流程的單點故障。
"""

from __future__ import annotations

import pytest

ANSWER = "print(sum(map(int, input().split())))"


@pytest.fixture
def active(make_assessment, question_snapshot, fake_ai):
    fake_ai.set_unavailable("chat_assist")
    return make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)


def test_session_still_loads(client, active):
    response = client.get(f"/candidate/session/{active['token']}")
    assert response.status_code == 200
    assert response.json()["question"]["title"] == "兩數相加"


def test_trial_run_still_works(client, active):
    response = client.post(
        f"/candidate/session/{active['token']}/run",
        json={"code": ANSWER, "language": "python", "stdin": "3 5\n"},
    )
    assert response.status_code == 200


def test_submission_still_works(client, active, db):
    response = client.post(
        f"/candidate/session/{active['token']}/submit",
        json={"answer": ANSWER, "language": "python"},
    )
    assert response.status_code == 200
    assert db.find("assessments", id=active["id"])["status"] == "COMPLETED_AWAITING_REVIEW"


def test_evaluation_still_runs_when_only_the_assistant_is_down(client, active, db):
    """助教與評測共用介面但不共用命運——只有 chat_assist 被設為不可用。"""
    client.post(
        f"/candidate/session/{active['token']}/submit",
        json={"answer": ANSWER, "language": "python"},
    )
    report = next(r for r in db.tables["ai_reports"] if r["assessment_id"] == active["id"])
    assert report["status"] == "SUCCESS"


def test_only_the_chat_endpoint_reports_503(client, active):
    assert (
        client.post(
            f"/candidate/session/{active['token']}/chat", json={"message": "問題"}
        ).status_code
        == 503
    )
    assert client.get(f"/candidate/session/{active['token']}").status_code == 200


def test_full_flow_completes_without_the_assistant(client, eng_manager_headers, active, db):
    client.post(f"/candidate/session/{active['token']}/chat", json={"message": "問題"})
    client.post(
        f"/candidate/session/{active['token']}/run",
        json={"code": ANSWER, "language": "python", "stdin": "3 5\n"},
    )
    client.post(
        f"/candidate/session/{active['token']}/submit",
        json={"answer": ANSWER, "language": "python"},
    )
    decision = client.post(
        f"/manager/assessments/{active['id']}/decision",
        json={"result": "PASS"},
        headers=eng_manager_headers,
    )
    assert decision.status_code == 200
    assert db.find("assessments", id=active["id"])["status"] == "DECIDED"
