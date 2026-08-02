"""service_role 使用範圍守護（research.md R-002）。

service_role 會完全繞過 RLS。一旦它被用於處理使用者請求，資料庫層的權限
政策形同不存在——而憲章原則 IV 要求權限必須在資料存取層強制執行。
R-002 因此明訂其使用範圍「僅限資料庫遷移與排程維護作業」，並要求以測試守護。

本測試從兩個方向守護：
1. 行為面——以 service_role 金鑰建立請求連線時必須失敗。
2. 靜態面——處理使用者請求的程式路徑不得出現該金鑰的名稱。
"""

from __future__ import annotations

import pathlib

import pytest

from backend.src.config import load_settings
from backend.src.repositories.base import (
    RequestContext,
    ServiceRoleMisuseError,
    assert_not_service_role,
)

SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"

# 允許提及 service_role 的位置：設定載入處，與守護機制本身。
ALLOWED_FILES = {
    SRC_ROOT / "config.py",
    SRC_ROOT / "repositories" / "base.py",
}

REQUEST_HANDLING_DIRS = ("api", "services", "repositories", "ai", "email", "sandbox", "audit")


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.invalid")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-synthetic")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret-synthetic")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key-synthetic")
    return load_settings()


def test_service_role_key_is_rejected_as_request_credential(settings):
    with pytest.raises(ServiceRoleMisuseError):
        assert_not_service_role("service-role-key-synthetic", settings)


def test_user_jwt_is_accepted(settings):
    assert assert_not_service_role("a-normal-user-jwt", settings) is None


def test_create_store_rejects_service_role_context(settings):
    from backend.src.repositories.base import create_supabase_store

    context = RequestContext(role="HR", jwt="service-role-key-synthetic")
    with pytest.raises(ServiceRoleMisuseError):
        create_supabase_store(settings, context)


@pytest.mark.parametrize("directory", REQUEST_HANDLING_DIRS)
def test_request_handling_modules_do_not_reference_service_role(directory):
    offenders = []
    for path in (SRC_ROOT / directory).rglob("*.py"):
        if path in ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if "service_role" in text or "SERVICE_ROLE" in text:
            offenders.append(str(path.relative_to(SRC_ROOT)))
    assert offenders == [], (
        "處理使用者請求的程式路徑不得使用 service_role 金鑰（research.md R-002）："
        + "、".join(offenders)
    )
