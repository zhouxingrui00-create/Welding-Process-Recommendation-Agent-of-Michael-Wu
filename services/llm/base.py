from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class LLMResponse:
    text: str
    available: bool
    model: str
    message: str
    provider: str = ""
    error_code: str = ""
    elapsed_ms: float = 0.0
    fallback_used: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)


class LLMError(Exception):
    """Only predefined, credential-free messages may cross the client boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def explanation_prompt(context: dict[str, Any]) -> str:
    # Preserve the original explanation-only instruction verbatim.
    system_instruction = (
        "你是铝合金焊接工艺初选解释助手。只解释给定的结构化结果和检索片段。"
        "不得新增、猜测、换算或修改任何电流、电压、速度、流量、温度、频率、尺寸等数值；"
        "不得把示例参数说成正式WPS；数据不足时必须明确说需要试焊和WPS/PQR验证。"
        "用中文写3至6段，包含选择理由、材料风险和验证重点，不要重复完整参数表。"
    )
    return system_instruction + "\n\n已审核上下文：\n" + json.dumps(context, ensure_ascii=False, indent=2)


def post_json(url: str, *, payload: dict, headers: dict | None, timeout: tuple[float, float]) -> dict:
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout, allow_redirects=False)
        if response.status_code in (401, 403):
            raise LLMError("authentication", "API Key 错误或无访问权限。")
        if not 200 <= response.status_code < 300:
            raise LLMError("http_error", f"模型服务返回 HTTP {response.status_code}。")
        data = response.json()
    except requests.Timeout:
        raise LLMError("timeout", "模型调用超时。") from None
    except requests.RequestException:
        raise LLMError("network", "模型服务无法连接或网络异常。") from None
    except ValueError:
        raise LLMError("invalid_response", "模型服务返回了无效 JSON。") from None
    if not isinstance(data, dict):
        raise LLMError("invalid_response", "模型服务返回结构无效。")
    return data


def require_text(text: Any) -> str:
    if not isinstance(text, str) or not text.strip():
        raise LLMError("empty_response", "模型未返回有效文本。")
    return text.strip()


class BaseLLMClient(ABC):
    provider: str
    model: str

    @abstractmethod
    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        """Generate text or raise LLMError; no recommendation decisions here."""
