-- 0002_internal_users：HR 與部門主管帳號
-- 來源：data-model.md §2；FR-001、FR-003、FR-005

CREATE TABLE IF NOT EXISTS internal_users (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID         UNIQUE NOT NULL,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(150) UNIQUE NOT NULL,
    role         VARCHAR(20)  NOT NULL
                 CONSTRAINT internal_users_role_check
                 CHECK (role IN ('HR', 'MANAGER')),
    dept_id      VARCHAR(50)  REFERENCES departments (id),
    is_active    BOOLEAN      NOT NULL DEFAULT true,

    -- MANAGER 必須隸屬部門；HR 為全公司角色，dept_id 必須為 NULL（data-model.md 驗證規則）
    CONSTRAINT internal_users_role_dept_consistency CHECK (
        (role = 'MANAGER' AND dept_id IS NOT NULL)
        OR
        (role = 'HR'      AND dept_id IS NULL)
    )
);

-- 「一人一主管」假設：每個部門至多一位 active 的 MANAGER。
-- 以部分唯一索引強制——停用的主管不佔用名額，使離職接手可行（邊界情況：主管離職）。
CREATE UNIQUE INDEX IF NOT EXISTS internal_users_one_active_manager_per_dept
    ON internal_users (dept_id)
    WHERE role = 'MANAGER' AND is_active;

COMMENT ON COLUMN internal_users.auth_user_id IS
    '對應 Supabase Auth 的使用者。登入時將 role 寫入 app_role、dept_id 寫入 dept_id 自訂 claim，供 RLS 使用（research.md R-002）。';
