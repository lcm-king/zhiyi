-- =============================================================================
-- 就诊记录种子数据（2026-08-14）
-- 用途：清除开发测试产生的垃圾诊断记录，替换为与患者健康档案一致的真实就诊记录
-- 患者1：高血压10年 / 冠心病5年(2019支架) / 2型糖尿病3年 / 青霉素过敏
-- 患者2：慢性心衰8年 / 房颤3年 / 高脂血症 / 磺胺过敏
-- =============================================================================

SET NAMES utf8mb4;

-- 1. 清空测试垃圾数据（备份表 diagnoses_backup_20260814 已保留原始数据）
DELETE FROM diagnoses;

-- 2. 患者1 就诊记录（5 次，医生郑经纬 = doctor_id 1，朱家角医院）
INSERT INTO diagnoses
  (patient_id, doctor_id, symptoms, extracted_symptoms, ai_suggestions, final_diagnosis,
   treatment_plan, medical_record, medication_review, follow_up_plan, use_ai, created_at)
VALUES
(1, 1,
 '近一周反复头晕头痛，晨起明显，自测血压 165/102 mmHg，偶有视物模糊',
 JSON_ARRAY('头晕','头痛','视物模糊','血压升高'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '高血压病 2 级（高危）', 'confidence', 92,
     'description', '晨起血压升高伴头晕头痛，符合高血压病 2 级表现，需评估靶器官损害。',
     'tags', JSON_ARRAY('高血压','头晕'), 'tone', 'red',
     'differential_diagnoses', JSON_ARRAY('继发性高血压','脑供血不足'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '血常规 + CRP', 'reason', '评估感染与炎症指标', 'priority', 'normal'),
       JSON_OBJECT('exam_name', '心电图', 'reason', '评估心肌缺血与心律失常', 'priority', 'normal')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '硝苯地平', 'reason', '控制血压', 'priority', 'high'),
       JSON_OBJECT('drug_name', '阿托伐他汀', 'reason', '稳定斑块、调脂治疗', 'priority', 'normal')))),
 '高血压病 2 级（高危）伴 2 型糖尿病',
 '["苯磺酸氨氯地平 5mg 每日一次口服", "阿托伐他汀 20mg 每晚一次口服", "二甲双胍 0.5g 每日两次口服", "每日晨起与睡前自测血压并记录"]',
 JSON_OBJECT('chief_complaint', '反复头晕头痛一周', 'present_illness', '近一周晨起头晕头痛，自测血压升高至 165/102 mmHg',
   'past_history', '高血压病 10 年，冠心病 5 年（2019 年冠脉支架植入术），2 型糖尿病 3 年',
   'allergies', '青霉素、花粉过敏', 'physical_examination', JSON_OBJECT('bp', '165/102 mmHg', 'hr', '78 次/分'),
   'preliminary_diagnosis', '高血压病 2 级（高危）伴 2 型糖尿病', 'treatment_plan', JSON_ARRAY('降压','调脂','降糖','生活方式干预'),
   'generated_at', '2026-08-04 09:30:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY('注意监测血糖，二甲双胍与造影剂联用需评估肾功能'),
   'recommendations', JSON_ARRAY('规律服药，勿自行停药','每日晨起测量血压'), 'requires_manual_review', false,
   'reviewed_at', '2026-08-04 09:30:00'),
 JSON_OBJECT('interval_days', 14, 'watch_items', JSON_ARRAY('血压波动','头晕加重','胸闷胸痛'),
   'lifestyle_advice', JSON_ARRAY('低盐低脂饮食，每日食盐 <5g','每日散步 30 分钟','戒烟限酒'),
   'warning_symptoms', JSON_ARRAY('剧烈胸痛','言语不清','肢体无力','意识改变')),
 1, '2026-08-04 09:30:00'),

