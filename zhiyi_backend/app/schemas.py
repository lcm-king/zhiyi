"""
智医 (ZhiYi) — Pydantic 数据模型（Schema）
基层医疗AI辅助诊疗平台

定义所有 API 的请求体 / 响应体结构，基于 Pydantic v2。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# =============================================================================
# 认证相关
# =============================================================================

class RegisterRequest(BaseModel):
    """用户注册请求。"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    phone: str = Field(..., pattern=r"^1\d{10}$", description="11 位手机号")
    password: str = Field(..., min_length=8, max_length=20, description="8-20 位密码")
    role: str = Field(..., pattern=r"^(doctor|patient|admin)$", description="角色")


class LoginRequest(BaseModel):
    """用户登录请求。"""
    phone: str = Field(..., pattern=r"^1\d{10}$", description="手机号")
    password: str = Field(..., description="登录密码")


class TokenResponse(BaseModel):
    """JWT Token 响应。"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")
    user_id: int = Field(default=0, description="用户ID")
    name: str = Field(default="", description="用户名")
    role: str = Field(default="patient", description="角色")


class UserProfileResponse(BaseModel):
    """用户基本信息响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    phone: str
    role: str
    is_active: bool
    created_at: datetime


# =============================================================================
# 诊断相关
# =============================================================================

class DiagnosisRequest(BaseModel):
    """AI 辅助诊断请求。"""
    patient_id: int = Field(..., description="患者 ID")
    symptoms: str = Field(..., min_length=5, max_length=2000, description="症状描述")


class PatientConsultRequest(BaseModel):
    """患者在线问诊请求。"""
    symptoms: str = Field(..., min_length=5, max_length=2000, description="症状描述")


class MedicationReview(BaseModel):
    """用药审核结果。"""
    passed: bool = Field(default=True, description="是否通过审核")
    warnings: list[str] = Field(default_factory=list, description="警告信息")
    recommendations: list[str] = Field(default_factory=list, description="用药建议")
    requires_manual_review: bool = Field(default=False, description="是否需要人工复核")
    reviewed_at: str = Field(default="", description="审核时间")


class MedicalRecord(BaseModel):
    """结构化电子病历。"""
    chief_complaint: str = ""
    present_illness: str = ""
    past_history: str = ""
    allergies: str = ""
    physical_examination: dict[str, Any] = Field(default_factory=dict)
    preliminary_diagnosis: str = ""
    treatment_plan: list[str] = Field(default_factory=list)
    generated_at: str = ""


class FollowUpPlan(BaseModel):
    """随访/复诊计划。"""
    interval_days: int = Field(..., ge=0, description="建议复诊间隔（天）")
    watch_items: list[str] = Field(default_factory=list, description="需观察的症状/指标")
    lifestyle_advice: list[str] = Field(default_factory=list, description="生活方式建议")
    warning_symptoms: list[str] = Field(default_factory=list, description="需立即就医的警示症状")


class ExamRecommendation(BaseModel):
    """检查项目推荐（可一键加入检查预约）。"""
    exam_name: str = Field(..., description="检查名称")
    reason: str = Field(..., description="推荐理由")
    priority: str = Field(default="normal", description="优先级 high/normal")


class DrugRecommendation(BaseModel):
    """药品推荐（可一键加入药品购物车）。"""
    drug_name: str = Field(..., description="药品名称")
    reason: str = Field(..., description="推荐理由")
    warning: Optional[str] = Field(None, description="特殊用药提示")


class DiagnosisSuggestion(BaseModel):
    """诊断建议条目。"""
    id: int
    name: str = Field(..., description="疑似疾病名称")
    confidence: int = Field(..., ge=0, le=100, description="置信度 0-100")
    description: str = Field(..., description="诊断分析说明")
    tags: list[str] = Field(default_factory=list, description="关联标签")
    tone: str = Field(default="blue", description="前端颜色主题")
    is_primary: bool = Field(default=False, description="是否为 LLM 首选诊断")
    differential_diagnoses: list[str] = Field(default_factory=list, description="鉴别诊断列表")
    recommended_exams: list[ExamRecommendation] = Field(default_factory=list, description="推荐检查")
    recommended_drugs: list[DrugRecommendation] = Field(default_factory=list, description="推荐药品")


