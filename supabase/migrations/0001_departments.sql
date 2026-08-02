-- 0001_departments：部門與其類型
-- 來源：data-model.md §1；FR-010（部門下拉選單）、FR-029（類型決定作答介面）

CREATE TABLE IF NOT EXISTS departments (
    id   VARCHAR(50)  PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(30)  NOT NULL
         CONSTRAINT departments_type_check
         CHECK (type IN ('ENGINEERING', 'NON_ENGINEERING'))
);

COMMENT ON TABLE  departments      IS '公司內的組織單位。type 決定應徵者看到的作答介面形式（FR-029）。';
COMMENT ON COLUMN departments.type IS 'ENGINEERING 提供程式碼作答介面；NON_ENGINEERING 提供結構化文字介面。';
