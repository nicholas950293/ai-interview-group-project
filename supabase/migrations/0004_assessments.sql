-- 0004_assessments：考核主表（合併應徵者資訊與單次考核歷程）
-- 來源：data-model.md §4；FR-009、FR-015～FR-019、FR-032～FR-034、FR-071～FR-073

CREATE TABLE IF NOT EXISTS assessments (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(100) NOT NULL,
    email               VARCHAR(150) NOT NULL,
    phone               VARCHAR(50),
    job_title           VARCHAR(100) NOT NULL,
    dept_id             VARCHAR(50)  NOT NULL REFERENCES departments (id),
    assigned_manager_id UUID         REFERENCES internal_users (id),

    status              VARCHAR(40)  NOT NULL DEFAULT 'PENDING_ASSIGN'
                        CONSTRAINT assessments_status_check
                        CHECK (status IN (
                            'PENDING_ASSIGN',
                            'PENDING_CANDIDATE',
                            'COMPLETED_AWAITING_REVIEW',
                            'DECIDED',
                            'EXPIRED'
                        )),

    token               VARCHAR(100) NOT NULL UNIQUE,
    token_expires_at    TIMESTAMPTZ  NOT NULL,

    question_snapshot   JSONB,
    code_language       VARCHAR(30)
                        CONSTRAINT assessments_language_check
                        CHECK (code_language IS NULL OR code_language IN
                               ('javascript', 'python', 'go', 'java', 'cpp')),
    candidate_answer    TEXT,
    ai_chat_history     JSONB        NOT NULL DEFAULT '[]'::jsonb,
    trial_run_count     INTEGER      NOT NULL DEFAULT 0
                        CONSTRAINT assessments_trial_run_count_non_negative
                        CHECK (trial_run_count >= 0),

    final_decision      VARCHAR(20)
                        CONSTRAINT assessments_final_decision_check
                        CHECK (final_decision IS NULL OR final_decision IN
                               ('PASS', 'SECOND_ROUND', 'FAIL')),

    email_status        VARCHAR(30)  NOT NULL DEFAULT 'NOT_SENT'
                        CONSTRAINT assessments_email_status_check
                        CHECK (email_status IN ('NOT_SENT', 'SENT', 'FAILED')),
    email_error         TEXT,

    submitted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS assessments_dept_idx   ON assessments (dept_id);
CREATE INDEX IF NOT EXISTS assessments_email_idx  ON assessments (email);
CREATE INDEX IF NOT EXISTS assessments_status_idx ON assessments (status);

COMMENT ON COLUMN assessments.final_decision IS
    'manager_decisions 最新一筆 result 的去正規化副本，僅存列舉值、不含評語。這是 HR 能取得決策結果卻無法取得評語的機制（FR-007、FR-008）。寫入時與 manager_decisions 於同一交易完成。';
COMMENT ON COLUMN assessments.token IS
    '以密碼學安全亂數產生，長度 >= 32 位元組的 URL-safe 編碼（FR-016）。';
COMMENT ON COLUMN assessments.candidate_answer IS
    '作答內容。禁止寫入應用程式日誌（FR-080）。submitted_at 非 NULL 後不得變更（FR-034）。';
