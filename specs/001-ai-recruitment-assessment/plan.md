# 實作計畫：AI 智慧招聘與技術考核系統

**分支**：`001-ai-recruitment-assessment` | **日期**：2026-07-31 | **規格**：[spec.md](spec.md)

**輸入**：功能規格 `specs/001-ai-recruitment-assessment/spec.md`（v3，82 條功能需求）

**依據憲章**：[v2.0.0](../../.specify/memory/constitution.md)

## 摘要

建置一套整合 HR、部門主管與應徵者三種角色的招聘技術考核系統。核心流程為
「HR 建案並產生 7 天效期連結 → 主管出題（題庫或 AI 生成）→ 應徵者免登入作答並試跑
程式碼 → 系統於隔離沙箱驗證並產出四維度 AI 報告 → 主管決策 → HR 寄送通知」。

技術方案以 FastAPI 作為唯一資料存取入口，權限由 PostgreSQL 的 RLS 依 JWT claim
強制執行；應徵者提交的程式碼一律在斷網、限資源、用後即棄的 Docker 容器中執行。
AI、Email 與沙箱三者皆置於可替換介面之後，使預設測試套件得以完全離線執行。

## 技術脈絡

**語言/版本**：Python 3.11+（後端）；JavaScript ES2022（前端，原生模組）

**主要相依**：FastAPI、uvicorn、Pydantic v2、supabase-py、google-generativeai、
Docker SDK for Python、httpx、PyJWT；前端為 CodeMirror 6 CDN
（HR／主管頁另用 Tailwind CDN；應徵者頁自 spec 002 v2 起改為自帶樣式表）

**儲存**：Supabase (PostgreSQL)。結構以版本控管的遷移檔定義於 `supabase/migrations/`

**測試**：pytest（+ pytest-asyncio、httpx AsyncClient）。分為離線預設套件與
需 Docker 的安全套件，見 [research.md](research.md) R-008

**目標平台**：Linux 伺服器（需 Docker daemon）。開發環境支援 Windows／macOS／Linux

**專案類型**：Web 服務 + 靜態前端 + 沙箱執行元件

**效能目標**：試跑 p90 < 15 秒（SC-004）；提交至報告可見 < 3 分鐘（SC-005）；
AI 出題 < 60 秒（SC-002）

**限制**：沙箱單次執行上限為 CPU 10 秒、記憶體 512 MB、牆鐘 30 秒、程序數 64、
輸出 1 MB，且無網路；沙箱同時執行數上限 10

**規模/範圍**：單一企業內部使用，同時線上作答 ≤ 50 人；8 張資料表；
17 個 REST 端點（HR 6、主管 7、應徵者 4）；3 個前端頁面

## 憲章檢查

*關卡：Phase 0 研究前必須通過，Phase 1 設計後重新檢查。*

### 初次檢查（Phase 0 前）

| 原則 | 狀態 | 合規方式 |
|------|------|---------|
| I. 規格驅動交付 | 通過 | spec.md v3 已定案，82 條 FR 皆有編號；本計畫每項設計決策皆標註對應 FR |
| II. 測試優先驗證 | 通過 | AI、Email、沙箱三者皆定義為介面（見 `contracts/`），預設套件以替身離線執行；每個驗收情境對應至少一項測試 |
| III. 有依據的技術選型 | 通過 | 技術棧未超出憲章「技術與資料限制」；超出 PRD 原設計之處記於「複雜度追蹤」 |
| IV. 應徵者資料保護與最小權限 | 通過 | RLS 依 `auth.jwt()` claim 於資料庫層強制執行（R-002）；HR 受限內容以拆表隔離（R-003）；日誌過濾規則見下 |
| V. 可稽核且公平的評估 | 通過 | `audit_logs`、`manager_decisions` 為獨立唯附加資料表；`ai_reports` 不含加權總分 |
| VI. 不受信任程式碼的隔離執行 | 通過 | 六項條件逐一對應容器參數（R-001）；沙箱不可用時降級為「接受提交但不執行」（FR-047） |

