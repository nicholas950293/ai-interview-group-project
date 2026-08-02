"""US2 端到端：跨部門隔離（quickstart.md 情境 2、FR-003、SC-008）。

本測試斷言的是 API 行為；同一規則在資料存取層的斷言見
`test_rls_dept_isolation.py`。兩者都必要——憲章「權限關卡」要求驗證的是
資料存取層的拒絕行為，而 API 層的 404 是那個拒絕在對外介面上的呈現。
"""

from __future__ import annotations


def test_other_department_assessment_is_invisible(client, design_manager_headers, make_assessment):
    eng = make_assessment(dept_id="ENG")

    listed = client.get("/manager/assessments", headers=design_manager_headers).json()
    assert eng["id"] not in [row["id"] for row in listed]


def test_direct_access_to_other_department_returns_404(
    client, design_manager_headers, make_assessment
):
    eng = make_assessment(dept_id="ENG")
    assert (
        client.get(f"/manager/assessments/{eng['id']}", headers=design_manager_headers).status_code
        == 404
    )


def test_nonexistent_and_forbidden_are_indistinguishable(
    client, design_manager_headers, make_assessment
):
    """兩者刻意回傳相同的狀態碼與訊息，避免以「存在與否」洩漏他部門資料。"""
    eng = make_assessment(dept_id="ENG")
    forbidden = client.get(f"/manager/assessments/{eng['id']}", headers=design_manager_headers)
    missing = client.get(
        "/manager/assessments/00000000-0000-4000-8000-000000000000",
        headers=design_manager_headers,
    )
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json() == missing.json()


def test_cross_department_write_is_rejected(client, design_manager_headers, make_assessment, db):
    eng = make_assessment(dept_id="ENG")
    response = client.post(
        f"/manager/assessments/{eng['id']}/assign-question",
        json={
            "question": {
                "title": "越權指派",
                "difficulty": "EASY",
                "language": "python",
                "description": "不應成功",
                "test_cases": [
                    {"name": "c", "stdin": "1\n", "expected_stdout": "1\n", "is_hidden": False}
                ],
            }
        },
        headers=design_manager_headers,
    )
    assert response.status_code == 404
    assert db.find("assessments", id=eng["id"])["status"] == "PENDING_ASSIGN"


def test_manager_cannot_read_other_department_question_bank(client, design_manager_headers):
    titles = {
        q["title"] for q in client.get("/manager/questions", headers=design_manager_headers).json()
    }
    assert "兩數相加" not in titles
