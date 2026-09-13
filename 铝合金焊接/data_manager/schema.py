"""Versioned research contract. Values are never filled or inferred."""
from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
GROUPS = {
    "材料": ("alloy", "temper", "thickness"),
    "焊接": ("process", "current", "voltage", "speed", "heat_input"),
    "性能": ("tensile_strength", "hardness", "elongation"),
    "缺陷": ("porosity", "crack", "undercut"),
    "来源": ("paper", "experiment_id", "source"),
}
FIELDS = tuple(field for fields in GROUPS.values() for field in fields)
REQUIRED = ("alloy", "experiment_id", "source")
UNITS = {
    "thickness": "mm", "current": "A", "voltage": "V", "speed": "mm/s",
    "heat_input": "kJ/mm", "tensile_strength": "MPa", "hardness": "HV",
    "elongation": "%", "porosity": "%", "undercut": "mm",
}
# Explicit conversions only; hardness scales and qualitative porosity cannot be converted.
CONVERSIONS = {
    "mm": {"mm": 1, "cm": 10, "m": 1000, "um": .001},
    "A": {"a": 1, "ka": 1000, "ma": .001},
    "V": {"v": 1, "kv": 1000, "mv": .001},
    "mm/s": {"mm/s": 1, "mm/min": 1/60, "m/min": 1000/60, "m/s": 1000},
    "kJ/mm": {"kj/mm": 1, "j/mm": .001, "kj/cm": .1, "j/cm": .0001},
    "MPa": {"mpa": 1, "gpa": 1000, "pa": .000001, "n/mm2": 1},
    "HV": {"hv": 1},
    "%": {"%": 1, "percent": 1, "fraction": 100},
}
POSITIVE = {"thickness", "speed", "tensile_strength", "hardness"}
PROCESS_ALIASES = {
    "tig": "TIG", "gtaw": "TIG", "mig": "MIG", "gmaw": "MIG",
    "fsw": "FSW", "搅拌摩擦焊": "FSW", "laser": "激光焊", "激光焊": "激光焊",
}


def schema_rows() -> list[dict]:
    return [{"分组": group, "字段": field, "类型": "number" if field in UNITS else "string",
             "标准单位": UNITS.get(field, ""), "必填": field in REQUIRED,
             "说明": {"porosity": "气孔率，百分数；不接受定性描述",
                      "crack": "present / absent / unknown；空白也表示未提供",
                      "undercut": "咬边深度", "hardness": "维氏硬度；不同标尺不能直接换算",
                      "heat_input": "只保存来源给出的热输入，不自动计算"}.get(field, "")}
            for group, fields in GROUPS.items() for field in fields]


def json_schema() -> dict:
    properties = {}
    for field in FIELDS:
        spec = {"type": ["number", "null"] if field in UNITS else ["string", "null"]}
        if field in REQUIRED:
            spec = {"type": "string", "minLength": 1}
        if field in UNITS:
            spec["x-unit"] = UNITS[field]
            spec["exclusiveMinimum" if field in POSITIVE else "minimum"] = 0
        if field == "porosity":
            spec["maximum"] = 100
        if field == "crack":
            spec["enum"] = ["present", "absent", "unknown", None]
        properties[field] = spec
    properties["record_kind"] = {"enum": ["experimental", "schema_test"]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Welding experiment normalized record", "schema_version": SCHEMA_VERSION,
            "type": "object", "additionalProperties": False,
            "required": list(FIELDS) + ["record_kind"], "properties": properties}
