-- 0008_audit_logs：系統稽核歷程（唯附加）
-- 來源：data-model.md §8；FR-076～FR-080、FR-082

CREATE TABLE IF NOT EXISTS audit_logs (
    id            BIGSERIAL   PRIMARY KEY,

    -- 刻意不設 FK 至 assessments：FR-082 要求個資刪除後稽核紀錄仍以去識別化的
    -- 考核識別碼保留。若設外鍵，刪除考核列會連帶破壞稽核歷程（data-model.md §8）。
    assessment_id UUID        NOT NULL,

    action        VARCHAR(50) NOT NULL
                  CONSTRAINT audit_logs_action_check
                  CHECK (action IN (
                      'ASSESSMENT_CREATED',
                      'MANAGER_REASSIGNED',
                      'TOKEN_REGENERATED',
                      'QUESTION_ASSIGNED',
                      'TRIAL_RUN',
                      'ANSWER_SUBMITTED',
                      'EVALUATION_STARTED',
                      'EVALUATION_COMPLETED',
                      'EVALUATION_FAILED',
                      'DECISION_RECORDED',
                      'DECISION_REVISED',
                      'NOTIFICATION_SENT',
                      'NOTIFICATION_FAILED',
                      'STATUS_EXPIRED',
                      'PII_ERASED'
                  )),
    from_status   VARCHAR(40),
    to_status     VARCHAR(40),
    actor_id      UUID,
    actor_role    VARCHAR(20) NOT NULL
                  CONSTRAINT audit_logs_actor_role_check
                  CHECK (actor_role IN ('HR', 'MANAGER', 'CANDIDATE', 'SYSTEM')),
    detail        JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_logs_assessment_idx ON audit_logs (assessment_id, created_at);

COMMENT ON TABLE audit_logs IS
    '唯附加，對所有角色皆然（FR-078）。';
COMMENT ON COLUMN audit_logs.actor_id IS
    '內部使用者識別碼；應徵者操作為 NULL（應徵者無帳號）。';
COMMENT ON COLUMN audit_logs.detail IS
    '補充說明。不得含應徵者姓名、Email、電話或作答內容（FR-079、FR-080），由 backend/src/audit/logger.py 過濾。';
