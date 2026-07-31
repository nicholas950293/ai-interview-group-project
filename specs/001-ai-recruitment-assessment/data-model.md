# 資料模型：AI 智慧招聘與技術考核系統

**階段**：Phase 1 | **日期**：2026-07-31 | **規格**：[spec.md](spec.md) | **研究**：[research.md](research.md)

本文件定義 8 張資料表、所有 JSONB 欄位的內部結構、狀態機、RLS 政策矩陣與驗證規則。
每項設計皆標註其來源功能需求編號。

---

## 資料表總覽

| 資料表 | 用途 | 唯附加 | 來源 FR |
|--------|------|:------:|---------|
| `departments` | 部門與其類型 | 否 | FR-010 |
| `internal_users` | HR 與主管帳號 | 否 | FR-001、FR-005 |
| `question_banks` | 部門專屬題庫 | 否 | FR-020～FR-022 |
| `assessments` | 考核主表（含應徵者資訊） | 否 | FR-009、FR-073 |
| `execution_records` | 沙箱執行紀錄 | 是 | FR-044、FR-048 |
| `ai_reports` | AI 評測報告 | 是 | FR-055、FR-059 |
| `manager_decisions` | 主管決策與內部評語 | 是 | FR-061～FR-064 |
| `audit_logs` | 系統稽核歷程 | 是 | FR-076～FR-078 |

相較 PRD 原始的 3 張表，增加的 5 張皆由憲章原則 V 與 FR-007／FR-008 所要求，
理由記於 [plan.md](plan.md) 的「複雜度追蹤」。

---

## 1. `departments`（部門）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | VARCHAR(50) | PK | 部門代碼 |
| `name` | VARCHAR(100) | NOT NULL | 部門名稱 |
| `type` | VARCHAR(30) | CHECK IN ('ENGINEERING','NON_ENGINEERING') | 決定應徵者作答介面形式（FR-029） |

---

## 2. `internal_users`（內部使用者）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `auth_user_id` | UUID | UNIQUE NOT NULL | 對應 Supabase Auth 的使用者 |
| `name` | VARCHAR(100) | NOT NULL | |
| `email` | VARCHAR(150) | UNIQUE NOT NULL | |
| `role` | VARCHAR(20) | CHECK IN ('HR','MANAGER') | FR-001 |
| `dept_id` | VARCHAR(50) | FK → departments，MANAGER 必填、HR 必為 NULL | FR-003 |
| `is_active` | BOOLEAN | DEFAULT true | 離職停用（邊界情況） |

**驗證規則**：

- `role = 'MANAGER'` 時 `dept_id` 不得為 NULL；`role = 'HR'` 時必須為 NULL。
  以 CHECK 約束強制。
- 每個部門至多一位 active 的 MANAGER（假設「一人一主管」）。以部分唯一索引強制。

**JWT claim 對應**：登入時將 `role` 寫入 `app_role`、`dept_id` 寫入 `dept_id`
自訂 claim，供 RLS 使用（R-002）。

---

## 3. `question_banks`（題庫）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `dept_id` | VARCHAR(50) | FK → departments，NOT NULL | FR-003 隔離依據 |
| `title` | VARCHAR(200) | NOT NULL | |
| `category` | VARCHAR(100) | | |
| `difficulty` | VARCHAR(20) | CHECK IN ('EASY','MEDIUM','HARD') | FR-021 |
| `language` | VARCHAR(30) | CHECK IN 五種語言 | |
| `description` | TEXT | NOT NULL | |
| `constraints` | TEXT | | |
| `test_cases` | JSONB | NOT NULL DEFAULT '[]' | FR-022 |
| `created_by` | UUID | FK → internal_users | |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

**驗證規則**：工程類部門的題目，`test_cases` 陣列長度必須 ≥ 1（FR-022、FR-026）。

### `test_cases` JSONB 結構

