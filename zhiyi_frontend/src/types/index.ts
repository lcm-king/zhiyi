import type { Component } from 'vue'

export type UserRole = 'doctor' | 'patient' | 'admin'

export interface UserProfile {
  id: number
  name: string
  role: UserRole
  title: string
  organization: string
  avatar: string
}

export interface PatientListItem {
  id: number
  user_id: number
  name: string
  gender: string
  birth_date: string
  phone: string
  is_active: boolean
}

export interface NavItem {
  label: string
  icon: Component
  to: string
}

export interface Metric {
  label: string
  value: string
  delta: string
  trend: 'up' | 'down' | 'neutral'
  icon: string
  tone: 'blue' | 'green' | 'amber' | 'red' | 'violet'
}

export interface DiagnosisSuggestion {
  id: number
  name: string
  confidence: number
  description: string
  tags: string[]
  tone: 'blue' | 'amber' | 'violet' | 'emerald' | 'rose'
  is_primary?: boolean
  differential_diagnoses?: string[]
  recommended_exams?: ExamRecommendation[]
  recommended_drugs?: DrugRecommendation[]
}

export interface ExamRecommendation {
  exam_item_id?: number
  exam_name: string
  reason: string
  priority: 'high' | 'normal'
}

export interface DrugRecommendation {
  drug_id?: number
  drug_name: string
  reason: string
  warning?: string
}

export interface MedicationReview {
  passed: boolean
  warnings: string[]
  recommendations: string[]
  requires_manual_review: boolean
  allergy_alert?: boolean
  reviewed_at?: string
}

export interface MedicalRecord {
  chief_complaint?: string
  present_illness?: string
  past_history?: string
  allergies?: string
  physical_examination?: {
    general?: string
    vital_signs?: string
    focused_exam?: string[]
  }
  differential_diagnosis?: string[]
  preliminary_diagnosis?: string
  treatment_plan?: string[]
  medication_review?: MedicationReview
  generated_at?: string
}

export interface FollowUpPlan {
  interval_days: number
  watch_items: string[]
  lifestyle_advice: string[]
  warning_symptoms: string[]
}

export interface DiagnosisResult {
  id: number
  patient_id: number
  symptoms: string
  extracted_symptoms?: string[]
  suggestions: DiagnosisSuggestion[]
  primary_diagnosis?: string
  primary_reasoning?: string
  medication_review?: MedicationReview
  medical_record?: MedicalRecord
  follow_up_plan?: FollowUpPlan
  agent_logs?: string[]
  generated_at: string
  from_mock?: boolean
  use_ai?: boolean
}

export interface PreConsultationResult extends DiagnosisResult {
  status: 'pending' | 'confirmed' | 'dismissed'
  urgency: 'low' | 'medium' | 'high'
  suggested_department: string
  is_pre_consultation: true
}

export interface PreConsultationItem {
  id: number
  patient_id: number
  patient_name: string
  symptoms: string
  primary_diagnosis: string
  urgency: 'low' | 'medium' | 'high'
  suggested_department: string
  status: 'pending' | 'confirmed' | 'dismissed'
  suggestions_count: number
  created_at: string
}

export interface PreConsultPrescriptionItem {
  drug_id: number
  drug_name?: string
  dosage: string
  quantity: number
  instructions?: string
}

export interface ExamItem {
  id: number
  name: string
  category: string
  hospital: string
  price: number
  duration: string
  availability: string
  icon: string
}

export interface Medicine {
  id: number
  name: string
  specification: string
  price: number
  stock: number
  prescription: boolean
  badge: string
}

export interface AdminDrugItem {
  id: number
  name: string
  specification?: string | null
  manufacturer?: string | null
  price: number
  stock: number
  need_prescription: boolean
  need_cold_chain: boolean
  is_active: boolean
}

export interface AdminExamItem {
  id: number
  name: string
  category?: string | null
  price: number
  description?: string | null
  is_active: boolean
}

export interface AuditLogItem {
  id: number
  user_id: number | null
  username: string
  action: string
  resource: string | null
  resource_id: number | null
  detail: Record<string, any> | null
  ip_address: string | null
  created_at: string
}

export interface LogisticsPoint {
  time: string
  location: string
  status: string
  temperature?: string
}