class DiagnosisResponse(BaseModel):
    """AI 辅助诊断响应。"""
    id: int = Field(..., description="诊断记录 ID")
    patient_id: int
    symptoms: str
    extracted_symptoms: list[str] = Field(default_factory=list, description="AI 提取的关键症状")
    suggestions: list[DiagnosisSuggestion] = Field(default_factory=list)
    primary_diagnosis: str = Field(default="", description="LLM 首选诊断")
    primary_reasoning: str = Field(default="", description="LLM 首选诊断推理依据")
    medication_review: MedicationReview = Field(default_factory=MedicationReview)
    medical_record: MedicalRecord = Field(default_factory=MedicalRecord)
    follow_up_plan: FollowUpPlan = Field(default_factory=FollowUpPlan)
    agent_logs: list[str] = Field(default_factory=list, description="Agent 工作流日志")
    generated_at: str = Field(..., description="生成时间")
    use_ai: bool = Field(default=False, description="是否使用了 Qwen 等大模型进行推理（false 表示使用本地规则引擎/知识库检索）")


class PreConsultationResponse(BaseModel):
    """AI 预问诊响应 — 仅供健康参考，不构成正式诊断。"""
    id: int = Field(..., description="预问诊记录 ID")
    patient_id: int
    symptoms: str
    extracted_symptoms: list[str] = Field(default_factory=list, description="AI 提取的关键症状")
    suggestions: list[DiagnosisSuggestion] = Field(default_factory=list)
    primary_diagnosis: str = Field(default="", description="AI 首选诊断（仅供参考）")
    primary_reasoning: str = Field(default="", description="AI 首选诊断推理依据")
    medication_review: MedicationReview = Field(default_factory=MedicationReview)
    medical_record: MedicalRecord = Field(default_factory=MedicalRecord)
    follow_up_plan: FollowUpPlan = Field(default_factory=FollowUpPlan)
    agent_logs: list[str] = Field(default_factory=list, description="Agent 工作流日志")
    generated_at: str = Field(..., description="生成时间")
    use_ai: bool = Field(default=False, description="是否使用大模型推理")
    status: str = Field(default="pending", description="pending/confirmed/dismissed")
    urgency: str = Field(default="low", description="紧急程度 low/medium/high")
    suggested_department: str = Field(default="", description="建议就诊科室")
    is_pre_consultation: bool = Field(default=True, description="是否为预问诊记录")


class PreConsultationListItem(BaseModel):
    """医生端待确认预问诊列表项。"""
    id: int
    patient_id: int
    patient_name: str = Field(default="", description="患者姓名")
    symptoms: str
    primary_diagnosis: str = Field(default="", description="AI 首选诊断")
    urgency: str = Field(default="low", description="紧急程度")
    suggested_department: str = Field(default="", description="建议就诊科室")
    status: str = Field(default="pending", description="pending/confirmed/dismissed")
    suggestions_count: int = Field(default=0, description="AI 建议条数")
    created_at: str = Field(default="", description="创建时间")


class PreConsultConfirmRequest(BaseModel):
    """医生确认预问诊并转为正式就诊的请求。"""
    final_diagnosis: Optional[str] = Field(None, description="最终确诊，缺省使用 AI 首选诊断")
    treatment_plan: Optional[str] = Field(None, description="治疗方案")
    prescription_items: list[PrescriptionItemCreate] = Field(default_factory=list, description="需要开具的处方药")


class MedicalRecordRequest(BaseModel):
    """病历生成/更新请求。"""
    diagnosis_id: int = Field(..., description="诊断记录 ID")
    patient_id: int = Field(..., description="患者 ID")
    doctor_id: int = Field(..., description="医生 ID")
    final_diagnosis: Optional[str] = Field(None, description="最终确诊")
    treatment_plan: Optional[str] = Field(None, description="治疗方案")