```json
[
  {
    "name": "基本案例",
    "stdin": "3 5\n",
    "expected_stdout": "8\n",
    "is_hidden": false,
    "timeout_seconds": 10
  }
]
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `name` | string | 是 | 顯示用名稱 |
| `stdin` | string | 是 | 餵給程式的標準輸入 |
| `expected_stdout` | string | 是 | 預期標準輸出，比對時去除尾端空白 |
| `is_hidden` | boolean | 是 | true 則不對應徵者顯示，僅用於評測 |
| `timeout_seconds` | integer | 否 | 單案例逾時，預設 10，不得超過沙箱上限 |

---

## 4. `assessments`（考核主表）

依「二輪面試不自動建立新考核」的決定，本表合併應徵者資訊與單次考核歷程
（[spec.md](spec.md) 假設章節）。同一人重複邀請產生多筆紀錄，以 `email` 關聯。

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `name` | VARCHAR(100) | NOT NULL | 應徵者姓名（個資，FR-079） |
| `email` | VARCHAR(150) | NOT NULL | 個資；同一人多筆紀錄的關聯鍵（FR-082） |
| `phone` | VARCHAR(50) | | 個資 |
| `job_title` | VARCHAR(100) | NOT NULL | |
| `dept_id` | VARCHAR(50) | FK → departments，NOT NULL | RLS 隔離依據 |
| `assigned_manager_id` | UUID | FK → internal_users | FR-011、FR-012 |
| `status` | VARCHAR(40) | CHECK，見狀態機 | FR-073 |
| `token` | VARCHAR(100) | UNIQUE NOT NULL | FR-015、FR-016 |
| `token_expires_at` | TIMESTAMPTZ | NOT NULL | FR-017 |
| `question_snapshot` | JSONB | | 指派時快照（FR-028） |
| `code_language` | VARCHAR(30) | | 應徵者所選語言 |
| `candidate_answer` | TEXT | | 作答內容（FR-080 禁入日誌） |
| `ai_chat_history` | JSONB | DEFAULT '[]' | FR-051 |
| `trial_run_count` | INTEGER | DEFAULT 0 | FR-032 |
| `final_decision` | VARCHAR(20) | CHECK IN ('PASS','SECOND_ROUND','FAIL') | HR 可見的決策結果（FR-007） |
| `email_status` | VARCHAR(30) | CHECK IN ('NOT_SENT','SENT','FAILED') | FR-071 |
| `email_error` | TEXT | | FR-072 |
| `submitted_at` | TIMESTAMPTZ | | FR-034 判定依據 |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

**關鍵設計說明**：`final_decision` 是 `manager_decisions` 最新一筆結果的
去正規化副本，僅存列舉值、**不含評語**。這是 HR 能取得決策結果卻無法取得
評語的機制（FR-007、FR-008、R-003）。寫入時與 `manager_decisions` 於同一交易完成。

**驗證規則**：

- `token` 以密碼學安全亂數產生，長度 ≥ 32 位元組的 URL-safe 編碼（FR-016）
- `submitted_at` 非 NULL 時拒絕任何作答內容變更（FR-034）
- `trial_run_count` 達上限（20）時拒絕試跑但不阻擋提交（FR-032）

### `question_snapshot` JSONB 結構

```json
{
  "source": "BANK",
  "source_id": "uuid-or-null",
  "title": "實作 LRU 快取",
  "category": "資料結構",
  "difficulty": "HARD",
  "language": "go",
  "description": "題目完整描述…",
  "constraints": "時間複雜度須為 O(1)…",
  "test_cases": [],
  "assigned_at": "2026-07-31T10:00:00Z",
  "assigned_by": "uuid"
}
```

`source` 為 `BANK`（取自題庫）或 `AI_GENERATED`（AI 生成後主管確認）。
`test_cases` 結構同 `question_banks.test_cases`。快照後題庫變更不影響本欄（FR-028）。

### `ai_chat_history` JSONB 結構

```json
[
  {
    "role": "candidate",
    "content": "這題的時間複雜度要求是什麼意思？",
    "created_at": "2026-07-31T10:15:00Z"
  },
  {
    "role": "assistant",
    "content": "O(1) 表示…（觀念引導，不含完整解答）",
    "created_at": "2026-07-31T10:15:04Z",
    "guardrail_triggered": false
  }
]
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|:----:|------|
| `role` | string | 是 | `candidate` 或 `assistant` |
| `content` | string | 是 | 訊息內容 |
| `created_at` | string | 是 | ISO 8601 時間 |
| `guardrail_triggered` | boolean | 否 | 僅 assistant；true 表示曾攔截索取完整解答的請求（SC-013 量測依據） |

