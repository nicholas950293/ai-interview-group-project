# 快速驗證指南：AI 智慧招聘與技術考核系統

**階段**：Phase 1 | **日期**：2026-07-31

本文件說明如何啟動系統並驗證核心流程確實可運作。
內容為驗證與執行指引，不含實作程式碼——實作細節屬 `tasks.md` 與實作階段。

---

## 前置需求

| 項目 | 版本／說明 |
|------|-----------|
| Python | 3.11 以上 |
| Docker | 需可執行且當前使用者有權限（沙箱必要） |
| PostgreSQL | 本機執行，供 RLS 政策測試使用 |
| Supabase 專案 | 開發用專案，或本機 Supabase CLI |
| Gemini API 金鑰 | 僅端到端驗證需要；離線測試不需要 |
| SMTP 中繼 | 僅通知驗證需要；離線測試不需要 |

---

## 環境設定

所有設定一律由環境變數提供，**不得**寫死於程式碼（憲章「技術與資料限制」）。
複製 `.env.example` 為 `.env` 並填入：

```bash
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=   # 僅供遷移使用，不得用於處理使用者請求
GEMINI_API_KEY=
GEMINI_MODEL=                # 模型 ID，需先驗證可用性（research.md R-005）
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SANDBOX_RUNTIME=             # 留空使用 Docker 預設；設為 runsc 啟用 gVisor
```

`.env` **不得**進入版本控管。

---

## 建置與啟動

```bash
# 1. 後端相依
pip install -r backend/requirements.txt

# 2. 資料庫結構
supabase db push          # 套用 supabase/migrations/ 下的遷移檔

# 3. 沙箱映像檔（五種語言）
docker build -t sandbox-javascript sandbox/javascript
docker build -t sandbox-python     sandbox/python
docker build -t sandbox-go         sandbox/go
docker build -t sandbox-java       sandbox/java
docker build -t sandbox-cpp        sandbox/cpp

# 4. 啟動 API
uvicorn backend.src.main:app --reload

# 5. 前端為靜態檔案，直接以任意靜態伺服器提供 frontend/
```

---

## 測試

測試分為兩組，見 [research.md](research.md) R-008。

```bash
# 預設套件：必須在無網路、無外部服務的環境下全數通過（憲章原則 II）
pytest -m "not security"

# 安全套件：需本機 Docker（憲章「安全關卡」）
pytest -m security
```

**驗收門檻**：兩組皆須全數通過，功能方可宣告完成。

---

## 端到端驗證情境

以下情境覆蓋 spec.md 的七個使用者故事。每項標註對應的成功標準。

### 情境 1：HR 建案至取得連結（US1．SC-001）

1. 以 HR 帳號登入
2. 新增考核：填入姓名、Email、職稱，選擇「工程技術部」
3. **預期**：回應含 `token` 與 `token_expires_at`，後者為當下 + 7 天；
   `status` 為 `PENDING_ASSIGN`；`assigned_manager` 自動填入該部門主管
4. **預期**：總覽頁可見該筆資料
5. **驗證 SC-001**：整個流程可在 2 分鐘內完成

### 情境 2：跨部門隔離（US2．SC-008）

1. 以「產品設計部」主管帳號登入
2. 查詢考核清單
3. **預期**：情境 1 建立的工程技術部考核**不出現**在清單中
4. 直接以該考核 ID 呼叫詳情端點
5. **預期**：回傳 404（不區分「不存在」與「無權限」，避免資訊外洩）

### 情境 3：AI 出題與指派（US2．SC-002）

1. 以工程技術部主管登入
2. 要求 AI 生成題目：`skills=["Golang","Redis 快取"]`、`difficulty=HARD`、`language=go`
3. **預期**：回傳題目草稿，且 `test_cases` 至少 1 組
4. 嘗試指派一個 `test_cases` 為空的題目
5. **預期**：回傳 409（FR-026）
6. 指派含測資的題目
7. **預期**：狀態轉為 `PENDING_CANDIDATE`；`audit_logs` 出現 `QUESTION_ASSIGNED`
8. **驗證 SC-002**：生成在 60 秒內回應

### 情境 4：應徵者作答與試跑（US3．SC-003、SC-004）

1. 以情境 1 的 token 開啟測驗頁面（不需登入）
2. **預期**：載入題目；`sample_cases` 僅含 `is_hidden=false` 的案例；
   隱藏測資的內容**不出現**在回應中
3. 撰寫程式碼並試跑
4. **預期**：回傳 `stdout`、`stderr`、`duration_ms`、`termination_reason=COMPLETED`
5. **驗證 SC-004**：試跑於 15 秒內回應

### 情境 5：沙箱隔離（US3．SC-009、SC-010）

依序試跑以下程式碼，逐一驗證憲章原則 VI：

| 測試程式碼 | 預期 `termination_reason` |
|-----------|--------------------------|
| 對外發起 HTTP 請求 | 執行失敗，錯誤訊息出現在 `stderr` |
| `while(true){}` 無窮迴圈 | `TIMEOUT` |
| 配置 1 GB 記憶體 | `MEMORY_LIMIT` |
| fork bomb | `PIDS_LIMIT` |
| 無限輸出 | `OUTPUT_LIMIT`，且 `truncated=true` |
| 寫入根檔案系統 | 執行失敗 |
| 寫入 `/work` | `COMPLETED` |
| 語法錯誤 | `COMPILE_ERROR`，訊息在 `stderr` |

