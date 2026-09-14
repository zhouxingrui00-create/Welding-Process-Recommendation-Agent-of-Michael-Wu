"""Explicit future training entry point. Default calls only check readiness."""
from __future__ import annotations

from importlib.metadata import version as package_version
import time

from .backends import ALGORITHMS, create_model
from .dataset import load_dataset
from .evaluate import evaluate
from .feature_engineering import DEFAULT_FEATURES, feature_domain
from .registry import ModelRegistry


def train(*, algorithm="random_forest", feature_list=DEFAULT_FEATURES, target="tensile_strength",
          manager=None, registry=None, version=None, parameters=None,
          enable_training=False, random_state=42, test_size=0.2) -> dict:
    """Never train on import/page load. Future explicit opt-in: enable_training=True.

    One target per version. Holdout groups use paper, falling back to source.
    At least two independent sources and two samples per split are required.
    """
    if algorithm not in ALGORITHMS:
        return {"status": "invalid_config", "message": "不支持的模型类型。"}
    try:
        dataset = load_dataset(manager, version=version, feature_list=feature_list, target=target)
    except (ValueError, LookupError) as exc:
        return {"status": "invalid_config", "message": str(exc)}
    summary = dataset.summary()
    if not dataset.inputs:
        return {"status": "no_data", "message": "暂无可训练数据；暂无训练模型。", "dataset": summary}
    if not enable_training:
        return {"status": "disabled", "message": "当前仅搭建框架，训练未启用。", "dataset": summary}
    if len(dataset.inputs) < 4 or len(set(dataset.groups)) < 2:
        return {"status": "insufficient_data", "message": "至少需要两组独立来源，且训练集和测试集各不少于两条完整记录。", "dataset": summary}
    if isinstance(test_size, bool) or not isinstance(test_size, (int, float)) or not 0 < test_size < 1:
        return {"status": "invalid_config", "message": "test_size 必须在 0 和 1 之间。"}
    try:
        from sklearn.model_selection import GroupShuffleSplit
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        training, testing = next(splitter.split(dataset.inputs, dataset.outputs, groups=dataset.groups))
        if min(len(training), len(testing)) < 2:
            return {"status": "insufficient_data", "message": "按来源分组后样本不足，请补充数据或调整测试比例。", "dataset": summary}
        model = create_model(algorithm, dataset.feature_list, parameters, random_state)
    except ImportError as exc:
        return {"status": "missing_dependency", "message": f"尚未安装可选训练依赖：{exc.name}。请安装 requirements-modeling.txt。"}
    except (ValueError, TypeError) as exc:
        return {"status": "invalid_config", "message": str(exc)}
    registry = registry if registry is not None else ModelRegistry()
    metadata = registry.begin_training(algorithm=algorithm, feature_list=dataset.feature_list, target=target,
                                       data_version=dataset.data_version, data_sha256=dataset.data_sha256,
                                       parameters=parameters or {}, random_state=random_state, dataset_summary=summary)
    started = time.perf_counter()
    try:
        train_x = [dataset.inputs[int(i)] for i in training]
        test_x = [dataset.inputs[int(i)] for i in testing]
        model.fit(train_x, [dataset.outputs[int(i)] for i in training])
        metrics = evaluate([dataset.outputs[int(i)] for i in testing], model.predict(test_x))
        split = {"method": "group_holdout", "group_by": "paper_or_source", "test_size": test_size,
                 "train_count": len(training), "test_count": len(testing),
                 "train_records": [dataset.record_ids[int(i)] for i in training],
                 "test_records": [dataset.record_ids[int(i)] for i in testing]}
        dependencies = {name: package_version(name) for name in ("scikit-learn", "numpy", "pandas")}
        if algorithm == "xgboost":
            dependencies["xgboost"] = package_version("xgboost")
        saved = registry.finish_training(metadata["model_version"], model, metrics=metrics,
                                         duration_seconds=time.perf_counter() - started,
                                         feature_domain=feature_domain(train_x, dataset.feature_list),
                                         split=split, dependencies=dependencies)
        return {"status": "trained", "message": "训练完成并保存。", "model": saved}
    except Exception as exc:
        registry.fail_training(metadata["model_version"], exc, time.perf_counter() - started)
        return {"status": "failed", "message": str(exc), "model_version": metadata["model_version"]}
