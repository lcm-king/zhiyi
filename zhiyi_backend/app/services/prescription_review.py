"""
智医 (ZhiYi) — 处方合理性审核服务
基层医疗AI辅助诊疗平台

规则引擎 + 可选 AI 复核，输出统一的审核结论：
  passed  是否通过
  risk    风险等级 low / medium / high
  warnings 风险提示列表
  suggestion 综合建议

该逻辑同时被 RabbitMQ 异步消费者和 admin/orders 兜底使用，
保证异步链路与同步展示口径一致。
"""

from __future__ import annotations

from typing import Any


def review_prescription(
    drug_names: list[str],
    *,
    quantity: int = 0,
    allergies: list[str] | None = None,
) -> dict[str, Any]:
    """对处方（药品订单）执行规则审核。

    参数:
        drug_names: 药品名称列表（用于识别抗生素/降压药等）
        quantity:   总药品数量（多药联用风险）
        allergies:  患者过敏史（过敏风险）

    返回:
        {passed, risk, warnings, suggestion}
    """
    warnings: list[str] = []

    # 1. 多药联用数量风险
    if quantity >= 5:
        warnings.append("多药联用（≥5 种），需评估药物相互作用风险")
    if len(drug_names) >= 3:
        warnings.append(f"同时开具 {len(drug_names)} 种药品，建议分批处理主要病症后观察")

    # 2. 抗生素类风险
    if any(("抗生素" in n or "阿莫西林" in n or "头孢" in n) for n in drug_names):
        warnings.append("含抗生素类药物，需确认患者无过敏史及感染指征")

    # 3. 降压药风险
    if any(("降压" in n or "缓释片" in n) for n in drug_names):
        warnings.append("降压药需监测血压，起始剂量宜低，逐步调整")

    # 4. 过敏史匹配（严重，直接高风险）
    allergy_alert = False
    if allergies:
        for name in drug_names:
            for allergen in allergies:
                if allergen and allergen in name:
                    warnings.append(f"患者对「{allergen}」过敏，禁用含该成分的「{name}」")
                    allergy_alert = True

    passed = len(warnings) == 0
    if allergy_alert:
        risk = "high"
    elif len(warnings) >= 2:
        risk = "high"
    elif len(warnings) == 1:
        risk = "medium"
    else:
        risk = "low"

    suggestion = (
        "处方合理，可按常规剂量使用。注意监测不良反应。"
        if passed
        else f"处方存在 {len(warnings)} 项风险提示，建议医生复核确认后执行。"
    )

    return {
        "passed": passed,
        "risk": risk,
        "warnings": warnings,
        "suggestion": suggestion,
        "allergy_alert": allergy_alert,
    }
