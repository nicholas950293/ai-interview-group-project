"""應用程式設定。

憲章「技術與資料限制」：所有環境相關設定必須由環境變數提供，不得寫死於程式碼。
缺少必要變數時，`load_settings()` 於啟動階段即拋出 `ConfigError`——寧可啟動失敗，
也不要在執行期以預設值靜默降級成不安全的組態。

可選變數（AI、SMTP）缺少時不阻擋啟動：依 FR-052、FR-059、FR-072，
外部服務不可用時核心流程必須仍可運作，因此其缺席以「該功能降級」表達，
而非以「系統無法啟動」表達。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# 缺少任一項即無法安全地強制執行權限，因此列為必要
REQUIRED_KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET")

DEFAULT_TOKEN_TTL_DAYS = 7
DEFAULT_MAX_TRIAL_RUNS = 20
DEFAULT_SANDBOX_CONCURRENCY = 10


class ConfigError(RuntimeError):
    """設定缺漏或不合法。"""


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    anon_key: str
    jwt_secret: str
    # 僅供遷移與維護作業；處理使用者請求的程式路徑不得使用（research.md R-002，T027 守護）
    service_role_key: str | None = None


@dataclass(frozen=True)
class AiSettings:
    api_key: str | None
    model: str | None

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)


@dataclass(frozen=True)
class SmtpSettings:
    host: str | None
    port: int
    user: str | None
    password: str | None
    sender: str | None

    @property
    def configured(self) -> bool:
        return bool(self.host and self.sender)


@dataclass(frozen=True)
class SandboxSettings:
    runtime: str | None
    image_prefix: str
    max_concurrency: int


@dataclass(frozen=True)
class Settings:
    supabase: SupabaseSettings
    ai: AiSettings
    smtp: SmtpSettings
    sandbox: SandboxSettings
    token_ttl_days: int
    max_trial_runs: int
    candidate_base_url: str


def _clean(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = _clean(env, key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"環境變數 {key} 必須為整數，實際值不合法") from exc


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """自環境變數載入設定；缺少必要變數時立即失敗。"""
    env = os.environ if env is None else env

    missing = [key for key in REQUIRED_KEYS if not _clean(env, key)]
    if missing:
        raise ConfigError("缺少必要環境變數：" + "、".join(missing))

    return Settings(
        supabase=SupabaseSettings(
            url=_clean(env, "SUPABASE_URL"),  # type: ignore[arg-type]
            anon_key=_clean(env, "SUPABASE_ANON_KEY"),  # type: ignore[arg-type]
            jwt_secret=_clean(env, "SUPABASE_JWT_SECRET"),  # type: ignore[arg-type]
            service_role_key=_clean(env, "SUPABASE_SERVICE_ROLE_KEY"),
        ),
        ai=AiSettings(
            api_key=_clean(env, "GEMINI_API_KEY"),
            model=_clean(env, "GEMINI_MODEL"),
        ),
        smtp=SmtpSettings(
            host=_clean(env, "SMTP_HOST"),
            port=_int(env, "SMTP_PORT", 587),
            user=_clean(env, "SMTP_USER"),
            password=_clean(env, "SMTP_PASSWORD"),
            sender=_clean(env, "SMTP_FROM"),
        ),
        sandbox=SandboxSettings(
            runtime=_clean(env, "SANDBOX_RUNTIME"),
            image_prefix=_clean(env, "SANDBOX_IMAGE_PREFIX") or "sandbox-",
            max_concurrency=_int(env, "SANDBOX_MAX_CONCURRENCY", DEFAULT_SANDBOX_CONCURRENCY),
        ),
        token_ttl_days=_int(env, "TOKEN_TTL_DAYS", DEFAULT_TOKEN_TTL_DAYS),
        max_trial_runs=_int(env, "MAX_TRIAL_RUNS", DEFAULT_MAX_TRIAL_RUNS),
        candidate_base_url=(_clean(env, "CANDIDATE_BASE_URL") or "").rstrip("/"),
    )
