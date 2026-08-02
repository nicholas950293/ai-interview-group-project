"""題目與測試案例（FR-020～FR-022、FR-026）。

對應 contracts/openapi.yaml 的 Question 與 TestCase schema，
以及 data-model.md §3 的 test_cases JSONB 結構。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 沙箱單案例逾時不得超過沙箱上限（contracts/sandbox-runner.md）
MAX_CASE_TIMEOUT_SECONDS = 10


class Language(StrEnum):
    JAVASCRIPT = "javascript"
    PYTHON = "python"
    GO = "go"
    JAVA = "java"
    CPP = "cpp"


class Difficulty(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class DeptType(StrEnum):
    ENGINEERING = "ENGINEERING"
    NON_ENGINEERING = "NON_ENGINEERING"


class QuestionSource(StrEnum):
    BANK = "BANK"
    AI_GENERATED = "AI_GENERATED"


class MissingTestCasesError(ValueError):
    """工程類題目缺少可執行的測試案例（FR-022、FR-026）。"""


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    stdin: str
    expected_stdout: str
    is_hidden: bool = False
    timeout_seconds: int = Field(default=MAX_CASE_TIMEOUT_SECONDS, ge=1)

    @field_validator("timeout_seconds")
    @classmethod
    def _cap_timeout(cls, value: int) -> int:
        # 實作不得接受高於沙箱上限的值（contracts/sandbox-runner.md）
        return min(value, MAX_CASE_TIMEOUT_SECONDS)

    def matches(self, actual_stdout: str) -> bool:
        """比對時去除尾端空白（data-model.md §3）。"""
        return actual_stdout.rstrip() == self.expected_stdout.rstrip()


class Question(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    source: QuestionSource | None = None
    title: str = Field(min_length=1, max_length=200)
    category: str | None = None
    difficulty: Difficulty
    language: Language | None = None
    description: str = Field(min_length=1)
    constraints: str | None = None
    test_cases: list[TestCase] = Field(default_factory=list)

    @property
    def visible_cases(self) -> list[TestCase]:
        """應徵者可見的範例案例。隱藏測資僅用於評測，不得外流。"""
        return [case for case in self.test_cases if not case.is_hidden]

    def require_test_cases_for(self, dept_type: DeptType) -> None:
        """工程類題目必須至少含 1 組測資，且每組 stdin 與 expected_stdout 皆非空。

        缺測資時拋出例外而非回傳布林值——contracts/ai-provider.md 要求
        「不得回傳缺測資的題目，否則錯誤會延後到指派階段才被發現」。
        """
        if dept_type is not DeptType.ENGINEERING:
            return
        if not self.test_cases:
            raise MissingTestCasesError("工程類題目必須包含至少一組可執行的測試案例")
        for case in self.test_cases:
            if not case.stdin.strip() and not case.expected_stdout.strip():
                raise MissingTestCasesError(
                    f"測試案例「{case.name}」的輸入與預期輸出皆為空，無法作為評測依據"
                )
