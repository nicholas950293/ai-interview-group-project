-- 0006_ai_reports：AI 評測報告（唯附加）
-- 來源：data-model.md §6；FR-055、FR-057、FR-059

CREATE TABLE IF NOT EXISTS ai_reports (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id   UUID          NOT NULL REFERENCES assessments (id),
    attempt_no      INTEGER       NOT NULL
                    CONSTRAINT ai_reports_attempt_no_positive CHECK (attempt_no >= 1),
    status          VARCHAR(20)   NOT NULL
                    CONSTRAINT ai_reports_status_check
                    CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
    dimensions      JSONB,
    test_pass_ratio NUMERIC(4,3)
                    CONSTRAINT ai_reports_pass_ratio_range
                    CHECK (test_pass_ratio IS NULL OR (test_pass_ratio >= 0 AND test_pass_ratio <= 1)),
    model_id        VARCHAR(100),
    error_message   TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT ai_reports_assessment_attempt_unique UNIQUE (assessment_id, attempt_no)
);

CREATE INDEX IF NOT EXISTS ai_reports_assessment_idx ON ai_reports (assessment_id, attempt_no DESC);

-- 刻意不存在的欄位：加權總分、綜合建議、錄取傾向。
-- 憲章原則 V 與 FR-057 禁止系統自動產生綜合判斷；缺少欄位使違規在結構層即無法表達。
COMMENT ON TABLE ai_reports IS
    '唯附加。僅 status 由 PENDING 轉為終態時允許更新（0011_append_only.sql 的例外），重試一律新增列（FR-059）。刻意不含加權總分與綜合建議欄位（FR-057）。';
COMMENT ON COLUMN ai_reports.dimensions IS
    '四維度：correctness、maintainability、performance、security。每個含 score（0-100 整數）與 comment（繁體中文）。';
COMMENT ON COLUMN ai_reports.model_id IS
    '實際使用的模型 ID，確保評測結果可追溯（research.md R-005）。';
