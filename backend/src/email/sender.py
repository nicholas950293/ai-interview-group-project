"""EmailSender 介面（research.md R-007）。

寄送失敗必須被捕捉並以回傳值表達，**不得**讓例外中斷請求——
FR-071／FR-072 要求寄送失敗時記錄狀態與原因，且 HR 可重新發送。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None

    @classmethod
    def success(cls) -> SendResult:
        return cls(ok=True)

    @classmethod
    def failure(cls, error: str) -> SendResult:
        return cls(ok=False, error=error)


@runtime_checkable
class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> SendResult: ...
