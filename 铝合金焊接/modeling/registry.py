"""Local model versions and atomic metadata/artifact publication.

Pickle files are loaded only from this trusted, application-owned registry.
Never copy untrusted downloaded pickle files into the registry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import re
from uuid import uuid4

from utils.paths import project_path
from .backends import ALGORITHMS
from .feature_engineering import FEATURE_SCHEMA_VERSION, validate_spec


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class ModelRegistry:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else project_path("data", "models")
        self.warnings: list[str] = []

    def _directory(self, model_version):
        if not isinstance(model_version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", model_version):
            raise ValueError("无效 model_version。")
        directory = self.root / model_version
        if not directory.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("模型路径超出注册目录。")
        return directory

    @staticmethod
    def _atomic_write(path, content):
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _write_metadata(self, metadata):
        content = json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        self._atomic_write(self._directory(metadata["model_version"]) / "metadata.json", content)

    def get(self, model_version):
        path = self._directory(model_version) / "metadata.json"
        if not path.exists():
            return None
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict) or metadata.get("model_version") != model_version:
            raise ValueError("模型元数据版本不一致。")
        validate_spec(metadata["feature_list"], metadata["target"])
        if metadata["algorithm"] not in ALGORITHMS or metadata["status"] not in ("training", "trained", "failed"):
            raise ValueError("模型元数据包含未知类型或状态。")
        if metadata.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            raise ValueError("模型特征契约版本不兼容。")
        for name in ("created_at", "data_version", "metrics", "training_duration_seconds", "trained_at", "feature_domain"):
            if name not in metadata:
                raise ValueError(f"模型元数据缺少 {name}。")
        return metadata

    def list_models(self, *, target=None, trained_only=False):
        self.warnings = []
        if not self.root.exists():
            return []
        result = []
        for path in self.root.glob("*/metadata.json"):
            try:
                metadata = self.get(path.parent.name)
                if target is not None and metadata["target"] != target:
                    continue
                if trained_only and metadata["status"] != "trained":
                    continue
                result.append(metadata)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.warnings.append(f"无法读取模型 {path.parent.name}：{exc}")
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def begin_training(self, *, algorithm, feature_list, target, data_version,
                       data_sha256, parameters, random_state, dataset_summary):
        features = validate_spec(feature_list, target)
        if algorithm not in ALGORITHMS or not data_version or not data_sha256:
            raise ValueError("注册训练必须包含模型类型、数据版本和数据摘要。")
        version = "v" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:12]
        metadata = {"model_version": version, "algorithm": algorithm, "feature_list": list(features),
                    "target": target, "feature_schema_version": FEATURE_SCHEMA_VERSION,
                    "status": "training", "created_at": utc_now(), "trained_at": None,
                    "training_duration_seconds": None, "data_version": data_version,
                    "data_sha256": data_sha256, "dataset_summary": dataset_summary,
                    "parameters": parameters, "random_state": random_state,
                    "metrics": {}, "feature_domain": {}, "artifact_file": None,
                    "artifact_sha256": None, "error": None}
        # Validate serialization before creating a version directory.
        json.dumps(metadata, allow_nan=False)
        self._directory(version).mkdir(parents=True, exist_ok=False)
        self._write_metadata(metadata)
        return metadata

    def finish_training(self, model_version, model, *, metrics, duration_seconds,
                        feature_domain, split, dependencies):
        metadata = self.get(model_version)
        if metadata is None or metadata["status"] != "training":
            raise ValueError("只有训练中的版本可以保存模型。")
        artifact = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
        self._atomic_write(self._directory(model_version) / "model.pkl", artifact)
        metadata.update(status="trained", trained_at=utc_now(), training_duration_seconds=duration_seconds,
                        metrics=metrics, feature_domain=feature_domain, split=split,
                        dependencies=dependencies, artifact_file="model.pkl", artifact_sha256=sha256(artifact).hexdigest())
        self._write_metadata(metadata)
        return metadata

    def fail_training(self, model_version, error, duration_seconds):
        metadata = self.get(model_version)
        if metadata is None or metadata["status"] != "training":
            raise ValueError("只有训练中的版本可以标记失败。")
        metadata.update(status="failed", error=str(error), training_duration_seconds=duration_seconds,
                        finished_at=utc_now())
        self._write_metadata(metadata)
        return metadata

    def load_model(self, model_version):
        metadata = self.get(model_version)
        if metadata is None or metadata["status"] != "trained":
            raise LookupError("暂无训练模型")
        artifact = self._directory(model_version) / "model.pkl"
        if not artifact.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("模型文件超出注册目录。")
        content = artifact.read_bytes()
        if sha256(content).hexdigest() != metadata.get("artifact_sha256"):
            raise ValueError("模型文件校验失败。")
        return pickle.loads(content)
