"""
智医 (ZhiYi) — 数据库 ORM 模型
基层医疗AI辅助诊疗平台

对应优化后的数据库设计：
  users, hospitals, doctors, patients, patient_health_profiles,
  exam_items, exam_appointments, prescriptions, prescription_items,
  drugs, drug_orders, drug_order_items, payments, diagnoses,
  audit_logs
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ── 枚举辅助 ───────────────────────────────────────────────

def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """返回枚举成员值列表，用于 SQLAlchemy Enum 按值存储。"""
    return [e.value for e in enum_cls]


class EncryptedString(TypeDecorator):
    """透明加密字符串列：写入时加密、读取时解密（Fernet）。

    用于身份证号等敏感字段的字段级加密存储。
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        from app.services.crypto import encrypt_text

        return encrypt_text(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        from app.services.crypto import decrypt_text

        return decrypt_text(value)


# ── 枚举类型 ───────────────────────────────────────────────

class UserRole(str, enum.Enum):
    DOCTOR = "doctor"
    PATIENT = "patient"
    ADMIN = "admin"


class Gender(str, enum.Enum):
    M = "M"
    F = "F"


class HospitalLevel(str, enum.Enum):
    VILLAGE = "village"
    TOWNSHIP = "township"
    COUNTY = "county"
    CITY = "city"


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PayStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PrescriptionStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    MOCK = "mock"
    WECHAT = "wechat"
    ALIPAY = "alipay"


# ── ORM 模型 ───────────────────────────────────────────────

class User(Base):
    """用户表 — 统一管理三种角色（医生、患者、管理员）的登录认证。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    phone = Column(String(20), unique=True, nullable=False, comment="手机号")
    password_hash = Column(String(255), nullable=False, comment="bcrypt 密码哈希")
    role = Column(Enum(UserRole, values_callable=_enum_values), nullable=False, comment="用户角色")
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True, comment="所属医院（医生必填）")
    is_active = Column(Boolean, default=True, comment="账号是否启用")
    created_at = Column(DateTime, default=datetime.utcnow, comment="注册时间")

    # 关联
    doctor = relationship("Doctor", back_populates="user", uselist=False, cascade="all, delete-orphan")
    patient = relationship("Patient", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Hospital(Base):
    """医院表 — 存储医疗机构信息。"""

    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="医院名称")
    level = Column(Enum(HospitalLevel, values_callable=_enum_values), nullable=False, comment="医院等级")
    address = Column(String(255), nullable=True, comment="详细地址")


class Doctor(Base):
    """医生表 — 存储医生执业信息。"""

    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(50), nullable=False, comment="医生姓名")
    department = Column(String(100), nullable=True, comment="科室")
    title = Column(String(50), nullable=True, comment="职称")
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    specialty = Column(Text, nullable=True, comment="专长描述")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    user = relationship("User", back_populates="doctor")
    hospital = relationship("Hospital")
    diagnoses = relationship("Diagnosis", back_populates="doctor")
    prescriptions = relationship("Prescription", back_populates="doctor")


class Patient(Base):
    """患者表 — 存储就诊人基本信息。"""

    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(50), nullable=False, comment="患者姓名")
    gender = Column(Enum(Gender, values_callable=_enum_values), nullable=False, comment="性别")
    birth_date = Column(DateTime, nullable=False, comment="出生日期")
    phone = Column(String(20), nullable=False, comment="联系电话")
    id_number = Column(EncryptedString, nullable=True, comment="身份证号（Fernet 字段级加密存储）")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    user = relationship("User", back_populates="patient")
    exam_appointments = relationship("ExamAppointment", back_populates="patient")
    drug_orders = relationship("DrugOrder", back_populates="patient")
    diagnoses = relationship("Diagnosis", back_populates="patient")
    prescriptions = relationship("Prescription", back_populates="patient")
    health_profile = relationship("PatientHealthProfile", back_populates="patient", uselist=False, cascade="all, delete-orphan")


class PatientHealthProfile(Base):
    """患者健康档案表 — 存储过敏史、既往史、家族病史等。

    替代原硬编码逻辑，支持医生端/患者端真实读写。
    """

    __tablename__ = "patient_health_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), unique=True, nullable=False)
    allergies = Column(JSON, default=list, comment="过敏史列表")
    past_history = Column(JSON, default=list, comment="既往病史列表")
    family_history = Column(JSON, default=list, comment="家族病史列表")
    lifestyle = Column(JSON, default=dict, comment="生活方式（吸烟、饮酒、运动等）")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="health_profile")


class ExamItem(Base):
    """检查项目表 — 可预约的医疗检查项目目录。"""

    __tablename__ = "exam_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="项目名称")
    category = Column(String(50), nullable=True, comment="分类（影像科/超声科/检验科等）")
    price = Column(Float, nullable=False, comment="价格（元）")
    description = Column(Text, nullable=True, comment="项目描述")
    is_active = Column(Boolean, default=True, comment="是否开放预约")
    created_at = Column(DateTime, default=datetime.utcnow)


class ExamAppointment(Base):
    """检查预约表 — 患者预约检查的记录。"""

    __tablename__ = "exam_appointments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    exam_item_id = Column(Integer, ForeignKey("exam_items.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    appointment_time = Column(DateTime, nullable=False, comment="预约时间")
    status = Column(Enum(AppointmentStatus, values_callable=_enum_values), default=AppointmentStatus.PENDING, comment="预约状态")
    order_id = Column(Integer, nullable=True, comment="关联订单号")
    report_url = Column(String(500), nullable=True, comment="检查报告链接")
    report_data = Column(JSON, nullable=True, comment="结构化报告数据（指标项）")
    ai_interpretation = Column(Text, nullable=True, comment="AI 报告解读")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    patient = relationship("Patient", back_populates="exam_appointments")
    exam_item = relationship("ExamItem")
    hospital = relationship("Hospital")


class Prescription(Base):
    """处方表 — 医生开具的处方主记录。"""

    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    diagnosis_id = Column(Integer, ForeignKey("diagnoses.id"), nullable=True)
    status = Column(Enum(PrescriptionStatus, values_callable=_enum_values), default=PrescriptionStatus.CONFIRMED)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="prescriptions")
    doctor = relationship("Doctor", back_populates="prescriptions")
    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionItem(Base):
    """处方项目表 — 处方中的药品及用法用量。"""

    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    dosage = Column(String(255), nullable=True, comment="用法用量，如 口服 每日 2 次 每次 1 片")
    quantity = Column(Integer, nullable=False, comment="开具数量")
    duration_days = Column(Integer, nullable=True, comment="用药天数")
    instructions = Column(Text, nullable=True, comment="用药注意事项")

    prescription = relationship("Prescription", back_populates="items")
    drug = relationship("Drug")


class Drug(Base):
    """药品表 — 平台药品目录。"""

    __tablename__ = "drugs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="药品名称")
    specification = Column(String(100), nullable=True, comment="规格（如 20mg × 30 片）")
    manufacturer = Column(String(100), nullable=True, comment="生产厂家")
    price = Column(Float, nullable=False, comment="单价（元）")
    stock = Column(Integer, default=0, comment="库存数量")
    need_prescription = Column(Boolean, default=True, comment="是否需要处方")
    need_cold_chain = Column(Boolean, nullable=False, default=False, server_default="0", comment="是否需要冷链配送（2-8℃）")
    is_active = Column(Boolean, default=True, comment="是否上架")
    created_at = Column(DateTime, default=datetime.utcnow)


class DrugOrder(Base):
    """药品订单主表 — 患者购药订单（可包含多种药品）。"""

    __tablename__ = "drug_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=True, comment="关联处方 ID")
    order_no = Column(String(50), unique=True, nullable=False, comment="订单编号")
    total_price = Column(Float, nullable=False, default=0.0, comment="订单总价")
    pay_status = Column(Enum(PayStatus, values_callable=_enum_values), default=PayStatus.PENDING, comment="支付状态")
    delivery_status = Column(Enum(DeliveryStatus, values_callable=_enum_values), default=DeliveryStatus.PENDING, comment="配送状态")
    shipped_at = Column(DateTime, nullable=True, comment="发货时间")
    delivered_at = Column(DateTime, nullable=True, comment="送达时间")
    address = Column(String(255), nullable=False, comment="收货地址")
    # AI 异步处方审核结果（RabbitMQ 消费者回调更新）
    review_status = Column(String(20), nullable=False, server_default="pending", default="pending", comment="AI 处方审核状态：pending/reviewed/warning")
    review_risk = Column(String(10), nullable=False, server_default="low", default="low", comment="AI 处方审核风险等级：low/medium/high")
    review_result = Column(Text, nullable=True, comment="AI 处方审核结果（JSON）")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    patient = relationship("Patient", back_populates="drug_orders")
    items = relationship("DrugOrderItem", back_populates="order", cascade="all, delete-orphan")


class DrugOrderItem(Base):
    """药品订单项表 — 订单中的每一种药品。"""

    __tablename__ = "drug_order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    drug_order_id = Column(Integer, ForeignKey("drug_orders.id"), nullable=False)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    quantity = Column(Integer, nullable=False, comment="购买数量")
    unit_price = Column(Float, nullable=False, comment="下单时单价")
    subtotal = Column(Float, nullable=False, comment="小计")

    order = relationship("DrugOrder", back_populates="items")
    drug = relationship("Drug")


class Payment(Base):
    """支付流水表 — 记录检查/药品订单的支付历史。"""

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, comment="关联订单 ID")
    order_type = Column(String(20), nullable=False, comment="订单类型：exam / drug")
    amount = Column(Float, nullable=False, comment="支付金额")
    status = Column(Enum(PaymentStatus, values_callable=_enum_values), default=PaymentStatus.PENDING)
    payment_method = Column(Enum(PaymentMethod, values_callable=_enum_values), default=PaymentMethod.MOCK)
    transaction_no = Column(String(100), nullable=True, comment="第三方支付流水号")
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Diagnosis(Base):
    """诊断记录表 — AI 辅助诊断的完整记录。"""

    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    symptoms = Column(Text, nullable=False, comment="患者症状描述")
    extracted_symptoms = Column(JSON, nullable=True, comment="AI 提取的关键症状")
    ai_suggestions = Column(JSON, nullable=True, comment="AI 诊断建议（JSON）")
    final_diagnosis = Column(Text, nullable=True, comment="最终确诊结果")
    treatment_plan = Column(Text, nullable=True, comment="治疗方案")
    medical_record = Column(JSON, nullable=True, comment="结构化病历 JSON")
    medication_review = Column(JSON, nullable=True, comment="用药审核结果 JSON")
    follow_up_plan = Column(JSON, nullable=True, comment="随访计划 JSON")
    use_ai = Column(Boolean, nullable=False, default=False, server_default="0", comment="是否使用大模型 AI 推理（true=AI/RAG，false=规则引擎）")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    patient = relationship("Patient", back_populates="diagnoses")
    doctor = relationship("Doctor", back_populates="diagnoses")


class AiPreConsultation(Base):
    """AI 预问诊记录 — 患者自助评估草稿，须医生确认后才转为正式就诊。"""

    __tablename__ = "ai_pre_consultations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    symptoms = Column(Text, nullable=False, comment="患者症状描述")
    extracted_symptoms = Column(JSON, nullable=True, comment="AI 提取的关键症状")
    ai_suggestions = Column(JSON, nullable=True, comment="AI 诊断建议（JSON）")
    primary_diagnosis = Column(Text, nullable=True, comment="AI 首选诊断")
    primary_reasoning = Column(Text, nullable=True, comment="AI 首选诊断推理依据")
    medication_review = Column(JSON, nullable=True, comment="用药审核结果 JSON")
    medical_record = Column(JSON, nullable=True, comment="AI 生成的病历草稿 JSON")
    follow_up_plan = Column(JSON, nullable=True, comment="随访计划 JSON")
    urgency = Column(String(10), nullable=False, default="low", comment="紧急程度 low/medium/high")
    suggested_department = Column(String(100), nullable=True, comment="建议就诊科室")
    status = Column(String(20), nullable=False, default="pending", comment="pending/confirmed/dismissed")
    confirmed_diagnosis_id = Column(Integer, ForeignKey("diagnoses.id"), nullable=True, comment="确认后生成的正式诊断 ID")
    confirmed_by_doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True, comment="确认医生 ID")
    confirmed_at = Column(DateTime, nullable=True, comment="确认时间")
    use_ai = Column(Boolean, nullable=False, default=False, server_default="0", comment="是否使用大模型 AI 推理")
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")
    confirmed_diagnosis = relationship("Diagnosis")
    confirmed_doctor = relationship("Doctor")


class AlertResolution(Base):
    """告警处理记录 — 记录已处理告警及其条件指纹，条件变化后告警重新出现。"""

    __tablename__ = "alert_resolutions"
    __table_args__ = (
        UniqueConstraint("alert_id", "fingerprint", name="uq_alert_resolution"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(100), nullable=False, comment="告警 ID，如 stock_3 / pending_ship")
    fingerprint = Column(String(100), nullable=False, comment="告警条件指纹，条件变化视为新告警")
    resolved_at = Column(DateTime, default=datetime.utcnow, comment="处理时间")


class AuditLog(Base):
    """审计日志表 — 记录关键操作便于医疗合规追溯。"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False, comment="操作类型")
    resource = Column(String(50), nullable=True, comment="操作对象类型")
    resource_id = Column(Integer, nullable=True, comment="操作对象 ID")
    detail = Column(JSON, nullable=True, comment="操作详情")
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
