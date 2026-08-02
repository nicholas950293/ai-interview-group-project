"""沙箱資源耗盡中止（FR-039、FR-040；憲章原則 VI）。

對應 contracts/sandbox-runner.md 的「資源耗盡中止」必測項目。
每一項都必須以明確的 `termination_reason` 回報，而不是以逾時或掛住表達。
"""

from __future__ import annotations

import time

import pytest

from backend.src.models.question import Language
from backend.src.models.report import TerminationReason
from backend.src.sandbox.runner import MAX_WALL_CLOCK_SECONDS, ResourceLimits

pytestmark = pytest.mark.security

INFINITE_LOOP = "while True:\n    pass\n"
MEMORY_HOG = "blob = bytearray(1024 * 1024 * 1024)\nprint(len(blob))\n"
FORK_BOMB = """
import os
while True:
    try:
        os.fork()
    except OSError:
        pass
"""
INFINITE_OUTPUT = """
import sys
line = "A" * 1024
while True:
    sys.stdout.write(line)
"""


async def test_infinite_loop_is_terminated_as_timeout(run):
    started = time.monotonic()
    result = await run(INFINITE_LOOP, Language.PYTHON, limits=ResourceLimits(wall_clock_seconds=10))
    elapsed = time.monotonic() - started

    assert result.termination_reason is TerminationReason.TIMEOUT
    # 中止耗時不得超過牆鐘上限 + 5 秒（contracts/sandbox-runner.md）
    assert elapsed < 10 + 5


async def test_memory_over_allocation_is_terminated(run):
    result = await run(MEMORY_HOG, Language.PYTHON)
    assert result.termination_reason is TerminationReason.MEMORY_LIMIT
    assert "1073741824" not in result.stdout


async def test_fork_bomb_hits_pids_limit_without_affecting_host(run):
    import os

    before = len(os.listdir("/proc")) if os.path.isdir("/proc") else None
    result = await run(FORK_BOMB, Language.PYTHON, limits=ResourceLimits(wall_clock_seconds=15))
    assert result.termination_reason in (
        TerminationReason.PIDS_LIMIT,
        TerminationReason.TIMEOUT,
    )
    if before is not None:
        after = len(os.listdir("/proc"))
        assert after < before * 2, "宿主程序數不得因沙箱內的 fork bomb 而暴增"


async def test_infinite_output_is_truncated(run):
    result = await run(
        INFINITE_OUTPUT, Language.PYTHON, limits=ResourceLimits(wall_clock_seconds=15)
    )
    assert result.termination_reason is TerminationReason.OUTPUT_LIMIT
    assert result.truncated is True
    # 輸出以串流讀取，達上限即停止——不得先緩衝完整輸出再截斷
    assert len(result.stdout.encode()) <= 1_048_576 + 4096


async def test_limits_cannot_be_raised_above_the_contract(run):
    """實作不得接受高於契約預設的值（contracts/sandbox-runner.md）。"""
    inflated = ResourceLimits(
        cpu_seconds=600, memory_mb=8192, wall_clock_seconds=600, max_processes=4096
    )
    clamped = inflated.clamped()
    assert clamped.cpu_seconds == 10
    assert clamped.memory_mb == 512
    assert clamped.wall_clock_seconds == MAX_WALL_CLOCK_SECONDS
    assert clamped.max_processes == 64

    started = time.monotonic()
    result = await run(INFINITE_LOOP, Language.PYTHON, limits=inflated)
    assert result.termination_reason is TerminationReason.TIMEOUT
    assert time.monotonic() - started < MAX_WALL_CLOCK_SECONDS + 5
