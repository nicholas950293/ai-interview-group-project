# 原始 PRD 封存：AI 智慧招聘與技術考核系統

> **用途**：此檔為使用者提供之原始 PRD 的封存版本（已修正編碼為 UTF-8）。
> Spec Kit 的 `spec.md` 必須保持技術中立，因此 PRD 中的技術棧、資料庫 DDL 與 API 路由
> 移至本檔保存，將於 `/speckit-plan` 階段轉入 `plan.md`、`data-model.md` 與 `contracts/`。
>
> **狀態**：此為原始輸入的忠實記錄，**未經**缺口補強。已知缺口與修正建議見文末。

## 1. 專案概述與目標

本系統旨在協助企業建立現代化、自動化且具資料安全隔離的跨部門招聘與技術考核流程。系統整合
人資（HR）、部門主管（Manager）與應徵者（Candidate）三大角色，透過 AI 技術輔助題目生成與
自動化客觀評測，降低招聘評估成本並提升人才篩選精準度。

## 2. 技術架構與選型

### 資料庫與身份驗證

**Supabase (PostgreSQL)** — 利用 Supabase PostgreSQL 處理關聯式資料與 JSONB 彈性資料結構。

- 用 Row Level Security (RLS) 實現部門間資料存取權限隔離
- 透過 Supabase REST Client API 進行資料即時同步

### AI 人工智慧服務

**Google Gemini API (gemini-3-flash-preview)**

- 動態出題：依據職缺能力指標，即時生成客觀考題
- 線上答題助教：在應徵者作答期間提供觀念引導（在錄用嚴禁直給）
- 多維度自動評測：針對程式碼與申論回答進行正確性、可維護性、效能與安全性評分

### 後端 API 服務

**Python (FastAPI Framework)**

- 用 Python Async/Await 處理高效能非同步 API 請求
- 整合 supabase-py SDK 存取資料庫，並透過 google-generativeai SDK 與 Gemini 溝通
- 提供 Pydantic 資料結構驗證與嚴謹的錯誤處理機制

### 前端介面

**HTML5 + CSS (Tailwind CSS CDN) + JavaScript (Vanilla ES6+) / React**

- 無需複雜之前端編譯或建置流程（Zero-Build Standard Stack）
- 原生 JavaScript / React 渲染 UI，搭配 Tailwind CSS 建構響應式深色調（Dark Mode）介面
- 內建動態題型呈現：工程師嵌入式 IDE 控制台／非工程師結構化答題表單

## 3. Supabase 資料庫 Schema DDL 與權限控制 (PostgreSQL)

```sql
-- 1. Departments Table (部門資料表)
CREATE TABLE departments (
  id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  type VARCHAR(30) CHECK (type IN ('ENGINEERING', 'NON_ENGINEERING'))
);

-- 2. Question Banks Table (部門專屬題庫表)
CREATE TABLE question_banks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dept_id VARCHAR(50) REFERENCES departments(id),
  title VARCHAR(200) NOT NULL,
  category VARCHAR(100),
  difficulty VARCHAR(20) CHECK (difficulty IN ('Easy', 'Medium', 'Hard')),
  language VARCHAR(30) DEFAULT 'javascript',
  description TEXT NOT NULL,
  constraints TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Candidates Table (應徵者與考核紀錄主表)
CREATE TABLE candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(100) NOT NULL,
  email VARCHAR(150) NOT NULL,
  phone VARCHAR(50),
  job_title VARCHAR(100) NOT NULL,
  dept_id VARCHAR(50) REFERENCES departments(id),
  assigned_manager_id VARCHAR(100),
  assigned_manager_name VARCHAR(100),
  status VARCHAR(50) DEFAULT 'PENDING_ASSIGN'
    CHECK (status IN ('PENDING_ASSIGN', 'PENDING_CANDIDATE',
                      'COMPLETED_AWAITING_REVIEW', 'DECIDED')),
  token VARCHAR(100) UNIQUE NOT NULL,
  token_expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '7 days'),
  question JSONB,
  code_language VARCHAR(30) DEFAULT 'javascript',
  candidate_answer TEXT,
  execution_logs TEXT,
  ai_chat_history JSONB DEFAULT '[]'::jsonb,
  ai_report JSONB,
  manager_decision JSONB,
  email_status VARCHAR(30) DEFAULT 'NOT_SENT'
    CHECK (email_status IN ('NOT_SENT', 'SENT')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_banks ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policy Example (部門主管只能存取所屬部門資料)
CREATE POLICY manager_dept_isolation ON candidates
  FOR ALL USING (dept_id = current_setting('app.current_dept_id', true));
```

