-- 0003_question_banks：部門專屬題庫
-- 來源：data-model.md §3；FR-020～FR-022

CREATE TABLE IF NOT EXISTS question_banks (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    dept_id     VARCHAR(50)  NOT NULL REFERENCES departments (id),
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(100),
    difficulty  VARCHAR(20)  NOT NULL
                CONSTRAINT question_banks_difficulty_check
                CHECK (difficulty IN ('EASY', 'MEDIUM', 'HARD')),
    language    VARCHAR(30)
                CONSTRAINT question_banks_language_check
                CHECK (language IN ('javascript', 'python', 'go', 'java', 'cpp')),
    description TEXT         NOT NULL,
    constraints TEXT,
    test_cases  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_by  UUID         REFERENCES internal_users (id),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- test_cases 必須為陣列；每組測資的必填欄位於應用層以 Pydantic 驗證（backend/src/models/question.py）
    CONSTRAINT question_banks_test_cases_is_array CHECK (jsonb_typeof(test_cases) = 'array')
);

CREATE INDEX IF NOT EXISTS question_banks_dept_idx ON question_banks (dept_id);

COMMENT ON COLUMN question_banks.test_cases IS
    '每組含 name、stdin、expected_stdout、is_hidden、timeout_seconds。工程類部門的題目長度必須 >= 1（FR-022、FR-026），於指派時強制檢查。';
