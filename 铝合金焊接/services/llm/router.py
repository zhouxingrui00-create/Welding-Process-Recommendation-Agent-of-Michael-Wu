from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from time import perf_counter
from typing import Any

import yaml

from services.llm.api_client import APIClient
from services.llm.base import BaseLLMClient, LLMError, LLMResponse, explanation_prompt, require_text
from services.llm.config import ModelConfig, load_model_config
from services.llm.ollama_client import OllamaClient
from services.logging_service import ModelCallLogger


class LLMRouter:
    """Cloud first, then Ollama; failures never prevent rule recommendations."""

    def __init__(self, config: ModelConfig | None = None, *, logger: ModelCallLogger | None = None):
        self.config_error = ""
        try:
            self.config = config if config is not None else load_model_config()
        except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError):
            self.config = ModelConfig()
            self.config_error = "模型配置文件无效或无法读取，已使用默认本地备用配置。"
        self.cloud = APIClient(self.config)
        self.local = OllamaClient(self.config)
        self.logger = logger if logger is not None else ModelCallLogger()
        self.last_response: LLMResponse | None = None
        self.states: dict[str, dict[str, Any]] = {}
        self.log_error = ""

    @property
    def model(self) -> str:
        if self.last_response is not None:
            return self.last_response.model
        return "尚未调用"

    def _attempt(self, client: BaseLLMClient, prompt: str, *, operation: str, timeout: float | None = None) -> LLMResponse:
        started_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        start = perf_counter()
        try:
            text = require_text(client.generate(prompt, timeout=timeout))
            result = LLMResponse(text, True, client.model, "模型调用成功。", client.provider)
        except LLMError as exc:
            result = LLMResponse("", False, client.model, str(exc), client.provider, exc.code)
        except Exception:
            # Never expose SDK/transport exceptions, which may contain credentials.
            result = LLMResponse("", False, client.model, "模型调用失败。", client.provider, "internal_error")
        result.elapsed_ms = round((perf_counter() - start) * 1000, 2)
        if self.config.api_key:
            result.model = result.model.replace(self.config.api_key, "[REDACTED]")
        self.states[client.provider] = {
            key: value for key, value in asdict(result).items() if key not in ("text", "attempts")
        }
        self.states[client.provider].update(checked_at=started_at, operation=operation)
        try:
            self.logger.write({
                "started_at": started_at, "provider": client.provider, "model": result.model,
                "operation": operation, "success": result.available,
                "elapsed_ms": result.elapsed_ms, "error_code": result.error_code,
            })
            self.log_error = ""
        except Exception:
            self.log_error = "模型调用日志写入失败，请检查日志目录权限。"
        return result

    def generate(self, prompt: str) -> LLMResponse:
        attempts = []
        clients = [self.local] if self.config.provider == "ollama" else [self.cloud]
        if self.config.provider != "ollama" and self.config.fallback_enabled:
            clients.append(self.local)
        for index, client in enumerate(clients):
            result = self._attempt(client, prompt, operation="generate")
            attempts.append(dict(self.states[client.provider]))
            if result.available:
                result.attempts = attempts
                result.fallback_used = index > 0
                result.message = "联网 API 不可用，已自动切换 Ollama 本地模型。" if index else "模型解释已生成。"
                self.last_response = result
                return result
        self.last_response = LLMResponse("", False, "规则推荐", "AI解释模块不可用", error_code="all_unavailable", attempts=attempts)
        return self.last_response

    def explain(self, context: dict[str, Any]) -> LLMResponse:
        return self.generate(explanation_prompt(context))

    def test_connections(self) -> dict[str, dict[str, Any]]:
        # Verify real inference with a neutral prompt, not merely a model listing.
        for client in (self.cloud, self.local):
            self._attempt(client, "Reply with OK only.", operation="connection_test", timeout=self.config.test_seconds)
        return self.status()

    def status(self) -> dict[str, dict[str, Any]]:
        return {
            client.provider: dict(self.states.get(client.provider, {
                "available": None, "model": client.model, "provider": client.provider,
                "message": "尚未测试连接。", "checked_at": None,
            })) for client in (self.cloud, self.local)
        }
