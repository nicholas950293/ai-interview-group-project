# 驗證報告：面試官簡易出題頁

**功能**：[003-manager-quick-ask](spec.md) | **日期**：2026-08-03

## 修改檔案

### 新增

| 檔案 | 責任 |
|------|------|
| `frontend/css/theme.css` | 共用設計系統：色票、reset、按鈕、卡片、表單、狀態訊息、頁首 |
| `frontend/manager/ask.html` | 出題頁（置中單卡片） |
| `frontend/manager/ask.js` | 組裝：權杖 → 待指派清單 → 送出。唯一接觸 API 的檔案 |
| `frontend/manager/core/question-draft.js` | 純函式：一段文字 → 後端要的 Question |
| `frontend/manager/css/ask.css` | 僅版面，無任何色碼 |
| `frontend/manager/tests/question-draft.test.js` | 11 項純邏輯測試 |
| `frontend/manager/core/errors.js` + `tests/errors.test.js` | 失敗訊息對應（交付後修正，FR-211、FR-212） |
| `backend/tests/unit/test_manager_ask_page.py` | 9 項結構守門測試 |

### 修改

| 檔案 | 變更 |
|------|------|
| `frontend/candidate/css/candidate.css` | 抽走共用層，只留該頁專屬版面 |
| `frontend/candidate/assessment.html` | 加載 `../css/theme.css` |
| `frontend/package.json` | test script 涵蓋 `manager/tests/` |
| `backend/tests/unit/test_candidate_frontend_boundaries.py` | 角色匯入邊界涵蓋 `frontend/manager/`；斷言共用 `theme.css` |
| `README.md` | 專案結構與前端測試指令 |

### 未修改（刻意）

- **後端全部程式碼**：`git diff -- backend/src/` 為空。送出走既有的
  `POST /manager/assessments/{id}/assign-question`。
- **`frontend/manager.html` 與 `frontend/js/manager.js`**：既有完整主管介面零變更（NFR-102）。
- **應徵者作答頁的 HTML／JS**：只多了一行 `<link>`；`main.js`、`core/`、`ui/` 皆未動。
- **資料庫結構、RLS 政策、SECURITY DEFINER 函式**：未觸碰。

## 驗證結果

| 關卡 | 指令 | 結果 |
|------|------|------|
| 前端純邏輯 | `node --test candidate/tests/*.test.js manager/tests/*.test.js` | **61 passed**（改版前 50，新增 11） |
| 後端全套 | `cd backend && LOCAL_DEMO_MODE= pytest` | **295 passed, 33 skipped**（改版前 286，新增 9） |
| Lint | `ruff check`（新增檔案） | 通過 |

### 端到端驗證（demo 模式）

以 `dept_id: DESIGN` 的權杖對 `demo-assessment-002` 送出題目：

```text
出題前  status: PENDING_ASSIGN   question: None
送出    HTTP 200  {"status":"PENDING_CANDIDATE"}
出題後  status: PENDING_CANDIDATE
        title : 實作一個帶 TTL 的 LRU 快取
        範例測資: [{'name': '範例', 'stdin': '3 5\n', 'expected_stdout': '8\n'}]
```

應徵者作答頁**未做任何修改**即讀到題目與範例測資。

### 無頭瀏覽器渲染

| 狀態 | 結果 |
|------|------|
| 未提供權杖 | 顯示權杖面板，出題表單隱藏 |
| 已提供權杖、有待指派對象 | 下拉帶出「陳小雯｜前端工程師（DESIGN）」，標頭顯示「1 位待指派」，送出鈕啟用 |
| 已提供權杖、無待指派對象 | 下拉為空、送出鈕停用，並說明為何清單為空 |
| 應徵者作答頁（抽離 theme.css 後） | 外觀與抽離前一致 |

## 實作過程中的發現

**測試抓出一段不可達的程式碼**。`question-draft.js` 原本有「第一行全是空白」的錯誤分支，
但函式已先 `trim()` 整段文字，該分支永遠進不去。測試首跑失敗使它被發現並移除，
行為改為「開頭空行自動略過」——對面試官更寬容，也少一段永遠不會執行的程式碼。

**demo 資料的部門錯配**。demo 種子中唯一「待指派題目」的考核屬 DESIGN 部門，
而 `demo-manager-user` 的 `dept_id` 為 ENG。以 ENG 權杖開啟本頁會看到空清單。
這是部門隔離（上游 FR-003）正確運作的結果，不是缺陷——已記於 spec.md「已知限制」。
未修改 `demo.py`：改種子資料不會讓產品更好，只會讓 demo 更順。

## 交付後修正：錯誤訊息無法行動（FR-211、FR-212）

**事故**：出題頁在只提供靜態檔的伺服器（`python3 -m http.server --directory frontend`，
port 5173）上開啟時，頁面正常顯示但 `/api/manager/assessments` 全數 404，
畫面只顯示「載入應徵者清單失敗，請稍後再試」。使用者無從判斷該重試、換網址還是換權杖。

**根因**：`ask.js` 的 catch 只區分 401/403，其餘一律吞成通用訊息——
違反本規格自己的 FR-211。

