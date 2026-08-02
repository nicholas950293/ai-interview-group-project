"""專屬連結識別碼（FR-015～FR-017）。

FR-016 要求「以密碼學安全的亂數產生，使其無法被猜測或列舉」。
因此使用 `secrets`（CSPRNG）而非 `random`，且長度固定為 32 位元組——
token 同時是應徵者的唯一憑證，其強度即整條應徵者路徑的存取控制強度。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# 32 位元組的 URL-safe 編碼為 43 個字元
TOKEN_BYTES = 32


def generate_token() -> str:
    import secrets

    return secrets.token_urlsafe(TOKEN_BYTES)


def expires_at(ttl_days: int, *, now: datetime | None = None) -> datetime:
    """自現在起算的到期時間（FR-017：預設 7 天）。"""
    return (now or datetime.now(UTC)) + timedelta(days=ttl_days)


def is_expired(expiry: datetime | str | None, *, now: datetime | None = None) -> bool:
    if expiry is None:
        return False
    if isinstance(expiry, str):
        expiry = datetime.fromisoformat(expiry)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return expiry < (now or datetime.now(UTC))


def candidate_url(base_url: str, token: str) -> str | None:
    """組出應徵者作答頁的完整連結。未設定基底網址時回傳 None。"""
    if not base_url:
        return None
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}token={token}"
