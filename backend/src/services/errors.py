"""領域錯誤。

以型別表達 HTTP 語意，使 API 層不需在每個端點重複判斷狀態碼，
且錯誤訊息集中於一處——contracts/openapi.yaml 要求訊息為繁體中文
且不得含個資或作答內容（FR-079、FR-080）。
"""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    """不存在，或無權存取。

    兩者刻意不區分——contracts/openapi.yaml 註明此舉是為避免以「存在與否」
    洩漏他部門資料的存在（FR-003）。
    """

    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class GoneError(AppError):
    status_code = 410
    code = "GONE"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class RateLimitedError(AppError):
    status_code = 429
    code = "TRIAL_RUN_LIMIT_REACHED"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