class DiagnosisQARequest(BaseModel):
    """医学知识库问答请求。"""
    question: str = Field(..., min_length=2, max_length=1000, description="医学问题")
    patient_id: Optional[int] = Field(None, description="关联患者 ID（可选，用于个性化）")


class DiagnosisQAResponse(BaseModel):
    """医学知识库问答响应。"""
    answer: str = Field(..., description="回答内容")
    sources: list[str] = Field(default_factory=list, description="引用疾病名称")
    related_diseases: list[dict[str, Any]] = Field(default_factory=list, description="相关疾病")
    disclaimer: str = Field(default="本回答仅供参考，不能替代专业医疗建议。", description="免责声明")


class PatientAssistRequest(BaseModel):
    """患者智能助手请求。"""
    question: str = Field(..., min_length=2, max_length=1000, description="健康咨询问题")


class PatientAssistResponse(BaseModel):
    """患者智能助手响应。"""
    answer: str = Field(..., description="回答内容")
    related_diseases: list[dict[str, Any]] = Field(default_factory=list, description="相关疾病")
    use_ai: bool = Field(False, description="是否使用了真实大模型推理")
    profile_summary: str = Field(default="", description="本次咨询结合的患者档案摘要")
    disclaimer: str = Field(default="本回答由 AI 结合知识库生成，仅供参考，不能替代医生面诊。如有紧急不适请立即就医。", description="免责声明")


class MedicalRecordResponse(BaseModel):
    """病历响应。"""
    id: int
    patient_id: int
    doctor_id: int
    chief_complaint: str = Field(default="", alias="symptoms")
    present_illness: str = ""
    physical_exam: str = ""
    final_diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    medical_record: MedicalRecord = Field(default_factory=MedicalRecord)
    created_at: str = ""


# =============================================================================
# 检查预约相关
# =============================================================================

class ExamItemResponse(BaseModel):
    """检查项目。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str] = None
    price: float
    description: Optional[str] = None
    is_active: bool


class ExamCartItem(BaseModel):
    """检查购物车条目。"""
    exam_item_id: int = Field(..., description="检查项目 ID")
    quantity: int = Field(default=1, ge=1)


class ExamOrderRequest(BaseModel):
    """创建检查订单请求。"""
    items: list[ExamCartItem] = Field(..., min_length=1)
    hospital_id: int = Field(..., description="检查医院 ID")
    appointment_time: datetime = Field(..., description="预约时间")
    patient_id: Optional[int] = Field(None, description="患者 ID（医生代下单时必填）")


class ExamOrderResponse(BaseModel):
    """检查订单响应。"""
    order_id: int
    order_no: str
    patient_id: int
    items: list[ExamItemResponse]
    total_price: float
    status: str
    appointment_time: datetime
    created_at: datetime


# =============================================================================
# 药品与订单相关
# =============================================================================

class DrugItemResponse(BaseModel):
    """药品项目。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    specification: Optional[str] = None
    manufacturer: Optional[str] = None
    price: float
    stock: int
    need_prescription: bool
    need_cold_chain: bool = False
    is_active: bool


class DrugCartItem(BaseModel):
    """药品购物车条目。"""
    drug_id: int = Field(..., description="药品 ID")
    quantity: int = Field(default=1, ge=1, description="数量")


class PrescriptionItemCreate(BaseModel):
    """处方项目创建。"""
    drug_id: int = Field(..., description="药品 ID")
    dosage: str = Field(..., description="用法用量")
    quantity: int = Field(..., ge=1, description="数量")
    duration_days: Optional[int] = Field(None, description="用药天数")
    instructions: Optional[str] = Field(None, description="注意事项")


class PrescriptionCreate(BaseModel):
    """医生开具处方请求。"""
    patient_id: int = Field(..., description="患者 ID")
    diagnosis_id: Optional[int] = Field(None, description="关联诊断记录 ID")
    items: list[PrescriptionItemCreate] = Field(..., min_length=1)


