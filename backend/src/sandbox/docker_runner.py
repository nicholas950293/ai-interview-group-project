"""DockerSandboxRunner——系統中唯一執行不受信任程式碼的實作。

憲章原則 VI 標示為不可妥協。contracts/sandbox-runner.md 的 12 項容器參數
在 `_host_config()` 中逐一對應，每一項都有安全套件的對應斷言。

## 幾個關鍵的實作決定

**原始碼以引數傳入，不掛載宿主目錄。** `run.sh` 接收 base64 編碼的原始碼與
標準輸入，寫入 tmpfs 的 `/work`。因此容器完全不需要接觸宿主檔案系統——
連唯讀的來源目錄都不需要。

**牆鐘逾時由宿主端計時器強制。** 計時器到期即 `kill`，不依賴被執行程式碼的
自我約束（契約 3）。容器內另以 `ulimit -t` 施加 CPU 時間上限，兩者互補：
前者防止掛住，後者防止純 CPU 消耗。

**輸出以串流讀取。** 達上限即停止讀取並中止執行，不先緩衝完整輸出再截斷
（契約 4）——否則 `max_output_bytes` 無法防止宿主記憶體耗盡。

**容器以 finally 明確移除，而非依賴 `--rm`。** 契約表列的是 `--rm`；
改用明確移除是**更強**的保證：`--rm` 在守護程序異常時可能不生效，
而 finally 中的 `remove(force=True)` 在任何路徑都會執行。FR-042
要求的是「執行結束後必須銷毀」，此作法完全滿足，且讓我們能在移除前
讀取 `State.OOMKilled` 以正確判定 MEMORY_LIMIT。

**絕不拋出例外給呼叫端**（契約 1）：所有失敗情境皆以 `termination_reason`
表達。沙箱不可用時回傳 `SANDBOX_UNAVAILABLE`——呼叫端據此降級為
「接受提交但不執行」，絕不改以未隔離的方式執行。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import threading
import time
from typing import Any

from backend.src.config import SandboxSettings
from backend.src.models.question import Language
from backend.src.models.report import ExecutionResult, TerminationReason
from backend.src.sandbox.runner import ExecutionRequest, ResourceLimits, unavailable_result

# run.sh 以此退出碼表示編譯／語法錯誤（FR-045）
COMPILE_ERROR_EXIT_CODE = 90

# 原始碼與輸入以命令列引數傳入，需留在 ARG_MAX 之內
MAX_SOURCE_BYTES = 262_144

CONTAINER_LABEL = "ai-recruitment-sandbox"

# 語言版本必須明確固定並對應徵者顯示（FR-037）。與 sandbox/*/Dockerfile 一致。
LANGUAGE_VERSIONS = {
    Language.PYTHON: "Python 3.12.8",
    Language.JAVASCRIPT: "Node.js 22.12.0",
    Language.GO: "Go 1.23.4",
    Language.JAVA: "OpenJDK 21.0.5",
    Language.CPP: "GCC 13.2 (C++20)",
}

# fork 失敗在各語言執行時期的訊息。pids cgroup 觸發時程序看到的是配置失敗，
# 而非一個可直接查詢的旗標，因此以訊息特徵判定（並在測試中固定行為）。
PIDS_LIMIT_MARKERS = (
    "Resource temporarily unavailable",
    "BlockingIOError",
    "Cannot allocate memory",
    "fork failed",
    "unable to create native thread",
)


class DockerSandboxRunner:
    def __init__(self, settings: SandboxSettings) -> None:
        self._settings = settings
        # 併發由呼叫端限制（FR-046）；介面本身不做排隊（契約 5）
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._client: Any = None

    # ────────────────────────── 對外介面 ──────────────────────────

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            async with self._semaphore:
                return await asyncio.to_thread(self._run_blocking, request)
        except Exception:  # noqa: BLE001 - 契約 1：絕不拋出例外給呼叫端
            return unavailable_result()

    async def health_check(self) -> bool:
        try:
            return await asyncio.to_thread(self._ping)
        except Exception:  # noqa: BLE001
            return False

    @property
    def waiting(self) -> bool:
        """是否有請求正在等候併發額度（FR-046 的等候狀態）。"""
        return self._semaphore.locked()

    def language_version(self, language: Language) -> str:
        return LANGUAGE_VERSIONS.get(Language(language), "")

    def image_for(self, language: Language) -> str:
        return f"{self._settings.image_prefix}{Language(language).value}"

    def list_leftover_containers(self) -> list[str]:
        """殘留容器清單。正常情況必為空——每次執行後容器都會被移除（FR-042）。"""
        client = self._connect()
        containers = client.containers.list(all=True, filters={"label": f"app={CONTAINER_LABEL}"})
        return [container.id for container in containers]

    # ────────────────────────── 內部實作 ──────────────────────────

    def _connect(self) -> Any:
        if self._client is None:
            import docker

            self._client = docker.from_env()
        return self._client

    def _ping(self) -> bool:
        client = self._connect()
        if not client.ping():
            return False
        # 映像檔未建置時沙箱同樣不可用——此時必須降級，而非在執行當下才失敗
        available = {tag for image in client.images.list() for tag in (image.tags or [])}
        for language in Language:
            image = self.image_for(language)
            if not any(tag == image or tag.startswith(f"{image}:") for tag in available):
                return False
        return True

    def _host_config(self, limits: ResourceLimits) -> dict[str, Any]:
        """contracts/sandbox-runner.md 的 12 項參數，逐一對應。"""
        config: dict[str, Any] = {
            "network_disabled": True,  # --network=none
            "read_only": True,  # --read-only
            "tmpfs": {"/work": f"rw,size={64}m,mode=1777"},  # --tmpfs
            "mem_limit": f"{limits.memory_mb}m",  # --memory
            "memswap_limit": f"{limits.memory_mb}m",  # --memory-swap（等同禁用 swap）
            "nano_cpus": 1_000_000_000,  # --cpus=1.0
            "pids_limit": limits.max_processes,  # --pids-limit
            "cap_drop": ["ALL"],  # --cap-drop=ALL
            "security_opt": ["no-new-privileges"],  # --security-opt
            "user": "65534:65534",  # --user（非 root 固定 UID）
            "labels": {"app": CONTAINER_LABEL},
        }
        if self._settings.runtime:
            config["runtime"] = self._settings.runtime  # --runtime=runsc（若可用）
        return config

    def _run_blocking(self, request: ExecutionRequest) -> ExecutionResult:
        limits = request.limits.clamped()

        source = request.code.encode("utf-8")
        stdin = request.stdin.encode("utf-8")
        if len(source) > MAX_SOURCE_BYTES or len(stdin) > MAX_SOURCE_BYTES:
            return ExecutionResult(
                stderr=f"原始碼或輸入超過 {MAX_SOURCE_BYTES // 1024} KB 上限",
                exit_code=None,
                termination_reason=TerminationReason.COMPILE_ERROR,
            )

        client = self._connect()
        container = client.containers.create(
            self.image_for(request.language),
            command=[
                base64.b64encode(source).decode("ascii"),
                base64.b64encode(stdin).decode("ascii"),
            ],
            **self._host_config(limits),
        )

        started = time.monotonic()
        timed_out = threading.Event()

        def _enforce_wall_clock() -> None:
            # 契約 3：牆鐘逾時由宿主端計時器強制，不依賴容器內部的自我約束
            timed_out.set()
            # 容器可能已自行結束
            with contextlib.suppress(Exception):
                container.kill()

        timer = threading.Timer(limits.wall_clock_seconds, _enforce_wall_clock)
        timer.start()

        stdout = bytearray()
        stderr = bytearray()
        truncated = False

        try:
            container.start()
            stream = container.attach(stdout=True, stderr=True, stream=True, demux=True, logs=True)
            for out_chunk, err_chunk in stream:
                if out_chunk:
                    stdout += out_chunk
                if err_chunk:
                    stderr += err_chunk
                # 契約 4：達上限即停止讀取並中止執行
                if len(stdout) + len(stderr) > limits.max_output_bytes:
                    truncated = True
                    with contextlib.suppress(Exception):
                        container.kill()
                    break

            state = self._wait_for_state(container, limits)
            duration_ms = int((time.monotonic() - started) * 1000)

            return self._to_result(
                stdout=bytes(stdout),
                stderr=bytes(stderr),
                state=state,
                duration_ms=duration_ms,
                limits=limits,
                timed_out=timed_out.is_set(),
                output_exceeded=truncated,
            )
        finally:
            timer.cancel()
            # 用後即棄（FR-042）：任何路徑都必須銷毀容器
            with contextlib.suppress(Exception):
                container.remove(force=True)

    @staticmethod
    def _wait_for_state(container: Any, limits: ResourceLimits) -> dict[str, Any]:
        # 已被 kill 或守護程序無回應時，直接讀取最後的狀態
        with contextlib.suppress(Exception):
            container.wait(timeout=limits.wall_clock_seconds + 5)
        try:
            container.reload()
            return dict(container.attrs.get("State") or {})
        except Exception:  # noqa: BLE001
            return {}

    def _to_result(
        self,
        *,
        stdout: bytes,
        stderr: bytes,
        state: dict[str, Any],
        duration_ms: int,
        limits: ResourceLimits,
        timed_out: bool,
        output_exceeded: bool,
    ) -> ExecutionResult:
        exit_code = state.get("ExitCode")
        oom_killed = bool(state.get("OOMKilled"))

        decoded_out = stdout[: limits.max_output_bytes].decode("utf-8", errors="replace")
        decoded_err = stderr[: limits.max_output_bytes].decode("utf-8", errors="replace")
        truncated = output_exceeded or len(stdout) > limits.max_output_bytes

        reason = TerminationReason.COMPLETED
        if oom_killed:
            reason = TerminationReason.MEMORY_LIMIT
        elif output_exceeded:
            reason = TerminationReason.OUTPUT_LIMIT
        elif timed_out:
            reason = TerminationReason.TIMEOUT
        elif exit_code == COMPILE_ERROR_EXIT_CODE:
            reason = TerminationReason.COMPILE_ERROR
        elif exit_code not in (0, None) and any(
            marker in decoded_err for marker in PIDS_LIMIT_MARKERS
        ):
            reason = TerminationReason.PIDS_LIMIT
        elif exit_code == 137 and not oom_killed:
            # SIGKILL 但非 OOM：CPU 上限（ulimit -t）或 pids 耗盡的常見結果
            reason = TerminationReason.TIMEOUT
        elif exit_code == 152:
            # 128 + SIGXCPU：RLIMIT_CPU 觸發
            reason = TerminationReason.TIMEOUT

        if reason is not TerminationReason.COMPLETED:
            exit_code = None if reason is not TerminationReason.COMPILE_ERROR else exit_code

        return ExecutionResult(
            stdout=decoded_out,
            stderr=decoded_err,
            exit_code=exit_code,
            duration_ms=duration_ms,
            peak_memory_kb=None,
            termination_reason=reason,
            truncated=truncated,
        )
