"""離線測試套件的共用夾具（憲章原則 II）。

四項外部相依全部以替身取代，因此整組測試不需網路、資料庫、Docker 或 SMTP：

| 相依 | 替身 |
|------|------|
| Supabase | `InMemoryDataStore`（鏡射 RLS 政策與 SECURITY DEFINER 函式） |
| Gemini   | `FakeAiProvider` |
| Docker   | `FakeSandboxRunner` |
| SMTP     | `FakeEmailSender` |

測試資料一律為合成資料。憲章原則 IV：真實應徵者資料不得出現於測試中。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.src.ai.fake_provider import FakeAiProvider
from backend.src.config import load_settings
from backend.src.email.fake_sender import FakeEmailSender
from backend.src.main import create_app
from backend.src.repositories.memory_store import InMemoryDatabase, InMemoryDataStore
from backend.src.sandbox.fake_runner import FakeSandboxRunner

# 供 RLS 測試使用的夾具（未設定 TEST_DATABASE_URL 時自動跳過）
from backend.tests.conftest_postgres import (  # noqa: F401
    DESIGN_MANAGER_CLAIMS,
    ENG_MANAGER_CLAIMS,
    HR_CLAIMS,
    as_role,
    eng_assessment_id,
    migrated_schema,
    owner_conn,
    psycopg,
)

JWT_SECRET = "synthetic-jwt-secret-for-offline-tests"  # noqa: S105

HR_AUTH_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
ENG_MANAGER_AUTH_ID = "aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa"
DESIGN_MANAGER_AUTH_ID = "aaaaaaaa-3333-4333-8333-aaaaaaaaaaaa"
SALES_MANAGER_AUTH_ID = "aaaaaaaa-4444-4444-8444-aaaaaaaaaaaa"

HR_USER_ID = "11111111-1111-4111-8111-111111111111"
ENG_MANAGER_ID = "22222222-2222-4222-8222-222222222222"
DESIGN_MANAGER_ID = "33333333-3333-4333-8333-333333333333"
SALES_MANAGER_ID = "44444444-4444-4444-8444-444444444444"

BANK_QUESTION_ID = "aa000000-0000-4000-8000-000000000001"

SAMPLE_TEST_CASES = [
    {
        "name": "基本案例",
        "stdin": "3 5\n",
        "expected_stdout": "8\n",
        "is_hidden": False,
        "timeout_seconds": 10,
    },
    {
        "name": "隱藏邊界",
        "stdin": "0 0\n",
        "expected_stdout": "0\n",
        "is_hidden": True,
        "timeout_seconds": 10,
    },
]


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.invalid")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-synthetic")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-synthetic")
    monkeypatch.setenv("CANDIDATE_BASE_URL", "https://assessment.invalid/assessment.html")
    monkeypatch.setenv("MAX_TRIAL_RUNS", "20")
    monkeypatch.setenv("TOKEN_TTL_DAYS", "7")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    return load_settings()


@pytest.fixture
def db() -> InMemoryDatabase:
    database = InMemoryDatabase()

    for dept_id, name, dept_type in (
        ("ENG", "工程技術部", "ENGINEERING"),
        ("DESIGN", "產品設計部", "ENGINEERING"),
        ("SALES", "業務發展部", "NON_ENGINEERING"),
    ):
        database.insert_raw("departments", {"id": dept_id, "name": name, "type": dept_type})

    for user_id, auth_id, name, email, role, dept_id in (
        (HR_USER_ID, HR_AUTH_ID, "合成 HR", "hr@example.com", "HR", None),
        (
            ENG_MANAGER_ID,
            ENG_MANAGER_AUTH_ID,
            "合成工程主管",
            "manager.eng@example.com",
            "MANAGER",
            "ENG",
        ),
        (
            DESIGN_MANAGER_ID,
            DESIGN_MANAGER_AUTH_ID,
            "合成設計主管",
            "manager.design@example.com",
            "MANAGER",
            "DESIGN",
        ),
        (
            SALES_MANAGER_ID,
            SALES_MANAGER_AUTH_ID,
            "合成業務主管",
            "manager.sales@example.com",
            "MANAGER",
            "SALES",
        ),
    ):
        database.insert_raw(
            "internal_users",
            {
                "id": user_id,
                "auth_user_id": auth_id,
                "name": name,
                "email": email,
                "role": role,
                "dept_id": dept_id,
                "is_active": True,
            },
        )

    database.insert_raw(
        "question_banks",
        {
            "id": BANK_QUESTION_ID,
            "dept_id": "ENG",
            "title": "兩數相加",
            "category": "基礎",
            "difficulty": "EASY",
            "language": "python",
            "description": "讀取兩個整數並輸出其和。",
            "constraints": "整數範圍 -10^9 至 10^9。",
            "test_cases": SAMPLE_TEST_CASES,
            "created_by": ENG_MANAGER_ID,
        },
    )
    database.insert_raw(
        "question_banks",
        {
            "id": "aa000000-0000-4000-8000-000000000003",
            "dept_id": "DESIGN",
            "title": "元件狀態管理",
            "category": "前端",
            "difficulty": "MEDIUM",
            "language": "javascript",
            "description": "實作一個簡易的狀態容器。",
            "constraints": "不得使用外部函式庫。",
            "test_cases": [
                {
                    "name": "基本案例",
                    "stdin": "inc\n",
                    "expected_stdout": "1\n",
                    "is_hidden": False,
                    "timeout_seconds": 10,
                }
            ],
            "created_by": DESIGN_MANAGER_ID,
        },
    )
    return database


@pytest.fixture
def fake_ai() -> FakeAiProvider:
    return FakeAiProvider()


@pytest.fixture
def fake_sandbox() -> FakeSandboxRunner:
    return FakeSandboxRunner()


@pytest.fixture
def fake_email() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def app(settings, db, fake_ai, fake_sandbox, fake_email):
    return create_app(
        settings=settings,
        store_factory=lambda context: InMemoryDataStore(db, context),
        ai_provider=fake_ai,
        sandbox_runner=fake_sandbox,
        email_sender=fake_email,
    )


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _token(auth_user_id: str, role: str, dept_id: str | None = None) -> str:
    claims: dict[str, Any] = {"sub": auth_user_id, "app_role": role}
    if dept_id:
        claims["dept_id"] = dept_id
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def hr_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(HR_AUTH_ID, 'HR')}"}


@pytest.fixture
def eng_manager_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(ENG_MANAGER_AUTH_ID, 'MANAGER', 'ENG')}"}


@pytest.fixture
def design_manager_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(DESIGN_MANAGER_AUTH_ID, 'MANAGER', 'DESIGN')}"}


@pytest.fixture
def sales_manager_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(SALES_MANAGER_AUTH_ID, 'MANAGER', 'SALES')}"}


# ── 建立各階段考核的工具 ────────────────────────────────────────────────


@pytest.fixture
def make_assessment(db):
    """直接寫入考核，跳過 API——供「給定一份已提交的作答」這類前置條件使用。"""

    counter = {"n": 0}

    def _make(
        *,
        dept_id: str = "ENG",
        status: str = "PENDING_ASSIGN",
        manager_id: str = ENG_MANAGER_ID,
        token: str | None = None,
        expires_in_days: int = 7,
        question_snapshot: dict[str, Any] | None = None,
        candidate_answer: str | None = None,
        code_language: str | None = None,
        submitted: bool = False,
        trial_run_count: int = 0,
        final_decision: str | None = None,
    ) -> dict[str, Any]:
        counter["n"] += 1
        index = counter["n"]
        return db.insert_raw(
            "assessments",
            {
                "name": f"合成應徵者{index}",
                "email": f"candidate{index}@example.com",
                "phone": f"0900-000-{index:03d}",
                "job_title": "後端工程師",
                "dept_id": dept_id,
                "assigned_manager_id": manager_id,
                "status": status,
                "token": token or f"synthetic-token-{index:04d}-0000000000000000",
                "token_expires_at": datetime.now(UTC) + timedelta(days=expires_in_days),
                "question_snapshot": question_snapshot,
                "candidate_answer": candidate_answer,
                "code_language": code_language,
                "trial_run_count": trial_run_count,
                "final_decision": final_decision,
                "submitted_at": datetime.now(UTC) if submitted else None,
            },
        )

    return _make


@pytest.fixture
def question_snapshot() -> dict[str, Any]:
    return {
        "source": "BANK",
        "source_id": BANK_QUESTION_ID,
        "title": "兩數相加",
        "category": "基礎",
        "difficulty": "EASY",
        "language": "python",
        "description": "讀取兩個整數並輸出其和。",
        "constraints": "整數範圍 -10^9 至 10^9。",
        "test_cases": SAMPLE_TEST_CASES,
        "assigned_at": datetime.now(UTC).isoformat(),
        "assigned_by": ENG_MANAGER_ID,
    }
