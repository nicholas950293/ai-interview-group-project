# 實作計畫：應徵者作答介面模組化

**分支**：`002-candidate-assessment-ui` | **日期**：2026-08-03 | **規格**：[spec.md](spec.md)

**輸入**：功能規格 `specs/002-candidate-assessment-ui/spec.md`（34 條 FR、7 條 NFR、8 條 INV）

**依據憲章**：[v2.0.0](../../.specify/memory/constitution.md)

## 摘要

把散落在 `frontend/` 根目錄的應徵者介面收攏成單一產品模組 `frontend/candidate/`，
並在模組內把「純邏輯」與「DOM 操作」拆成兩層：`core/` 不引用任何瀏覽器 API，
因此可在 Node 中直接匯入測試；`ui/` 只負責把 core 的輸出寫進 DOM。

後端**零變更**。所有既有的 candidate API、token 驗證、逾期判定、重複提交防護、
試跑限制與提交後評測流程完全保留。

## 技術脈絡

**語言/版本**：JavaScript ES2022（原生模組，無轉譯）

**主要相依**：無新增。CodeMirror 6 CDN 維持既有用法；v2 視覺改版後樣式改為自帶，
不再使用 Tailwind CDN（字型自 Google Fonts CDN 載入，失敗時退回系統字型）

**測試**：
- 純邏輯：Node 內建 `node:test`（Node 18+ 內建，零 npm 安裝）
- 結構不變條件：既有 pytest 套件新增一份靜態掃描 + 服務路徑測試

**目標平台**：現代瀏覽器（支援原生 ES 模組與 `<dialog>`）

**專案類型**：靜態前端模組（無建置流程）

**限制**：不得引入 npm 相依、不得引入打包器、不得修改後端

**規模/範圍**：1 個 HTML 入口、1 個轉址頁、4 個 core 模組、5 個 ui 模組、
1 個組裝進入點、4 份 Node 測試檔、1 份 pytest 守門測試

## 現有程式碼分析

### 需要搬移的檔案

| 現有路徑 | 新路徑 | 處理方式 |
|---------|--------|---------|
| `frontend/assessment.html` | `frontend/candidate/assessment.html` | 搬移並重寫標記（加入無障礙標示、確認對話、對話容器 id） |
| `frontend/assessment.html`（原路徑） | 同路徑保留 | 改寫為極小的轉址頁（FR-106） |
| `frontend/js/editor.js` | 拆為 `candidate/main.js` + `candidate/core/*` + `candidate/ui/*` | 拆分後刪除原檔 |
| `frontend/js/chat.js` | `frontend/candidate/ui/chat.js` | 搬移並改為「由呼叫端注入容器」（FR-131） |

### 不搬移的檔案與理由

| 檔案 | 理由 |
|------|------|
| `frontend/js/api.js` | 三種角色共用，且規格要求所有 API 呼叫集中於此（FR-104）。搬入 candidate 會讓 HR／主管反過來依賴應徵者目錄，邊界更糟 |
| `frontend/js/hr.js`、`frontend/js/manager.js`、`frontend/index.html`、`frontend/manager.html` | 屬內部介面，本功能不觸碰（NFR-002） |

### `editor.js` 現行 233 行的責任拆解

| 現行程式碼 | 拆往 | 為什麼 |
|-----------|------|--------|
| `boot()` 中的 token 解析與 catch 分支 | `core/gate.js` | 這是純判定：輸入 session 或錯誤，輸出畫面狀態。抽出後才可測 |
| `showNotice()` 的樣式對應 | `ui/notice.js` | 純 DOM |
| `render()` 中的欄位取用 | `core/session-view.js` | 白名單投影（FR-132），可測 |
| `renderSampleCases()` 的 `innerHTML` 字串拼接 | `ui/question.js` | 改為建 DOM 節點，移除自建的 `escapeHtml`（FR-116） |
| `mountEditor()` / `currentCode()` | `ui/editor.js` | CodeMirror 掛載與 fallback |
| 試跑按鈕的結果格式化與錯誤分支 | `core/run-result.js` + `core/trial-runs.js` | 純函式，US2 的驗收情境幾乎全在這裡 |
| 提交按鈕的 `confirm`/`alert` | `ui/answer.js` + `core/gate.js` | 對話改為頁內 `<dialog>`；失敗後的狀態轉換由 gate 決定 |