以 JSONB 陣列而非獨立資料表儲存，是因為對話僅由單一應徵者循序附加，
無併發寫入問題，且無唯附加的稽核要求。此為憲章原則 III 的最小實作選擇。

---

## 5. `execution_records`（沙箱執行紀錄．唯附加）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `assessment_id` | UUID | FK → assessments，NOT NULL | |
| `trigger` | VARCHAR(20) | CHECK IN ('TRIAL_RUN','EVALUATION') | FR-048 |
| `language` | VARCHAR(30) | NOT NULL | |
| `stdout` | TEXT | | 上限 1 MB，超過截斷（FR-044） |
| `stderr` | TEXT | | 上限 1 MB，超過截斷 |
| `exit_code` | INTEGER | | |
| `duration_ms` | INTEGER | | FR-044 |
| `peak_memory_kb` | INTEGER | | 資源用量（FR-048） |
| `termination_reason` | VARCHAR(30) | CHECK IN ('COMPLETED','TIMEOUT','MEMORY_LIMIT','PIDS_LIMIT','OUTPUT_LIMIT','COMPILE_ERROR','SANDBOX_UNAVAILABLE') | FR-040、FR-045、FR-047 |
| `test_results` | JSONB | | 僅 EVALUATION 觸發時填入 |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

**唯附加**：無 UPDATE 與 DELETE 權限，以 RLS 與 GRANT 雙重限制。

### `test_results` JSONB 結構

```json
{
  "total": 5,
  "passed": 4,
  "pass_ratio": 0.8,
  "cases": [
    {
      "name": "基本案例",
      "passed": true,
      "duration_ms": 42,
      "termination_reason": "COMPLETED"
    }
  ]
}
```

`pass_ratio` 是正確性維度的客觀依據（FR-054）。`cases[].actual_stdout`
**不予保存**——避免隱藏測資的預期輸出經由紀錄外洩。

---

## 6. `ai_reports`（AI 評測報告．唯附加）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `assessment_id` | UUID | FK → assessments，NOT NULL | |
| `attempt_no` | INTEGER | NOT NULL，自 1 起 | 重試產生新列（FR-059） |
| `status` | VARCHAR(20) | CHECK IN ('PENDING','SUCCESS','FAILED') | R-006 |
| `dimensions` | JSONB | | 四維度評分 |
| `test_pass_ratio` | NUMERIC(4,3) | | 來自 execution_records |
| `model_id` | VARCHAR(100) | | 實際使用的模型（R-005 可追溯性） |
| `error_message` | TEXT | | status = FAILED 時填入 |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

**唯附加**：僅 `status` 由 `PENDING` 轉為終態時允許一次更新，其餘欄位不可變。
重試一律新增列。

### `dimensions` JSONB 結構

```json
{
  "correctness":     { "score": 80, "comment": "通過 4/5 測試案例，邊界情況…" },
  "maintainability": { "score": 65, "comment": "命名清晰但缺少錯誤處理…" },
  "performance":     { "score": 90, "comment": "時間複雜度符合要求…" },
  "security":        { "score": 70, "comment": "未驗證輸入長度…" }
}
```

四個維度皆必填，`score` 為 0–100 整數（[spec.md](spec.md) 假設章節），
`comment` 為繁體中文說明。

**明確不存在的欄位**：加權總分、綜合建議、錄取傾向。憲章原則 V 與 FR-057
禁止系統自動產生綜合判斷。

---

