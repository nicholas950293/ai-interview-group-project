# 驗證紀錄

**任務**：T110、T111 | **日期**：2026-08-02
**測試套件狀態**：`cd backend && pytest` → **267 passed、33 skipped**、lint 全數通過

本文件記錄 [quickstart.md](quickstart.md) 的 11 個端到端情境的驗證狀態，
以及對[憲章 v2.0.0](../../.specify/memory/constitution.md) 的最終合規檢查。

## 驗證環境的限制

本次驗證環境**沒有 Docker，也沒有本機 PostgreSQL**。因此：

- 需要真實容器的斷言（沙箱隔離）與需要真實資料庫的斷言（RLS 政策）
  **測試已撰寫但未執行**，於下表標示為「待驗證」。
- 這些行為在離線套件中由 `FakeSandboxRunner` 與 `InMemoryDataStore` 覆蓋。
  後者**鏡射** RLS 政策矩陣與 SECURITY DEFINER 函式，使「他部門查不到資料」
  這類斷言在離線環境仍是一項真實的測試——但它驗證的是**應用層看到的結果**，
  不是資料庫的拒絕行為。憲章「權限關卡」要求的是後者。

**結論**：功能尚不得依憲章「開發流程與品質關卡」宣告完成，
必須先在具備 Docker 與 PostgreSQL 的環境補跑兩組測試。

## quickstart 情境驗證狀態

| # | 情境 | 對應測試 | 狀態 |
|---|------|---------|------|
| 1 | HR 建案至取得連結（SC-001） | `test_us1_create_flow.py`、`test_hr_create_assessment.py` | ✅ 通過 |
| 2 | 跨部門隔離（SC-008） | `test_us2_dept_isolation.py` | ✅ 通過（應用層）<br>⏳ `test_rls_dept_isolation.py` 待 PostgreSQL |
| 3 | AI 出題與指派（SC-002） | `test_manager_ai_generate.py`、`test_us2_assign_requires_testcases.py` | ✅ 通過（替身）<br>⏳ 60 秒目標待實際 API 量測 |
| 4 | 應徵者作答與試跑（SC-003、SC-004） | `test_candidate_session.py`、`test_candidate_run.py`、`test_performance.py` | ✅ 通過（系統開銷）<br>⏳ 實際執行時間待 Docker |
| 5 | 沙箱隔離（SC-009、SC-010） | `tests/security/*` | ⏳ **待 Docker**（SC-010 的併發性質已於 `test_performance.py` 驗證） |
| 6 | 提交與自動評測（SC-005） | `test_us4_evaluation_flow.py`、`test_ai_report_shape.py`、`test_us3_submit_once.py` | ✅ 通過 |
| 7 | AI 助教 Guardrail（SC-013） | `test_us7_guardrail.py`、`test_candidate_chat.py` | ✅ 通過（替身）<br>⏳ 實際模型的攔截率待線上量測 |
| 8 | 主管決策與 HR 可見範圍（SC-011、SC-012） | `test_us5_decision_revision.py`、`test_us6_no_leak.py` | ✅ 通過（應用層）<br>⏳ `test_rls_hr_restriction.py` 待 PostgreSQL |
| 9 | 連結逾期與重新產生 | `test_us3_expiry.py`、`test_token_functions.py` | ✅ 通過（應用層）<br>⏳ SQL 函式版本待 PostgreSQL |
| 10 | 外部服務降級 | `test_us3_sandbox_degraded.py`、`test_us4_evaluation_failure.py`、`test_us7_ai_unavailable.py`、`test_us6_send_failure.py` | ✅ 四項降級全數通過 |
| 11 | 稽核完整性（SC-014） | `test_audit_completeness.py`、`test_append_only.py` | ✅ 通過（應用層）<br>⏳ 資料庫層的 UPDATE／DELETE 拒絕待 PostgreSQL |

## 憲章合規最終檢查

