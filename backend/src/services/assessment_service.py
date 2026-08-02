"""考核流程協調（FR-009～FR-019、FR-028、FR-032）。

服務層負責「流程」，不負責「權限」——權限由 RLS 於資料存取層強制
（憲章原則 IV）。因此這裡看到的每一次「找不到」都已經是政策套用後的結果。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.src.audit.logger import AuditAction, AuditLogger
from backend.src.config import Settings
from backend.src.models.assessment import (
    AssessmentStatus,
    CreateAssessmentRequest,
)
from backend.src.models.decision import DecisionRequest
from backend.src.models.question import DeptType, MissingTestCasesError, Question
from backend.src.repositories.assessment_repo import AssessmentRepository
from backend.src.repositories.base import RequestContext
from backend.src.repositories.decision_repo import DecisionRepository
from backend.src.services.errors import (
    ConflictError,
    NotFoundError,
    RateLimitedError,
    ValidationError,
)
from backend.src.services.state_machine import assert_transition
from backend.src.services.token_service import (
    candidate_url,
    expires_at,
    generate_token,
    is_expired,
)


class AssessmentService:
    def __init__(
        self,
        repo: AssessmentRepository,
        audit: AuditLogger,
        context: RequestContext,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._context = context
        self._settings = settings

    # ────────────────────────── US1：建案 ──────────────────────────

    def create_assessment(self, payload: CreateAssessmentRequest) -> dict[str, Any]:
        department = self._repo.department(payload.dept_id)
        if department is None:
            raise NotFoundError("找不到指定的部門")

        email = payload.email.strip().lower()

        # 同一 Email 與同一職缺已有進行中的考核時，須明確確認（FR-009 邊界情況）
        if not payload.confirm_duplicate:
            duplicates = self._repo.find_active_duplicates(email=email, job_title=payload.job_title)
            if duplicates:
                raise ConflictError(
                    "此 Email 與職缺已有進行中的考核；如確定要另建一筆，請明確確認",
                    code="DUPLICATE_ASSESSMENT",
                )

        # 依所選部門自動指派責任主管（FR-011）
        manager = self._repo.active_manager_of(payload.dept_id)
        token = generate_token()
        expiry = expires_at(self._settings.token_ttl_days)

        created = self._repo.create(
            {
                "name": payload.name,
                "email": email,
                "phone": payload.phone,
                "job_title": payload.job_title,
                "dept_id": payload.dept_id,
                "assigned_manager_id": manager["id"] if manager else None,
                "status": str(AssessmentStatus.PENDING_ASSIGN),
                "token": token,
                "token_expires_at": expiry,
            }
        )

        self._audit.record(
            assessment_id=created["id"],
            action=AuditAction.ASSESSMENT_CREATED,
            context=self._context,
            to_status=str(AssessmentStatus.PENDING_ASSIGN),
            detail={"dept_id": payload.dept_id},
        )

        return {
            "id": created["id"],
            "token": token,
            "token_expires_at": expiry,
            "status": AssessmentStatus.PENDING_ASSIGN,
            "assigned_manager": manager["name"] if manager else None,
            "candidate_url": candidate_url(self._settings.candidate_base_url, token),
        }

    def reassign_manager(self, assessment_id: str, manager_id: str) -> dict[str, Any]:
        assessment = self._require(assessment_id)
        manager = self._repo.internal_user(manager_id)
        if manager is None or manager.get("role") != "MANAGER":
            raise ValidationError("指定的責任主管不存在或不是主管角色")

        previous = assessment.get("assigned_manager_id")
        self._repo.update(assessment_id, {"assigned_manager_id": manager_id})
        self._audit.record(
            assessment_id=assessment_id,
            action=AuditAction.MANAGER_REASSIGNED,
            context=self._context,
            detail={"from_manager_id": previous, "to_manager_id": manager_id},
        )
        return {"assigned_manager": manager.get("name")}

    def regenerate_token(self, assessment_id: str) -> dict[str, Any]:
        """重新產生連結。舊 token 立即失效（FR-019）。"""
        assessment = self._require(assessment_id)
        status = AssessmentStatus(assessment["status"])

        token = generate_token()
        expiry = expires_at(self._settings.token_ttl_days)
        values: dict[str, Any] = {"token": token, "token_expires_at": expiry}

        # 逾期者回到待作答；其餘狀態僅換發連結，不改變流程位置
        if status is AssessmentStatus.EXPIRED:
            assert_transition(status, AssessmentStatus.PENDING_CANDIDATE)
            values["status"] = str(AssessmentStatus.PENDING_CANDIDATE)

        self._repo.update(assessment_id, values)
        self._audit.record(
            assessment_id=assessment_id,
            action=AuditAction.TOKEN_REGENERATED,
            context=self._context,
            from_status=str(status),
            to_status=values.get("status", str(status)),
        )
        return {
            "token": token,
            "token_expires_at": expiry,
            "candidate_url": candidate_url(self._settings.candidate_base_url, token),
        }

    # ────────────────────────── US2：指派題目 ──────────────────────────

    def assign_question(self, assessment_id: str, question: Question) -> dict[str, Any]:
        assessment = self._require(assessment_id)
        status = AssessmentStatus(assessment["status"])
        assert_transition(status, AssessmentStatus.PENDING_CANDIDATE)

        department = self._repo.department(assessment["dept_id"])
        dept_type = DeptType(department["type"]) if department else DeptType.NON_ENGINEERING
        # 缺測資的工程類題目必須被拒絕指派（FR-026）
        try:
            question.require_test_cases_for(dept_type)
        except MissingTestCasesError as exc:
            raise ConflictError(str(exc), code="MISSING_TEST_CASES") from exc

        # 快照：題庫後續變更不影響已指派的考核（FR-028）
        snapshot = question.model_dump(mode="json")
        snapshot["assigned_at"] = datetime.now(UTC).isoformat()
        snapshot["assigned_by"] = self._context.internal_user_id

        self._repo.update(
            assessment_id,
            {
                "question_snapshot": snapshot,
                "status": str(AssessmentStatus.PENDING_CANDIDATE),
                "code_language": snapshot.get("language"),
            },
        )
        self._audit.record(
            assessment_id=assessment_id,
            action=AuditAction.QUESTION_ASSIGNED,
            context=self._context,
            from_status=str(status),
            to_status=str(AssessmentStatus.PENDING_CANDIDATE),
            detail={
                "source": snapshot.get("source"),
                "difficulty": snapshot.get("difficulty"),
                "language": snapshot.get("language"),
                "test_case_count": len(question.test_cases),
            },
        )
        return {"status": AssessmentStatus.PENDING_CANDIDATE}

    # ────────────────────────── US5：決策 ──────────────────────────

    def record_decision(self, assessment_id: str, payload: DecisionRequest) -> dict[str, Any]:
        """記錄或修訂決策（FR-061～FR-065）。

        決策與 `assessments.final_decision` 於同一流程寫入——後者是 HR 能取得
        決策結果卻無法取得評語的唯一來源（FR-007、R-003）。

        `SECOND_ROUND` 不建立新考核、不觸發任何後續流程（FR-065）：
        這裡除了寫入決策之外，刻意沒有任何分支。
        """
        assessment = self._require(assessment_id)
        status = AssessmentStatus(assessment["status"])

        if status is AssessmentStatus.COMPLETED_AWAITING_REVIEW:
            assert_transition(status, AssessmentStatus.DECIDED)
            action = AuditAction.DECISION_RECORDED
            next_status: AssessmentStatus | None = AssessmentStatus.DECIDED
        elif status is AssessmentStatus.DECIDED:
            # 修訂只新增紀錄，不改變狀態（data-model.md 狀態機）
            action = AuditAction.DECISION_REVISED
            next_status = None
        else:
            raise ConflictError("目前狀態不允許記錄決策", code="INVALID_STATE")

        decisions = DecisionRepository(self._repo.store)
        revision_no = decisions.next_revision_no(assessment_id)
        decisions.append(
            assessment_id=assessment_id,
            revision_no=revision_no,
            decided_by=self._context.internal_user_id,
            result=str(payload.result),
            internal_comment=payload.internal_comment,
        )

        values: dict[str, Any] = {"final_decision": str(payload.result)}
        if next_status is not None:
            values["status"] = str(next_status)
        self._repo.update(assessment_id, values)

        self._audit.record(
            assessment_id=assessment_id,
            action=action,
            context=self._context,
            from_status=str(status),
            to_status=str(next_status or status),
            # 內部評語刻意不進入稽核 detail（FR-007、FR-079）
            detail={"result": str(payload.result), "revision_no": revision_no},
        )
        return {"revision_no": revision_no}

    # ────────────────────────── 共用 ──────────────────────────

    def _require(self, assessment_id: str) -> dict[str, Any]:
        assessment = self._repo.get(assessment_id)
        if assessment is None:
            # 「不存在」與「無權存取」刻意不區分（contracts/openapi.yaml）
            raise NotFoundError("找不到指定的考核")
        return self.apply_lazy_expiry(assessment)

    def apply_lazy_expiry(self, assessment: dict[str, Any]) -> dict[str, Any]:
        """逾期惰性判定（data-model.md「逾期判定」）。

        不使用排程作業：任何讀取路徑若發現效期已過且狀態仍可逾期，
        即轉為 EXPIRED 並寫入稽核。此設計避免引入排程器（憲章原則 III）。
        """
        status = AssessmentStatus(assessment["status"])
        if status not in (AssessmentStatus.PENDING_ASSIGN, AssessmentStatus.PENDING_CANDIDATE):
            return assessment
        if not is_expired(assessment.get("token_expires_at")):
            return assessment

        assert_transition(status, AssessmentStatus.EXPIRED)
        self._repo.update(assessment["id"], {"status": str(AssessmentStatus.EXPIRED)})
        self._audit.record(
            assessment_id=assessment["id"],
            action=AuditAction.STATUS_EXPIRED,
            context=self._context,
            from_status=str(status),
            to_status=str(AssessmentStatus.EXPIRED),
            detail={"reason": "TOKEN_EXPIRED"},
        )
        return {**assessment, "status": str(AssessmentStatus.EXPIRED)}

    def consume_trial_run(self, assessment: dict[str, Any]) -> int:
        """檢查試跑次數上限（FR-032）。回傳剩餘次數。

        達上限後停止提供試跑，但**不阻擋提交**——這是 FR-032 的明確要求，
        因此上限的檢查點必須只在試跑路徑上。
        """
        used = assessment.get("trial_run_count", 0)
        remaining = self._settings.max_trial_runs - used
        if remaining <= 0:
            raise RateLimitedError("已達試跑次數上限，仍可提交作答")
        return remaining