### 已發現的行為缺口（本次一併修正）

1. `session.chat_history` 由後端回傳但前端完全未讀取 → 重新整理即遺失對話（FR-128）。
2. 試跑／提交遇 409、410 時畫面停留在可作答狀態（FR-121、FR-126）。
3. 試跑 503 時 `catch` 直接 return，未扣次數是對的，但沒有明確告知「仍可提交」的位置一致性；
   統一由 `core/run-result.js` 產生訊息（FR-120）。
4. 試跑與提交按鈕在請求進行中未停用，可重複送出（FR-122、FR-127）。
5. `renderSampleCases` 以字串拼接 HTML，靠自寫的 `escapeHtml` 防護 → 改為建節點（FR-116）。

## 後端不變更的理由

規格要求「若不需修改後端請明確說明原因」。逐項檢查後確認**不需要**：

| 本功能需要的能力 | 既有 API 是否已提供 | 出處 |
|-----------------|-------------------|------|
| 載入 session（職缺、題目、到期時間、剩餘次數、已提交時間） | 是 | `CandidateSession`，`backend/src/api/candidate.py:71` |
| 對話歷程還原 | 是，`chat_history` 已在回應中 | `candidate.py:87`、`test_candidate_chat.py::test_history_is_returned_in_the_session` |
| 逾期判定 | 是，410 + `LINK_EXPIRED` | `candidate.py:58-68` |
| 未指派題目 | 是，`status=PENDING_ASSIGN` 且 `question=None` | `test_candidate_session.py::test_pending_assign_shows_status_without_question` |
| 重複提交防護 | 是，409 + `ALREADY_SUBMITTED` | `candidate.py:44` |
| 試跑次數上限 | 是，429 + `trial_runs_remaining` | `candidate.py:104-106` |
| 沙箱不可用 | 是，503 | `candidate.py:109-110` |
| 提交後自動評測 | 是，背景任務 | `candidate.py:203-206` |
| 隱藏測資不外洩 | 是，回應只含 `sample_cases` | `test_candidate_session.py::test_hidden_test_cases_are_absent` |
| 頁面路徑變更 | 不需改碼：`CANDIDATE_BASE_URL` 為環境變數 | `backend/src/config.py:151` |
| 新路徑可被服務 | 不需改碼：`StaticFiles` 已遞迴掛載整個 `frontend/` | `backend/src/main.py` `_register_routes` |

**唯一需要留意的是路由順序**：`/candidate/session/{token}` 是 API 路由，
而靜態檔掛載在 `/`。FastAPI 先比對已註冊路由、最後才落到 mount，因此
`/candidate/assessment.html` 走靜態檔、`/candidate/session/xxx` 走 API。
這是隱含的順序相依，因此以測試釘住（INV-005、INV-006），而不是靠註解提醒。

**環境變數的後續動作**：`.env.example` 的 `CANDIDATE_BASE_URL` 說明更新為新路徑。
既有部署即使沿用舊值也不會壞——舊路徑有轉址頁。

## 專案結構

