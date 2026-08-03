"""AuthProvider 的測試替身與 demo 模式實作。

憲章原則 II：預設測試套件必須在無網路、無外部服務的環境中完整執行。
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.src.auth.provider import (
    AuthenticatedUser,
    AuthUnavailableError,
    Credentials,
    InvalidCredentialsError,
)


@dataclass(frozen=True)
class _Account:
    auth_user_id: str
    password: str


class FakeAuthProvider:
    """以記憶體帳號表驗證密碼。

    合成資料。憲章原則 IV：真實應徵者／使用者資料不得出現於測試或 demo 中。
    """

    def __init__(self, accounts: dict[str, _Account] | None = None) -> None:
        self._accounts: dict[str, _Account] = dict(accounts or {})
        self.unavailable = False

    def register(self, email: str, auth_user_id: str, password: str) -> None:
        self._accounts[email.strip().lower()] = _Account(auth_user_id, password)

    def set_unavailable(self, value: bool = True) -> None:
        self.unavailable = value

    async def verify_password(self, credentials: Credentials) -> AuthenticatedUser:
        if self.unavailable:
            raise AuthUnavailableError("認證服務目前不可用")

        account = self._accounts.get(credentials.email.strip().lower())
        # 帳號不存在與密碼錯誤回傳同一個例外——區分兩者等於提供帳號列舉管道
        if account is None or account.password != credentials.password:
            raise InvalidCredentialsError("帳號或密碼錯誤")

        # 替身直接以 auth_user_id 當作 access_token：demo 的記憶體儲存不做 RLS，
        # 這個值只會被當成不透明字串轉發。
        return AuthenticatedUser(
            auth_user_id=account.auth_user_id, access_token=account.auth_user_id
        )


def build_demo_auth_provider() -> FakeAuthProvider:
    """demo 模式的帳號，與 backend/src/demo.py 的種子使用者對應。"""
    provider = FakeAuthProvider()
    provider.register("hr@example.com", "demo-hr-user", "demo1234")
    provider.register("manager@example.com", "demo-manager-user", "demo1234")
    return provider
