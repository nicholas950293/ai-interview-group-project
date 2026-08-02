-- 0011_append_only：唯附加強制
-- 來源：FR-064、FR-078；憲章原則 V（稽核歷程必須以獨立的唯附加資料結構實作）
--
-- 撤銷 UPDATE 與 DELETE 權限，使「不得修改或刪除」由資料庫拒絕，
-- 而非仰賴應用程式自律。RLS 政策（0009）本就未涵蓋這些動作，
-- 此處以 GRANT 層再撤一次，形成雙重限制（data-model.md §5「唯附加」）。

REVOKE UPDATE, DELETE ON execution_records FROM anon, authenticated, PUBLIC;
REVOKE UPDATE, DELETE ON ai_reports        FROM anon, authenticated, PUBLIC;
REVOKE UPDATE, DELETE ON manager_decisions FROM anon, authenticated, PUBLIC;
REVOKE UPDATE, DELETE ON audit_logs        FROM anon, authenticated, PUBLIC;

-- 觸發器作為第三層防線：即使日後有人誤授權，或以資料表擁有者身分連線
-- （擁有者不受 GRANT 限制），修改與刪除仍會被拒絕。
-- ai_reports 的唯一例外是 status 由 PENDING 轉為終態——這一次轉換由
-- record_evaluation_result() 執行，其餘欄位在該次更新後即不可變。
CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% 為唯附加資料表，不接受 % 操作（FR-078）',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE OR REPLACE FUNCTION reject_ai_report_mutation() RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'ai_reports 為唯附加資料表，不接受 DELETE 操作（FR-078）'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF OLD.status <> 'PENDING' THEN
        RAISE EXCEPTION 'ai_reports 僅允許 status 由 PENDING 轉為終態，不得再次修改（FR-059）'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF NEW.id            IS DISTINCT FROM OLD.id
       OR NEW.assessment_id IS DISTINCT FROM OLD.assessment_id
       OR NEW.attempt_no    IS DISTINCT FROM OLD.attempt_no
       OR NEW.created_at    IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'ai_reports 的識別欄位不可變更（FR-078）'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS execution_records_append_only ON execution_records;
CREATE TRIGGER execution_records_append_only
    BEFORE UPDATE OR DELETE ON execution_records
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

DROP TRIGGER IF EXISTS manager_decisions_append_only ON manager_decisions;
CREATE TRIGGER manager_decisions_append_only
    BEFORE UPDATE OR DELETE ON manager_decisions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;
CREATE TRIGGER audit_logs_append_only
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

DROP TRIGGER IF EXISTS ai_reports_append_only ON ai_reports;
CREATE TRIGGER ai_reports_append_only
    BEFORE UPDATE OR DELETE ON ai_reports
    FOR EACH ROW EXECUTE FUNCTION reject_ai_report_mutation();
