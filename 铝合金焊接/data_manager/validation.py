"""Deterministic data checks. No imputation, prediction, or training."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import chain

from .importers import RawTable
from .schema import CONVERSIONS, FIELDS, POSITIVE, PROCESS_ALIASES, REQUIRED, SCHEMA_VERSION, UNITS

MISSING = {"", "na", "n/a", "null", "none", "nan", "未知", "待补充", "未提供"}


def missing(value):
    return value is None or isinstance(value, str) and value.strip().lower() in MISSING


def unit_key(unit):
    compact = str(unit).strip().replace(" ", "").replace("²", "2").replace("μ", "u").replace("µ", "u").replace("％", "%")
    # SI prefixes are case-sensitive: MA/MV/Mm/mPa cannot be silently read as milli/mega.
    if compact in {"MA", "MV", "Mm", "mPa", "M/s", "M/min", "Mm/s", "Mm/min"}:
        return "unsupported:" + compact
    return compact.lower()


def fingerprint(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def measurement_fingerprint(record):
    # All-empty templates and repeated legitimate measurements with different IDs are not auto-deleted.
    if not any(record.get(f) is not None for f in UNITS):
        return None
    return fingerprint({f: record.get(f) for f in FIELDS if f not in ("paper", "experiment_id", "source")})


@dataclass
class ValidationReport:
    records: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    issue_counts: Counter = field(default_factory=Counter)
    severity_counts: Counter = field(default_factory=Counter)
    row_numbers: list[int] = field(default_factory=list)
    missing_counts: Counter = field(default_factory=Counter)
    input_count: int = 0

    def add(self, severity, code, row, name, message):
        self.issue_counts[code] += 1
        self.severity_counts[severity] += 1
        if len(self.issues) < 2000:
            self.issues.append(dict(severity=severity, code=code, row=row, field=name, message=message))

    @property
    def ok(self):
        return not self.severity_counts["error"]

    def summary(self):
        return {"schema_version": SCHEMA_VERSION, "ok": self.ok, "input_count": self.input_count,
                "error_count": self.severity_counts["error"], "warning_count": self.severity_counts["warning"],
                "issue_counts": dict(self.issue_counts), "missing_counts": dict(self.missing_counts),
                "issues": self.issues, "issues_truncated": sum(self.issue_counts.values()) > len(self.issues)}


def validate(table: RawTable, *, dataset="research", assume_canonical_units=False) -> ValidationReport:
    report = ValidationReport(input_count=len(table.rows))
    if not table.rows:
        report.add("error", "empty_dataset", None, "", "没有可导入记录。")
    for name in table.units:
        if name not in UNITS:
            report.add("error", "unknown_unit_field", None, name, "单位映射包含未知或非数值字段。")
    for raw in table.rows:
        row, values = raw["row"], raw["values"]
        mapped, units = {}, dict(table.units)
        for header, value in values.items():
            match = re.fullmatch(r"([a-z_]+)\s*\[([^\]]+)\]", header)
            name, declared = (match.group(1), match.group(2)) if match else (header, None)
            if name.endswith("_unit") and name[:-5] in UNITS:
                continue
            if name not in FIELDS and name != "record_kind":
                report.add("error", "unknown_field", row, name, "未知字段；请显式映射到 Schema，避免静默丢失。")
                continue
            if name in mapped:
                report.add("error", "duplicate_column", row, name, "多个列映射到同一字段。")
            mapped[name] = value
            declarations = [u for u in (units.get(name), declared, values.get(name + "_unit")) if not missing(u)]
            if len({unit_key(u) for u in declarations}) > 1:
                report.add("error", "unit_conflict", row, name, "列、单元格或全局单位声明冲突。")
            if declarations:
                units[name] = declarations[-1]
                if name not in UNITS:
                    report.add("error", "invalid_unit", row, name, "文本字段不应包含单位声明。")
        record = {}
        for name in FIELDS:
            value = mapped.get(name)
            if missing(value):
                record[name] = None
                report.missing_counts[name] += 1
                if name in REQUIRED:
                    report.add("error", "missing_required", row, name, "必填来源/材料字段缺失。")
                continue
            if name not in UNITS:
                if not isinstance(value, str):
                    report.add("error", "invalid_type", row, name, "应为文本；编号请在 Excel 中保存为文本。")
                    record[name] = None
                    continue
                value = value.strip()
                if value.startswith("="):
                    report.add("error", "formula", row, name, "请导入原始文本或数值，不导入公式。")
                if name in ("alloy", "temper"):
                    value = value.upper()
                if name == "process":
                    value = PROCESS_ALIASES.get(value.lower(), value)
                if name == "crack":
                    value = {"有": "present", "无": "absent", "是": "present", "否": "absent",
                             "true": "present", "false": "absent"}.get(value.lower(), value.lower())
                    if value not in ("present", "absent", "unknown"):
                        report.add("error", "invalid_category", row, name, "裂纹应为 present / absent / unknown。")
                record[name] = value
                continue
            declared = units.get(name)
            if isinstance(value, dict):
                if set(value) != {"value", "unit"}:
                    report.add("error", "invalid_type", row, name, "数值对象只支持 value 和 unit。")
                cell_unit = value.get("unit")
                if declared and cell_unit and unit_key(declared) != unit_key(cell_unit):
                    report.add("error", "unit_conflict", row, name, "数值对象与外部单位冲突。")
                declared = cell_unit or declared
                value = value.get("value")
                if missing(value):
                    record[name] = None
                    report.missing_counts[name] += 1
                    continue
            if isinstance(value, str):
                match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*", value)
                if match:
                    value, inline_unit = match.groups()
                    if inline_unit:
                        if declared and unit_key(declared) != unit_key(inline_unit):
                            report.add("error", "unit_conflict", row, name, "数值后缀与声明单位冲突。")
                        declared = inline_unit
            try:
                if isinstance(value, bool):
                    raise ValueError()
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError()
            except (ValueError, TypeError, OverflowError):
                report.add("error", "invalid_number", row, name, "需要有限数值，不能是公式、区间或定性描述。")
                record[name] = None
                continue
            if not declared:
                if assume_canonical_units:
                    declared = UNITS[name]
                    report.add("warning", "assumed_unit", row, name, f"使用用户声明的标准单位 {declared}。")
                else:
                    report.add("error", "missing_unit", row, name, f"缺少单位；标准单位为 {UNITS[name]}。")
            factor = CONVERSIONS[UNITS[name]].get(unit_key(declared))
            if factor is None:
                if declared:
                    report.add("error", "invalid_unit", row, name, f"不支持单位 {declared}；目标 {UNITS[name]}。")
                record[name] = None
                continue
            number *= factor
            if not math.isfinite(number) or number < 0 or name in POSITIVE and number == 0 or name == "porosity" and number > 100:
                report.add("error", "out_of_range", row, name, "数值违反 Schema 范围，请核对录入及单位。")
                record[name] = None
                continue
            record[name] = number
        kind = mapped.get("record_kind") or "experimental"
        if kind not in ("experimental", "schema_test"):
            report.add("error", "invalid_kind", row, "record_kind", "不支持的记录性质。")
            kind = None
        if dataset == "research" and (kind == "schema_test" or str(record.get("source", "")).startswith("demo_placeholder")):
            report.add("error", "demo_in_research", row, "record_kind", "测试占位记录只能导入 Demo 仓库。")
        if dataset == "demo" and kind != "schema_test":
            report.add("error", "research_in_demo", row, "record_kind", "Demo 仓库仅接受 schema_test 记录。")
        record["record_kind"] = kind
        report.records.append(record)
        report.row_numbers.append(row)
    for name, count in report.missing_counts.items():
        if name not in REQUIRED:
            report.add("warning", "missing_optional", None, name, f"{count} 条记录缺失；保留为空，不填补。")
    return report


def check_duplicates(report, existing):
    identities, contents, measurements = set(), set(), set()
    for record in existing:
        identities.add((record["source"], record["experiment_id"]))
        contents.add(fingerprint(record))
        measured = measurement_fingerprint(record)
        if measured:
            measurements.add(measured)
    for row, record in zip(report.row_numbers, report.records):
        identity = (record.get("source"), record.get("experiment_id"))
        content = fingerprint(record)
        measured = measurement_fingerprint(record)
        if identity in identities or content in contents:
            report.add("error", "duplicate", row, "experiment_id", "与本批或已入库记录重复（source + experiment_id / 完整记录）。")
        elif measured and measured in measurements:
            report.add("warning", "possible_duplicate", row, "experiment_id", "材料、工艺和测量值相同但来源编号不同，请复核是否重复摘录或平行实验。")
        identities.add(identity)
        contents.add(content)
        if measured:
            measurements.add(measured)


def check_outliers(report, existing):
    # Review-only 3*IQR fences, computed per alloy/temper/process and field with >= 8 observations.
    groups = defaultdict(list)
    requested_groups = {(record.get("alloy"), record.get("temper"), record.get("process"), name)
                        for record in report.records for name in UNITS if record.get(name) is not None}
    if not requested_groups:
        return
    for record in chain(existing, report.records):
        for name in UNITS:
            value = record.get(name)
            key = (record.get("alloy"), record.get("temper"), record.get("process"), name)
            if value is not None and key in requested_groups:
                groups[key].append(value)
    fences = {}
    for key, numbers in groups.items():
        if len(numbers) < 8:
            continue
        numbers.sort()
        def quantile(p):
            index = (len(numbers) - 1) * p
            lower = int(index)
            return numbers[lower] + (numbers[min(lower+1, len(numbers)-1)] - numbers[lower]) * (index-lower)
        q1, q3 = quantile(.25), quantile(.75)
        fences[key] = (q1 - 3 * (q3-q1), q3 + 3 * (q3-q1))
    for row, record in zip(report.row_numbers, report.records):
        for name in UNITS:
            value = record.get(name)
            bounds = fences.get((record.get("alloy"), record.get("temper"), record.get("process"), name))
            if value is not None and bounds and not bounds[0] <= value <= bounds[1]:
                report.add("warning", "statistical_outlier", row, name, "超出同材料/状态/方法组的 3×IQR 范围；仅标记复核，不删除或修改。")
