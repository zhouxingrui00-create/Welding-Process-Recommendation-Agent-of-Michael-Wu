from __future__ import annotations

from typing import Protocol

from agent.models import WeldingRequest


class ProcessPredictionModel(Protocol):
    """未来工艺参数预测模型的稳定接口；第一版不提供实现。"""

    def predict(self, request: WeldingRequest) -> dict:
        ...

