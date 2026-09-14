"""Regression metrics on caller-supplied held-out measurements only."""
from __future__ import annotations

import math


def evaluate(y_true, y_pred) -> dict:
    actual, predicted = list(y_true), list(y_pred)
    if len(actual) != len(predicted):
        raise ValueError("真实值与预测值数量不一致。")
    if not actual:
        return {"status": "no_data", "sample_count": 0, "mae": None, "rmse": None, "r2": None}
    actual, predicted = [float(x) for x in actual], [float(x) for x in predicted]
    if not all(math.isfinite(x) for x in actual + predicted):
        raise ValueError("评价数据不能包含 NaN 或无穷值。")
    n = len(actual)
    errors = [a - p for a, p in zip(actual, predicted)]
    squared = sum(e * e for e in errors)
    mean = sum(actual) / n
    total = sum((a - mean) ** 2 for a in actual)
    metrics = {"status": "evaluated", "sample_count": n,
               "mae": sum(abs(e) for e in errors) / n, "rmse": math.sqrt(squared / n),
               "r2": 1 - squared / total if n >= 2 and total > 0 else None}
    if any(value is not None and not math.isfinite(value) for key, value in metrics.items()
           if key in ("mae", "rmse", "r2")):
        raise ValueError("评价数值溢出。")
    return metrics
