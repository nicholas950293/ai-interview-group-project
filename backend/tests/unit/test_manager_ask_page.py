"""面試官簡易出題頁的結構不變條件。

這一頁沒有自己的後端：它走既有的
`POST /manager/assessments/{id}/assign-question`。因此這裡守的東西有三類——
頁面能被服務、不遮蔽 API 路由、以及不自行開一條資料通道（直接 fetch、
自建端點、或繞過 api.js）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.src.config import load_settings
from backend.src.main import create_app

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
MANAGER_DIR = FRONTEND / "manager"
PAGE = MANAGER_DIR / "ask.html"

# 出題頁允許自 api.js 取用的匯出。`candidate` 與 `hr` 不在其中。
ALLOWED_API_IMPORTS = frozenset({"manager", "clearAuthToken", "ApiError"})

BROWSER_GLOBALS = ("document", "window", "fetch", "localStorage", "sessionStorage")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _js_sources(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.js"))


@pytest.fixture
def demo_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("LOCAL_DEMO_MODE", "1")
    return TestClient(create_app(settings=load_settings()))


def test_page_and_its_modules_exist() -> None:
    assert PAGE.is_file()
    assert (MANAGER_DIR / "ask.js").is_file()
    assert (MANAGER_DIR / "core" / "question-draft.js").is_file()
    assert (MANAGER_DIR / "css" / "ask.css").is_file()


def test_page_is_served(demo_client: TestClient) -> None:
    response = demo_client.get("/manager/ask.html")
    assert response.status_code == 200
    assert "出題給應徵者" in response.text
    assert "./ask.js" in response.text


def test_manager_api_routes_are_not_shadowed_by_the_new_folder(demo_client: TestClient) -> None:
    """新增 frontend/manager/ 後，/manager/* 的 API 路由必須仍然優先比對。

    這與應徵者頁的 /candidate 前綴是同一個隱含相依（FastAPI 先比對已註冊路由、
    最後才落到 StaticFiles 掛載）。它今天成立，但沒有東西保證明天還成立。
    """
    import jwt

    token = jwt.encode(
        {"sub": "demo-manager-user", "app_role": "MANAGER", "dept_id": "ENG"},
        "demo-jwt-secret",
        algorithm="HS256",
    )
    response = demo_client.get("/manager/assessments", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json(), list)


def test_existing_manager_hub_is_untouched(demo_client: TestClient) -> None:
    """新頁面是額外入口，不取代既有的完整主管介面。"""
    assert "主管 Hub" in demo_client.get("/manager.html").text


def test_no_direct_fetch_in_the_page() -> None:
    """所有後端存取一律經由 frontend/js/api.js。"""
    offenders = [
        path.name for path in _js_sources(MANAGER_DIR) if re.search(r"\bfetch\s*\(", _read(path))
    ]
    assert offenders == [], f"這些檔案直接呼叫了 fetch：{offenders}"


def test_only_the_allowed_api_namespace_is_imported() -> None:
    """出題頁不得取用 candidate 或 hr 命名空間。"""
    imported: set[str] = set()
    for path in _js_sources(MANAGER_DIR):
        for match in re.finditer(
            r"""import\s*\{([^}]*)\}\s*from\s*['"][^'"]*js/api\.js['"]""", _read(path)
        ):
            imported.update(name.strip() for name in match.group(1).split(",") if name.strip())

    assert imported, "出題頁應至少自 api.js 匯入一項，否則本檢查失去意義"
    disallowed = imported - ALLOWED_API_IMPORTS
    assert not disallowed, f"取用了允許清單外的匯出：{disallowed}"


def test_core_layer_is_free_of_browser_globals() -> None:
    """core/ 為純邏輯，可於 Node 直接匯入測試。"""
    offenders = [
        f"{path.name}:{name}"
        for path in _js_sources(MANAGER_DIR / "core")
        for name in BROWSER_GLOBALS
        if re.search(rf"\b{name}\b", _read(path))
    ]
    assert offenders == [], f"core/ 引用了瀏覽器 API：{offenders}"


def test_every_element_id_used_by_the_script_exists_in_the_markup() -> None:
    """DOM 契約：ask.js 查找的每個 id 都必須存在於 ask.html。"""
    required = set(re.findall(r"""el\(['"]([^'"]+)['"]\)""", _read(MANAGER_DIR / "ask.js")))
    present = set(re.findall(r"""\bid=["']([^"']+)["']""", _read(PAGE)))

    assert required, "ask.js 應查找至少一個 id，否則本檢查失去意義"
    missing = sorted(required - present)
    assert not missing, f"ask.html 缺少 ask.js 需要的 id：{missing}"


def test_page_shares_the_common_design_system() -> None:
    """視覺一致性靠共用樣式表，而不是複製色碼——色票只有一份定義。"""
    markup = _read(PAGE)
    assert "../css/theme.css" in markup
    assert "tailwindcss.com" not in markup

    # 出題頁自己的樣式表不得重新定義色票，否則兩頁會各自漂移
    page_css = _read(MANAGER_DIR / "css" / "ask.css")
    assert "--bg-panel:" not in page_css
    assert "--accent:" not in page_css
    assert not re.search(r"#[0-9a-fA-F]{6}\b", page_css), "出題頁樣式表不得寫死色碼"
