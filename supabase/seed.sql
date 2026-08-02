-- seed.sql：開發與測試用合成資料
--
-- 憲章原則 IV：真實應徵者資料不得出現於測試、測試資料、範例檔案或任何
-- 進版控的產出物中。以下姓名、Email 與電話皆為虛構，Email 網域使用
-- RFC 2606 保留的 example.com，確保不會誤寄至真實信箱。

-- ── 部門 ───────────────────────────────────────────────────────────────
INSERT INTO departments (id, name, type) VALUES
    ('ENG',    '工程技術部', 'ENGINEERING'),
    ('DESIGN', '產品設計部', 'ENGINEERING'),
    ('SALES',  '業務發展部', 'NON_ENGINEERING')
ON CONFLICT (id) DO NOTHING;

-- ── 內部使用者 ─────────────────────────────────────────────────────────
-- auth_user_id 對應 Supabase Auth；此處使用固定 UUID 以便測試組出 JWT claim。
INSERT INTO internal_users (id, auth_user_id, name, email, role, dept_id, is_active) VALUES
    ('11111111-1111-4111-8111-111111111111',
     'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa',
     '合成 HR',      'hr@example.com',            'HR',      NULL,     true),
    ('22222222-2222-4222-8222-222222222222',
     'aaaaaaaa-2222-4222-8222-aaaaaaaaaaaa',
     '合成工程主管',  'manager.eng@example.com',   'MANAGER', 'ENG',    true),
    ('33333333-3333-4333-8333-333333333333',
     'aaaaaaaa-3333-4333-8333-aaaaaaaaaaaa',
     '合成設計主管',  'manager.design@example.com','MANAGER', 'DESIGN', true),
    ('44444444-4444-4444-8444-444444444444',
     'aaaaaaaa-4444-4444-8444-aaaaaaaaaaaa',
     '合成業務主管',  'manager.sales@example.com', 'MANAGER', 'SALES',  true)
ON CONFLICT (id) DO NOTHING;

-- ── 題庫 ───────────────────────────────────────────────────────────────
INSERT INTO question_banks
    (id, dept_id, title, category, difficulty, language, description, constraints, test_cases, created_by)
VALUES
    ('aa000000-0000-4000-8000-000000000001', 'ENG',
     '兩數相加', '基礎', 'EASY', 'python',
     '自標準輸入讀取兩個以空白分隔的整數，輸出其和。',
     '整數範圍為 -10^9 至 10^9。',
     '[
        {"name": "基本案例", "stdin": "3 5\n",   "expected_stdout": "8\n",   "is_hidden": false, "timeout_seconds": 10},
        {"name": "負數",     "stdin": "-2 7\n",  "expected_stdout": "5\n",   "is_hidden": false, "timeout_seconds": 10},
        {"name": "隱藏邊界", "stdin": "0 0\n",   "expected_stdout": "0\n",   "is_hidden": true,  "timeout_seconds": 10}
      ]'::jsonb,
     '22222222-2222-4222-8222-222222222222'),

    ('aa000000-0000-4000-8000-000000000002', 'ENG',
     '實作 LRU 快取', '資料結構', 'HARD', 'go',
     '實作固定容量的 LRU 快取。輸入為操作序列，每行一個操作，輸出每次 get 的結果。',
     '所有操作的時間複雜度須為 O(1)。',
     '[
        {"name": "基本流程", "stdin": "2\nput 1 1\nput 2 2\nget 1\nput 3 3\nget 2\n", "expected_stdout": "1\n-1\n", "is_hidden": false, "timeout_seconds": 10},
        {"name": "淘汰順序", "stdin": "1\nput 1 1\nput 2 2\nget 1\n",                 "expected_stdout": "-1\n",    "is_hidden": true,  "timeout_seconds": 10}
      ]'::jsonb,
     '22222222-2222-4222-8222-222222222222'),

    ('aa000000-0000-4000-8000-000000000003', 'DESIGN',
     '元件狀態管理', '前端', 'MEDIUM', 'javascript',
     '實作一個簡易的狀態容器，支援 subscribe 與 dispatch。輸入為操作序列，輸出每次狀態變更後的值。',
     '不得使用任何外部函式庫。',
     '[
        {"name": "基本案例", "stdin": "inc\ninc\ndec\n", "expected_stdout": "1\n2\n1\n", "is_hidden": false, "timeout_seconds": 10}
      ]'::jsonb,
     '33333333-3333-4333-8333-333333333333'),

    -- 非工程類部門的題目不需測資（FR-022 僅規範工程類）
    ('aa000000-0000-4000-8000-000000000004', 'SALES',
     '客戶異議處理', '情境題', 'MEDIUM', NULL,
     '客戶以「價格過高」為由拒絕續約。請說明你的處理步驟與談判策略。',
     '請以 300 字以內作答。',
     '[]'::jsonb,
     '44444444-4444-4444-8444-444444444444')
ON CONFLICT (id) DO NOTHING;

-- ── 考核（合成應徵者）─────────────────────────────────────────────────
-- token 於正式流程中由密碼學安全亂數產生（FR-016）；此處為固定的合成值，
-- 僅供本機開發，不得出現在任何正式環境。
INSERT INTO assessments
    (id, name, email, phone, job_title, dept_id, assigned_manager_id,
     status, token, token_expires_at)
VALUES
    ('bb000000-0000-4000-8000-000000000001',
     '測試應徵者甲', 'candidate.a@example.com', '0900-000-001',
     '後端工程師', 'ENG', '22222222-2222-4222-8222-222222222222',
     'PENDING_ASSIGN', 'seed-token-pending-assign-0000000000000001', NOW() + INTERVAL '7 days'),

    ('bb000000-0000-4000-8000-000000000002',
     '測試應徵者乙', 'candidate.b@example.com', '0900-000-002',
     '前端工程師', 'DESIGN', '33333333-3333-4333-8333-333333333333',
     'PENDING_ASSIGN', 'seed-token-design-dept-000000000000000002', NOW() + INTERVAL '7 days'),

    ('bb000000-0000-4000-8000-000000000003',
     '測試應徵者丙', 'candidate.c@example.com', '0900-000-003',
     '業務代表', 'SALES', '44444444-4444-4444-8444-444444444444',
     'PENDING_ASSIGN', 'seed-token-expired-00000000000000000000003', NOW() - INTERVAL '1 day')
ON CONFLICT (id) DO NOTHING;
