"""Unified lazy adapters. Importing this module never constructs or fits a model."""
from __future__ import annotations

from typing import Protocol, Any

from .feature_engineering import build_preprocessor

ALGORITHMS = {
    "random_forest": "Random Forest", "xgboost": "XGBoost",
    "gaussian_process": "Gaussian Process", "mlp": "MLP",
}


class RegressionModel(Protocol):
    def fit(self, inputs: list[dict], outputs: list[float]) -> Any: ...
    def predict(self, inputs: list[dict]) -> Any: ...
    def uncertainty(self, inputs: list[dict]) -> dict: ...


class SklearnAdapter:
    def __init__(self, algorithm, feature_list, parameters=None, random_state=42):
        if algorithm not in ALGORITHMS:
            raise ValueError("不支持的模型类型。")
        from sklearn.pipeline import Pipeline
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.neural_network import MLPRegressor

        self.algorithm, self.feature_list = algorithm, tuple(feature_list)
        options = {"random_state": random_state, **(parameters or {})}
        if algorithm == "xgboost":
            from xgboost import XGBRegressor
            estimator = XGBRegressor(**{"objective": "reg:squarederror", **options})
        elif algorithm == "random_forest":
            estimator = RandomForestRegressor(**options)
        elif algorithm == "gaussian_process":
            estimator = GaussianProcessRegressor(**{"normalize_y": True, **options})
        else:
            estimator = MLPRegressor(**{"max_iter": 1000, **options})
        self.pipeline = Pipeline([("features", build_preprocessor(feature_list)), ("regressor", estimator)])

    def _frame(self, inputs):
        import pandas as pd
        return pd.DataFrame(inputs, columns=self.feature_list)

    def fit(self, inputs, outputs):
        self.pipeline.fit(self._frame(inputs), outputs)
        return self

    def predict(self, inputs):
        return self.pipeline.predict(self._frame(inputs))

    def uncertainty(self, inputs):
        if self.algorithm != "gaussian_process":
            return {"available": False, "method": None, "standard_deviation": None,
                    "reason": "该模型尚未实现经验证的不确定性估计。"}
        transformed = self.pipeline.named_steps["features"].transform(self._frame(inputs))
        _, std = self.pipeline.named_steps["regressor"].predict(transformed, return_std=True)
        return {"available": True, "method": "gaussian_process_posterior_std",
                "standard_deviation": [float(x) for x in std],
                "reason": "模型假设下的后验标准差，未做覆盖率校准，不等同于准确率或置信百分比。"}


def create_model(algorithm, feature_list, parameters=None, random_state=42) -> RegressionModel:
    return SklearnAdapter(algorithm, feature_list, parameters, random_state)
