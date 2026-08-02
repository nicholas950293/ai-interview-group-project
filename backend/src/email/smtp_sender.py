"""SMTP 寄送（research.md R-007）。

連線參數全部來自環境變數，不綁定特定供應商——企業通常已有可用的 SMTP
中繼，且 SendGrid、SES、Mailgun 皆提供 SMTP 介面，未來切換不需改動程式碼。

**失敗以回傳值表達，而非拋出例外**：FR-071／FR-072 要求寄送失敗時記錄
狀態與原因，且 HR 可重新發送。一個未捕捉的例外會讓 HR 看到 500，
卻不知道信究竟寄出去了沒有。
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage as MimeMessage

from backend.src.config import SmtpSettings
from backend.src.email.sender import EmailMessage, SendResult


class SmtpEmailSender:
    def __init__(self, settings: SmtpSettings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> SendResult:
        if not self._settings.configured:
            return SendResult.failure("SMTP 尚未設定（缺少 SMTP_HOST 或 SMTP_FROM）")
        try:
            await asyncio.to_thread(self._send_blocking, message)
        except Exception as exc:  # noqa: BLE001 - 任何寄送失敗都必須以回傳值表達
            return SendResult.failure(f"{type(exc).__name__}: {exc}")
        return SendResult.success()

    def _send_blocking(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._settings.sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)

        with smtplib.SMTP(self._settings.host, self._settings.port, timeout=30) as client:
            client.ehlo()
            if client.has_extn("starttls"):
                client.starttls()
                client.ehlo()
            if self._settings.user and self._settings.password:
                client.login(self._settings.user, self._settings.password)
            client.send_message(mime)
