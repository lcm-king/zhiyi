"""
智医 (ZhiYi) — 检查报告动态生成器

按患者病历（过敏史 / 既往史 / 家族史 / 生活方式 / 年龄 / 性别）**确定性**生成
结构化检查报告：同一 (patient_id, exam_item_id) 组合永远生成同一份报告；
不同患者因病历不同，指标数值与异常倾向随之变化。

用于演示环境让"已完成报告"随患者档案动态呈现；真实报告仍以医生上传为准
（exam.py update_report 会覆盖 report_data）。
"""

from __future__ import annotations

import random
from typing import Any, Optional


# =============================================================================
# 指标模板
# 数值型：base=基准值, ref=(下限, 上限), unit=单位, spread=抖动幅度
# 描述型：normal=正常选项, abnormal=异常选项（按病历/随机挑选）
# =============================================================================

_NUM = "num"
_DESC = "desc"


def _m(name: str, base: float, ref_low: float, ref_high: float, unit: str, spread: float = 0.0, decimals: int = 1) -> dict[str, Any]:
    return {
        "kind": _NUM,
        "name": name,
        "base": base,
        "ref": (ref_low, ref_high),
        "unit": unit,
        "spread": spread,
        "decimals": decimals,
    }


def _d(name: str, normal: list[str], abnormal: list[str], abnormal_flag: Optional[str] = None, abnormal_rate: float = 0.12) -> dict[str, Any]:
    return {
        "kind": _DESC,
        "name": name,
        "normal": normal,
        "abnormal": abnormal,
        "abnormal_flag": abnormal_flag,
        "abnormal_rate": abnormal_rate,
    }


TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "胸部低剂量 CT": [
        _d("肺窗结节", ["未见明显结节"], ["右肺上叶见 3mm 微小结节", "左肺下叶见 5mm 小结节", "双肺散在粟粒样小结节"], "lung", 0.18),
        _d("肺纹理", ["清晰，走形自然"], ["增多、增粗", "紊乱伴索条影"], "lung", 0.22),
        _d("纵隔淋巴结", ["未见肿大"], ["纵隔见稍大淋巴结", "气管前腔静脉后见肿大淋巴结"], None, 0.08),
        _d("胸腔积液", ["无"], ["右侧少量胸腔积液", "双侧少量胸腔积液"], "lung", 0.10),
        _d("主动脉", ["未见异常"], ["主动脉壁见钙化斑", "主动脉硬化表现"], "blood_pressure", 0.20),
    ],
    "腹部超声": [
        _d("肝脏", ["形态大小正常，回声均匀"], ["弥漫性回声增强（脂肪肝倾向）", "肝内见囊性无回声区"], "fatty_liver", 0.20),
        _d("胆囊", ["壁薄光滑，腔内未见异常"], ["胆囊壁毛糙、增厚", "胆囊内见强回声（结石可能）"], None, 0.12),
        _d("胰腺", ["形态正常，回声均匀"], ["胰腺回声增强"], None, 0.06),
        _d("脾脏", ["大小正常"], ["脾脏稍大"], None, 0.06),
        _d("双肾", ["形态大小正常，集合系统未见分离"], ["右肾见囊肿", "双肾皮质回声增强"], None, 0.12),
    ],
    "血常规 + CRP": [
        _m("白细胞计数", 6.2, 3.5, 9.5, "×10⁹/L", 0.8),
        _m("红细胞计数", 4.7, 4.3, 5.8, "×10¹²/L", 0.3),
        _m("血红蛋白", 145, 130, 175, "g/L", 6, 0),
        _m("血小板计数", 235, 125, 350, "×10⁹/L", 22),
        _m("C反应蛋白", 2.1, 0, 10, "mg/L", 1.2),
    ],
    "心电图": [
        _m("心率", 76, 60, 100, "次/分", 8, 0),
        _m("PR间期", 0.16, 0.12, 0.20, "s", 0.02, 2),
        _m("QRS时限", 0.09, 0.06, 0.11, "s", 0.01, 2),
        _d("ST段", ["未见明显偏移"], ["ST段下移 0.05mV", "ST段抬高 0.1mV"], "cardiac", 0.15),
        _d("T波", ["形态正常"], ["T波低平", "T波倒置"], "cardiac", 0.15),
        _d("心律", ["窦性心律"], ["窦性心律不齐", "偶发房性早搏", "偶发室性早搏"], "cardiac", 0.10),
    ],
    "心脏彩色多普勒超声": [
        _m("左室射血分数(EF)", 62, 50, 75, "%", 4, 0),
        _m("左房内径", 34, 27, 40, "mm", 2.5),
        _m("室间隔厚度", 10, 8, 12, "mm", 1.2, 1),
        _d("瓣膜反流", ["各瓣膜启闭正常"], ["二尖瓣轻度反流", "主动脉瓣轻度反流"], "cardiac", 0.18),
        _d("室壁运动", ["未见节段性运动异常"], ["下壁节段性运动减弱"], "cardiac", 0.10),
    ],
    "肝功能全套": [
        _m("谷丙转氨酶(ALT)", 24, 9, 50, "U/L", 4),
        _m("谷草转氨酶(AST)", 22, 15, 40, "U/L", 4),
        _m("总胆红素", 13, 5, 21, "μmol/L", 2.2),
        _m("白蛋白", 44, 40, 55, "g/L", 2.5),
        _m("γ-谷氨酰转肽酶(GGT)", 28, 10, 60, "U/L", 6),
    ],
    "肾功能 + 电解质": [
        _m("肌酐", 78, 57, 111, "μmol/L", 7),
        _m("尿素氮", 5.2, 2.9, 8.2, "mmol/L", 0.8),
        _m("尿酸", 340, 208, 428, "μmol/L", 25),
        _m("钾", 4.1, 3.5, 5.3, "mmol/L", 0.25, 2),
        _m("钠", 140, 137, 147, "mmol/L", 1.8),
        _m("钙", 2.35, 2.11, 2.52, "mmol/L", 0.08, 2),
    ],
    "糖化血红蛋白": [
        _m("糖化血红蛋白(HbA1c)", 5.6, 4.0, 6.0, "%", 0.35, 1),
        _m("空腹血糖", 5.4, 3.9, 6.1, "mmol/L", 0.45, 1),
        _m("餐后2小时血糖", 7.1, 3.9, 7.8, "mmol/L", 0.8),
    ],
    "甲状腺功能五项": [
        _m("促甲状腺激素(TSH)", 2.1, 0.27, 4.2, "mIU/L", 0.5, 2),
        _m("游离T3(FT3)", 4.6, 3.1, 6.8, "pmol/L", 0.7, 2),
        _m("游离T4(FT4)", 15.8, 12.0, 22.0, "pmol/L", 1.8),
        _m("甲状腺过氧化物酶抗体(TPOAb)", 18, 0, 34, "IU/mL", 6),
        _m("甲状腺球蛋白抗体(TgAb)", 22, 0, 115, "IU/mL", 8),
    ],
    "脑电图": [
        _d("背景节律", ["α节律分布正常"], ["α节律偏慢", "背景节律慢化"], "cardiac", 0.12),
        _d("慢波", ["未见明显慢波"], ["颞区散在θ波", "双侧弥漫性θ活动"], None, 0.12),
        _d("棘波/尖波", ["未见"], ["颞区偶见尖波"], "cardiac", 0.08),
        _d("过度换气反应", ["正常"], ["诱发出现慢波增多"], None, 0.08),
    ],
    "骨密度测定": [
        _m("腰椎L1-L4 T值", -0.6, -2.5, 1.0, "", 0.45, 2),
        _m("股骨颈 T值", -0.4, -2.5, 1.0, "", 0.4, 2),
        _d("骨密度结论", ["骨量正常"], ["骨量减少", "骨质疏松（T值<-2.5）"], "bone", 0.18),
    ],
}


# 通用兜底模板（未匹配到具体项目时）
GENERIC_TEMPLATE: list[dict[str, Any]] = [
    _d("检查所见", ["未见明显异常"], ["见轻度异常改变"], None, 0.10),
]


# =============================================================================
# 病历 → 风险标记
# =============================================================================

def _has_any(keywords: list[str], haystack: list[str]) -> bool:
    for item in haystack or []:
        for kw in keywords:
            if kw in str(item):
                return True
    return False


