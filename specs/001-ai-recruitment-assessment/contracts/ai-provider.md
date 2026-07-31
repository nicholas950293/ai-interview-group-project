# 契約：AiProvider（AI 服務介面）

**對應需求**：FR-024、FR-027、FR-049～FR-059 | **憲章依據**：原則 II、原則 V
**研究決策**：[research.md](../research.md) R-005

AI 有三種用途：出題、答題助教、自動評測。三者共用同一介面，
以便測試以單一替身取代（憲章原則 II 要求測試套件離線可執行）。

---

## 介面定義

```python
class AiProvider(Protocol):
    async def generate_question(self, req: GenerateQuestionRequest) -> Question: ...
    async def chat_assist(self, req: ChatAssistRequest) -> ChatAssistResult: ...
    async def evaluate(self, req: EvaluateRequest) -> EvaluationResult: ...
```

模型 ID 由環境變數 `GEMINI_MODEL` 提供，**不得**寫死於程式碼（R-005）。
實際使用的模型 ID 必須回傳並記錄於 `ai_reports.model_id`，以確保評測結果可追溯。

提示詞存放於 `backend/src/ai/prompts/` 的獨立檔案，納入版本控管，
使其可被審查與調整而不需改動程式碼。

---

## 1. `generate_question`（出題）

### 請求

| 欄位 | 型別 | 說明 |
|------|------|------|
| `skills` | `list[str]` | 能力指標，如 `["Golang", "Redis 快取"]` |
| `difficulty` | `Difficulty` | `EASY` / `MEDIUM` / `HARD` |
| `language` | `Language` | 適用語言 |
| `dept_type` | `DeptType` | `ENGINEERING` / `NON_ENGINEERING` |

### 回應

回傳 `Question`（結構見 [openapi.yaml](openapi.yaml) 的 `Question` schema）。

**硬性要求**：`dept_type = ENGINEERING` 時，`test_cases` 必須至少含 1 組
且每組 `stdin` 與 `expected_stdout` 皆非空（FR-022、FR-026）。
未滿足時實作必須視為生成失敗並拋出 `AiGenerationError`，
**不得**回傳缺測資的題目——否則錯誤會延後到指派階段才被發現。

### 失敗行為

服務不可用或回應格式不符時拋出 `AiUnavailableError`。
API 層轉為 HTTP 503，前端保留主管輸入（FR-027）。

---

## 2. `chat_assist`（答題助教）

### 請求

| 欄位 | 型別 | 說明 |
|------|------|------|
| `question` | `Question` | 當前題目（含隱藏測資，供 AI 判斷但不得洩漏） |
| `history` | `list[ChatMessage]` | 既有對話歷程 |
| `message` | `str` | 應徵者本次提問 |
| `current_code` | `str \| None` | 應徵者當前程式碼 |

### 回應

| 欄位 | 型別 | 說明 |
|------|------|------|
| `reply` | `str` | 觀念引導回覆，繁體中文 |
| `guardrail_triggered` | `bool` | 是否攔截了索取完整解答的請求 |

### Guardrail 要求（FR-050）

回覆**不得**包含：

- 可直接提交的完整解答
- 完整且可執行的函式或程式
- 隱藏測試案例的內容

允許：觀念說明、思路拆解、相關知識、對既有程式碼的問題指出（不直接給修正碼）、
不超過 3 行的示意片段。

`guardrail_triggered` 為 `true` 時仍須回傳有幫助的引導內容，
**不得**僅回傳拒絕訊息——否則會傷害作答體驗且無法達成 SC-013 的品質目標。

此欄位是 SC-013（索取完整解答時直接給出可提交答案的比率低於 1%）的量測依據，
必須寫入 `ai_chat_history`。

### 失敗行為

拋出 `AiUnavailableError`。API 層轉為 HTTP 503。
作答、試跑與提交功能**不得**受影響（FR-052）。

---

## 3. `evaluate`（自動評測）

### 請求

| 欄位 | 型別 | 說明 |
|------|------|------|
| `question` | `Question` | 含完整測資 |
| `answer` | `str` | 應徵者作答 |
| `language` | `Language \| None` | 非工程類為 `None` |
| `execution` | `ExecutionResult \| None` | 沙箱執行結果 |
| `test_results` | `TestResults \| None` | 測資通過情形 |
| `chat_history` | `list[ChatMessage]` | 供評估解決問題思路 |

### 回應

| 欄位 | 型別 | 說明 |
|------|------|------|
| `dimensions` | `dict[str, Dimension]` | 四維度，皆必填 |
| `model_id` | `str` | 實際使用的模型 |

四個維度為 `correctness`、`maintainability`、`performance`、`security`，
每個含 `score`（0–100 整數）與 `comment`（繁體中文）。

### 硬性禁止（FR-057、憲章原則 V）

回應**不得**包含加權總分、綜合評價、錄取傾向或任何形式的整體建議。
若模型輸出含有此類內容，實作必須予以剝除。介面型別本身不提供對應欄位，
使違規在型別層即無法表達。

### 正確性維度的客觀依據（FR-054）

`test_results` 非 `None` 時，`correctness.score` 必須與 `pass_ratio` 一致
（允許誤差在測資權重範圍內）。實作應將 `pass_ratio` 作為該維度評分的
主要輸入，而非讓模型自由裁量——這是「客觀評測」的來源。

`test_results` 為 `None`（沙箱不可用）時，`correctness.comment` 必須明確
標示未經測資驗證。

### 失敗行為

拋出 `AiUnavailableError`。呼叫端寫入 `ai_reports` 的 `status = FAILED`
與 `error_message`，**不得**阻擋提交流程（FR-059）。不做自動重試（R-006）。

---

## `FakeAiProvider`（測試替身）

用於預設離線套件。行為要求：

- `generate_question` 回傳含 2 組測資的固定題目
- `chat_assist` 可設定為觸發或不觸發 guardrail，供 SC-013 相關測試
- `evaluate` 依傳入的 `test_results.pass_ratio` 計算 `correctness.score`，
  其餘三維度回傳固定值——使「正確性與測資一致」的契約可被驗證
- 三個方法皆可設定為拋出 `AiUnavailableError`，供降級路徑測試

**不得**在替身中呼叫任何外部服務。