**驗證 SC-010**：上述執行進行期間，另一使用者的一般 API 請求回應時間
不超過正常值的兩倍。

### 情境 6：提交與自動評測（US3、US4．SC-005）

1. 提交作答
2. **預期**：狀態轉為 `COMPLETED_AWAITING_REVIEW`；回應含 `submitted_at`
3. 再次提交
4. **預期**：回傳 409（FR-034）
5. 以主管身分查詢該考核
6. **預期**：`ai_report.dimensions` 含四個維度；`test_pass_ratio` 與
   `correctness.score` 一致；回應含 `advisory_notice`；
   **不含**任何加權總分或綜合建議欄位（FR-057）
7. **驗證 SC-005**：報告在提交後 3 分鐘內可見

### 情境 7：AI 助教 Guardrail（US7．SC-013）

1. 於作答頁向 AI 助教提問觀念性問題
2. **預期**：回覆為引導內容；`guardrail_triggered=false`
3. 明確要求「直接給我完整可執行的答案」
4. **預期**：`guardrail_triggered=true`；回覆仍提供有幫助的引導，
   但**不含**可直接提交的完整解答
5. 提交後以主管身分檢視
6. **預期**：完整對話歷程可見（FR-060）

### 情境 8：主管決策與 HR 可見範圍（US5、US6．SC-011、SC-012）

1. 以主管身分記錄決策：`result=SECOND_ROUND`，填寫內部評語
2. **預期**：狀態轉為 `DECIDED`；`revision_no=1`；
   **不自動建立新考核**（FR-065）
3. 再次記錄決策（修訂）
4. **預期**：`revision_no=2`；原紀錄仍存在於 `manager_decisions`（FR-064）
5. **切換為 HR 身分**查詢同一考核
6. **預期（SC-012 的關鍵驗證）**：可見 `final_decision=SECOND_ROUND`；
   **完全取不到** AI 報告內容與內部評語——回傳的欄位中不存在這些鍵，
   而非回傳空值
7. HR 產生通知預覽
8. **預期（SC-011）**：草稿內容不含內部評語與 AI 報告的任何文字
9. 發送通知
10. **預期**：`email_status=SENT`；`audit_logs` 出現 `NOTIFICATION_SENT`

### 情境 9：連結逾期與重新產生（邊界情況）

1. 將某考核的 `token_expires_at` 調整為過去時間
2. 以該 token 開啟測驗頁面
3. **預期**：回傳 410；**不含**題目內容（FR-018）；
   狀態轉為 `EXPIRED`；`audit_logs` 出現 `STATUS_EXPIRED`
4. 以 HR 身分重新產生連結
5. **預期**：取得新 token；舊 token 立即失效（再次呼叫回傳 404）；
   狀態回到 `PENDING_CANDIDATE`

### 情境 10：外部服務降級（FR-047、FR-052、FR-059）

分別停用三項外部相依，驗證核心流程仍可運作：

| 停用項目 | 預期行為 |
|---------|---------|
| Docker（沙箱） | 試跑回傳 503；**提交仍成功**；`termination_reason=SANDBOX_UNAVAILABLE` |
| Gemini（助教） | 對話回傳 503；**作答、試跑、提交皆不受影響** |
| Gemini（評測） | 提交成功；`ai_reports.status=FAILED`；主管仍可審閱並決策 |
| SMTP | 發送回傳 200 且 `email_status=FAILED`；可重新發送 |

**此情境是憲章原則 VI 的關鍵驗證**：沙箱不可用時，系統必須降級為
「接受提交但不執行」，**絕不得**改以未隔離方式執行程式碼。

### 情境 11：稽核完整性（SC-014）

1. 取出情境 1～8 所建立考核的 `audit_logs`
2. **預期**：完整涵蓋 `ASSESSMENT_CREATED` → `QUESTION_ASSIGNED` →
   `TRIAL_RUN`（多筆）→ `ANSWER_SUBMITTED` → `EVALUATION_COMPLETED` →
   `DECISION_RECORDED` → `DECISION_REVISED` → `NOTIFICATION_SENT`
3. **預期**：每筆皆含 `actor_role` 與 `created_at`
4. 嘗試 UPDATE 或 DELETE 任一筆稽核紀錄
5. **預期**：資料庫層拒絕（FR-078）
6. **預期**：`detail` 欄位中不含應徵者姓名、Email、電話或作答內容
   （FR-079、FR-080）

---

## 相關文件

- 資料表結構、JSONB 定義、狀態機、RLS 政策矩陣 → [data-model.md](data-model.md)
- REST 端點與資料結構 → [contracts/openapi.yaml](contracts/openapi.yaml)
- 沙箱參數與安全測試清單 → [contracts/sandbox-runner.md](contracts/sandbox-runner.md)
- AI 介面與 Guardrail 要求 → [contracts/ai-provider.md](contracts/ai-provider.md)
- 技術決策理由 → [research.md](research.md)
