"""沙箱檔案系統存取阻擋（FR-041～FR-043；憲章原則 VI）。

對應 contracts/sandbox-runner.md 的「檔案系統存取阻擋」必測項目。
其中「前次執行的殘留檔案不存在」是 FR-042「每次執行必須使用全新環境」
唯一能以行為驗證的方式。
"""

from __future__ import annotations

import pytest

from backend.src.models.question import Language

pytestmark = pytest.mark.security

WRITE_ROOT = """
for path in ("/etc/pwned", "/pwned", "/usr/bin/pwned"):
    try:
        open(path, "w").write("x")
        print("WROTE", path)
    except Exception as exc:
        print("BLOCKED", path, type(exc).__name__)
"""

WRITE_WORK = """
open("/work/scratch.txt", "w").write("hello")
print("READ", open("/work/scratch.txt").read())
"""

LEFTOVER_CHECK = """
import os
print("EXISTS", os.path.exists("/work/scratch.txt"), sorted(os.listdir("/work")))
"""

WHOAMI = """
import os
print("UID", os.getuid())
"""

HOST_PATHS = """
import os
found = []
for path in ("/var/run/docker.sock", "/host", "/proc/1/environ", "/root/.ssh"):
    if os.path.exists(path):
        try:
            open(path, "rb").read(1)
            found.append(path)
        except Exception:
            pass
print("READABLE", found)
"""


async def test_root_filesystem_is_read_only(run):
    result = await run(WRITE_ROOT, Language.PYTHON)
    assert "WROTE" not in result.stdout
    assert result.stdout.count("BLOCKED") == 3


async def test_work_directory_is_writable(run):
    result = await run(WRITE_WORK, Language.PYTHON)
    assert "READ hello" in result.stdout


async def test_previous_run_leaves_nothing_behind(run):
    """每次執行使用全新環境，結束後銷毀，不得跨執行重用（FR-042）。"""
    await run(WRITE_WORK, Language.PYTHON)
    result = await run(LEFTOVER_CHECK, Language.PYTHON)
    assert "EXISTS False" in result.stdout


async def test_process_runs_as_non_root(run):
    """必須以最低權限身分執行（FR-043）。"""
    result = await run(WHOAMI, Language.PYTHON)
    assert "UID 0" not in result.stdout


async def test_host_sensitive_paths_are_unreachable(run):
    result = await run(HOST_PATHS, Language.PYTHON)
    assert "/var/run/docker.sock" not in result.stdout
    assert "/root/.ssh" not in result.stdout


async def test_container_is_removed_after_execution(runner, run):
    """--rm：結束即刪除（contracts/sandbox-runner.md）。"""
    await run("print('done')", Language.PYTHON)
    assert runner.list_leftover_containers() == []
