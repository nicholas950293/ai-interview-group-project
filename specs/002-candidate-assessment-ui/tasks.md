---

description: "應徵者作答介面模組化：依使用者故事組織的實作任務清單"
---

# 任務清單：應徵者作答介面模組化

**輸入**：設計文件位於 `specs/002-candidate-assessment-ui/`

**前置文件**：[plan.md](plan.md)、[spec.md](spec.md)、[quickstart.md](quickstart.md)

**測試**：**強制，非選用**。[憲章 v2.0.0](../../.specify/memory/constitution.md)
原則 II 標示為不可妥協——`core/` 模組的測試必須先於實作撰寫並先失敗。

**組織方式**：任務依使用者故事分組。US1～US4 為 P1，US5～US6 為 P2。

## 格式：`[ID] [P?] [Story] 描述`

- **[P]**：可平行執行（不同檔案、無未完成的相依）
- **[Story]**：所屬使用者故事（US1～US6）

## 路徑慣例

依 [plan.md](plan.md)：`frontend/candidate/`、`frontend/js/`、`backend/tests/unit/`

---

## Phase 1：基準與環境（阻斷性前置作業）

**目的**：先取得可比對的基準，再改動任何東西

- [X] T001 執行 `cd backend && pytest` 取得變更前的基準結果並記錄通過數（INV-008 的比對基準）
- [X] T002 建立 `frontend/package.json`，內容僅為 `{"name","private":true,"type":"module","scripts":{"test":"node --test candidate/tests/"}}`（plan.md 複雜度追蹤）
- [X] T003 建立目錄 `frontend/candidate/core/`、`frontend/candidate/ui/`、`frontend/candidate/css/`、`frontend/candidate/tests/`（FR-101）

---

## Phase 2：純邏輯層（測試先行）

**⚠️ 每一對任務必須先跑測試並確認失敗，才可實作**

### 訊息單一來源

- [X] T004 [P] 撰寫 `frontend/candidate/tests/messages.test.js`：斷言所有面向應徵者的訊息鍵存在、皆為非空字串、且不含 token 佔位符（FR-134）
- [X] T005 實作 `frontend/candidate/core/messages.js`（FR-108、FR-134）

### 畫面狀態判定（US1）

- [X] T006 [P] [US1] 撰寫 `frontend/candidate/tests/gate.test.js`：涵蓋 US1 驗收情境 1～7 與 US4 情境 5～6（gate 由錯誤轉換狀態）
- [X] T007 [US1] 實作 `frontend/candidate/core/gate.js`，匯出 `GateState`、`gateFromToken`、`gateFromSession`、`gateFromError`（FR-108～FR-111、FR-121、FR-126）

### 白名單視圖模型（US1、US3）

- [X] T008 [P] [US1] 撰寫 `frontend/candidate/tests/session-view.test.js`：斷言輸出鍵為固定白名單、額外欄位（含 `ai_report`、`manager_decision`）被丟棄、`sample_cases` 只保留三個欄位、非工程類不含語言（FR-132、US3 情境 1～2）
- [X] T009 [US1] 實作 `frontend/candidate/core/session-view.js`，匯出 `toSessionView`、`toSampleCase`（FR-132、FR-133）

### 試跑結果與次數（US2）

- [X] T010 [P] [US2] 撰寫 `frontend/candidate/tests/run-result.test.js`：涵蓋 US2 驗收情境 4～9（輸出／錯誤／終止原因／耗時／截斷／次數推進／429／503）
- [X] T011 [US2] 實作 `frontend/candidate/core/run-result.js`，匯出 `describeTermination`、`formatRunOutput`、`formatRunMeta`、`resolveRunFailure`、`afterTrialRun`（FR-117～FR-121）

- [X] T012 執行 `node --test frontend/candidate/tests/` 確認 Phase 2 全數通過

---

## Phase 3：DOM 綁定層（US1～US4）

- [X] T013 [P] [US1] 實作 `frontend/candidate/ui/notice.js`：依 `GateState` 呈現提示區並設定 `role="status"`（FR-110、NFR-006）
- [X] T014 [P] [US1] 實作 `frontend/candidate/ui/question.js`：以建立節點方式渲染題目與範例測資，不使用 `innerHTML`（FR-116）
- [X] T015 [P] [US2] 實作 `frontend/candidate/ui/editor.js`：CodeMirror 6 掛載、語言切換保留內容、CDN 失敗退回 textarea（FR-112、FR-114、FR-115）
- [X] T016 [US2][US3][US4] 實作 `frontend/candidate/ui/answer.js`：語言選擇、試跑、提交、`<dialog>` 提交確認與 `window.confirm` 備援、請求進行中停用按鈕（FR-112、FR-113、FR-118、FR-122～FR-127）
- [X] T017 [P] [US5] 實作 `frontend/candidate/ui/chat.js`：由呼叫端注入容器、還原歷史對話、錯誤只寫入自身區塊（FR-128～FR-131）

---

## Phase 4：入口與組裝

