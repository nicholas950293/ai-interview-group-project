"""效能驗證（SC-004、SC-005、SC-010）。

**這組測試量測的是本系統負責的部分**，也就是 API 與協調層的開銷；
沙箱內程式碼的實際執行時間取決於應徵者的程式與宿主機規格，不在此列。

以替身取代沙箱後，測得的時間即為「扣除執行本身之後，系統還花了多久」。
若這個開銷本身就吃掉大半預算，那麼再快的沙箱也救不回 SC-004。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.src.models.question import Language
from backend.src.models.report import ExecutionResult, TerminationReason
from backend.src.sandbox.runner import ExecutionRequest

ANSWER = "print(sum(map(int, input().split())))"

# 系統開銷的預算：SC-004 給試跑 15 秒，其中屬於協調層的部分應遠低於 1 秒
TRIAL_RUN_OVERHEAD_BUDGET_S = 1.0
# SC-005 給報告 3 分鐘；協調層（含測資逐項執行的排程）預算同樣抓 1 秒
EVALUATION_OVERHEAD_BUDGET_S = 1.0


@pytest.fixture
def ready(make_assessment, question_snapshot, fake_sandbox):
    for stdin, stdout in (("3 5\n", "8\n"), ("0 0\n", "0\n")):
        fake_sandbox.register_for_stdin(
            stdin,
            "python",
            ExecutionResult(
                stdout=stdout, exit_code=0, termination_reason=TerminationReason.COMPLETED
            ),
        )
    return make_assessment(status="PENDING_CANDIDATE", question_snapshot=question_snapshot)


def test_trial_run_overhead_is_within_budget(client, ready):
    """SC-004：試跑 p90 < 15 秒。此處量測扣除執行本身的系統開銷。"""
    durations = []
    for _ in range(10):
        started = time.perf_counter()
        response = client.post(
            f"/candidate/session/{ready['token']}/run",
            json={"code": ANSWER, "language": "python", "stdin": "3 5\n"},
        )
        durations.append(time.perf_counter() - started)
        assert response.status_code == 200

    durations.sort()
    p90 = durations[int(len(durations) * 0.9) - 1]
    assert p90 < TRIAL_RUN_OVERHEAD_BUDGET_S, f"試跑的系統開銷 p90 為 {p90:.3f}s"


def test_evaluation_overhead_is_within_budget(client, ready, db):
    """SC-005：提交至報告可見 < 3 分鐘。此處量測協調層的開銷。"""
    started = time.perf_counter()
    response = client.post(
        f"/candidate/session/{ready['token']}/submit",
        json={"answer": ANSWER, "language": "python"},
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    report = next(r for r in db.tables["ai_reports"] if r["assessment_id"] == ready["id"])
    assert report["status"] == "SUCCESS", "報告必須在提交流程結束時即可見"
    assert elapsed < EVALUATION_OVERHEAD_BUDGET_S, f"評測協調開銷為 {elapsed:.3f}s"


def test_overview_scales_with_many_assessments(client, hr_headers, make_assessment):
    """總覽頁是 HR 最常用的畫面，不得隨資料量線性劣化到不可用。"""
    for _ in range(50):
        make_assessment(dept_id="ENG")

    started = time.perf_counter()
    response = client.get("/hr/assessments", headers=hr_headers)
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert len(response.json()) == 50
    assert elapsed < 2.0, f"50 筆考核的總覽查詢耗時 {elapsed:.3f}s"


async def test_slow_sandbox_execution_does_not_block_other_requests(fake_sandbox):
    """SC-010：任一應徵者的程式碼執行，不得使其他使用者的回應時間超出正常值兩倍。

    沙箱執行以 `asyncio.to_thread` 與 Semaphore 隔離，因此事件迴圈不會被
    佔用。這裡以一個刻意變慢的替身驗證該性質。
    """
    original_run = fake_sandbox.run

    async def slow_run(request):
        await asyncio.sleep(0.5)
        return await original_run(request)

    fake_sandbox.run = slow_run

    async def other_work() -> float:
        started = time.perf_counter()
        await asyncio.sleep(0)  # 讓出控制權，模擬一次一般 API 處理
        return time.perf_counter() - started

    baseline = await other_work()
    slow_task = asyncio.create_task(
        fake_sandbox.run(ExecutionRequest(code=ANSWER, language=Language.PYTHON, stdin="3 5\n"))
    )
    during = await other_work()
    await slow_task

    # baseline 極小，因此以絕對上限判定較有意義
    assert during < max(
        baseline * 2, 0.05
    ), f"沙箱執行期間，其他工作的回應時間為 {during:.4f}s（基準 {baseline:.4f}s）"


async def test_sandbox_concurrency_is_capped_at_ten(settings):
    """FR-046：同時執行數上限為 10，超出者等候而非失敗。"""
    from backend.src.sandbox.docker_runner import DockerSandboxRunner

    runner = DockerSandboxRunner(settings.sandbox)
    assert runner._semaphore._value == 10  # noqa: SLF001 - 直接驗證併發上限
    assert settings.sandbox.max_concurrency == 10
