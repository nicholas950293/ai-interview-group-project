"""結果通知（FR-067～FR-072）。

範本只吃三個輸入：應徵者姓名、應徵職稱、決策結果。這不是簡化，而是
FR-070 的實作方式——沒有辦法把內部評語或 AI 報告放進來，因為這一層
根本拿不到它們（HR 的身分在資料存取層就讀不到，見 R-003）。
"""

from __future__ import annotations

import pathlib
from typing import Any

from backend.src.audit.logger import AuditAction, AuditLogger
from backend.src.email.sender import EmailMessage, EmailSender
from backend.src.models.assessment import AssessmentStatus, EmailStatus
from backend.src.models.decision import DecisionResult
from backend.src.repositories.assessment_repo import AssessmentRepository
from backend.src.repositories.base import RequestContext
from backend.src.services.errors import ConflictError, NotFoundError

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

TEMPLATE_FILES = {
    DecisionResult.PASS: "pass.txt",
    DecisionResult.SECOND_ROUND: "second_round.txt",
    DecisionResult.FAIL: "fail.txt",
}

SUBJECT_PREFIX = "主旨："
SEPARATOR = "---"


def render_template(result: DecisionResult, *, name: str, job_title: str) -> tuple[str, str]:
    """套用制式範本，回傳 (主旨, 內文)。"""
    raw = (TEMPLATES_DIR / TEMPLATE_FILES[result]).read_text(encoding="utf-8")
    subject_line, _, body = raw.partition(f"\n{SEPARATOR}\n")
    subject = subject_line.removeprefix(SUBJECT_PREFIX).strip()
    return (
        subject.format(name=name, job_title=job_title),
        body.strip().format(name=name, job_title=job_title),
    )


class NotificationService:
    def __init__(
        self,
        repo: AssessmentRepository,
        sender: EmailSender,
        audit: AuditLogger,
        context: RequestContext,
    ) -> None:
        self._repo = repo
        self._sender = sender
        self._audit = audit
        self._context = context

    def preview(self, assessment_id: str) -> dict[str, str]:
        assessment = self._require_decided(assessment_id)
        subject, body = render_template(
            DecisionResult(assessment["final_decision"]),
            name=assessment["name"],
            job_title=assessment["job_title"],
        )
        return {"subject": subject, "body": body}

    async def send(self, assessment_id: str, *, subject: str, body: str) -> dict[str, Any]:
        """發送通知。

        寄送失敗**不得**拋出例外（R-007）：HR 需要知道「寄了但失敗」與
        「系統壞了」的差別，而後者會讓人不敢重試。
        """
        assessment = self._require_decided(assessment_id)

        result = await self._sender.send(
            EmailMessage(to=assessment["email"], subject=subject, body=body)
        )

        if result.ok:
            self._repo.update(
                assessment_id,
                {"email_status": str(EmailStatus.SENT), "email_error": None},
            )
            self._audit.record(
                assessment_id=assessment_id,
                action=AuditAction.NOTIFICATION_SENT,
                context=self._context,
                detail={"email_status": str(EmailStatus.SENT)},
            )
            return {"email_status": EmailStatus.SENT.value, "email_error": None}

        self._repo.update(
            assessment_id,
            {"email_status": str(EmailStatus.FAILED), "email_error": result.error},
        )
        self._audit.record(
            assessment_id=assessment_id,
            action=AuditAction.NOTIFICATION_FAILED,
            context=self._context,
            detail={"email_status": str(EmailStatus.FAILED), "reason": result.error},
        )
        return {"email_status": EmailStatus.FAILED.value, "email_error": result.error}

    def _require_decided(self, assessment_id: str) -> dict[str, Any]:
        assessment = self._repo.get(assessment_id)
        if assessment is None:
            raise NotFoundError("找不到指定的考核")
        if assessment["status"] != str(AssessmentStatus.DECIDED) or not assessment.get(
            "final_decision"
        ):
            raise ConflictError("此考核尚未完成決策，無法發送結果通知", code="NOT_DECIDED")
        return assessment
