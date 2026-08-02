"""HR 端點（FR-009～FR-014、FR-019）。

契約見 contracts/openapi.yaml 的 `hr` tag。

本模組的回應模型一律使用 `AssessmentSummaryHR`（`extra="forbid"`），
使「不小心多回傳一個受限欄位」在序列化階段就會失敗，而非仰賴人工審查
（FR-007、FR-008）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from backend.src.audit.logger import AuditLogger
from backend.src.config import Settings
from backend.src.dependencies import (
    get_email_sender,
    get_settings,
    get_store,
    require_hr,
)
from backend.src.email.sender import EmailSender
from backend.src.models.assessment import (
    AssessmentCreated,
    AssessmentSummaryHR,
    CreateAssessmentRequest,
)
from backend.src.repositories.assessment_repo import HR_VIEW, AssessmentRepository
from backend.src.repositories.base import DataStore, RequestContext
from backend.src.services.assessment_service import AssessmentService
from backend.src.services.notification_service import NotificationService
from backend.src.services.state_machine import parse_status

router = APIRouter(prefix="/hr", tags=["hr"])


def _service(store: DataStore, context: RequestContext, settings: Settings) -> AssessmentService:
    repo = AssessmentRepository(store)
    return AssessmentService(repo, AuditLogger(store), context, settings)


def _notifications(
    store: DataStore, context: RequestContext, sender: EmailSender
) -> NotificationService:
    return NotificationService(AssessmentRepository(store), sender, AuditLogger(store), context)


def _to_summary(row: dict[str, Any], manager_names: dict[str, str]) -> AssessmentSummaryHR:
    return AssessmentSummaryHR(
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
    )


@router.post("/assessments", status_code=201, response_model=AssessmentCreated)
async def create_assessment(
    payload: CreateAssessmentRequest,
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> AssessmentCreated:
    result = _service(store, context, settings).create_assessment(payload)
    return AssessmentCreated(**result)


@router.get("/assessments", response_model=list[AssessmentSummaryHR])
async def list_assessments(
    dept_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    job_title: str | None = Query(default=None),
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> list[AssessmentSummaryHR]:
    service = _service(store, context, settings)
    repo = AssessmentRepository(store)

    # 逾期於讀取時惰性判定，因此總覽頁看到的狀態一定是最新的（FR-018）
    for row in repo.list():
        service.apply_lazy_expiry(row)

    rows = repo.list(
        view=HR_VIEW,
        dept_id=dept_id,
        status=parse_status(status) if status else None,
        job_title=job_title,
    )
    manager_names = repo.manager_names()
    return [_to_summary(row, manager_names) for row in rows]


@router.post("/assessments/{assessment_id}/reassign-manager")
async def reassign_manager(
    assessment_id: str,
    manager_id: str = Body(..., embed=True),
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return _service(store, context, settings).reassign_manager(assessment_id, manager_id)


@router.post("/assessments/{assessment_id}/regenerate-token")
async def regenerate_token(
    assessment_id: str,
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return _service(store, context, settings).regenerate_token(assessment_id)


@router.post("/assessments/{assessment_id}/notification/preview")
async def preview_notification(
    assessment_id: str,
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, str]:
    """產生通知草稿供預覽（FR-068、FR-069）。

    草稿只由 `final_decision`、姓名與職稱組出——內部評語與 AI 報告
    在這條路徑上根本不可讀（FR-070、R-003）。
    """
    return _notifications(store, context, sender).preview(assessment_id)


@router.post("/assessments/{assessment_id}/notification/send")
async def send_notification(
    assessment_id: str,
    subject: str = Body(...),
    body: str = Body(...),
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    """發送結果通知（FR-067、FR-071、FR-072）。

    寄送失敗同樣回傳 200，並將 email_status 標為 FAILED——這是刻意的：
    「請求成功處理，但寄送這件事失敗了」與「系統壞了」是兩回事。
    """
    return await _notifications(store, context, sender).send(
        assessment_id, subject=subject, body=body
    )


@router.get("/departments")
async def list_departments(
    context: RequestContext = Depends(require_hr),
    store: DataStore = Depends(get_store),
) -> list[dict[str, Any]]:
    """部門下拉選單的資料來源（FR-010）。"""
    return store.select("departments", order_by="id")