- [X] T018 建立 `frontend/candidate/assessment.html`：區域標示、確認對話、對話容器、fallback CSS 連結（FR-101、FR-112、FR-113、NFR-006）
- [X] T019 [P] 建立 `frontend/candidate/css/candidate.css`：隨頁面出貨的樣式表（NFR-007）
- [X] T020 實作 `frontend/candidate/main.js`：解析 token → `gateFromToken` → 載入 session → 依 gate 分派 → 掛載各 ui 模組（FR-104、FR-111）
- [X] T021 改寫 `frontend/assessment.html` 為轉址頁，保留 `token` 查詢參數並提供可點擊的備援連結（FR-106）
- [X] T022 刪除 `frontend/js/editor.js` 與 `frontend/js/chat.js`（已搬移完畢，FR-101）

---

## Phase 5：邊界守門測試（US6）

- [X] T023 [US6] 建立 `backend/tests/unit/test_candidate_frontend_boundaries.py`，涵蓋：
  - INV-001 `frontend/candidate/` 無直接 `fetch(`
  - INV-002 雙向匯入邊界
  - INV-003 自 `api.js` 匯入的識別字在允許清單內
  - INV-004 無受限欄位識別字
  - INV-005 `/candidate/session/{token}` 仍回傳 API JSON
  - INV-006 `/assessment.html` 與 `/candidate/assessment.html` 皆為 200
  - INV-007 `core/` 不引用 `document`／`window`／`fetch`／`localStorage`

---

## Phase 6：文件與驗證

- [X] T024 [P] 建立 `specs/002-candidate-assessment-ui/quickstart.md`：手動驗收清單（DOM 綁定、CodeMirror fallback、對話還原）
- [X] T025 [P] 更新 `.env.example` 的 `CANDIDATE_BASE_URL` 說明為新路徑，並註明舊路徑仍可用
- [X] T026 [P] 更新 `README.md` 的專案結構與測試段落，加入前端測試指令
- [X] T027 [P] 於 `specs/001-ai-recruitment-assessment/plan.md` 的前端結構區塊加註「應徵者前端已於 spec 002 移入 `frontend/candidate/`」
- [X] T028 執行 `node --test frontend/candidate/tests/` 與 `cd backend && pytest`，確認全數通過且結果不低於 T001 的基準
- [X] T029 執行 `ruff check backend --config backend/ruff.toml` 確認新增的 pytest 檔案通過 lint
- [X] T030 建立 `specs/002-candidate-assessment-ui/verification.md`：記錄修改檔案、驗證結果與未完成風險

---

## Phase 7：v2 視覺改版（依 Claude Design 交接稿）

**範圍**：僅標記、樣式與 ui/ 層的 class 字串。`core/`、API 呼叫路徑與資料綁定不動。

- [X] T031 建立 `frontend/candidate/css/candidate.css`：以設計稿色票／字級／圓角建立
      深色主題樣式表；移除 `fallback.css` 與 Tailwind CDN（FR-138、INV-010）
- [X] T032 改寫 `frontend/candidate/assessment.html`：左右兩欄、提交鈕移至頁首右上角、
      題目／作答／執行結果三張卡片、AI 對話側欄（FR-135、FR-136）
- [X] T033 [P] 更新 `ui/notice.js`、`ui/question.js`、`ui/chat.js` 的 class 字串至新樣式
- [X] T034 [P] 於 `ui/editor.js` 以 `EditorView.theme` 就地定義 CodeMirror 深色主題，
      不另引入主題套件
- [X] T035 修正終端狀態下頁首提交鈕仍可點擊的迴歸：`main.js` 的 `applyGate` 一併隱藏
      `#topbar-actions` 與 `#topbar-meta`（FR-137）
- [X] T036 [P] `ui/chat.js` 加入 Enter 送出與常見問題捷徑，兩者皆走既有的 form submit
      路徑（FR-139、FR-140）
- [X] T037 [P] `ui/answer.js` 於確認視窗顯示作答字數（FR-141）
- [X] T038 新增守門測試 `test_every_element_in_the_dom_contract_exists_in_the_markup`
      與 `test_candidate_page_styles_are_locally_owned`（INV-009、INV-010）
- [X] T039 以無頭瀏覽器實地渲染驗證：可作答、找不到連結、已提交三種狀態
- [X] T040 更新 spec.md「v2 視覺改版」章節、plan.md、quickstart.md 與 verification.md

---

## 相依關係

```text
T001 → T002 → T003
T003 → Phase 2（T004～T012）
T012 → Phase 3（T013～T017）
T013～T017 → T018 → T020
T020 → T021 → T022
T022 → T023 → T028
T028 → T030
```

## 平行執行機會

- T004、T006、T008、T010 皆為不同測試檔，可同時撰寫
- T013、T014、T015、T017 皆為不同 ui 檔案，可同時實作
- T024～T027 為四份互不相干的文件

## 完成定義

1. `node --test frontend/candidate/tests/` 全數通過
2. `cd backend && pytest` 全數通過，且四份 candidate 契約測試檔案的 `git diff` 為空
3. `frontend/candidate/` 之外沒有任何應徵者專屬的程式碼
4. quickstart.md 的手動清單逐項確認
