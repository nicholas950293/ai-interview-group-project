---

description: "面試官簡易出題頁的實作任務清單"
---

# 任務清單：面試官簡易出題頁

**輸入**：[spec.md](spec.md)、[plan.md](plan.md)

**路徑慣例**：`frontend/css/`、`frontend/manager/`、`backend/tests/unit/`

---

## Phase 1：抽出共用設計系統

- [X] T001 建立 `frontend/css/theme.css`：自 `candidate/css/candidate.css` 抽出色票、
      reset、按鈕、卡片、表單元件、狀態訊息與頁首（plan.md「設計系統的抽離」）
- [X] T002 精簡 `frontend/candidate/css/candidate.css` 為頁面專屬版面，
      並於 `candidate/assessment.html` 先載 `theme.css` 再載 `candidate.css`
- [X] T003 以無頭瀏覽器比對作答頁抽離前後的外觀，確認不變

## Phase 2：純邏輯層

- [X] T004 撰寫 `frontend/manager/tests/question-draft.test.js`：
      標題／敘述拆分、長度截斷、空白輸入、測資產生規則（FR-205～FR-207）
- [X] T005 實作 `frontend/manager/core/question-draft.js`
- [X] T006 移除測試抓出的不可達錯誤分支（`TITLE_ONLY_WHITESPACE`），
      並改以「開頭空行自動略過」的斷言取代
- [X] T007 更新 `frontend/package.json` 的 test script 以涵蓋 `manager/tests/`

## Phase 3：頁面

- [X] T008 建立 `frontend/manager/ask.html`：置中單卡片，含應徵者選單、題目輸入框、
      範例測資兩欄、送出按鈕與權杖面板（FR-201、FR-202）
- [X] T009 [P] 建立 `frontend/manager/css/ask.css`：只有版面，不得含任何色碼（INV-105）
- [X] T010 實作 `frontend/manager/ask.js`：權杖 → 載入待指派清單 → 送出
      （FR-203、FR-204、FR-208、FR-210、FR-211）

## Phase 4：守門測試

- [X] T011 建立 `backend/tests/unit/test_manager_ask_page.py`（INV-101～INV-107）
- [X] T012 強化 `test_candidate_frontend_boundaries.py` 的角色匯入邊界，
      使其涵蓋新的 `frontend/manager/` 目錄，並斷言兩頁共用 `theme.css`

## Phase 5：驗證與文件

- [X] T013 端到端驗證：demo 模式下送出題目 → 確認應徵者 session 的 `question` 出現、
      狀態轉為 `PENDING_CANDIDATE`
- [X] T014 無頭瀏覽器渲染驗證：權杖面板、清單已載入、清單為空三種狀態
- [X] T015 執行 `node --test` 與 `pytest`，確認全數通過且無既有測試轉為失敗
- [X] T016 更新 `README.md` 的專案結構與前端測試指令
- [X] T017 建立 `verification.md`

---

## Phase 6：端到端串接（QA 可操作的最小流程）

**目的**：把分段皆綠的契約測試，串成一條可被 QA 手動走完、也可被自動化驗證的路徑。

- [X] T018 修正 `_is_demo_mode`：`LOCAL_DEMO_MODE=0`／`false` 原本會**啟用** demo 模式
      （`bool("0")` 為真）。改為只認 `1`／`true`／`yes`／`on`
- [X] T019 建立 `backend/tests/unit/test_demo_mode_gate.py`：demo 開關的真值判定，
      以及正式環境拒絕 demo JWT 密鑰、demo token 與 demo 帳號（20 項）
- [X] T020 建立 `backend/tests/integration/test_demo_e2e_flow.py`：登入 → 看到同部門
      待指派 → 指派 → 應徵者讀到題目 → 提交 → 狀態轉為待主管審核，
      以及跨部門、未授權、錯誤 token、重複提交、隱藏測資不外洩（9 項）
- [X] T021 建立 `quickstart.md`：QA 的手動操作手冊與邊界情境
- [X] T022 更新 `README.md` 的 demo 流程與 `.env.example` 的 `LOCAL_DEMO_MODE` 說明

**未修改（刻意）**：`api/candidate.py`、`api/manager.py`、`services/assessment_service.py`、
`demo.py` 的部門配置、`frontend/candidate/`——端到端串接靠既有 API 完成，
不需要動任何一條業務邏輯。

---

## 完成定義

1. `node --test` 與 `cd backend && pytest` 全數通過
2. 後端程式碼 `git diff` 為空
3. 應徵者作答頁外觀與行為不變