### 重新檢查（Phase 1 設計後）

| 原則 | 狀態 | 設計後驗證 |
|------|------|-----------|
| I | 通過 | data-model.md 與 contracts/ 中每個實體與端點皆標註來源 FR |
| II | 通過 | `SandboxRunner`、`AiProvider`、`EmailSender` 三份介面契約已定義；替身實作為任務清單的前置項 |
| III | 通過 | 資料表由 PRD 的 3 張增為 8 張，理由記於「複雜度追蹤」；未引入訊息佇列、未引入前端框架 |
| IV | 通過 | RLS 政策矩陣見 data-model.md；`service_role` 僅限遷移與維護，且以測試守護 |
| V | 通過 | 狀態轉換一律經 `audit_logs` 記錄；決策以 `revision_no` 唯附加 |
| VI | 通過 | 容器參數表已固化於 `contracts/sandbox-runner.md`，安全套件逐項斷言 |

**關卡結論**：無未經辯護的違規。「複雜度追蹤」中的三項偏離皆為憲章原則所直接要求，
非自主增加的複雜度。

### 品質關卡對應

- **離線測試套件**：`pytest -m "not security"` 不需網路與外部服務
- **安全關卡**：`pytest -m security` 驗證網路阻斷、資源耗盡中止、檔案系統存取阻擋
- **權限關卡**：越權測試針對 RLS 的拒絕行為斷言，涵蓋跨部門主管、HR 讀取受限表、
  應徵者跨考核存取三類

## 專案結構

### 文件（本功能）

```text
specs/001-ai-recruitment-assessment/
├── spec.md              # 功能規格（v3）
├── prd-source.md        # 原始 PRD 封存與已知缺口
├── plan.md              # 本檔案
├── research.md          # Phase 0 產出：8 項技術決策
├── data-model.md        # Phase 1 產出：8 張資料表與 RLS 政策矩陣
├── quickstart.md        # Phase 1 產出：端到端驗證指南
├── contracts/           # Phase 1 產出
│   ├── openapi.yaml         # REST API 契約
│   ├── sandbox-runner.md    # 沙箱執行介面契約
│   └── ai-provider.md       # AI 服務介面契約
├── checklists/
│   └── requirements.md  # 規格品質檢核表
└── tasks.md             # Phase 2 產出（由 /speckit-tasks 建立）
```

### 原始碼（儲存庫根目錄）

```text
backend/
├── src/
│   ├── main.py                  # FastAPI 應用程式進入點
│   ├── config.py                # 環境變數設定（無寫死值）
│   ├── api/
│   │   ├── hr.py                # HR 端點（FR-009～FR-014、FR-067～FR-072）
│   │   ├── manager.py           # 主管端點（FR-023～FR-028、FR-060～FR-066）
│   │   └── candidate.py         # 應徵者端點（FR-029～FR-035）
│   ├── models/                  # Pydantic 結構定義
│   │   ├── assessment.py
│   │   ├── question.py          # 含 test_cases 結構（FR-022）
│   │   ├── report.py
│   │   └── decision.py
│   ├── repositories/            # Supabase 存取層，唯一接觸資料庫之處
│   │   ├── base.py              # JWT 轉發連線建立
│   │   └── assessment_repo.py
│   ├── services/
│   │   ├── assessment_service.py
│   │   ├── evaluation_service.py    # 提交後評測流程協調
│   │   └── notification_service.py
│   ├── sandbox/
│   │   ├── runner.py            # SandboxRunner 介面（契約見 contracts/）
│   │   ├── docker_runner.py     # 正式實作（FR-036～FR-048）
│   │   └── fake_runner.py       # 測試替身
│   ├── ai/
│   │   ├── provider.py          # AiProvider 介面
│   │   ├── gemini_provider.py   # 正式實作
│   │   ├── fake_provider.py     # 測試替身
│   │   └── prompts/             # 版本控管的提示詞（R-005）
│   ├── email/
│   │   ├── sender.py            # EmailSender 介面
│   │   ├── smtp_sender.py
│   │   └── fake_sender.py
│   └── audit/
│       └── logger.py            # 唯附加稽核寫入（FR-076～FR-078）
└── tests/
    ├── contract/                # 對照 openapi.yaml 的契約測試
    ├── integration/             # 跨層流程測試（含 RLS 政策驗證）
    ├── security/                # 沙箱隔離測試（marker: security）
    └── unit/

frontend/
├── index.html               # HR 總覽
├── manager.html             # 主管 Hub
├── assessment.html          # 應徵者作答頁（含編輯器與 AI 助教）
├── js/
│   ├── api.js               # 對後端 API 的唯一呼叫點
│   ├── hr.js
│   ├── manager.js
│   ├── editor.js            # CodeMirror 6 整合
│   └── chat.js
└── css/
```

