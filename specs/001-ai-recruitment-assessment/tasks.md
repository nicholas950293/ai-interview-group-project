---

description: "AI 智慧招聘與技術考核系統：依使用者故事組織的實作任務清單"
---

# 任務清單：AI 智慧招聘與技術考核系統

**輸入**：設計文件位於 `specs/001-ai-recruitment-assessment/`

**前置文件**：[plan.md](plan.md)、[spec.md](spec.md)、[research.md](research.md)、
[data-model.md](data-model.md)、[contracts/](contracts/)、[quickstart.md](quickstart.md)

**測試**：**強制，非選用**。[憲章 v2.0.0](../../.specify/memory/constitution.md)
原則 II「測試優先驗證」標示為不可妥協——測試必須先於實作撰寫、必須先失敗，
且任務唯有測試通過才可勾選完成。

**組織方式**：任務依使用者故事分組，使每個故事可獨立實作、獨立測試、獨立交付。

## 格式：`[ID] [P?] [Story] 描述`

- **[P]**：可平行執行（不同檔案、無未完成的相依）
- **[Story]**：所屬使用者故事（US1～US7）
- 每項任務皆含明確檔案路徑

## 路徑慣例

依 [plan.md](plan.md) 的結構決策：`backend/src/`、`backend/tests/`、
`frontend/`、`sandbox/`、`supabase/migrations/`

---

## Phase 1：環境建置（共用基礎）

**目的**：專案初始化與基本結構

- [ ] T001 移除 v1 失效草稿 `src/assessment.py` 與 `tests/unit/test_assessment_flow.py`，並刪除空目錄
- [ ] T002 建立專案目錄結構 `backend/src/`、`backend/tests/`、`frontend/`、`sandbox/`、`supabase/migrations/`
- [ ] T003 建立 `backend/requirements.txt`（FastAPI、uvicorn、Pydantic v2、supabase-py、google-generativeai、docker、httpx、PyJWT、pytest、pytest-asyncio）
- [ ] T004 [P] 建立 `backend/pytest.ini`，註冊 `security` marker 並設定預設排除（對應 research.md R-008）
- [ ] T005 [P] 建立 `backend/ruff.toml` 設定 linting 與格式化規則
- [ ] T006 [P] 建立 `.env.example`，列出全部環境變數且不含任何實際值（憲章：金鑰不得進版控）
- [ ] T007 建立 `backend/src/config.py`，以環境變數載入所有設定，缺少必要變數時啟動即失敗
- [ ] T008 [P] 建立前端骨架 `frontend/index.html`、`frontend/manager.html`、`frontend/assessment.html`，引入 Tailwind CSS CDN
- [ ] T009 [P] 建立 `README.md`，說明專案用途、建置步驟與測試指令

---

## Phase 2：基礎建設（阻斷性前置作業）

**目的**：所有使用者故事共同依賴的核心基礎設施

**⚠️ 關鍵**：本階段完成前，任何使用者故事皆不得開始

### 資料庫結構（對應 data-model.md）

