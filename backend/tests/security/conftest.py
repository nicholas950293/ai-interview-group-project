"""安全套件的共用夾具（憲章「安全關卡」）。

這組測試斷言的是**真實容器**的行為，替身在此無意義（research.md R-008）。
因此需要本機 Docker 與已建置的五個沙箱映像檔：

```bash
for lang in javascript python go java cpp; do
  docker build -t "sandbox-$lang" "sandbox/$lang"
done
cd backend && pytest -m security
```
"""

from __future__ import annotations

import asyncio

import pytest

from backend.src.config import SandboxSettings
from backend.src.models.question import Language
from backend.src.sandbox.docker_runner import DockerSandboxRunner
from backend.src.sandbox.runner import ExecutionRequest, ResourceLimits

pytestmark = pytest.mark.security

SETTINGS = SandboxSettings(runtime=None, image_prefix="sandbox-", max_concurrency=10)


@pytest.fixture(scope="session")
def runner() -> DockerSandboxRunner:
    instance = DockerSandboxRunner(SETTINGS)
    if not asyncio.run(instance.health_check()):
        pytest.skip("本機 Docker 不可用或沙箱映像檔尚未建置，跳過安全套件")
    return instance


@pytest.fixture
def run(runner):
    async def _run(
        code: str,
        language: Language = Language.PYTHON,
        stdin: str = "",
        limits: ResourceLimits | None = None,
    ):
        return await runner.run(
            ExecutionRequest(
                code=code,
                language=language,
                stdin=stdin,
                limits=limits or ResourceLimits(),
            )
        )

    return _run
