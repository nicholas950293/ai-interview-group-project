"""契約：GET /hr/assessments（contracts/openapi.yaml）。

對應 FR-013、FR-014。最關鍵的斷言是 **回應不含受限欄位**——
FR-008 要求 HR 的查詢結果本身即不包含 AI 報告、內部評語與作答內容。
"""

from __future__ import annotations

RESTRICTED_KEYS = {
    "candidate_answer",
    "ai_chat_history",
    "internal_comment",
    "ai_report",
    "dimensions",
    "question_snapshot",
}

ALLOWED_KEYS = {
    "id",
    "name",
    "email",
    "job_title",
    "dept_id",
    "assigned_manager",
    "status",
    "final_decision",
    "email_status",
    "token_expires_at",
    "created_at",
}


def test_list_returns_company_wide_overview(client, hr_headers, make_assessment):
    make_assessment(dept_id="ENG")
    make_assessment(dept_id="DESIGN", manager_id="33333333-3333-4333-8333-333333333333")
    make_assessment(dept_id="SALES", manager_id="44444444-4444-4444-8444-444444444444")

    response = client.get("/hr/assessments", headers=hr_headers)
    assert response.status_code == 200
    rows = response.json()
    assert {row["dept_id"] for row in rows} == {"ENG", "DESIGN", "SALES"}


def test_response_contains_no_restricted_fields(
    client, hr_headers, make_assessment, question_snapshot, db
):
    assessment = make_assessment(
        status="COMPLETED_AWAITING_REVIEW",
        question_snapshot=question_snapshot,
        candidate_answer="print(sum(map(int, input().split())))",
        code_language="python",
        submitted=True,
        final_decision="PASS",
    )
    db.insert_raw(
        "manager_decisions",
        {
            "assessment_id": assessment["id"],
            "revision_no": 1,
            "decided_by": "22222222-2222-4222-8222-222222222222",
            "result": "PASS",
            "internal_comment": "內部評語：溝通能力佳",
        },
    )
    db.insert_raw(
        "ai_reports",
        {
            "assessment_id": assessment["id"],
            "attempt_no": 1,
            "status": "SUCCESS",
            "dimensions": {"correctness": {"score": 80, "comment": "AI 報告內容"}},
        },
    )

    response = client.get("/hr/assessments", headers=hr_headers)
    rows = response.json()
    assert rows

    for row in rows:
        assert set(row) <= ALLOWED_KEYS, f"回應出現未預期的欄位：{set(row) - ALLOWED_KEYS}"
        assert not (set(row) & RESTRICTED_KEYS)

    # 受限內容的實際文字也不得以任何形式出現
    assert "內部評語" not in response.text
    assert "AI 報告內容" not in response.text
    assert "print(sum" not in response.text


def test_final_decision_is_visible_to_hr(client, hr_headers, make_assessment):
    """FR-007：HR 可見的決策資訊僅限決策結果。"""
    make_assessment(status="DECIDED", final_decision="SECOND_ROUND", submitted=True)
    rows = client.get("/hr/assessments", headers=hr_headers).json()
    assert rows[0]["final_decision"] == "SECOND_ROUND"


def test_filters_by_dept_status_and_job_title(client, hr_headers, make_assessment):
    """FR-014：總覽必須支援依部門、狀態與應徵職稱篩選。"""
    make_assessment(dept_id="ENG", status="PENDING_ASSIGN")
    make_assessment(dept_id="DESIGN", manager_id="33333333-3333-4333-8333-333333333333")
    target = make_assessment(dept_id="ENG", status="PENDING_CANDIDATE")

    by_dept = client.get("/hr/assessments?dept_id=ENG", headers=hr_headers).json()
    assert {row["dept_id"] for row in by_dept} == {"ENG"}

    by_status = client.get("/hr/assessments?status=PENDING_CANDIDATE", headers=hr_headers).json()
    assert [row["id"] for row in by_status] == [target["id"]]

    by_job = client.get("/hr/assessments?job_title=後端", headers=hr_headers).json()
    assert all("後端" in row["job_title"] for row in by_job)


def test_unknown_status_filter_is_rejected(client, hr_headers):
    """FR-075：系統必須拒絕任何未定義的狀態值。"""
    assert client.get("/hr/assessments?status=待審核", headers=hr_headers).status_code == 422


def test_manager_role_is_forbidden(client, eng_manager_headers):
    assert client.get("/hr/assessments", headers=eng_manager_headers).status_code == 403
