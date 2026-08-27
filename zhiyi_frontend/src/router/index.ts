import { createRouter, createWebHistory } from 'vue-router'
import type { UserRole } from '@/types'
import LoginView from '@/views/auth/LoginView.vue'
import AppShell from '@/layouts/AppShell.vue'
import DoctorDiagnosisView from '@/views/doctor/DoctorDiagnosisView.vue'
import PreConsultationQueueView from '@/views/doctor/PreConsultationQueueView.vue'
import PatientDetailView from '@/views/doctor/PatientDetailView.vue'
import PrescriptionReviewView from '@/views/doctor/PrescriptionReviewView.vue'
import PatientHealthView from '@/views/patient/PatientHealthView.vue'
import ExamPharmacyView from '@/views/patient/ExamPharmacyView.vue'
import PatientOrdersView from '@/views/patient/PatientOrdersView.vue'
import ExamReportView from '@/views/patient/ExamReportView.vue'
import PatientAssistantView from '@/views/patient/PatientAssistantView.vue'
import AdminOverviewView from '@/views/admin/AdminOverviewView.vue'
import DoctorManagementView from '@/views/admin/DoctorManagementView.vue'
import CatalogManagementView from '@/views/admin/CatalogManagementView.vue'
import OrderShipmentView from '@/views/admin/OrderShipmentView.vue'
import AuditLogView from '@/views/admin/AuditLogView.vue'
import PatientRecordsView from '@/views/doctor/PatientRecordsView.vue'
import KnowledgeBaseView from '@/views/doctor/KnowledgeBaseView.vue'
import ExamReportManageView from '@/views/doctor/ExamReportManageView.vue'

export const roleHome: Record<UserRole, string> = {
  doctor: '/doctor/diagnosis',
  patient: '/patient/health',
  admin: '/admin/overview',
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/doctor/diagnosis' },
    { path: '/login', component: LoginView, meta: { public: true, title: '登录' } },
    {
      path: '/', component: AppShell,
      children: [
        { path: 'doctor/diagnosis', component: DoctorDiagnosisView, meta: { role: 'doctor', title: '智能诊疗' } },
        { path: 'doctor/pre-consults', component: PreConsultationQueueView, meta: { role: 'doctor', title: '待确认问诊' } },
        { path: 'doctor/records', component: PatientRecordsView, meta: { role: 'doctor', title: '患者档案' } },
        { path: 'doctor/records/:id', component: PatientDetailView, meta: { role: 'doctor', title: '患者详情' } },
        { path: 'doctor/prescriptions', component: PrescriptionReviewView, meta: { role: 'doctor', title: '处方审核' } },
        { path: 'doctor/reports', component: ExamReportManageView, meta: { role: 'doctor', title: '检查报告' } },
        { path: 'doctor/knowledge', component: KnowledgeBaseView, meta: { role: 'doctor', title: '医学知识库' } },
        { path: 'patient/health', component: PatientHealthView, meta: { role: 'patient', title: '健康档案' } },
        { path: 'patient/exams', component: ExamPharmacyView, meta: { role: 'patient', title: '检查与购药' } },
        { path: 'patient/orders', component: PatientOrdersView, meta: { role: 'patient', title: '订单与物流' } },
        { path: 'patient/reports', component: ExamReportView, meta: { role: 'patient', title: '检查报告' } },
        { path: 'patient/assistant', component: PatientAssistantView, meta: { role: 'patient', title: '智能助手' } },
        { path: 'admin/overview', component: AdminOverviewView, meta: { role: 'admin', title: '运营总览' } },
        { path: 'admin/doctors', component: DoctorManagementView, meta: { role: 'admin', title: '医生管理' } },
        { path: 'admin/catalog', component: CatalogManagementView, meta: { role: 'admin', title: '药品与检查' } },
        { path: 'admin/orders', component: OrderShipmentView, meta: { role: 'admin', title: '订单发货' } },
        { path: 'admin/audit-logs', component: AuditLogView, meta: { role: 'admin', title: '操作日志' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/doctor/diagnosis' },
  ],
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  const storedRole = localStorage.getItem('zhiyi-role') as UserRole | null
  if (!storedRole || !roleHome[storedRole]) return '/login'
  if (to.meta.role && to.meta.role !== storedRole) return roleHome[storedRole]
  return true
})

export default router
