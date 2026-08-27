import type { DiagnosisResult, DiagnosisSuggestion, PreConsultationItem, PreConsultationResult, UserProfile } from '@/types'
export const mockUsers: Record<string, UserProfile> = {
  doctor: { id: 101, name: '郑经纬', role: 'doctor', title: '主治医师', organization: '长沙市岳麓区社区卫生服务中心', avatar: '郑' },
  patient: { id: 201, name: '郑经纬', role: 'patient', title: '患者', organization: '湖南省长沙市', avatar: '郑' },
  admin: { id: 501, name: 'admin_li', role: 'admin', title: '平台管理员', organization: '智医运营中心', avatar: 'a' },
}

export const diagnosisSuggestions: DiagnosisSuggestion[] = [
  { id: 1, name: '慢性心力衰竭（CHF）加重期', confidence: 94, description: '符合夜间阵发性呼吸困难、活动耐量下降及既往高血压史特征。', tags: ['建议心电图', 'NT-proBNP'], tone: 'blue' },
  { id: 2, name: '慢性阻塞性肺疾病急性加重', confidence: 68, description: '与持续干咳、呼吸困难及潜在吸烟史相关联，建议排除感染因素。', tags: ['肺功能测试', '胸部 X 光'], tone: 'amber' },
  { id: 3, name: '缺血性心脏病待排', confidence: 42, description: '症状存在心肌缺血相关性，需结合心电图与心肌酶谱进一步判断。', tags: ['肌钙蛋白', '心脏彩超'], tone: 'violet' },
]


// 模拟诊断：根据症状关键词返回不同结果（仅用于开发/演示 fallback）
const diseaseRules: Array<{
  keywords: string[]
  name: string
  description: string
  tags: string[]
  exams: string[]
  drugs: string[]
  tone: 'blue' | 'amber' | 'violet' | 'emerald' | 'rose'
}> = [
  {
    keywords: ['胸闷', '气促', '呼吸困难', '夜间', '平卧', '水肿', '心衰'],
    name: '慢性心力衰竭',
    description: '患者出现劳力性呼吸困难、夜间阵发性呼吸困难及下肢水肿表现，需考虑慢性心力衰竭可能。',
    tags: ['心脏超声', 'BNP'],
    exams: ['心脏超声', 'BNP/NT-proBNP', '胸部 X 线', '心电图'],
    drugs: ['呋塞米', '螺内酯', '沙库巴曲缬沙坦'],
    tone: 'blue',
  },
  {
    keywords: ['咳嗽', '咳痰', '发热', '肺炎', '胸痛', '呼吸急促'],
    name: '社区获得性肺炎',
    description: '急性起病伴发热、咳嗽咳痰及胸痛，需警惕肺部感染。',
    tags: ['胸部 CT', '血常规'],
    exams: ['胸部 X 线/CT', '血常规+CRP', '痰培养'],
    drugs: ['阿莫西林克拉维酸', '左氧氟沙星'],
    tone: 'amber',
  },
  {
    keywords: ['多饮', '多尿', '多食', '体重下降', '血糖', '糖尿病'],
    name: '2 型糖尿病',
    description: '典型“三多一少”症状，需完善血糖及糖化血红蛋白检查。',
    tags: ['空腹血糖', '糖化血红蛋白'],
    exams: ['空腹血糖', '糖化血红蛋白', '尿微量白蛋白', '血脂全套'],
    drugs: ['二甲双胍', '阿卡波糖', '格列美脲'],
    tone: 'violet',
  },
  {
    keywords: ['腹痛', '腹泻', '呕吐', '恶心', '胃肠炎'],
    name: '急性胃肠炎',
    description: '以腹痛、腹泻、呕吐为主要表现，多由感染或饮食不当引起。',
    tags: ['便常规', '血常规'],
    exams: ['血常规', '便常规+潜血', '电解质'],
    drugs: ['蒙脱石散', '口服补液盐', '益生菌'],
    tone: 'emerald',
  },
  {
    keywords: ['头痛', '头晕', '高血压', '血压升高', '耳鸣'],
    name: '原发性高血压',
    description: '常见头晕头痛、血压升高，需监测血压并排除继发性因素。',
    tags: ['动态血压', '心电图'],
    exams: ['动态血压监测', '心电图', '肾功能+电解质', '眼底检查'],
    drugs: ['氨氯地平', '厄贝沙坦', '美托洛尔'],
    tone: 'rose',
  },
]

