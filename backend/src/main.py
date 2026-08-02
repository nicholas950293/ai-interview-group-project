"""FastAPI 應用程式進入點。

負責三件事：組裝相依、統一錯誤處理、安裝日誌過濾器。

**日誌過濾器不是可選項**：FR-079 與 FR-080 禁止應徵者姓名、Email、電話
與作答內容進入應用程式日誌。過濾器是最後一道防線——第一道是「不去記錄
這些欄位」，由 tests/unit/test_log_pii_filter.py 的靜態檢查守護。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.src.ai.provider import AiProvider, AiUnavailableError
from backend.src.audit.logger import REDACTED, scrub_text
from backend.src.config import Settings, load_settings
from backend.src.email.sender import EmailSender
from backend.src.repositories.base import (
    DataAccessError,
    RequestContext,
    ServiceRoleMisuseError,
    create_supabase_store,
)
from backend.src.sandbox.runner import SandboxRunner
from backend.src.services.errors import AppError, ServiceUnavailableError
from backend.src.services.state_machine import InvalidTransitionError, UnknownStatusError

LOGGER_NAME = "recruitment"

# 這些欄位一旦出現在 log record 的 extra 中即整個遮蔽（FR-079、FR-080）。
#
# 刻意**不含** "name"：`LogRecord.name` 是 logger 自身的名稱，遮蔽它會破壞
# 所有日誌的來源標示，而 `extra={"name": ...}` 本來就會被 logging 模組拒絕。
# 應徵者姓名請以 "candidate_name" 傳遞——但更正確的作法是根本不要傳。
PII_EXTRA_KEYS = frozenset(
    {
        "candidate_name",
        "email",
        "phone",
        "answer",
        "candidate_answer",
        "code",
        "internal_comment",
    }
)


class PiiLogFilter(logging.Filter):
    """禁止個資與作答內容進入日誌。

    以「形態偵測 + 鍵名封鎖」兩路處理：
    - 訊息本文中的 Email 與電話形態一律替換為遮蔽字串
    - `extra` 中被封鎖的鍵名，其值一律替換為遮蔽字串

    姓名無法以形態辨識，因此其保證來自「不記錄」而非「過濾」——
    這是靜態檢查存在的原因。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: (REDACTED if key in PII_EXTRA_KEYS else _scrub_value(value))
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(_scrub_value(value) for value in record.args)

        for key in PII_EXTRA_KEYS:
            if hasattr(record, key):
                setattr(record, key, REDACTED)
        return True


def _scrub_value(value: Any) -> Any:
    return scrub_text(value) if isinstance(value, str) else value


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not any(isinstance(f, PiiLogFilter) for f in logger.filters):
        logger.addFilter(PiiLogFilter())
    # 掛在 handler 上，使經由 root handler 輸出的紀錄同樣被過濾
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, PiiLogFilter) for f in handler.filters):
            handler.addFilter(PiiLogFilter())
    return logger


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    # contracts/openapi.yaml 的 Error schema：{code, message}
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def create_app(
    *,
    settings: Settings | None = None,
    store_factory: Any = None,
    ai_provider: AiProvider | None = None,
    sandbox_runner: SandboxRunner | None = None,
    email_sender: EmailSender | None = None,
) -> FastAPI:
    """組裝應用程式。

    四項外部相依（資料庫、AI、沙箱、Email）皆可注入替身——憲章
    「外部服務隔離」要求測試套件得以在無網路環境下完整執行。
    """
    settings = settings or load_settings()
    logger = configure_logging()

    app = FastAPI(
        title="AI 智慧招聘與技術考核系統 API",
        version="1.0.0",
        root_path="/api",
    )
    app.state.settings = settings
    app.state.logger = logger
    app.state.store_factory = store_factory or (
        lambda context: create_supabase_store(settings, context)
    )
    app.state.ai_provider = ai_provider or _default_ai_provider(settings)
    app.state.sandbox_runner = sandbox_runner or _default_sandbox_runner(settings)
    app.state.email_sender = email_sender or _default_email_sender(settings)

    _register_error_handlers(app)
    _register_routes(app)
    return app


def _default_ai_provider(settings: Settings) -> AiProvider:
    from backend.src.ai.gemini_provider import GeminiProvider

    return GeminiProvider(settings.ai)


def _default_sandbox_runner(settings: Settings) -> SandboxRunner:
    from backend.src.sandbox.docker_runner import DockerSandboxRunner

    return DockerSandboxRunner(settings.sandbox)


def _default_email_sender(settings: Settings) -> EmailSender:
    from backend.src.email.smtp_sender import SmtpEmailSender

    return SmtpEmailSender(settings.smtp)


def _register_routes(app: FastAPI) -> None:
    from backend.src.api import candidate, hr, manager

    app.include_router(hr.router)
    app.include_router(manager.router)
    app.include_router(candidate.router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(AiUnavailableError)
    async def _ai_unavailable(_: Request, exc: AiUnavailableError) -> JSONResponse:
        # AI 不可用一律 503；核心流程不受影響（FR-027、FR-052、FR-059）
        error = ServiceUnavailableError("AI 服務目前不可用，請稍後再試")
        return _error_response(error.status_code, "AI_UNAVAILABLE", error.message)

    @app.exception_handler(InvalidTransitionError)
    async def _invalid_transition(_: Request, exc: InvalidTransitionError) -> JSONResponse:
        return _error_response(409, "INVALID_STATE_TRANSITION", "目前狀態不允許此操作")

    @app.exception_handler(UnknownStatusError)
    async def _unknown_status(_: Request, exc: UnknownStatusError) -> JSONResponse:
        return _error_response(422, "UNKNOWN_STATUS", "未定義的考核狀態")

    @app.exception_handler(ServiceRoleMisuseError)
    async def _service_role(_: Request, exc: ServiceRoleMisuseError) -> JSONResponse:
        # 絕不把內部原因回給呼叫端；細節僅存在於伺服器端的例外
        return _error_response(500, "INTERNAL_ERROR", "伺服器內部錯誤")

    @app.exception_handler(DataAccessError)
    async def _data_access(_: Request, exc: DataAccessError) -> JSONResponse:
        return _error_response(403, "ACCESS_DENIED", "沒有權限執行此操作")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 不回傳原始輸入值——輸入可能含個資（FR-079）
        fields = sorted({".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()})
        return _error_response(422, "VALIDATION_ERROR", "輸入驗證失敗：" + "、".join(fields))


app = create_app()

app_context_type = RequestContext  # 供型別提示重新匯出
