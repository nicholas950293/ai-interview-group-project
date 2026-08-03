# AI 智慧招聘與技術考核系統

整合 HR、部門主管與應徵者三種角色的招聘技術考核平台。核心流程為：

> HR 建案並產生 7 天效期連結 → 主管出題（題庫或 AI 生成）→ 應徵者免登入作答並試跑程式碼
> → 系統於隔離沙箱驗證並產出四維度 AI 報告 → 主管決策 → HR 寄送通知

規格文件位於 [specs/001-ai-recruitment-assessment/](specs/001-ai-recruitment-assessment/)，
專案治理規範見 [.specify/memory/constitution.md](.specify/memory/constitution.md)。

## 專案結構

```text
backend/     FastAPI 服務。src/ 為程式碼，tests/ 為測試（憲章要求兩者分離）
frontend/    靜態前端（原生 ES2022 模組，無建置流程）
  login.html                                             內部人員登入（spec 004）
  index.html / manager.html / js/hr.js / js/manager.js   內部介面（HR、主管）
  js/api.js                                              對後端的唯一呼叫點
  css/theme.css                                          共用設計系統（色票、按鈕、卡片）
  candidate/                                             應徵者作答介面（spec 002）
    core/   純邏輯，不碰 DOM，可於 Node 直接測試
    ui/     DOM 綁定，不做判定、不呼叫 API
  manager/                                               面試官簡易出題頁（spec 003）
sandbox/     五種語言的沙箱映像檔定義
supabase/    版本控管的資料庫遷移檔與合成測試資料
specs/       規格、計畫、資料模型、契約與任務清單
```

## 建置

```bash
# 1. 後端相依
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt

# 2. 環境變數
cp .env.example .env    # 填入實際值；.env 不得進入版本控管

# 3. 資料庫結構
supabase db push        # 套用 supabase/migrations/
psql "$DATABASE_URL" -f supabase/seed.sql   # 合成測試資料（選用）

# 4. 沙箱映像檔（需 Docker）
for lang in javascript python go java cpp; do
  docker build -t "sandbox-$lang" "sandbox/$lang"
done

# 5. 啟動 API（同時也會提供 frontend/ 的靜態檔，開發時用這個就夠）
uvicorn backend.src.main:app --reload
#    → http://localhost:8000/login.html                        內部人員登入
#    → http://localhost:8000/                                 HR 總覽
#    → http://localhost:8000/manager/ask.html                  面試官出題
#    → http://localhost:8000/candidate/assessment.html?token=… 應徵者作答
```

> **不要用純靜態伺服器開前端。** `python3 -m http.server --directory frontend`
> 這類伺服器給得出頁面，但 `/api/*` 會全部 404，畫面看起來像壞掉。
> 前端與後端必須同源，或由反向代理把 `/api` 指向後端。

```bash
# 本機 demo：記憶體資料 + 全替身服務，不需 Supabase、Docker 或 SMTP
LOCAL_DEMO_MODE=1 uvicorn backend.src.main:app --reload
```

demo 帳號（合成資料，非真實憑證）：`hr@example.com` 與 `manager@example.com`，
密碼皆為 `demo1234`。登入頁會在 demo 模式下自行顯示這段提示。

**完整的 demo 流程（主管出題 → 應徵者作答 → 提交）**，含每一步的預期結果與邊界情境，
見 [specs/003-manager-quick-ask/quickstart.md](specs/003-manager-quick-ask/quickstart.md)。

> `LOCAL_DEMO_MODE` 只接受 `1`／`true`／`yes`／`on`。其餘值（含 `0`、`false`）
> 一律視為關閉——demo 模式會把整個系統換成記憶體假資料與固定 JWT 密鑰，
> 它的開關必須是「明確要求」才算數。

> **正式環境**：內部人員的密碼由 Supabase Auth 保管，本系統不儲存密碼。
> 部署前必須套用 `supabase/migrations/0012_internal_users_bootstrap.sql`，
> 否則登入會在查詢角色那一步失敗（原因見 [spec 004](specs/004-internal-login/spec.md)）。

## 測試

測試分為兩組，見 [research.md](specs/001-ai-recruitment-assessment/research.md) R-008。
設定檔為 `backend/pytest.ini`，因此測試指令自 `backend/` 目錄執行：

```bash
cd backend

# 預設套件：無網路、無外部服務、無 Docker 即可全數通過（憲章原則 II）
pytest

# 安全套件：需本機 Docker 與已建置的沙箱映像檔（憲章「安全關卡」）
pytest -m security

# RLS 政策測試：需本機 PostgreSQL；未設定時自動跳過
TEST_DATABASE_URL=postgresql://localhost/test_recruitment pytest -m postgres
```

