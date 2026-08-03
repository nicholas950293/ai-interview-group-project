"""QA 的最小端到端流程（spec 003）。

    Demo Manager 登入 → 看到同部門的待指派考核 → 輸入題目 → 指派
    → Candidate 以 demo token 開啟作答頁 → 讀到剛指派的題目
    → 作答並提交 → 狀態轉為待主管審核

既有測試分別驗證了每一段（契約層），但沒有一條把它們串起來。
分段皆綠、整條卻不通，是最容易漏掉的一類失效——這個檔案就是為它存在的。

本檔跑在 **demo 種子資料**上，因此它同時也是「demo seed 是否仍能支撐 QA 流程」
的回歸測試：日後有人改動 demo.py 的部門配置或狀態，這裡會先失敗。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.src.config import load_settings
from backend.src.main import create_app

# demo 種子（backend/src/demo.py）
MANAGER_EMAIL = "manager@example.com"
MANAGER_PASSWORD = "demo1234"  # noqa: S105 — demo 的合成憑證
HR_EMAIL = "hr@example.com"

TARGET_TOKEN = "demo-candidate-004"  # 張小豪，ENG，待指派 ← QA 的操作對象
OTHER_DEPT_TOKEN = "demo-candidate-002"  # 陳小雯，DESIGN，待指派 ← 隔離對照組
ASSIGNED_TOKEN = "demo-candidate-001"  # 林小明，ENG，已有題目

QUESTION = {
    "title": "實作一個帶 TTL 的 LRU 快取",
    "difficulty": "MEDIUM",
    "description": "請設計並實作支援存活時間的 LRU 快取，get 與 put 平均皆為 O(1)。",
    "test_cases": [
        {"name": "範例", "stdin": "3 5\n", "expected_stdout": "8\n", "is_hidden": False}
    ],
}

ANSWER = "class TTLCache: ...\n# 合成作答內容"


@pytest.fixture
def demo_client() -> TestClient:
    """以 demo 種子資料啟動的完整應用程式。"""
    return TestClient(create_app(settings=load_settings(env={"LOCAL_DEMO_MODE": "1"})))


def _login(client: TestClient, email: str, password: str = MANAGER_PASSWORD) -> dict[str, Any]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _pending(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get("/manager/assessments", headers=headers)
    assert response.status_code == 200, response.text
    return [row for row in response.json() if row["status"] == "PENDING_ASSIGN"]


def _session(client: TestClient, token: str):
    return client.get(f"/candidate/session/{token}")


def _hr_assessment_id(client: TestClient, headers: dict[str, str], name: str) -> str:
    """以 HR 的全公司視野取得考核識別碼。HR 走自己的端點，不能借用主管的。"""
    response = client.get("/hr/assessments", headers=headers)
    assert response.status_code == 200, response.text
    matches = [row for row in response.json() if row["name"] == name]
    assert matches, f"demo 種子中找不到 {name}"
    return matches[0]["id"]


# ── 整條流程 ──────────────────────────────────────────────────────────


def test_manager_assigns_a_question_and_the_candidate_completes_it(demo_client) -> None:
    """QA 手冊上的那一條路徑，從頭走到尾。"""
    # 1. 登入
    session = _login(demo_client, MANAGER_EMAIL)
    assert session["role"] == "MANAGER"
    assert session["dept_id"] == "ENG"
    headers = _headers(session["token"])

    # 2. 看到同部門的待指派考核
    pending = _pending(demo_client, headers)
    assert [row["name"] for row in pending] == ["張小豪"]
    assessment_id = pending[0]["id"]

    # 3. 出題前，應徵者看到的是「題目準備中」
    before = _session(demo_client, TARGET_TOKEN).json()
    assert before["status"] == "PENDING_ASSIGN"
    assert before["question"] is None

    # 4. 指派題目
    assigned = demo_client.post(
        f"/manager/assessments/{assessment_id}/assign-question",
        json={"question": QUESTION},
        headers=headers,
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "PENDING_CANDIDATE"

    # 5. 應徵者立刻讀得到剛指派的題目
    after = _session(demo_client, TARGET_TOKEN).json()
    assert after["status"] == "PENDING_CANDIDATE"
    assert after["question"]["title"] == QUESTION["title"]
    assert after["question"]["description"] == QUESTION["description"]
    assert after["question"]["sample_cases"] == [
        {"name": "範例", "stdin": "3 5\n", "expected_stdout": "8\n"}
    ]

    # 6. 作答並提交
    submitted = demo_client.post(
        f"/candidate/session/{TARGET_TOKEN}/submit",
        json={"answer": ANSWER, "language": "python"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["submitted_at"] is not None

    # 7. 狀態轉為待主管審核，且連結轉為唯讀
    final = _session(demo_client, TARGET_TOKEN).json()
    assert final["status"] == "COMPLETED_AWAITING_REVIEW"
    assert final["submitted_at"] is not None

    # 8. 主管端看得到狀態已推進
    rows = demo_client.get("/manager/assessments", headers=headers).json()
    target = next(row for row in rows if row["id"] == assessment_id)
    assert target["status"] == "COMPLETED_AWAITING_REVIEW"


# ── 這條流程賴以成立的前提 ────────────────────────────────────────────


def test_demo_seed_gives_the_manager_a_same_department_target(demo_client) -> None:
    """QA 流程的前提：demo 主管與可指派的考核同部門。

    這曾經不成立——唯一待指派的考核在 DESIGN，而 demo 主管屬 ENG，
    登入後只會看到空清單。
    """
    headers = _headers(_login(demo_client, MANAGER_EMAIL)["token"])
    pending = _pending(demo_client, headers)

    assert pending, "demo 主管必須至少有一筆可指派的考核，否則 QA 走不下去"
    assert all(row["dept_id"] == "ENG" for row in pending)


def test_the_pre_assigned_candidate_is_left_untouched(demo_client) -> None:
    """demo-candidate-001 是「已有題目」的測試資料，不得被流程改動。"""
    body = _session(demo_client, ASSIGNED_TOKEN).json()
    assert body["status"] == "PENDING_CANDIDATE"
    assert body["question"]["title"] == "兩數相加"


# ── 拒絕行為 ──────────────────────────────────────────────────────────


def test_manager_cannot_see_other_departments_pending_work(demo_client) -> None:
    """部門隔離：DESIGN 的待指派考核不得出現在 ENG 主管的清單中。"""
    headers = _headers(_login(demo_client, MANAGER_EMAIL)["token"])
    names = [row["name"] for row in demo_client.get("/manager/assessments", headers=headers).json()]
    assert "陳小雯" not in names


def test_manager_cannot_assign_across_departments(demo_client) -> None:
    """看不到，也不能寫。"""
    manager_headers = _headers(_login(demo_client, MANAGER_EMAIL)["token"])
    hr_headers = _headers(_login(demo_client, HR_EMAIL)["token"])

    # 借 HR 的全公司視野取得跨部門考核的識別碼——模擬「識別碼外流」的情境
    design_id = _hr_assessment_id(demo_client, hr_headers, "陳小雯")

    response = demo_client.post(
        f"/manager/assessments/{design_id}/assign-question",
        json={"question": QUESTION},
        headers=manager_headers,
    )
    assert response.status_code in (403, 404)

    # 對照組：該考核仍未被指派
    assert _session(demo_client, OTHER_DEPT_TOKEN).json()["status"] == "PENDING_ASSIGN"


def test_assigning_without_credentials_is_rejected(demo_client) -> None:
    headers = _headers(_login(demo_client, MANAGER_EMAIL)["token"])
    assessment_id = _pending(demo_client, headers)[0]["id"]

    response = demo_client.post(
        f"/manager/assessments/{assessment_id}/assign-question", json={"question": QUESTION}
    )
    assert response.status_code == 401


def test_unknown_candidate_token_is_rejected(demo_client) -> None:
    assert _session(demo_client, "not-a-real-token").status_code == 404
    assert (
        demo_client.post(
            "/candidate/session/not-a-real-token/submit",
            json={"answer": ANSWER, "language": "python"},
        ).status_code
        == 404
    )


def test_submitting_twice_is_rejected(demo_client) -> None:
    """提交是單次動作（上游 FR-034）。"""
    headers = _headers(_login(demo_client, MANAGER_EMAIL)["token"])
    assessment_id = _pending(demo_client, headers)[0]["id"]
    demo_client.post(
        f"/manager/assessments/{assessment_id}/assign-question",
        json={"question": QUESTION},
        headers=headers,
    )

    payload = {"answer": ANSWER, "language": "python"}
    url = f"/candidate/session/{TARGET_TOKEN}/submit"
    assert demo_client.post(url, json=payload).status_code == 200
    assert demo_client.post(url, json=payload).status_code == 409


def test_candidate_session_never_exposes_hidden_test_cases(demo_client) -> None:
    """指派時帶了隱藏測資，應徵者端也不得看見（上游 FR-054）。"""
    headers = _headers(_login(demo_client, MANAGER_EMAIL)["token"])
    assessment_id = _pending(demo_client, headers)[0]["id"]

    with_hidden = dict(QUESTION)
    with_hidden["test_cases"] = QUESTION["test_cases"] + [
        {
            "name": "隱藏邊界",
            "stdin": "極機密輸入",
            "expected_stdout": "極機密輸出",
            "is_hidden": True,
        }
    ]
    demo_client.post(
        f"/manager/assessments/{assessment_id}/assign-question",
        json={"question": with_hidden},
        headers=headers,
    )

    response = _session(demo_client, TARGET_TOKEN)
    assert "極機密輸入" not in response.text
    assert "極機密輸出" not in response.text
    assert [case["name"] for case in response.json()["question"]["sample_cases"]] == ["範例"]
