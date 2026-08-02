"""契約：通知預覽與發送（FR-067～FR-072）。"""

from __future__ import annotations

import pytest


@pytest.fixture
def decided(make_assessment, question_snapshot):
    return make_assessment(
        status="DECIDED",
        question_snapshot=question_snapshot,
        candidate_answer="print(1)",
        code_language="python",
        submitted=True,
        final_decision="PASS",
    )


def test_preview_returns_subject_and_body(client, hr_headers, decided):
    response = client.post(
        f"/hr/assessments/{decided['id']}/notification/preview", headers=hr_headers
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    assert set(draft) == {"subject", "body"}
    assert draft["subject"]
    assert draft["body"]


@pytest.mark.parametrize(
    ("result", "expected"),
    [("PASS", "通過"), ("SECOND_ROUND", "後續面試"), ("FAIL", "感謝")],
)
def test_template_follows_the_decision(client, hr_headers, make_assessment, result, expected):
    assessment = make_assessment(status="DECIDED", submitted=True, final_decision=result)
    draft = client.post(
        f"/hr/assessments/{assessment['id']}/notification/preview", headers=hr_headers
    ).json()
    assert expected in draft["body"]


def test_second_round_promises_no_schedule(client, hr_headers, make_assessment):
    """FR-068、spec.md 驗收情境 6.3：不承諾具體時程。"""
    assessment = make_assessment(status="DECIDED", submitted=True, final_decision="SECOND_ROUND")
    body = client.post(
        f"/hr/assessments/{assessment['id']}/notification/preview", headers=hr_headers
    ).json()["body"]
    for forbidden in ("三天內", "一週內", "明天", "下週", "24 小時"):
        assert forbidden not in body


def test_preview_before_decision_returns_409(client, hr_headers, make_assessment):
    assessment = make_assessment(status="COMPLETED_AWAITING_REVIEW", submitted=True)
    response = client.post(
        f"/hr/assessments/{assessment['id']}/notification/preview", headers=hr_headers
    )
    assert response.status_code == 409


def test_send_returns_email_status(client, hr_headers, decided, fake_email, db):
    response = client.post(
        f"/hr/assessments/{decided['id']}/notification/send",
        json={"subject": "測驗結果通知", "body": "內文"},
        headers=hr_headers,
    )
    assert response.status_code == 200
    assert response.json() == {"email_status": "SENT", "email_error": None}

    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].subject == "測驗結果通知"
    assert db.find("assessments", id=decided["id"])["email_status"] == "SENT"


def test_hr_can_edit_before_sending(client, hr_headers, decided, fake_email):
    """FR-069：HR 必須能編輯通知內容後才發送。"""
    client.post(
        f"/hr/assessments/{decided['id']}/notification/send",
        json={"subject": "自訂主旨", "body": "自訂內文"},
        headers=hr_headers,
    )
    assert fake_email.sent[0].body == "自訂內文"


def test_send_is_audited(client, hr_headers, decided, db):
    client.post(
        f"/hr/assessments/{decided['id']}/notification/send",
        json={"subject": "主旨", "body": "內文"},
        headers=hr_headers,
    )
    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == decided["id"]
    ]
    assert "NOTIFICATION_SENT" in actions


def test_manager_role_is_forbidden(client, eng_manager_headers, decided):
    assert (
        client.post(
            f"/hr/assessments/{decided['id']}/notification/preview", headers=eng_manager_headers
        ).status_code
        == 403
    )
