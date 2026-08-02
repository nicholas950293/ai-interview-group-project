"""FakeAiProvider（測試替身）。

行為要求見 contracts/ai-provider.md：

- `generate_question` 回傳含 2 組測資的固定題目
- `chat_assist` 可設定為觸發或不觸發 guardrail（SC-013 相關測試）
- `evaluate` 依傳入的 `test_results.pass_ratio` 計算 `correctness.score`，
  其餘三維度回傳固定值——使「正確性與測資一致」的契約可被驗證
- 三個方法皆可設定為拋出 `AiUnavailableError`，供降級路徑測試

**不得**在替身中呼叫任何外部服務。
"""

from __future__ import annotations

from backend.src.ai.provider import (
    AiGenerationError,
    AiUnavailableError,
    ChatAssistRequest,
    ChatAssistResult,
    EvaluateRequest,
    EvaluationResult,
    GenerateQuestionRequest,
)
from backend.src.models.question import DeptType, Question, QuestionSource, TestCase
from backend.src.models.report import Dimension

FAKE_MODEL_ID = "fake-model-offline"

# 索取完整解答的意圖偵測（與 gemini_provider 共用同一組判準）
SOLUTION_REQUEST_MARKERS = (
    "完整解答",
    "完整答案",
    "直接給我",
    "幫我寫完",
    "可執行的完整",
    "full solution",
    "give me the code",
    "write the whole",
)


class FakeAiProvider:
    def __init__(self) -> None:
        self.unavailable_for: set[str] = set()
        self.force_guardrail: bool | None = None
        # 用於驗證「AI 生成缺測資時必須視為失敗」的路徑
        self.generate_without_test_cases = False
        self.generate_calls: list[GenerateQuestionRequest] = []
        self.chat_calls: list[ChatAssistRequest] = []
        self.evaluate_calls: list[EvaluateRequest] = []

    def set_unavailable(self, *methods: str) -> None:
        self.unavailable_for.update(methods)

    def _guard(self, method: str) -> None:
        if method in self.unavailable_for:
            raise AiUnavailableError(f"AI 服務不可用（測試替身設定：{method}）")

    async def generate_question(self, req: GenerateQuestionRequest) -> Question:
        self._guard("generate_question")
        self.generate_calls.append(req)

        cases = (
            []
            if self.generate_without_test_cases
            else [
                TestCase(
                    name="基本案例",
                    stdin="3 5\n",
                    expected_stdout="8\n",
                    is_hidden=False,
                ),
                TestCase(
                    name="隱藏邊界",
                    stdin="0 0\n",
                    expected_stdout="0\n",
                    is_hidden=True,
                ),
            ]
        )
        question = Question(
            source=QuestionSource.AI_GENERATED,
            title=f"合成題目：{'、'.join(req.skills) or '未指定能力指標'}",
            category="合成分類",
            difficulty=req.difficulty,
            language=req.language,
            description="這是離線測試替身產生的題目描述。",
            constraints="這是離線測試替身產生的限制條件。",
            test_cases=cases,
        )
        # 硬性要求：工程類缺測資即視為生成失敗，不得回傳缺測資的題目
        if req.dept_type is DeptType.ENGINEERING and not question.test_cases:
            raise AiGenerationError("生成的工程類題目缺少測試案例")
        return question

    async def chat_assist(self, req: ChatAssistRequest) -> ChatAssistResult:
        self._guard("chat_assist")
        self.chat_calls.append(req)

        triggered = (
            self.force_guardrail
            if self.force_guardrail is not None
            else any(marker in req.message.lower() for marker in SOLUTION_REQUEST_MARKERS)
        )
        if triggered:
            # guardrail 觸發時仍須回傳有幫助的引導，不得僅回傳拒絕訊息
            reply = (
                "我不會直接提供可提交的完整解答，但可以拆解思路："
                "先確認輸入格式與邊界條件，再想清楚資料結構的選擇，"
                "最後才處理效能。你目前卡在哪一步？"
            )
        else:
            reply = "先從題目的輸入輸出關係著手，想想哪一種資料結構能讓查詢維持在常數時間。"
        return ChatAssistResult(reply=reply, guardrail_triggered=triggered)

    async def evaluate(self, req: EvaluateRequest) -> EvaluationResult:
        self._guard("evaluate")
        self.evaluate_calls.append(req)

        if req.test_results is not None:
            # 正確性以測資通過比例為客觀依據（FR-054）
            correctness = Dimension(
                score=round(req.test_results.pass_ratio * 100),
                comment=(f"通過 {req.test_results.passed}/{req.test_results.total} 個測試案例。"),
            )
        else:
            correctness = Dimension(
                score=0,
                comment="沙箱不可用，本次未經測資驗證，此維度不具客觀依據。",
            )

        return EvaluationResult(
            dimensions={
                "correctness": correctness,
                "maintainability": Dimension(score=65, comment="命名尚可，錯誤處理不足。"),
                "performance": Dimension(score=70, comment="時間複雜度符合題目要求。"),
                "security": Dimension(score=60, comment="未驗證輸入長度。"),
            },
            model_id=FAKE_MODEL_ID,
        )
