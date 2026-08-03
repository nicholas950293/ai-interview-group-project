"""本機 demo 模式的假資料與記憶體資料庫種子。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.src.repositories.base import RequestContext
from backend.src.repositories.memory_store import InMemoryDatabase, InMemoryDataStore


def build_demo_store_factory() -> Any:
    db = InMemoryDatabase()
    seed_demo_database(db)

    def store_factory(context: RequestContext) -> InMemoryDataStore:
        return InMemoryDataStore(db, context)

    return store_factory


def seed_demo_database(db: InMemoryDatabase) -> None:
    now = datetime.now(UTC)

    for dept_id, name, dept_type in (
        ("ENG", "工程技術部", "ENGINEERING"),
        ("DESIGN", "產品設計部", "ENGINEERING"),
        ("SALES", "業務發展部", "NON_ENGINEERING"),
    ):
        db.insert_raw("departments", {"id": dept_id, "name": name, "type": dept_type})

    for user_id, auth_id, name, email, role, dept_id in (
        ("demo-hr-user", "demo-hr-user", "Demo HR", "hr@example.com", "HR", None),
        (
            "demo-manager-user",
            "demo-manager-user",
            "Demo 工程主管",
            "manager@example.com",
            "MANAGER",
            "ENG",
        ),
    ):
        db.insert_raw(
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

    db.insert_raw(
        "question_banks",
        {
            "id": "demo-question-bank-001",
            "dept_id": "ENG",
            "title": "兩數相加",
            "category": "基礎",
            "difficulty": "EASY",
            "language": "python",
            "description": "讀取兩個整數並輸出其和。",
            "constraints": "輸入為兩個整數。",
            "test_cases": [
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
            ],
            "created_by": "demo-manager-user",
        },
    )

    db.insert_raw(
        "assessments",
        {
            "id": "demo-assessment-001",
            "name": "林小明",
            "email": "candidate1@example.com",
            "phone": "0900-000-001",
            "job_title": "後端工程師",
            "dept_id": "ENG",
            "assigned_manager_id": "demo-manager-user",
            "status": "PENDING_CANDIDATE",
            "token": "demo-candidate-001",
            "token_expires_at": now + timedelta(days=7),
            "question_snapshot": {
                "source": "BANK",
                "source_id": "demo-question-bank-001",
                "title": "兩數相加",
                "category": "基礎",
                "difficulty": "EASY",
                "language": "python",
                "description": "讀取兩個整數並輸出其和。",
                "constraints": "輸入為兩個整數。",
                "test_cases": [
                    {
                        "name": "基本案例",
                        "stdin": "3 5\n",
                        "expected_stdout": "8\n",
                        "is_hidden": False,
                    }
                ],
            },
            "candidate_answer": None,
            "code_language": "python",
            "trial_run_count": 0,
            "final_decision": None,
            "submitted_at": None,
            "created_at": now,
        },
    )

    # 待指派題目，且屬 demo 主管所在的 ENG 部門——登入後就有對象可以出題。
    # demo-assessment-002 刻意留在 DESIGN，用來呈現部門隔離（FR-003）：
    # 以 demo 主管登入時看不到它。
    db.insert_raw(
        "assessments",
        {
            "id": "demo-assessment-004",
            "name": "張小豪",
            "email": "candidate4@example.com",
            "phone": "0900-000-004",
            "job_title": "資深後端工程師",
            "dept_id": "ENG",
            "assigned_manager_id": "demo-manager-user",
            "status": "PENDING_ASSIGN",
            "token": "demo-candidate-004",
            "token_expires_at": now + timedelta(days=7),
            "question_snapshot": None,
            "candidate_answer": None,
            "code_language": None,
            "trial_run_count": 0,
            "final_decision": None,
            "submitted_at": None,
            "created_at": now,
        },
    )

    db.insert_raw(
        "assessments",
        {
            "id": "demo-assessment-002",
            "name": "陳小雯",
            "email": "candidate2@example.com",
            "phone": "0900-000-002",
            "job_title": "前端工程師",
            "dept_id": "DESIGN",
            "assigned_manager_id": "demo-manager-user",
            "status": "PENDING_ASSIGN",
            "token": "demo-candidate-002",
            "token_expires_at": now + timedelta(days=7),
            "question_snapshot": None,
            "candidate_answer": None,
            "code_language": None,
            "trial_run_count": 0,
            "final_decision": None,
            "submitted_at": None,
            "created_at": now,
        },
    )

    db.insert_raw(
        "assessments",
        {
            "id": "demo-assessment-003",
            "name": "王大同",
            "email": "candidate3@example.com",
            "phone": "0900-000-003",
            "job_title": "後端工程師",
            "dept_id": "ENG",
            "assigned_manager_id": "demo-manager-user",
            "status": "COMPLETED_AWAITING_REVIEW",
            "token": "demo-candidate-003",
            "token_expires_at": now + timedelta(days=7),
            "question_snapshot": {
                "source": "BANK",
                "source_id": "demo-question-bank-001",
                "title": "兩數相加",
                "category": "基礎",
                "difficulty": "EASY",
                "language": "python",
                "description": "讀取兩個整數並輸出其和。",
                "constraints": "輸入為兩個整數。",
                "test_cases": [
                    {
                        "name": "基本案例",
                        "stdin": "3 5\n",
                        "expected_stdout": "8\n",
                        "is_hidden": False,
                    }
                ],
            },
            "candidate_answer": "def add(a, b):\n    return a + b\n",
            "code_language": "python",
            "trial_run_count": 1,
            "final_decision": None,
            "submitted_at": now - timedelta(minutes=10),
            "created_at": now - timedelta(days=1),
        },
    )

    db.insert_raw(
        "audit_logs",
        {
            "assessment_id": "demo-assessment-001",
            "action": "ASSESSMENT_CREATED",
            "from_status": None,
            "to_status": "PENDING_CANDIDATE",
            "actor_role": "HR",
            "detail": {"token": "demo-candidate-001"},
        },
    )
