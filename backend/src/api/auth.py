"""登入端點（FR-005）。

流程刻意分成兩步，因為身分的兩半存在不同地方：

    1. 密碼 → Supabase Auth 驗證（本系統不存密碼）
    2. 角色與部門 → 回頭查 `internal_users`（唯一的真相來源）

第 2 步用第 1 步拿到的 Supabase token 讀取，因此仍受 RLS 約束；
`internal_users` 需要一條「可讀自己那一列」的政策才讀得到
（supabase/migrations/0012_internal_users_bootstrap.sql）。

兩半湊齊後，本系統簽出自己的 JWT，內含 RLS 政策所讀取的 `app_role` 與
`dept_id` claim——與 dependencies.py 的驗證來源完全相同。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Body, Depends

from backend.src.auth.provider import (
    AuthenticatedUser,
    AuthProvider,
    AuthUnavailableError,
    Credentials,
    InvalidCredentialsError,
)
from backend.src.config import Settings
from backend.src.dependencies import get_auth_provider, get_settings, get_store_factory
from backend.src.repositories.base import ROLE_AUTHENTICATED, RequestContext
from backend.src.services.errors import ServiceUnavailableError, UnauthorizedError

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_CLAIM = "app_role"
VALID_ROLES = ("HR", "MANAGER")

# PostgREST 要求 `role` claim 才會套用 authenticated 的政策
POSTGREST_ROLE = ROLE_AUTHENTICATED


def _issue_token(user_row: dict[str, Any], auth_user_id: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": auth_user_id,
        "role": POSTGREST_ROLE,
        ROLE_CLAIM: user_row["role"],
        "dept_id": user_row.get("dept_id"),
        "iat": now,
        "exp": now + timedelta(hours=settings.session_ttl_hours),
    }
    return jwt.encode(claims, settings.supabase.jwt_secret, algorithm="HS256")


@router.post("/login")
async def login(
    email: str = Body(...),
    password: str = Body(...),
    settings: Settings = Depends(get_settings),
    auth: AuthProvider = Depends(get_auth_provider),
    store_factory: Any = Depends(get_store_factory),
) -> dict[str, Any]:
    """以 Email 與密碼換取本系統的存取權杖。"""
    try:
        user: AuthenticatedUser = await auth.verify_password(
            Credentials(email=email.strip(), password=password)
        )
    except InvalidCredentialsError as exc:
        raise UnauthorizedError("帳號或密碼錯誤") from exc
    except AuthUnavailableError as exc:
        raise ServiceUnavailableError("認證服務目前不可用，請稍後再試") from exc

    # 以剛取得的 Supabase token 讀自己那一列；RLS 仍然生效
    context = RequestContext(
        role=POSTGREST_ROLE, auth_user_id=user.auth_user_id, jwt=user.access_token
    )
    rows = store_factory(context).select(
        "internal_users", filters={"auth_user_id": user.auth_user_id}, limit=1
    )

    # 密碼對了但系統裡沒有對應的內部使用者：這是帳號未開通，不是憑證錯誤。
    # 但對外仍以同一種訊息回應，不透露帳號在 Supabase 存在與否。
    if not rows:
        raise UnauthorizedError("帳號或密碼錯誤")

    row = rows[0]
    if not row.get("is_active", True) or row.get("role") not in VALID_ROLES:
        raise UnauthorizedError("此帳號沒有可用的系統角色")

    return {
        "token": _issue_token(row, user.auth_user_id, settings),
        "role": row["role"],
        "name": row.get("name"),
        "dept_id": row.get("dept_id"),
        "expires_in_hours": settings.session_ttl_hours,
    }
