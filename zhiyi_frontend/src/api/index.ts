import { generateMockDiagnosis, generateMockPreConsult, mockPreConsultations, mockUsers } from './mock'
import type { AdminDrugItem, AdminExamItem, AuditLogItem, DiagnosisResult, PatientListItem, PreConsultPrescriptionItem, PreConsultationItem, PreConsultationResult, UserProfile, UserRole } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
const wait = (ms = 350) => new Promise((resolve) => setTimeout(resolve, ms))

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('zhiyi-token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function _fetch<T = any>(url: string, options: RequestInit = {}): Promise<T> {
  const body = options.body
  const method = (options.method || 'GET').toUpperCase()
  const needContentType = body != null || ['POST', 'PUT', 'PATCH'].includes(method)
  const response = await fetch(url, {
    ...options,
    headers: {
      // 显式 UTF-8 编码，避免中文在部分代理/网关下被错误解码
      ...(needContentType ? { 'Content-Type': 'application/json; charset=utf-8' } : {}),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `请求失败: ${url}`)
  }
  return response.json() as Promise<T>
}

/** 演示登录 — 对接 POST /api/auth/demo-login?role=xxx */
export async function login(role: UserRole): Promise<UserProfile & { access_token?: string }> {
  if (USE_MOCK) {
    await wait()
    return mockUsers[role]
  }
  const data = await _fetch<UserProfile & { access_token?: string }>(
    `${API_BASE_URL}/auth/demo-login?role=${role}`,
    { method: 'POST' },
  )
  if (data.access_token) {
    localStorage.setItem('zhiyi-token', data.access_token)
  }
  return data
}

/** AI 诊断 — 对接 POST /api/diagnosis/assist */
export async function runDiagnosis(patientId: number, symptoms: string): Promise<DiagnosisResult> {
  if (USE_MOCK) {
    await wait()
    return generateMockDiagnosis(patientId, symptoms)
  }
  try {
    return await _fetch<DiagnosisResult>(`${API_BASE_URL}/diagnosis/assist`, {
      method: 'POST',
      body: JSON.stringify({ patient_id: patientId, symptoms }),
    })
  } catch (err) {
    // 开发/演示环境：后端不可用时降级到本地 mock，并给出明显提示
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn('[runDiagnosis] 后端不可用，使用本地模拟结果：', err)
      return { ...generateMockDiagnosis(patientId, symptoms), from_mock: true }
    }
    throw err
  }
}