(1, 1,
 '活动后胸闷、心悸半月，爬三层楼即感气促，休息 3-5 分钟缓解，无胸痛放射',
 JSON_ARRAY('胸闷','心悸','活动后气促'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '冠状动脉粥样硬化性心脏病（稳定型心绞痛）', 'confidence', 86,
     'description', '活动后胸闷气促，休息可缓解，结合冠脉支架术后病史，考虑稳定型心绞痛。',
     'tags', JSON_ARRAY('冠心病','胸闷'), 'tone', 'orange',
     'differential_diagnoses', JSON_ARRAY('心力衰竭','心律失常'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '心电图', 'reason', '评估心肌缺血', 'priority', 'high'),
       JSON_OBJECT('exam_name', '心脏彩色多普勒超声', 'reason', '评估心功能与室壁运动', 'priority', 'high')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '阿司匹林', 'reason', '抗血小板治疗', 'priority', 'high'),
       JSON_OBJECT('drug_name', '美托洛尔', 'reason', '减慢心率、减少心肌耗氧', 'priority', 'high')))),
 '冠状动脉粥样硬化性心脏病（稳定型心绞痛）',
 '["阿司匹林 100mg 每日一次口服", "琥珀酸美托洛尔缓释片 47.5mg 每日一次口服", "硝酸甘油 0.5mg 舌下含服（胸闷发作时）", "限制剧烈活动，避免诱发因素"]',
 JSON_OBJECT('chief_complaint', '活动后胸闷心悸半月', 'present_illness', '半月来活动后胸闷气促，休息缓解，无静息痛',
   'past_history', '冠心病 5 年，2019 年冠脉支架植入术', 'allergies', '青霉素、花粉过敏',
   'physical_examination', JSON_OBJECT('bp', '148/90 mmHg', 'hr', '82 次/分'),
   'preliminary_diagnosis', '冠状动脉粥样硬化性心脏病（稳定型心绞痛）',
   'treatment_plan', JSON_ARRAY('抗血小板','调脂','控制心率','随访心功能'), 'generated_at', '2026-07-15 10:20:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY('注意观察有无静息痛或疼痛加重'),
   'recommendations', JSON_ARRAY('随身携带硝酸甘油','避免过度劳累与情绪激动'), 'requires_manual_review', false,
   'reviewed_at', '2026-07-15 10:20:00'),
 JSON_OBJECT('interval_days', 30, 'watch_items', JSON_ARRAY('胸痛性质与频率','活动耐量变化'),
   'lifestyle_advice', JSON_ARRAY('低盐低脂饮食','规律作息，避免熬夜','坚持康复运动'),
   'warning_symptoms', JSON_ARRAY('持续胸痛超过 20 分钟','冷汗、濒死感','血压骤降')),
 1, '2026-07-15 10:20:00'),

(1, 1,
 '近一月口干多饮多尿，体重下降约 2kg，空腹血糖 9.8 mmol/L，餐后 2h 血糖 14.2 mmol/L',
 JSON_ARRAY('口干','多饮','多尿','体重下降','血糖升高'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '2 型糖尿病（血糖控制不佳）', 'confidence', 90,
     'description', '空腹及餐后血糖均明显升高，伴典型三多一少症状，符合 2 型糖尿病血糖控制不佳。',
     'tags', JSON_ARRAY('糖尿病','血糖升高'), 'tone', 'red',
     'differential_diagnoses', JSON_ARRAY('糖尿病酮症','感染所致应激性高血糖'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '糖化血红蛋白', 'reason', '评估近 3 个月平均血糖', 'priority', 'high'),
       JSON_OBJECT('exam_name', '肾功能 + 电解质', 'reason', '评估糖尿病肾病风险', 'priority', 'normal')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '二甲双胍', 'reason', '一线降糖治疗', 'priority', 'high')))),
 '2 型糖尿病（血糖控制不佳）',
 '["二甲双胍 0.5g 每日两次口服", "达格列净 10mg 每日一次口服", "血糖监测：空腹+三餐后 2h 每日记录", "转诊内分泌科进一步评估胰岛功能"]',
 JSON_OBJECT('chief_complaint', '口干多饮多尿一月', 'present_illness', '一月来口干多饮多尿，体重下降约 2kg，空腹血糖 9.8 mmol/L',
   'past_history', '2 型糖尿病 3 年', 'allergies', '青霉素、花粉过敏',
   'physical_examination', JSON_OBJECT('bp', '142/86 mmHg', 'bmi', 24.8),
   'preliminary_diagnosis', '2 型糖尿病（血糖控制不佳）',
   'treatment_plan', JSON_ARRAY('强化降糖','饮食控制','运动干预','监测并发症'), 'generated_at', '2026-06-10 14:00:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY('二甲双胍需随餐服用，注意胃肠道反应'),
   'recommendations', JSON_ARRAY('每日记录血糖','控制主食量，增加蔬菜摄入'), 'requires_manual_review', false,
   'reviewed_at', '2026-06-10 14:00:00'),
 JSON_OBJECT('interval_days', 30, 'watch_items', JSON_ARRAY('空腹与餐后血糖','体重变化','有无视物模糊'),
   'lifestyle_advice', JSON_ARRAY('低糖低脂饮食','每周至少 150 分钟中等强度运动','定期检查足部'),
   'warning_symptoms', JSON_ARRAY('恶心呕吐、腹痛','呼吸有烂苹果味','意识模糊')),
 1, '2026-06-10 14:00:00'),

