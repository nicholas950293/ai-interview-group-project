"""內部使用者的密碼驗證介面（FR-005）。

密碼**不存在本系統**：`internal_users` 沒有密碼欄位，只有指向 Supabase Auth 的
`auth_user_id`。本介面的職責僅止於「這組帳密是不是真的」，角色與部門一律回頭
向 `internal_users` 查——身分的真相來源只有一個。

與 AiProvider／SandboxRunner／EmailSender 同樣是可替換介面（憲章原則 II）：
預設測試套件以 `FakeAuthProvider` 完全離線執行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AuthError(RuntimeError):
    """認證流程的基底例外。"""


class InvalidCredentialsError(AuthError):
    """帳號或密碼錯誤。

    刻意不區分「帳號不存在」與「密碼錯誤」——區分兩者等於提供帳號列舉的管道。
    """


class AuthUnavailableError(AuthError):
    """認證服務暫時不可用（網路、Supabase 中斷）。與憑證錯誤是不同的事。"""


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


@dataclass(frozen=True)
class AuthenticatedUser:
    """密碼驗證通過後的結果。

    `access_token` 是 Supabase Auth 發出的 token，用於以該使用者的身分讀取
    `internal_users` 取得角色與部門；它本身**不含** app_role／dept_id claim，
    因此不能直接拿來當作本系統的憑證。
    """

    auth_user_id: str
    access_token: str


class AuthProvider(Protocol):
    async def verify_password(self, credentials: Credentials) -> AuthenticatedUser:
        """驗證帳密。

        Raises:
            InvalidCredentialsError: 帳號或密碼錯誤。
            AuthUnavailableError: 認證服務不可用。
        """
        ...