## 7. `manager_decisions`（主管決策．唯附加）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `assessment_id` | UUID | FK → assessments，NOT NULL | |
| `revision_no` | INTEGER | NOT NULL，自 1 起 | 修訂以新增列呈現（FR-064） |
| `decided_by` | UUID | FK → internal_users，NOT NULL | FR-063 |
| `result` | VARCHAR(20) | CHECK IN ('PASS','SECOND_ROUND','FAIL') | FR-061 |
| `internal_comment` | TEXT | | **HR 不可讀**（FR-007、FR-066） |
| `decided_at` | TIMESTAMPTZ | DEFAULT NOW() | FR-063 |

**唯附加**：無 UPDATE 與 DELETE 權限。`(assessment_id, revision_no)` 唯一。

**RLS**：僅 `app_role = 'MANAGER'` 且 `dept_id` 相符者可讀寫。HR 角色的政策
不涵蓋本表——這是 FR-008「查詢結果本身即不含受限欄位」的實施點。

---

## 8. `audit_logs`（稽核歷程．唯附加）

| 欄位 | 型別 | 約束 | 說明 |
|------|------|------|------|
| `id` | BIGSERIAL | PK | |
| `assessment_id` | UUID | NOT NULL（不設 FK，見下） | FR-082 |
| `action` | VARCHAR(50) | NOT NULL | 見操作類型清單 |
| `from_status` | VARCHAR(40) | | FR-076 |
| `to_status` | VARCHAR(40) | | FR-076 |
| `actor_id` | UUID | | 內部使用者；應徵者操作為 NULL |
| `actor_role` | VARCHAR(20) | NOT NULL | `HR` / `MANAGER` / `CANDIDATE` / `SYSTEM` |
| `detail` | JSONB | | 補充說明，**不得含個資或作答內容**（FR-079、FR-080） |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | FR-076 |

**不設 FK 至 `assessments` 的理由**：FR-082 要求個資刪除後稽核紀錄仍以
去識別化的考核識別碼保留。若設外鍵，刪除考核列會連帶破壞稽核歷程。

**操作類型清單**：`ASSESSMENT_CREATED`、`MANAGER_REASSIGNED`、`TOKEN_REGENERATED`、
`QUESTION_ASSIGNED`、`TRIAL_RUN`、`ANSWER_SUBMITTED`、`EVALUATION_STARTED`、
`EVALUATION_COMPLETED`、`EVALUATION_FAILED`、`DECISION_RECORDED`、
`DECISION_REVISED`、`NOTIFICATION_SENT`、`NOTIFICATION_FAILED`、
`STATUS_EXPIRED`、`PII_ERASED`。

**唯附加**：無 UPDATE 與 DELETE 權限，對所有角色皆然（FR-078）。

---

## 狀態機

```text
                  ┌──────────────────┐
                  │ PENDING_ASSIGN   │  建立考核（HR）
                  │ 待指派題目        │
                  └────────┬─────────┘
                           │ 主管指派題目
                           ▼
                  ┌──────────────────┐
              ┌──▶│ PENDING_CANDIDATE│  應徵者可作答
              │   │ 待應徵者作答      │
              │   └────────┬─────────┘
   HR 重新產生 │            │ 應徵者提交
   連結        │            ▼
              │   ┌──────────────────────────┐
              │   │ COMPLETED_AWAITING_REVIEW│  評測進行／完成
              │   │ 待主管審核                │
              │   └────────┬─────────────────┘
              │            │ 主管記錄決策
              │            ▼
              │   ┌──────────────────┐
              │   │ DECIDED          │  終態
              │   │ 已決策            │
              │   └──────────────────┘
              │
              │   ┌──────────────────┐
              └───│ EXPIRED          │  逾期（由 PENDING_ASSIGN
                  │ 已逾期            │   或 PENDING_CANDIDATE 進入）
                  └──────────────────┘
```

### 合法轉換表（FR-074）

