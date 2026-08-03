"""AI 供應商的選擇邏輯（spec 003 之後的 AI 接入）。

這裡守的核心問題是：**什麼情況下會有真實的 API 呼叫發生。**

呼叫真實模型會產生費用，並把提示詞內容送出本機。因此「哪些能力走真的」
必須是一個明確、可預期、且可被測試斷言的決定——不能取決於「.env 裡剛好
有沒有金鑰」這種偶然。
"""

from __future__ import annotations

import pytest

from backend.src.ai.fake_provider import FakeAiProvider
from backend.src.ai.scoped_provider import (
    ALL_FEATURES,
    CHAT_ASSIST,
    DEFAULT_LIVE_FEATURES,
    EVALUATE,
    GENERATE_QUESTION,
    ScopedAiProvider,
    parse_live_features,
)
from backend.src.config import load_settings
from backend.src.main import _default_ai_provider

BASE_ENV = {
    "SUPABASE_URL": "https://synthetic.invalid",
    "SUPABASE_ANON_KEY": "anon-key-synthetic",
    "SUPABASE_JWT_SECRET": "synthetic-secret",  # noqa: S105 — 合成測試資料
}
WITH_KEY = BASE_ENV | {"GEMINI_API_KEY": "synthetic-key", "GEMINI_MODEL": "synthetic-model"}


# ── AI_LIVE_FEATURES 的解析 ───────────────────────────────────────────


def test_default_is_chat_assist_only() -> None:
    """預設只開答題助教。

    evaluate 每次提交都會自動呼叫並送出完整作答；讓它因為「金鑰剛好存在」
    就默默啟用，會使成本與資料流向都不是有意識的決定。
    """
    assert parse_live_features(None) == DEFAULT_LIVE_FEATURES
    assert parse_live_features("") == DEFAULT_LIVE_FEATURES
    assert parse_live_features("   ") == DEFAULT_LIVE_FEATURES
    assert DEFAULT_LIVE_FEATURES == frozenset({CHAT_ASSIST})


def test_all_opens_every_capability() -> None:
    assert parse_live_features("all") == ALL_FEATURES


def test_none_closes_every_capability() -> None:
    assert parse_live_features("none") == frozenset()


def test_explicit_list_is_honoured() -> None:
    assert parse_live_features("chat_assist,evaluate") == {CHAT_ASSIST, EVALUATE}
    assert parse_live_features(" GENERATE_QUESTION , chat_assist ") == {
        GENERATE_QUESTION,
        CHAT_ASSIST,
    }


def test_unknown_names_are_ignored_not_guessed() -> None:
    """設定錯字不得靜默地打開或關掉某項能力。"""
    assert parse_live_features("chat_assist,chatassist,typo") == {CHAT_ASSIST}
    assert parse_live_features("typo-only") == frozenset()


# ── 分派 ──────────────────────────────────────────────────────────────


class _Marker:
    """以可辨識的回傳值標示「這次走了哪一邊」。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[str] = []

    async def generate_question(self, req):  # noqa: ANN001, ANN201
        self.calls.append("generate_question")
        return self.label

    async def chat_assist(self, req):  # noqa: ANN001, ANN201
        self.calls.append("chat_assist")
        return self.label

    async def evaluate(self, req):  # noqa: ANN001, ANN201
        self.calls.append("evaluate")
        return self.label


@pytest.mark.asyncio
async def test_only_the_enabled_capability_reaches_the_live_provider() -> None:
    live, fallback = _Marker("live"), _Marker("fallback")
    provider = ScopedAiProvider(live, fallback, frozenset({CHAT_ASSIST}))

    assert await provider.chat_assist(None) == "live"
    assert await provider.generate_question(None) == "fallback"
    assert await provider.evaluate(None) == "fallback"

    assert live.calls == ["chat_assist"]
    assert sorted(fallback.calls) == ["evaluate", "generate_question"]


@pytest.mark.asyncio
async def test_no_enabled_capability_means_nothing_reaches_the_live_provider() -> None:
    live, fallback = _Marker("live"), _Marker("fallback")
    provider = ScopedAiProvider(live, fallback, frozenset())

    await provider.chat_assist(None)
    await provider.generate_question(None)
    await provider.evaluate(None)

    assert live.calls == []


# ── 組裝：什麼情況下才會出現真實供應商 ────────────────────────────────


def test_without_a_key_the_provider_is_a_fake() -> None:
    assert isinstance(_default_ai_provider(load_settings(env=BASE_ENV)), FakeAiProvider)


def test_a_partial_key_is_not_enough() -> None:
    """只有金鑰沒有模型（或反之）都不算設定完成。"""
    only_key = BASE_ENV | {"GEMINI_API_KEY": "synthetic-key"}
    only_model = BASE_ENV | {"GEMINI_MODEL": "synthetic-model"}

    assert isinstance(_default_ai_provider(load_settings(env=only_key)), FakeAiProvider)
    assert isinstance(_default_ai_provider(load_settings(env=only_model)), FakeAiProvider)


def test_with_a_key_only_the_configured_capabilities_go_live() -> None:
    provider = _default_ai_provider(load_settings(env=WITH_KEY))
    assert isinstance(provider, ScopedAiProvider)
    assert provider.live_features == frozenset({CHAT_ASSIST})


def test_explicitly_disabling_everything_falls_back_entirely() -> None:
    """AI_LIVE_FEATURES=none 必須完全不接觸真實供應商，即使金鑰齊全。"""
    provider = _default_ai_provider(load_settings(env=WITH_KEY | {"AI_LIVE_FEATURES": "none"}))
    assert isinstance(provider, FakeAiProvider)


def test_demo_mode_no_longer_forces_a_fake_provider() -> None:
    """demo 模式的意義是「資料與基礎設施用假的」，與 AI 金鑰是兩件事。

    這讓「記憶體資料 + 真實 AI」成為可行的本機組態——否則要在本機驗證
    AI 助教，就得先架好整套 Supabase。
    """
    demo_with_key = {"LOCAL_DEMO_MODE": "1"} | WITH_KEY
    provider = _default_ai_provider(load_settings(env=demo_with_key))
    assert isinstance(provider, ScopedAiProvider)


def test_demo_mode_without_a_key_is_still_entirely_fake() -> None:
    provider = _default_ai_provider(load_settings(env={"LOCAL_DEMO_MODE": "1"}))
    assert isinstance(provider, FakeAiProvider)


# ── 離線測試套件的防護 ────────────────────────────────────────────────


def test_the_offline_suite_never_uses_a_live_provider(app) -> None:
    """整組測試都必須走替身——否則測試會花錢、會不穩定、會把內容送出本機。

    `conftest.py` 的 `app` 夾具明確注入 `FakeAiProvider`，本測試釘住那個保證：
    日後若有人拿掉注入，改由 `.env` 決定，這裡會立刻失敗。
    """
    assert isinstance(app.state.ai_provider, FakeAiProvider)
