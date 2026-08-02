"""AiProvider 介面（契約：contracts/ai-provider.md）。

AI 有三種用途：出題、答題助教、自動評測。三者共用同一介面，
以便測試以單一替身取代（憲章原則 II 要求測試套件離線可執行）。

模型 ID 由環境變數 `GEMINI_MODEL` 提供，不得寫死於程式碼（R-005）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from backend.src.models.assessment import ChatMessage
from backend.src.models.question import DeptType, Difficulty, Language, Question
from backend.src.models.report import Dimension, ExecutionResult, TestResults


class AiUnavailableError(RuntimeError):
    """AI 服務不可用或回應格式不符。API 層轉為 HTTP 503。"""


class AiGenerationError(AiUnavailableError):
    """生成結果不符硬性要求（例如工程類題目缺測資）。

    繼承 AiUnavailableError，使 API 層的 503 處理不需區分兩者；
    但型別上仍可分辨「服務掛了」與「服務回了不能用的東西」。
    """


@dataclass(frozen=True)
class GenerateQuestionRequest:
    skills: list[str]
    difficulty: Difficulty
    language: Language
    dept_type: DeptType


@dataclass(frozen=True)
class ChatAssistRequest:
    question: Question  # 含隱藏測資，供 AI 判斷但不得洩漏
    history: list[ChatMessage] = field(default_factory=list)
    message: str = ""
    current_code: str | None = None


@dataclass(frozen=True)
class ChatAssistResult:
    reply: str
    guardrail_triggered: bool = False


@dataclass(frozen=True)
class EvaluateRequest:
    question: Question
    answer: str
    language: Language | None = None
    execution: ExecutionResult | None = None
    test_results: TestResults | None = None
    chat_history: list[ChatMessage] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationResult:
    """評測結果。

    **刻意不提供**加權總分、綜合評價或錄取傾向欄位——FR-057 與憲章原則 V
    禁止系統自動產生綜合判斷，介面型別本身不提供對應欄位，
    使違規在型別層即無法表達。
    """

    dimensions: dict[str, Dimension]
    model_id: str


@runtime_checkable
class AiProvider(Protocol):
    async def generate_question(self, req: GenerateQuestionRequest) -> Question: ...

    async def chat_assist(self, req: ChatAssistRequest) -> ChatAssistResult: ...

    async def evaluate(self, req: EvaluateRequest) -> EvaluationResult: ...
