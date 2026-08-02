"""RLS 政策測試的共用夾具。

RLS 的驗證需要真實 PostgreSQL——替身無法驗證資料庫層的拒絕行為
（research.md R-008）。PostgreSQL 為本機程序而非網路服務，不影響離線可執行性；
未設定 `TEST_DATABASE_URL` 時整組測試跳過，使預設套件在沒有資料庫的環境仍可通過。

這些測試連線時一律 `SET ROLE authenticated` 並設定 `request.jwt.claims`，
與 PostgREST 的實際行為一致（research.md R-002）。以資料表擁有者身分連線
會繞過 RLS，因此絕不可省略 `SET ROLE`。
"""

from __future__ import annotations

import os
import pathlib
import uuid

import pytest

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "supabase" / "migrations"

HR_CLAIMS = '{"sub": "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", "app_role": "HR"}'
ENG_MANAGER_CLAIMS = (
    '{"sub": "aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa", "app_role": "MANAGER", "dept_id": "ENG"}'
)
DESIGN_MANAGER_CLAIMS = (
    '{"sub": "aaaaaaaa-3333-4333-8333-aaaaaaaaaaaa", "app_role": "MANAGER", "dept_id": "DESIGN"}'
)


def _database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL", "").strip() or None


@pytest.fixture(scope="session")
def psycopg():
    if _database_url() is None:
        pytest.skip("未設定 TEST_DATABASE_URL，跳過需要本機 PostgreSQL 的 RLS 測試")
    try:
        import psycopg as _psycopg
    except ImportError:  # pragma: no cover - 相依未安裝時的跳過路徑
        pytest.skip("未安裝 psycopg，跳過需要本機 PostgreSQL 的 RLS 測試")
    return _psycopg


@pytest.fixture(scope="session")
def migrated_schema(psycopg):
    """套用全部遷移檔並載入合成資料。整個 session 共用一份結構。"""
    url = _database_url()
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(path.read_text(encoding="utf-8"))
        seed = MIGRATIONS_DIR.parent / "seed.sql"
        conn.execute(seed.read_text(encoding="utf-8"))
    return url


@pytest.fixture
def owner_conn(psycopg, migrated_schema):
    """以資料表擁有者身分連線。僅用於建立前置資料與驗證結果，不用於斷言權限。"""
    with psycopg.connect(migrated_schema, autocommit=True) as conn:
        yield conn


@pytest.fixture
def as_role(psycopg, migrated_schema):
    """以 authenticated 角色並帶指定 JWT claim 連線，重現 PostgREST 的實際行為。"""

    def _connect(claims: str):
        conn = psycopg.connect(migrated_schema, autocommit=True)
        conn.execute("SET ROLE authenticated")
        conn.execute("SELECT set_config('request.jwt.claims', %s, false)", (claims,))
        return conn

    opened: list = []

    def _factory(claims: str):
        conn = _connect(claims)
        opened.append(conn)
        return conn

    yield _factory
    for conn in opened:
        conn.close()


@pytest.fixture
def eng_assessment_id(owner_conn) -> str:
    """工程技術部的一筆已提交考核，含 AI 報告、執行紀錄與主管決策。"""
    assessment_id = str(uuid.uuid4())
    owner_conn.execute(
        """
        INSERT INTO assessments (id, name, email, job_title, dept_id, assigned_manager_id,
                                 status, token, token_expires_at, candidate_answer,
                                 code_language, submitted_at)
        VALUES (%s, '合成應徵者', 'rls.case@example.com', '後端工程師', 'ENG',
                '22222222-2222-4222-8222-222222222222',
                'COMPLETED_AWAITING_REVIEW', %s, NOW() + INTERVAL '7 days',
                'print(1)', 'python', NOW())
        """,
        (assessment_id, f"rls-token-{assessment_id}"),
    )
    owner_conn.execute(
        """
        INSERT INTO execution_records (assessment_id, trigger, language, termination_reason)
        VALUES (%s, 'EVALUATION', 'python', 'COMPLETED')
        """,
        (assessment_id,),
    )
    owner_conn.execute(
        """
        INSERT INTO ai_reports
            (assessment_id, attempt_no, status, dimensions, test_pass_ratio, model_id)
        VALUES (%s, 1, 'SUCCESS',
                '{"correctness": {"score": 80, "comment": "測試"},
                  "maintainability": {"score": 70, "comment": "測試"},
                  "performance": {"score": 90, "comment": "測試"},
                  "security": {"score": 60, "comment": "測試"}}'::jsonb,
                0.8, 'synthetic-model')
        """,
        (assessment_id,),
    )
    owner_conn.execute(
        """
        INSERT INTO manager_decisions
            (assessment_id, revision_no, decided_by, result, internal_comment)
        VALUES (%s, 1, '22222222-2222-4222-8222-222222222222', 'PASS', '內部評語：僅同部門主管可見')
        """,
        (assessment_id,),
    )
    owner_conn.execute(
        """
        INSERT INTO audit_logs (assessment_id, action, actor_role)
        VALUES (%s, 'ASSESSMENT_CREATED', 'HR')
        """,
        (assessment_id,),
    )
    return assessment_id
