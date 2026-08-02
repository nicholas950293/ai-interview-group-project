-- 0009_rls_policies：RLS 政策矩陣
-- 來源：data-model.md「RLS 政策矩陣」；research.md R-002、R-003
-- 憲章原則 IV：角色隔離必須在資料存取層強制執行，不得僅依賴介面隱藏。
--
-- 權限判定的唯一輸入是 PostgREST 設定的 request.jwt.claims GUC，其內容來自
-- 簽章過的 JWT，後端無從偽造。Supabase 的 auth.jwt() 讀取的是同一個 GUC，
-- 因此下列 helper 在 Supabase 與本機 PostgreSQL 上行為一致（RLS 測試需要後者）。

-- ── 角色 ───────────────────────────────────────────────────────────────
-- Supabase 已內建；本機 PostgreSQL 需自行建立，使 RLS 測試可執行。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- ── JWT claim helper ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION jwt_claims() RETURNS jsonb
    LANGUAGE sql STABLE
AS $$
    SELECT COALESCE(NULLIF(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
$$;

CREATE OR REPLACE FUNCTION app_role() RETURNS text
    LANGUAGE sql STABLE
AS $$
    SELECT jwt_claims() ->> 'app_role';
$$;

CREATE OR REPLACE FUNCTION app_dept_id() RETURNS text
    LANGUAGE sql STABLE
AS $$
    SELECT jwt_claims() ->> 'dept_id';
$$;

CREATE OR REPLACE FUNCTION app_auth_user_id() RETURNS uuid
    LANGUAGE sql STABLE
AS $$
    SELECT NULLIF(jwt_claims() ->> 'sub', '')::uuid;
$$;

GRANT EXECUTE ON FUNCTION jwt_claims(), app_role(), app_dept_id(), app_auth_user_id()
    TO anon, authenticated;

-- ── 啟用 RLS ───────────────────────────────────────────────────────────
ALTER TABLE departments       ENABLE ROW LEVEL SECURITY;
ALTER TABLE internal_users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_banks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments       ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_reports        ENABLE ROW LEVEL SECURITY;
ALTER TABLE manager_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs        ENABLE ROW LEVEL SECURITY;

-- 底層資料表一律不對 anon 開放。應徵者只能經 SECURITY DEFINER 函式存取
-- （0010_security_definer_functions.sql，research.md R-002）。
REVOKE ALL ON departments, internal_users, question_banks, assessments,
              execution_records, ai_reports, manager_decisions, audit_logs
    FROM anon;

-- ── departments：HR 與主管皆可讀 ────────────────────────────────────────
DROP POLICY IF EXISTS departments_select ON departments;
CREATE POLICY departments_select ON departments
    FOR SELECT TO authenticated
    USING (app_role() IN ('HR', 'MANAGER'));

GRANT SELECT ON departments TO authenticated;

-- ── internal_users：HR 讀全部；主管僅讀自己 ────────────────────────────
DROP POLICY IF EXISTS internal_users_hr_select ON internal_users;
CREATE POLICY internal_users_hr_select ON internal_users
    FOR SELECT TO authenticated
    USING (app_role() = 'HR');

DROP POLICY IF EXISTS internal_users_self_select ON internal_users;
CREATE POLICY internal_users_self_select ON internal_users
    FOR SELECT TO authenticated
    USING (app_role() = 'MANAGER' AND auth_user_id = app_auth_user_id());

GRANT SELECT ON internal_users TO authenticated;

-- ── question_banks：僅同部門主管可讀寫；HR 無政策 ──────────────────────
DROP POLICY IF EXISTS question_banks_manager_all ON question_banks;
CREATE POLICY question_banks_manager_all ON question_banks
    FOR ALL TO authenticated
    USING      (app_role() = 'MANAGER' AND dept_id = app_dept_id())
    WITH CHECK (app_role() = 'MANAGER' AND dept_id = app_dept_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON question_banks TO authenticated;

-- ── assessments：HR 全部門；主管限所屬部門 ─────────────────────────────
DROP POLICY IF EXISTS assessments_hr_all ON assessments;
CREATE POLICY assessments_hr_all ON assessments
    FOR ALL TO authenticated
    USING      (app_role() = 'HR')
    WITH CHECK (app_role() = 'HR');

DROP POLICY IF EXISTS assessments_manager_all ON assessments;
CREATE POLICY assessments_manager_all ON assessments
    FOR ALL TO authenticated
    USING      (app_role() = 'MANAGER' AND dept_id = app_dept_id())
    WITH CHECK (app_role() = 'MANAGER' AND dept_id = app_dept_id());

GRANT SELECT, INSERT, UPDATE ON assessments TO authenticated;

-- HR 對 assessments 的讀取不得含 candidate_answer 與 ai_chat_history。
-- RLS 只能做列級過濾，欄位級隔離以限定欄位的 view 表達（data-model.md 註 1）。
-- security_invoker：view 以呼叫者身分套用底層 RLS，不繞過政策。
CREATE OR REPLACE VIEW hr_assessments
    WITH (security_invoker = true)
AS
SELECT id, name, email, phone, job_title, dept_id, assigned_manager_id,
       status, token, token_expires_at, final_decision,
       email_status, email_error, submitted_at, created_at
FROM assessments;

GRANT SELECT ON hr_assessments TO authenticated;

COMMENT ON VIEW hr_assessments IS
    'HR 可見欄位。刻意不含 candidate_answer 與 ai_chat_history（data-model.md RLS 矩陣註 1）。';

-- ── execution_records：僅同部門主管可讀 ────────────────────────────────
DROP POLICY IF EXISTS execution_records_manager_select ON execution_records;
CREATE POLICY execution_records_manager_select ON execution_records
    FOR SELECT TO authenticated
    USING (
        app_role() = 'MANAGER'
        AND EXISTS (
            SELECT 1 FROM assessments a
            WHERE a.id = execution_records.assessment_id
              AND a.dept_id = app_dept_id()
        )
    );

GRANT SELECT ON execution_records TO authenticated;

-- ── ai_reports：僅同部門主管可讀。HR 無任何政策 ────────────────────────
-- FR-007／FR-008 的實施點之一：HR 的查詢回傳空集合，而非受限內容。
DROP POLICY IF EXISTS ai_reports_manager_select ON ai_reports;
CREATE POLICY ai_reports_manager_select ON ai_reports
    FOR SELECT TO authenticated
    USING (
        app_role() = 'MANAGER'
        AND EXISTS (
            SELECT 1 FROM assessments a
            WHERE a.id = ai_reports.assessment_id
              AND a.dept_id = app_dept_id()
        )
    );

GRANT SELECT ON ai_reports TO authenticated;

-- ── manager_decisions：僅同部門主管可讀與新增。HR 無任何政策 ───────────
DROP POLICY IF EXISTS manager_decisions_manager_select ON manager_decisions;
CREATE POLICY manager_decisions_manager_select ON manager_decisions
    FOR SELECT TO authenticated
    USING (
        app_role() = 'MANAGER'
        AND EXISTS (
            SELECT 1 FROM assessments a
            WHERE a.id = manager_decisions.assessment_id
              AND a.dept_id = app_dept_id()
        )
    );

DROP POLICY IF EXISTS manager_decisions_manager_insert ON manager_decisions;
CREATE POLICY manager_decisions_manager_insert ON manager_decisions
    FOR INSERT TO authenticated
    WITH CHECK (
        app_role() = 'MANAGER'
        AND EXISTS (
            SELECT 1 FROM assessments a
            WHERE a.id = manager_decisions.assessment_id
              AND a.dept_id = app_dept_id()
        )
    );

GRANT SELECT, INSERT ON manager_decisions TO authenticated;

-- ── audit_logs：HR 讀全部；主管讀同部門。兩者皆可新增 ──────────────────
DROP POLICY IF EXISTS audit_logs_hr_select ON audit_logs;
CREATE POLICY audit_logs_hr_select ON audit_logs
    FOR SELECT TO authenticated
    USING (app_role() = 'HR');

DROP POLICY IF EXISTS audit_logs_manager_select ON audit_logs;
CREATE POLICY audit_logs_manager_select ON audit_logs
    FOR SELECT TO authenticated
    USING (
        app_role() = 'MANAGER'
        AND EXISTS (
            SELECT 1 FROM assessments a
            WHERE a.id = audit_logs.assessment_id
              AND a.dept_id = app_dept_id()
        )
    );

DROP POLICY IF EXISTS audit_logs_insert ON audit_logs;
CREATE POLICY audit_logs_insert ON audit_logs
    FOR INSERT TO authenticated
    WITH CHECK (app_role() IN ('HR', 'MANAGER'));

GRANT SELECT, INSERT ON audit_logs TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE audit_logs_id_seq TO authenticated;
