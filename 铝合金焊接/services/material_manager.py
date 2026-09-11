"""Nullable, file-backed material data. Reads never create experimental records."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from utils.paths import project_path


RECORD_FIELDS = (
    "id", "alloy", "temper", "chemical_composition", "thickness_mm",
    "welding_method", "welding_parameters", "microstructure",
    "mechanical_properties", "defects", "source",
)
COLLECTIONS = ("properties", "welding_cases", "literature")


def has_data(value: Any) -> bool:
    if isinstance(value, dict):
        return any(has_data(item) for item in value.values())
    if isinstance(value, list):
        return any(has_data(item) for item in value)
    return value is not None and value != ""


class MaterialManager:
    """Query raw data without inferring missing values or promoting cases to WPS."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else project_path("data", "materials")
        self.warnings: list[str] = []

    @staticmethod
    def normalize_alloy(alloy: str) -> str:
        value = alloy.strip().upper()
        if not re.fullmatch(r"[0-9][A-Z0-9]{3}", value):
            raise ValueError("材料牌号应为四位字母数字，例如 6A01 或 6061。")
        return value

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8-sig")
            payload = json.loads(text) if text.strip() else {}
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            self._warn(f"{path.name} 无法读取或 JSON 无效，已按空数据处理。")
            return {}
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            self._warn(f"{path.name} 顶层应为对象或 null，已按空数据处理。")
            return {}
        return payload

    def list_materials(self) -> list[str]:
        legacy = self._read(self.root / "materials.json").get("materials") or []
        names = {item["alloy"] for item in legacy if isinstance(item, dict) and item.get("alloy")}
        if self.root.exists():
            names.update(path.name.upper() for path in self.root.iterdir()
                         if path.is_dir() and re.fullmatch(r"[0-9][A-Za-z0-9]{3}", path.name))
        return sorted(names)

    def get_material(self, alloy: str) -> dict[str, Any]:
        alloy = self.normalize_alloy(alloy)
        path = self.root / alloy / "material.json"
        if path.parent.is_dir() or alloy == "6A01":
            return {**dict.fromkeys(RECORD_FIELDS), **self._read(path)}
        for item in self._read(self.root / "materials.json").get("materials") or []:
            if isinstance(item, dict) and item.get("alloy") == alloy:
                return item
        return {}

    def _records(self, alloy: str, collection: str) -> list[dict[str, Any]]:
        alloy = self.normalize_alloy(alloy)
        path = self.root / alloy / f"{collection}.json"
        rows = self._read(path).get("records") or []
        if not isinstance(rows, list):
            self._warn(f"{path.name} 的 records 应为数组或 null，已按空数据处理。")
            return []
        result = []
        for row in rows:
            if row is None:
                continue
            if not isinstance(row, dict):
                self._warn(f"{path.name} 含非对象记录，已跳过。")
                continue
            if row.get("alloy") and str(row["alloy"]).upper() != alloy:
                self._warn(f"{path.name} 含其他牌号记录，已跳过。")
                continue
            # Identity-only and fully-null templates are not data records.
            if not any(has_data(value) for key, value in row.items() if key not in ("id", "alloy")):
                continue
            result.append({**dict.fromkeys(RECORD_FIELDS), **row})
        return result

    def get_properties(self, alloy: str, temper: str | None = None) -> list[dict[str, Any]]:
        return self._filter(self._records(alloy, "properties"), temper=temper)

    def get_literature(self, alloy: str) -> list[dict[str, Any]]:
        return self._records(alloy, "literature")

    @staticmethod
    def _filter(rows: list[dict[str, Any]], **filters: Any) -> list[dict[str, Any]]:
        # Unknown conditions are not treated as a match to a specified condition.
        return [row for row in rows if all(
            value is None or (str(row.get(key)).strip().upper() == str(value).strip().upper())
            for key, value in filters.items()
        )]

    def get_welding_cases(
        self, alloy: str, temper: str | None = None,
        welding_method: str | None = None, thickness_mm: float | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._filter(self._records(alloy, "welding_cases"),
                            temper=temper, welding_method=welding_method)
        if thickness_mm is not None:
            rows = [row for row in rows if isinstance(row.get("thickness_mm"), (int, float))
                    and not isinstance(row["thickness_mm"], bool)
                    and row["thickness_mm"] == thickness_mm]
        return rows

    def _values(self, alloy: str, field: str, legacy_field: str) -> list[str]:
        material = self.get_material(alloy)
        rows = [material] + [row for kind in COLLECTIONS for row in self._records(alloy, kind)]
        values = {row[field].strip() for row in rows
                  if isinstance(row.get(field), str) and row[field].strip()}
        extra = material.get(legacy_field)
        if isinstance(extra, list):
            values.update(value.strip() for value in extra if isinstance(value, str) and value.strip())
        return sorted(values)

    def get_tempers(self, alloy: str) -> list[str]:
        return self._values(alloy, "temper", "supported_tempers")

    def get_welding_methods(self, alloy: str) -> list[str]:
        return self._values(alloy, "welding_method", "supported_welding_methods")

    def get_summary(self, alloy: str) -> dict[str, Any]:
        self.warnings.clear()
        return {
            "material": self.get_material(alloy),
            "counts": {kind: len(self._records(alloy, kind)) for kind in COLLECTIONS},
            "tempers": self.get_tempers(alloy),
            "welding_methods": self.get_welding_methods(alloy),
            "model_status": {"available": False, "status": "未训练 / 未接入", "training_samples": None},
            "warnings": list(self.warnings),
        }

    @staticmethod
    def get_priority(alloy: str) -> list[str]:
        alloy = MaterialManager.normalize_alloy(alloy)
        return [alloy, f"{alloy[0]}xxx", "通用铝合金"]

    def get_knowledge(self, alloy: str, temper: str | None = None,
                      welding_method: str | None = None,
                      thickness_mm: float | None = None) -> list[dict[str, Any]]:
        """Expose matching records as reference context, with explicit provenance gaps."""
        alloy = self.normalize_alloy(alloy)
        groups = {
            "material": [self.get_material(alloy)],
            "properties": self.get_properties(alloy, temper),
            "welding_cases": self.get_welding_cases(alloy, temper, welding_method, thickness_mm),
            "literature": self.get_literature(alloy),
        }
        hits = []
        for kind, rows in groups.items():
            for number, row in enumerate(rows, 1):
                content = {key: value for key, value in row.items()
                           if key not in ("id", "alloy", "series", "schema_version") and has_data(value)}
                if not content:
                    continue
                source = row.get("source")
                traceable = isinstance(source, dict) and any(source.get(key) for key in ("title", "url", "report_id", "doi"))
                hits.append({
                    "id": f"{alloy}/{kind}/{row.get('id') or number}",
                    "source": f"data/materials/{alloy}/{kind}.json · " + ("原始记录" if traceable else "来源待补充"),
                    "page": source.get("page") if isinstance(source, dict) else None,
                    "text": "专项原始资料，仅供查询；不代表已验证工艺。\n" + json.dumps(content, ensure_ascii=False),
                    "score": 1.0, "material_scope": alloy, "priority": 0,
                })
        return hits
