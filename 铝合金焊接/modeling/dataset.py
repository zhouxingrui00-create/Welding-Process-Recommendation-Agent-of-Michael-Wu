"""Read a pinned formal research snapshot; Demo records are never trainable."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
import json

from data_manager import DataManager
from .feature_engineering import DEFAULT_FEATURES, feature_record, numeric_value, validate_spec


@dataclass
class TrainingDataset:
    feature_list: tuple[str, ...]
    target: str
    data_version: str | None = None
    data_sha256: str | None = None
    inputs: list[dict] = field(default_factory=list)
    outputs: list[float] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    record_ids: list[dict] = field(default_factory=list)
    total_records: int = 0
    excluded: dict[str, int] = field(default_factory=dict)

    def summary(self):
        return {"data_version": self.data_version, "data_sha256": self.data_sha256,
                "total_records": self.total_records, "usable_records": len(self.inputs),
                "excluded": self.excluded, "feature_list": list(self.feature_list), "target": self.target}


def load_dataset(manager=None, *, version=None, feature_list=DEFAULT_FEATURES,
                 target="tensile_strength") -> TrainingDataset:
    features = validate_spec(feature_list, target)
    manager = manager if manager is not None else DataManager()
    result = TrainingDataset(features, target)
    if version is None:
        versions = manager.versions("research")
        if not versions:
            return result
        version = versions[0]["version"]
    metadata = manager.version_detail("research", version)["metadata"]
    result.data_version = "research:" + metadata["dataset_version"]
    digest, excluded, offset = sha256(), Counter(), 0
    while True:
        batch = manager.records("research", version=version, limit=1000, offset=offset)
        if not batch:
            break
        for record in batch:
            result.total_records += 1
            digest.update(json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
            if record.get("record_kind") != "experimental":
                excluded["non_experimental"] += 1
                continue
            if not record.get("source") or not record.get("experiment_id"):
                excluded["missing_provenance"] += 1
                continue
            try:
                output = numeric_value(target, record.get(target))
            except ValueError:
                excluded["missing_or_invalid_target"] += 1
                continue
            try:
                inputs = feature_record(record, features)
            except ValueError:
                excluded["missing_or_invalid_features"] += 1
                continue
            result.inputs.append(inputs)
            result.outputs.append(output)
            # Keep records from the same paper/source in one partition.
            result.groups.append(str(record.get("paper") or record["source"]).strip())
            result.record_ids.append({"source": record["source"], "experiment_id": record["experiment_id"]})
        offset += len(batch)
    result.data_sha256 = digest.hexdigest()
    result.excluded = dict(excluded)
    return result