- [ ] T010 [P] 建立遷移檔 `supabase/migrations/0001_departments.sql`（含 type CHECK 約束）
- [ ] T011 [P] 建立遷移檔 `supabase/migrations/0002_internal_users.sql`（含 role/dept_id 一致性 CHECK 與每部門單一 active 主管的部分唯一索引）
- [ ] T012 [P] 建立遷移檔 `supabase/migrations/0003_question_banks.sql`（含 test_cases JSONB 與 difficulty CHECK）
- [ ] T013 [P] 建立遷移檔 `supabase/migrations/0004_assessments.sql`（含 status CHECK、token UNIQUE、final_decision、email_status）
- [ ] T014 [P] 建立遷移檔 `supabase/migrations/0005_execution_records.sql`（含 termination_reason CHECK）
- [ ] T015 [P] 建立遷移檔 `supabase/migrations/0006_ai_reports.sql`（含 attempt_no、status、dimensions JSONB）
- [ ] T016 [P] 建立遷移檔 `supabase/migrations/0007_manager_decisions.sql`（含 revision_no 與 assessment_id 複合唯一）
- [ ] T017 [P] 建立遷移檔 `supabase/migrations/0008_audit_logs.sql`（刻意不設 assessments 外鍵，理由見 data-model.md）
- [ ] T018 建立遷移檔 `supabase/migrations/0009_rls_policies.sql`，實作 data-model.md 的 RLS 政策矩陣（HR 在 ai_reports 與 manager_decisions 上無任何政策）
- [ ] T019 建立遷移檔 `supabase/migrations/0010_security_definer_functions.sql`，實作 `get_assessment_by_token`、`append_chat_message`、`record_trial_run`、`submit_answer` 四個函式，每個皆於內部重新驗證 token 與效期
- [ ] T020 建立遷移檔 `supabase/migrations/0011_append_only.sql`，撤銷 execution_records、ai_reports、manager_decisions、audit_logs 的 UPDATE 與 DELETE 權限
- [ ] T021 建立 `supabase/seed.sql`，含部門、內部使用者與題庫的合成測試資料（憲章原則 IV：不得使用真實應徵者資料）

### 基礎建設測試（先撰寫，必須先失敗）

- [ ] T022 [P] 撰寫 RLS 跨部門隔離測試於 `backend/tests/integration/test_rls_dept_isolation.py`，斷言他部門主管查詢回傳空集合（FR-003、SC-008）
- [ ] T023 [P] 撰寫 HR 受限表測試於 `backend/tests/integration/test_rls_hr_restriction.py`，斷言 HR 查詢 ai_reports 與 manager_decisions 回傳空集合（FR-007、FR-008、SC-012）
- [ ] T024 [P] 撰寫唯附加測試於 `backend/tests/integration/test_append_only.py`，斷言四張表的 UPDATE 與 DELETE 皆被資料庫拒絕（FR-078）
- [ ] T025 [P] 撰寫 SECURITY DEFINER 函式測試於 `backend/tests/integration/test_token_functions.py`，斷言逾期 token 與偽造 token 皆被拒絕（FR-018）

### 應用層基礎

- [ ] T026 實作 `backend/src/repositories/base.py`，以請求者 JWT 建立 Supabase 連線（research.md R-002）
- [ ] T027 撰寫 service_role 使用範圍守護測試於 `backend/tests/unit/test_service_role_guard.py`，斷言處理使用者請求的程式路徑不使用 service_role 金鑰
- [ ] T028 [P] 建立 Pydantic 模型 `backend/src/models/question.py`（Question、TestCase，含工程類必含測資的驗證）
- [ ] T029 [P] 建立 Pydantic 模型 `backend/src/models/assessment.py`（Assessment、AssessmentStatus、CandidateSession）
- [ ] T030 [P] 建立 Pydantic 模型 `backend/src/models/report.py`（AiReport、Dimension、ExecutionResult；刻意不提供總分欄位，使 FR-057 違規在型別層即無法表達）
- [ ] T031 [P] 建立 Pydantic 模型 `backend/src/models/decision.py`（Decision、DecisionResult）
- [ ] T032 實作 `backend/src/audit/logger.py`，提供唯附加稽核寫入，並過濾個資與作答內容（FR-076～FR-080）
- [ ] T033 實作狀態機於 `backend/src/services/state_machine.py`，含 data-model.md 的合法轉換表；並撰寫測試斷言所有非法轉換皆被拒絕（FR-074、FR-075）
- [ ] T034 [P] 定義 `backend/src/sandbox/runner.py` 的 SandboxRunner Protocol 與 `backend/src/sandbox/fake_runner.py` 測試替身（契約見 contracts/sandbox-runner.md）
- [ ] T035 [P] 定義 `backend/src/ai/provider.py` 的 AiProvider Protocol 與 `backend/src/ai/fake_provider.py` 測試替身（契約見 contracts/ai-provider.md）
- [ ] T036 [P] 定義 `backend/src/email/sender.py` 的 EmailSender Protocol 與 `backend/src/email/fake_sender.py` 測試替身
- [ ] T037 建立 `backend/src/main.py`，含 FastAPI 應用程式、JWT 驗證相依、統一錯誤處理，以及禁止個資與作答內容進入日誌的過濾器（FR-079、FR-080）