/** 保存/确认病历 — 对接 POST /api/diagnosis/record */
export async function saveMedicalRecord(payload: {
  diagnosis_id: number
  patient_id: number
  doctor_id: number
  final_diagnosis?: string
  treatment_plan?: string
}) {
  return _fetch(`${API_BASE_URL}/diagnosis/record`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 诊断历史 — 对接 GET /api/diagnosis/history */
export async function getDiagnosisHistory(patientId?: number) {
  const query = patientId ? `?patient_id=${patientId}` : ''
  return _fetch(`${API_BASE_URL}/diagnosis/history${query}`)
}

/** 删除诊断记录 — 对接 DELETE /api/diagnosis/history/{diagnosis_id} */
export async function deleteDiagnosis(diagnosisId: number) {
  return _fetch(`${API_BASE_URL}/diagnosis/history/${diagnosisId}`, { method: 'DELETE' })
}

/** AI 医学问答 — 对接 POST /api/diagnosis/qa */
export async function askMedicalQuestion(question: string, patientId?: number) {
  return _fetch(`${API_BASE_URL}/diagnosis/qa`, {
    method: 'POST',
    body: JSON.stringify({ question, patient_id: patientId }),
  })
}

/** 创建订单 — 对接 POST /api/exams/orders 或 /api/drugs/orders */
export async function createOrder(type: 'exam' | 'drug', payload: Record<string, any>) {
  const url = `${API_BASE_URL}/${type === 'exam' ? 'exams' : 'drugs'}/orders`
  return _fetch(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 检查项目列表 — 对接 GET /api/exams/items */
export async function getExamItems(category?: string) {
  const query = category && category !== '全部项目' ? `?category=${encodeURIComponent(category)}` : ''
  return _fetch(`${API_BASE_URL}/exams/items${query}`)
}

/** 药品列表 — 对接 GET /api/drugs/items */
export async function getDrugs(needPrescription?: boolean) {
  const query = needPrescription !== undefined ? `?need_prescription=${needPrescription}` : ''
  return _fetch(`${API_BASE_URL}/drugs/items${query}`)
}

/** 检查购物车 — 对接 GET /api/exams/cart */
export async function getExamCart() {
  return _fetch(`${API_BASE_URL}/exams/cart`)
}

/** 药品购物车 — 对接 GET /api/drugs/cart */
export async function getDrugCart() {
  return _fetch(`${API_BASE_URL}/drugs/cart`)
}

/** 添加检查到购物车 */
export async function addExamToCart(examItemId: number, quantity = 1) {
  return _fetch(`${API_BASE_URL}/exams/cart`, {
    method: 'POST',
    body: JSON.stringify({ exam_item_id: examItemId, quantity }),
  })
}

/** 添加药品到购物车 */
export async function addDrugToCart(drugId: number, quantity = 1) {
  return _fetch(`${API_BASE_URL}/drugs/cart`, {
    method: 'POST',
    body: JSON.stringify({ drug_id: drugId, quantity }),
  })
}

/** 更新药品购物车数量 — 对接 PUT /api/drugs/cart/{drug_id} */
export async function updateDrugCart(drugId: number, quantity: number) {
  return _fetch(`${API_BASE_URL}/drugs/cart/${drugId}?quantity=${quantity}`, {
    method: 'PUT',
  })
}

/** 移除药品购物车项 — 对接 DELETE /api/drugs/cart/{drug_id} */
export async function removeDrugFromCart(drugId: number) {
  return _fetch(`${API_BASE_URL}/drugs/cart/${drugId}`, {
    method: 'DELETE',
  })
}

/** 管理后台告警列表 — 对接 GET /api/admin/alerts */
export async function getAlerts() {
  return _fetch(`${API_BASE_URL}/admin/alerts`)
}

/** 标记告警已处理 — 对接 POST /api/admin/alerts/{alert_id}/resolve */
export async function resolveAlert(alertId: string) {
  return _fetch(`${API_BASE_URL}/admin/alerts/${alertId}/resolve`, {
    method: 'POST',
  })
}

/** 导出报表 — 对接 GET /api/admin/export */
export async function exportReport(): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/admin/export`, {
    headers: authHeaders(),
  })
  if (!response.ok) throw new Error('导出失败')
  return response.blob()
}

/** 患者列表 — 对接 GET /api/profile/patients?search=xxx */
export async function getPatients(search?: string): Promise<PatientListItem[]> {
  const qs = search ? `?search=${encodeURIComponent(search)}` : ''
  return _fetch<PatientListItem[]>(`${API_BASE_URL}/profile/patients${qs}`)
}

/** 患者健康档案 — 对接 GET /api/profile/{patient_id} */
export async function getPatientProfile(patientId: number) {
  return _fetch(`${API_BASE_URL}/profile/${patientId}`)
}

/** 更新健康档案 — 对接 PUT /api/profile/{patient_id} */
export async function updatePatientProfile(patientId: number, payload: Record<string, any>) {
  return _fetch(`${API_BASE_URL}/profile/${patientId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

/** 我的检查订单 */
export async function getExamOrders() {
  return _fetch(`${API_BASE_URL}/exams/orders`)
}

/** 我的药品订单 */
export async function getDrugOrders() {
  return _fetch(`${API_BASE_URL}/drugs/orders`)
}

/** 药品订单物流状态 */
export async function getDrugOrderStatus(orderId: number) {
  return _fetch(`${API_BASE_URL}/drugs/orders/${orderId}/status`)
}

/** 支付订单 */
export async function payOrder(orderId: number, type: 'exam' | 'drug' = 'drug') {
  const body: Record<string, any> = { order_type: type }
  if (type === 'drug') body.payment_method = 'mock'
  return _fetch(`${API_BASE_URL}/${type === 'exam' ? 'exams' : 'drugs'}/orders/${orderId}/pay`, {
    method: 'POST',
    body: type === 'exam' ? undefined : JSON.stringify(body),
  })
}

/** 管理后台数据看板 */
export async function getDashboard() {
  return _fetch(`${API_BASE_URL}/admin/dashboard`)
}

/** 通用 GET 请求 */
export async function apiGet(path: string) {
  return _fetch(`${API_BASE_URL}${path}`)
}

/** 通用 POST 请求 */
export async function apiPost(path: string, body?: Record<string, any>) {
  return _fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
}

// =============================================================================
// 认证模块
// =============================================================================

/** 用户登出 — 对接 POST /api/auth/logout */
export async function logout() {
  return _fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST' })
}

/** 获取当前用户 — 对接 GET /api/auth/me */
export async function getCurrentUser() {
  return _fetch(`${API_BASE_URL}/auth/me`)
}

// =============================================================================
// 检查模块
// =============================================================================

/** 检查项目详情 — 对接 GET /api/exams/items/{id} */
export async function getExamItemDetail(itemId: number) {
  return _fetch(`${API_BASE_URL}/exams/items/${itemId}`)
}

/** 更新检查购物车数量 — 对接 PUT /api/exams/cart/{item_id} */
export async function updateExamCart(itemId: number, quantity: number) {
  return _fetch(`${API_BASE_URL}/exams/cart/${itemId}?quantity=${quantity}`, { method: 'PUT' })
}

/** 移除检查购物车项 — 对接 DELETE /api/exams/cart/{item_id} */
export async function removeExamFromCart(itemId: number) {
  return _fetch(`${API_BASE_URL}/exams/cart/${itemId}`, { method: 'DELETE' })
}

/** 清空检查购物车 — 对接 DELETE /api/exams/cart */
export async function clearExamCart() {
  return _fetch(`${API_BASE_URL}/exams/cart`, { method: 'DELETE' })
}

/** 取消检查预约 — 对接 POST /api/exams/orders/{id}/cancel */
export async function cancelExamOrder(orderId: number) {
  return _fetch(`${API_BASE_URL}/exams/orders/${orderId}/cancel`, { method: 'POST' })
}

/** 查看检查报告 — 对接 GET /api/exams/orders/{id}/report */
export async function getExamReport(orderId: number) {
  return _fetch(`${API_BASE_URL}/exams/orders/${orderId}/report`)
}

/** AI 解读检查报告 — 对接 GET /api/exams/appointments/{id}/interpret */
export async function getReportInterpretation(appointmentId: number) {
  return _fetch(`${API_BASE_URL}/exams/appointments/${appointmentId}/interpret`)
}

// =============================================================================
// 药品模块
// =============================================================================

/** 药品详情 — 对接 GET /api/drugs/items/{id} */
export async function getDrugDetail(drugId: number) {
  return _fetch(`${API_BASE_URL}/drugs/items/${drugId}`)
}

/** 药品订单详情 — 对接 GET /api/drugs/orders/{id} */
export async function getDrugOrderDetail(orderId: number) {
  return _fetch(`${API_BASE_URL}/drugs/orders/${orderId}`)
}

/** 清空药品购物车 — 对接 DELETE /api/drugs/cart */
export async function clearDrugCart() {
  return _fetch(`${API_BASE_URL}/drugs/cart`, { method: 'DELETE' })
}

// =============================================================================
// 物流模块
// =============================================================================

/** HTTP 物流状态查询 — 对接 GET /api/logistics/{order_id} */
export async function getLogisticsStatus(orderId: number) {
  return _fetch(`${API_BASE_URL}/logistics/${orderId}`)
}

// =============================================================================
// 管理后台模块
// =============================================================================

/** 创建医生 — 对接 POST /api/admin/doctors */
export async function createDoctor(payload: { username: string; phone: string; password: string; name: string; department?: string; hospital_id?: number }) {
  return _fetch(`${API_BASE_URL}/admin/doctors`, { method: 'POST', body: JSON.stringify({ ...payload, role: 'doctor' }) })
}

/** 删除医生 — 对接 DELETE /api/admin/doctors/{user_id} */
export async function deleteDoctor(userId: number) {
  return _fetch(`${API_BASE_URL}/admin/doctors/${userId}`, { method: 'DELETE' })
}

/** 管理后台药品列表 — 对接 GET /api/admin/drugs */
export async function getAdminDrugs(): Promise<AdminDrugItem[]> {
  return _fetch<AdminDrugItem[]>(`${API_BASE_URL}/admin/drugs`)
}

/** 管理后台检查项目列表 — 对接 GET /api/admin/exam-items */
export async function getAdminExamItems(): Promise<AdminExamItem[]> {
  return _fetch<AdminExamItem[]>(`${API_BASE_URL}/admin/exam-items`)
}

/** 新增药品 — 对接 POST /api/admin/drugs */
export async function createDrug(payload: { name: string; price: number; specification?: string; manufacturer?: string; stock?: number; need_prescription?: boolean }) {
  return _fetch(`${API_BASE_URL}/admin/drugs`, { method: 'POST', body: JSON.stringify(payload) })
}

/** 更新药品 — 对接 PUT /api/admin/drugs/{drug_id} */
export async function updateDrug(drugId: number, payload: Record<string, any>) {
  return _fetch(`${API_BASE_URL}/admin/drugs/${drugId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

/** 下架药品 — 对接 DELETE /api/admin/drugs/{drug_id} */
export async function deleteDrug(drugId: number) {
  return _fetch(`${API_BASE_URL}/admin/drugs/${drugId}`, { method: 'DELETE' })
}

/** 新增检查项目 — 对接 POST /api/admin/exam-items */
export async function createExamItem(payload: { name: string; price: number; category?: string; description?: string }) {
  return _fetch(`${API_BASE_URL}/admin/exam-items`, { method: 'POST', body: JSON.stringify(payload) })
}

/** 更新检查项目 — 对接 PUT /api/admin/exam-items/{item_id} */
export async function updateExamItem(itemId: number, payload: Record<string, any>) {
  return _fetch(`${API_BASE_URL}/admin/exam-items/${itemId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

/** 下架检查项目 — 对接 DELETE /api/admin/exam-items/{item_id} */
export async function deleteExamItem(itemId: number) {
  return _fetch(`${API_BASE_URL}/admin/exam-items/${itemId}`, { method: 'DELETE' })
}

/** 管理后台订单列表 — 对接 GET /api/admin/orders */
export async function getAdminOrders(deliveryStatus?: string) {
  const query = deliveryStatus ? `?delivery_status=${deliveryStatus}` : ''
  return _fetch(`${API_BASE_URL}/admin/orders${query}`)
}

/** 管理员发货 — 对接 POST /api/admin/orders/{order_id}/ship */
export async function shipAdminOrder(orderId: number) {
  return _fetch(`${API_BASE_URL}/admin/orders/${orderId}/ship`, { method: 'POST' })
}

/** 操作日志 — 对接 GET /api/admin/audit-logs */
export async function getAuditLogs(action?: string, limit = 100): Promise<AuditLogItem[]> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (action) qs.set('action', action)
  return _fetch<AuditLogItem[]>(`${API_BASE_URL}/admin/audit-logs?${qs.toString()}`)
}

// =============================================================================
// 支付模块
// =============================================================================

/** 创建支付宝支付 — 对接 POST /api/pay/alipay/create */
export async function createAlipayPayment(orderId: number, orderType: 'exam' | 'drug', amount: number) {
  return _fetch(`${API_BASE_URL}/pay/alipay/create`, {
    method: 'POST',
    body: JSON.stringify({ order_id: orderId, order_type: orderType, amount }),
  })
}

// =============================================================================
// 健康档案
// =============================================================================

/** 患者就诊记录 — 对接 GET /api/profile/{patient_id}/visits */
export async function getPatientVisits(patientId: number) {
  return _fetch(`${API_BASE_URL}/profile/${patientId}/visits`)
}

/** 患者健康趋势 — 对接 GET /api/profile/{patient_id}/trend */
export async function getPatientTrend(patientId: number) {
  return _fetch(`${API_BASE_URL}/profile/${patientId}/trend`)
}

// =============================================================================
// 智能助手（Qwen3.7-max / RAG）
// =============================================================================

export interface PatientAssistResult {
  answer: string
  related_diseases?: Array<{ name?: string; score?: number; description?: string }>
  use_ai: boolean
  profile_summary?: string
  disclaimer?: string
}

/** 患者智能助手 — 对接 POST /api/diagnosis/patient-assist */
export async function patientAssist(question: string): Promise<PatientAssistResult> {
  return _fetch<PatientAssistResult>(`${API_BASE_URL}/diagnosis/patient-assist`, {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

/** AI 预问诊（健康参考，不落正式就诊记录）— 对接 POST /api/diagnosis/patient-consult */
export async function patientConsult(symptoms: string): Promise<PreConsultationResult> {
  if (USE_MOCK) {
    await wait()
    return generateMockPreConsult(1, symptoms)
  }
  return _fetch<PreConsultationResult>(`${API_BASE_URL}/diagnosis/patient-consult`, {
    method: 'POST',
    body: JSON.stringify({ symptoms }),
  })
}

/** 医生端预问诊列表 — 对接 GET /api/diagnosis/pre-consultations */
export async function getPreConsultations(status?: string): Promise<PreConsultationItem[]> {
  if (USE_MOCK) {
    await wait()
    return status ? mockPreConsultations.filter((i) => i.status === status) : mockPreConsultations
  }
  const qs = status ? `?status=${status}` : ''
  return _fetch<PreConsultationItem[]>(`${API_BASE_URL}/diagnosis/pre-consultations${qs}`)
}

/** 预问诊详情 — 对接 GET /api/diagnosis/pre-consultations/{id} */
export async function getPreConsultationDetail(id: number): Promise<PreConsultationResult> {
  if (USE_MOCK) {
    await wait()
    const item = mockPreConsultations.find((i) => i.id === id) || mockPreConsultations[0]
    return generateMockPreConsult(item?.patient_id || 1, item?.symptoms || '')
  }
  return _fetch<PreConsultationResult>(`${API_BASE_URL}/diagnosis/pre-consultations/${id}`)
}

/** 医生确认预问诊并生成正式就诊 — 对接 POST /api/diagnosis/pre-consultations/{id}/confirm */
export async function confirmPreConsultation(
  id: number,
  payload: {
    final_diagnosis?: string
    treatment_plan?: string
    prescription_items?: PreConsultPrescriptionItem[]
  },
): Promise<DiagnosisResult> {
  if (USE_MOCK) {
    await wait()
    const item = mockPreConsultations.find((i) => i.id === id)
    const result = generateMockDiagnosis(item?.patient_id || 1, item?.symptoms || '')
    return { ...result, primary_diagnosis: payload.final_diagnosis || result.primary_diagnosis }
  }
  return _fetch<DiagnosisResult>(`${API_BASE_URL}/diagnosis/pre-consultations/${id}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export { API_BASE_URL }