function matchDiseases(symptoms: string): typeof diseaseRules {
  const matched = diseaseRules
    .map((d) => ({
      ...d,
      score: d.keywords.reduce((sum, kw) => sum + (symptoms.includes(kw) ? 1 : 0), 0),
    }))
    .filter((d) => d.score > 0)
    .sort((a, b) => b.score - a.score)
  if (matched.length === 0) {
    return diseaseRules.slice(0, 3)
  }
  return matched.slice(0, 5)
}

export function generateMockDiagnosis(patientId: number, symptoms: string): DiagnosisResult {
  const matched = matchDiseases(symptoms)
  const suggestions: DiagnosisSuggestion[] = matched.map((d, idx) => ({
    id: idx + 1,
    name: d.name,
    confidence: Math.max(20, 95 - idx * 18),
    description: d.description,
    tags: d.tags,
    tone: d.tone,
    differential_diagnoses: matched.filter((_, i) => i !== idx).map((x) => x.name).slice(0, 3),
    recommended_exams: d.exams.map((name) => ({ exam_name: name, reason: '辅助诊断与病情评估', priority: 'high' as const })),
    recommended_drugs: d.drugs.map((name) => ({ drug_name: name, reason: '对症治疗' })),
  }))

  return {
    id: Date.now(),
    patient_id: patientId,
    symptoms,
    extracted_symptoms: symptoms.split(/[，,。;；\s、]+/).filter(Boolean).slice(0, 6),
    suggestions,
    medication_review: {
      passed: true,
      warnings: [],
      recommendations: ['请结合患者实际过敏史与肝肾功能调整用药'],
      requires_manual_review: false,
      allergy_alert: false,
      reviewed_at: new Date().toISOString(),
    },
    medical_record: {
      chief_complaint: symptoms.slice(0, 60),
      present_illness: `患者因「${symptoms.slice(0, 60)}」就诊。`,
      past_history: '高血压、2型糖尿病',
      allergies: '青霉素',
      physical_examination: {
        general: '神清，精神尚可',
        vital_signs: '待测量',
        focused_exam: ['血压监测', '心肺听诊', '腹部触诊'],
      },
      differential_diagnosis: matched.slice(1).map((d) => d.name).slice(0, 3),
      preliminary_diagnosis: `${matched[0].name}（AI 辅助诊断）`,
      treatment_plan: matched[0].drugs,
      generated_at: new Date().toISOString(),
    },
    follow_up_plan: {
      interval_days: 7,
      watch_items: ['症状变化', '用药反应', '生命体征'],
      lifestyle_advice: ['低盐低脂饮食', '适量活动', '避免受凉'],
      warning_symptoms: ['出现胸痛、意识改变、呼吸困难加重等情况立即就医'],
    },
    agent_logs: ['[症状分析] 提取关键症状', '[鉴别诊断] 匹配医学知识库', '[诊断建议] 生成推荐方案', '[用药审核] 完成安全性检查', '[病历生成] 结构化病历已生成'],
    generated_at: new Date().toISOString(),
    from_mock: true,
  }
}

export function generateMockPreConsult(patientId: number, symptoms: string): PreConsultationResult {
  const base = generateMockDiagnosis(patientId, symptoms)
  return {
    ...base,
    status: 'pending',
    urgency: 'medium',
    suggested_department: '全科 / 内科',
    is_pre_consultation: true,
  }
}

export const mockPreConsultations: PreConsultationItem[] = [
  {
    id: 1,
    patient_id: 201,
    patient_name: '陈建国',
    symptoms: '最近三天反复头痛，伴发热 38 度，咳嗽咳痰，乏力',
    primary_diagnosis: '急性支气管炎',
    urgency: 'medium',
    suggested_department: '全科 / 内科',
    status: 'pending',
    suggestions_count: 3,
    created_at: '2026-08-14 08:30',
  },
  {
    id: 2,
    patient_id: 202,
    patient_name: '李秀英',
    symptoms: '胸闷气促一周，夜间加重，下肢轻度浮肿',
    primary_diagnosis: '慢性心力衰竭（待查）',
    urgency: 'high',
    suggested_department: '心血管内科',
    status: 'pending',
    suggestions_count: 3,
    created_at: '2026-08-14 08:12',
  },
]