`pytest` 預設即排除 `security` 標記，因此「直接執行 pytest」等同於離線套件。

### 前端測試

前端的純邏輯層（`candidate/core/`、`manager/core/`）以 Node 內建的測試執行器驗證，
不需要 npm 安裝、瀏覽器或網路（需 Node 18 以上）：

```bash
cd frontend
npm test        # 等同 node --test tests/ candidate/tests/ manager/tests/
```

`frontend/package.json` 只宣告 `"type": "module"` 與測試指令，不含任何相依套件——
專案維持「無建置流程」的既有決策。應徵者介面的結構性不變條件（禁止直接 `fetch`、
角色間的匯入邊界、頁面路徑不遮蔽 API 路由）由
`backend/tests/unit/test_candidate_frontend_boundaries.py` 守護，隨 `pytest` 一併執行。

## 品質關卡

功能宣告完成前必須全數成立（憲章「開發流程與品質關卡」）：

| 關卡 | 驗證方式 |
|------|---------|
| 離線測試套件 | `cd backend && pytest` 全數通過，且過程不需網路 |
| 安全關卡 | `pytest -m security` 驗證網路阻斷、資源耗盡中止、檔案系統存取阻擋 |
| 權限關卡 | 跨部門主管、HR 讀取受限表、應徵者跨考核存取三類越權測試皆斷言拒絕行為 |

## Lint

```bash
ruff check backend --config backend/ruff.toml
ruff format backend --config backend/ruff.toml
```

## 部署

### 環境變數

全部設定由環境變數提供，`.env.example` 列出完整清單與用途說明。
其中三項為**必填**，缺少時應用程式啟動即失敗（`backend/src/config.py`）：

| 變數 | 用途 |
|------|------|
| `SUPABASE_URL` | Supabase 專案位址 |
| `SUPABASE_ANON_KEY` | 前端與應徵者路徑使用的公開金鑰 |
| `SUPABASE_JWT_SECRET` | 驗證內部使用者 JWT 的簽章密鑰 |

其餘為選填。AI 與 SMTP 未設定時，對應功能回傳 503 或標記寄送失敗，
但建案、指派、作答、試跑、提交與決策等核心流程仍可運作（FR-052、FR-059、FR-072）。

> **`SUPABASE_SERVICE_ROLE_KEY` 僅供資料庫遷移與維護作業使用。**
> 它會完全繞過 RLS，因此不得用於處理使用者請求；
> `backend/tests/unit/test_service_role_guard.py` 會在 CI 中守護這條規則。

### 部署順序

1. 套用 `supabase/migrations/` 的全部遷移檔（依檔名順序）。
2. 建置五個沙箱映像檔並確認 `docker images` 可見 `sandbox-*`。
   **沙箱映像檔未建置時，系統會判定沙箱不可用並降級為「接受提交但不執行」**
   （憲章原則 VI），不會改以未隔離的方式執行程式碼。
3. 設定環境變數並啟動 API。
4. 以任意靜態伺服器提供 `frontend/`，並將反向代理的 `/api` 指向後端。

### 上線前必須完成的事

- [ ] **實測 `GEMINI_MODEL` 的可用性**。PRD 指定的 `gemini-3-flash-preview`
      為預覽版 ID，其可用性、配額與速率限制必須以實際 API 呼叫驗證
      （[research.md](specs/001-ai-recruitment-assessment/research.md) R-005）。
      若不可用，改用當時可用的 flash 級模型——只需變更環境變數。
- [ ] 在具備 Docker 的環境執行 `pytest -m security`，確認沙箱隔離全數通過。
- [ ] 以本機 PostgreSQL 執行 `TEST_DATABASE_URL=... pytest -m postgres`，確認 RLS 政策生效。
- [ ] 依 [quickstart.md](specs/001-ai-recruitment-assessment/quickstart.md) 執行 11 個端到端情境。
- [ ] **實測登入**。`SupabaseAuthProvider` 只通過離線契約測試，未對真實 Supabase 驗證過；
      同時確認 `0012_internal_users_bootstrap.sql` 已套用，否則登入會在查詢角色時失敗
      （[spec 004](specs/004-internal-login/verification.md)）。

驗證狀態與尚未完成的項目記錄於
[verification.md](specs/001-ai-recruitment-assessment/verification.md)。
