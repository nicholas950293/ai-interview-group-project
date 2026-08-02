"""GeminiProvider 的離線可測部分（research.md R-005、contracts/ai-provider.md）。

外部呼叫本身不在離線套件的範圍內（憲章原則 II 要求測試不需外部服務），
但**回應的解析與剝除**完全在我方控制之內，而那正是 FR-057 的執行點：
即使模型輸出了綜合建議，也不得傳到下游。
"""

from __future__ import annotations

import pytest

from backend.src.ai.gemini_provider import (
    build_dimensions,
    load_prompt,
    parse_json_response,
    strip_aggregate_judgement,
)
from backend.src.ai.provider import AiUnavailableError
from backend.src.config import AiSettings
from backend.src.models.report import DIMENSION_NAMES


def test_parses_plain_json():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parses_json_inside_code_fence():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parses_json_with_surrounding_prose():
    assert parse_json_response('好的，這是結果：\n{"a": 1}\n希望有幫助。') == {"a": 1}


@pytest.mark.parametrize("text", ["", "完全沒有 JSON", "{不是合法的 JSON"])
def test_unparseable_response_is_treated_as_unavailable(text):
    with pytest.raises(AiUnavailableError):
        parse_json_response(text)


def test_aggregate_judgement_is_stripped():
    """FR-057：系統不得自動計算加權總分或錄取建議。"""
    payload = {
        "dimensions": {name: {"score": 80, "comment": "說明"} for name in DIMENSION_NAMES},
        "total_score": 80,
        "overall_comment": "整體表現良好，建議錄取",
        "recommendation": "HIRE",
        "summary": "綜合評價",
    }
    cleaned = strip_aggregate_judgement(payload)
    assert set(cleaned) == {"dimensions"}


def test_stripping_is_recursive():
    payload = {
        "dimensions": {
            "correctness": {"score": 80, "comment": "說明", "overall": "不該存在"},
        }
    }
    cleaned = strip_aggregate_judgement(payload)
    assert set(cleaned["dimensions"]["correctness"]) == {"score", "comment"}


def test_build_dimensions_requires_all_four():
    payload = {"dimensions": {"correctness": {"score": 80, "comment": "說明"}}}
    with pytest.raises(AiUnavailableError):
        build_dimensions(payload, test_pass_ratio=None)


def test_correctness_is_overridden_by_pass_ratio():
    """FR-054：pass_ratio 是正確性維度的客觀依據，不由模型自由裁量。"""
    payload = {
        "dimensions": {name: {"score": 99, "comment": f"{name} 說明"} for name in DIMENSION_NAMES}
    }
    dimensions = build_dimensions(payload, test_pass_ratio=0.4)
    assert dimensions["correctness"].score == 40
    assert dimensions["maintainability"].score == 99


def test_correctness_comment_flags_missing_verification():
    payload = {
        "dimensions": {name: {"score": 70, "comment": f"{name} 說明"} for name in DIMENSION_NAMES}
    }
    dimensions = build_dimensions(payload, test_pass_ratio=None)
    assert "未經測資驗證" in dimensions["correctness"].comment


def test_scores_are_clamped_to_the_defined_scale():
    """FR-056：評分尺度必須一致且明確定義。"""
    payload = {
        "dimensions": {
            "correctness": {"score": 250, "comment": "說明"},
            "maintainability": {"score": -10, "comment": "說明"},
            "performance": {"score": 50, "comment": "說明"},
            "security": {"score": 50, "comment": "說明"},
        }
    }
    dimensions = build_dimensions(payload, test_pass_ratio=None)
    assert dimensions["maintainability"].score == 0
    assert dimensions["performance"].score == 50


def test_model_id_comes_from_configuration_not_code():
    """R-005：模型 ID 不得寫死於程式碼。"""
    from backend.src.ai.gemini_provider import GeminiProvider

    provider = GeminiProvider(AiSettings(api_key="k", model="configured-model"))
    assert provider.model_id == "configured-model"

    unconfigured = GeminiProvider(AiSettings(api_key=None, model=None))
    with pytest.raises(AiUnavailableError):
        _ = unconfigured.model_id


@pytest.mark.parametrize("name", ["generate_question.txt", "evaluate.txt", "chat_assist.txt"])
def test_prompts_are_versioned_files(name):
    """提示詞必須與程式邏輯分離，存放於版本控管的獨立檔案（R-005）。"""
    assert load_prompt(name).strip()
