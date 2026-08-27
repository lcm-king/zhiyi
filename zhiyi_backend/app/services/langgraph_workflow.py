"""
智医 (ZhiYi) — LangGraph 多 Agent 诊断工作流
基层医疗AI辅助诊疗平台

实现 5 个 Agent 协同工作的诊断流程：
  1. 症状分析 Agent     → 提取关键症状、体征、病史
  2. 鉴别诊断 Agent     → 基于知识库检索相似病例
  3. 诊断建议 Agent     → 生成推荐诊断列表（含置信度）
  4. 用药审核 Agent     → 检查处方合理性
  5. 病历生成 Agent     → 自动生成结构化电子病历

当 Qwen（qwen3.7-max）不可用时，自动降级为基于规则和知识库的模拟输出。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TypedDict

# ── LangGraph 图编排（第一亮点：StateGraph 多 Agent 工作流）──
# langgraph 为可选依赖：安装后走 StateGraph 编译执行，缺失时降级手动链式调用。
try:
    from langgraph.graph import END, StateGraph

    LANGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover - langgraph 未安装时降级
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]
    LANGRAPH_AVAILABLE = False

import httpx

from app.config import get_settings
from app.services.knowledge_base import search_diseases

logger = logging.getLogger("zhiyi.langgraph")
settings = get_settings()

# Qwen 对话大模型（DashScope 兼容模式，当前 chat provider：qwen3.7-max）
QWEN_API_KEY = settings.qwen_api_key or ""
QWEN_API_URL = settings.qwen_api_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_CHAT_MODEL = settings.qwen_chat_model or "qwen3.7-max"

# SiliconFlow embedding（RAG 向量化；Qwen 对话模型不提供 embedding 接口）
SILICONFLOW_API_KEY = settings.siliconflow_api_key or ""
SILICONFLOW_API_URL = settings.siliconflow_api_url or "https://api.siliconflow.cn/v1"
SILICONFLOW_EMBEDDING_MODEL = settings.siliconflow_embedding_model or "BAAI/bge-m3"


# =============================================================================
# 工作流状态
# =============================================================================

@dataclass
class DiagnosisState:
    """诊断工作流的状态容器，在 5 个 Agent 之间传递。"""

    # 输入
    patient_id: int
    patient_name: str = ""
    symptoms: str = ""
    patient_allergies: list[str] = field(default_factory=list)
    patient_history: list[str] = field(default_factory=list)
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None

    # 中间结果
    extracted_symptoms: list[str] = field(default_factory=list)
    extracted_signs: list[str] = field(default_factory=list)
    matched_diseases: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_suggestions: list[dict[str, Any]] = field(default_factory=list)
    # LLM 首选诊断（真正驱动最终排序与病历，而不是被丢弃）
    primary_diagnosis: str = ""
    primary_confidence: Optional[int] = None
    primary_reasoning: str = ""
    llm_analysis: dict[str, Any] = field(default_factory=dict)
    medication_review: dict[str, Any] = field(default_factory=dict)
    medical_record: dict[str, Any] = field(default_factory=dict)
    follow_up_plan: dict[str, Any] = field(default_factory=dict)

    # 元信息
    workflow_started: str = ""
    agent_logs: list[str] = field(default_factory=list)
    use_ai: bool = False  # 是否使用了 AI（否则为规则引擎）


# =============================================================================
# LangGraph 图状态（TypedDict）
# =============================================================================

class DiagnosisStateDict(TypedDict, total=False):
    """LangGraph 图节点间传递的状态字典（字段与 DiagnosisState 一一对应）。"""

    patient_id: int
    patient_name: str
    symptoms: str
    patient_allergies: list[str]
    patient_history: list[str]
    patient_age: Optional[int]
    patient_gender: Optional[str]
    extracted_symptoms: list[str]
    extracted_signs: list[str]
    matched_diseases: list[dict[str, Any]]
    diagnosis_suggestions: list[dict[str, Any]]
    primary_diagnosis: str
    primary_confidence: Optional[int]
    primary_reasoning: str
    llm_analysis: dict[str, Any]
    medication_review: dict[str, Any]
    medical_record: dict[str, Any]
    follow_up_plan: dict[str, Any]
    workflow_started: str
    agent_logs: list[str]
    use_ai: bool


def _state_to_dict(state: DiagnosisState) -> dict[str, Any]:
    """将 DiagnosisState 转为图状态字典。"""
    from dataclasses import asdict
    return asdict(state)


def _state_from_dict(data: dict[str, Any]) -> DiagnosisState:
    """从图状态字典还原 DiagnosisState（忽略未知字段）。"""
    field_names = set(DiagnosisState.__dataclass_fields__.keys())
    return DiagnosisState(**{k: v for k, v in data.items() if k in field_names})


def _extract_json(text: str) -> str:
    """从大模型输出中稳健提取 JSON。

    推理模型（qwen3.7-max）对复杂 JSON 指令的遵循不稳定，可能返回
    自然语言前缀、markdown 代码块或多余解释。此函数剔除杂质后取首个
    “{”到最后一个“}”之间的内容，供 json.loads 解析。
    """
    if not text:
        return ""
    # 去掉 markdown 代码块围栏（```json / ```）
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start:end + 1]
    return cleaned



# =============================================================================
# Agent 1：症状分析 + RAG 知识检索
# =============================================================================

async def agent_symptom_analysis(state: DiagnosisState) -> DiagnosisState:
    """RAG 模式：知识库检索（向量优先、关键词兜底）→ Qwen LLM 推理。

    流程：
    1. ChromaDB 向量检索 top-8 最相关疾病；失败/为空时用关键词检索兜底
    2. 将检索结果 + 患者信息注入 prompt，Qwen3.7-max 完成推理
    3. LLM 输出的首选诊断（primary_diagnosis）存入状态，后续 Agent 置顶展示
    """
    state.agent_logs.append("[症状分析] 启动：知识库检索 → LLM 推理…")

    if QWEN_API_KEY:
        try:
            # Step 1: 向量检索知识库（失败时关键词兜底，保证 LLM 有上下文）
            state.matched_diseases = await _rag_retrieve(state)
            if not state.matched_diseases:
                state.matched_diseases = search_diseases(
                    state.symptoms,
                    top_k=5,
                    patient_history=state.patient_history,
                    patient_allergies=state.patient_allergies,
                )
            if state.matched_diseases:
                state.agent_logs.append(
                    f"[知识检索] 匹配到 {len(state.matched_diseases)} 种疑似疾病："
                    f"{', '.join(d['name'] for d in state.matched_diseases[:3])}"
                )
            else:
                state.agent_logs.append("[知识检索] 未命中知识库，将使用 LLM 通用医学知识推理")

            # Step 2: LLM 推理（即使无向量检索结果也调用，避免诊断失效）
            result = await _rag_diagnose(state)
            try:
                data = json.loads(_extract_json(result))
            except Exception as exc:
                # 模型偶发输出自然语言而非 JSON：严格模式重试一次
                logger.warning(
                    "RAG 推理输出非合法 JSON（%.120s…），切换严格模式重试：%s",
                    (result or "")[:120].replace("\n", " "),
                    exc,
                )
                result = await _rag_diagnose(state, strict=True)
                data = json.loads(_extract_json(result))

            symptoms_raw = data.get("symptoms") or []
            state.extracted_symptoms = (
                list(symptoms_raw) if isinstance(symptoms_raw, list) else [str(symptoms_raw)]
            )
            state.primary_diagnosis = str(data.get("primary_diagnosis") or "").strip()
            confidence_raw = data.get("confidence")
            try:
                state.primary_confidence = int(float(confidence_raw))
            except (TypeError, ValueError):
                state.primary_confidence = None
            state.primary_reasoning = str(data.get("reasoning") or "").strip()
            state.llm_analysis = data
            state.use_ai = True
            state.agent_logs.append(
                f"[LLM 推理] Qwen3.7-max 提取 {len(state.extracted_symptoms)} 个症状，"
                f"首选诊断：{state.primary_diagnosis or '待确认'}"
            )
            return state
        except Exception as exc:
            logger.warning("LLM 推理失败，降级规则引擎：%s", exc)
    else:
        state.agent_logs.append("[系统提示] 未配置 Qwen API Key，本次诊断使用本地规则引擎")

    # ===== 规则引擎降级 =====
    return await _fallback_rule_engine(state)


# =============================================================================
# Agent 2：鉴别诊断（RAG 模式下已在 Agent 1 中完成）
# =============================================================================

async def agent_differential_diagnosis(state: DiagnosisState) -> DiagnosisState:
    """鉴别诊断：LLM 首选诊断置顶，其余按知识库检索结果排序。"""
    # 1) LLM 首选诊断置顶（真实驱动排序，避免首选被淹没在列表里）
    if state.primary_diagnosis:
        primary = state.primary_diagnosis
        idx = next(
            (
                i
                for i, d in enumerate(state.matched_diseases)
                if primary == d.get("name")
                or primary in str(d.get("name", ""))
                or str(d.get("name", "")) in primary
            ),
            None,
        )
        if idx is None:
            # 知识库未收录该名称：合成一条 LLM 推理记录，确保首选诊断可见
            state.matched_diseases.insert(
                0,
                {
                    "id": f"llm-{abs(hash(primary)) % 100000}",
                    "name": primary,
                    "category": "AI 推理",
                    "match_score": state.primary_confidence or 90,
                    "matched_keywords": ["LLM 首选诊断"],
                    "typical_symptoms": state.extracted_symptoms,
                    "signs": [],
                    "diagnostic_criteria": [],
                    "differential_diagnoses": state.llm_analysis.get("differential") or [],
                    "recommended_exams": state.llm_analysis.get("suggested_exams") or [],
                    "treatment_principles": [],
                    "risk_factors": [],
                    "common_drugs": [],
                },
            )
        else:
            item = state.matched_diseases.pop(idx)
            item["match_score"] = max(
                int(item.get("match_score", 0) or 0), state.primary_confidence or 90
            )
            item["raw_score"] = item["match_score"] * 1.1
            item["matched_keywords"] = list(
                set(item.get("matched_keywords", []) + ["LLM 首选诊断"])
            )
            state.matched_diseases.insert(0, item)
        state.agent_logs.append(f"[鉴别诊断] LLM 首选诊断「{primary}」已置顶")
        return state

    if state.matched_diseases:
        state.agent_logs.append("[鉴别诊断] 已通过知识库检索完成")
        return state

    # 降级：关键词检索
    state.agent_logs.append("[鉴别诊断] 使用关键词检索知识库…")
    matched = search_diseases(
        state.symptoms,
        top_k=5,
        patient_history=state.patient_history,
        patient_allergies=state.patient_allergies,
        extracted_symptoms=state.extracted_symptoms,
    )
    state.matched_diseases = matched
    names = [d["name"] for d in matched[:3]]
    state.agent_logs.append(f"[鉴别诊断] 匹配到 {len(matched)} 种疑似疾病：{', '.join(names)}")
    return state


# =============================================================================
# Agent 3：诊断建议
# =============================================================================

async def agent_diagnosis_suggestion(state: DiagnosisState) -> DiagnosisState:
    """基于知识库匹配结果生成诊断建议列表（含置信度、鉴别诊断、检查/药品推荐）。"""
    state.agent_logs.append("[诊断建议] 生成推荐诊断方案…")

    suggestions: list[dict[str, Any]] = []
    tones = ["blue", "amber", "violet", "emerald", "rose"]

    for i, disease in enumerate(state.matched_diseases):
        base_score = disease.get("match_score", 30)
        is_primary = (
            i == 0
            and bool(state.primary_diagnosis)
            and (
                disease.get("name") == state.primary_diagnosis
                or state.primary_diagnosis in str(disease.get("name", ""))
                or str(disease.get("name", "")) in state.primary_diagnosis
            )
        )
        # AI 模式：LLM 推理，置信度显著提升；首选诊断直接采用 LLM 置信度
        rag_multiplier = 1.5 if state.use_ai else 1.0
        if is_primary and state.primary_confidence:
            confidence = min(99, max(20, state.primary_confidence))
        else:
            confidence = min(99, max(20, int(base_score * rag_multiplier) + (5 - i) * 2))
        reasons = disease.get("typical_symptoms", [])[:2]
        matched_kws = disease.get("matched_keywords", [])[:3]

        # 推荐检查（可映射到数据库检查项目）
        exams = [
            {"exam_name": e, "reason": f"用于评估{disease['name']}病情或排除鉴别诊断", "priority": "high" if idx < 2 else "normal"}
            for idx, e in enumerate(disease.get("recommended_exams", []))
        ]

        # 推荐药品（带过敏警示）
        drugs: list[dict[str, Any]] = []
        for drug in disease.get("common_drugs", [])[:4]:
            warning = None
            for allergy in state.patient_allergies:
                if allergy in drug or drug in allergy:
                    warning = f"患者有 {allergy} 过敏史，使用 {drug} 前需确认是否过敏"
                    break
            drugs.append({"drug_name": drug, "reason": f"{disease['name']}常用治疗药物", "warning": warning})

        # LLM 首选诊断的说明直接使用模型推理依据
        description = (
            f"结合患者{', '.join(state.extracted_symptoms[:2]) if state.extracted_symptoms else '所述症状'}等表现，"
            f"需考虑{disease['name']}可能。{'; '.join(reasons)}"
        )
        if is_primary and state.primary_reasoning:
            description = f"{state.primary_reasoning}（AI 首选诊断，请结合面诊确认）"

        suggestions.append({
            "id": i + 1,
            "name": disease["name"],
            "confidence": confidence,
            "description": description,
            "tags": matched_kws,
            "tone": tones[i % len(tones)],
            "is_primary": is_primary,
            "differential_diagnoses": disease.get("differential_diagnoses", []),
            "recommended_exams": exams,
            "recommended_drugs": drugs,
        })

    state.diagnosis_suggestions = suggestions
    state.agent_logs.append(f"[诊断建议] 生成 {len(suggestions)} 条诊断建议，最高置信度 {suggestions[0]['confidence'] if suggestions else 0}%")
    return state


# =============================================================================
# Agent 4：用药审核
# =============================================================================

async def agent_medication_review(state: DiagnosisState) -> DiagnosisState:
    """审核处方合理性：药物相互作用、剂量、过敏史、年龄/性别禁忌。"""
    state.agent_logs.append("[用药审核] 审核处方合理性…")

    warnings: list[str] = []
    recommendations: list[str] = []
    allergy_alert = False

    # 检查过敏史与推荐药品的冲突
    if state.patient_allergies:
        for allergy in state.patient_allergies:
            allergy_lower = allergy.lower()
            for disease in state.matched_diseases[:3]:
                for drug in disease.get("common_drugs", []):
                    drug_lower = drug.lower()
                    # 直接包含或类别匹配
                    matched = (
                        allergy in drug or drug in allergy
                        or ("青霉素" in allergy and ("头孢" in drug or "阿莫西林" in drug or "青霉素" in drug))
                        or ("磺胺" in allergy and "磺胺" in drug)
                        or ("阿司匹林" in allergy and ("阿司匹林" in drug or "NSAID" in drug))
                    )
                    if matched:
                        warnings.append(f"⚠️ 患者对 {allergy} 过敏，请避免使用 {drug}")
                        recommendations.append(f"如必须使用同类药物，建议选择非 {allergy} 类替代方案")
                        allergy_alert = True
            if "青霉素" in allergy:
                warnings.append("⚠️ 患者青霉素过敏，避免使用 β-内酰胺类抗生素（如青霉素、阿莫西林、头孢菌素）")
                recommendations.append("推荐使用大环内酯类（如阿奇霉素）或喹诺酮类（如左氧氟沙星）替代")

    # 高血压相关提示
    if "高血压" in state.symptoms or any("高血压" in str(d.get("name", "")) for d in state.matched_diseases):
        warnings.append("⚠️ 如开具 ACEI/ARB 类药物与利尿剂，需监测血压和肾功能")

    # 儿童/老年用药提示
    age = state.patient_age
    if age is not None and age < 12:
        warnings.append("⚠️ 患者为儿童，用药需按体重精确计算剂量，慎用喹诺酮/四环素类")
    elif age is not None and age >= 65:
        recommendations.append("老年患者起始剂量宜低，注意肝肾功能及多重用药相互作用")

    # 妊娠期提示（女性患者）
    if state.patient_gender == "F":
        warnings.append("⚠️ 育龄期/妊娠期女性用药需确认妊娠状态，避免使用 X 级致畸药物")

    # 症状复杂提示
    if state.extracted_symptoms and len(state.extracted_symptoms) > 3:
        warnings.append("⚠️ 患者症状较多，建议分步处理，优先解决主要矛盾")

    state.medication_review = {
        "passed": len(warnings) == 0,
        "warnings": warnings,
        "recommendations": recommendations,
        "requires_manual_review": len(warnings) > 0 or allergy_alert,
        "allergy_alert": allergy_alert,
        "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    state.agent_logs.append(f"[用药审核] {'通过' if state.medication_review['passed'] else '需要复核'}")
    return state


# =============================================================================
# Agent 5：病历生成
# =============================================================================

async def agent_medical_record(state: DiagnosisState) -> DiagnosisState:
    """自动生成结构化电子病历，并生成随访建议。"""
    state.agent_logs.append("[病历生成] 生成结构化电子病历…")

    top_diagnosis = (
        state.primary_diagnosis
        or (state.diagnosis_suggestions[0]["name"] if state.diagnosis_suggestions else "待确认")
    )
    top_confidence = state.primary_confidence or (
        state.diagnosis_suggestions[0]["confidence"] if state.diagnosis_suggestions else 0
    )

    # 现病史更贴近输入
    present_illness = (
        f"患者因「{state.symptoms[:60]}{'…' if len(state.symptoms) > 60 else ''}」就诊。"
        f"起病以来精神、食欲、睡眠一般，大小便未见明显异常。"
    )

    # 体格检查建议
    physical_exam_suggestions = ["血压监测", "心肺听诊", "腹部触诊"]
    if state.matched_diseases:
        physical_exam_suggestions = state.matched_diseases[0].get("signs", physical_exam_suggestions)[:5]

    # 治疗原则
    treatment_principles: list[str] = []
    if state.matched_diseases:
        treatment_principles = state.matched_diseases[0].get("treatment_principles", [])[:4]

    # 鉴别诊断
    differential: list[str] = []
    if state.matched_diseases:
        differential = state.matched_diseases[0].get("differential_diagnoses", [])[:4]

    state.medical_record = {
        "chief_complaint": state.symptoms[:200],
        "present_illness": present_illness,
        "past_history": "; ".join(state.patient_history) if state.patient_history else "既往体健",
        "allergies": "; ".join(state.patient_allergies) if state.patient_allergies else "无已知过敏史",
        "physical_examination": {
            "general": "神清，精神尚可，步入诊室",
            "vital_signs": "待测量（BP/HR/RR/T/SpO2）",
            "focused_exam": physical_exam_suggestions,
        },
        "differential_diagnosis": differential,
        "preliminary_diagnosis": f"{top_diagnosis}（AI 辅助诊断，置信度 {top_confidence}%），需医生最终确认",
        "treatment_plan": treatment_principles,
        "medication_review": state.medication_review,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 生成随访计划
    watch_items = ["症状变化", "用药反应", "生命体征"]
    lifestyle = ["低盐低脂饮食", "适量活动", "避免受凉"]
    warning = ["出现胸痛、意识改变、呼吸困难加重等情况立即就医"]
    interval = 7

    if state.matched_diseases:
        disease = state.matched_diseases[0]
        if "高血压" in disease["name"] or "糖尿病" in disease["name"]:
            interval = 14
            watch_items = ["血压/血糖控制情况", "有无头晕、乏力", "用药依从性"]
            lifestyle = ["低盐低脂饮食", "规律监测血压/血糖", "戒烟限酒"]
        elif "心力衰竭" in disease["name"]:
            interval = 3
            watch_items = ["水肿变化", "体重波动", "夜间能否平卧", "尿量"]
            warning = ["呼吸困难加重、下肢水肿明显、尿量骤减需急诊"]
        elif "肺炎" in disease["name"] or "上呼吸道感染" in disease["name"]:
            interval = 3
            watch_items = ["体温", "咳嗽咳痰变化", "胸痛、气促"]
            lifestyle = ["多饮水", "注意休息", "避免劳累"]

    state.follow_up_plan = {
        "interval_days": interval,
        "watch_items": watch_items,
        "lifestyle_advice": lifestyle,
        "warning_symptoms": warning,
    }

    state.agent_logs.append(f"[病历生成] 结构化病历已生成，初步诊断：{top_diagnosis}")
    return state



# =============================================================================
# LangGraph 图节点包装（StateGraph 节点统一接收/返回字典）
# =============================================================================

async def _node_symptom_analysis(state: DiagnosisStateDict) -> dict[str, Any]:
    """图节点 1：症状分析 Agent。"""
    return _state_to_dict(await agent_symptom_analysis(_state_from_dict(dict(state))))


async def _node_differential_diagnosis(state: DiagnosisStateDict) -> dict[str, Any]:
    """图节点 2：鉴别诊断 Agent。"""
    return _state_to_dict(await agent_differential_diagnosis(_state_from_dict(dict(state))))


async def _node_diagnosis_suggestion(state: DiagnosisStateDict) -> dict[str, Any]:
    """图节点 3：诊断建议 Agent。"""
    return _state_to_dict(await agent_diagnosis_suggestion(_state_from_dict(dict(state))))


async def _node_medication_review(state: DiagnosisStateDict) -> dict[str, Any]:
    """图节点 4：用药审核 Agent。"""
    return _state_to_dict(await agent_medication_review(_state_from_dict(dict(state))))


async def _node_medical_record(state: DiagnosisStateDict) -> dict[str, Any]:
    """图节点 5：病历生成 Agent。"""
    return _state_to_dict(await agent_medical_record(_state_from_dict(dict(state))))


# 编译产物缓存
_compiled_graph = None


def get_compiled_graph():
    """构建并缓存 LangGraph StateGraph（5 节点线性流水线）。

    节点顺序：症状分析 → 鉴别诊断 → 诊断建议 → 用药审核 → 病历生成。
    使用 StateGraph.add_node / add_edge / set_entry_point / compile 完成真实图编排。
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph
    if not LANGRAPH_AVAILABLE:
        return None

    workflow = StateGraph(DiagnosisStateDict)

    workflow.add_node("symptom_analysis", _node_symptom_analysis)
    workflow.add_node("differential_diagnosis", _node_differential_diagnosis)
    workflow.add_node("diagnosis_suggestion", _node_diagnosis_suggestion)
    workflow.add_node("medication_review", _node_medication_review)
    workflow.add_node("medical_record", _node_medical_record)

    workflow.set_entry_point("symptom_analysis")
    workflow.add_edge("symptom_analysis", "differential_diagnosis")
    workflow.add_edge("differential_diagnosis", "diagnosis_suggestion")
    workflow.add_edge("diagnosis_suggestion", "medication_review")
    workflow.add_edge("medication_review", "medical_record")
    workflow.add_edge("medical_record", END)

    _compiled_graph = workflow.compile()
    logger.info("LangGraph 诊断工作流已编译：StateGraph 5 节点流水线")
    return _compiled_graph


