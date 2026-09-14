"""Shared training/inference contract; no inferred measurements or imputation."""
from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real

from data_manager.schema import POSITIVE, PROCESS_ALIASES, UNITS
from data_manager.validation import missing

CATEGORICAL_FEATURES = ("alloy", "temper", "process")
NUMERIC_FEATURES = ("thickness", "current", "voltage", "speed", "heat_input")
DEFAULT_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGETS = ("tensile_strength", "hardness", "elongation")
FEATURE_SCHEMA_VERSION = "1.0.0"


def validate_spec(feature_list=DEFAULT_FEATURES, target="tensile_strength") -> tuple[str, ...]:
    features = tuple(feature_list)
    if not features or len(set(features)) != len(features):
        raise ValueError("feature_list 不能为空或包含重复字段。")
    if set(features) - set(DEFAULT_FEATURES):
        raise ValueError("特征只能使用材料与焊接参数，不能包含性能、缺陷或来源字段。")
    if target not in TARGETS:
        raise ValueError(f"target 必须是 {', '.join(TARGETS)}。")
    return features


def numeric_value(name, value) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值，单位为 {UNITS[name]}。")
    if value < 0 or name in POSITIVE and value == 0:
        raise ValueError(f"{name} 超出允许范围。")
    return float(value)


def feature_record(parameters: Mapping, feature_list=DEFAULT_FEATURES) -> dict:
    """Accept canonical units only; caller must explicitly convert other units first."""
    if not isinstance(parameters, Mapping):
        raise ValueError("welding_parameters 必须是字段字典。")
    features = validate_spec(feature_list)
    result = {}
    for name in features:
        value = parameters.get(name)
        if missing(value):
            raise ValueError(f"缺少特征 {name}，不自动补齐焊接参数。")
        if name in NUMERIC_FEATURES:
            result[name] = numeric_value(name, value)
        else:
            if not isinstance(value, str):
                raise ValueError(f"{name} 必须是文本。")
            value = value.strip()
            result[name] = (PROCESS_ALIASES.get(value.lower(), value) if name == "process" else value.upper())
    return result


def feature_domain(records, features) -> dict:
    """Observed training range/categories, never a claim about model validity."""
    return {name: ({"min": min(r[name] for r in records), "max": max(r[name] for r in records)}
                   if name in NUMERIC_FEATURES else {"values": sorted({r[name] for r in records})})
            for name in features}


def domain_warnings(record, domain) -> list[str]:
    warnings = []
    for name, value in record.items():
        bounds = domain[name]
        if "values" in bounds:
            if value not in bounds["values"]:
                warnings.append(f"{name}={value} 未出现在训练数据中。")
        elif not bounds["min"] <= value <= bounds["max"]:
            warnings.append(f"{name} 超出训练数据范围 [{bounds['min']}, {bounds['max']}]。")
    return warnings


def build_preprocessor(feature_list):
    """Lazy optional dependency. Must be fitted only on the training partition."""
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    features = validate_spec(feature_list)
    transformers = []
    numeric = [f for f in features if f in NUMERIC_FEATURES]
    categorical = [f for f in features if f in CATEGORICAL_FEATURES]
    if numeric:
        transformers.append(("numeric", StandardScaler(), numeric))
    if categorical:
        transformers.append(("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical))
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0)
