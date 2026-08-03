# Quickstart：應徵者作答介面的驗證指南

**功能**：[002-candidate-assessment-ui](spec.md)

本文件涵蓋兩件事：如何在本機把應徵者介面跑起來，以及自動化測試**沒有**涵蓋的
手動驗收項目（DOM 綁定層、CDN 降級、無障礙）。

## 自動化驗證

三條指令，全部離線可執行：

```bash
# 1. 純邏輯層（Node 18+，零 npm 安裝）
cd frontend && node --test "candidate/tests/*.test.js"

# 2. 結構不變條件 + 全部既有行為
cd backend && pytest

# 3. Lint
ruff check backend --config backend/ruff.toml
```

> **注意**：若本機 `.env` 設有 `LOCAL_DEMO_MODE`，`backend/src/config.py` 的
> `load_dotenv()` 會把它帶進測試程序，使 `load_settings()` 以 demo 密鑰覆寫測試密鑰，
> 導致所有需認證的 HR／主管測試回傳 401。此為既有問題（非本功能造成），
> 暫以 `LOCAL_DEMO_MODE= pytest` 規避。詳見 [verification.md](verification.md)。

## 本機啟動

```bash
# demo 模式：記憶體資料 + 全替身服務，不需 Supabase、Docker 或 SMTP
LOCAL_DEMO_MODE=1 uvicorn backend.src.main:app --reload
```

demo 種子資料提供以下入口：

| 角色 | 網址 |
|------|------|
| 應徵者（正式路徑） | <http://localhost:8000/candidate/assessment.html?token=demo-candidate-001> |
| 應徵者（舊路徑，應自動轉址） | <http://localhost:8000/assessment.html?token=demo-candidate-001> |
| HR | <http://localhost:8000/> |
| 主管 | <http://localhost:8000/manager.html> |

## 手動驗收清單

自動化測試涵蓋判定邏輯與結構邊界；以下項目需要真實瀏覽器。

### A. 畫面狀態（US1）

- [ ] 開啟 `?token=demo-candidate-001` → 顯示作答工作區，標題含職缺名稱，
      右上顯示到期時間與剩餘試跑次數
- [ ] 移除 `?token=` → 顯示「連結不完整」；開啟 DevTools Network 確認**沒有**發出
      任何 `/candidate/session/` 請求
- [ ] 改為不存在的 token → 顯示「找不到此測驗連結」，且訊息中不含 token 值
- [ ] 舊路徑 `/assessment.html?token=…` → 自動轉址至 `/candidate/assessment.html`，
      且網址列保留 `?token=`；按上一頁**不會**又被彈回轉址頁

### B. 工程類作答（US2）

- [ ] 程式碼編輯器出現語法標示；切換語言後**已輸入的內容不遺失**
- [ ] 於 DevTools 封鎖 `esm.sh` 後重新載入 → 退回純文字輸入框，仍可輸入與提交
- [ ] 於 DevTools 封鎖 `fonts.googleapis.com` 後重新載入 → 退回系統字型，版面不變形
- [ ] 點試跑 → 按鈕於請求期間停用，輸出區先顯示「執行中…」，
      完成後顯示輸出、終止原因與耗時，剩餘次數減一
- [ ] 連續快速點擊試跑 → Network 面板只有一筆請求

### C. 非工程類作答（US3）

- [ ] 以非工程類部門的 token 開啟（demo 資料需自行建立）→ 顯示文字作答區，
      且語言選擇、試跑按鈕、標準輸入、執行結果區塊**全部不出現**

### D. 提交（US4）

- [ ] 點提交 → 出現頁內確認對話，文字明確說明「無法修改」
- [ ] 在對話中選「返回作答」→ Network 面板無提交請求，作答內容原封不動
- [ ] 選「確定提交」→ 工作區隱藏，顯示含提交時間的成功訊息
- [ ] 重新整理同一連結 → 顯示已提交的唯讀狀態

### E. AI 助教（US5）

- [ ] 送出一則問題後重新整理頁面 → **對話內容仍在**（FR-128 修正的行為）
- [ ] 送出問題時顯示「思考中…」暫時訊息
- [ ] 在 DevTools 將 `/candidate/session/*/chat` 攔截為 503 → 錯誤只出現在助教區塊，
      且試跑與提交按鈕**仍可按**

### F. 無障礙（NFR-006）

- [ ] 以鍵盤 Tab 可依序抵達語言選擇 → 試跑 → 提交 → 助教輸入
- [ ] 開啟螢幕報讀器，狀態提示區（逾期／已提交）會被朗讀（`role="status"`）
- [ ] 提交確認對話開啟時焦點被限制在對話內

## 需要後端配合才能驗的情境

以下情境在 demo 模式下無法直接重現，需以真實後端或修改種子資料驗證：

| 情境 | 對應需求 | 驗證方式 |
|------|---------|---------|
| 連結逾期（410） | FR-108、FR-121 | 將該筆考核的 `token_expires_at` 調到過去 |
| 題目準備中 | FR-108 | 建立狀態為 `PENDING_ASSIGN` 的考核 |
| 試跑次數用盡（429） | FR-119 | 將 `trial_run_count` 設為 `MAX_TRIAL_RUNS` |
| 沙箱不可用（503） | FR-120 | 停止 Docker daemon 後試跑 |