> **後續變更**：應徵者前端已於
> [spec 002](../002-candidate-assessment-ui/spec.md) 移入 `frontend/candidate/`，
> `editor.js` 與 `chat.js` 隨之拆分搬移，原 `assessment.html` 改為保留舊連結的轉址頁。
> 後端與 candidate API 未因該次變更而調整。

```text
sandbox/
├── javascript/Dockerfile
├── python/Dockerfile
├── go/Dockerfile
├── java/Dockerfile
└── cpp/Dockerfile

supabase/
└── migrations/              # 版本控管的結構定義（憲章技術限制要求）
```

**結構決策**：採前後端分離的 Web 應用結構，並額外獨立 `sandbox/` 與 `supabase/`
兩個頂層目錄。

`sandbox/` 獨立的理由是它的產出物是容器映像檔而非 Python 模組，其建置與版本
週期和後端不同。`supabase/migrations/` 獨立的理由是憲章「技術與資料限制」明訂
資料表結構必須以版本控管的遷移檔定義。

`repositories/` 層是唯一接觸資料庫的位置，使「JWT 轉發」與「`service_role`
不得用於使用者請求」兩項規則有單一的強制點，也讓權限測試有明確的攔截位置。

v1 的 `src/assessment.py` 與 `tests/unit/test_assessment_flow.py` 與本規格不相容，
將於實作階段第一項任務中移除。

## 複雜度追蹤

本節記錄超出 PRD 原始設計的複雜度。三項皆源自憲章原則的直接要求。

| 偏離 | 為何需要 | 較簡單的替代方案為何被否決 |
|------|---------|--------------------------|
| 資料表由 3 張增為 8 張 | 憲章原則 V 要求稽核歷程以獨立唯附加結構實作；FR-007／FR-008 要求 HR 的查詢結果本身即不含 AI 報告與內部評語 | 沿用 PRD 的單表 + JSONB 設計時，RLS 僅能做列級過濾，無法阻擋 HR 讀取同一列中的受限欄位，直接牴觸 FR-008 |
| 引入 Docker 沙箱基礎設施 | 憲章原則 VI（不可妥協）要求六項隔離條件，且使用者已確認採「後端沙箱真實執行多語言」 | 語言層沙箱（VM2、RestrictedPython）有反覆的逃逸紀錄且無法施加資源上限；純語法檢查不符使用者已確認的範圍決定 |
| 執行紀錄獨立成表 | FR-048 要求每次沙箱執行皆留下稽核紀錄，且單次考核最多產生 21 次執行（20 次試跑 + 1 次評測） | PRD 的 `execution_logs TEXT` 單一欄位只能保留最後一次，無法滿足逐次稽核 |

**未引入的複雜度**（明確記錄以供日後審查）：訊息佇列（R-006）、前端框架（R-004）、
多 AI 供應商支援（R-005）、獨立的評測引擎服務（R-001）。四者皆為規格未要求，
依憲章原則 III 排除。
