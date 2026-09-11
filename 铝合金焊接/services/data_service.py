from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from agent.models import WeldingRequest
from services.material_manager import MaterialManager
from utils.paths import project_path


@lru_cache(maxsize=4)
def _load_json(relative_path: str) -> dict[str, Any]:
    with project_path(*relative_path.split("/")).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class DataService:
    def __init__(self, material_manager: MaterialManager | None = None) -> None:
        self.material_manager = material_manager or MaterialManager()
        self.material_db = _load_json("data/materials/materials.json")
        self.process_db = _load_json("data/processes/process_parameters.json")

    @property
    def material_sources(self) -> dict[str, Any]:
        return self.material_db["sources"]

    @property
    def process_sources(self) -> dict[str, Any]:
        return self.process_db["sources"]

    def get_material(self, request: WeldingRequest) -> dict[str, Any]:
        if request.alloy == "6A01":
            summary = self.material_manager.get_summary(request.alloy)
            # Adapter for the existing rule/display contract. Unknowns stay explicit;
            # no 6061 filler, risk rating, strength or process row is copied here.
            return {
                "alloy": "6A01", "series": "6xxx", "alloy_system": "专项资料待补充",
                "strengthening": "专项资料待补充", "weldability": "专项结论待补充；现阶段仅提供基础规则初选。",
                "fusion_risk_level": "未知", "primary_risks": [], "filler_options": [], "source_ids": [],
                "supported_tempers": summary["tempers"],
                "temper_warning": "6A01 专项数据库尚未形成已验证工艺；未知状态、性能与缺陷不作推定。",
                "specialized_data": summary,
                "data_priority": self.material_manager.get_priority(request.alloy),
                "related_cases": self.material_manager.get_welding_cases(
                    request.alloy, None if request.temper == "未知" else request.temper,
                    None if request.preferred_method == "自动推荐" else request.preferred_method,
                    request.thickness_mm,
                ),
            }
        for item in self.material_db["materials"]:
            if item["alloy"] == request.alloy:
                result = dict(item)
                supported = item["supported_tempers"]
                if request.temper not in supported and "H系列" not in supported:
                    result["temper_warning"] = (
                        f"种子库没有 {request.material_id} 的专门状态数据，"
                        "以下仅按合金系列给出定性分析。"
                    )
                else:
                    result["temper_warning"] = ""
                return result
        raise LookupError(f"材料数据库中没有 {request.alloy}。")

    def get_source(self, source_id: str) -> dict[str, Any]:
        if source_id in self.process_sources:
            return self.process_sources[source_id]
        if source_id in self.material_sources:
            return self.material_sources[source_id]
        return {"title": source_id, "url": "", "note": "来源定义缺失"}

    def select_filler(self, material: dict[str, Any], request: WeldingRequest) -> dict[str, Any] | None:
        options = material.get("filler_options", [])
        if not options:
            return None
        if request.crack_focus:
            for option in options:
                if "裂纹" in option.get("best_for", ""):
                    return option
        if request.high_strength:
            for option in options:
                if "强度" in option.get("best_for", ""):
                    return option
        return options[0]

    @staticmethod
    def _record_matches(record: dict[str, Any], request: WeldingRequest) -> bool:
        if record["method"] not in (request.preferred_method, "通用") and request.preferred_method != "自动推荐":
            return False
        thickness = record.get("thickness_mm")
        if thickness and not (thickness["min"] <= request.thickness_mm <= thickness["max"]):
            return False
        for field, value in (("alloys", request.alloy), ("joints", request.joint_type), ("positions", request.position)):
            allowed = record.get(field, ["*"])
            if "*" not in allowed and value not in allowed:
                return False
        return True

    def get_process_parameters(
        self, method: str, request: WeldingRequest, filler: dict[str, Any] | None
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if request.alloy == "6A01":
            # This phase only reads cases; it does not approve or convert them to WPS.
            return [], []
        matched = []
        for record in self.process_db["records"]:
            if record["method"] != method:
                continue
            if self._record_matches(record, request):
                matched.append(record)
        matched.sort(key=lambda item: item.get("specificity", 0))

        parameters: dict[str, dict[str, Any]] = {}
        conflicts: list[str] = []
        for record in matched:
            for param in record.get("parameters", []):
                name = param["name"]
                candidate = dict(param)
                candidate["record_id"] = record["id"]
                candidate["applicable_conditions"] = record["applicable_conditions"]
                candidate["source"] = self.get_source(param["source_id"])
                if name in parameters and parameters[name].get("value") != candidate.get("value"):
                    if record.get("specificity", 0) == parameters[name].get("specificity", -1):
                        conflicts.append(f"参数“{name}”存在同等适用级别的不同数据。")
                candidate["specificity"] = record.get("specificity", 0)
                parameters[name] = candidate

        if filler and method in ("TIG", "MIG"):
            parameters["焊丝/填充材料"] = {
                "name": "焊丝/填充材料",
                "value": filler["designation"],
                "unit": "",
                "source_id": filler["source_id"],
                "source": self.get_source(filler["source_id"]),
                "confidence": filler["confidence"],
                "example_data": filler["example_data"],
                "applicable_conditions": filler["conditions"],
                "record_id": f"material-{request.alloy}-filler",
                "specificity": 50,
                "note": filler.get("note", ""),
            }
        return list(parameters.values()), sorted(set(conflicts))
