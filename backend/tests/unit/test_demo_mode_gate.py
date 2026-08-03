"""demo 模式的開關與其邊界（spec 003 端到端串接的安全前提）。

demo 模式會把整個系統換成記憶體假資料、替身服務與固定的 JWT 密鑰。
因此這裡守兩件事：

1. **它只在明確要求時啟用**——`LOCAL_DEMO_MODE=0` 必須是關閉。
2. **正式環境不接受任何 demo 憑證**——demo 的 JWT 密鑰與 demo token
   都不得被特別對待。

本檔一律以明確的 env 對應傳入 `load_settings()`，不使用 monkeypatch：
`load_settings(env=None)` 會讀取本機 `.env`，測試結果將取決於開發者機器上
碰巧有什麼設定——那樣的測試證明不了任何事。
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.src.config import load_settings
from backend.src.main import create_app
from backend.src.repositories.memory_store import InMemoryDatabase, InMemoryDataStore

DEMO_JWT_SECRET = "demo-jwt-secret"  # noqa: S105 — demo 模式的固定值，非機密
PRODUCTION_JWT_SECRET = "synthetic-production-secret"  # noqa: S105 — 合成測試資料

PRODUCTION_ENV = {
    "SUPABASE_URL": "https://synthetic.invalid",
    "SUPABASE_ANON_KEY": "anon-key-synthetic",
    "SUPABASE_JWT_SECRET": PRODUCTION_JWT_SECRET,
}


# ── 開關 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_demo_mode_enabled_only_by_an_explicit_yes(value: str) -> None:
    assert load_settings(env={"LOCAL_DEMO_MODE": value}).demo_mode is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", "", "  "])
def test_demo_mode_stays_off_for_anything_that_means_no(value: str) -> None:
    """`LOCAL_DEMO_MODE=0` 的意圖顯然是關閉。

    若以 `bool(值)` 判定，這些值全部會被讀成開啟——正式環境會靜默降級為
    記憶體假資料 + 固定 JWT 密鑰的無認證系統。
    """
    settings = load_settings(env=PRODUCTION_ENV | {"LOCAL_DEMO_MODE": value})
    assert settings.demo_mode is False


def test_demo_mode_absent_is_off() -> None:
    assert load_settings(env=PRODUCTION_ENV).demo_mode is False


def test_non_demo_mode_still_requires_real_supabase_settings() -> None:
    """demo 模式是唯一能省略必要設定的情況；關閉時仍必須啟動即失敗。"""
    from backend.src.config import ConfigError

    with pytest.raises(ConfigError):
        load_settings(env={"LOCAL_DEMO_MODE": "0"})


# ── 正式環境不接受 demo 憑證 ──────────────────────────────────────────


@pytest.fixture
def production_client() -> TestClient:
    """非 demo 模式的應用程式。

    資料層仍以記憶體替身注入（正式的 Supabase 連線無法離線測試），
    但**設定本身不是 demo 模式**——JWT 密鑰為正式值，這正是本節要驗證的部分。
    """
    settings = load_settings(env=PRODUCTION_ENV)
    assert settings.demo_mode is False
    assert settings.supabase.jwt_secret != DEMO_JWT_SECRET

    database = InMemoryDatabase()
    return TestClient(
        create_app(
            settings=settings,
            store_factory=lambda context: InMemoryDataStore(database, context),
        )
    )


def test_production_rejects_a_jwt_signed_with_the_demo_secret(production_client) -> None:
    """demo 的 JWT 密鑰在正式環境必須簽不出有效憑證。"""
    token = jwt.encode(
        {"sub": "demo-manager-user", "app_role": "MANAGER", "dept_id": "ENG"},
        DEMO_JWT_SECRET,
        algorithm="HS256",
    )
    response = production_client.get(
        "/manager/assessments", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "token", ["demo-candidate-001", "demo-candidate-002", "demo-candidate-004"]
)
def test_production_does_not_special_case_demo_candidate_tokens(production_client, token) -> None:
    """demo token 不得在任何地方被寫死放行——它們只是普通字串。"""
    assert production_client.get(f"/candidate/session/{token}").status_code == 404


def test_production_has_no_demo_accounts(production_client) -> None:
    """demo 帳號只存在於 FakeAuthProvider；正式環境走 Supabase Auth。"""
    response = production_client.post(
        "/auth/login", json={"email": "manager@example.com", "password": "demo1234"}
    )
    # 401（憑證錯誤）或 503（連不上 Supabase）皆可接受，但**絕不能是 200**
    assert response.status_code in (401, 503)


def test_production_health_does_not_claim_demo_mode(production_client) -> None:
    """登入頁以此決定是否顯示測試帳號——回報錯了就會在正式環境印出憑證。"""
    assert production_client.get("/health").json()["demo_mode"] is False
