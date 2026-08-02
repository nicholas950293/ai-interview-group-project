-- 0005_execution_records：沙箱執行紀錄（唯附加）
-- 來源：data-model.md §5；FR-040、FR-044～FR-048

CREATE TABLE IF NOT EXISTS execution_records (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id      UUID        NOT NULL REFERENCES assessments (id),
    trigger            VARCHAR(20) NOT NULL
                       CONSTRAINT execution_records_trigger_check
                       CHECK (trigger IN ('TRIAL_RUN', 'EVALUATION')),
    language           VARCHAR(30) NOT NULL,
    stdout             TEXT,
    stderr             TEXT,
    exit_code          INTEGER,
    duration_ms        INTEGER,
    peak_memory_kb     INTEGER,
    termination_reason VARCHAR(30) NOT NULL
                       CONSTRAINT execution_records_termination_reason_check
                       CHECK (termination_reason IN (
                           'COMPLETED',
                           'TIMEOUT',
                           'MEMORY_LIMIT',
                           'PIDS_LIMIT',
                           'OUTPUT_LIMIT',
                           'COMPILE_ERROR',
                           'SANDBOX_UNAVAILABLE'
                       )),
    test_results       JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS execution_records_assessment_idx
    ON execution_records (assessment_id, created_at);

COMMENT ON TABLE execution_records IS
    '唯附加。UPDATE 與 DELETE 權限於 0011_append_only.sql 撤銷（FR-078）。';
COMMENT ON COLUMN execution_records.test_results IS
    '僅 EVALUATION 觸發時填入。刻意不保存 cases[].actual_stdout，避免隱藏測資的預期輸出經由紀錄外洩。';
COMMENT ON COLUMN execution_records.stdout IS '上限 1 MB，超過截斷（FR-044）。';
