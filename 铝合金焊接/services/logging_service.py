from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from threading import Lock

from utils.config import load_settings
from utils.paths import project_path


class RecommendationLogger:
    def __init__(self) -> None:
        log_dir = load_settings()["app"]["log_dir"]
        self.log_dir = project_path(*log_dir.split("/"))

    def write(self, payload: dict[str, Any]) -> str:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        record_id = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
        record = {
            "record_id": record_id,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            **payload,
        }
        target = self.log_dir / f"recommendations-{datetime.now().strftime('%Y-%m')}.jsonl"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record_id


class ModelCallLogger:
    """One metadata record per attempt, including failed calls and connection tests."""

    _lock = Lock()

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir if log_dir is not None else project_path(load_settings()["app"]["log_dir"])

    def write(self, record: dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        target = self.log_dir / f"llm-calls-{datetime.now().strftime('%Y-%m')}.jsonl"
        # Deliberately omit prompts, response bodies, URLs, headers and API keys.
        allowed = ("started_at", "provider", "model", "operation", "success", "elapsed_ms", "error_code")
        payload = {key: record[key] for key in allowed}
        with self._lock, target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