(1, 1,
 '受凉后咳嗽咳痰 5 天，黄痰，咽痛，低热 37.8℃，无胸痛咯血',
 JSON_ARRAY('咳嗽','咳黄痰','咽痛','低热'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '急性上呼吸道感染', 'confidence', 88,
     'description', '受凉后咳嗽咳痰伴咽痛低热，符合急性上呼吸道感染，需注意与流感鉴别。',
     'tags', JSON_ARRAY('感冒','咳嗽'), 'tone', 'blue',
     'differential_diagnoses', JSON_ARRAY('流行性感冒','急性支气管炎'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '血常规 + CRP', 'reason', '评估感染类型', 'priority', 'high')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '阿莫西林', 'reason', '抗感染治疗（青霉素过敏者禁用，需更换）', 'priority', 'normal'),
       JSON_OBJECT('drug_name', '布洛芬', 'reason', '退热止痛', 'priority', 'normal')))),
 '急性上呼吸道感染',
 '["头孢呋辛酯 0.25g 每日两次口服（青霉素过敏，避免使用阿莫西林）", "布洛芬 0.3g 必要时口服退热", "多饮水、注意休息"]',
 JSON_OBJECT('chief_complaint', '咳嗽咳痰 5 天', 'present_illness', '受凉后出现咳嗽咳黄痰、咽痛、低热，无胸痛咯血',
   'past_history', '高血压病、冠心病、2 型糖尿病', 'allergies', '青霉素、花粉过敏',
   'physical_examination', JSON_OBJECT('t', '37.8℃', 'pharynx', '咽部充血'),
   'preliminary_diagnosis', '急性上呼吸道感染',
   'treatment_plan', JSON_ARRAY('抗感染','对症退热','休息补液'), 'generated_at', '2026-05-06 09:10:00'),
 JSON_OBJECT('passed', false, 'warnings', JSON_ARRAY('患者青霉素过敏，已调整为头孢类，用药期间观察有无过敏反应'),
   'recommendations', JSON_ARRAY('多饮水','监测体温'), 'requires_manual_review', true,
   'reviewed_at', '2026-05-06 09:10:00'),
 JSON_OBJECT('interval_days', 7, 'watch_items', JSON_ARRAY('体温','咳嗽咳痰变化'),
   'lifestyle_advice', JSON_ARRAY('注意保暖','避免劳累','勤通风'),
   'warning_symptoms', JSON_ARRAY('呼吸困难','高热不退','咳脓臭痰')),
 1, '2026-05-06 09:10:00'),

(1, 1,
 '常规复诊：血压控制评估，近两周自测血压 135-145/85-90 mmHg，无不适',
 JSON_ARRAY('血压偏高','复诊'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '高血压病 2 级（高危）伴冠心病', 'confidence', 84,
     'description', '血压控制仍欠佳，需优化降压方案并坚持生活方式干预。',
     'tags', JSON_ARRAY('高血压','复诊'), 'tone', 'orange',
     'differential_diagnoses', JSON_ARRAY('白大衣高血压','继发性高血压'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '血常规 + CRP', 'reason', '常规复查', 'priority', 'normal'),
       JSON_OBJECT('exam_name', '心电图', 'reason', '随访心脏情况', 'priority', 'normal')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '硝苯地平', 'reason', '维持降压治疗', 'priority', 'high')))),
 '高血压病 2 级（高危）伴冠心病',
 '["苯磺酸氨氯地平 5mg 每日一次口服（维持）", "阿托伐他汀 20mg 每晚一次口服（维持）", "继续家庭血压监测，每周门诊随访"]',
 JSON_OBJECT('chief_complaint', '高血压常规复诊', 'present_illness', '近两周家庭自测血压 135-145/85-90 mmHg，无明显不适',
   'past_history', '高血压病 10 年，冠心病 5 年', 'allergies', '青霉素、花粉过敏',
   'physical_examination', JSON_OBJECT('bp', '142/88 mmHg', 'hr', '76 次/分'),
   'preliminary_diagnosis', '高血压病 2 级（高危）伴冠心病',
   'treatment_plan', JSON_ARRAY('维持降压调脂','随访评估'), 'generated_at', '2026-03-18 09:00:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY(), 'recommendations', JSON_ARRAY('坚持服药，勿擅自调整剂量'),
   'requires_manual_review', false, 'reviewed_at', '2026-03-18 09:00:00'),
 JSON_OBJECT('interval_days', 30, 'watch_items', JSON_ARRAY('血压','胸闷症状'),
   'lifestyle_advice', JSON_ARRAY('低盐低脂饮食','规律运动'), 'warning_symptoms', JSON_ARRAY('胸痛','黑矇','晕厥')),
 1, '2026-03-18 09:00:00');

