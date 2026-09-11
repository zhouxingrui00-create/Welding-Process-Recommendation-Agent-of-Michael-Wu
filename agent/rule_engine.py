from __future__ import annotations

from typing import Any

from agent.models import WeldingRequest


METHODS = ("TIG", "MIG", "激光焊", "FSW")


class RuleEngine:
    def recommend(self, request: WeldingRequest, material: dict[str, Any]) -> dict[str, Any]:
        scores = {"TIG": 50, "MIG": 45, "激光焊": 20, "FSW": 5}
        reasons: dict[str, list[str]] = {method: [] for method in METHODS}

        if request.thickness_mm <= 4:
            scores["TIG"] += 20
            reasons["TIG"].append("薄板更便于用 TIG 精细控制热输入和熔池")
        else:
            scores["MIG"] += 20
            reasons["MIG"].append("中厚板通常更重视熔敷效率")

        if request.low_distortion:
            scores["激光焊"] += 12
            scores["FSW"] += 12
            scores["TIG"] -= 5
            reasons["激光焊"].append("低变形要求倾向高能量密度、小热影响区方案")
            reasons["FSW"].append("固相连接可减少熔化凝固相关变形")

        if request.high_strength:
            scores["FSW"] += 12
            reasons["FSW"].append("高强度要求需优先评估固相连接和接头性能验证")

        if request.crack_focus:
            scores["FSW"] += 8
            reasons["FSW"].append("固相过程可避开凝固热裂纹机制")

        high_risk = material.get("fusion_risk_level") == "高"
        if high_risk:
            scores["TIG"] -= 70
            scores["MIG"] -= 75
            scores["激光焊"] -= 40
            scores["FSW"] += 70
            reasons["FSW"].append("该合金传统熔焊风险高，优先评估经验证的固相连接")

        if request.joint_type in ("对接", "搭接"):
            scores["FSW"] += 10
        else:
            scores["FSW"] -= 35
            reasons["FSW"].append("当前接头几何可能限制常规 FSW 工装与可达性")

        if request.position != "平焊":
            scores["FSW"] -= 20
            scores["激光焊"] -= 8

        ranked = sorted(METHODS, key=lambda item: scores[item], reverse=True)
        requested_override = request.preferred_method != "自动推荐"
        primary = request.preferred_method if requested_override else ranked[0]
        alternatives = [item for item in ranked if item != primary][:2]

        warnings: list[str] = []
        if high_risk and primary in ("TIG", "MIG", "激光焊"):
            warnings.append(
                f"{request.alloy} 属于传统熔焊高风险材料；所选 {primary} 仅作为待评审方案，"
                "不提供通用精确参数，必须由焊接工程师评估并完成工艺评定。"
            )
        if primary in ("激光焊", "FSW"):
            warnings.append(f"种子库尚无可直接下发的 {primary} 数值参数，仅给出方法级建议。")

        primary_reasons = reasons[primary] or ["根据材料、板厚、接头与性能要求的基础规则排序"]
        if requested_override:
            primary_reasons.insert(0, "尊重用户指定方法；系统仍保留风险审查与备选方法")
        return {
            "primary": primary,
            "alternatives": alternatives,
            "reason": "；".join(primary_reasons),
            "scores": scores,
            "warnings": warnings,
            "requested_override": requested_override,
        }
