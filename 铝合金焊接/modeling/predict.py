"""Agent-facing prediction API with explicit unavailable/uncertainty states."""
from __future__ import annotations

import math

from data_manager.schema import UNITS
from .feature_engineering import domain_warnings, feature_record, validate_spec
from .registry import ModelRegistry


def predict(welding_parameters, *, target="tensile_strength", model_version=None, registry=None) -> dict:
    result = {"status": "no_model", "message": "暂无训练模型", "model_version": None,
              "target": target, "predicted_performance": {},
              "confidence": {"available": False, "method": None, "value": None,
                             "standard_deviation": None, "reason": "暂无训练模型"}, "warnings": []}
    registry = registry if registry is not None else ModelRegistry()
    try:
        validate_spec(target=target)
        if model_version:
            metadata = registry.get(model_version)
        else:
            candidates = registry.list_models(target=target, trained_only=True)
            result["warnings"] = list(registry.warnings)
            metadata = candidates[0] if candidates else None
        if metadata is None or metadata["status"] != "trained":
            return result
        if metadata["target"] != target:
            raise ValueError("所选模型的 target 与预测请求不一致。")
        record = feature_record(welding_parameters, metadata["feature_list"])
    except (ValueError, TypeError) as exc:
        result.update(status="invalid_input", message=str(exc))
        return result
    except (OSError, KeyError) as exc:
        result.update(status="model_unavailable", message=f"模型不可用：{exc}")
        return result
    result["model_version"] = metadata["model_version"]
    try:
        warnings = domain_warnings(record, metadata["feature_domain"])
        result["warnings"].extend(warnings)
        # Unknown categories are not silently treated as a supported welding domain.
        if warnings:
            result.update(status="out_of_domain", message="参数超出训练范围，暂不提供外推预测。")
            result["confidence"]["reason"] = "参数超出训练范围。"
            return result
        model = registry.load_model(metadata["model_version"])
        values = list(model.predict([record]))
        if len(values) != 1 or not math.isfinite(float(values[0])):
            raise ValueError("模型未返回单个有限预测值。")
        uncertainty = model.uncertainty([record])
        std = None
        if uncertainty["available"]:
            deviations = uncertainty["standard_deviation"]
            if len(deviations) != 1:
                raise ValueError("模型不确定性维度不一致。")
            std = float(deviations[0])
            if not math.isfinite(std) or std < 0:
                raise ValueError("模型不确定性无效。")
        result.update(status="ok", message="预测完成。", data_version=metadata["data_version"],
                      predicted_performance={target: {"value": float(values[0]), "unit": UNITS[target]}},
                      confidence={"available": uncertainty["available"], "method": uncertainty["method"],
                                  "value": None, "standard_deviation": std,
                                  "unit": UNITS[target] if std is not None else None,
                                  "reason": uncertainty["reason"]})
    except Exception as exc:
        result.update(status="model_unavailable", message=f"模型不可用：{exc}")
        result["confidence"]["reason"] = "模型加载或推理未成功。"
    return result


class WeldingPredictor:
    def __init__(self, *, registry=None, target="tensile_strength", model_version=None):
        self.registry, self.target, self.model_version = registry, target, model_version

    def predict(self, welding_parameters) -> dict:
        return predict(welding_parameters, registry=self.registry, target=self.target, model_version=self.model_version)
