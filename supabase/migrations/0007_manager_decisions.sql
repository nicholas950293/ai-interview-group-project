-- 0007_manager_decisions：主管決策與內部評語（唯附加）
-- 來源：data-model.md §7；FR-061～FR-064、FR-066

CREATE TABLE IF NOT EXISTS manager_decisions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id    UUID        NOT NULL REFERENCES assessments (id),
    revision_no      INTEGER     NOT NULL
                     CONSTRAINT manager_decisions_revision_no_positive CHECK (revision_no >= 1),
    decided_by       UUID        NOT NULL REFERENCES internal_users (id),
    result           VARCHAR(20) NOT NULL
                     CONSTRAINT manager_decisions_result_check
                     CHECK (result IN ('PASS', 'SECOND_ROUND', 'FAIL')),
    internal_comment TEXT,
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 修訂以新增列呈現；同一考核的修訂序號不得重複（FR-064）
    CONSTRAINT manager_decisions_assessment_revision_unique UNIQUE (assessment_id, revision_no)
);

CREATE INDEX IF NOT EXISTS manager_decisions_assessment_idx
    ON manager_decisions (assessment_id, revision_no DESC);

COMMENT ON TABLE manager_decisions IS
    '唯附加。修訂以新增列呈現，原紀錄不得覆寫或刪除（FR-064、FR-078）。HR 角色在本表沒有任何 RLS 政策——這是 FR-008 的實施點。';
COMMENT ON COLUMN manager_decisions.internal_comment IS
    'HR 不可讀（FR-007、FR-066）。僅同部門主管可見。';