| 來源狀態 | 目標狀態 | 觸發者 | 稽核操作類型 |
|---------|---------|--------|------------|
| `PENDING_ASSIGN` | `PENDING_CANDIDATE` | 主管 | `QUESTION_ASSIGNED` |
| `PENDING_CANDIDATE` | `COMPLETED_AWAITING_REVIEW` | 應徵者 | `ANSWER_SUBMITTED` |
| `COMPLETED_AWAITING_REVIEW` | `DECIDED` | 主管 | `DECISION_RECORDED` |
| `PENDING_ASSIGN` | `EXPIRED` | 系統 | `STATUS_EXPIRED` |
| `PENDING_CANDIDATE` | `EXPIRED` | 系統 | `STATUS_EXPIRED` |
| `EXPIRED` | `PENDING_CANDIDATE` | HR | `TOKEN_REGENERATED` |

其餘所有轉換必須被拒絕（FR-074、FR-075）。

**`DECIDED` 為終態**：決策為 `SECOND_ROUND` 時不自動建立新考核，
狀態停留於 `DECIDED`（FR-065）。決策修訂只新增 `manager_decisions` 列，
不改變狀態。

**逾期判定**：不使用排程作業。狀態於存取時惰性判定——任何讀取考核的路徑
若發現 `token_expires_at < NOW()` 且狀態為 `PENDING_ASSIGN` 或
`PENDING_CANDIDATE`，即轉為 `EXPIRED` 並寫入稽核。此設計避免引入排程器
（憲章原則 III）。

---

## RLS 政策矩陣

RLS 依 `auth.jwt()` 中的 `app_role` 與 `dept_id` claim 判定（R-002）。
`—` 表示該角色的政策不涵蓋此表，查詢結果為空。

| 資料表 | HR | MANAGER（同部門） | MANAGER（他部門） | 應徵者（token） |
|--------|-----|------------------|------------------|----------------|
| `departments` | 讀 | 讀 | 讀 | — |
| `internal_users` | 讀 | 讀（自己） | — | — |
| `question_banks` | — | 讀寫 | — | — |
| `assessments` | 讀寫（全部門）<sup>1</sup> | 讀寫 | — | 經函式讀寫單筆<sup>2</sup> |
| `execution_records` | — | 讀 | — | 經函式讀寫單筆 |
| `ai_reports` | **—**<sup>3</sup> | 讀 | — | — |
| `manager_decisions` | **—**<sup>3</sup> | 讀寫（僅新增） | — | — |
| `audit_logs` | 讀 | 讀（同部門） | — | — |

<sup>1</sup> HR 對 `assessments` 的讀取不含 `candidate_answer` 與
`ai_chat_history`（以 view 限定欄位）；`final_decision` 可讀。

<sup>2</sup> 應徵者無 JWT，一律經 `SECURITY DEFINER` 函式存取，
底層資料表不對 `anon` 角色開放（R-002）。

<sup>3</sup> **FR-007／FR-008 的實施點**。HR 角色在這兩張表上沒有任何政策，
因此查詢回傳空集合而非受限內容。此行為必須有越權測試斷言。

### 需要的 `SECURITY DEFINER` 函式

| 函式 | 用途 | 對應 FR |
|------|------|--------|
| `get_assessment_by_token(token)` | 驗證 token 與效期，回傳應徵者可見欄位 | FR-018、FR-029 |
| `append_chat_message(token, role, content)` | 附加對話訊息 | FR-051 |
| `record_trial_run(token, execution)` | 寫入試跑紀錄並遞增計數 | FR-031、FR-032 |
| `submit_answer(token, answer, language)` | 提交作答並轉換狀態，含重複提交檢查 | FR-033、FR-034 |

四個函式皆須在內部重新驗證 token 與效期，**不得**信任呼叫端已驗證。

---

## 個資刪除流程（FR-082）

1. 以 `email` 找出該人的所有 `assessments` 列
2. 將 `name`、`email`、`phone` 覆寫為去識別化佔位值，`candidate_answer` 與
   `ai_chat_history` 清空
3. 關聯的 `execution_records`、`ai_reports` 保留（不含個資）
4. `manager_decisions.internal_comment` 保留（企業內部紀錄，不含應徵者個資）
5. 寫入 `audit_logs` 的 `PII_ERASED`，僅記錄考核識別碼

**不採實體刪除**，因為 `audit_logs` 的唯附加要求與稽核完整性優先於資料列的移除；
去識別化已足以達成個資保護目的。