def build_risk_flags(
    *,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    allergies: Optional[list[str]] = None,
    past_history: Optional[list[str]] = None,
    family_history: Optional[list[str]] = None,
    lifestyle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """把患者病历归纳为一组风险标记，供指标生成时做偏移。"""
    past = past_history or []
    family = family_history or []
    life = lifestyle or {}
    flags: dict[str, Any] = {
        "age": age,
        "gender": gender,
        "flags": set(),
        "context_notes": [],
    }

    def mark(keyword_groups: list[tuple[list[str], str]], haystack: list[str]) -> None:
        for keywords, flag in keyword_groups:
            if _has_any(keywords, haystack):
                flags["flags"].add(flag)

    mark(
        [
            (["高血压", "血压偏高", "血压升高"], "blood_pressure"),
            (["糖尿病", "血糖偏高", "血糖异常", "糖耐量"], "diabetes"),
            (["贫血", "缺铁", "血红蛋白低"], "anemia"),
            (["高血脂", "高脂血症", "血脂异常", "胆固醇高"], "lipids"),
            (["脂肪肝", "肝回声增强"], "fatty_liver"),
            (["冠心病", "心律不齐", "心律失常", "早搏", "房颤"], "cardiac"),
            (["慢性支气管炎", "慢阻肺", "肺气肿", "哮喘", "肺结核"], "lung"),
            (["甲状腺结节", "甲亢", "甲减", "桥本"], "thyroid"),
            (["骨质疏松", "骨量减少"], "bone"),
        ],
        past,
    )
    mark(
        [
            (["高血压", "心脑血管"], "blood_pressure"),
            (["糖尿病"], "diabetes"),
            (["冠心病", "心脏病"], "cardiac"),
            (["骨质疏松"], "bone"),
        ],
        family,
    )

    # 生活方式
    smoking = str(life.get("smoking", "") or life.get("smoke", "") or "").strip()
    if smoking and "无" not in smoking and "否" not in smoking and smoking != "0":
        flags["flags"].add("lung")
        flags["context_notes"].append("长期吸烟史")
    drinking = str(life.get("drinking", "") or life.get("alcohol", "") or "").strip()
    if drinking and "无" not in drinking and "否" not in drinking and drinking != "0":
        flags["flags"].add("liver")
        flags["context_notes"].append("长期饮酒史")

    # 年龄倾向
    if age is not None:
        if age >= 60:
            flags["flags"].add("elderly")
            flags["context_notes"].append(f"{age} 岁")
        elif age <= 12:
            flags["flags"].add("child")

    return flags


# =============================================================================
# 指标生成
# =============================================================================

def _gen_metric(spec: dict[str, Any], flags: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    name = spec["name"]
    if spec["kind"] == _NUM:
        base = spec["base"]
        ref_low, ref_high = spec["ref"]
        value = base + rng.uniform(-spec["spread"], spec["spread"])

        # 按病历对相关指标做倾向性偏移
        bias = 0.0
        fl = flags["flags"]
        if name in ("血红蛋白", "红细胞计数") and "anemia" in fl:
            bias = -12 if name == "血红蛋白" else -0.4
        elif "空腹血糖" in name or name == "糖化血红蛋白(HbA1c)" or "餐后2小时血糖" in name:
            if "diabetes" in fl:
                bias = 1.4 if name != "糖化血红蛋白(HbA1c)" else 1.0
            elif "child" in fl:
                bias = -0.3
        elif name in ("谷丙转氨酶(ALT)", "谷草转氨酶(AST)", "γ-谷氨酰转肽酶(GGT)") and "liver" in fl:
            bias = 14 if name == "谷丙转氨酶(ALT)" else 8
        elif name in ("尿酸",) and ("blood_pressure" in fl or "lipids" in fl):
            bias = 30
        elif name in ("腰椎L1-L4 T值", "股骨颈 T值") and ("bone" in fl or "elderly" in fl):
            bias = -0.8 if "bone" in fl else -0.3
        elif name == "心率" and "cardiac" in fl:
            bias = rng.choice([-8, 6, 12])
        elif name in ("左室射血分数(EF)",) and "cardiac" in fl:
            bias = -5
        elif name == "促甲状腺激素(TSH)" and "thyroid" in fl:
            bias = rng.choice([-1.2, 2.0])

        value += bias
        decimals = spec.get("decimals", 1)
        value = round(value, decimals)

        if value > ref_high:
            status = "high"
        elif value < ref_low:
            status = "low"
        else:
            status = "normal"

        return {
            "name": name,
            "value": str(value),
            "unit": spec["unit"],
            "reference_range": f"{ref_low}-{ref_high}{spec['unit']}" if spec["unit"] else f"{ref_low}-{ref_high}",
            "status": status,
        }

    # 描述型
    abnormal_rate = spec.get("abnormal_rate", 0.12)
    flag = spec.get("abnormal_flag")
    fl = flags["flags"]
    forced = flag and flag in fl
    if forced or (not spec.get("normal_only") and rng.random() < abnormal_rate):
        value = rng.choice(spec["abnormal"])
        status = "abnormal"
    else:
        value = rng.choice(spec["normal"])
        status = "normal"
    return {
        "name": name,
        "value": value,
        "unit": "",
        "reference_range": "未见异常" if status == "normal" else "异常",
        "status": status,
    }


def _build_summary(exam_name: str, metrics: list[dict[str, Any]], flags: dict[str, Any]) -> str:
    abnormal = [m for m in metrics if m.get("status") != "normal"]
    parts = [f"{exam_name}检查完成。"]
    if not abnormal:
        parts.append("各项指标均在参考范围内，整体未见明显异常。")
    else:
        names = "、".join(m["name"] for m in abnormal[:4])
        parts.append(f"发现 {len(abnormal)} 项异常/可疑：{names}。")
    if flags.get("context_notes"):
        parts.append("结合病历：" + "，".join(flags["context_notes"]) + "，建议重点关注相关指标。")
    parts.append("本报告由 AI 按患者病历自动生成，仅供参考，请以医生正式报告为准。")
    return "".join(parts)


# =============================================================================
# 对外接口
# =============================================================================

def generate_report_data(
    *,
    patient_id: int,
    exam_item_id: int,
    exam_name: str,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    allergies: Optional[list[str]] = None,
    past_history: Optional[list[str]] = None,
    family_history: Optional[list[str]] = None,
    lifestyle: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """确定性生成一份结构化检查报告（同一患者+项目永远相同）。"""
    rng = random.Random(f"zhiyi-report:{patient_id}:{exam_item_id}:{exam_name}")
    flags = build_risk_flags(
        age=age,
        gender=gender,
        allergies=allergies,
        past_history=past_history,
        family_history=family_history,
        lifestyle=lifestyle,
    )
    template = TEMPLATES.get(exam_name) or GENERIC_TEMPLATE
    metrics = [_gen_metric(spec, flags, rng) for spec in template]
    summary = _build_summary(exam_name, metrics, flags)
    return {
        "metrics": metrics,
        "summary": summary,
        "source": "ai-dynamic",
    }


def generate_interpretation(exam_name: str, report_data: dict) -> str:
    """基于结构化报告数据生成 AI 解读（与 exam.py 原有规则一致）。"""
    metrics = report_data.get("metrics", [])
    summary = report_data.get("summary", "")
    abnormal = [m for m in metrics if m.get("status") != "normal"]

    if not metrics:
        return f"{exam_name}报告已录入，暂无结构化指标可供解读。"

    # 摘要里"结合病历：…"片段对解读有参考价值，其余为模板化说明，避免重复
    note = ""
    idx = summary.find("结合病历：")
    if idx >= 0:
        note = summary[idx:]
        end = note.find("本报告由 AI")
        if end > 0:
            note = note[:end]
    note_suffix = f" {note.strip()}" if note.strip() else ""

    if not abnormal:
        return f"{exam_name}各项指标均在参考范围内，整体未见明显异常。{note_suffix}"

    abnormal_text = "；".join(
        f"{m['name']}为{m['value']}{m.get('unit', '')}（{m.get('reference_range', '')}）"
        for m in abnormal
    )
    return (
        f"{exam_name}发现 {len(abnormal)} 项异常：{abnormal_text}。"
        f"建议结合临床症状进一步评估，必要时复查或转诊专科。{note_suffix}"
    )
