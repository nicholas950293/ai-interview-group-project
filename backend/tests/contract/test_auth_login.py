"""契約：POST /auth/login（FR-005）。

登入把身分的兩半湊起來：密碼由 Supabase Auth 保管，角色與部門在 `internal_users`。
最關鍵的斷言有兩類——**簽出的權杖必須帶對 claim**（否則 RLS 會放行錯誤的資料），
以及**失敗訊息不得洩漏帳號是否存在**（否則就是帳號列舉管道）。
"""

from __future__ import annotations

import jwt
import pytest

PASSWORD = "synthetic-password"  # noqa: S105 — 合成測試資料


@pytest.fixture
def accounts(fake_auth):
    fake_auth.register("hr@example.invalid", "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", PASSWORD)
    fake_auth.register("eng@example.invalid", "aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa", PASSWORD)
    return fake_auth


def _login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_manager_login_returns_token_and_identity(client, accounts):
    response = _login(client, "eng@example.invalid")
    assert response.status_code == 200, response.text

    body = response.json()
    assert set(body) == {"token", "role", "name", "dept_id", "expires_in_hours"}
    assert body["role"] == "MANAGER"
    assert body["dept_id"] == "ENG"


def test_hr_login_has_no_department(client, accounts):
    body = _login(client, "hr@example.invalid").json()
    assert body["role"] == "HR"
    assert body["dept_id"] is None


def test_token_carries_the_claims_rls_reads(client, accounts, settings):
    """RLS 依 app_role 與 dept_id 判定；claim 錯了就等於權限錯了。"""
    token = _login(client, "eng@example.invalid").json()["token"]
    claims = jwt.decode(token, settings.supabase.jwt_secret, algorithms=["HS256"])

    assert claims["app_role"] == "MANAGER"
    assert claims["dept_id"] == "ENG"
    assert claims["sub"] == "aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa"
    # PostgREST 只對 role=authenticated 套用政策
    assert claims["role"] == "authenticated"
    assert claims["exp"] > claims["iat"]


def test_issued_token_is_accepted_by_the_api(client, accounts):
    """登入拿到的權杖必須真的能用——否則登入等於沒登入。"""
    token = _login(client, "eng@example.invalid").json()["token"]
    response = client.get("/manager/assessments", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_token_does_not_carry_personal_data(client, accounts):
    """FR-079：姓名與 Email 是個資，不放進到處轉發的權杖裡。"""
    token = _login(client, "eng@example.invalid").json()["token"]
    assert "example.invalid" not in token
    payload = jwt.decode(token, options={"verify_signature": False})
    assert "email" not in payload
    assert "name" not in payload


def test_wrong_password_is_rejected(client, accounts):
    response = _login(client, "eng@example.invalid", "not-the-password")
    assert response.status_code == 401
    assert set(response.json()) >= {"code", "message"}


def test_unknown_account_is_indistinguishable_from_a_wrong_password(client, accounts):
    """區分「帳號不存在」與「密碼錯誤」等於提供帳號列舉管道。"""
    unknown = _login(client, "nobody@example.invalid")
    wrong = _login(client, "eng@example.invalid", "not-the-password")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_password_authenticated_but_not_an_internal_user(client, fake_auth):
    """密碼對了但系統裡沒有這個人：仍以同一種訊息回應，不透露帳號存在。"""
    fake_auth.register("ghost@example.invalid", "ffffffff-9999-4999-8999-ffffffffffff", PASSWORD)
    response = _login(client, "ghost@example.invalid")
    assert response.status_code == 401


def test_auth_service_unavailable_returns_503(client, accounts, fake_auth):
    """認證服務中斷與憑證錯誤是不同的事，不可混為一談。"""
    fake_auth.set_unavailable()
    response = _login(client, "eng@example.invalid")
    assert response.status_code == 503


def test_login_needs_no_existing_credentials(client, accounts):
    """登入端點本身不得要求 Authorization 標頭，否則沒人登得進來。"""
    response = client.post(
        "/auth/login", json={"email": "eng@example.invalid", "password": PASSWORD}
    )
    assert response.status_code == 200
