from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from dotenv import dotenv_values

from utils.paths import project_path


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "openai-compatible"
    cloud_base_url: str = ""
    cloud_model: str = ""
    api_key: str = field(default="", repr=False)
    local_base_url: str = "http://127.0.0.1:11434"
    local_model: str = "qwen2.5:7b-instruct-q4_K_M"
    connect_seconds: float = 3
    cloud_seconds: float = 30
    local_seconds: float = 90
    test_seconds: float = 15
    fallback_enabled: bool = True


def valid_base_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(url.scheme in ("http", "https") and url.hostname and url.port != 0
                    and not url.username and not url.password and not url.query and not url.fragment)
    except ValueError:
        return False


def load_model_config(config_path: Path | None = None, env_path: Path | None = None) -> ModelConfig:
    path = config_path or project_path("config", "model_config.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cloud, local = raw.get("cloud", {}), raw.get("local", {})
    timeouts, fallback = raw.get("timeout", {}), raw.get("fallback", {})
    # Do not mutate os.environ: edits/removals in .env are picked up on reload.
    env = {**dotenv_values(env_path or project_path(".env"), interpolate=False, encoding="utf-8-sig"), **os.environ}

    def value(name: str, default: str) -> str:
        return str(env.get(name) or default).strip()

    def seconds(name: str, default: float) -> float:
        value = float(timeouts.get(name, default))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Timeout must be positive and finite")
        return value

    if fallback.get("strategy", "cloud_then_local") != "cloud_then_local":
        raise ValueError("Unsupported fallback strategy")
    enabled = fallback.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("fallback.enabled must be boolean")
    return ModelConfig(
        provider=value("LLM_PROVIDER", cloud.get("provider", "openai-compatible")).lower(),
        cloud_base_url=value("LLM_BASE_URL", cloud.get("base_url", "")),
        cloud_model=value("LLM_MODEL", cloud.get("model", "")),
        api_key=value("LLM_API_KEY", ""),
        local_base_url=str(local.get("base_url", ModelConfig.local_base_url)).strip(),
        local_model=str(local.get("model", ModelConfig.local_model)).strip(),
        connect_seconds=seconds("connect_seconds", 3),
        cloud_seconds=seconds("cloud_seconds", 30),
        local_seconds=seconds("local_seconds", 90),
        test_seconds=seconds("test_seconds", 15),
        fallback_enabled=enabled,
    )
