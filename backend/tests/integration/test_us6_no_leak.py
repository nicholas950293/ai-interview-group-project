"""US6：通知內容不得含內部評語與 AI 報告（FR-070、SC-011）。

SC-011 的目標值是「出現次數為 0」。這在架構上由兩件事共同保證：
HR 的查詢結果本身就取不到這些內容（FR-008），以及通知範本只吃
`final_decision` 一個輸入。本測試驗證後者。
"""

from __future__ import annotations

import pytest

INTERNAL_COMMENT = "內部評語：溝通能力不足，但技術可用"
REPORT_COMMENT = "AI 報告：命名清晰但缺少錯誤處理"


@pytest.fixture
def decided_with_restricted_content(
    client, eng_manager_headers, make_assessment, question_snapshot, db
):
    assessment = make_assessment(
        status="COMPLETED_AWAITING_REVIEW",
        question_snapshot=question_snapshot,
        candidate_answer="print('應徵者的作答內容')",
        code_language="python",
        submitted=True,
    )
    db.insert_raw(
        "ai_reports",
        {
            "assessment_id": assessment["id"],
            "attempt_no": 1,
            "status": "SUCCESS",
            "dimensions": {
                "correctness": {"score": 80, "comment": REPORT_COMMENT},
                "maintainability": {"score": 60, "comment": REPORT_COMMENT},
                "performance": {"score": 70, "comment": REPORT_COMMENT},
                "security": {"score": 50, "comment": REPORT_COMMENT},
            },
            "test_pass_ratio": 0.8,
            "model_id": "synthetic",
        },
    )
    client.post(
        f"/manager/assessments/{assessment['id']}/decision",
        json={"result": "SECOND_ROUND", "internal_comment": INTERNAL_COMMENT},
        headers=eng_manager_headers,
    )
    return assessment


def test_draft_contains_no_restricted_content(client, hr_headers, decided_with_restricted_content):
    response = client.post(
        f"/hr/assessments/{decided_with_restricted_content['id']}/notification/preview",
        headers=hr_headers,
    )
    assert response.status_code == 200
    assert INTERNAL_COMMENT not in response.text
    assert REPORT_COMMENT not in response.text
    assert "應徵者的作答內容" not in response.text


def test_sent_content_contains_no_restricted_content(
    client, hr_headers, decided_with_restricted_content, fake_email
):
    draft = client.post(
        f"/hr/assessments/{decided_with_restricted_content['id']}/notification/preview",
        headers=hr_headers,
    ).json()
    client.post(
        f"/hr/assessments/{decided_with_restricted_content['id']}/notification/send",
        json=draft,
        headers=hr_headers,
    )
    sent = fake_email.sent[0]
    assert INTERNAL_COMMENT not in sent.body
    assert REPORT_COMMENT not in sent.body
    assert INTERNAL_COMMENT not in sent.subject


def test_hr_cannot_inject_restricted_content_it_cannot_read(
    client, hr_headers, decided_with_restricted_content
):
    """HR 讀不到受限內容，因此也無從把它放進通知——這是架構性的保證。"""
    rows = client.get("/hr/assessments", headers=hr_headers).json()
    assert INTERNAL_COMMENT not in str(rows)
    assert REPORT_COMMENT not in str(rows)

    detail = client.get(
        f"/manager/assessments/{decided_with_restricted_content['id']}", headers=hr_headers
    )
    assert detail.status_code == 403


def test_draft_addresses_the_candidate_by_name_only(
    client, hr_headers, decided_with_restricted_content, db
):
    """通知是對外文件，可以有姓名；但不得有任何評測細節。"""
    body = client.post(
        f"/hr/assessments/{decided_with_restricted_content['id']}/notification/preview",
        headers=hr_headers,
    ).json()["body"]
    stored = db.find("assessments", id=decided_with_restricted_content["id"])
    assert stored["name"] in body
    for token in ("score", "分數", "維度", "correctness"):
        assert token not in body