**檢查點**：基礎完成——離線測試套件可執行，使用者故事可開始平行進行

---

## Phase 3：使用者故事 1 — HR 建立徵才案並邀請應徵者（優先級：P1）🎯 MVP

**目標**：HR 可新增應徵者、自動指派責任主管、取得 7 天效期的專屬連結，並於總覽頁追蹤進度

**獨立測試**：不依賴主管或應徵者任何動作，完成建案並在總覽頁看到「待指派題目」狀態

### 使用者故事 1 的測試

> **注意：先撰寫這些測試，確認其失敗後才開始實作**

- [ ] T038 [P] [US1] 撰寫契約測試 `backend/tests/contract/test_hr_create_assessment.py`，對照 contracts/openapi.yaml 的 POST /hr/assessments
- [ ] T039 [P] [US1] 撰寫契約測試 `backend/tests/contract/test_hr_list_assessments.py`，斷言回應不含 candidate_answer、ai_chat_history 與內部評語
- [ ] T040 [P] [US1] 撰寫整合測試 `backend/tests/integration/test_us1_create_flow.py`，涵蓋 quickstart.md 情境 1（建案→連結→總覽）
- [ ] T041 [P] [US1] 撰寫整合測試 `backend/tests/integration/test_us1_duplicate_invite.py`，斷言重複邀請回傳 409 且 confirm_duplicate=true 時建立成功

### 使用者故事 1 的實作

- [ ] T042 [P] [US1] 實作密碼學安全的 token 產生器於 `backend/src/services/token_service.py`（FR-015、FR-016）
- [ ] T043 [US1] 實作 `backend/src/repositories/assessment_repo.py` 的建立與查詢方法
- [ ] T044 [US1] 實作 `backend/src/services/assessment_service.py` 的建案流程（自動指派主管、產生 token、設定 7 天效期、寫入稽核）
- [ ] T045 [US1] 實作 `backend/src/api/hr.py` 的 POST /hr/assessments 與 GET /hr/assessments 端點
- [ ] T046 [US1] 實作 `backend/src/api/hr.py` 的重新指派主管端點，含 MANAGER_REASSIGNED 稽核（FR-012）
- [ ] T047 [US1] 實作 `backend/src/api/hr.py` 的重新產生連結端點，舊 token 立即失效（FR-019）
- [ ] T048 [US1] 實作前端 `frontend/js/hr.js` 與 `frontend/js/api.js`，提供總覽清單、篩選與新增表單

**檢查點**：US1 可獨立運作並通過測試——這是可展示的 MVP

---

## Phase 4：使用者故事 2 — 主管出題並指派給應徵者（優先級：P1）

**目標**：主管在部門隔離下，從題庫挑題或以 AI 生成題目，確認後指派並開通測驗

**獨立測試**：於既有考核上完成選題或生成、指派，狀態轉為「待應徵者作答」，不需應徵者參與

### 使用者故事 2 的測試

- [ ] T049 [P] [US2] 撰寫契約測試 `backend/tests/contract/test_manager_questions.py`，涵蓋 GET /manager/assessments 與 GET /manager/questions
- [ ] T050 [P] [US2] 撰寫契約測試 `backend/tests/contract/test_manager_ai_generate.py`，斷言草稿含測資、AI 不可用時回傳 503
- [ ] T051 [P] [US2] 撰寫契約測試 `backend/tests/contract/test_manager_assign.py`，涵蓋 POST assign-question
- [ ] T052 [P] [US2] 撰寫整合測試 `backend/tests/integration/test_us2_dept_isolation.py`，涵蓋 quickstart.md 情境 2（他部門考核不可見且直接存取回傳 404）
- [ ] T053 [P] [US2] 撰寫整合測試 `backend/tests/integration/test_us2_assign_requires_testcases.py`，斷言缺測資的工程類題目被拒絕指派（FR-026）

