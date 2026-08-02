"""US6：寄送失敗的處理（FR-071、FR-072、quickstart.md 情境 10）。

寄送失敗必須被捕捉並記錄，**不得**讓例外中斷請求（R-007）——
否則 HR 會看到一個 500，卻不知道信到底寄出去了沒有。
"""

from __future__ import annotations

import pytest

PAYLOAD = {"subject": "測驗結果通知", "body": "內文"}


@pytest.fixture
def decided(make_assessment):
    return make_assessment(status="DECIDED", submitted=True, final_decision="FAIL")


def test_send_failure_returns_200_with_failed_status(client, hr_headers, decided, fake_email, db):
    fake_email.healthy = False

    response = client.post(
        f"/hr/assessments/{decided['id']}/notification/send", json=PAYLOAD, headers=hr_headers
    )
    assert response.status_code == 200, "寄送失敗不得以例外中斷請求"

    body = response.json()
    assert body["email_status"] == "FAILED"
    assert body["email_error"]

    stored = db.find("assessments", id=decided["id"])
    assert stored["email_status"] == "FAILED"
    assert stored["email_error"]


def test_failure_is_audited(client, hr_headers, decided, fake_email, db):
    fake_email.healthy = False
    client.post(
        f"/hr/assessments/{decided['id']}/notification/send", json=PAYLOAD, headers=hr_headers
    )
    actions = [
        log["action"] for log in db.tables["audit_logs"] if log["assessment_id"] == decided["id"]
    ]
    assert "NOTIFICATION_FAILED" in actions
    assert "NOTIFICATION_SENT" not in actions


def test_hr_can_resend_after_failure(client, hr_headers, decided, fake_email, db):
    fake_email.healthy = False
    client.post(
        f"/hr/assessments/{decided['id']}/notification/send", json=PAYLOAD, headers=hr_headers
    )

    fake_email.healthy = True
    response = client.post(
        f"/hr/assessments/{decided['id']}/notification/send", json=PAYLOAD, headers=hr_headers
    )
    assert response.json()["email_status"] == "SENT"

    stored = db.find("assessments", id=decided["id"])
    assert stored["email_status"] == "SENT"
    assert stored["email_error"] is None, "重送成功後必須清除失敗原因"
    assert len(fake_email.sent) == 1


def test_failure_reason_is_visible_in_the_overview(client, hr_headers, decided, fake_email):
    """FR-071：總覽必須顯示寄送狀態。"""
    fake_email.healthy = False
    client.post(
        f"/hr/assessments/{decided['id']}/notification/send", json=PAYLOAD, headers=hr_headers
    )
    rows = client.get("/hr/assessments", headers=hr_headers).json()
    row = next(r for r in rows if r["id"] == decided["id"])
    assert row["email_status"] == "FAILED"


def test_send_before_decision_is_rejected(client, hr_headers, make_assessment, fake_email):
    assessment = make_assessment(status="COMPLETED_AWAITING_REVIEW", submitted=True)
    response = client.post(
        f"/hr/assessments/{assessment['id']}/notification/send", json=PAYLOAD, headers=hr_headers
    )
    assert response.status_code == 409
    assert fake_email.sent == []
