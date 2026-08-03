"""讓 AI 能力可以逐項接上真實模型。

`AiProvider` 是單一介面，涵蓋三項能力：出題、答題助教、提交後評測。
但這三項的風險與成本並不相同——

* `chat_assist` 由應徵者主動觸發，一次一則，最容易觀察品質
* `generate_question` 由主管主動觸發
* `evaluate` **每次提交都會自動執行**，且會把應徵者的完整作答送給外部模型

因此「接上 AI」不該是一個全有全無的開關。本模組讓每項能力各自決定要走
真實供應商還是替身，使上線可以從最容易驗證的那一項開始。
"""

from __future__ import annotations

from typing import Any

from backend.src.ai.provider import (
    ChatAssistRequest,
    ChatAssistResult,
    EvaluateRequest,
    EvaluationResult,
    GenerateQuestionRequest,
)
from backend.src.models.question import Question

CHAT_ASSIST = "chat_assist"
GENERATE_QUESTION = "generate_question"
EVALUATE = "evaluate"

ALL_FEATURES = frozenset({CHAT_ASSIST, GENERATE_QUESTION, EVALUATE})

# 預設只讓答題助教走真實模型。
#
# 這是刻意保守的預設：evaluate 每次提交都會自動呼叫並送出完整作答，
# 若因為「.env 剛好有金鑰」就默默啟用，成本與資料流向都不是有意識的決定。
# 要放寬只需設定 AI_LIVE_FEATURES，不需要改程式碼。
DEFAULT_LIVE_FEATURES = frozenset({CHAT_ASSIST})


def parse_live_features(raw: str | None) -> frozenset[str]:
    """解析 `AI_LIVE_FEATURES`。

    `all` 表示三項全開；空值採用預設；未知名稱一律忽略——設定錯字不應該
    靜默地把某項能力打開或關掉，而忽略未知值至少不會產生意外的行為。
    """
    if raw is None or not raw.strip():
        return DEFAULT_LIVE_FEATURES

    tokens = {token.strip().lower() for token in raw.split(",") if token.strip()}
    if "all" in tokens:
        return ALL_FEATURES
    if "none" in tokens:
        return frozenset()
    return frozenset(tokens & ALL_FEATURES)


class ScopedAiProvider:
    """把指定的能力交給真實供應商，其餘沿用替身。"""

    def __init__(self, live: Any, fallback: Any, features: frozenset[str]) -> None:
        self._live = live
        self._fallback = fallback
        self._features = features

    @property
    def live_features(self) -> frozenset[str]:
        return self._features

    def _pick(self, feature: str) -> Any:
        return self._live if feature in self._features else self._fallback

    async def generate_question(self, req: GenerateQuestionRequest) -> Question:
        return await self._pick(GENERATE_QUESTION).generate_question(req)

    async def chat_assist(self, req: ChatAssistRequest) -> ChatAssistResult:
        return await self._pick(CHAT_ASSIST).chat_assist(req)

    async def evaluate(self, req: EvaluateRequest) -> EvaluationResult:
        return await self._pick(EVALUATE).evaluate(req)
