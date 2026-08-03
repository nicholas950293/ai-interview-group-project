-- 0012_internal_users_bootstrap：登入時的自我查詢政策
-- 來源：spec 004（FR-005 的登入流程）

-- 為什麼需要這條政策
-- ────────────────────────────────────────────────────────────────────
-- 0009 的兩條 internal_users 政策都以 app_role() 為條件：
--
--   internal_users_hr_select    USING (app_role() = 'HR')
--   internal_users_self_select  USING (app_role() = 'MANAGER' AND auth_user_id = ...)
--
-- 但登入當下 Supabase Auth 剛發出的 token **還沒有** app_role claim——那正是
-- 我們要查出來的東西。於是形成雞生蛋：要先知道角色，才讀得到記錄角色的那一列。
--
-- 這條政策打破該循環：任何已認證的使用者都可以讀「自己那一列」，不需要角色。
--
-- 安全影響
-- ────────────────────────────────────────────────────────────────────
-- 它比既有政策更**窄**，不放寬任何跨使用者的存取：
--   * 條件為 auth_user_id = app_auth_user_id()，只可能命中請求者本人那一列
--   * 使用者讀到的是自己的姓名、Email、角色與部門——他本來就知道的資訊
--   * 不影響 assessments、ai_reports、manager_decisions 等任何其他資料表
--   * anon 仍被 0009 的 REVOKE 擋在門外，本政策只授予 authenticated

DROP POLICY IF EXISTS internal_users_bootstrap_select ON internal_users;
CREATE POLICY internal_users_bootstrap_select ON internal_users
    FOR SELECT TO authenticated
    USING (auth_user_id = app_auth_user_id());

COMMENT ON POLICY internal_users_bootstrap_select ON internal_users IS
    '登入流程用：已認證者可讀自己那一列以取得角色與部門。不得放寬為讀取他人。';