```text
frontend/
├── package.json                 # 只含 {"type":"module","private":true} 與 test script
├── index.html                   # HR（不動）
├── manager.html                 # 主管（不動）
├── assessment.html              # ← 改為轉址頁，保留舊連結（FR-106）
├── js/
│   ├── api.js                   # 唯一 fetch 出口（不動）
│   ├── hr.js                    # 不動
│   └── manager.js               # 不動
└── candidate/                   # ← 應徵者產品模組（本功能）
    ├── assessment.html          # 正式入口 /candidate/assessment.html
    ├── main.js                  # 組裝：解析 token → 載入 → 依 gate 分派
    ├── core/                    # 純邏輯：不引用 document / window / fetch
    │   ├── gate.js              # 畫面狀態判定（FR-108～FR-111）
    │   ├── session-view.js      # session → 白名單視圖模型（FR-132）
    │   ├── run-result.js        # 執行結果與錯誤 → 顯示文字（FR-117～FR-121）
    │   └── messages.js          # 所有面向應徵者的字串（單一來源）
    ├── ui/                      # 薄 DOM 綁定：不做決策
    │   ├── notice.js            # 狀態提示區
    │   ├── question.js          # 題目與範例測資
    │   ├── editor.js            # CodeMirror 掛載與 fallback
    │   ├── answer.js            # 語言、試跑、提交、確認對話
    │   └── chat.js              # AI 助教
    ├── css/
    │   └── candidate.css        # 隨頁面出貨的樣式表（深色主題，無 CSS CDN）
    └── tests/                   # node:test，無需瀏覽器
        ├── gate.test.js
        ├── session-view.test.js
        ├── run-result.test.js
        └── messages.test.js

backend/tests/unit/
└── test_candidate_frontend_boundaries.py   # INV-001～INV-006 的守門測試
```

### 結構決策

**為什麼 core／ui 兩層而不是一層？**
應徵者體驗的正確性幾乎全在「判定」上——現在是不是逾期、還能不能試跑、
這個錯誤該轉到哪個畫面。這些判定若和 `document.getElementById` 寫在一起，
就只能靠人開瀏覽器點一遍來驗證。拆成兩層後，US1～US4 的驗收情境有超過八成
可以用純函式測試涵蓋，而 `ui/` 剩下的部分是「把字串放進節點」這種看一眼就能確認的程式碼。

**為什麼 `frontend/package.json` 而不是 `frontend/candidate/package.json`？**
`core/` 的測試不匯入 `api.js`，但 `ui/` 匯入它。若 `type: module` 只宣告在
`candidate/` 之下，Node 會把 `frontend/js/api.js` 當成 CommonJS 解析而失敗。
放在 `frontend/` 根目錄可讓整個前端在 Node 眼中一致為 ESM。這個檔案不含任何相依，
也不參與瀏覽器載入流程——不是建置流程（NFR-003）。

**為什麼入口是 `assessment.html` 而不是 `index.html`？**
`/candidate/` 這個前綴已被 API 佔用。用具名檔案讓「頁面」與「API」在 URL 上
一眼可辨，也避免依賴 `StaticFiles(html=True)` 的目錄索引行為。

## 憲章檢查

### 初次檢查（設計前）

| 原則 | 狀態 | 合規方式 |
|------|------|---------|
| I. 規格驅動交付 | 通過 | spec.md 已定案，FR-101～FR-134 皆有編號；tasks.md 每項任務標註對應 FR |
| II. 測試優先驗證 | 通過 | `core/` 四份測試先於實作撰寫；搬移的既有行為以「既有測試不修改仍通過」證明等價 |
| III. 有依據的技術選型 | 通過 | 新增相依 0 項；`frontend/package.json` 為模組型別標記，非相依宣告 |
| IV. 應徵者資料保護與最小權限 | 通過 | FR-132～FR-134 以白名單投影 + 靜態掃描雙重把關；後端安全模型零變更 |
| V. 可稽核且公平的評估 | 不適用 | 本功能不觸及稽核、評測或決策路徑 |
| VI. 不受信任程式碼的隔離執行 | 不適用 | 本功能不觸及沙箱 |

### 重新檢查（設計後）

