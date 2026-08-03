# 驗證報告：應徵者作答介面模組化

**功能**：[002-candidate-assessment-ui](spec.md) | **日期**：2026-08-03

## 修改檔案

### 新增

| 檔案 | 行數 | 責任 |
|------|-----:|------|
| `frontend/package.json` | 8 | 宣告 `type: module` 與測試指令；無任何相依 |
| `frontend/candidate/assessment.html` | 116 | 應徵者作答頁（正式入口） |
| `frontend/candidate/main.js` | 150 | 組裝點；唯一接觸 API 的檔案 |
| `frontend/candidate/core/gate.js` | 74 | 畫面狀態判定（純函式） |
| `frontend/candidate/core/session-view.js` | 80 | session → 白名單視圖模型（純函式） |
| `frontend/candidate/core/run-result.js` | 60 | 試跑結果與失敗分支（純函式） |
| `frontend/candidate/core/messages.js` | 73 | 面向應徵者的全部字串 |
| `frontend/candidate/ui/elements.js` | 55 | `assessment.html` 的 DOM 契約 |
| `frontend/candidate/ui/notice.js` | 35 | 狀態提示區 |
| `frontend/candidate/ui/question.js` | 53 | 題目與範例測資（建節點，非字串拼接） |
| `frontend/candidate/ui/editor.js` | 55 | CodeMirror 掛載與 fallback |
| `frontend/candidate/ui/answer.js` | 146 | 語言、試跑、提交、確認對話 |
| `frontend/candidate/ui/chat.js` | 102 | AI 助教 |
| `frontend/candidate/css/candidate.css` | 約 560 | 深色主題樣式表，隨頁面出貨、無 CSS CDN |
| `frontend/candidate/tests/*.test.js` | 4 檔 | 純邏輯層的 50 項測試 |
| `backend/tests/unit/test_candidate_frontend_boundaries.py` | 15 項 | 結構不變條件守門 |
| `specs/002-candidate-assessment-ui/{spec,plan,tasks,quickstart,verification}.md` | — | 規格產出物 |

### 修改

| 檔案 | 變更 |
|------|------|
| `frontend/assessment.html` | 改為轉址頁，保留 `token` 查詢字串（FR-106） |
| `.env.example` | `CANDIDATE_BASE_URL` 說明改為新路徑，註明舊路徑仍可用 |
| `README.md` | 專案結構加入 `candidate/`；新增「前端測試」段落 |
| `specs/001-ai-recruitment-assessment/plan.md` | 前端結構加註後續變更指向 spec 002 |

### 刪除

| 檔案 | 去處 |
|------|------|
| `frontend/js/editor.js` | 拆分為 `candidate/main.js` + `core/*` + `ui/editor.js` + `ui/answer.js` |
| `frontend/js/chat.js` | 搬至 `candidate/ui/chat.js`，改為由呼叫端注入容器 |

### 未修改（刻意）

- **後端全部程式碼**：零變更。理由逐項列於 [plan.md](plan.md)「後端不變更的理由」——
  candidate 的四個端點已覆蓋本規格所需的全部資料與錯誤語意，頁面路徑由環境變數決定，
  靜態檔掛載已遞迴涵蓋新目錄。
- **candidate 四份契約測試**：`git diff` 為空，已驗證。這是「行為等價」的主要證據。
- **`frontend/js/api.js`、`hr.js`、`manager.js`、`index.html`、`manager.html`**：零變更。
- **資料庫 schema、RLS 政策、SECURITY DEFINER 函式**：未觸碰。

## 驗證結果

| 關卡 | 指令 | 結果 |
|------|------|------|
| 前端純邏輯 | `cd frontend && node --test "candidate/tests/*.test.js"` | **50 passed, 0 failed** |
| 後端全套（含新增守門） | `cd backend && LOCAL_DEMO_MODE= pytest` | **284 passed, 33 skipped** |
| 契約測試未被修改 | `git diff -- backend/tests/contract/test_candidate_*.py` | **空** |
| Lint（新增檔案） | `ruff check backend/tests/unit/test_candidate_frontend_boundaries.py` | **通過** |

變更前基準為 269 passed；新增 15 項守門測試後為 284 passed，**無既有測試轉為失敗**。

### 不變條件覆蓋

