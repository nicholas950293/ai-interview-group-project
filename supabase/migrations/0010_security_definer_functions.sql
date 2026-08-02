-- 0010_security_definer_functions：應徵者存取路徑
-- 來源：data-model.md「需要的 SECURITY DEFINER 函式」；research.md R-002
--
-- 應徵者沒有 JWT，因此「憑 token 存取」這件事必須同樣落在資料庫層，
-- 而非退化成應用程式層的 if 判斷。底層資料表不對 anon 開放（0009），
-- anon 唯一的入口是本檔案中授權的函式。
--
-- 每個函式皆於內部重新驗證 token 與效期，不得信任呼叫端已驗證。

SET search_path = public;

-- ── 內部 helper（不授權給 anon）─────────────────────────────────────────

-- 逾期惰性判定：不使用排程作業。任何讀取路徑若發現效期已過且狀態為
-- PENDING_ASSIGN 或 PENDING_CANDIDATE，即轉為 EXPIRED 並寫入稽核
-- （data-model.md「逾期判定」，避免引入排程器）。
CREATE OR REPLACE FUNCTION expire_if_due(p_assessment_id uuid)
    RETURNS assessments
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_row  assessments;
    v_from text;
BEGIN
    SELECT * INTO v_row FROM assessments WHERE id = p_assessment_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    IF v_row.token_expires_at < NOW()
       AND v_row.status IN ('PENDING_ASSIGN', 'PENDING_CANDIDATE') THEN
        v_from := v_row.status;

        UPDATE assessments SET status = 'EXPIRED' WHERE id = v_row.id
        RETURNING * INTO v_row;

        INSERT INTO audit_logs (assessment_id, action, from_status, to_status, actor_role, detail)
        VALUES (v_row.id, 'STATUS_EXPIRED', v_from, 'EXPIRED', 'SYSTEM',
                jsonb_build_object('reason', 'TOKEN_EXPIRED'));
    END IF;

    RETURN v_row;
END;
$$;

REVOKE ALL ON FUNCTION expire_if_due(uuid) FROM PUBLIC, anon, authenticated;

-- ── 1. get_assessment_by_token（FR-018、FR-029）─────────────────────────
-- 回傳應徵者可見欄位。隱藏測資的 stdin 與 expected_stdout 必須被移除。
CREATE OR REPLACE FUNCTION get_assessment_by_token(
    p_token           text,
    p_max_trial_runs  integer DEFAULT 20
)
    RETURNS jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_id        uuid;
    v_row       assessments;
    v_dept_type text;
    v_question  jsonb;
BEGIN
    SELECT id INTO v_id FROM assessments WHERE token = p_token;
    IF NOT FOUND THEN
        RETURN NULL;                                     -- API 層轉為 404
    END IF;

    v_row := expire_if_due(v_id);

    SELECT type INTO v_dept_type FROM departments WHERE id = v_row.dept_id;

    IF v_row.status = 'EXPIRED' THEN
        -- 逾期者必須拒絕提供題目內容（FR-018）
        RETURN jsonb_build_object(
            'status',           'EXPIRED',
            'job_title',        v_row.job_title,
            'dept_type',        v_dept_type,
            'token_expires_at', v_row.token_expires_at,
            'question',         NULL
        );
    END IF;

    IF v_row.question_snapshot IS NOT NULL THEN
        v_question := jsonb_build_object(
            'title',       v_row.question_snapshot ->> 'title',
            'description', v_row.question_snapshot ->> 'description',
            'constraints', v_row.question_snapshot ->> 'constraints',
            'language',    v_row.question_snapshot ->> 'language',
            'sample_cases', COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                           'name',            c ->> 'name',
                           'stdin',           c ->> 'stdin',
                           'expected_stdout', c ->> 'expected_stdout'))
                FROM jsonb_array_elements(
                         COALESCE(v_row.question_snapshot -> 'test_cases', '[]'::jsonb)) AS c
                WHERE COALESCE((c ->> 'is_hidden')::boolean, false) = false
            ), '[]'::jsonb)
        );
    END IF;

    RETURN jsonb_build_object(
        'assessment_id',        v_row.id,
        'job_title',            v_row.job_title,
        'dept_type',            v_dept_type,
        'status',               v_row.status,
        'token_expires_at',     v_row.token_expires_at,
        'question',             v_question,
        'code_language',        v_row.code_language,
        'trial_runs_remaining', GREATEST(p_max_trial_runs - v_row.trial_run_count, 0),
        'submitted_at',         v_row.submitted_at,
        'chat_history',         v_row.ai_chat_history
    );
END;
$$;

-- ── 2. append_chat_message（FR-051）─────────────────────────────────────
CREATE OR REPLACE FUNCTION append_chat_message(
    p_token     text,
    p_role      text,
    p_content   text,
    p_guardrail boolean DEFAULT NULL
)
    RETURNS jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_id      uuid;
    v_row     assessments;
    v_message jsonb;
