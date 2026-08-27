-- =============================================================================
-- 智医 (ZhiYi) — 数据库迁移脚本：v1.0 → v2.0
-- 基层医疗AI辅助诊疗平台 · 优化版数据结构升级
-- =============================================================================
-- 适用场景：
--   已部署 v1.0 版本并存在业务数据，需要升级到 v2.0 数据结构。
--   新部署请直接使用 docker/mysql/init.sql，无需执行本脚本。
-- 执行方式：
--   docker exec -i zhiyi-mysql mysql -uroot -p<password> zhiyi < migrate_v1_to_v2.sql
-- 注意事项：
--   1. 执行前务必全量备份数据库。
--   2. 本脚本使用 IF EXISTS / IF NOT EXISTS 尽量做到幂等，但仍建议在维护窗口执行。
-- =============================================================================

USE zhiyi;

-- ── 0. 枚举值统一小写 ──────────────────────────────────────
-- v1.0 部分旧数据使用大写枚举名（如 DOCTOR/PENDING），v2.0 模型按值存储为小写。
ALTER TABLE users MODIFY COLUMN role ENUM('doctor','patient','admin') NOT NULL;
UPDATE users SET role = LOWER(role) WHERE role != LOWER(role);

ALTER TABLE exam_appointments MODIFY COLUMN status ENUM('pending','paid','confirmed','completed','cancelled') DEFAULT 'pending';
UPDATE exam_appointments SET status = LOWER(status) WHERE status != LOWER(status);

-- hospitals.level 旧数据已为小写，仅确保枚举定义与模型一致
ALTER TABLE hospitals MODIFY COLUMN level ENUM('village','township','county','city') NOT NULL;

-- ── 1. 新增患者健康档案表 ──────────────────────────────────
CREATE TABLE IF NOT EXISTS patient_health_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT UNIQUE NOT NULL,
    allergies JSON DEFAULT (JSON_ARRAY()),
    past_history JSON DEFAULT (JSON_ARRAY()),
    family_history JSON DEFAULT (JSON_ARRAY()),
    lifestyle JSON DEFAULT (JSON_OBJECT()),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 为已有患者自动创建空健康档案
INSERT IGNORE INTO patient_health_profiles (patient_id, allergies, past_history, family_history, lifestyle)
SELECT id, JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(), JSON_OBJECT() FROM patients;