| 不變條件 | 守護測試 | 狀態 |
|---------|---------|------|
| INV-001 無直接 `fetch` | `test_candidate_never_calls_fetch_directly` | 通過 |
| INV-002 角色間匯入邊界（雙向） | `test_import_boundary_between_roles_holds_in_both_directions` | 通過 |
| INV-003 api.js 匯入白名單 | `test_candidate_only_imports_its_own_api_namespace` | 通過 |
| INV-004 無受限識別字 | `test_candidate_sources_contain_no_restricted_identifiers` | 通過 |
| INV-005 API 路由未被靜態檔遮蔽 | `test_candidate_api_route_is_not_shadowed_by_static_files` | 通過 |
| INV-006 新舊路徑皆可服務 | `test_candidate_page_is_served_at_the_new_path`、`test_legacy_path_still_reaches_the_candidate_page` | 通過 |
| INV-007 core/ 不碰瀏覽器 API | `test_core_layer_is_free_of_browser_globals` | 通過 |
| INV-008 契約測試未修改 | `git diff`（人工關卡） | 通過 |

額外守護：`test_only_the_composition_root_touches_the_api` 斷言 API 呼叫僅出現在
`main.js`，使 `ui/` 每個檔案都能被單獨閱讀。

### 一併修正的既有缺口

| 缺口 | 原行為 | 現行為 |
|------|--------|--------|
| 對話重整即消失 | `session.chat_history` 由後端回傳但前端從未讀取 | 載入時以 `chat.restore()` 還原（FR-128） |
| 試跑／提交遇 409、410 | 只把訊息塞進輸出區，畫面仍停在可作答 | 轉入對應終端狀態（FR-121、FR-126） |
| 重複送出 | 試跑／提交／對話按鈕在請求期間仍可按 | 三處皆於進行中停用（FR-122、FR-127、FR-130） |
| 範例測資渲染 | `innerHTML` 字串拼接 + 自寫 `escapeHtml` | 建節點 + `textContent`（FR-116） |
| 提交確認 | `window.confirm` | 頁內 `<dialog>`，不支援時退回 `confirm`（FR-123） |

## 尚未完成與風險

### 1. 既有問題：`.env` 的 `LOCAL_DEMO_MODE` 會汙染測試套件（阻擋性，非本功能造成）

**現象**：直接執行 `cd backend && pytest` 時 **111 項失敗**，全部集中在需認證的
HR／主管路徑（401 UNAUTHORIZED）。

**根因**：工作區未提交的 `backend/src/config.py` 新增了 `load_dotenv()`。本機 `.env`
設有 `LOCAL_DEMO_MODE`，載入後使 `load_settings()` 走 demo 分支，以 `demo-jwt-secret`
覆寫 `conftest.py` 用 `monkeypatch` 設定的測試密鑰，導致測試簽發的 JWT 全部驗證失敗。

**證據**：將 `config.py`／`main.py`／`demo.py` 暫存後執行 → 268 passed；
保留變更但以 `LOCAL_DEMO_MODE= pytest` 執行 → 269 passed。

**建議修法**（未實作——超出本功能範圍，且屬他人進行中的工作）：
`_is_demo_mode()` 判定為真時，不應覆寫呼叫端已明確提供的 Supabase 設定值，
或在 `load_settings(env=...)` 帶入明確 env 時跳過 `load_dotenv()`。

**目前的規避方式**：`LOCAL_DEMO_MODE= pytest`，已記於 [quickstart.md](quickstart.md)。

### 2. DOM 綁定層無自動化測試（已知取捨）

`ui/` 底下的模組沒有單元測試。這是 [plan.md](plan.md)「測試策略」中明確接受的取捨：
引入 jsdom 會違反「無建置流程、零 npm 相依」的既有決策（NFR-003、NFR-004）。
判定邏輯已全數移出 `ui/`，剩餘程式碼為無分支的節點寫入，其風險以
[quickstart.md](quickstart.md) 的手動清單涵蓋。

**若日後改變取捨**：`ui/` 的每個模組都接收節點而非自行查找，加上 jsdom 後
可直接測試，不需要再重構。

### 3. 舊路徑轉址頁的移除時機未定