BEGIN
    IF p_role NOT IN ('candidate', 'assistant') THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'INVALID_ROLE');
    END IF;

    SELECT id INTO v_id FROM assessments WHERE token = p_token;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NOT_FOUND');
    END IF;

    v_row := expire_if_due(v_id);
    IF v_row.status = 'EXPIRED' THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'EXPIRED');
    END IF;

    v_message := jsonb_build_object(
        'role', p_role, 'content', p_content,
        'created_at', to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'));
    IF p_guardrail IS NOT NULL THEN
        v_message := v_message || jsonb_build_object('guardrail_triggered', p_guardrail);
    END IF;

    UPDATE assessments
       SET ai_chat_history = COALESCE(ai_chat_history, '[]'::jsonb) || jsonb_build_array(v_message)
     WHERE id = v_row.id;

    RETURN jsonb_build_object('ok', true, 'message', v_message);
END;
$$;

-- ── 3. record_trial_run（FR-031、FR-032、FR-048）────────────────────────
CREATE OR REPLACE FUNCTION record_trial_run(
    p_token          text,
    p_execution      jsonb,
    p_max_trial_runs integer DEFAULT 20
)
    RETURNS jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_id  uuid;
    v_row assessments;
BEGIN
    SELECT id INTO v_id FROM assessments WHERE token = p_token;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NOT_FOUND');
    END IF;

    v_row := expire_if_due(v_id);
    IF v_row.status = 'EXPIRED' THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'EXPIRED');
    END IF;
    IF v_row.submitted_at IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'ALREADY_SUBMITTED');
    END IF;
    -- 達上限後停止提供試跑，但不阻擋提交（FR-032）
    IF v_row.trial_run_count >= p_max_trial_runs THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'LIMIT_REACHED',
                                  'trial_runs_remaining', 0);
    END IF;

    INSERT INTO execution_records (
        assessment_id, trigger, language, stdout, stderr,
        exit_code, duration_ms, peak_memory_kb, termination_reason)
    VALUES (
        v_row.id, 'TRIAL_RUN',
        COALESCE(p_execution ->> 'language', v_row.code_language, 'unknown'),
        p_execution ->> 'stdout',
        p_execution ->> 'stderr',
        (p_execution ->> 'exit_code')::integer,
        (p_execution ->> 'duration_ms')::integer,
        (p_execution ->> 'peak_memory_kb')::integer,
        COALESCE(p_execution ->> 'termination_reason', 'COMPLETED'));

    UPDATE assessments SET trial_run_count = trial_run_count + 1 WHERE id = v_row.id
    RETURNING * INTO v_row;

    INSERT INTO audit_logs (assessment_id, action, actor_role, detail)
    VALUES (v_row.id, 'TRIAL_RUN', 'CANDIDATE',
            jsonb_build_object(
                'termination_reason', COALESCE(p_execution ->> 'termination_reason', 'COMPLETED'),
                'duration_ms',        (p_execution ->> 'duration_ms')::integer,
                'attempt',            v_row.trial_run_count));

    RETURN jsonb_build_object(
        'ok', true,
        'trial_runs_remaining', GREATEST(p_max_trial_runs - v_row.trial_run_count, 0));
END;
$$;

-- ── 4. submit_answer（FR-033、FR-034）───────────────────────────────────
CREATE OR REPLACE FUNCTION submit_answer(
    p_token    text,
    p_answer   text,
    p_language text DEFAULT NULL
)
    RETURNS jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_id   uuid;
    v_row  assessments;
    v_from text;
BEGIN
    SELECT id INTO v_id FROM assessments WHERE token = p_token;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NOT_FOUND');
    END IF;

    v_row := expire_if_due(v_id);
    IF v_row.status = 'EXPIRED' THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'EXPIRED');
    END IF;
    -- 提交為單次動作；提交後不得再次提交或修改（FR-034）
    IF v_row.submitted_at IS NOT NULL THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'ALREADY_SUBMITTED');
    END IF;
    IF v_row.status <> 'PENDING_CANDIDATE' THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'INVALID_STATUS',
                                  'status', v_row.status);
    END IF;

    v_from := v_row.status;

    UPDATE assessments
       SET candidate_answer = p_answer,
           code_language    = COALESCE(p_language, code_language),
           status           = 'COMPLETED_AWAITING_REVIEW',
           submitted_at     = NOW()
     WHERE id = v_row.id
    RETURNING * INTO v_row;

    INSERT INTO audit_logs (assessment_id, action, from_status, to_status, actor_role, detail)
    VALUES (v_row.id, 'ANSWER_SUBMITTED', v_from, 'COMPLETED_AWAITING_REVIEW', 'CANDIDATE',
            jsonb_build_object('language', v_row.code_language,
                               'answer_length', length(COALESCE(p_answer, ''))));

    RETURN jsonb_build_object('ok', true, 'submitted_at', v_row.submitted_at);
END;
$$;

