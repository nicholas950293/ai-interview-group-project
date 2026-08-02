"""AI 評測報告與沙箱執行結果（FR-044、FR-054～FR-059）。

**刻意不提供總分欄位**：憲章原則 V 與 FR-057 禁止系統自動產生加權總分、
綜合評價或錄取傾向。此處不定義對應欄位，使違規在型別層即無法表達——
若日後有人試圖加總四個維度，沒有地方可以放結果。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# FR-058：報告必須在所有呈現位置明確標示為 AI 輔助建議
ADVISORY_NOTICE = "本報告由 AI 產出，僅供參考。最終決定權屬於主管。"

# FR-056：評分尺度一致且明確定義
SCORE_MIN = 0
SCORE_MAX = 100

DIMENSION_NAMES = ("correctness", "maintainability", "performance", "security")


class TerminationReason(StrEnum):
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"
    MEMORY_LIMIT = "MEMORY_LIMIT"
    PIDS_LIMIT = "PIDS_LIMIT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    COMPILE_ERROR = "COMPILE_ERROR"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"


class ExecutionTrigger(StrEnum):
    TRIAL_RUN = "TRIAL_RUN"
    EVALUATION = "EVALUATION"


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ExecutionResult(BaseModel):
    """一次沙箱執行的完整結果。

    contracts/sandbox-runner.md 行為契約 2：絕不回傳部分結果後才失敗——
    回傳值必為完整且一致的 ExecutionResult。
    """

    model_config = ConfigDict(extra="forbid")

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    peak_memory_kb: int | None = None
    termination_reason: TerminationReason = TerminationReason.COMPLETED
    truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return self.termination_reason is TerminationReason.COMPLETED and self.exit_code == 0


class TestCaseResult(BaseModel):
    """單一測試案例的結果。

    刻意不含 actual_stdout——避免隱藏測資的預期輸出經由紀錄外洩
    （data-model.md §5）。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    duration_ms: int = 0
    termination_reason: TerminationReason = TerminationReason.COMPLETED


class TestResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = 0
    passed: int = 0
    pass_ratio: float = 0.0
    cases: list[TestCaseResult] = Field(default_factory=list)

    @classmethod
    def from_cases(cls, cases: list[TestCaseResult]) -> TestResults:
        passed = sum(1 for case in cases if case.passed)
        total = len(cases)
        return cls(
            total=total,
            passed=passed,
            pass_ratio=round(passed / total, 3) if total else 0.0,
            cases=cases,
        )


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=SCORE_MIN, le=SCORE_MAX)
    comment: str


class AiReport(BaseModel):
    """AI 評測報告。

    型別中不存在 total_score、overall_comment、recommendation 之類的欄位，
    且不得新增——見模組 docstring 與 FR-057。
    """

    model_config = ConfigDict(extra="forbid")

    attempt_no: int = 1
    status: ReportStatus = ReportStatus.PENDING
    test_pass_ratio: float | None = None
    model_id: str | None = None
    error_message: str | None = None
    dimensions: dict[str, Dimension] | None = None
    advisory_notice: str = ADVISORY_NOTICE
    created_at: datetime | None = None

    def has_all_dimensions(self) -> bool:
        return bool(self.dimensions) and all(name in self.dimensions for name in DIMENSION_NAMES)