### 使用者故事 2 的實作

- [ ] T054 [US2] 實作 `backend/src/ai/gemini_provider.py` 的 generate_question，並建立提示詞檔案 `backend/src/ai/prompts/generate_question.txt`（缺測資時視為生成失敗）
- [ ] T055 [P] [US2] 實作 `backend/src/repositories/question_repo.py` 的部門題庫查詢
- [ ] T056 [US2] 實作 `backend/src/services/assessment_service.py` 的題目快照與指派邏輯（FR-028）
- [ ] T057 [US2] 實作 `backend/src/api/manager.py` 的題庫查詢、考核清單與 AI 出題端點
- [ ] T058 [US2] 實作 `backend/src/api/manager.py` 的指派端點，含狀態轉換與 QUESTION_ASSIGNED 稽核
- [ ] T059 [US2] 實作前端 `frontend/js/manager.js` 的題庫選擇、AI 生成、草稿編輯與指派介面

**檢查點**：US1 與 US2 皆可獨立運作

---

## Phase 5：使用者故事 3 — 應徵者完成測驗並提交（優先級：P1）

**目標**：應徵者免登入作答、於隔離沙箱試跑程式碼、單次提交

**獨立測試**：持有有效連結者可進入、作答、試跑、提交，全程不需 HR 或主管介入

**⚠️ 本階段包含憲章原則 VI（不可妥協）的實作與驗證，是全專案風險最高的部分**

### 使用者故事 3 的測試

- [ ] T060 [P] [US3] 撰寫契約測試 `backend/tests/contract/test_candidate_session.py`，斷言隱藏測資的內容不出現在回應中
- [ ] T061 [P] [US3] 撰寫契約測試 `backend/tests/contract/test_candidate_run.py`，涵蓋試跑成功、次數上限 429、沙箱不可用 503
- [ ] T062 [P] [US3] 撰寫契約測試 `backend/tests/contract/test_candidate_submit.py`，涵蓋提交成功與重複提交 409
- [ ] T063 [P] [US3] 撰寫整合測試 `backend/tests/integration/test_us3_expiry.py`，涵蓋 quickstart.md 情境 9（逾期 410 且不回傳題目、狀態轉 EXPIRED）
- [ ] T064 [P] [US3] 撰寫整合測試 `backend/tests/integration/test_us3_submit_once.py`，斷言提交後作答內容不可變更（FR-034）
- [ ] T065 [P] [US3] 撰寫整合測試 `backend/tests/integration/test_us3_sandbox_degraded.py`，斷言沙箱不可用時仍可提交且不改以未隔離方式執行（FR-047、憲章原則 VI）

### 沙箱安全測試（marker: security，需本機 Docker）

> 對應憲章「安全關卡」三類要求與 contracts/sandbox-runner.md 的必測項目

- [ ] T066 [US3] 撰寫網路阻斷測試 `backend/tests/security/test_sandbox_network.py`，斷言對外 HTTP、DNS 解析與宿主 IP 連線皆失敗
- [ ] T067 [US3] 撰寫資源耗盡測試 `backend/tests/security/test_sandbox_resources.py`，斷言無窮迴圈→TIMEOUT、超額配置→MEMORY_LIMIT、fork bomb→PIDS_LIMIT、無限輸出→OUTPUT_LIMIT
- [ ] T068 [US3] 撰寫檔案系統測試 `backend/tests/security/test_sandbox_filesystem.py`，斷言根檔案系統寫入失敗、/work 寫入成功、前次執行殘留檔案不存在（FR-042）
- [ ] T069 [US3] 撰寫五語言基準測試 `backend/tests/security/test_sandbox_languages.py`，各語言各一組正常執行與編譯錯誤案例

### 使用者故事 3 的實作

