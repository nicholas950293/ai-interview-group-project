"""以 Supabase Auth 驗證內部使用者的密碼（FR-005）。

密碼由 Supabase Auth 保管，本系統從不接觸雜湊、也不儲存密碼——
`internal_users` 只有指向 Supabase 的 `auth_user_id`。

只呼叫 password grant 這一個端點；取得 token 後仍需回頭查 `internal_users`
才知道角色與部門（見 backend/src/api/auth.py）。
"""

from __future__ import annotations

from typing import Any

from backend.src.auth.provider import (
    AuthenticatedUser,
    AuthUnavailableError,
    Credentials,
    InvalidCredentialsError,
)
from backend.src.config import SupabaseSettings

_TIMEOUT_SECONDS = 10.0


class SupabaseAuthProvider:
    def __init__(self, settings: SupabaseSettings) -> None:
        self._settings = settings

    @property
    def _token_url(self) -> str:
        return f"{self._settings.url.rstrip('/')}/auth/v1/token?grant_type=password"

    async def verify_password(self, credentials: Credentials) -> AuthenticatedUser:
        import httpx  # 延後匯入：離線測試不需要此相依

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self._token_url,
                    headers={
                        "apikey": self._settings.anon_key,
                        "Content-Type": "application/json",
                    },
                    json={"email": credentials.email, "password": credentials.password},
                )
        except Exception as exc:  # noqa: BLE001 — 任何傳輸層失敗都是「服務不可用」
            raise AuthUnavailableError("無法連線至認證服務") from exc

        # 400／401 一律視為憑證錯誤；不回放 Supabase 的原始訊息，
        # 以免以「帳號不存在／密碼錯誤」的差異提供帳號列舉管道
        if response.status_code in (400, 401):
            raise InvalidCredentialsError("帳號或密碼錯誤")
        if response.status_code >= 500:
            raise AuthUnavailableError("認證服務目前不可用")
        if response.status_code != 200:
            raise AuthUnavailableError("認證服務回應非預期狀態")

        return _to_user(response.json())


def _to_user(payload: dict[str, Any]) -> AuthenticatedUser:
    access_token = payload.get("access_token")
    auth_user_id = (payload.get("user") or {}).get("id")
    if not access_token or not auth_user_id:
        raise AuthUnavailableError("認證服務回應缺少必要欄位")
    return AuthenticatedUser(auth_user_id=str(auth_user_id), access_token=str(access_token))
