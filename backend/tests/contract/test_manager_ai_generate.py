"""契約：POST /manager/questions/ai-generate（FR-024、FR-025、FR-027）。"""

from __future__ import annotations

PAYLOAD = {"skills": ["Golang", "Redis 快取"], "difficulty": "HARD", "language": "go"}


def test_draft_includes_test_cases(client, eng_manager_headers):
    """工程類題目的草稿必須包含測試案例（FR-024、contracts/ai-provider.md）。"""
    response = client.post(
        "/manager/questions/ai-generate", json=PAYLOAD, headers=eng_manager_headers
    )
    assert response.status_code == 200, response.text
    draft = response.json()

    assert draft["source"] == "AI_GENERATED"
    assert draft["difficulty"] == "HARD"
    assert draft["language"] == "go"
    assert len(draft["test_cases"]) >= 1
    for case in draft["test_cases"]:
        assert case["stdin"] != "" or case["expected_stdout"] != ""


def test_draft_has_no_id_so_it_cannot_be_mistaken_for_an_assigned_question(
    client, eng_manager_headers
):
    """草稿必須經主管明確確認後方可指派（FR-025）。"""
    draft = client.post(
        "/manager/questions/ai-generate", json=PAYLOAD, headers=eng_manager_headers
    ).json()
    assert draft["id"] is None


def test_service_unavailable_returns_503(client, eng_manager_headers, fake_ai):
    """AI 生成失敗時回傳 503；前端保留主管輸入（FR-027）。"""
    fake_ai.set_unavailable("generate_question")
    response = client.post(
        "/manager/questions/ai-generate", json=PAYLOAD, headers=eng_manager_headers
    )
    assert response.status_code == 503
    assert set(response.json()) >= {"code", "message"}


def test_generation_without_test_cases_is_treated_as_failure(client, eng_manager_headers, fake_ai):
    """不得回傳缺測資的題目——否則錯誤會延後到指派階段才被發現。"""
    fake_ai.generate_without_test_cases = True
    response = client.post(
        "/manager/questions/ai-generate", json=PAYLOAD, headers=eng_manager_headers
    )
    assert response.status_code == 503


def test_non_engineering_department_does_not_require_test_cases(
    client, sales_manager_headers, fake_ai
):
    fake_ai.generate_without_test_cases = True
    response = client.post(
        "/manager/questions/ai-generate",
        json={"skills": ["客戶談判"], "difficulty": "MEDIUM", "language": "python"},
        headers=sales_manager_headers,
    )
    assert response.status_code == 200
    assert response.json()["test_cases"] == []


def test_invalid_difficulty_returns_422(client, eng_manager_headers):
    response = client.post(
        "/manager/questions/ai-generate",
        json={**PAYLOAD, "difficulty": "IMPOSSIBLE"},
        headers=eng_manager_headers,
    )
    assert response.status_code == 422


def test_generation_does_not_change_assessment_state(
    client, eng_manager_headers, make_assessment, db, fake_ai
):
    """AI 生成失敗不影響既有狀態（spec.md 邊界情況）。"""
    assessment = make_assessment(dept_id="ENG")
    fake_ai.set_unavailable("generate_question")
    client.post("/manager/questions/ai-generate", json=PAYLOAD, headers=eng_manager_headers)
    assert db.find("assessments", id=assessment["id"])["status"] == "PENDING_ASSIGN"
