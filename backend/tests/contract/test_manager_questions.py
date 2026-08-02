"""契約：GET /manager/assessments 與 GET /manager/questions（FR-003、FR-020、FR-023）。"""

from __future__ import annotations


def test_assessment_list_is_scoped_to_own_department(
    client, eng_manager_headers, design_manager_headers, make_assessment
):
    eng = make_assessment(dept_id="ENG")
    make_assessment(dept_id="DESIGN", manager_id="33333333-3333-4333-8333-333333333333")

    rows = client.get("/manager/assessments", headers=eng_manager_headers).json()
    assert [row["id"] for row in rows] == [eng["id"]]

    other = client.get("/manager/assessments", headers=design_manager_headers).json()
    assert eng["id"] not in [row["id"] for row in other]


def test_assessment_summary_includes_has_report_flag(
    client, eng_manager_headers, make_assessment, db
):
    plain = make_assessment(dept_id="ENG")
    with_report = make_assessment(dept_id="ENG", status="COMPLETED_AWAITING_REVIEW", submitted=True)
    db.insert_raw(
        "ai_reports",
        {
            "assessment_id": with_report["id"],
            "attempt_no": 1,
            "status": "SUCCESS",
            "dimensions": {},
        },
    )

    rows = client.get("/manager/assessments", headers=eng_manager_headers).json()
    flags = {row["id"]: row["has_report"] for row in rows}
    assert flags[with_report["id"]] is True
    assert flags[plain["id"]] is False


def test_question_bank_is_scoped_to_own_department(
    client, eng_manager_headers, design_manager_headers
):
    eng_questions = client.get("/manager/questions", headers=eng_manager_headers).json()
    assert {q["title"] for q in eng_questions} == {"兩數相加"}

    design_questions = client.get("/manager/questions", headers=design_manager_headers).json()
    assert {q["title"] for q in design_questions} == {"元件狀態管理"}


def test_question_shape_matches_contract(client, eng_manager_headers):
    question = client.get("/manager/questions", headers=eng_manager_headers).json()[0]
    assert set(question) >= {"id", "title", "difficulty", "language", "description", "test_cases"}
    assert question["difficulty"] in {"EASY", "MEDIUM", "HARD"}
    case = question["test_cases"][0]
    assert set(case) == {"name", "stdin", "expected_stdout", "is_hidden", "timeout_seconds"}


def test_hr_role_is_forbidden_on_manager_endpoints(client, hr_headers):
    assert client.get("/manager/assessments", headers=hr_headers).status_code == 403
    assert client.get("/manager/questions", headers=hr_headers).status_code == 403


def test_requires_authentication(client):
    assert client.get("/manager/assessments").status_code == 401
