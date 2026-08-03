"""應徵者前端的結構不變條件（specs/002-candidate-assessment-ui INV-001～INV-007）。

這些檢查放在 pytest 而不是前端，理由是它們守的東西有一半在後端：
路由不得被靜態檔遮蔽、兩條頁面路徑都要能被服務。把兩半拆到不同的執行器，
就會有一半沒人跑。

檢查本身是靜態掃描——刻意不解析 JS，因為需要斷言的是「這些字串不該出現」，
而字串比對對這種否定式斷言而言既足夠也不會有解析器版本問題。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.src.config import load_settings
from backend.src.main import create_app

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
CANDIDATE_DIR = FRONTEND / "candidate"
CORE_DIR = CANDIDATE_DIR / "core"
API_MODULE = FRONTEND / "js" / "api.js"

# 應徵者介面允許自 api.js 取用的匯出（INV-003）。
# `hr` 與 `manager` 不在其中——不是因為它們被隱藏，而是應徵者頁面根本沒有理由碰。
ALLOWED_API_IMPORTS = frozenset({"candidate", "ApiError", "formatDate"})

# 這些識別字若出現在應徵者介面，代表有人把內部資料引進了對外頁面（INV-004）。
FORBIDDEN_IDENTIFIERS = (
    "dimensions",
    "internal_comment",
    "ai_report",
    "aiReport",
    "manager_decision",
    "managerDecision",
    "is_hidden",
    "isHidden",
    "test_cases",
    "testCases",
)

# core/ 是純邏輯層，不得碰任何瀏覽器 API，否則它就無法在 Node 中被測試（INV-007）
BROWSER_GLOBALS = ("document", "window", "fetch", "localStorage", "sessionStorage")


def _sources(directory: Path, suffixes: tuple[str, ...] = (".js", ".html", ".css")) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix in suffixes)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _import_sources(content: str) -> list[str]:
    """回傳所有 `import ... from '<來源>'` 的來源字串。"""
    return re.findall(r"""\bfrom\s+['"]([^'"]+)['"]""", content)


@pytest.fixture
def demo_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("LOCAL_DEMO_MODE", "1")
    return TestClient(create_app(settings=load_settings()))


def test_candidate_sources_exist_in_a_single_folder() -> None:
    """FR-101：應徵者介面的檔案全部集中於 frontend/candidate/。"""
    assert (CANDIDATE_DIR / "assessment.html").is_file()
    assert (CANDIDATE_DIR / "main.js").is_file()
    assert _sources(CORE_DIR), "core/ 不得為空"
    assert _sources(CANDIDATE_DIR / "ui"), "ui/ 不得為空"

    # 搬移必須是搬移，不是複製
    assert not (FRONTEND / "js" / "editor.js").exists()
    assert not (FRONTEND / "js" / "chat.js").exists()


def test_candidate_never_calls_fetch_directly() -> None:
    """INV-001：所有 API 呼叫一律經由 frontend/js/api.js（FR-104）。"""
    offenders = [
        path.relative_to(FRONTEND)
        for path in _sources(CANDIDATE_DIR)
        if re.search(r"\bfetch\s*\(", _read(path))
    ]
    assert offenders == [], f"這些檔案直接呼叫了 fetch：{offenders}"


def test_import_boundary_between_roles_holds_in_both_directions() -> None:
    """INV-002：應徵者與內部介面互不相依（FR-102）。"""
    for path in _sources(CANDIDATE_DIR, (".js",)):
        for source in _import_sources(_read(path)):
            assert "hr.js" not in source, f"{path.name} 匯入了 HR 模組"
            assert "manager.js" not in source, f"{path.name} 匯入了主管模組"

    for name in ("hr.js", "manager.js"):
        content = _read(FRONTEND / "js" / name)
        for source in _import_sources(content):
            assert "candidate/" not in source, f"{name} 匯入了應徵者模組"


def test_candidate_only_imports_its_own_api_namespace() -> None:
    """INV-003：不得取用 hr／manager 命名空間（FR-103）。"""
    imported: set[str] = set()
    for path in _sources(CANDIDATE_DIR, (".js",)):
        for match in re.finditer(
            r"""import\s*\{([^}]*)\}\s*from\s*['"][^'"]*js/api\.js['"]""", _read(path)
        ):
            imported.update(name.strip() for name in match.group(1).split(",") if name.strip())

    assert imported, "應徵者介面應至少自 api.js 匯入一項，否則本檢查失去意義"
    disallowed = imported - ALLOWED_API_IMPORTS
    assert not disallowed, f"取用了允許清單外的匯出：{disallowed}"


def test_only_the_composition_root_touches_the_api() -> None:
    """API 呼叫集中於 main.js，使 ui/ 模組可被單獨閱讀（plan.md 結構決策）。"""
    importers = [
        path.relative_to(CANDIDATE_DIR)
        for path in _sources(CANDIDATE_DIR, (".js",))
        if any("js/api.js" in source for source in _import_sources(_read(path)))
    ]
    assert [str(p) for p in importers] == ["main.js"]


def test_candidate_sources_contain_no_restricted_identifiers() -> None:
    """INV-004：AI 報告、內部評語、決策與隱藏測資不得出現於應徵者介面（FR-133）。

    掃描範圍排除 `tests/`：那裡的受限識別字是刻意放進去的污染輸入，
    用來證明視圖模型會把它們丟掉。把測試也納入掃描，等於禁止我們驗證這件事。
    """
    offenders: list[str] = []
    for path in _sources(CANDIDATE_DIR):
        if "tests" in path.relative_to(CANDIDATE_DIR).parts:
            continue
        content = _read(path)
        offenders += [
            f"{path.relative_to(FRONTEND)}:{identifier}"
            for identifier in FORBIDDEN_IDENTIFIERS
            if identifier in content
        ]
    assert offenders == [], f"應徵者介面出現了受限識別字：{offenders}"


def test_candidate_never_persists_the_token() -> None:
    """FR-134：token 是憑證，不得被寫入瀏覽器儲存空間。"""
    for path in _sources(CANDIDATE_DIR, (".js",)):
        content = _read(path)
        assert "localStorage" not in content, f"{path.name} 使用了 localStorage"
        assert "sessionStorage" not in content, f"{path.name} 使用了 sessionStorage"


def test_core_layer_is_free_of_browser_globals() -> None:
    """INV-007：core/ 可在 Node 中直接匯入，因此純邏輯測試不需要 DOM。"""
    offenders: list[str] = []
    for path in _sources(CORE_DIR, (".js",)):
        content = _read(path)
        offenders += [
            f"{path.name}:{name}"
            for name in BROWSER_GLOBALS
            if re.search(rf"\b{name}\b", content)
        ]
    assert offenders == [], f"core/ 引用了瀏覽器 API：{offenders}"


def test_api_module_remains_the_single_fetch_site() -> None:
    """FR-104 的另一半：唯一允許 fetch 的位置仍然只有 api.js。"""
    frontend_js = [
        path
        for path in _sources(FRONTEND, (".js",))
        if "node_modules" not in path.parts and path != API_MODULE
    ]
    offenders = [
        str(path.relative_to(FRONTEND))
        for path in frontend_js
        if re.search(r"\bfetch\s*\(", _read(path))
    ]
    assert offenders == [], f"api.js 以外的模組直接呼叫了 fetch：{offenders}"


def test_candidate_page_is_served_at_the_new_path(demo_client: TestClient) -> None:
    """INV-006：新路徑可被服務（FR-105）。"""
    response = demo_client.get("/candidate/assessment.html")
    assert response.status_code == 200
    assert "線上測驗" in response.text
    assert "./main.js" in response.text


def test_legacy_path_still_reaches_the_candidate_page(demo_client: TestClient) -> None:
    """INV-006：已寄出的舊連結不得失效（FR-106）。"""
    response = demo_client.get("/assessment.html")
    assert response.status_code == 200
    assert "candidate/assessment.html" in response.text
    # 轉址必須帶著查詢字串，否則 token 會在跳轉時掉光
    assert "window.location.search" in response.text


def test_candidate_api_route_is_not_shadowed_by_static_files(demo_client: TestClient) -> None:
    """INV-005：靜態頁面掛在 /，但 API 路由必須優先比對（FR-107）。

    這是 FastAPI 的路由順序造成的隱含相依。它今天成立，但沒有任何東西
    保證明天還成立——除了這個測試。
    """
    response = demo_client.get("/candidate/session/demo-candidate-001")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["job_title"]


def test_candidate_api_still_rejects_unknown_tokens(demo_client: TestClient) -> None:
    """安全模型未因路徑調整而鬆動：不存在的 token 仍是 404，不落到靜態檔。"""
    response = demo_client.get("/candidate/session/not-a-real-token")
    assert response.status_code == 404


def test_internal_pages_are_untouched(demo_client: TestClient) -> None:
    """NFR-002：HR 與主管介面不受本次變更影響。"""
    assert "考核總覽" in demo_client.get("/").text
    assert "主管 Hub" in demo_client.get("/manager.html").text


def test_every_element_in_the_dom_contract_exists_in_the_markup() -> None:
    """ui/elements.js 是這一頁的 DOM 契約，標記必須提供其中每一個 id。

    改版時最容易發生的退化就是動到 id：JS 拿到 null，畫面看起來只是「某塊沒東西」，
    不會拋錯，也不會有任何測試失敗——除了這一項。
    """
    contract = _read(CANDIDATE_DIR / "ui" / "elements.js")
    markup = _read(CANDIDATE_DIR / "assessment.html")

    required = set(re.findall(r"""el\(['"]([^'"]+)['"]\)""", contract))
    present = set(re.findall(r"""\bid=["']([^"']+)["']""", markup))

    assert required, "elements.js 應查找至少一個 id，否則本檢查失去意義"
    missing = sorted(required - present)
    assert not missing, f"assessment.html 缺少 elements.js 需要的 id：{missing}"


def test_candidate_page_styles_are_locally_owned() -> None:
    """樣式表隨頁面出貨，不依賴 CSS CDN（NFR-007）。"""
    markup = _read(CANDIDATE_DIR / "assessment.html")
    assert "./css/candidate.css" in markup
    assert (CANDIDATE_DIR / "css" / "candidate.css").is_file()
    # 版面不得再依賴 Tailwind CDN——設計稿是精確數值，且少一個 CDN 少一種破版模式
    assert "tailwindcss.com" not in markup


def test_candidate_page_does_not_reference_internal_scripts() -> None:
    """應徵者頁面不得載入內部介面的腳本。"""
    markup = _read(CANDIDATE_DIR / "assessment.html")
    assert "hr.js" not in markup
    assert "manager.js" not in markup
