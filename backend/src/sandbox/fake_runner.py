"""FakeSandboxRunner（測試替身）。

用於預設離線套件。以預先登錄的 `(code, language) → ExecutionResult` 對應表
回傳結果，並支援模擬 `health_check()` 為 False 以驗證降級路徑（FR-047）。

**不得**在替身中實作任何真實執行邏輯（contracts/sandbox-runner.md）。
"""

from __future__ import annotations

from backend.src.models.question import Language
from backend.src.models.report import ExecutionResult, TerminationReason
from backend.src.sandbox.runner import ExecutionRequest, unavailable_result


class FakeSandboxRunner:
    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self.calls: list[ExecutionRequest] = []
        self._registered: dict[tuple[str, str], ExecutionResult] = {}
        self._by_stdin: dict[tuple[str, str], ExecutionResult] = {}
        self.default_result = ExecutionResult(
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=5,
            termination_reason=TerminationReason.COMPLETED,
        )

    def register(self, code: str, language: Language, result: ExecutionResult) -> None:
        self._registered[(code, str(language))] = result

    def register_for_stdin(self, stdin: str, language: Language, result: ExecutionResult) -> None:
        """依標準輸入登錄結果，供測資逐項驗證的測試使用。"""
        self._by_stdin[(stdin, str(language))] = result

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls.append(request)
        if not self.healthy:
            # 契約 1：絕不拋出例外；不可用一律以 termination_reason 表達
            return unavailable_result()
        keyed = self._by_stdin.get((request.stdin, str(request.language)))
        if keyed is not None:
            return keyed
        return self._registered.get((request.code, str(request.language)), self.default_result)

    async def health_check(self) -> bool:
        return self.healthy