## 4. Python Backend (FastAPI) API 路由規範

| HTTP Method | API Path | 權責角色 | 說明 |
|---|---|---|---|
| GET | `/api/hr/candidates` | HR | 取得全公司所有面試者資訊清單 |
| POST | `/api/hr/candidates` | HR | 新增徵才案（含部門下拉選單），並寫入夾帶 7 天效期 Token 與指派主管 |
| POST | `/api/hr/send-email` | HR | 發送個人化面試結果通知 Email 給應徵者 |
| GET | `/api/manager/candidates/{dept_id}` | 部門主管 | 取得該主管所屬部門之應徵者（資料隔離） |
| POST | `/api/manager/ai-generate-question` | 部門主管 | 呼叫 Python + Gemini API 依能力需求動態出題 |
| POST | `/api/manager/assign-question` | 部門主管 | 指定／AI 生成之考題發送給面試者並開通測驗 |
| POST | `/api/manager/decision` | 部門主管 | 儲存主管最終決策（Pass / 2nd Round / Fail）與評語 |
| GET | `/api/candidate/test-session/{token}` | 應徵者 | 依專屬 Token 載入個人測驗頁面（含校驗 7 天效期） |
| POST | `/api/candidate/submit` | 應徵者 | 提交答案，同步觸發 Python 後端呼叫 Gemini 評測 |

## 5. 角色核心功能需求與作業流程

### 5.1 HR 人資全域管理視角

- **全域應徵者總覽**：實時掌握全公司應徵者的考核進度（待指派、測驗中、待主管審核、主管已決策）
- **新增應徵者與部門選擇**：輸入應徵者基本資訊，直接透過下拉式選單選擇應徵者所屬部門
  （如：工程技術部、產品行銷部、產品設計部等），系統將自動連結部門題型並指派責任主管
- **預設 7 天專屬連結效期**：建立應徵者時，系統自動生成專屬 Token 連結並設定
  `token_expires_at` 為建立日起算 7 天內有效
- **一鍵通知發送**：主管完成決策後，HR 可透過彈出視窗審視、微調 Email 內容後發送通知

### 5.2 部門主管視角 (Department Manager Hub)

- **部門資料隔離**：主管登入後僅能看到所屬部門的應徵者與部門專屬題庫
- **動態出題機制**：
  1. 預設題庫載入：直接選擇部門累積之標準考題
  2. AI 智慧生成：輸入能力指標（如：Golang, Redis 快取, 難度：高），由 Gemini 產出實戰題目
- **解答與 AI 對話全歷程審視**：
  - 查看應徵者提交之完整程式碼／申論回答與執行 Log
  - 審視應徵者在作答期間與 AI 答題助教的對話紀錄（評估溝通能力與解決問題思路）
- **主管最終裁決權**：閱覽 AI 產出之客觀評測報告，並做出最終裁決
  （Pass / 2nd Round / Fail）；填寫內部評語

### 5.3 應徵者測驗體驗端 (Candidate Assessment Portal)

- **Token 免登入存取（7 天效期）**：透過專屬 URL Token 進入個人化測驗頁面，
  超過 7 天將顯示連結逾期警示
- **動態作答介面**：
  - 工程師類型 (ENGINEERING)：內建輕量程式碼編輯器（支援 JS, Python, Go, Java, C++）、
    語法標示與 Console 模擬執行
  - 非工程師類型 (NON_ENGINEERING)：提供結構化文字／段落作答輸入介面
