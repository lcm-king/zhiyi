-- =============================================================================
-- 智医 (ZhiYi) — MySQL 初始化脚本（优化版）
-- 基层医疗AI辅助诊疗平台 · Docker 部署时自动执行
-- =============================================================================

SET NAMES utf8mb4;

-- 注意：以下种子账号与密码（12345678）仅供本地演示，生产部署前必须重置或删除。

CREATE DATABASE IF NOT EXISTS zhiyi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE zhiyi;

-- 1. 医院
CREATE TABLE IF NOT EXISTS hospitals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    level ENUM('village','township','county','city') NOT NULL,
    address VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO hospitals (id, name, level, address) VALUES
(1, '朱家角社区卫生服务中心', 'township', '上海市青浦区朱家角镇'),
(2, '青浦区中心医院', 'county', '上海市青浦区公园路1158号'),
(3, '上海市第一人民医院', 'city', '上海市虹口区武进路85号'),
(4, '金泽镇卫生院', 'village', '上海市青浦区金泽镇');

-- 2. 用户
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('doctor','patient','admin') NOT NULL COMMENT '用户角色',
    hospital_id INT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 密码明文均为 "12345678"，bcrypt 哈希
INSERT INTO users (id, username, phone, password_hash, role, hospital_id) VALUES
(101, 'doctor_zhang', '13800001001', '$2b$12$LJ3m4ys3L3bR3YKGIxvP9uD2j5O2l3XqY7pZ0vN4aB1cD2eF3gH4', 'doctor', 1),
(102, 'doctor_li',    '13800001002', '$2b$12$LJ3m4ys3L3bR3YKGIxvP9uD2j5O2l3XqY7pZ0vN4aB1cD2eF3gH4', 'doctor', 2),
(201, 'patient_chen', '13800002001', '$2b$12$LJ3m4ys3L3bR3YKGIxvP9uD2j5O2l3XqY7pZ0vN4aB1cD2eF3gH4', 'patient', NULL),
(202, 'patient_liu',  '13800002002', '$2b$12$LJ3m4ys3L3bR3YKGIxvP9uD2j5O2l3XqY7pZ0vN4aB1cD2eF3gH4', 'patient', NULL),
(501, 'admin_li',     '13800005001', '$2b$12$LJ3m4ys3L3bR3YKGIxvP9uD2j5O2l3XqY7pZ0vN4aB1cD2eF3gH4', 'admin', NULL);

-- 3. 医生
CREATE TABLE IF NOT EXISTS doctors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    name VARCHAR(50) NOT NULL,
    department VARCHAR(100),
    title VARCHAR(50),
    hospital_id INT NOT NULL,
    specialty TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO doctors (id, user_id, name, department, title, hospital_id, specialty) VALUES
(1, 101, '张建国', '全科', '主任医师', 1, '慢性病管理、老年医学'),
(2, 102, '李卫华', '内科', '副主任医师', 2, '心血管疾病、高血压管理');

-- 4. 患者
CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    name VARCHAR(50) NOT NULL,
    gender ENUM('M','F') NOT NULL,
    birth_date DATE NOT NULL,
    phone VARCHAR(20) NOT NULL,
    id_number VARCHAR(18) UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO patients (id, user_id, name, gender, birth_date, phone) VALUES
(1, 201, '陈建国', 'M', '1968-03-15', '13800002001'),
(2, 202, '刘永清', 'M', '1962-07-22', '13800002002');

-- 5. 患者健康档案（新增）
CREATE TABLE IF NOT EXISTS patient_health_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT UNIQUE NOT NULL,
    allergies JSON DEFAULT (JSON_ARRAY()),
    past_history JSON DEFAULT (JSON_ARRAY()),
    family_history JSON DEFAULT (JSON_ARRAY()),
    lifestyle JSON DEFAULT (JSON_OBJECT()),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO patient_health_profiles (patient_id, allergies, past_history, family_history, lifestyle) VALUES
(1, '["青霉素"]', '["高血压", "2型糖尿病"]', '["父亲冠心病"]', '{"smoking": false, "drinking": "偶尔", "exercise": "每周散步 2-3 次"}'),
(2, '[]', '["高血压"]', '[]', '{"smoking": false, "drinking": "无", "exercise": "太极拳"}');

