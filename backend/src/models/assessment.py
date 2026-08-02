"""考核、狀態與應徵者工作階段（FR-009、FR-029、FR-073）。

對應 data-model.md §4 與 contracts/openapi.yaml 的 AssessmentSummary*／CandidateSession。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.src.models.question import DeptType, Language


class AssessmentStatus(StrEnum):
    PENDING_ASSIGN = "PENDING_ASSIGN"
    PENDING_CANDIDATE = "PENDING_CANDIDATE"
    COMPLETED_AWAITING_REVIEW = "COMPLETED_AWAITING_REVIEW"
    DECIDED = "DECIDED"
    EXPIRED = "EXPIRED"


class EmailStatus(StrEnum):
    NOT_SENT = "NOT_SENT"
    SENT = "SENT"
    FAILED = "FAILED"


class ChatRole(StrEnum):
    CANDIDATE = "candidate"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: ChatRole
    content: str
    created_at: datetime | None = None
    guardrail_triggered: bool | None = None


class CreateAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=150)
    phone: str | None = Field(default=None, max_length=50)
    job_title: str = Field(min_length=1, max_length=100)
    dept_id: str = Field(min_length=1, max_length=50)
    # 同一 Email 與職缺已有進行中的考核時，須明確為 true 才建立（FR-009 邊界情況）
    confirm_duplicate: bool = False

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, value: str) -> str:
        # 僅做最小形式檢查；真正的可達性由寄送結果決定（FR-071、FR-072），
        # 不為此引入額外的驗證相依（憲章原則 III）。
        local, _, domain = value.partition("@")
        if not local or not domain or "." not in domain or any(c.isspace() for c in value):
            raise ValueError("Email 格式不正確")
        return value.strip()


class AssessmentCreated(BaseModel):
    id: str
    token: str
    token_expires_at: datetime
    status: AssessmentStatus
    assigned_manager: str | None = None
    candidate_url: str | None = None


class AssessmentSummaryHR(BaseModel):
    """HR 可見欄位。

    刻意不含 ai_report、internal_comment、candidate_answer 與 ai_chat_history
    ——FR-008 要求 HR 的查詢結果本身即不包含受限欄位。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    email: str
    job_title: str
    dept_id: str
    assigned_manager: str | None = None
    status: AssessmentStatus
    final_decision: str | None = None
    email_status: EmailStatus = EmailStatus.NOT_SENT
    token_expires_at: datetime | None = None
    created_at: datetime | None = None


class AssessmentSummaryManager(AssessmentSummaryHR):
    has_report: bool = False


class ExecutionRecordView(BaseModel):
    """主管審閱時看到的單次沙箱執行紀錄（FR-044、FR-048、FR-060）。"""

    model_config = ConfigDict(extra="ignore")

    trigger: str
    language: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    peak_memory_kb: int | None = None
    termination_reason: str
    test_results: dict | None = None
    created_at: datetime | None = None


class AssessmentDetail(BaseModel):
    """主管專用的完整審閱內容（FR-060）。

    HR 呼叫此端點必須被拒絕（contracts/openapi.yaml）——本模型含
    candidate_answer、ai_chat_history、ai_report 與 internal_comment，
    全部是 FR-007／FR-008 對 HR 封閉的內容。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    email: str
    job_title: str
    dept_id: str
    status: AssessmentStatus
    question_snapshot: dict | None = None
    code_language: Language | None = None
    candidate_answer: str | None = None
    ai_chat_history: list[ChatMessage] = Field(default_factory=list)
    executions: list[ExecutionRecordView] = Field(default_factory=list)
    ai_report: dict | None = None
    decisions: list[dict] = Field(default_factory=list)


class SampleCase(BaseModel):
    """應徵者可見的範例測資。刻意不含 is_hidden 與 timeout_seconds。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    stdin: str
    expected_stdout: str


class CandidateQuestion(BaseModel):
    """應徵者可見的題目內容。隱藏測資的 stdin 與 expected_stdout 必須被移除。"""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str
    constraints: str | None = None
    language: Language | None = None
    sample_cases: list[SampleCase] = Field(default_factory=list)


class CandidateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_title: str
    dept_type: DeptType
    status: AssessmentStatus
    token_expires_at: datetime
    question: CandidateQuestion | None = None
    code_language: Language | None = None
    trial_runs_remaining: int = 0
    submitted_at: datetime | None = None
    chat_history: list[ChatMessage] = Field(default_factory=list)
