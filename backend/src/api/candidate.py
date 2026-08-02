"""應徵者端點（FR-018、FR-029～FR-035、FR-049～FR-053）。

契約見 contracts/openapi.yaml 的 `candidate` tag。

應徵者沒有 JWT，其身分即為路徑中的 token。所有資料存取一律經
SECURITY DEFINER 函式，函式內部重新驗證 token 與效期——本層的檢查
是為了回傳正確的 HTTP 狀態碼，不是授權的依據（research.md R-002）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends

from backend.src.ai.provider import AiProvider, AiUnavailableError, ChatAssistRequest
from backend.src.config import Settings
from backend.src.dependencies import (
    get_ai_provider,
    get_candidate_store,
    get_sandbox_runner,
    get_settings,
)
from backend.src.models.assessment import CandidateSession, ChatMessage
from backend.src.models.question import Language, Question
from backend.src.models.report import ExecutionResult
from backend.src.repositories.base import DataStore
from backend.src.sandbox.runner import ExecutionRequest, SandboxRunner
from backend.src.services.errors import (
    ConflictError,
    GoneError,
    NotFoundError,
    RateLimitedError,
    ServiceUnavailableError,
)
from backend.src.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/candidate", tags=["candidate"])

# SECURITY DEFINER 函式的失敗原因 → HTTP 語意
_REASON_ERRORS = {
    "NOT_FOUND": lambda: NotFoundError("找不到此測驗連結"),
    "EXPIRED": lambda: GoneError("測驗連結已逾期，請聯繫 HR 申請重新產生連結", code="LINK_EXPIRED"),
    "ALREADY_SUBMITTED": lambda: ConflictError(
        "此考核已提交，不可重複作答或修改", code="ALREADY_SUBMITTED"
    ),
    "INVALID_STATUS": lambda: ConflictError("目前狀態不允許此操作", code="INVALID_STATE"),
    "INVALID_ROLE": lambda: ConflictError("訊息角色不合法", code="INVALID_ROLE"),
    "LIMIT_REACHED": lambda: RateLimitedError("已達試跑次數上限，仍可提交作答"),
}


def _raise_for(reason: str | None) -> None:
    factory = _REASON_ERRORS.get(reason or "")
    raise factory() if factory else ConflictError("操作無法完成")


def _load_session(store: DataStore, token: str, settings: Settings) -> dict[str, Any]:
    session = store.rpc(
        "get_assessment_by_token",
        {"p_token": token, "p_max_trial_runs": settings.max_trial_runs},
    )
    if not session:
        raise NotFoundError("找不到此測驗連結")
    if session.get("status") == "EXPIRED":
        # 逾期者必須拒絕提供題目內容（FR-018）
        raise GoneError("測驗連結已逾期，請聯繫 HR 申請重新產生連結", code="LINK_EXPIRED")
    return session


@router.get("/session/{token}", response_model=CandidateSession)
async def get_session(
    token: str,
    store: DataStore = Depends(get_candidate_store),
    settings: Settings = Depends(get_settings),
) -> CandidateSession:
    session = _load_session(store, token, settings)
    return CandidateSession(
        job_title=session["job_title"],
        dept_type=session["dept_type"],
        status=session["status"],
        token_expires_at=session["token_expires_at"],
        question=session.get("question"),
        code_language=session.get("code_language"),
        trial_runs_remaining=session.get("trial_runs_remaining", 0),
        submitted_at=session.get("submitted_at"),
        chat_history=session.get("chat_history") or [],
    )


@router.post("/session/{token}/run", response_model=ExecutionResult)
async def run_code(
    token: str,
    code: str = Body(...),
    language: Language = Body(...),
    stdin: str = Body(default=""),
    store: DataStore = Depends(get_candidate_store),
    settings: Settings = Depends(get_settings),
    sandbox: SandboxRunner = Depends(get_sandbox_runner),
) -> ExecutionResult:
    session = _load_session(store, token, settings)
    if session.get("submitted_at") is not None:
        raise ConflictError("此考核已提交，不可再試跑", code="ALREADY_SUBMITTED")
    # 達上限後停止提供試跑，但不阻擋提交（FR-032）
    if session.get("trial_runs_remaining", 0) <= 0:
        raise RateLimitedError("已達試跑次數上限，仍可提交作答")

    # 沙箱不可用時降級為「接受提交但不執行」，絕不改以未隔離方式執行（憲章原則 VI）
    if not await sandbox.health_check():
        raise ServiceUnavailableError("程式碼執行環境目前不可用，仍可直接提交作答")

    result = await sandbox.run(ExecutionRequest(code=code, language=language, stdin=stdin))

    # 執行紀錄與試跑計數於同一函式內完成（FR-032、FR-048）
    recorded = store.rpc(
        "record_trial_run",
        {
            "p_token": token,
            "p_execution": result.model_dump(mode="json") | {"language": str(language)},
            "p_max_trial_runs": settings.max_trial_runs,
        },
    )
    if not recorded.get("ok"):
        _raise_for(recorded.get("reason"))
    return result


@router.post("/session/{token}/chat")
async def chat(
    token: str,
    message: str = Body(..., embed=True),
    store: DataStore = Depends(get_candidate_store),
    settings: Settings = Depends(get_settings),
    ai: AiProvider = Depends(get_ai_provider),
) -> dict[str, Any]:
    """向 AI 助教提問（FR-049～FR-052）。

    AI 不可用時回傳 503——作答、試跑與提交**不得**受影響（FR-052）。
    """
    session = _load_session(store, token, settings)
    snapshot = session.get("question") or {}

    # 助教需要完整題目（含隱藏測資）以判斷引導方向，但不得洩漏（contracts/ai-provider.md）
    question = Question(
        title=snapshot.get("title") or "（題目準備中）",
        difficulty="MEDIUM",
        language=snapshot.get("language"),
        description=snapshot.get("description") or "",
        constraints=snapshot.get("constraints"),
    )
    history = [ChatMessage.model_validate(item) for item in session.get("chat_history") or []]

    try:
        reply = await ai.chat_assist(
            ChatAssistRequest(question=question, history=history, message=message)
        )
    except AiUnavailableError as exc:
        raise ServiceUnavailableError("AI 助教目前不可用，作答與提交不受影響") from exc

    # 問答一律附加至 ai_chat_history（FR-051）
    appended = store.rpc(
        "append_chat_message",
        {"p_token": token, "p_role": "candidate", "p_content": message},
    )
    if not appended.get("ok"):
        _raise_for(appended.get("reason"))
    store.rpc(
        "append_chat_message",
        {
            "p_token": token,
            "p_role": "assistant",
            "p_content": reply.reply,
            "p_guardrail": reply.guardrail_triggered,
        },
    )
    return {"reply": reply.reply, "guardrail_triggered": reply.guardrail_triggered}


@router.post("/session/{token}/submit")
async def submit(
    token: str,
    background: BackgroundTasks,
    answer: str = Body(...),
    language: Language | None = Body(default=None),
    store: DataStore = Depends(get_candidate_store),
    settings: Settings = Depends(get_settings),
    sandbox: SandboxRunner = Depends(get_sandbox_runner),
    ai: AiProvider = Depends(get_ai_provider),
) -> dict[str, Any]:
    _load_session(store, token, settings)

    result = store.rpc(
        "submit_answer",
        {
            "p_token": token,
            "p_answer": answer,
            "p_language": str(language) if language else None,
        },
    )
    if not result.get("ok"):
        _raise_for(result.get("reason"))

    # 提交後自動觸發評測，無需人工操作（FR-053）。
    # 評測失敗不得阻擋提交流程（FR-059），因此以背景任務執行（research.md R-006）。
    evaluation = EvaluationService(store, sandbox, ai)
    background.add_task(evaluation.evaluate, token)

    return {"submitted_at": result.get("submitted_at")}