-- 3. 患者2 就诊记录（3 次，医生李卫华 = doctor_id 2）
INSERT INTO diagnoses
  (patient_id, doctor_id, symptoms, extracted_symptoms, ai_suggestions, final_diagnosis,
   treatment_plan, medical_record, medication_review, follow_up_plan, use_ai, created_at)
VALUES
(2, 2,
 '活动后气促加重一周，夜间需垫高枕头入睡，双下肢轻度水肿，偶有心悸',
 JSON_ARRAY('气促','夜间呼吸困难','下肢水肿','心悸'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '慢性心力衰竭（NYHA II 级）伴心房颤动', 'confidence', 89,
     'description', '活动后气促、夜间阵发性呼吸困难、双下肢水肿，结合慢性心衰及房颤病史，考虑心衰加重。',
     'tags', JSON_ARRAY('心衰','房颤'), 'tone', 'red',
     'differential_diagnoses', JSON_ARRAY('慢性阻塞性肺疾病','肺栓塞'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '心脏彩色多普勒超声', 'reason', '评估心功能射血分数', 'priority', 'high'),
       JSON_OBJECT('exam_name', '心电图', 'reason', '评估房颤心律', 'priority', 'high'),
       JSON_OBJECT('exam_name', '血常规 + CRP', 'reason', '评估感染与贫血', 'priority', 'normal')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '呋塞米', 'reason', '利尿减轻负荷', 'priority', 'high'),
       JSON_OBJECT('drug_name', '美托洛尔', 'reason', '控制心室率', 'priority', 'high')))),
 '慢性心力衰竭（NYHA II 级）伴心房颤动',
 '["呋塞米 20mg 每日一次口服", "琥珀酸美托洛尔缓释片 23.75mg 每日一次口服", "华法林/新型口服抗凝药（房颤卒中预防）", "每日记录体重，限盐限水"]',
 JSON_OBJECT('chief_complaint', '活动后气促加重一周', 'present_illness', '一周来活动后气促加重，夜间阵发性呼吸困难，双下肢水肿',
   'past_history', '慢性心力衰竭 8 年，心房颤动 3 年，高脂血症', 'allergies', '磺胺类药物过敏',
   'physical_examination', JSON_OBJECT('bp', '138/84 mmHg', 'hr', '96 次/分（房颤律）', 'edema', '双下肢轻度凹陷性水肿'),
   'preliminary_diagnosis', '慢性心力衰竭（NYHA II 级）伴心房颤动',
   'treatment_plan', JSON_ARRAY('利尿','控制心室率','抗凝','限制水钠'), 'generated_at', '2026-08-02 10:00:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY('磺胺类药物过敏，避免使用磺胺类利尿剂（如氢氯噻嗪）'),
   'recommendations', JSON_ARRAY('每日晨起称体重','记录出入量'), 'requires_manual_review', true,
   'reviewed_at', '2026-08-02 10:00:00'),
 JSON_OBJECT('interval_days', 14, 'watch_items', JSON_ARRAY('体重','气促程度','水肿变化'),
   'lifestyle_advice', JSON_ARRAY('限盐 <3g/日','限水 1500ml/日','避免剧烈活动'),
   'warning_symptoms', JSON_ARRAY('静息时气促','咳粉红色泡沫痰','晕厥')),
 1, '2026-08-02 10:00:00'),

