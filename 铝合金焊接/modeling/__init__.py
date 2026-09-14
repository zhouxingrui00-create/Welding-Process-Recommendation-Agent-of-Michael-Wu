"""Welding parameter → mechanical property modeling, with no startup training."""
from .predict import WeldingPredictor, predict
from .registry import ModelRegistry

__all__ = ["ModelRegistry", "WeldingPredictor", "predict"]