# =============================================================================
# 工作流编排
# =============================================================================

async def run_diagnosis_workflow(
    patient_id: int,
    symptoms: str,
    *,
    patient_name: str = "",
    patient_allergies: Optional[list[str]] = None,
    patient_history: Optional[list[str]] = None,
    patient_age: Optional[int] = None,
    patient_gender: Optional[str] = None,
) -> DiagnosisState:
    """执行完整的 5-Agent 诊断工作流。"""
    state = DiagnosisState(
        patient_id=patient_id,
        patient_name=patient_name or f"患者{patient_id}",
        symptoms=symptoms,
        patient_allergies=patient_allergies or [],
        patient_history=patient_history or [],
        patient_age=patient_age,
        patient_gender=patient_gender,
        workflow_started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    logger.info("启动诊断工作流：patient_id=%d, symptoms=%s…", patient_id, symptoms[:50])

    # 优先使用 LangGraph StateGraph 编译图执行 5-Agent 流水线
    graph = get_compiled_graph()
    if graph is not None:
        try:
            result = await graph.ainvoke(_state_to_dict(state))
            final_state = _state_from_dict(result)
            final_state.agent_logs.append("[LangGraph] 5-Agent 流水线已由 StateGraph 编排执行")
            logger.info(
                "诊断工作流完成（LangGraph 图执行）：耗时 %s, 诊断 %d 条, AI=%s",
                final_state.workflow_started,
                len(final_state.diagnosis_suggestions),
                final_state.use_ai,
            )
            return final_state
        except Exception as exc:
            logger.warning("LangGraph 图执行失败，降级为手动链式调用：%s", exc)

    # 兜底：手动链式调用（langgraph 未安装或图执行异常时）
    state = await agent_symptom_analysis(state)
    state = await agent_differential_diagnosis(state)
    state = await agent_diagnosis_suggestion(state)
    state = await agent_medication_review(state)
    state = await agent_medical_record(state)

    logger.info(
        "诊断工作流完成（手动链式）：耗时 %s, 诊断 %d 条, AI=%s",
        state.workflow_started,
        len(state.diagnosis_suggestions),
        state.use_ai,
    )

    return state


# =============================================================================
# RAG 核心：知识库检索 + LLM 推理
# =============================================================================

async def _fallback_rule_engine(state: DiagnosisState) -> DiagnosisState:
    """无 LLM API 时的关键词匹配降级。"""
    symptom_map = {
        "胸闷": ["胸闷", "胸部不适"], "气促": ["气促", "呼吸困难"],
        "咳嗽": ["咳嗽"], "发热": ["发热"], "咳痰": ["咳痰"],
        "头痛": ["头痛"], "头晕": ["头晕"], "心悸": ["心悸", "心慌"],
        "水肿": ["水肿", "浮肿"], "乏力": ["乏力", "疲劳"],
        "胸痛": ["胸痛"], "腹痛": ["腹痛"], "腹泻": ["腹泻"],
        "呕吐": ["呕吐", "恶心"], "喘息": ["喘息", "哮鸣"],
        "失眠": ["失眠", "睡眠障碍"], "多饮": ["多饮", "烦渴"],
        "多尿": ["多尿"], "体重下降": ["体重下降", "消瘦"],
        "关节痛": ["关节痛", "关节疼痛"], "麻木": ["麻木", "感觉异常"],
        "反酸": ["反酸", "烧心"], "心慌": ["心悸", "心慌"],
        "困倦": ["困倦", "犯困", "想睡觉", "嗜睡"],
        "睡眠不足": ["睡眠不足", "熬夜", "晚睡", "睡得晚", "没睡够", "2点钟睡"],
        "发烧": ["发热"], "痰": ["咳痰"], "喘": ["喘息"],
        "疼": ["疼痛"], "痛": ["疼痛"],
    }
    for keyword, labels in symptom_map.items():
        if keyword in state.symptoms:
            state.extracted_symptoms.extend(labels)
    if not state.extracted_symptoms:
        # 兜底：直接取用户输入
        state.extracted_symptoms = state.symptoms.replace("，", ",").split(",")[:3]
        if not state.extracted_symptoms or not state.extracted_symptoms[0].strip():
            state.extracted_symptoms = [state.symptoms.strip()[:20] or "待进一步检查确认的症状"]
    state.agent_logs.append(f"[症状分析] 提取到 {len(state.extracted_symptoms)} 个症状（规则引擎）")
    return state


async def _rag_retrieve(state: DiagnosisState) -> list[dict[str, Any]]:
    """RAG 第一步：SiliconFlow embedding 向量化症状 → ChromaDB 语义搜索。"""
    try:
        import chromadb
        from app.services.knowledge_base import DISEASE_KNOWLEDGE

        query_parts = [state.symptoms]
        if state.patient_history:
            query_parts.append("既往史：" + "；".join(state.patient_history))
        if state.patient_allergies:
            query_parts.append("过敏史：" + "；".join(state.patient_allergies))
        query_text = "。".join(query_parts)

        query_vectors = await get_qwen_embeddings([query_text])
        if not query_vectors:
            return []

        client = chromadb.HttpClient(
            host=settings.chroma_host or "localhost",
            port=int(settings.chroma_port or 8000),
        )
        collection = client.get_or_create_collection("disease_knowledge")
        results = collection.query(query_embeddings=query_vectors, n_results=8)

        disease_map = {d["id"]: d for d in DISEASE_KNOWLEDGE}
        matched: list[dict[str, Any]] = []
        if results.get("ids") and results["ids"][0]:
            for i, did in enumerate(results["ids"][0]):
                if did in disease_map:
                    d = dict(disease_map[did])
                    dist = results.get("distances", [[0.5]] * 10)
                    score = max(20, int((1 - dist[0][i]) * 100))
                    d["match_score"] = score
                    d["raw_score"] = score
                    d["matched_keywords"] = ["向量语义匹配"]
                    matched.append(d)
        return matched
    except Exception as exc:
        logger.warning("RAG 向量检索失败：%s", exc)
        return []


async def _rag_diagnose(state: DiagnosisState, strict: bool = False) -> str:
    """RAG 第二步：知识库上下文注入 prompt → Qwen chat 推理诊断。"""
    context_parts = []
    for i, d in enumerate(state.matched_diseases[:5]):
        ctx = (
            f"[{i + 1}] {d['name']}（{d.get('category', '未知')}）\n"
            f"  关键词：{', '.join(d.get('keywords', [])[:6])}\n"
            f"  典型症状：{'；'.join(d.get('typical_symptoms', [])[:3])}\n"
            f"  体征：{'；'.join(d.get('signs', [])[:3])}\n"
            f"  诊断标准：{'；'.join(d.get('diagnostic_criteria', [])[:2])}\n"
            f"  鉴别：{'、'.join(d.get('differential_diagnoses', [])[:3])}"
        )
        context_parts.append(ctx)

    system_prompt = (
        "你是资深基层全科医生。以下是从83种疾病知识库中检索到的与患者症状最相关的疾病"
        "诊断知识，检索结果仅供参考。请以患者主诉为准，结合医学常识给出最合理的诊断。"
        "特别提醒：当主诉表现为困倦、想睡觉、睡眠不足/熬夜、白天犯困、睡眠时间短等时，"
        "应优先考虑睡眠障碍/失眠/睡眠剥夺，不要机械套用检索结果中的神经科疾病"
        "（如三叉神经痛）。若【知识库检索结果】为空，请直接基于通用医学知识"
        "结合患者信息给出合理诊断。"
        "只输出一个 JSON 对象，不要输出任何解释、前后缀文字或 markdown 代码块标记，"
        "严格按以下结构返回："
        '{"symptoms":["症状1","症状2"],"primary_diagnosis":"首选诊断疾病名",'
        '"confidence":80,"reasoning":"推理依据（基于知识库中的诊断标准和体征）",'
        '"differential":["鉴别1","鉴别2"],'
        '"suggested_exams":["检查1","检查2"],"urgency":"low/medium/high"}'
    )
    if strict:
        system_prompt += (
            "【重要】上一次输出未通过解析。本次必须且只能输出一个合法 JSON 对象，"
            "禁止输出 JSON 以外的任何字符、解释或代码块。"
        )

    context_block = "\n".join(context_parts) if context_parts else "（无检索结果，请基于通用医学知识判断）"
    user_prompt = (
        f"【知识库检索结果】\n{context_block}\n\n"
        f"【患者信息】\n{state.patient_name}，{state.patient_gender or '未知'}，"
        f"{state.patient_age or '未知'}岁\n"
        f"主诉：{state.symptoms}\n"
        f"既往史：{'; '.join(state.patient_history) if state.patient_history else '无'}\n"
        f"过敏史：{'; '.join(state.patient_allergies) if state.patient_allergies else '无'}"
    )

    return await _call_qwen(system_prompt, user_prompt, timeout=15.0, json_mode=True)


# =============================================================================
# 大模型 API 调用（聊天模型 + 嵌入模型，双 provider 自动降级）
# =============================================================================

async def _call_openai_chat(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float = 15.0,
    json_mode: bool = False,
) -> str:
    """调用 OpenAI 兼容格式的 chat/completions API 进行自然语言推理。

    Qwen（DashScope 兼容模式，qwen3.7-max）为当前接入的 provider。部分推理模型
    可能把 token 消耗在 reasoning_content 上，若正文为空则回退使用推理内容。
    """
    if not api_key:
        raise ValueError("未配置 API Key")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    if json_mode:
        # Qwen DashScope 兼容模式支持 response_format=json_object，
        # 强制模型只输出合法 JSON，避免自然语言前缀导致解析失败。
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        raw = response.text or ""
        if not raw.strip():
            raise ValueError("OpenAI 兼容接口返回空响应体（HTTP 200 但无内容）")
        try:
            data = response.json()
        except Exception as exc:
            raise ValueError(f"OpenAI 兼容接口响应不是合法 JSON：{raw[:120]!r}") from exc
        if not isinstance(data, dict) or not data.get("choices"):
            raise ValueError(f"OpenAI 兼容接口响应缺少 choices 字段：{str(data)[:200]}")
        message = data["choices"][0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):  # OpenAI parts 数组格式
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        content = content.strip()
        if not content:
            reasoning = message.get("reasoning_content") or ""
            if isinstance(reasoning, list):
                reasoning = "".join(
                    part.get("text", "") for part in reasoning if isinstance(part, dict)
                )
            content = reasoning.strip()
        if not content:
            raise ValueError("模型返回空内容（content 与 reasoning_content 均为空）")
        return content


async def _get_embeddings(
    api_key: str,
    base_url: str,
    model: str,
    texts: list[str],
    timeout: float = 15.0,
) -> list[list[float]]:
    """调用 OpenAI 兼容格式的 embeddings API 生成文本向量。"""
    if not api_key:
        raise ValueError("未配置 API Key")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


async def _call_qwen(
    system_prompt: str,
    user_prompt: str,
    timeout: float = 5.0,
    json_mode: bool = False,
) -> str:
    """调用对话大模型：仅使用 DashScope 的 qwen3.7-max（OpenAI 兼容模式）。

    网络抖动时自动重试，仍失败则抛异常，由调用方降级为本地规则引擎。
    """
    if not QWEN_API_KEY:
        raise ValueError("未配置 Qwen API Key")

    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            return await _call_openai_chat(
                QWEN_API_KEY, QWEN_API_URL, QWEN_CHAT_MODEL,
                system_prompt, user_prompt, timeout=max(timeout, 60.0),
                json_mode=json_mode,
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Qwen3.7-max 第 %s 次调用失败：%s", attempt + 1, exc
            )
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


async def get_qwen_embeddings(texts: list[str], timeout: float = 10.0) -> list[list[float]]:
    """调用 embedding 接口（SiliconFlow BAAI/bge-m3）用于 ChromaDB 语义检索。

    Qwen 对话模型不提供 embedding 接口，向量化固定使用
    SiliconFlow 的 BAAI/bge-m3；网络抖动时重试一次，仍失败由调用方降级为关键词检索。
    """
    if not SILICONFLOW_API_KEY:
        raise ValueError("未配置 SiliconFlow API Key（embedding）")

    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            return await _get_embeddings(
                SILICONFLOW_API_KEY, SILICONFLOW_API_URL, SILICONFLOW_EMBEDDING_MODEL,
                texts, timeout=max(timeout, 60.0),
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "SiliconFlow embedding 第 %s 次调用失败（将重试）：%s", attempt + 1, exc
            )
            if attempt == 0:
                await asyncio.sleep(1.5)
    raise last_exc  # type: ignore[misc]