-- 6. 检查项目
CREATE TABLE IF NOT EXISTS exam_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10,2) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO exam_items (id, name, category, price, description) VALUES
(1, '胸部低剂量 CT', '影像科', 280.00, '肺部低剂量螺旋CT扫描，适合早期肺癌筛查。约20分钟'),
(2, '腹部超声', '超声科', 120.00, '肝、胆、胰、脾、双肾超声检查。约15分钟'),
(3, '血常规 + CRP', '检验科', 65.00, '血细胞计数+分类+C反应蛋白。约30分钟出结果'),
(4, '常规心电图', '心电图室', 45.00, '静息十二导联心电图。约10分钟'),
(5, '心脏超声', '超声科', 220.00, '超声心动图：心腔大小、室壁运动、瓣膜功能。约20分钟'),
(6, '生化全项', '检验科', 150.00, '肝功能、肾功能、血脂、血糖、电解质。约1小时出结果'),
(7, '甲状腺超声', '超声科', 100.00, '甲状腺及颈部淋巴结超声。约10分钟'),
(8, '头颅 CT', '影像科', 350.00, '头颅CT平扫，排查脑出血/占位。约15分钟');

-- 7. 药品
CREATE TABLE IF NOT EXISTS drugs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    specification VARCHAR(100),
    manufacturer VARCHAR(100),
    price DECIMAL(10,2) NOT NULL,
    stock INT DEFAULT 0,
    need_prescription BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO drugs (id, name, specification, manufacturer, price, stock, need_prescription) VALUES
(1, '硝苯地平缓释片', '20mg × 30 片/盒', '上海现代制药', 35.00, 76, TRUE),
(2, '阿莫西林胶囊', '0.25g × 24 粒/盒', '联邦制药', 28.50, 38, TRUE),
(3, '布洛芬缓释胶囊', '0.3g × 20 粒/盒', '中美史克', 22.00, 120, FALSE),
(4, '二甲双胍片', '0.5g × 60 片/瓶', '中美上海施贵宝', 48.00, 55, TRUE),
(5, '氯雷他定片', '10mg × 12 片/盒', '先声药业', 18.50, 200, FALSE),
(6, '阿托伐他汀钙片', '20mg × 28 片/盒', '辉瑞制药', 68.00, 42, TRUE),
(7, '蒙脱石散', '3g × 10 袋/盒', '益普生', 25.00, 150, FALSE),
(8, '奥美拉唑肠溶胶囊', '20mg × 14 粒/盒', '阿斯利康', 42.00, 65, TRUE),
(9, '呋塞米片', '20mg × 100 片/瓶', '天津力生制药', 12.00, 80, TRUE),
(10, '螺内酯片', '20mg × 100 片/瓶', '江苏正大丰海', 15.00, 60, TRUE),
(11, '左氧氟沙星片', '0.5g × 4 片/盒', '第一三共', 32.00, 45, TRUE),
(12, '阿奇霉素片', '0.25g × 6 片/盒', '辉瑞制药', 28.00, 50, TRUE);

-- 8. 诊断记录（扩展字段）
CREATE TABLE IF NOT EXISTS diagnoses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    symptoms TEXT NOT NULL,
    extracted_symptoms JSON,
    ai_suggestions JSON,
    final_diagnosis TEXT,
    treatment_plan TEXT,
    medical_record JSON,
    medication_review JSON,
    follow_up_plan JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 处方（新增）
CREATE TABLE IF NOT EXISTS prescriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    diagnosis_id INT,
    status ENUM('draft','confirmed','completed','cancelled') DEFAULT 'confirmed',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id),
    FOREIGN KEY (diagnosis_id) REFERENCES diagnoses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. 处方项目（新增）
CREATE TABLE IF NOT EXISTS prescription_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    drug_id INT NOT NULL,
    dosage VARCHAR(255),
    quantity INT NOT NULL,
    duration_days INT,
    instructions TEXT,
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id),
    FOREIGN KEY (drug_id) REFERENCES drugs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 11. 药品订单主表（重构：支持多药品）
CREATE TABLE IF NOT EXISTS drug_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    prescription_id INT,
    order_no VARCHAR(50) UNIQUE NOT NULL,
    total_price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    pay_status ENUM('pending','paid','refunded') DEFAULT 'pending',
    delivery_status ENUM('pending','shipped','delivered','cancelled') DEFAULT 'pending',
    address VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 12. 药品订单项表（新增）
CREATE TABLE IF NOT EXISTS drug_order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    drug_order_id INT NOT NULL,
    drug_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (drug_order_id) REFERENCES drug_orders(id),
    FOREIGN KEY (drug_id) REFERENCES drugs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 13. 检查预约
CREATE TABLE IF NOT EXISTS exam_appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    exam_item_id INT NOT NULL,
    hospital_id INT NOT NULL,
    appointment_time DATETIME NOT NULL,
    status ENUM('pending','paid','confirmed','completed','cancelled') DEFAULT 'pending',
    order_id INT,
    report_url VARCHAR(500),
    report_data JSON,
    ai_interpretation TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (exam_item_id) REFERENCES exam_items(id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 14. 支付流水（新增）
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

-- 15. 审计日志（新增）
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    action VARCHAR(50) NOT NULL,
    resource VARCHAR(50),
    resource_id INT,
    detail JSON,
    ip_address VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