-- ── 2. 扩展诊断记录表 ──────────────────────────────────────
-- MySQL 8.0 单条 ALTER 不支持 IF NOT EXISTS，需逐列判断
SET @exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'diagnoses' AND COLUMN_NAME = 'extracted_symptoms');
SET @sql = IF(@exists = 0, 'ALTER TABLE diagnoses ADD COLUMN extracted_symptoms JSON AFTER symptoms', 'SELECT "extracted_symptoms 已存在" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'diagnoses' AND COLUMN_NAME = 'medication_review');
SET @sql = IF(@exists = 0, 'ALTER TABLE diagnoses ADD COLUMN medication_review JSON AFTER treatment_plan', 'SELECT "medication_review 已存在" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'diagnoses' AND COLUMN_NAME = 'follow_up_plan');
SET @sql = IF(@exists = 0, 'ALTER TABLE diagnoses ADD COLUMN follow_up_plan JSON AFTER medical_record', 'SELECT "follow_up_plan 已存在" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- medical_record 旧版为 TEXT，需转为 JSON（内容已是合法 JSON）
SET @mr_type = (SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'diagnoses' AND COLUMN_NAME = 'medical_record');
SET @sql = IF(@mr_type = 'text', 'ALTER TABLE diagnoses MODIFY COLUMN medical_record JSON', 'SELECT "medical_record 类型无需调整" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- treatment_plan 旧版为 TEXT，部分记录是字符串而非 JSON，先包装成 JSON 数组
UPDATE diagnoses
SET treatment_plan = JSON_ARRAY(treatment_plan)
WHERE treatment_plan IS NOT NULL
  AND treatment_plan != ''
  AND JSON_VALID(treatment_plan) = 0;

-- 将 treatment_plan 转为 JSON 类型
SET @tp_type = (SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'diagnoses' AND COLUMN_NAME = 'treatment_plan');
SET @sql = IF(@tp_type = 'text', 'ALTER TABLE diagnoses MODIFY COLUMN treatment_plan JSON', 'SELECT "treatment_plan 类型无需调整" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ── 3. 扩展检查预约表 ──────────────────────────────────────
SET @exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'exam_appointments' AND COLUMN_NAME = 'report_data');
SET @sql = IF(@exists = 0, 'ALTER TABLE exam_appointments ADD COLUMN report_data JSON AFTER report_url', 'SELECT "report_data 已存在" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'exam_appointments' AND COLUMN_NAME = 'ai_interpretation');
SET @sql = IF(@exists = 0, 'ALTER TABLE exam_appointments ADD COLUMN ai_interpretation TEXT AFTER report_data', 'SELECT "ai_interpretation 已存在" AS message');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ── 4. 新增处方表 ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prescriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    diagnosis_id INT,
    status ENUM('draft','confirmed','completed','cancelled') DEFAULT 'confirmed',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
    FOREIGN KEY (diagnosis_id) REFERENCES diagnoses(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS prescription_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    drug_id INT NOT NULL,
    dosage VARCHAR(255),
    quantity INT NOT NULL,
    duration_days INT,
    instructions TEXT,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── 5. 重构药品订单表：一单一药 → 主从结构 ────────────────
-- 说明：v1.0 的 drug_orders 表包含 drug_id / quantity 等字段；
-- 若迁移过程中断，可能留下 drug_orders_old。两种情况都视为有待迁移数据。
SET @old_table_exists = (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'drug_orders_old');
SET @old_column_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'drug_orders' AND COLUMN_NAME = 'drug_id');
SET @has_old_drug_order = IF(@old_table_exists > 0 OR @old_column_exists > 0, 1, 0);

-- 仅在旧表未重命名且当前 drug_orders 仍是旧结构时才重命名
SET @sql = IF(@old_column_exists > 0 AND @old_table_exists = 0,
    'ALTER TABLE drug_orders RENAME TO drug_orders_old',
    'SELECT "drug_orders 无需重命名" AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 创建新的订单主表（仅在旧表被重命名后执行）
SET @need_create_master = (
    SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'zhiyi' AND TABLE_NAME = 'drug_orders'
);

SET @create_master_sql = IF(@need_create_master = 0,
    'CREATE TABLE drug_orders (
        id INT AUTO_INCREMENT PRIMARY KEY,
        patient_id INT NOT NULL,
        prescription_id INT,
        order_no VARCHAR(50) UNIQUE NOT NULL,
        total_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
        pay_status ENUM(\'pending\',\'paid\',\'refunded\') DEFAULT \'pending\',
        delivery_status ENUM(\'pending\',\'shipped\',\'delivered\',\'cancelled\') DEFAULT \'pending\',
        address VARCHAR(255) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
        FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4',
    'SELECT "drug_orders 已存在，跳过创建" AS message'
);
PREPARE stmt FROM @create_master_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS drug_order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    drug_order_id INT NOT NULL,
    drug_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (drug_order_id) REFERENCES drug_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 迁移旧订单数据到新主从表
-- v1.0 旧表没有 unit_price，需用 total_price / quantity 反推（保留 2 位小数）
-- PREPARE 只能执行单条语句，故拆成三步
SET @migrate_master = IF(@has_old_drug_order > 0,
    'INSERT INTO drug_orders (id, patient_id, prescription_id, order_no, total_price, pay_status, delivery_status, address, created_at)
     SELECT id, patient_id, prescription_id, CONCAT(\'DO\', LPAD(id, 10, \'0\')), total_price, LOWER(pay_status), LOWER(delivery_status), address, created_at
     FROM drug_orders_old',
    'SELECT "无旧订单数据需要迁移" AS message'
);
PREPARE stmt FROM @migrate_master; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @migrate_items = IF(@has_old_drug_order > 0,
    'INSERT INTO drug_order_items (drug_order_id, drug_id, quantity, unit_price, subtotal)
     SELECT id, drug_id, quantity, ROUND(total_price / quantity, 2), total_price FROM drug_orders_old',
    'SELECT "无旧订单明细需要迁移" AS message'
);
PREPARE stmt FROM @migrate_items; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @drop_old = IF(@has_old_drug_order > 0,
    'DROP TABLE drug_orders_old',
    'SELECT "无旧订单表需要删除" AS message'
);
PREPARE stmt FROM @drop_old; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ── 6. 新增支付流水表 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    status ENUM('pending','success','failed','refunded') DEFAULT 'pending',
    payment_method ENUM('mock','wechat','alipay') DEFAULT 'mock',
    transaction_no VARCHAR(100),
    paid_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 为已支付订单生成 mock 支付流水（避免历史订单无支付记录）
INSERT IGNORE INTO payments (order_id, order_type, amount, status, payment_method, paid_at)
SELECT id, 'drug', total_price, 'success', 'mock', created_at
FROM drug_orders
WHERE pay_status = 'paid';

-- ── 7. 新增审计日志表 ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    action VARCHAR(50) NOT NULL,
    resource VARCHAR(50),
    resource_id INT,
    detail JSON,
    ip_address VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================================================
-- 迁移完成
-- =============================================================================
