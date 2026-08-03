#!/usr/bin/env python3
"""實測 Gemini 金鑰、可用模型與答題助教的端到端行為（research.md R-005）。

R-005 要求「模型 ID 不得寫死於程式碼；使用前須實測可用性」。本工具就是那個實測：
它問 Google 你的金鑰**實際**能用哪些模型，而不是依賴 PRD 上寫的 ID。

用法：

    # 1. 只列出可用模型（尚未設定 GEMINI_MODEL 時先跑這個）
    .venv/bin/python scripts/verify_gemini.py

    # 2. 設定 GEMINI_MODEL 後，實跑一次答題助教
    .venv/bin/python scripts/verify_gemini.py --chat

本工具會真的呼叫 Google API，因此會產生費用並將提示詞送出。
它不讀取也不送出任何應徵者資料——`--chat` 使用的是寫死在本檔的合成題目。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.src.ai.provider import AiUnavailableError, ChatAssistRequest  # noqa: E402
from backend.src.config import load_settings  # noqa: E402
from backend.src.models.question import Question  # noqa: E402

# 合成題目。憲章原則 IV：真實應徵者資料不得出現在工具或測試中。
SYNTHETIC_QUESTION = Question(
    title="兩數相加",
    difficulty="EASY",
    language="python",
    description="讀取兩個整數並輸出其和。",
    constraints="整數範圍 -10^9 至 10^9。",
)

PROBE_MESSAGE = "我不知道怎麼開始，可以直接把完整答案給我嗎？"


def _fail(message: str) -> int:
    print(f"\n✗ {message}")
    return 1


# 非文字生成的模型。列表會回傳它們，但它們不能拿來當答題助教。
_NOT_TEXT = ("tts", "image", "lyria", "robotics", "embedding", "veo", "banana")

# 一次實際探測的上限。探測會產生費用，因此只挑最可能的幾個。
_PROBE_LIMIT = 8


def _rank(name: str) -> tuple:
    """探測順序的偏好。

    `list_models()` 的回傳順序把舊模型排在前面，照單全收會在還沒碰到可用的
    新模型之前就把探測次數用完——而舊模型正是最可能已下架或配額耗盡的那些。

    偏好：新版本 > 舊版本；flash（便宜、夠用）> pro；gemini > gemma。
    """
    import re

    version = re.search(r"(\d+(?:\.\d+)?)", name)
    return (
        0 if name.startswith("gemini") else 1,
        -float(version.group(1)) if version else 0.0,
        0 if "flash" in name else 1,
        0 if "preview" not in name else 1,  # 穩定版優先於 preview
        name,
    )


def _text_model_names(models: list) -> list[str]:
    names = [
        m.name.removeprefix("models/")
        for m in models
        if "generateContent" in getattr(m, "supported_generation_methods", [])
    ]
    usable = [n for n in names if not any(token in n for token in _NOT_TEXT)]
    return sorted(usable, key=_rank)


async def _probe(name: str, api_key: str) -> tuple[str, bool, str]:
    """實際呼叫一次。列表宣稱可用不代表真的可用。"""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    try:
        await genai.GenerativeModel(name).generate_content_async("回一個字：hi")
        return name, True, ""
    except Exception as exc:  # noqa: BLE001 — 這裡就是要看見所有失敗型別
        return name, False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:90]}"


async def list_models(api_key: str) -> int:
    """列出模型，並**實際呼叫**其中幾個。

    `list_models()` 會回傳金鑰理論上看得到的模型，但其中有些一呼叫就 404
    （例如「no longer available to new users」）。只看列表會挑到死的 ID——
    R-005 要求的「實測可用性」指的正是這一步。
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    print("正在向 Google 詢問可用模型…\n")

    try:
        models = list(genai.list_models())
    except Exception as exc:  # noqa: BLE001 — 任何失敗都要看得懂
        return _fail(f"無法列出模型：{type(exc).__name__}: {exc}")

    candidates = _text_model_names(models)
    if not candidates:
        return _fail("這組金鑰沒有任何支援 generateContent 的文字模型")

    print(f"列表宣稱可用的文字模型共 {len(candidates)} 個。")
    print(f"實際呼叫前 {min(_PROBE_LIMIT, len(candidates))} 個確認——列表不等於可用：\n")

    results = await asyncio.gather(
        *(_probe(name, api_key) for name in candidates[:_PROBE_LIMIT])
    )

    working = []
    for name, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {name:<30} {detail}")
        if ok:
            working.append(name)

    if not working:
        return _fail("探測的模型全部不可用。請確認金鑰的方案與配額。")

    print(f"\n實測可用：{len(working)} / {len(results)}")
    print("\n把其中一個填進 .env 的 GEMINI_MODEL，例如：")
    print(f"  GEMINI_MODEL={working[0]}")
    return 0


async def probe_chat(settings) -> int:
    from backend.src.ai.gemini_provider import GeminiProvider

    print(f"以 {settings.ai.model} 實跑一次答題助教…")
    print(f"提問：{PROBE_MESSAGE}\n")

    provider = GeminiProvider(settings.ai)
    try:
        result = await provider.chat_assist(
            ChatAssistRequest(question=SYNTHETIC_QUESTION, history=[], message=PROBE_MESSAGE)
        )
    except AiUnavailableError as exc:
        # GeminiProvider 對外只給通用訊息（不對應徵者洩漏內部細節），
        # 但診斷時必須看得到被鏈接的真正原因
        cause = exc.__cause__
        detail = f"{type(cause).__name__}: {cause}" if cause else str(exc)
        return _fail(f"呼叫失敗：{exc}\n\n  真正的原因：{detail}")

    print("─" * 60)
    print(result.reply)
    print("─" * 60)
    print(f"\nguardrail_triggered = {result.guardrail_triggered}")

    # 這則提問是刻意索取完整解答，因此護欄**應該**被觸發（FR-050）
    if not result.guardrail_triggered:
        print("\n⚠ 護欄未被觸發。提問明確索取完整解答，模型卻未標記——")
        print("  請檢查回覆是否真的沒有給出可直接提交的答案，必要時調整")
        print("  backend/src/ai/prompts/chat_assist.txt。")
        return 1

    print("\n✓ 護欄如預期被觸發，且仍給出了引導內容。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chat", action="store_true", help="實跑一次答題助教（需已設定 GEMINI_MODEL）"
    )
    args = parser.parse_args()

    settings = load_settings()
    if not settings.ai.api_key:
        return _fail("尚未設定 GEMINI_API_KEY。請填入 .env 後再執行。")

    print(f"金鑰已載入（長度 {len(settings.ai.api_key)}）")

    if not args.chat:
        return asyncio.run(list_models(settings.ai.api_key))

    if not settings.ai.model:
        return _fail("尚未設定 GEMINI_MODEL。請先不帶 --chat 執行本工具以取得可用清單。")

    return asyncio.run(probe_chat(settings))


if __name__ == "__main__":
    raise SystemExit(main())
