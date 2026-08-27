// 智医 (ZhiYi) — MongoDB 初始化脚本
// 基层医疗AI辅助诊疗平台

// 切换数据库
db = db.getSiblingDB('zhiyi');

// ── 病历文档集合 ──
db.createCollection('medical_records');
db.medical_records.createIndex({ patient_id: 1, created_at: -1 });
db.medical_records.createIndex({ doctor_id: 1 });

// ── 患者档案集合（含就诊 visits / 健康趋势）──
db.createCollection('patient_profiles');
db.patient_profiles.createIndex({ patient_id: 1 }, { unique: true });
db.patient_profiles.createIndex({ updated_at: -1 });

// ── AI 医学问答日志集合 ──
db.createCollection('ai_qa_logs');
db.ai_qa_logs.createIndex({ patient_id: 1, created_at: -1 });
db.ai_qa_logs.createIndex({ created_at: -1 });