-- ── 評測路徑（FR-053、FR-059）──────────────────────────────────────────
-- 提交後的背景評測同樣不持有使用者 JWT。為維持「service_role 不得用於處理
-- 使用者請求」（R-002），評測的寫入也走 SECURITY DEFINER 函式，同樣以
-- 不可推測的 token 為鍵。與前四個函式的差異是**不檢查效期**——重新評測
-- （FR-059）可能發生在連結逾期之後。

CREATE OR REPLACE FUNCTION record_evaluation_start(p_token text)
    RETURNS jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_row     assessments;
    v_attempt integer;
BEGIN
    SELECT * INTO v_row FROM assessments WHERE token = p_token FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NOT_FOUND');
    END IF;
    IF v_row.submitted_at IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NOT_SUBMITTED');
    END IF;

    SELECT COALESCE(MAX(attempt_no), 0) + 1 INTO v_attempt
      FROM ai_reports WHERE assessment_id = v_row.id;

    INSERT INTO ai_reports (assessment_id, attempt_no, status)
    VALUES (v_row.id, v_attempt, 'PENDING');

    INSERT INTO audit_logs (assessment_id, action, actor_role, detail)
    VALUES (v_row.id, 'EVALUATION_STARTED', 'SYSTEM',
            jsonb_build_object('attempt_no', v_attempt));

    RETURN jsonb_build_object(
        'ok', true,
        'assessment_id',     v_row.id,
        'attempt_no',        v_attempt,
        'question_snapshot', v_row.question_snapshot,
        'answer',            v_row.candidate_answer,
        'language',          v_row.code_language,
        'chat_history',      v_row.ai_chat_history);
END;
$$;

CREATE OR REPLACE FUNCTION record_evaluation_result(
    p_token           text,
    p_attempt_no      integer,
    p_status          text,
    p_dimensions      jsonb   DEFAULT NULL,
    p_test_pass_ratio numeric DEFAULT NULL,
    p_model_id        text    DEFAULT NULL,
    p_error_message   text    DEFAULT NULL,
    p_execution       jsonb   DEFAULT NULL
)
    RETURNS jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = public
AS $$
DECLARE
    v_row assessments;
BEGIN
    IF p_status NOT IN ('SUCCESS', 'FAILED') THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'INVALID_STATUS');
    END IF;

    SELECT * INTO v_row FROM assessments WHERE token = p_token;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NOT_FOUND');
    END IF;

    IF p_execution IS NOT NULL THEN
        INSERT INTO execution_records (
            assessment_id, trigger, language, stdout, stderr,
            exit_code, duration_ms, peak_memory_kb, termination_reason, test_results)
        VALUES (
            v_row.id, 'EVALUATION',
            COALESCE(p_execution ->> 'language', v_row.code_language, 'unknown'),
            p_execution ->> 'stdout',
            p_execution ->> 'stderr',
            (p_execution ->> 'exit_code')::integer,
            (p_execution ->> 'duration_ms')::integer,
            (p_execution ->> 'peak_memory_kb')::integer,
            COALESCE(p_execution ->> 'termination_reason', 'COMPLETED'),
            p_execution -> 'test_results');
    END IF;

    -- ai_reports 為唯附加；僅 status 由 PENDING 轉為終態時允許這一次更新
    UPDATE ai_reports
       SET status          = p_status,
           dimensions      = p_dimensions,
           test_pass_ratio = p_test_pass_ratio,
           model_id        = p_model_id,
           error_message   = p_error_message
     WHERE assessment_id = v_row.id
       AND attempt_no    = p_attempt_no
       AND status        = 'PENDING';

    IF NOT FOUND THEN
        RETURN jsonb_build_object('ok', false, 'reason', 'NO_PENDING_REPORT');
    END IF;

    INSERT INTO audit_logs (assessment_id, action, actor_role, detail)
    VALUES (v_row.id,
            CASE WHEN p_status = 'SUCCESS' THEN 'EVALUATION_COMPLETED' ELSE 'EVALUATION_FAILED' END,
            'SYSTEM',
            jsonb_build_object('attempt_no', p_attempt_no,
                               'model_id',   p_model_id,
                               'test_pass_ratio', p_test_pass_ratio));

    RETURN jsonb_build_object('ok', true);
END;
$$;

-- ── 授權 ───────────────────────────────────────────────────────────────
-- 預設 EXECUTE 授予 PUBLIC，先撤銷再精確授權。
REVOKE ALL ON FUNCTION
    get_assessment_by_token(text, integer),
    append_chat_message(text, text, text, boolean),
    record_trial_run(text, jsonb, integer),
    submit_answer(text, text, text),
    record_evaluation_start(text),
    record_evaluation_result(text, integer, text, jsonb, numeric, text, text, jsonb)
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    get_assessment_by_token(text, integer),
    append_chat_message(text, text, text, boolean),
    record_trial_run(text, jsonb, integer),
    submit_answer(text, text, text),
    record_evaluation_start(text),
    record_evaluation_result(text, integer, text, jsonb, numeric, text, text, jsonb)
    TO anon, authenticated;