- [ ] T070 [P] [US3] 建立五個沙箱映像檔 `sandbox/javascript/Dockerfile`、`sandbox/python/Dockerfile`、`sandbox/go/Dockerfile`、`sandbox/java/Dockerfile`、`sandbox/cpp/Dockerfile`，固定語言版本且不含網路工具與套件管理器
- [ ] T071 [US3] 實作 `backend/src/sandbox/docker_runner.py`，套用 contracts/sandbox-runner.md 的全部 12 項容器參數，並以宿主端計時器強制牆鐘逾時、以串流方式讀取輸出
- [ ] T072 [US3] 實作沙箱併發控制於 `backend/src/sandbox/docker_runner.py`，以 asyncio.Semaphore(10) 限制並提供等候狀態（FR-046）
- [ ] T073 [US3] 實作 `backend/src/api/candidate.py` 的 session 載入、試跑與提交端點，一律經 SECURITY DEFINER 函式存取
- [ ] T074 [US3] 實作試跑次數上限與計數遞增於 `backend/src/services/assessment_service.py`，達上限後停止試跑但不阻擋提交（FR-032）
- [ ] T075 [US3] 實作前端 `frontend/js/editor.js`，整合 CodeMirror 6，提供語言選擇、試跑與提交，並依部門類型切換為文字作答介面

**檢查點**：US1～US3 皆可獨立運作；安全套件全數通過

---

## Phase 6：使用者故事 4 — AI 自動產出多維度評測報告（優先級：P1）

**目標**：提交後自動以測資驗證正確性，並產出四維度評測報告

**獨立測試**：給定一份已提交作答，可驗證報告含四維度評分且標示為 AI 建議

### 使用者故事 4 的測試

- [ ] T076 [P] [US4] 撰寫契約測試 `backend/tests/contract/test_ai_report_shape.py`，斷言四維度皆存在、含 advisory_notice，且回應中不存在任何總分或綜合建議欄位（FR-057）
- [ ] T077 [P] [US4] 撰寫整合測試 `backend/tests/integration/test_us4_evaluation_flow.py`，涵蓋 quickstart.md 情境 6，斷言 correctness.score 與 test_pass_ratio 一致（FR-054）
- [ ] T078 [P] [US4] 撰寫整合測試 `backend/tests/integration/test_us4_evaluation_failure.py`，斷言評測失敗時提交仍成功、ai_reports.status=FAILED、主管仍可決策（FR-059）

### 使用者故事 4 的實作

- [ ] T079 [US4] 實作測資執行器於 `backend/src/services/evaluation_service.py`，逐一以沙箱執行測試案例並產出 test_results（不保存 actual_stdout，避免隱藏測資外洩）
- [ ] T080 [US4] 實作 `backend/src/ai/gemini_provider.py` 的 evaluate，並建立提示詞 `backend/src/ai/prompts/evaluate.txt`；剝除模型輸出中的任何綜合建議
- [ ] T081 [US4] 實作提交後的背景評測觸發於 `backend/src/services/evaluation_service.py`，寫入 ai_reports 與 EVALUATION_* 稽核（research.md R-006）
- [ ] T082 [US4] 實作 `backend/src/api/manager.py` 的 reevaluate 端點，產生新的 attempt_no 且保留失敗紀錄

**檢查點**：US1～US4 皆可獨立運作——核心價值主張已可展示

---

## Phase 7：使用者故事 5 — 主管審閱並做出決策（優先級：P2）

**目標**：主管檢視完整作答、執行紀錄與對話歷程，記錄決策與內部評語

**獨立測試**：給定一份已評測的考核，主管可完成審閱與決策，且決策可被查詢

### 使用者故事 5 的測試