class PrescriptionItemResponse(BaseModel):
    """处方项目响应。"""
    id: int
    drug_id: int
    drug_name: str
    specification: Optional[str]
    dosage: str
    quantity: int
    duration_days: Optional[int]
    instructions: Optional[str]


class PrescriptionResponse(BaseModel):
    """处方响应。"""
    id: int
    patient_id: int
    doctor_id: int
    diagnosis_id: Optional[int]
    status: str
    items: list[PrescriptionItemResponse]
    created_at: datetime


class DrugOrderRequest(BaseModel):
    """创建药品订单请求。"""
    items: list[DrugCartItem] = Field(..., min_length=1)
    address: str = Field(..., min_length=5, max_length=255, description="收货地址")
    prescription_id: Optional[int] = Field(None, description="关联处方 ID")
    patient_id: Optional[int] = Field(None, description="患者 ID（医生代下单时必填）")


class DrugOrderItemResponse(BaseModel):
    """药品订单项响应。"""
    id: int
    drug_id: int
    drug_name: str
    specification: Optional[str]
    quantity: int
    unit_price: float
    subtotal: float
    need_cold_chain: bool = False
    dosage: str = Field(default="", description="用法用量（来自关联处方）")
    instructions: str = Field(default="", description="用药注意事项（来自关联处方）")


class DrugOrderResponse(BaseModel):
    """药品订单响应。"""
    id: int
    order_no: str
    patient_id: int
    prescription_id: Optional[int]
    items: list[DrugOrderItemResponse]
    total_price: float
    pay_status: str
    delivery_status: str
    address: str
    created_at: datetime
    cold_chain: bool = False


class DrugOrderStatusResponse(BaseModel):
    """药品订单状态响应（含物流轨迹与冷链温度）。"""
    order_id: int
    order_no: str
    status: str
    delivery_status: str
    estimated_arrival: Optional[str] = None
    shipped_at: Optional[str] = None
    delivered_at: Optional[str] = None
    cold_chain: bool = False
    current_temperature: Optional[float] = None
    temperature_history: list[float] = Field(default_factory=list)
    tracking_points: list[dict[str, Any]] = Field(default_factory=list)
    current_position: Optional[dict[str, float]] = None
    hub: Optional[dict[str, Any]] = None
    route: list[dict[str, float]] = Field(default_factory=list)


class PaymentRequest(BaseModel):
    """模拟支付请求。"""
    order_type: str = Field(..., pattern=r"^(exam|drug)$", description="订单类型")
    payment_method: str = Field(default="mock", pattern=r"^(mock|wechat|alipay)$")


class PaymentResponse(BaseModel):
    """支付响应。"""
    payment_id: int
    order_id: int
    order_type: str
    amount: float
    status: str
    paid_at: Optional[str] = None


# =============================================================================
# 物流追踪相关
# =============================================================================

class DeliveryRequest(BaseModel):
    """管理员发货请求。"""
    order_id: int = Field(..., description="订单 ID")
    from_address: str = Field(..., description="发货地址")
    to_address: str = Field(..., description="收货地址")


class PositionUpdate(BaseModel):
    """WebSocket 推送的位置更新。"""
    type: str = "position_update"
    order_id: int
    position: dict[str, float]  # {"lng": xxx, "lat": xxx}
    progress: float = Field(..., ge=0, le=100)
    status: str


# =============================================================================
# 患者健康档案相关
# =============================================================================

class PatientProfileResponse(BaseModel):
    """患者健康档案响应。"""
    patient_id: int
    name: str
    gender: str
    birth_date: str
    phone: str
    age: int = Field(default=0, description="年龄")
    allergies: list[str] = Field(default_factory=list)
    past_history: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    lifestyle: dict[str, Any] = Field(default_factory=dict)
    recent_visits: list[dict[str, Any]] = Field(default_factory=list)
    visit_count: int = Field(default=0, description="总就诊次数")
    recent_reports: list[dict[str, Any]] = Field(default_factory=list, description="最新检查报告")
    health_trend: list[dict[str, Any]] = Field(default_factory=list, description="健康趋势数据")