| 原則 | 狀態 | 設計後驗證 |
|------|------|-----------|
| I | 通過 | 每個 core／ui 模組在本檔的結構圖中標註對應 FR |
| II | 通過 | 測試策略見下節；`node --test` 與 `pytest` 皆可離線執行 |
| III | 通過 | 未引入框架、打包器、CSS 建置；複雜度追蹤僅一項且已辯護 |
| IV | 通過 | INV-003、INV-004 以 pytest 靜態掃描強制；INV-007 保證 core 不碰 storage |

**關卡結論**：無未經辯護的違規。

## 測試策略

### 為什麼是這個組合

前端沒有既有的測試基礎設施。要驗證應徵者介面，只有三條路：

1. **引入 vitest + jsdom** — 可測 DOM，但要新增 npm 相依與建置流程，
   與 NFR-003、NFR-004 及上游 R-004 的「無建置流程」決策衝突。
2. **只做靜態掃描 + 手動清單** — 零成本，但逾期／已提交／試跑次數這些
   最容易寫錯的判定沒有回歸保護。
3. **把判定抽成純函式，用 Node 內建測試器測；結構用 pytest 守門** — 採用此案。

第 3 案的取捨是：DOM 綁定層沒有自動化測試。這是刻意接受的——把決策全部移出後，
`ui/` 只剩下 `element.textContent = value` 這一類無分支的程式碼，
其風險用 quickstart 的手動驗收清單涵蓋即可。

### 三層驗證

| 層級 | 工具 | 涵蓋 | 指令 |
|------|------|------|------|
| 純邏輯 | `node:test` | US1～US4 的狀態判定、結果格式化、次數推進、白名單投影 | `node --test frontend/candidate/tests/` |
| 結構不變條件 | `pytest` | INV-001～INV-006（fetch 禁令、匯入邊界、受限欄位、路由不相撞、兩條路徑可服務） | `cd backend && pytest tests/unit/test_candidate_frontend_boundaries.py` |
| 既有行為等價 | `pytest` | 四份 candidate 契約測試與全部既有測試，**不做任何修改**即須通過 | `cd backend && pytest` |
| 手動驗收 | quickstart | DOM 綁定、CodeMirror fallback、對話還原、無障礙 | [quickstart.md](quickstart.md) |

### 測試先行的落實順序

每個 core 模組一律「先寫測試 → 執行並確認因『模組不存在』而失敗 → 再實作」。
tasks.md 中以成對任務（T0xx 測試、T0xx+1 實作）明確表達此順序。

## 風險與緩解

| 風險 | 影響 | 緩解 |
|------|------|------|
| 已寄出的舊連結失效 | 應徵者無法作答，需 HR 重發 | 保留 `/assessment.html` 轉址頁並以測試釘住（INV-006） |
| 靜態頁遮蔽 API 路由 | candidate API 全掛 | INV-005 測試直接斷言 API 回應為 JSON |
| 搬移過程遺失行為 | 靜默的功能退化 | 既有 pytest 套件零修改必須通過（INV-008）；搬移前先跑一次基準 |
| `<dialog>` 瀏覽器支援 | 提交確認無法顯示 | 偵測 `showModal` 是否存在，缺少時退回 `window.confirm` |
| Node 版本過舊（< 18） | 前端測試無法執行 | 測試指令與 README 標註最低版本；pytest 層的守門不受影響 |

## 複雜度追蹤

| 偏離 | 為何需要 | 較簡單的替代方案為何被否決 |
|------|---------|--------------------------|
| 新增 `frontend/package.json` | Node 需要 `"type": "module"` 才能把 `.js` 當 ES 模組載入；否則 `core/` 的測試無法匯入受測模組 | 把測試檔改副檔名為 `.mjs` 仍無法解決「受測的 `.js` 被當成 CJS」的問題；改寫全部前端為 `.mjs` 會影響瀏覽器路徑與既有 HTML |

**未引入的複雜度**（明確記錄以供日後審查）：前端測試框架、jsdom、打包器、
TypeScript、CSS 前處理器、前端路由。六者皆非規格所要求，依憲章原則 III 排除。