- [ ] T083 [P] [US5] 撰寫契約測試 `backend/tests/contract/test_manager_detail.py`，斷言回應含作答、執行紀錄、測資通過情形與完整對話歷程
- [ ] T084 [P] [US5] 撰寫契約測試 `backend/tests/contract/test_manager_decision.py`，涵蓋 POST decision
- [ ] T085 [P] [US5] 撰寫整合測試 `backend/tests/integration/test_us5_decision_revision.py`，斷言二次決策產生 revision_no=2 且原紀錄仍存在（FR-064）
- [ ] T086 [P] [US5] 撰寫整合測試 `backend/tests/integration/test_us5_second_round.py`，斷言 SECOND_ROUND 決策不建立新考核且狀態停留於 DECIDED（FR-065）

### 使用者故事 5 的實作

- [ ] T087 [US5] 實作 `backend/src/repositories/decision_repo.py` 的唯附加寫入與 revision_no 遞增
- [ ] T088 [US5] 實作決策寫入與 assessments.final_decision 的同交易更新於 `backend/src/services/assessment_service.py`（FR-007 的資料來源）
- [ ] T089 [US5] 實作 `backend/src/api/manager.py` 的考核詳情與決策端點，含 DECISION_RECORDED 與 DECISION_REVISED 稽核
- [ ] T090 [US5] 實作前端 `frontend/js/manager.js` 的審閱畫面，呈現作答、執行紀錄、對話歷程、AI 報告與決策表單

**檢查點**：US1～US5 皆可獨立運作

---

## Phase 8：使用者故事 6 — HR 審閱後發送結果通知（優先級：P2）

**目標**：HR 預覽並微調通知內容後發送，內容不得含內部評語與 AI 報告

**獨立測試**：給定一筆已決策的考核，HR 可預覽、編輯、發送並看到寄送狀態更新

### 使用者故事 6 的測試

- [ ] T091 [P] [US6] 撰寫契約測試 `backend/tests/contract/test_hr_notification.py`，涵蓋 preview 與 send 端點
- [ ] T092 [P] [US6] 撰寫整合測試 `backend/tests/integration/test_us6_no_leak.py`，斷言草稿與寄出內容皆不含內部評語與 AI 報告的任何文字（FR-070、SC-011）
- [ ] T093 [P] [US6] 撰寫整合測試 `backend/tests/integration/test_us6_send_failure.py`，斷言寄送失敗回傳 200 且 email_status=FAILED，並可重新發送（FR-072）

### 使用者故事 6 的實作

- [ ] T094 [P] [US6] 建立三種決策結果的制式通知範本於 `backend/src/services/templates/`，SECOND_ROUND 範本不承諾具體時程
- [ ] T095 [P] [US6] 實作 `backend/src/email/smtp_sender.py`，連線參數全部來自環境變數，失敗以回傳值表達而非拋出例外
- [ ] T096 [US6] 實作 `backend/src/services/notification_service.py` 與 `backend/src/api/hr.py` 的預覽與發送端點，含 NOTIFICATION_* 稽核
- [ ] T097 [US6] 實作前端 `frontend/js/hr.js` 的通知預覽視窗與編輯後發送流程

**檢查點**：US1～US6 皆可獨立運作

---

## Phase 9：使用者故事 7 — 應徵者取得 AI 觀念引導（優先級：P3）

**目標**：應徵者作答中可向 AI 助教提問，取得引導但不取得完整解答

**獨立測試**：應徵者可發問並取得回覆，且回覆不含可直接提交的完整解答

### 使用者故事 7 的測試

- [ ] T098 [P] [US7] 撰寫契約測試 `backend/tests/contract/test_candidate_chat.py`，涵蓋 POST chat 與 503 降級
- [ ] T099 [P] [US7] 撰寫整合測試 `backend/tests/integration/test_us7_guardrail.py`，涵蓋 quickstart.md 情境 7，斷言索取完整解答時 guardrail_triggered=true 且回覆仍具引導價值（SC-013）
- [ ] T100 [P] [US7] 撰寫整合測試 `backend/tests/integration/test_us7_ai_unavailable.py`，斷言 AI 助教不可用時作答、試跑與提交皆不受影響（FR-052）

### 使用者故事 7 的實作

