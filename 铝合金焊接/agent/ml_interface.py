from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from modeling.predict import WeldingPredictor, predict


class ProcessPredictionModel(Protocol):
    """焊接参数（科研 Schema 标准单位）→ 力学性能的统一 Agent 接口。"""

    def predict(self, welding_parameters: Mapping) -> dict:
        ...


__all__ = ["ProcessPredictionModel", "WeldingPredictor", "predict"]
