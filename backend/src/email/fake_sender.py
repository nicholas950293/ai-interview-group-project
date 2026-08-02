"""FakeEmailSender（測試替身）。用於預設離線套件，不連線任何 SMTP 主機。"""

from __future__ import annotations

from backend.src.email.sender import EmailMessage, SendResult


class FakeEmailSender:
    def __init__(
        self, *, healthy: bool = True, error: str = "SMTP 連線失敗（測試替身設定）"
    ) -> None:
        self.healthy = healthy
        self.error = error
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> SendResult:
        if not self.healthy:
            # 失敗以回傳值表達，不拋出例外（R-007）
            return SendResult.failure(self.error)
        self.sent.append(message)
        return SendResult.success()