- [ ] T101 [US7] 實作 `backend/src/ai/gemini_provider.py` 的 chat_assist，並建立提示詞 `backend/src/ai/prompts/chat_assist.txt`，明確禁止輸出完整解答與隱藏測資
- [ ] T102 [US7] 實作對話附加與端點於 `backend/src/api/candidate.py`，經 append_chat_message 函式寫入並記錄 guardrail_triggered
- [ ] T103 [US7] 實作前端 `frontend/js/chat.js` 的助教對話介面，與作答區並存

**檢查點**：全部七個使用者故事皆可獨立運作

---

## Phase 10：收尾與跨領域事項

**目的**：影響多個使用者故事的完善工作與最終驗收

- [ ] T104 實作逾期惰性判定於 `backend/src/services/assessment_service.py`，於任何讀取路徑檢查效期並轉為 EXPIRED（避免引入排程器，見 data-model.md）
- [ ] T105 實作個資刪除流程於 `backend/src/services/pii_service.py`，依 Email 去識別化所有相關考核並寫入 PII_ERASED 稽核（FR-082）
- [ ] T106 [P] 撰寫稽核完整性測試 `backend/tests/integration/test_audit_completeness.py`，涵蓋 quickstart.md 情境 11，斷言完整操作鏈皆有紀錄且含 actor_role（SC-014）
- [ ] T107 [P] 撰寫日誌過濾測試 `backend/tests/unit/test_log_pii_filter.py`，斷言姓名、Email、電話與作答內容皆不出現於日誌（FR-079、FR-080）
- [ ] T108 執行效能驗證並記錄結果，涵蓋 SC-004（試跑 15 秒）、SC-005（報告 3 分鐘）、SC-010（沙箱執行不影響他人回應時間）
- [ ] T109 [P] 補齊 `README.md` 的部署說明與 `.env.example` 的變數註解，並確認 GEMINI_MODEL 的可用性已實測（research.md R-005）
- [ ] T110 依 `quickstart.md` 逐項執行全部 11 個驗證情境並記錄結果
- [ ] T111 執行憲章合規最終檢查，逐條核對六項原則與三道品質關卡（離線測試、安全關卡、權限關卡）
- [ ] T112 清除暫時性程式碼與 TODO 註解，執行 ruff 檢查並修正全部問題

---

## 相依關係與執行順序

### 階段相依

- **Phase 1 環境建置**：無相依，可立即開始
- **Phase 2 基礎建設**：依賴 Phase 1——**阻斷所有使用者故事**
- **Phase 3～9 使用者故事**：皆依賴 Phase 2 完成
- **Phase 10 收尾**：依賴所有預定交付的使用者故事完成

### 使用者故事相依

| 故事 | 優先級 | 可否獨立開始 | 說明 |
|------|:------:|:-----------:|------|
| US1 HR 建案 | P1 | 是 | 無其他故事相依 |
| US2 主管出題 | P1 | 是 | 測試資料可由 seed 提供，不需 US1 完成 |
| US3 應徵者作答 | P1 | 是 | 同上；但沙箱工作量最大，建議最早投入人力 |
| US4 AI 評測 | P1 | 部分 | 測資執行需 US3 的 DockerSandboxRunner（T071） |
| US5 主管決策 | P2 | 是 | 可用 seed 的已提交考核測試 |
| US6 HR 通知 | P2 | 部分 | 需 US5 的 final_decision 欄位（T088） |
| US7 AI 助教 | P3 | 是 | 純附加功能 |

**僅有的兩條跨故事實作相依**：US4 → T071（沙箱）、US6 → T088（final_decision）。
其餘故事之間互相獨立。

### 每個故事內部

- 測試必須先撰寫且先失敗（憲章原則 II，不可妥協）
- 模型 → 服務 → 端點 → 前端
- 故事完成後才進入下一優先級

---

## 平行執行機會

### Phase 2 的最大平行度

八個遷移檔（T010～T017）彼此獨立，可同時撰寫：

