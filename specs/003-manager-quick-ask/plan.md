# 實作計畫：面試官簡易出題頁

**分支**：`003-manager-quick-ask` | **日期**：2026-08-03 | **規格**：[spec.md](spec.md)

**依據憲章**：[v2.0.0](../../.specify/memory/constitution.md)

## 摘要

新增 `frontend/manager/ask.html`：一張置中卡片，讓面試官打完題目直接送給待指派的應徵者。
送出走既有的 `assign-question` 端點，**後端零變更**。

同時把 spec 002 建立的深色設計系統從應徵者頁抽成共用層 `frontend/css/theme.css`，
讓兩個角色的頁面共用同一份色票與元件定義。

## 技術脈絡

**語言/版本**：JavaScript ES2022（原生模組，無轉譯）

**主要相依**：無新增

**測試**：`node:test`（純邏輯）+ 既有 pytest 套件（結構不變條件與頁面服務）

**限制**：不得修改後端、不得引入 npm 相依

## 設計系統的抽離

規格要求「視覺與應徵者作答頁完全一致」。三種做法：

| 做法 | 否決／採用理由 |
|------|--------------|
| 出題頁直接連 `candidate/css/candidate.css` | 建立跨角色相依：改應徵者樣式會靜默影響面試官頁 |
| 把色票複製一份到出題頁 | 兩份真相來源。「完全一致」若靠複製維持，下次只改一邊就開始漂移 |
| **抽出 `frontend/css/theme.css` 共用層**（採用） | 色票與共用元件只有一份定義；頁面專屬版面各自留在自己的樣式表 |

`theme.css` 收的是：色票變數、reset、按鈕、卡片（panel）、表單元件、狀態訊息、
頁首、關鍵影格與捲軸。頁面專屬的版面（作答頁的三欄、出題頁的置中卡片）不進去。

抽離後 `candidate.css` 只剩該頁專屬版面；`assessment.html` 改為先載 `theme.css`
再載 `candidate.css`。以無頭瀏覽器比對確認作答頁外觀不變。

INV-105 由測試守護：`ask.css` 內不得出現任何六位色碼或色票變數定義。

## 專案結構

```text
frontend/
├── css/
│   └── theme.css                # ← 新增：共用設計系統（色票、按鈕、卡片、表單）
├── js/api.js                    # 唯一 fetch 出口（不動）
├── manager.html                 # 既有完整主管介面（不動）
├── candidate/                   # spec 002（css/candidate.css 精簡為頁面專屬版面）
└── manager/                     # ← 新增：面試官快速出題
    ├── ask.html
    ├── ask.js                   # 組裝：權杖 → 清單 → 送出。唯一接觸 API 的檔案
    ├── core/
    │   └── question-draft.js    # 純函式：一段文字 → Question（FR-205～FR-207）
    ├── css/ask.css              # 只有版面，無任何顏色
    └── tests/question-draft.test.js

backend/tests/unit/
└── test_manager_ask_page.py     # INV-101～INV-107
```

沿用 spec 002 的 core／ui 分層原則：有判斷的部分抽成純函式並以 `node:test` 覆蓋，
其餘是 DOM 綁定。本頁規模小，`ui/` 層併入 `ask.js`。

## 後端不變更的理由

| 需要的能力 | 既有 API | 出處 |
|-----------|---------|------|
| 指派題目並開通測驗 | `POST /manager/assessments/{id}/assign-question` | `backend/src/api/manager.py:123` |
| 只列待指派的考核 | `GET /manager/assessments` 回應含 `status` | `AssessmentSummaryManager` |
| 部門隔離 | `require_manager` + RLS，前端不需處理 | 上游 FR-003 |
| 缺測資的拒絕 | `Question.require_test_cases_for` | `backend/src/models/question.py` |
| 題目送達應徵者 | `GET /candidate/session/{token}` 已回傳 `question` | spec 002 已驗證 |

**路由順序**：新增 `frontend/manager/` 目錄後，`/manager/assessments` 仍須走 API 而非
靜態檔。與 spec 002 的 `/candidate` 前綴是同一個隱含相依，同樣以測試釘住（INV-104）。

## 憲章檢查

| 原則 | 狀態 | 合規方式 |
|------|------|---------|
| I. 規格驅動交付 | 通過 | FR-201～FR-211 皆有編號並對應至實作檔案 |
| II. 測試優先驗證 | 部分 | `question-draft` 的測試與實作同批撰寫（非嚴格先行），但測試確實抓出一段不可達的錯誤分支並使其被移除；驗收情境皆有對應測試 |
| III. 有依據的技術選型 | 通過 | 新增相依 0 項 |
| IV. 資料保護與最小權限 | 通過 | 後端安全模型零變更；部門隔離仍由後端強制，前端不做任何權限判斷 |
| V. 可稽核 | 通過 | 走既有端點，`QUESTION_ASSIGNED` 稽核紀錄照常寫入 |
| VI. 沙箱 | 不適用 | 不觸及 |

**原則 II 的誠實紀錄**：本功能未嚴格遵守「測試先於實作且先失敗」。`question-draft.js`
與其測試同批寫成，測試首跑時有一項失敗——原因是實作已先 `trim()` 整段文字，
使「第一行全為空白」的錯誤分支不可達。該分支已移除。

## 端到端串接（Phase 6）

出題頁完成後，「主管出題 → 應徵者作答」這條路徑的每一段都有契約測試，
但沒有任何一條測試把它們串起來。分段皆綠、整條卻不通，是最容易漏掉的一類失效——
特別是它依賴 demo 種子資料的部門配置，而那是**資料**而非程式碼，沒有東西守著它。

因此新增兩份測試：

| 檔案 | 守什麼 |
|------|--------|
| `tests/integration/test_demo_e2e_flow.py` | 整條流程，跑在 demo 種子上。日後有人改動 `demo.py` 的部門或狀態，這裡會先失敗 |
| `tests/unit/test_demo_mode_gate.py` | demo 模式的開關，以及正式環境不接受任何 demo 憑證 |

實作過程中發現 `_is_demo_mode` 以 `bool(值)` 判定，導致 `LOCAL_DEMO_MODE=0` 與
`=false` 會**啟用** demo 模式——在正式環境等於靜默降級成記憶體假資料 +
固定 JWT 密鑰的無認證系統。已改為只認明確的真值。

QA 的手動路徑見 [quickstart.md](quickstart.md)。

## 風險

| 風險 | 緩解 |
|------|------|
| 抽離 theme.css 弄壞作答頁 | 61 項前端測試 + 無頭瀏覽器前後比對；作答頁外觀確認不變 |
| 新增靜態目錄遮蔽 `/manager/*` API | INV-104 直接斷言 API 回應為 JSON |
| 面試官誤送給非待指派的考核 | 清單只列 `PENDING_ASSIGN`；後端另有 409 把關 |
| 無登入頁，權杖需手動貼 | 已記於 spec.md「已知限制」；不在本功能範圍 |
