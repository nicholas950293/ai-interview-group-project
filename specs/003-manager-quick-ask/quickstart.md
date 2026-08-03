# Quickstart：QA 的最小端到端流程

**功能**：[003-manager-quick-ask](spec.md)（出題頁）+ [004-internal-login](../004-internal-login/spec.md)（登入）

本文件是**一條可被操作驗證的完整路徑**：

```text
Demo Manager 登入 → 看到同部門的待指派考核 → 輸入題目 → 指派
   → Candidate 以 demo token 開啟作答頁 → 顯示剛指派的題目
   → 作答並提交 → 顯示提交成功
```

## 啟動

```bash
LOCAL_DEMO_MODE=1 uvicorn backend.src.main:app --reload
```

demo 模式使用記憶體資料與替身服務，**不需要** Supabase、Docker 或 SMTP。
**資料在重啟後回到初始狀態**——重跑流程只要重啟伺服器。

> **前端與後端必須同源。** 不要用 `python3 -m http.server` 之類的純靜態伺服器開前端，
> 那樣頁面出得來但 `/api/*` 全部 404。用上面這個指令，它會一併提供 `frontend/`。

## demo 種子資料

| 對象 | Email／Token | 部門 | 狀態 | 用途 |
|------|-------------|------|------|------|
| Demo 工程主管 | `manager@example.com` / `demo1234` | ENG | — | **QA 的操作者** |
| Demo HR | `hr@example.com` / `demo1234` | 全公司 | — | 檢視全公司總覽 |
| 張小豪 | `demo-candidate-004` | ENG | 待指派題目 | **QA 的操作對象** |
| 林小明 | `demo-candidate-001` | ENG | 待應徵者作答 | 已有題目，勿動 |
| 陳小雯 | `demo-candidate-002` | **DESIGN** | 待指派題目 | **部門隔離的對照組** |
| 王大同 | `demo-candidate-003` | ENG | 待主管審核 | 已提交 |

> **陳小雯刻意留在 DESIGN。** demo 主管屬 ENG，因此她**不應該**出現在出題頁的清單裡——
> 這是「主管只看得到自己部門」的可觀察證據。若把她也改成 ENG，這條規則就沒東西可驗了。

## 主線流程

### 1. 先看應徵者現在看到什麼

開 <http://localhost:8000/candidate/assessment.html?token=demo-candidate-004>

**預期**：「題目準備中，主管尚未完成出題。」不應出現作答區。

### 2. 未登入直接開出題頁

開 <http://localhost:8000/manager/ask.html>

**預期**：自動導向 `/login.html?next=%2Fmanager%2Fask.html`。

### 3. 登入

輸入 `manager@example.com` / `demo1234`。

**預期**：
- 自動回到出題頁（因為步驟 2 記住了 `next`）
- 頁首右上顯示「Demo 工程主管｜ENG」與登出按鈕
- 卡片標題右側顯示「1 位待指派」

### 4. 確認只看得到同部門的人

展開「送給誰」下拉。

**預期**：只有「張小豪｜資深後端工程師（ENG）」。
**陳小雯（DESIGN）不得出現。**

### 5. 輸入題目並送出

- **題目**：第一行是標題，其餘是敘述。例如：

  ```text
  實作一個帶 TTL 的 LRU 快取

  請設計並實作支援存活時間的 LRU 快取，需支援 get(key) 與 put(key, value, ttl)，
  兩者平均時間複雜度皆為 O(1)。容量已滿時淘汰最久未使用的項目。
  ```

- **範例測資**：輸入 `3 5`、預期輸出 `8`
  （工程職缺後端強制要求測資，留空會被拒絕——見下方邊界情境）

按「送出給應徵者」。

**預期**：卡片下方出現綠色訊息
「✓ 題目已送給 張小豪｜資深後端工程師（ENG）。該筆考核轉為「待應徵者作答」…」

### 6. 應徵者看到題目

重新整理步驟 1 的分頁。

**預期**：
- 職缺變成「資深後端工程師」
- 題目標題與敘述正是你剛才輸入的
- 範例測資顯示 `3 5` → `8`
- 出現程式碼編輯器、語言選擇與試跑按鈕

### 7. 作答並提交

在作答區輸入任意內容，按右上角「提交作答」，於確認視窗按「確定提交」。

**預期**：工作區隱藏，顯示「已於 …… 成功提交，感謝你的作答。」

### 8. 狀態已推進

重新整理應徵者分頁 → 顯示已完成提交的唯讀狀態。

回到出題頁重新整理 → 張小豪已不在待指派清單中（他的狀態變成「待主管審核」）。

以 HR 帳號登入 <http://localhost:8000/> 亦可看到該筆狀態為「待主管審核」。

## 邊界情境（值得順手驗）

| 操作 | 預期 |
|------|------|
| 工程職缺不填測資就送出 | 顯示後端的「工程類題目必須包含至少一組可執行的測試案例」，狀態不變 |
| 題目框留空送出 | 提示「請先輸入題目內容」，且 Network 面板**沒有**請求 |
| 密碼打錯 | 「帳號或密碼錯誤」 |
| 用不存在的帳號登入 | **與密碼打錯完全相同的訊息**（防帳號列舉） |
| 點登出後再開出題頁 | 再次被導向登入頁 |
| 開 `?token=不存在的值` | 「找不到此測驗連結」，訊息中不含 token 值 |
| 已提交後再次提交 | 409，畫面轉為已提交的唯讀狀態 |
| 陳小雯（DESIGN）出現在 ENG 主管清單 | **不該發生**——若發生代表部門隔離破了 |

## 自動化對應

上述流程有對應的自動化測試，改動後可先跑它再手動驗：

```bash
cd backend

# 整條流程 + 拒絕行為（9 項）
LOCAL_DEMO_MODE= pytest tests/integration/test_demo_e2e_flow.py

# demo 模式的開關與「正式環境拒絕 demo 憑證」（20 項）
LOCAL_DEMO_MODE= pytest tests/unit/test_demo_mode_gate.py
```

> **為什麼指令前面要加 `LOCAL_DEMO_MODE=`**：`backend/src/config.py` 會讀取本機 `.env`，
> 若你的 `.env` 設了 `LOCAL_DEMO_MODE`，它會滲入測試程序並以 demo 密鑰覆寫測試密鑰，
> 使所有需認證的測試回傳 401。這是既有問題，記於
> [spec 002 verification.md](../002-candidate-assessment-ui/verification.md) 風險 1。

## 這條流程沒有涵蓋的

刻意不在本次範圍內，QA 不必驗：

- **AI 自動評測**：提交會觸發背景評測，但 demo 模式用的是替身，報告內容無意義。
- **Email 通知**：demo 模式的 `FakeEmailSender` 不會真的寄信。
- **程式碼試跑**：demo 模式的沙箱是替身，回傳的是預先註冊的結果而非真的執行。
  按「試跑」不會壞，但輸出不代表真實執行。
- **正式環境的登入**：demo 帳號只存在於 `FakeAuthProvider`。正式環境走 Supabase Auth，
  且必須先套用 `supabase/migrations/0012_internal_users_bootstrap.sql`
  （原因見 [spec 004](../004-internal-login/spec.md)）。
