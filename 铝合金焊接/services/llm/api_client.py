from services.llm.base import BaseLLMClient, LLMError, post_json, require_text
from services.llm.config import ModelConfig, valid_base_url


class APIClient(BaseLLMClient):
    provider = "openai-compatible"

    def __init__(self, config: ModelConfig):
        self.config = config
        self.model = config.cloud_model

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        config = self.config
        if config.provider not in ("openai", "openai-compatible", "openai_compatible", "api"):
            raise LLMError("configuration", "LLM_PROVIDER 不支持，请使用 openai-compatible 或 ollama。")
        if not config.api_key or not self.model or not valid_base_url(config.cloud_base_url):
            raise LLMError("configuration", "联网 API 未完整配置，请检查 .env 的 URL、Key 和模型名称。")
        data = post_json(
            config.cloud_base_url.rstrip("/") + "/chat/completions",
            payload={"model": self.model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=(config.connect_seconds, timeout or config.cloud_seconds),
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("invalid_response", "API 响应缺少 choices/message/content。") from None
        return require_text(content)