class PatientProfileUpdate(BaseModel):
    """患者健康档案更新请求。"""
    allergies: Optional[list[str]] = None
    past_history: Optional[list[str]] = None
    family_history: Optional[list[str]] = None
    lifestyle: Optional[dict[str, Any]] = None


class PatientListItem(BaseModel):
    """患者列表项（用于医生选择患者）。"""
    id: int
    user_id: int
    name: str
    gender: str
    birth_date: str
    phone: str
    is_active: bool


class ReportMetric(BaseModel):
    """检查报告单项指标。"""
    name: str
    value: str
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    status: str = Field(default="normal", description="normal / high / low / abnormal")


class ReportData(BaseModel):
    """检查报告数据。"""
    summary: str
    metrics: list[ReportMetric]


class ExamReportUpdate(BaseModel):
    """管理员上传/更新检查报告请求。"""
    report_data: ReportData
    report_url: Optional[str] = None
    status: Optional[str] = Field(default="completed", pattern=r"^(completed|confirmed)$")


class ExamReportInterpretResponse(BaseModel):
    """AI 报告解读响应。"""
    appointment_id: int
    exam_name: str
    interpretation: str
    abnormal_items: list[ReportMetric] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# =============================================================================
# 管理后台相关
# =============================================================================

class AdminUserResponse(BaseModel):
    """管理员视角的用户信息。"""
    id: int
    username: str
    phone: str
    role: str
    is_active: bool
    doctor_name: Optional[str] = None
    patient_name: Optional[str] = None
    created_at: datetime


class AdminUserCreate(BaseModel):
    """管理员创建用户请求。"""
    username: str = Field(..., min_length=2, max_length=50)
    phone: str = Field(..., pattern=r"^1\d{10}$")
    password: str = Field(..., min_length=8, max_length=20)
    role: str = Field(..., pattern=r"^(doctor|patient|admin)$")
    name: Optional[str] = None          # 医生/患者姓名
    department: Optional[str] = None    # 医生科室
    hospital_id: Optional[int] = None
    gender: Optional[str] = None        # 患者性别 M/F
    birth_date: Optional[str] = None    # 患者出生日期


class AdminDrugCreate(BaseModel):
    """管理员新增药品请求。"""
    name: str = Field(..., min_length=1, max_length=100)
    specification: Optional[str] = None
    manufacturer: Optional[str] = None
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0)
    need_prescription: bool = True


class AdminDrugUpdate(BaseModel):
    """管理员更新药品请求（所有字段可选）。"""
    name: Optional[str] = None
    specification: Optional[str] = None
    manufacturer: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    stock: Optional[int] = Field(None, ge=0)
    need_prescription: Optional[bool] = None
    is_active: Optional[bool] = None


class AdminExamItemCreate(BaseModel):
    """管理员新增检查项目请求。"""
    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = None
    price: float = Field(..., gt=0)
    description: Optional[str] = None


class AdminExamItemUpdate(BaseModel):
    """管理员更新检查项目请求。"""
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DashboardResponse(BaseModel):
    """管理员数据看板响应。"""
    today_consultations: int = 0
    ai_usage_rate: float = 0.0
    drug_order_count: int = 0
    pending_alerts: int = 0
    monthly_services: int = 0
    trend_data: list[int] = Field(default_factory=list)
    trend_labels: list[str] = Field(default_factory=list, description="趋势横轴日期标签（MM-DD）")
    service_distribution: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# 通用响应
# =============================================================================

class MessageResponse(BaseModel):
    """通用消息响应。"""
    ok: bool = True
    message: str = ""
    data: Optional[Any] = None


class PaginatedResponse(BaseModel):
    """分页响应。"""
    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    pages: int = 0