| 原則 | 狀態 | 依據 |
|------|------|------|
| I. 規格驅動交付 | 通過 | 112 項任務皆對應 FR 編號；實作期間未新增規格外的行為 |
| II. 測試優先驗證（不可妥協） | **部分** | 離線套件 267 項全數通過且不需網路／外部服務；但安全套件（Docker）與 RLS 套件（PostgreSQL）尚未執行，見上方限制說明 |
| III. 有依據的技術選型與最小範圍 | 通過 | 執行期相依未超出 plan.md 技術脈絡；未引入訊息佇列、前端框架或多 AI 供應商 |
| IV. 應徵者資料保護與最小權限 | 通過 | RLS 政策矩陣已實作於 0009；`service_role` 守護測試通過；日誌過濾器與靜態檢查皆到位（`test_log_pii_filter.py`）；測試資料全為合成資料 |
| V. 可稽核且公平的評估 | 通過 | 四張唯附加表 + 觸發器；`AiReport` 型別不存在總分欄位；`strip_aggregate_judgement` 剝除模型輸出的綜合建議 |
| VI. 不受信任程式碼的隔離執行（不可妥協） | **部分** | 12 項容器參數已實作於 `docker_runner.py` 並有逐項對應的測試；降級路徑（接受提交但不執行）已驗證通過；但**隔離效果本身尚未在真實容器上驗證** |

### 品質關卡

| 關卡 | 狀態 |
|------|------|
| 完整測試套件通過，且可在無網路環境執行 | ✅ 離線套件 267 項通過 |
| 每項 FR 對應到已完成的任務與通過的測試 | ✅ 見 tasks.md 與各測試檔的 FR 標註 |
| tasks.md 中沒有任務在缺少對應實作的情況下被勾選 | ✅ T022–T025、T066–T069 因無法執行驗證而**刻意保持未勾選** |
| 安全關卡（網路阻斷、資源耗盡、檔案系統） | ⏳ 待 Docker |
| 權限關卡（資料存取層的拒絕行為） | ⏳ 待 PostgreSQL |

### 記錄在案的實作偏離

| 偏離 | 理由 |
|------|------|
| 容器以 `finally` 中的 `remove(force=True)` 銷毀，而非 `--rm` | 契約表列 `--rm`；改用明確移除是**更強**的保證（`--rm` 在守護程序異常時可能不生效），且讓我們能在移除前讀取 `State.OOMKilled` 以正確判定 `MEMORY_LIMIT`。FR-042 要求的「執行結束後必須銷毀」完全滿足 |
| 新增兩個 SECURITY DEFINER 函式（`record_evaluation_start`／`record_evaluation_result`） | data-model.md 列出四個函式，但背景評測同樣不持有使用者 JWT。若不新增，評測寫入只能走 `service_role`，直接牴觸 R-002。兩者同樣以不可推測的 token 為鍵 |
| 新增 `backend/src/dependencies.py` 與 `repositories/memory_store.py` | 前者是 FastAPI 相依的集中處（plan.md 的檔案清單非窮舉）；後者是資料庫這個外部服務的替身，與 `fake_runner`／`fake_provider`／`fake_sender` 同一模式，為憲章原則 II 所要求 |
| `PIDS_LIMIT` 以 stderr 訊息特徵判定 | pids cgroup 觸發時，程序看到的是配置失敗而非可查詢的旗標。判定邏輯集中於 `_to_result`，並由 `test_sandbox_resources.py` 固定行為 |

## 尚未完成的項目

1. **在具備 Docker 的環境執行 `pytest -m security`**（T066–T069）。
   若安全套件無法通過，**不得**以放寬容器參數的方式讓測試變綠——
   依憲章原則 VI，正確的降級是「接受提交但不執行」。
2. **在具備 PostgreSQL 的環境執行 `pytest -m postgres`**（T022–T025）。
3. **實測 `GEMINI_MODEL` 的可用性**（research.md R-005）。
4. 以真實模型量測 SC-002（60 秒出題）與 SC-013（guardrail 攔截率 < 1%）。
