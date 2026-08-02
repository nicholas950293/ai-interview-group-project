"""US2：工程類題目缺測資即拒絕指派（FR-022、FR-026、quickstart.md 情境 3）。"""

from __future__ import annotations

import pytest

BASE_QUESTION = {
    "title": "缺測資的題目",
    "difficulty": "MEDIUM",
    "language": "go",
    "description": "題目描述。",
}


def _assign(client, headers, assessment_id, question):
    return client.post(
        f"/manager/assessments/{assessment_id}/assign-question",
        json={"question": question},
        headers=headers,
    )


def test_engineering_question_without_test_cases_is_rejected(
    client, eng_manager_headers, make_assessment, db
):
    assessment = make_assessment(dept_id="ENG")
    response = _assign(
        client, eng_manager_headers, assessment["id"], {**BASE_QUESTION, "test_cases": []}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "MISSING_TEST_CASES"

    # 狀態不得改變
    assert db.find("assessments", id=assessment["id"])["status"] == "PENDING_ASSIGN"


def test_empty_test_case_content_is_rejected(client, eng_manager_headers, make_assessment):
    assessment = make_assessment(dept_id="ENG")
    response = _assign(
        client,
        eng_manager_headers,
        assessment["id"],
        {
            **BASE_QUESTION,
            "test_cases": [
                {"name": "空案例", "stdin": "  ", "expected_stdout": "", "is_hidden": False}
            ],
        },
    )
    assert response.status_code == 409


def test_question_with_test_cases_is_accepted(client, eng_manager_headers, make_assessment, db):
    assessment = make_assessment(dept_id="ENG")
    response = _assign(
        client,
        eng_manager_headers,
        assessment["id"],
        {
            **BASE_QUESTION,
            "test_cases": [
                {"name": "案例", "stdin": "1 2\n", "expected_stdout": "3\n", "is_hidden": False}
            ],
        },
    )
    assert response.status_code == 200
    assert db.find("assessments", id=assessment["id"])["status"] == "PENDING_CANDIDATE"


def test_non_engineering_department_may_assign_without_test_cases(
    client, sales_manager_headers, make_assessment, db
):
    """FR-022 只規範工程類題目；非工程類為文字作答，無測資可言。"""
    assessment = make_assessment(dept_id="SALES", manager_id="44444444-4444-4444-8444-444444444444")
    response = _assign(
        client,
        sales_manager_headers,
        assessment["id"],
        {
            "title": "客戶異議處理",
            "difficulty": "MEDIUM",
            "description": "請說明你的處理步驟。",
            "test_cases": [],
        },
    )
    assert response.status_code == 200
    assert db.find("assessments", id=assessment["id"])["status"] == "PENDING_CANDIDATE"


@pytest.mark.parametrize("timeout", [30, 999])
def test_case_timeout_is_capped_at_sandbox_limit(
    client, eng_manager_headers, make_assessment, db, timeout
):
    """單案例逾時不得超過沙箱上限（contracts/sandbox-runner.md）。"""
    assessment = make_assessment(dept_id="ENG")
    _assign(
        client,
        eng_manager_headers,
        assessment["id"],
        {
            **BASE_QUESTION,
            "test_cases": [
                {
                    "name": "案例",
                    "stdin": "1\n",
                    "expected_stdout": "1\n",
                    "is_hidden": False,
                    "timeout_seconds": timeout,
                }
            ],
        },
    )
    snapshot = db.find("assessments", id=assessment["id"])["question_snapshot"]
    assert snapshot["test_cases"][0]["timeout_seconds"] == 10
