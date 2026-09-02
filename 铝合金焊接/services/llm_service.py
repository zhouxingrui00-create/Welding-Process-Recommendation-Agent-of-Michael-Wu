from __future__ import annotations

import ctypes
import json
import os
from dataclasses import dataclass
from typing import Any

import requests

from utils.config import load_settings


@dataclass
class LLMResponse:
    text: str
    available: bool
    model: str
    message: str


def total_ram_gb() -> float | None:
    try:
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.total_physical / (1024**3), 1)
    except (AttributeError, OSError):
        pass
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 1)
    except (AttributeError, ValueError, OSError):
        return None


class OllamaService:
    def __init__(self) -> None:
        config = load_settings()["ollama"]
        self.base_url = config["base_url"].rstrip("/")
        self.model = config["model"]
        self.fallback_model = config["fallback_model"]
        self.timeout = int(config["timeout_seconds"])

    def hardware_advice(self) -> str:
        ram = total_ram_gb()
        if ram is not None and ram < 15:
            return f"检测到约 {ram:g} GB 内存，建议改用 {self.fallback_model}。"
        return f"默认使用 {self.model}；若响应过慢或内存不足，改用 {self.fallback_model}。"

    def status(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            response.raise_for_status()
            models = [item.get("name", "") for item in response.json().get("models", [])]
        except (requests.RequestException, ValueError) as exc:
            return {
                "running": False,
                "installed": False,
                "model": self.model,
                "message": f"Ollama 未连接：{exc}",
                "install_command": f"ollama pull {self.model}",
                "hardware_advice": self.hardware_advice(),
            }
        installed = self.model in models
        return {
            "running": True,
            "installed": installed,
            "model": self.model,
            "models": models,
            "message": "Ollama 与目标模型可用。" if installed else "Ollama 已启动，但目标模型未安装。",
            "install_command": f"ollama pull {self.model}",
            "fallback_command": f"ollama pull {self.fallback_model}",
            "hardware_advice": self.hardware_advice(),
        }

    def explain(self, context: dict[str, Any]) -> LLMResponse:
        status = self.status()
        if not status["running"] or not status["installed"]:
            return LLMResponse("", False, self.model, status["message"])
        system_instruction = (
            "你是铝合金焊接工艺初选解释助手。只解释给定的结构化结果和检索片段。"
            "不得新增、猜测、换算或修改任何电流、电压、速度、流量、温度、频率、尺寸等数值；"
            "不得把示例参数说成正式WPS；数据不足时必须明确说需要试焊和WPS/PQR验证。"
            "用中文写3至6段，包含选择理由、材料风险和验证重点，不要重复完整参数表。"
        )
        prompt = system_instruction + "\n\n已审核上下文：\n" + json.dumps(
            context, ensure_ascii=False, indent=2
        )
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = str(response.json().get("response", "")).strip()
            if not text:
                return LLMResponse("", False, self.model, "Ollama 返回了空解释。")
            return LLMResponse(text, True, self.model, "本地模型解释已生成。")
        except (requests.RequestException, ValueError) as exc:
            return LLMResponse("", False, self.model, f"Ollama 生成失败：{exc}")

