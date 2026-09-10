from services.llm.base import BaseLLMClient, LLMError, post_json, require_text
from services.llm.config import ModelConfig, valid_base_url


class OllamaClient(BaseLLMClient):
    provider = "ollama"

    def __init__(self, config: ModelConfig):
        self.config = config
        self.model = config.local_model

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        config = self.config
        if not self.model or not valid_base_url(config.local_base_url):
            raise LLMError("configuration", "Ollama 地址或模型名称未正确配置。")
        data = post_json(
            config.local_base_url.rstrip("/") + "/api/generate",
            payload={"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
            headers=None,
            timeout=(config.connect_seconds, timeout or config.local_seconds),
        )
        if data.get("error"):
            raise LLMError("model_error", "Ollama 模型加载或生成失败，请检查模型是否已安装。")
        return require_text(data.get("response"))
