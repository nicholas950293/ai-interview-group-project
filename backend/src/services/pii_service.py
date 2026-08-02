"""個資刪除（FR-082）。

**不採實體刪除。** `audit_logs` 的唯附加要求（FR-078）與稽核完整性
（憲章原則 V）優先於資料列的移除，而去識別化已足以達成個資保護目的。
刪除考核列會連帶讓稽核歷程失去對象，等於用一項合規要求換掉另一項。

流程見 data-model.md「個資刪除流程」：
1. 以 `email` 找出該人的所有考核
2. 覆寫 `name`、`email`、`phone`，清空 `candidate_answer` 與 `ai_chat_history`
3. `execution_records`、`ai_reports` 保留（不含個資）
4. `manager_decisions.internal_comment` 保留（企業內部紀錄）
5. 寫入 `PII_ERASED`，僅記錄考核識別碼
"""

from __future__ import annotations

import hashlib
from typing import Any

from backend.src.audit.logger import AuditAction, AuditLogger
from backend.src.repositories.assessment_repo import AssessmentRepository
from backend.src.repositories.base import RequestContext

# .invalid 為 RFC 2606 保留的頂級網域，保證無法寄達
ERASED_EMAIL_DOMAIN = "erased.invalid"
ERASED_NAME_PREFIX = "已刪除應徵者"


def _pseudonym(email: str) -> str:
    """自 Email 導出穩定的假名。

    使用雜湊而非流水號，使同一人的多筆紀錄在去識別化後仍可彼此對應
    （稽核需要），但無法反推原始 Email。
    """
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


class PiiService:
    def __init__(
        self,
        repo: AssessmentRepository,
        audit: AuditLogger,
        context: RequestContext,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._context = context

    def erase(self, email: str) -> dict[str, Any]:
        normalized = email.strip().lower()
        token = _pseudonym(normalized)

        targets = [
            row
            for row in self._repo.store.select("assessments", filters={"email": normalized})
            if not str(row.get("email", "")).endswith(ERASED_EMAIL_DOMAIN)
        ]

        for row in targets:
            self._repo.update(
                row["id"],
                {
                    "name": f"{ERASED_NAME_PREFIX}-{token}",
                    "email": f"{token}@{ERASED_EMAIL_DOMAIN}",
                    "phone": None,
                    "candidate_answer": None,
                    "ai_chat_history": [],
                },
            )
            self._audit.record(
                assessment_id=row["id"],
                action=AuditAction.PII_ERASED,
                context=self._context,
                # 僅記錄考核識別碼；連被刪除的 Email 都不得留下（FR-079、FR-082）
                detail={"reason": "PII_ERASURE_REQUEST"},
            )

        return {"erased": len(targets), "assessment_ids": [row["id"] for row in targets]}
