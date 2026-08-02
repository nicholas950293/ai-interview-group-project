"""提交後的自動評測（FR-053～FR-059；research.md R-006）。

流程：以題目測試案例逐項在沙箱中驗證 → 將通過比例交給 AI 作為正確性維度的
客觀依據 → 寫入 `ai_reports`。

## 兩個不可妥協的性質

**評測失敗不得阻擋提交（FR-059）。** 因此本服務以背景任務執行，且所有
失敗路徑都以「寫入 status=FAILED 的報告」收尾，而非拋出例外。應徵者無法
重來，失敗的原因也與他無關——把提交弄丟是不可接受的失敗模式。

**沙箱不可用時不得改以未隔離的方式執行（憲章原則 VI）。** 此時
`test_results` 為 None，評測仍會產出報告，但正確性維度必須明確標示
未經測資驗證（contracts/ai-provider.md）。
"""

from __future__ import annotations

from typing import Any

from backend.src.ai.provider import AiProvider, AiUnavailableError, EvaluateRequest
from backend.src.models.assessment import ChatMessage
from backend.src.models.question import Language, Question
from backend.src.models.report import (
    ExecutionResult,
    TerminationReason,
    TestCaseResult,
    TestResults,
)
from backend.src.repositories.base import DataStore
from backend.src.sandbox.runner import (
    ExecutionRequest,
    ResourceLimits,
    SandboxRunner,
    unavailable_result,
)


class EvaluationService:
    def __init__(self, store: DataStore, sandbox: SandboxRunner, ai: AiProvider) -> None:
        self._store = store
        self._sandbox = sandbox
        self._ai = ai

    async def evaluate(self, token: str) -> None:
        """執行一次評測。以 token 為鍵，與應徵者路徑使用同一組函式（R-002）。"""
        started = self._store.rpc("record_evaluation_start", {"p_token": token})
        if not started or not started.get("ok"):
            return

        attempt_no = started["attempt_no"]
        answer = started.get("answer") or ""
        language = started.get("language")
        question = self._question_from(started.get("question_snapshot"))

        execution, test_results = await self._verify_with_test_cases(question, answer, language)

        try:
            evaluation = await self._ai.evaluate(
                EvaluateRequest(
                    question=question or self._placeholder_question(),
                    answer=answer,
                    language=Language(language) if language else None,
                    execution=execution,
                    test_results=test_results,
                    chat_history=[
                        ChatMessage.model_validate(item)
                        for item in started.get("chat_history") or []
                    ],
                )
            )
        except AiUnavailableError as exc:
            # 失敗留下紀錄而非消失，滿足 FR-059 的可重試要求
            self._record(
                token,
                attempt_no,
                status="FAILED",
                error_message=str(exc) or "AI 評測服務不可用",
                execution=execution,
                test_results=test_results,
            )
            return

        self._record(
            token,
            attempt_no,
            status="SUCCESS",
            dimensions={
                name: dimension.model_dump() for name, dimension in evaluation.dimensions.items()
            },
            test_pass_ratio=test_results.pass_ratio if test_results else None,
            model_id=evaluation.model_id,
            execution=execution,
            test_results=test_results,
        )

    # ────────────────────────── 測資驗證 ──────────────────────────

    async def _verify_with_test_cases(
        self, question: Question | None, answer: str, language: str | None
    ) -> tuple[ExecutionResult | None, TestResults | None]:
        """逐一以沙箱執行測試案例（FR-054）。

        刻意**不保存** actual_stdout——隱藏測資的預期輸出若經由執行紀錄外洩，
        後續應徵者即可反推答案（data-model.md §5）。
        """
        if question is None or not question.test_cases or not language:
            return None, None

        if not await self._sandbox.health_check():
            # 接受提交但不執行（FR-047）
            return unavailable_result(), None

        cases: list[TestCaseResult] = []
        last: ExecutionResult | None = None

        for case in question.test_cases:
            result = await self._sandbox.run(
                ExecutionRequest(
                    code=answer,
                    language=Language(language),
                    stdin=case.stdin,
                    limits=ResourceLimits(wall_clock_seconds=case.timeout_seconds),
                )
            )
            last = result
            passed = (
                result.termination_reason is TerminationReason.COMPLETED
                and result.exit_code == 0
                and case.matches(result.stdout)
            )
            cases.append(
                TestCaseResult(
                    name=case.name,
                    passed=passed,
                    duration_ms=result.duration_ms,
                    termination_reason=result.termination_reason,
                )
            )

        return last, TestResults.from_cases(cases)

    # ────────────────────────── 寫入 ──────────────────────────

    def _record(
        self,
        token: str,
        attempt_no: int,
        *,
        status: str,
        dimensions: dict[str, Any] | None = None,
        test_pass_ratio: float | None = None,
        model_id: str | None = None,
        error_message: str | None = None,
        execution: ExecutionResult | None = None,
        test_results: TestResults | None = None,
    ) -> None:
        payload: dict[str, Any] | None = None
        if execution is not None:
            payload = execution.model_dump(mode="json")
            payload["test_results"] = test_results.model_dump(mode="json") if test_results else None

        self._store.rpc(
            "record_evaluation_result",
            {
                "p_token": token,
                "p_attempt_no": attempt_no,
                "p_status": status,
                "p_dimensions": dimensions,
                "p_test_pass_ratio": test_pass_ratio,
                "p_model_id": model_id,
                "p_error_message": error_message,
                "p_execution": payload,
            },
        )

    @staticmethod
    def _question_from(snapshot: dict[str, Any] | None) -> Question | None:
        if not snapshot:
            return None
        try:
            return Question.model_validate(snapshot)
        except Exception:  # noqa: BLE001 - 快照結構異常不得中斷評測流程
            return None

    @staticmethod
    def _placeholder_question() -> Question:
        return Question(
            title="（題目快照缺失）",
            difficulty="MEDIUM",
            description="此考核沒有可用的題目快照。",
        )