- **AI 答題助教即時幫手**：答題過程中可隨時向 AI 詢問題目觀念，設有 Guardrail 機制
  （不直接提供完整答案）

## 6. 關鍵資訊安全與 Guardrail 機制

1. **主管評語隱私保護 (Manager Comment Privacy Guardrail)**
   主管在系統內輸入之內部評語（Comments）屬於企業內部機密。Python 後端在組裝 Email 內容時，
   嚴禁將內部評語自動帶入 Email 內文，需經 HR 有權手動微調。

2. **AI 客觀性警示 (AI Copilot Notice)**
   Gemini 產生的分數（正確性、效能、安全性等）僅供主管決策參考（Copilot），
   主管保有最高且唯一的錄取決定權。

3. **連結有效性檢查 (Token Expiry Guardrail)**
   應徵者存取測驗頁面時，系統必須檢查 `token_expires_at` 時間戳記，
   若超過 7 天預設效期則拒絕載入題目並提示聯繫 HR 展延。

---

## 已知缺口與修正建議（規劃階段必須處理）

以下為原始 PRD 未涵蓋、需在 `plan.md` / `data-model.md` 補齊的項目：

### 資料模型

1. **`candidates` 表混合兩個概念**：同時承載「應徵者個資」與「單次考核狀態」。
   決策選項含 `2nd Round`，代表同一人可能有多次考核。建議拆為 `candidates` 與
   `assessments` 兩張表。
2. **缺少內部使用者表**：`assigned_manager_id VARCHAR(100)` 無外鍵，系統中不存在
   HR／主管的帳號資料表。
3. **缺少稽核表**：無任何狀態歷程紀錄。`status` 直接覆寫，違反憲章原則 V 的唯附加要求。
   需新增 `audit_logs` 表。
4. **四個 JSONB 欄位無結構定義**：`question`、`ai_chat_history`、`ai_report`、
   `manager_decision` 皆未定義內部欄位，導致無法產生 Pydantic model。**此為產碼的
   直接阻斷點。**
5. **狀態集合缺少逾期狀態**：`CHECK` 約束中無 `EXPIRED`，但 Guardrail 3 要求處理逾期。
6. **`email_status` 缺少失敗狀態**：僅有 `NOT_SENT` / `SENT`，無 `FAILED` 與重送機制。

### 安全架構

7. **RLS 設計實際上不會生效**：policy 使用 `current_setting('app.current_dept_id', true)`
   這個自訂 session 變數，而非 Supabase 標準的 JWT claim 機制。若後端以 `service_role`
   金鑰連線，RLS 會被完全繞過。需明確定義：誰在哪一層設定該變數，或改用 `auth.jwt()`。
8. **兩條資料存取路徑未劃分**：第 2 節同時描述「前端透過 Supabase REST Client 即時同步」
   與「後端 FastAPI 存取資料庫」。需明確定義哪些操作走哪條路徑、各自使用哪把金鑰。
9. **內部使用者認證流程未定義**：九條 API 路由標示了權責角色，但未說明角色如何驗證。
10. **Token 規則不完整**：未定義長度／亂度、是否一次性、提交後是否失效。

### 範圍與可測試性

11. **多語言程式碼執行範圍未定**：「Console 模擬執行」語意不明。若真正執行不受信任的
    應徵者程式碼，必須有沙箱隔離設計——PRD 完全未提及。此為全文風險最高項目。
12. **Guardrail 缺乏驗收標準**：「不直接提供完整答案」無可測試的判定方式。
13. **前端技術未決**：「Vanilla ES6+ / React」兩者並列；且 Zero-Build 與 React
    在標準用法下互斥。
14. **無可量測的成功標準**：原始 PRD 完全沒有此章節（已於 `spec.md` 補上）。
15. **無資料保存期限**：系統儲存 Email 與電話，涉及個資法，未規定保存期限與刪除權。
16. **模型可用性需確認**：`gemini-3-flash-preview` 為預覽版模型 ID，導入前應先確認
    其可用性、配額與正式版遷移路徑。