**修正**：新增 `core/errors.js`，把狀態碼對應到可行動的說明並以 7 項測試覆蓋：

| 狀況 | 訊息 |
|------|------|
| 連線失敗 | 連不上伺服器，確認後端仍在執行且同源 |
| 404 | 找不到後端 API——這頁多半開在只提供靜態檔的伺服器上 |
| 401 | 權杖無效或已過期（退回權杖輸入畫面） |
| 403 | 這組權杖沒有主管權限 |
| 其他 | 優先採用後端訊息並附上狀態碼 |

只有 401／403 會退回權杖輸入畫面——網址錯或後端沒開時，重貼權杖也解決不了。

**一併修正**：`README.md` 的建置步驟原本教人用 `python3 -m http.server --directory frontend`
提供前端，卻沒說 `/api` 需要同源或反向代理。該指示已改寫並加上警告。

**驗證**：在 port 5173 實地重現，畫面現在顯示「找不到後端 API（404）。這一頁多半被開在
只提供靜態檔的伺服器上——請改用有跑後端的網址…」。

## 端到端串接的驗證（Phase 6）

QA 可操作的最小流程已串通並自動化。

| 關卡 | 結果 |
|------|------|
| 端到端流程 `tests/integration/test_demo_e2e_flow.py` | **9 passed** |
| demo 開關與正式環境隔離 `tests/unit/test_demo_mode_gate.py` | **20 passed** |
| 後端全套 | **334 passed, 33 skipped**（Phase 6 前 305） |
| 前端 | **74 passed** |

端到端測試逐步斷言的內容，與 [quickstart.md](quickstart.md) 的手動步驟一一對應：
登入 → 只看到同部門的待指派（張小豪，且**陳小雯不在其中**）→ 出題前應徵者看到
`PENDING_ASSIGN` 且無題目 → 指派 → 應徵者立刻讀到題目與範例測資 → 提交 →
狀態轉為 `COMPLETED_AWAITING_REVIEW` → 主管端看得到狀態已推進。

拒絕行為亦逐項覆蓋：跨部門指派、未帶憑證、錯誤 token、重複提交、隱藏測資不外洩。

### Phase 6 發現的缺陷

**`LOCAL_DEMO_MODE=0` 會啟用 demo 模式**（`bool("0")` 為真）。實測：

```text
LOCAL_DEMO_MODE='1'     → demo_mode=True
LOCAL_DEMO_MODE='0'     → demo_mode=True   ← 想關掉，結果打開了
LOCAL_DEMO_MODE='false' → demo_mode=True
```

在正式環境，這等於整個系統靜默降級為記憶體假資料 + 固定 JWT 密鑰的無認證系統。
已改為只認 `1`／`true`／`yes`／`on`，並以 20 項測試釘住開關與正式環境的隔離。

### 關於 demo 種子的部門配置

需求原文建議把 `demo-candidate-002` 改成與 demo 主管同部門。**刻意未照做**：
測試需求「Demo Manager 只能看到同部門的待指派考核」需要一筆**不同部門**的
待指派考核才有東西可證。因此保留陳小雯（DESIGN）作為對照組，
另以張小豪（ENG，`demo-candidate-004`）作為 QA 的操作對象——
兩者在 quickstart 的表格中明確標示用途。

## 尚未完成與風險

1. **沒有登入頁**（既有問題，非本功能造成）。專案至今沒有取得 JWT 的介面；
   `setAuthToken` 有匯出但在本功能之前無人呼叫。本頁提供貼上權杖的欄位作為權宜之計。
   正式登入流程需另立功能。

2. **權杖存於 localStorage**。與既有 HR／主管頁同一個機制（`recruitment.jwt`），
   本功能未改變它。若日後導入登入流程，應一併檢討權杖的保存方式。

3. **DOM 綁定層無自動化測試**。與 spec 002 同一取捨：判斷邏輯已抽成純函式，
   `ask.js` 剩下的是節點寫入與事件綁定，其風險以無頭渲染驗證涵蓋。

4. **未驗證的互動**：實際點擊送出後的成功訊息、後端錯誤（缺測資、409）在畫面上的
   呈現，無頭截圖無法驅動。API 層的錯誤已由後端契約測試覆蓋，但前端呈現未看過。

5. **`theme.css` 尚無視覺回歸測試**。目前靠人工比對截圖確認作答頁未變。
   若日後兩頁樣式持續增長，值得考慮加上視覺回歸工具——但那會引入 npm 相依，
   與「無建置流程」的既有決策衝突，需另行評估。

## 安全模型確認

- 後端零變更；部門隔離、JWT 驗證、`assign-question` 的狀態與測資檢查全部保留。
- 前端不做任何權限判斷：清單內容由後端依權杖的 `dept_id` 決定，
  出題頁只是把後端回傳的結果畫出來。
- 出題頁不接觸應徵者的 token、作答內容、AI 報告或決策資料。
- 角色邊界由測試雙向守護：`frontend/manager/` 不匯入應徵者模組，反之亦然。
