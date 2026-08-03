# 驗證報告：內部人員登入

**功能**：[004-internal-login](spec.md) | **日期**：2026-08-03

## 修改檔案

### 新增

| 檔案 | 責任 |
|------|------|
| `backend/src/auth/provider.py` | 密碼驗證介面與例外（`AuthProvider` 協定） |
| `backend/src/auth/supabase_auth.py` | 正式實作：Supabase Auth password grant |
| `backend/src/auth/fake_auth.py` | 測試替身 + demo 帳號 |
| `backend/src/api/auth.py` | `POST /auth/login` |
| `backend/tests/contract/test_auth_login.py` | 10 項契約測試 |
| `supabase/migrations/0012_internal_users_bootstrap.sql` | 登入用的自我查詢政策 |
| `frontend/login.html`、`js/login.js`、`css/login.css` | 登入頁 |
| `frontend/js/session.js` | 三個內部頁面共用的登入狀態 |
| `frontend/js/login-target.js` + `tests/login-target.test.js` | 導向目標與 open redirect 防護（6 項測試） |

### 修改

| 檔案 | 變更 |
|------|------|
| `backend/src/main.py` | 掛載 auth router、組裝 AuthProvider、`/health` 回報 `demo_mode` |
| `backend/src/config.py` | 新增 `session_ttl_hours`（`SESSION_TTL_HOURS`，預設 8） |
| `backend/src/dependencies.py` | 新增 `get_auth_provider` |
| `backend/src/repositories/base.py` | 新增 `ROLE_AUTHENTICATED` |
| `backend/src/repositories/memory_store.py` | 鏡射 0012 政策——登入中的身分只能讀自己那一列 |
| `backend/src/demo.py` | 新增 ENG 部門的待指派考核（張小豪），使 demo 主管登入後有對象可出題 |
| `frontend/js/api.js` | 新增 `auth.login`、`system.health`、`clearAuthToken` |
| `frontend/js/hr.js`、`js/manager.js` | 未登入導向登入頁；401 改為重新登入（原本只能 alert「請先登入」） |
| `frontend/manager/ask.*` | 移除貼權杖面板，改為登入導向；頁首顯示登入者與登出 |
| `backend/tests/conftest.py` | 新增 `fake_auth` 夾具 |
| `backend/tests/unit/test_demo_mode.py` | `/health` 斷言放寬以容納 `demo_mode` |

## 驗證結果

| 關卡 | 結果 |
|------|------|
| 前端純邏輯 | **74 passed**（新增前 68，login-target 新增 6） |
| 後端全套 | **305 passed, 33 skipped**（新增前 295，登入契約新增 10） |
| Lint | 新增檔案全數通過（`config.py:123` 的 S105 為先前既有問題） |

### 實地驗證（demo 模式，Chrome headless）

| 步驟 | 結果 |
|------|------|
| 未登入直接開 `/manager/ask.html` | 導向 `/login.html?next=…`（標題確認為登入頁） |
| 登入頁 | 正常渲染；demo 帳號提示只在 `demo_mode` 為真時出現 |
| 輸入 `manager@example.com` / `demo1234` 送出 | 導回出題頁 |
| 出題頁頁首 | 顯示「Demo 工程主管｜ENG」與登出按鈕 |
| 待指派清單 | 帶出「張小豪｜資深後端工程師（ENG）」，「1 位待指派」 |

**不再需要貼任何權杖。**

## 安全考量與其處理

| 風險 | 處理 |
|------|------|
| **帳號列舉** | 帳號不存在／密碼錯誤／非內部使用者三者回應完全相同，並以測試斷言兩者 `json()` 相等 |
| **Open redirect** | `next` 只接受同源絕對路徑；拒絕 `https://`、`//`、`/\`、控制字元與相對路徑，6 項測試涵蓋 |
| **個資散布** | 權杖不含 Email 與姓名，以測試斷言 |
| **RLS 放寬** | 0012 的條件為 `auth_user_id = app_auth_user_id()`，只可能命中請求者本人；`anon` 仍被 0009 擋住 |
| **正式環境印出憑證** | demo 帳號提示以 `/health` 的 `demo_mode` 為條件 |
| **401 濫觸發登出** | `handleAuthFailure` 只認 401／403；其餘錯誤保留原訊息，避免掩蓋真正原因 |

## 尚未完成與風險

1. **`SupabaseAuthProvider` 未經真實 Supabase 驗證**。本機沒有 Supabase 實例，
   該實作只通過離線的介面契約測試。首次部署必須實測 password grant 的回應形狀
   （`access_token` 與 `user.id`）。

2. **0012 必須先套用**，否則登入會在「查角色」那一步失敗並回 401。
   這條 migration 是資料庫變更，套用到正式環境前需要你確認。

3. **內部帳號的建立流程未定**。`internal_users.auth_user_id` 必須對應 Supabase Auth
   的真實使用者，但「誰來建帳號、怎麼建」沒有介面也沒有腳本。

4. **權杖存於 `localStorage`**，可被 XSS 竊取。與既有頁面一致，本功能未改變它。
   要真正防禦需改為 httpOnly cookie，那會動到整個請求路徑，屬獨立變更。

5. **沒有忘記密碼／變更密碼**。

6. **登入頁的 DOM 綁定無自動化測試**。判斷邏輯（導向目標）已抽成純函式並覆蓋，
   表單提交與錯誤顯示以無頭渲染驗證。

7. **`demo.py` 新增了種子資料**。原本唯一待指派的考核在 DESIGN 部門，而 demo 主管
   屬 ENG——以前可以手工簽一張 DESIGN 權杖繞過，有了登入頁就繞不過了。
   新增的張小豪（ENG）讓 demo 主管登入後就有對象；陳小雯（DESIGN）刻意保留，
   用來呈現部門隔離。
