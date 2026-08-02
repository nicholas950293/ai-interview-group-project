"""US3：連結逾期（quickstart.md 情境 9、FR-018、FR-019）。"""

from __future__ import annotations


def test_expired_link_returns_410_without_question(client, make_assessment, question_snapshot, db):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
    )

    response = client.get(f"/candidate/session/{assessment['token']}")
    assert response.status_code == 410
    assert response.json()["code"] == "LINK_EXPIRED"

    # 題目內容不得出現在逾期回應中（FR-018）
    assert "兩數相加" not in response.text
    assert question_snapshot["description"] not in response.text


def test_status_transitions_to_expired_and_is_audited(
    client, make_assessment, question_snapshot, db
):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
    )
    client.get(f"/candidate/session/{assessment['token']}")

    assert db.find("assessments", id=assessment["id"])["status"] == "EXPIRED"

    logs = [
        log
        for log in db.tables["audit_logs"]
        if log["assessment_id"] == assessment["id"] and log["action"] == "STATUS_EXPIRED"
    ]
    assert len(logs) == 1
    assert logs[0]["from_status"] == "PENDING_CANDIDATE"
    assert logs[0]["to_status"] == "EXPIRED"
    assert logs[0]["actor_role"] == "SYSTEM"


def test_regenerated_link_restores_access_and_kills_the_old_one(
    client, hr_headers, make_assessment, question_snapshot, db
):
    assessment = make_assessment(
        status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
    )
    old_token = assessment["token"]
    client.get(f"/candidate/session/{old_token}")  # 觸發逾期判定

    new_token = client.post(
        f"/hr/assessments/{assessment['id']}/regenerate-token", headers=hr_headers
    ).json()["token"]

    # 舊 token 立即失效（FR-019）
    assert client.get(f"/candidate/session/{old_token}").status_code == 404

    # 新 token 可正常載入，狀態回到待作答
    response = client.get(f"/candidate/session/{new_token}")
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_CANDIDATE"
    assert response.json()["question"]["title"] == "兩數相加"


def test_expiry_is_evaluated_lazily_on_every_read_path(
    client, make_assessment, question_snapshot, db
):
    """不使用排程作業——任何讀取路徑都會判定（data-model.md「逾期判定」）。"""
    for endpoint, method, payload in (
        ("", "get", None),
        ("/run", "post", {"code": "x", "language": "python", "stdin": ""}),
        ("/submit", "post", {"answer": "x", "language": "python"}),
        ("/chat", "post", {"message": "x"}),
    ):
        assessment = make_assessment(
            status="PENDING_CANDIDATE", question_snapshot=question_snapshot, expires_in_days=-1
        )
        url = f"/candidate/session/{assessment['token']}{endpoint}"
        response = getattr(client, method)(url, json=payload) if payload else client.get(url)
        assert response.status_code == 410, f"{url} 應回傳 410"
        assert db.find("assessments", id=assessment["id"])["status"] == "EXPIRED"


def test_decided_assessment_never_becomes_expired(client, make_assessment, db):
    """DECIDED 為終態；效期過了也不得轉為 EXPIRED（FR-074）。"""
    assessment = make_assessment(status="DECIDED", submitted=True, expires_in_days=-30)
    client.get(f"/candidate/session/{assessment['token']}")
    assert db.find("assessments", id=assessment["id"])["status"] == "DECIDED"
