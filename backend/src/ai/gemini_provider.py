"""Gemini 實作（research.md R-005）。

模型 ID 一律來自環境變數 `GEMINI_MODEL`，**不得**寫死於程式碼——預覽版模型的
ID 與可用性會變動，把它寫進程式碼會製造一個必然發生的維護債。

提示詞存放於 `prompts/` 的獨立檔案並納入版本控管，使其可被審查與調整
而不需改動程式碼。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from backend.src.ai.provider import (
    AiGenerationError,
    AiUnavailableError,
    ChatAssistRequest,
    ChatAssistResult,
    EvaluateRequest,
    EvaluationResult,
    GenerateQuestionRequest,
)
from backend.src.config import AiSettings
from backend.src.models.question import (
    DeptType,
    MissingTestCasesError,
    Question,
    QuestionSource,
)
from backend.src.models.report import (
    DIMENSION_NAMES,
    SCORE_MAX,
    SCORE_MIN,
    Dimension,
    ExecutionResult,
    TestResults,
)

PROMPTS_DIR = pathlib.Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def parse_json_response(text: str) -> Any:
    """自模型回應中取出 JSON。

    模型偶爾會加上 ```json 圍欄或前後說明文字，即使提示詞明確要求不要。
    這裡容忍那種情況，但不容忍解析失敗——格式不符即視為服務不可用
    （contracts/ai-provider.md 失敗行為）。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise AiUnavailableError("AI 回應格式不符，無法解析")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AiUnavailableError("AI 回應格式不符，無法解析") from exc


class GeminiProvider:
    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings

    @property
    def model_id(self) -> str:
        if not self._settings.configured:
            raise AiUnavailableError("AI 服務未設定（缺少 GEMINI_API_KEY 或 GEMINI_MODEL）")
        return self._settings.model  # type: ignore[return-value]

    async def _generate(self, prompt: str) -> str:
        model_id = self.model_id
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - 相依未安裝
            raise AiUnavailableError("AI 相依套件未安裝") from exc

        try:
            genai.configure(api_key=self._settings.api_key)
            model = genai.GenerativeModel(model_id)
            response = await model.generate_content_async(prompt)
            return response.text
        except AiUnavailableError:
            raise
        except Exception as exc:  # 外部服務的失敗型別不在我方控制範圍內
            raise AiUnavailableError("AI 服務呼叫失敗") from exc

    async def generate_question(self, req: GenerateQuestionRequest) -> Question:
        prompt = load_prompt("generate_question.txt").format(
            skills="、".join(req.skills),
            difficulty=str(req.difficulty),
            language=str(req.language),
            dept_type=str(req.dept_type),
        )
        payload = parse_json_response(await self._generate(prompt))

        try:
            question = Question(
                source=QuestionSource.AI_GENERATED,
                title=payload.get("title", ""),
                category=payload.get("category"),
                difficulty=payload.get("difficulty", req.difficulty),
                language=payload.get("language", req.language),
                description=payload.get("description", ""),
                constraints=payload.get("constraints"),
                test_cases=payload.get("test_cases", []),
            )
        except Exception as exc:
            raise AiGenerationError("AI 產生的題目結構不合法") from exc

        # 硬性要求：缺測資即視為生成失敗，不得回傳缺測資的題目——
        # 否則錯誤會延後到指派階段才被發現（contracts/ai-provider.md）
        try:
            question.require_test_cases_for(DeptType(req.dept_type))
        except MissingTestCasesError as exc:
            raise AiGenerationError(str(exc)) from exc

        return question

    async def chat_assist(self, req: ChatAssistRequest) -> ChatAssistResult:
        history = "\n".join(f"{m.role}：{m.content}" for m in req.history) or "（尚無對話）"
        prompt = load_prompt("chat_assist.txt").format(
            title=req.question.title,
            description=req.question.description,
            constraints=req.question.constraints or "（無）",
            history=history,
            message=req.message,
        )
        payload = parse_json_response(await self._generate(prompt))

        reply = str(payload.get("reply") or "").strip()
        if not reply:
            raise AiUnavailableError("AI 助教未回傳有效內容")

        return ChatAssistResult(
            reply=reply,
            guardrail_triggered=bool(payload.get("guardrail_triggered", False)),
        )

    async def evaluate(self, req: EvaluateRequest) -> EvaluationResult:
        prompt = load_prompt("evaluate.txt").format(
            title=req.question.title,
            description=req.question.description,
            constraints=req.question.constraints or "（無）",
            language=str(req.language) if req.language else "（非程式作答）",
            answer=req.answer,
            test_summary=_summarize_tests(req.test_results),
            execution_summary=_summarize_execution(req.execution),
            chat_summary=(
                "\n".join(f"{m.role}：{m.content}" for m in req.chat_history) or "（無對話）"
            ),
        )
        payload = strip_aggregate_judgement(parse_json_response(await self._generate(prompt)))
        ratio = req.test_results.pass_ratio if req.test_results is not None else None

        return EvaluationResult(
            dimensions=build_dimensions(payload, test_pass_ratio=ratio),
            model_id=self.model_id,
        )


# ── 回應處理 ───────────────────────────────────────────────────────────
# 這些函式刻意置於類別之外：它們是純函式，因此可在完全離線的情況下測試，
# 而 FR-057 的執行點就在其中（憲章原則 II）。

# 任何形式的整體判斷。FR-057 與憲章原則 V 禁止系統自動產生綜合建議，
# 因此即使模型輸出了，也必須在傳到下游之前剝除。
AGGREGATE_KEYS = frozenset(
    {
        "total",
        "total_score",
        "overall",
        "overall_score",
        "overall_comment",
        "weighted_score",
        "weighted_total",
        "recommendation",
        "hiring_recommendation",
        "verdict",
        "conclusion",
        "final_score",
        "summary",
    }
)


def strip_aggregate_judgement(payload: Any) -> Any:
    """遞迴移除任何綜合判斷欄位（FR-057）。"""
    if isinstance(payload, dict):
        return {
            key: strip_aggregate_judgement(value)
            for key, value in payload.items()
            if str(key).lower() not in AGGREGATE_KEYS
        }
    if isinstance(payload, list):
        return [strip_aggregate_judgement(item) for item in payload]
    return payload


def build_dimensions(
    payload: dict[str, Any], *, test_pass_ratio: float | None
) -> dict[str, Dimension]:
    """建立四維度評分。

    `correctness` 的分數在有測資結果時**一律**以 `pass_ratio` 覆寫，
    而非讓模型自由裁量——這是 FR-054「客觀依據」的來源。模型的說明文字
    仍予保留，因為那部分確實需要判斷力。
    """
    raw = payload.get("dimensions")
    if not isinstance(raw, dict):
        raise AiUnavailableError("AI 回應缺少 dimensions")

    missing = [name for name in DIMENSION_NAMES if name not in raw]
    if missing:
        raise AiUnavailableError("AI 回應缺少維度：" + "、".join(missing))

    dimensions: dict[str, Dimension] = {}
    for name in DIMENSION_NAMES:
        entry = raw[name] if isinstance(raw[name], dict) else {}
        score = _clamp_score(entry.get("score"))
        comment = str(entry.get("comment") or "").strip() or "（模型未提供說明）"

        if name == "correctness":
            if test_pass_ratio is not None:
                score = _clamp_score(round(test_pass_ratio * 100))
            else:
                comment = f"未經測資驗證（沙箱不可用）。{comment}"

        dimensions[name] = Dimension(score=score, comment=comment)
    return dimensions


def _clamp_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 0
    return max(SCORE_MIN, min(SCORE_MAX, score))


def _summarize_tests(test_results: TestResults | None) -> str:
    if test_results is None:
        return "沙箱不可用，本次未執行測試案例。"
    lines = [f"通過 {test_results.passed}/{test_results.total}（比例 {test_results.pass_ratio}）"]
    # 只列名稱與結果，不列輸入輸出——隱藏測資不得經由提示詞外流
    lines += [
        f"- {case.name}：{'通過' if case.passed else '未通過'}（{case.termination_reason}）"
        for case in test_results.cases
    ]
    return "\n".join(lines)


def _summarize_execution(execution: ExecutionResult | None) -> str:
    if execution is None:
        return "無執行紀錄。"
    return (
        f"中止原因 {execution.termination_reason}、"
        f"退出碼 {execution.exit_code}、耗時 {execution.duration_ms} ms"
    )
