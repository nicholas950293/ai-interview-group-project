"""主管端點（FR-020、FR-023～FR-028、FR-060～FR-066）。

契約見 contracts/openapi.yaml 的 `manager` tag。

所有查詢皆限於所屬部門。這件事不是由本模組的 if 判斷達成的——
RLS 政策使他部門的列根本不會出現在查詢結果中，因此本模組看到的
「找不到」已經是政策套用後的結果（憲章原則 IV）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends

from backend.src.ai.provider import AiProvider, GenerateQuestionRequest
from backend.src.audit.logger import AuditLogger
from backend.src.config import Settings
from backend.src.dependencies import (
    get_ai_provider,
    get_sandbox_runner,
    get_settings,
    get_store,
    require_manager,
)
from backend.src.models.assessment import (
    AssessmentDetail,
    AssessmentSummaryManager,
    ExecutionRecordView,
)
from backend.src.models.decision import DecisionRequest
from backend.src.models.question import DeptType, Difficulty, Language, Question
from backend.src.models.report import AiReport
from backend.src.repositories.assessment_repo import AssessmentRepository
from backend.src.repositories.base import DataStore, RequestContext
from backend.src.repositories.decision_repo import DecisionRepository
from backend.src.repositories.question_repo import QuestionRepository
from backend.src.sandbox.runner import SandboxRunner
from backend.src.services.assessment_service import AssessmentService
from backend.src.services.errors import ConflictError, NotFoundError
from backend.src.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/manager", tags=["manager"])


def _service(store: DataStore, context: RequestContext, settings: Settings) -> AssessmentService:
    repo = AssessmentRepository(store)
    return AssessmentService(repo, AuditLogger(store), context, settings)


def _dept_type(store: DataStore, context: RequestContext) -> DeptType:
    rows = store.select("departments", filters={"id": context.dept_id}, limit=1)
    if not rows:
        raise NotFoundError("找不到所屬部門")
    return DeptType(rows[0]["type"])


@router.get("/assessments", response_model=list[AssessmentSummaryManager])
async def list_assessments(
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> list[AssessmentSummaryManager]:
    repo = AssessmentRepository(store)
    service = _service(store, context, settings)
    manager_names = repo.manager_names()

    summaries: list[AssessmentSummaryManager] = []
    for row in repo.list():
        row = service.apply_lazy_expiry(row)
        summaries.append(
            AssessmentSummaryManager(
                id=row["id"],
                name=row["name"],
                email=row["email"],
                job_title=row["job_title"],
                dept_id=row["dept_id"],
                assigned_manager=manager_names.get(row.get("assigned_manager_id")),
                status=row["status"],
                final_decision=row.get("final_decision"),
                email_status=row.get("email_status", "NOT_SENT"),
                token_expires_at=row.get("token_expires_at"),
                created_at=row.get("created_at"),
                has_report=repo.has_report(row["id"]),
            )
        )
    return summaries


@router.get("/questions", response_model=list[Question])
async def list_questions(
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
) -> list[Question]:
    return QuestionRepository(store).to_models(QuestionRepository(store).list())


@router.post("/questions/ai-generate", response_model=Question)
async def generate_question(
    skills: list[str] = Body(...),
    difficulty: Difficulty = Body(...),
    language: Language = Body(...),
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
    ai: AiProvider = Depends(get_ai_provider),
) -> Question:
    """產生題目草稿。

    **不直接指派**——草稿必須經主管明確確認後方可指派（FR-025）。
    因此回傳的 Question 沒有 id，也不會寫入任何資料表。
    """
    draft = await ai.generate_question(
        GenerateQuestionRequest(
            skills=skills,
            difficulty=difficulty,
            language=language,
            dept_type=_dept_type(store, context),
        )
    )
    return draft


@router.post("/assessments/{assessment_id}/assign-question")
async def assign_question(
    assessment_id: str,
    question: Question = Body(..., embed=True),
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return _service(store, context, settings).assign_question(assessment_id, question)


@router.get("/assessments/{assessment_id}", response_model=AssessmentDetail)
async def get_assessment(
    assessment_id: str,
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> AssessmentDetail:
    """完整審閱內容（FR-060）。

    找不到與無權存取都回傳 404，且訊息相同——不區分兩者可避免以
    「存在與否」洩漏他部門資料的存在。
    """
    repo = AssessmentRepository(store)
    row = repo.get(assessment_id)
    if row is None:
        raise NotFoundError("找不到指定的考核")
    row = _service(store, context, settings).apply_lazy_expiry(row)

    report = repo.latest_report(assessment_id)
    return AssessmentDetail(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        job_title=row["job_title"],
        dept_id=row["dept_id"],
        status=row["status"],
        question_snapshot=row.get("question_snapshot"),
        code_language=row.get("code_language"),
        candidate_answer=row.get("candidate_answer"),
        ai_chat_history=row.get("ai_chat_history") or [],
        executions=[
            ExecutionRecordView.model_validate(record) for record in repo.executions(assessment_id)
        ],
        ai_report=_report_view(report),
        decisions=DecisionRepository(store).list_for(assessment_id),
    )


def _report_view(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """報告的對外形狀。

    以 `AiReport` 序列化而非直接回傳資料列，確保 `advisory_notice` 一定存在
    （FR-058），且沒有任何總分或綜合建議欄位有機會混進來（FR-057）。
    """
    if report is None:
        return None
    return AiReport(
        attempt_no=report.get("attempt_no", 1),
        status=report.get("status", "PENDING"),
        test_pass_ratio=report.get("test_pass_ratio"),
        model_id=report.get("model_id"),
        error_message=report.get("error_message"),
        dimensions=report.get("dimensions"),
        created_at=report.get("created_at"),
    ).model_dump(mode="json")


@router.post("/assessments/{assessment_id}/decision")
async def record_decision(
    assessment_id: str,
    payload: DecisionRequest,
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return _service(store, context, settings).record_decision(assessment_id, payload)


@router.post("/assessments/{assessment_id}/reevaluate", status_code=202)
async def reevaluate(
    assessment_id: str,
    background: BackgroundTasks,
    context: RequestContext = Depends(require_manager),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    sandbox: SandboxRunner = Depends(get_sandbox_runner),
    ai: AiProvider = Depends(get_ai_provider),
) -> dict[str, str]:
    """重新觸發評測（FR-059）。

    產生新的 attempt_no，失敗紀錄保留——重試一律新增列，不覆寫（FR-078）。
    自動重試在 AI 服務故障時會放大成本，因此只由主管手動觸發（R-006）。
    """
    repo = AssessmentRepository(store)
    row = repo.get(assessment_id)
    if row is None:
        raise NotFoundError("找不到指定的考核")
    if row.get("submitted_at") is None:
        raise ConflictError("此考核尚未提交，無法評測", code="NOT_SUBMITTED")

    background.add_task(EvaluationService(store, sandbox, ai).evaluate, row["token"])
    return {"status": "SCHEDULED"}
