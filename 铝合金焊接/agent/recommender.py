from __future__ import annotations

from typing import Any

from agent.models import Recommendation, WeldingRequest
from agent.rule_engine import RuleEngine
from agent.safety_checker import ParameterSafetyChecker
from services.data_service import DataService
from services.llm.router import LLMRouter
from services.logging_service import RecommendationLogger
from services.rag_service import RagService


class WeldingRecommender:
    def __init__(
        self,
        data_service: DataService | None = None,
        rag_service: RagService | None = None,
        llm_service: LLMRouter | None = None,
        logger: RecommendationLogger | None = None,
    ) -> None:
        self.data = data_service or DataService()
        self.rag = rag_service or RagService()
        self.llm = llm_service or LLMRouter()
        self.logger = logger or RecommendationLogger()
        self.rules = RuleEngine()
        self.safety = ParameterSafetyChecker()

    @staticmethod
    def _risk_items(request: WeldingRequest, material: dict[str, Any]) -> list[dict[str, str]]:
        messages = {
            "热裂纹": "接头拘束、填充材料、熔池成分和热输入需共同评估，并通过试焊检查。",
            "液化裂纹": "高风险合金的热影响区可能发生晶界液化，不能套用普通铝合金熔焊参数。",
            "延迟应力腐蚀开裂": "焊后外观正常不代表服役安全，需评估残余拉应力、环境和寿命。",
            "热影响区软化": "热处理强化状态可能在HAZ显著降强，设计计算不得沿用母材状态强度。",
            "热影响区严重软化": "高强热处理合金的局部组织与性能变化必须通过接头试验量化。",
            "加工硬化状态HAZ软化": "H状态材料会局部丧失加工硬化效果，应核对焊态允许性能。",
            "气孔": "控制母材、焊丝和保护气系统中的水分、油污与泄漏，并检查气体保护。",
            "变形": "采用合理装夹、焊接顺序和受控热输入；低变形要求应做尺寸验证。",
            "氧化膜夹杂": "氧化膜熔点高，必须在焊前完成脱脂和专用机械清理。",
            "氧化膜与水分污染": "清理、干燥和防再污染是控制气孔及夹杂的关键。",
            "污染引起的氢孔": "铝熔池对氢敏感，应隔离水分、油污和受潮焊材。",
            "阳极氧化色差": "若焊后阳极氧化，应把填丝选择和外观验收纳入试样评估。",
            "Zn/Mg烧损与气孔": "挥发性合金元素和保护条件会影响成分及缺陷，须专项开发工艺。",
        }
        risks = [
            {"name": name, "level": "高" if material["fusion_risk_level"] == "高" else "中", "message": messages.get(name, "需要在试焊和检测中重点验证。")}
            for name in material["primary_risks"]
        ]
        if request.low_distortion and not any(item["name"] == "变形" for item in risks):
            risks.append({"name": "变形", "level": "中", "message": messages["变形"]})
        return risks

    @staticmethod
    def _fallback_explanation(
        request: WeldingRequest, material: dict[str, Any], method: dict[str, Any], has_numeric: bool
    ) -> str:
        parameter_status = (
            "结构化数据库中存在与当前条件相符的厂商示例起始参数；这些参数仍需试焊确认。"
            if has_numeric
            else "结构化数据库没有与当前厚度、接头和位置完全匹配的可靠数值，因此未给出精确设定值。"
        )
        return (
            f"{request.material_id} 属于 {material['series']} 系，{material['weldability']} "
            f"规则引擎把 {method['primary']} 作为当前首选，主要依据是：{method['reason']}。\n\n"
            f"{parameter_status} 推荐中的填充材料和通用操作要求也只是初选结果，"
            "需要结合焊机特性、装配间隙、拘束度和实际散热条件确认。\n\n"
            "正式使用前应编制并评定WPS/PQR；安全关键构件还必须按适用产品标准和设计要求审查。"
        )

    @staticmethod
    def _validation_items(
        request: WeldingRequest, material: dict[str, Any], parameters: list[dict[str, Any]]
    ) -> list[str]:
        items = [
            "用同牌号、同状态、同厚度和代表性接头做试焊，记录实际设备程序与环境条件。",
            "按适用标准完成WPS/PQR或等效工艺评定，并由有资质人员审核。",
            "至少验证外观、尺寸、表面/体积缺陷；承载接头增加所需力学性能试验。",
            "核对每个数值参数的来源适用条件，示例数据不得直接作为生产设定。",
        ]
        if material["fusion_risk_level"] == "高":
            items.insert(0, "2024/7075类高风险材料不得未经专项工程评审用于传统熔焊承载构件。")
            items.append("若采用FSW，仍需对工具、装夹、缺陷、残余性能和腐蚀行为做专项评定。")
        if any(param.get("example_data") for param in parameters):
            items.append("本结果含“示例数据”标记项，只能作为试验起点，不能视为已批准工艺。")
        if not request.allow_preheat:
            items.append("用户未允许预热；任何预热措施必须先获得工艺授权并重新审查热影响。")
        return items

    def recommend(self, request: WeldingRequest, use_llm: bool = True, write_log: bool = True) -> Recommendation:
        material = self.data.get_material(request)
        method = self.rules.recommend(request, material)
        filler = self.data.select_filler(material, request)
        raw_parameters, conflicts = self.data.get_process_parameters(method["primary"], request, filler)
        parameters, notices = self.safety.check(raw_parameters)
        notices.extend(method["warnings"])
        if material.get("temper_warning"):
            notices.append(material["temper_warning"])
        if not parameters:
            notices.append("数据不足：没有与当前条件匹配且可追溯的工艺参数。")

        query = (
            f"铝合金 {request.material_id} {request.thickness_mm:g} mm {request.joint_type} "
            f"{method['primary']} 焊接性 热裂纹 气孔 软化 变形"
        )
        if request.alloy == "6A01":
            manager = self.data.material_manager
            dedicated = manager.get_knowledge(
                request.alloy, None if request.temper == "未知" else request.temper,
                method["primary"], request.thickness_mm,
            )
            retrieved = self.rag.search(query, material_priority="6A01")
            knowledge = sorted(dedicated + retrieved, key=lambda item: item["priority"])
            notices.append("资料优先级：6A01 专项数据库 → 6xxx 系列 → 通用铝合金知识；回退资料不能视为 6A01 实验结论。")
            notices.extend(manager.warnings)
            if not any(item["priority"] == 0 for item in knowledge):
                notices.append("当前条件没有匹配的 6A01 专项资料，已回退到系列 / 通用知识。")
        else:
            knowledge = self.rag.search(query)
        conflicts.extend(self.rag.detect_potential_conflicts(knowledge))
        conflicts = sorted(set(conflicts))
        risks = self._risk_items(request, material)
        has_numeric = any(isinstance(param.get("value"), dict) for param in parameters)
        fallback = self._fallback_explanation(request, material, method, has_numeric)
        llm_status: dict[str, Any]
        explanation = fallback
        if use_llm:
            llm_context = {
                "material": {
                    "id": request.material_id,
                    "system": material["alloy_system"],
                    "strengthening": material["strengthening"],
                    "weldability": material["weldability"],
                    "risks": material["primary_risks"],
                },
                "method": {key: method[key] for key in ("primary", "alternatives", "reason", "warnings")},
                "parameter_names_only": [param["name"] for param in parameters],
                "knowledge": [
                    {"source": item["source"], "page": item.get("page"), "text": item["text"]}
                    for item in knowledge
                ],
                "required_conclusion": "所有参数需试焊和WPS/PQR验证。",
            }
            if request.alloy == "6A01":
                llm_context["material"]["data_status"] = (
                    "6A01 专项模块仅供资料查询；无已验证工艺、无已训练预测模型。"
                    "系列和通用资料不得描述为该牌号实验结果；来源缺失项不得视为可靠结论。"
                )
                llm_context["knowledge"] = [
                    {"source": item["source"], "page": item.get("page"),
                     "material_scope": item["material_scope"], "text": item["text"]}
                    for item in knowledge
                ]
            response = self.llm.explain(llm_context)
            llm_status = {
                "available": response.available,
                "model": response.model,
                "message": response.message,
                "attempts": response.attempts,
            }
            if response.available:
                valid, safety_message = self.safety.validate_llm_explanation(response.text)
                if valid:
                    explanation = response.text
                else:
                    notices.append(safety_message)
                    llm_status["message"] = safety_message
        else:
            llm_status = {"available": False, "model": self.llm.model, "message": "本次运行已禁用LLM。"}

        result = Recommendation(
            request=request,
            material=material,
            method=method,
            parameters=parameters,
            risks=risks,
            knowledge=knowledge,
            explanation=explanation,
            validation=self._validation_items(request, material, parameters),
            conflicts=conflicts,
            notices=sorted(set(notices)),
            llm_status=llm_status,
        )
        if write_log:
            record_id = self.logger.write(result.to_dict())
            result.notices.append(f"本次推荐已记录，日志ID：{record_id}")
        return result