```text
Task: "建立遷移檔 supabase/migrations/0001_departments.sql"
Task: "建立遷移檔 supabase/migrations/0002_internal_users.sql"
Task: "建立遷移檔 supabase/migrations/0003_question_banks.sql"
Task: "建立遷移檔 supabase/migrations/0004_assessments.sql"
Task: "建立遷移檔 supabase/migrations/0005_execution_records.sql"
Task: "建立遷移檔 supabase/migrations/0006_ai_reports.sql"
Task: "建立遷移檔 supabase/migrations/0007_manager_decisions.sql"
Task: "建立遷移檔 supabase/migrations/0008_audit_logs.sql"
```

四份基礎測試（T022～T025）與四個 Pydantic 模型（T028～T031）同理。
三份介面契約（T034～T036）亦可同時進行。

### 使用者故事 1 的平行範例

```text
# 先平行撰寫全部測試，確認失敗
Task: "契約測試 backend/tests/contract/test_hr_create_assessment.py"
Task: "契約測試 backend/tests/contract/test_hr_list_assessments.py"
Task: "整合測試 backend/tests/integration/test_us1_create_flow.py"
Task: "整合測試 backend/tests/integration/test_us1_duplicate_invite.py"

# 測試失敗後，token 產生器可與 repo 平行實作
Task: "token 產生器 backend/src/services/token_service.py"
```

### 團隊分工

Phase 2 完成後，四位開發者可同時進行：

- 開發者 A：US3（沙箱，工作量最大，建議最資深者負責）
- 開發者 B：US1 + US6
- 開發者 C：US2 + US7
- 開發者 D：US5，待 T071 完成後接手 US4

---

## 實作策略

### MVP 優先（僅 US1）

1. 完成 Phase 1 環境建置
2. 完成 Phase 2 基礎建設（**關鍵，阻斷全部故事**）
3. 完成 Phase 3 US1
4. **停下來驗證**：獨立測試 US1
5. 可展示則展示

### 建議的實際交付順序

MVP 之後，下一個里程碑建議是 **US2 + US3 + US4**——三者合起來才構成「應徵者能完成一次考核並得到評測」的完整價值。單獨交付其中任一個，對外沒有可展示的成果。

之後 US5 + US6 構成「決策與通知」的閉環，US7 為體驗加強。

### 風險提示

**US3 的沙箱是全專案最大的不確定性**。T066～T071 這六項任務涉及憲章唯一標示為
不可妥協且無法以例外繞過的原則。建議：

- 在 Phase 2 期間就先做沙箱的技術驗證（spike），確認 Docker 參數在目標環境確實生效
- 若安全套件無法通過，**不得**以放寬參數的方式讓測試變綠——依憲章原則 VI，
  正確的降級是「接受提交但不執行」

---

## 備註

- `[P]` 表示不同檔案且無未完成相依，可平行執行
- `[Story]` 標籤提供任務至使用者故事的追溯性
- **測試為強制**：憲章原則 II 不可妥協。實作前必須確認測試失敗
- 每項任務或每組邏輯相關任務完成後即提交
- 任何檢查點皆可停下來獨立驗證該故事
- 任務唯有其測試通過才可勾選完成——憲章明訂「不得在缺少對應實作的情況下勾選」

---

## 任務統計

| 階段 | 任務數 | 其中測試 |
|------|:------:|:-------:|
| Phase 1 環境建置 | 9 | 0 |
| Phase 2 基礎建設 | 28 | 5 |
| Phase 3 US1（P1．MVP） | 11 | 4 |
| Phase 4 US2（P1） | 11 | 5 |
| Phase 5 US3（P1） | 16 | 10 |
| Phase 6 US4（P1） | 7 | 3 |
| Phase 7 US5（P2） | 8 | 4 |
| Phase 8 US6（P2） | 7 | 3 |
| Phase 9 US7（P3） | 6 | 3 |
| Phase 10 收尾 | 9 | 2 |
| **總計** | **112** | **39** |