(2, 2,
 '反复心悸、脉律不齐两周，自测脉搏约 90-110 次/分且不规律，无胸痛晕厥',
 JSON_ARRAY('心悸','脉律不齐','心率快'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '心房颤动（阵发性）', 'confidence', 91,
     'description', '心悸伴脉律绝对不齐，结合既往房颤病史，考虑阵发性房颤发作，需评估卒中风险。',
     'tags', JSON_ARRAY('房颤','心悸'), 'tone', 'orange',
     'differential_diagnoses', JSON_ARRAY('室上性心动过速','频发房性早搏'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '心电图', 'reason', '明确心律失常类型', 'priority', 'high'),
       JSON_OBJECT('exam_name', '心脏彩色多普勒超声', 'reason', '评估心房大小与心功能', 'priority', 'normal')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '美托洛尔', 'reason', '控制心室率', 'priority', 'high')))),
 '心房颤动（阵发性）',
 '["琥珀酸美托洛尔缓释片 23.75mg 每日一次口服", "抗凝治疗评估（CHA2DS2-VASc 评分）", "避免咖啡浓茶等刺激性饮品"]',
 JSON_OBJECT('chief_complaint', '反复心悸两周', 'present_illness', '两周来反复心悸，脉律绝对不齐，自测脉搏 90-110 次/分',
   'past_history', '心房颤动 3 年，慢性心力衰竭', 'allergies', '磺胺类药物过敏',
   'physical_examination', JSON_OBJECT('bp', '132/80 mmHg', 'hr', '98 次/分（绝对不齐）'),
   'preliminary_diagnosis', '心房颤动（阵发性）',
   'treatment_plan', JSON_ARRAY('控制心室率','卒中风险评估','抗凝治疗'), 'generated_at', '2026-06-20 09:40:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY(), 'recommendations', JSON_ARRAY('每日监测脉搏','规律作息，避免熬夜'),
   'requires_manual_review', false, 'reviewed_at', '2026-06-20 09:40:00'),
 JSON_OBJECT('interval_days', 30, 'watch_items', JSON_ARRAY('心率与节律','有无晕厥'),
   'lifestyle_advice', JSON_ARRAY('低盐饮食','戒烟限酒','保持情绪平稳'),
   'warning_symptoms', JSON_ARRAY('胸痛','晕厥','言语不清','肢体无力')),
 1, '2026-06-20 09:40:00'),

(2, 2,
 '血脂复查：总胆固醇 6.2 mmol/L，低密度脂蛋白 4.1 mmol/L，无特殊不适',
 JSON_ARRAY('血脂升高','复查'),
 JSON_ARRAY(
   JSON_OBJECT('id', 1, 'name', '高脂血症（混合型）', 'confidence', 85,
     'description', '总胆固醇及低密度脂蛋白升高，结合心衰房颤病史，需强化调脂治疗。',
     'tags', JSON_ARRAY('高脂血症'), 'tone', 'blue',
     'differential_diagnoses', JSON_ARRAY('继发性高脂血症（甲状腺功能减退等）'),
     'recommended_exams', JSON_ARRAY(
       JSON_OBJECT('exam_name', '肝功能全套', 'reason', '评估调脂药物安全性', 'priority', 'normal')),
     'recommended_drugs', JSON_ARRAY(
       JSON_OBJECT('drug_name', '阿托伐他汀', 'reason', '强化调脂、稳定斑块', 'priority', 'high')))),
 '高脂血症（混合型）',
 '["阿托伐他汀 20mg 每晚一次口服", "低脂饮食，控制动物内脏及油炸食品摄入", "3 个月后复查血脂、肝功能"]',
 JSON_OBJECT('chief_complaint', '血脂异常复查', 'present_illness', '复查血脂：总胆固醇 6.2 mmol/L，LDL-C 4.1 mmol/L',
   'past_history', '高脂血症，慢性心力衰竭，心房颤动', 'allergies', '磺胺类药物过敏',
   'physical_examination', JSON_OBJECT('bp', '128/78 mmHg'),
   'preliminary_diagnosis', '高脂血症（混合型）',
   'treatment_plan', JSON_ARRAY('强化调脂','饮食干预','定期复查'), 'generated_at', '2026-04-10 09:00:00'),
 JSON_OBJECT('passed', true, 'warnings', JSON_ARRAY('服药期间注意肌痛、乏力等不适'),
   'recommendations', JSON_ARRAY('低脂饮食','规律运动'), 'requires_manual_review', false,
   'reviewed_at', '2026-04-10 09:00:00'),
 JSON_OBJECT('interval_days', 90, 'watch_items', JSON_ARRAY('血脂水平','肝功能'),
   'lifestyle_advice', JSON_ARRAY('减少饱和脂肪摄入','增加膳食纤维'), 'warning_symptoms', JSON_ARRAY('肌痛','酱油色尿','黄疸')),
 1, '2026-04-10 09:00:00');