`frontend/assessment.html` 需保留至最後一封含舊路徑的邀請信逾期之後（至少 7 天）。
本規格刻意不設移除時程；移除時須同步確認 `.env` 的 `CANDIDATE_BASE_URL` 已改為新路徑，
並更新 `backend/tests/unit/test_demo_mode.py` 中對 `/assessment.html` 的斷言。

### 4. `<dialog>` 的瀏覽器支援

提交確認優先使用 `<dialog>`，偵測 `showModal` 不存在時退回 `window.confirm`。
降級路徑未經自動化測試驗證，列於手動清單。

### 5. 非工程類作答的 demo 資料缺失

`backend/src/demo.py` 的種子資料只有工程類考核，因此 US3（文字作答介面）
無法在 demo 模式下手動驗證。純邏輯層已由 `session-view.test.js` 覆蓋
（`isEngineering === false` 時 `language` 為 `null`），但 DOM 呈現需自行建立
非工程類考核才能確認。

### 6. `main.js` 與 `ui/answer.js` 接近行數上限

分別為 150 與 146 行，貼近 NFR-005 的 ~150 行界線。兩者責任單一且不宜再拆
（前者是組裝點，後者是單一互動面板），但後續若再加功能應先考慮拆分而非追加。

## v2 視覺改版的補充驗證（2026-08-03）

依 Claude Design 交接稿改為深色主題與左右兩欄版面。改動限於標記、樣式與 ui/ 層
class 字串；`core/` 四個模組、`main.js` 的 API 呼叫路徑與資料綁定皆未變更。

| 關卡 | 結果 |
|------|------|
| 前端純邏輯 | 50 passed（`core/` 未動，測試零修改仍通過——即等價性證明） |
| 後端全套 | **286 passed**（改版前 284，新增 2 項守門） |
| 實地渲染（Chrome headless 1440×900） | 可作答／找不到連結／已提交三種狀態皆正確 |

### 改版中發現並修正的迴歸

**終端狀態下頁首提交鈕仍可點擊**（FR-137）。提交鈕從工作區移到頁首後，
`applyGate` 只隱藏工作區就不再足夠——逾期或已提交的應徵者會看到一顆按了必定
失敗的提交鈕。這個缺陷是實地渲染「找不到連結」狀態時才發現的，
純邏輯測試與靜態掃描都抓不到。

### 改版中確認的降級行為

無頭環境載入不到 `esm.sh`，CodeMirror 掛載失敗並**如預期退回純文字輸入框**
（FR-114）。這是意外得到的一次真實降級驗證，非刻意安排。

### 新增的不變條件

- **INV-009**：`ui/elements.js` 查找的每個 id 都存在於 `assessment.html`
  （`test_every_element_in_the_dom_contract_exists_in_the_markup`）。
  改版最容易踩的雷就是動到 id——JS 拿到 `null`，畫面只是「某塊沒東西」，不會拋錯。
- **INV-010**：頁面不引用 Tailwind CDN，且引用本地樣式表
  （`test_candidate_page_styles_are_locally_owned`）。

### 尚未驗證

- **非工程類版面**：demo 種子資料只有工程類考核，文字作答版面（隱藏語言選擇、
  試跑鈕、執行結果卡片）未經實地渲染確認。純邏輯層已由 `session-view.test.js` 覆蓋，
  DOM 契約由 INV-009 覆蓋，但視覺結果未看過。
- **提交確認視窗與試跑互動**：無頭截圖無法驅動點擊，`<dialog>` 的實際外觀、
  焦點鎖定與試跑輸出的呈現仍需人工確認（見 [quickstart.md](quickstart.md)）。
- **螢幕報讀器**：`role="status"` / `role="log"` / `aria-live` 已標註，未實測。

## 安全模型確認

本次變更**未觸碰**任何安全邊界：

- candidate API 的路徑、請求／回應結構、狀態碼語意、token 驗證與逾期判定：零變更。
- 應徵者仍不需帳號，僅以 URL token 識別身分。
- token 不進入 `localStorage`／`sessionStorage`（`test_candidate_never_persists_the_token` 守護），
  也不出現在任何面向使用者的訊息中——錯誤文字一律取自本地字串表，不回放後端原文。
- 視圖模型採白名單投影：AI 報告、主管內部評語、決策結果與隱藏測資即使出現在
  API 回應中也無法被渲染（`session-view.test.js` 以污染輸入驗證）。
- HR 與主管介面的檔案內容零變更，其測試全數通過。
