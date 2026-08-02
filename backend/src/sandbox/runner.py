"""SandboxRunner 介面（契約：contracts/sandbox-runner.md）。

這是系統中唯一執行不受信任程式碼的位置。憲章原則 VI 標示為不可妥協。

行為契約（所有實作皆須滿足）：

1. **絕不拋出例外給呼叫端**。所有失敗情境皆以 `termination_reason` 表達。
2. **絕不回傳部分結果後才失敗**。回傳值必為完整且一致的 `ExecutionResult`。
3. **牆鐘逾時由呼叫端外部計時強制**，不依賴被執行程式碼的自我約束。
4. **輸出以串流讀取**，達上限即停止讀取並中止執行。
5. **併發由呼叫端以 Semaphore 限制**；介面本身不做排隊。
6. `health_check()` 為 False 時，呼叫端必須降級為「接受提交但不執行」，
   **不得**改以未隔離的方式執行。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from backend.src.models.question import Language
from backend.src.models.report import ExecutionResult, TerminationReason

# contracts/sandbox-runner.md：實作不得接受高於下列預設的值。
# 放寬任一上限須依憲章原則 VI 於 plan.md 記錄並附風險評估。
MAX_CPU_SECONDS = 10
MAX_MEMORY_MB = 512
MAX_WALL_CLOCK_SECONDS = 30
MAX_PROCESSES = 64
MAX_OUTPUT_BYTES = 1_048_576


@dataclass(frozen=True)
class ResourceLimits:
    cpu_seconds: int = MAX_CPU_SECONDS
    memory_mb: int = MAX_MEMORY_MB
    wall_clock_seconds: int = MAX_WALL_CLOCK_SECONDS
    max_processes: int = MAX_PROCESSES
    max_output_bytes: int = MAX_OUTPUT_BYTES

    def clamped(self) -> ResourceLimits:
        """將任何超出契約上限的值夾回上限。

        以「靜默夾回」而非「拋出例外」處理，是因為呼叫端傳入過大的值通常是
        設定錯誤，而在安全方向上失敗（用更嚴的限制）永遠比拒絕執行更合適。
        """
        return replace(
            self,
            cpu_seconds=min(self.cpu_seconds, MAX_CPU_SECONDS),
            memory_mb=min(self.memory_mb, MAX_MEMORY_MB),
            wall_clock_seconds=min(self.wall_clock_seconds, MAX_WALL_CLOCK_SECONDS),
            max_processes=min(self.max_processes, MAX_PROCESSES),
            max_output_bytes=min(self.max_output_bytes, MAX_OUTPUT_BYTES),
        )


@dataclass(frozen=True)
class ExecutionRequest:
    code: str  # 應徵者提交的原始碼。不受信任。
    language: Language
    stdin: str = ""
    limits: ResourceLimits = ResourceLimits()


@runtime_checkable
class SandboxRunner(Protocol):
    async def run(self, request: ExecutionRequest) -> ExecutionResult: ...

    async def health_check(self) -> bool: ...


def unavailable_result(message: str = "沙箱目前不可用，本次未執行程式碼") -> ExecutionResult:
    """沙箱不可用時的標準回傳（FR-047）。

    降級的定義是「接受提交但不執行」——絕不得改以未隔離的方式執行程式碼
    （憲章原則 VI）。
    """
    return ExecutionResult(
        stdout="",
        stderr=message,
        exit_code=None,
        duration_ms=0,
        termination_reason=TerminationReason.SANDBOX_UNAVAILABLE,
        truncated=False,
    )
