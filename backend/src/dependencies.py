"""FastAPI 相依：設定、身分、資料存取與三個外部服務介面。

身分一律來自簽章過的 JWT。API 層的角色檢查是**便利與訊息品質**的措施，
不是授權的依據——真正的權限由 RLS 於資料存取層強制（憲章原則 IV）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header, Request

from backend.src.ai.provider import AiProvider
from backend.src.config import Settings
from backend.src.email.sender import EmailSender
from backend.src.repositories.base import (
    ROLE_CANDIDATE,
    ROLE_HR,
    ROLE_MANAGER,
    DataStore,
    RequestContext,
)
from backend.src.sandbox.runner import SandboxRunner
from backend.src.services.errors import ForbiddenError, UnauthorizedError

StoreFactory = Callable[[RequestContext], DataStore]

CANDIDATE_CONTEXT = RequestContext(role=ROLE_CANDIDATE)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store_factory(request: Request) -> StoreFactory:
    return request.app.state.store_factory


def get_auth_provider(request: Request) -> Any:
    """內部使用者的密碼驗證器（FR-005）。回傳型別為 AuthProvider 協定。"""
    return request.app.state.auth_provider


def get_ai_provider(request: Request) -> AiProvider:
    return request.app.state.ai_provider


def get_sandbox_runner(request: Request) -> SandboxRunner:
    return request.app.state.sandbox_runner


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


def _decode_jwt(token: str, secret: str) -> dict[str, Any]:
    import jwt  # PyJWT

    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("認證憑證無效或已過期") from exc


def get_request_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> RequestContext:
    """自 Authorization 標頭建立請求身分。

    `app_role` 與 `dept_id` 取自 JWT 自訂 claim，與 RLS 政策讀取的來源
    完全相同（research.md R-002）——因此 API 層與資料庫層不可能對身分有分歧。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("缺少認證憑證")

    token = authorization.split(" ", 1)[1].strip()
    settings: Settings = request.app.state.settings
    claims = _decode_jwt(token, settings.supabase.jwt_secret)

    role = claims.get("app_role")
    if role not in (ROLE_HR, ROLE_MANAGER):
        raise ForbiddenError("此帳號沒有可用的系統角色")

    context = RequestContext(
        role=role,
        auth_user_id=claims.get("sub"),
        dept_id=claims.get("dept_id"),
        jwt=token,
    )

    # 補上內部使用者識別碼，供稽核紀錄的 actor_id 使用（FR-076）。
    store = request.app.state.store_factory(context)
    rows = store.select("internal_users", filters={"auth_user_id": context.auth_user_id}, limit=1)
    if rows:
        context = RequestContext(
            role=role,
            auth_user_id=context.auth_user_id,
            internal_user_id=rows[0].get("id"),
            dept_id=context.dept_id or rows[0].get("dept_id"),
            jwt=token,
        )
    return context


def get_store(
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> DataStore:
    return request.app.state.store_factory(context)


def require_hr(context: RequestContext = Depends(get_request_context)) -> RequestContext:
    if context.role != ROLE_HR:
        raise ForbiddenError("此操作僅限 HR 角色")
    return context


def require_manager(context: RequestContext = Depends(get_request_context)) -> RequestContext:
    if context.role != ROLE_MANAGER:
        raise ForbiddenError("此操作僅限部門主管角色")
    return context


def get_candidate_store(request: Request) -> DataStore:
    """應徵者路徑的存取層。

    應徵者沒有 JWT，其身分即為 token 本身。底層資料表不對 anon 開放，
    因此本 store 只能呼叫 SECURITY DEFINER 函式（research.md R-002）。
    """
    return request.app.state.store_factory(CANDIDATE_CONTEXT)
