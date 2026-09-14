"""Infrastructure tests only. No estimator.fit, experimental fixtures or datasets.

Scalar values in metric/prediction tests are deterministic protocol test doubles,
not experimental measurements, and never enter the research database.
"""
import builtins
import importlib
import json
import pickle
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from data_manager import DataManager
from modeling import ModelRegistry, WeldingPredictor, predict
from modeling.backends import ALGORITHMS
from modeling.dataset import TrainingDataset, load_dataset
from modeling.evaluate import evaluate
from modeling.feature_engineering import feature_record, validate_spec
from modeling.train import train

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def empty(tmp_path):
    return DataManager(tmp_path / "research"), ModelRegistry(tmp_path / "models")


def block_ml_imports(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in ("sklearn", "xgboost"):
            pytest.fail("空状态不应导入可选机器学习依赖")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
@pytest.mark.parametrize("enabled", [False, True])
def test_empty_training_never_builds_model_or_writes(empty, monkeypatch, algorithm, enabled):
    block_ml_imports(monkeypatch)
    manager, registry = empty
    result = train(manager=manager, registry=registry, algorithm=algorithm, enable_training=enabled)
    assert result["status"] == "no_data"
    assert result["dataset"]["usable_records"] == 0
    assert not registry.root.exists() and not manager.root.exists()


def test_empty_prediction_and_agent_interface(empty, monkeypatch):
    from agent.ml_interface import predict as agent_predict
    block_ml_imports(monkeypatch)
    _, registry = empty
    for result in (predict({}, registry=registry), agent_predict({}, registry=registry),
                   WeldingPredictor(registry=registry).predict({})):
        assert result["status"] == "no_model"
        assert result["message"] == "暂无训练模型"
        assert result["predicted_performance"] == {}
        assert result["confidence"]["value"] is None
        assert not result["confidence"]["available"]
        json.dumps(result, allow_nan=False)
    assert registry.list_models() == [] and not registry.root.exists()


def test_demo_only_is_not_training_data(empty):
    manager, registry = empty
    manager.import_file(ROOT / "data/templates/demo_schema_only.csv", dataset="demo")
    assert manager.summary("demo")["record_count"] == 1
    assert load_dataset(manager).total_records == 0
    assert train(manager=manager, registry=registry, enable_training=True)["status"] == "no_data"
    assert not registry.root.exists()


def test_dataset_pins_version_and_excludes_non_experimental_and_missing_labels():
    manager = Mock()
    manager.versions.return_value = [{"version": 7}]
    manager.version_detail.return_value = {"metadata": {"dataset_version": "v000007"}}
    # Routing-only records; no welding or mechanical measurements are fabricated.
    manager.records.side_effect = [
        [{"record_kind": "schema_test"}, {"record_kind": "experimental"},
         {"record_kind": "experimental", "source": "unit-test-only", "experiment_id": "missing-label"}], []]
    result = load_dataset(manager)
    assert result.data_version == "research:v000007"
    assert result.total_records == 3 and not result.inputs
    assert result.excluded == {"non_experimental": 1, "missing_provenance": 1, "missing_or_invalid_target": 1}
    assert len(result.data_sha256) == 64
    assert all(call.args[0] == "research" and call.kwargs["version"] == 7 for call in manager.records.call_args_list)


def test_nonempty_readiness_is_disabled_before_any_model_construction(monkeypatch, empty):
    module = importlib.import_module("modeling.train")
    # Non-numeric control-flow sentinel, never passed to fit or persistence.
    dataset = TrainingDataset(("alloy",), "hardness", inputs=[{}])
    monkeypatch.setattr(module, "load_dataset", lambda *a, **kw: dataset)
    factory = Mock(side_effect=AssertionError("must not construct model"))
    monkeypatch.setattr(module, "create_model", factory)
    assert train(registry=empty[1])["status"] == "disabled"
    factory.assert_not_called()
    assert not empty[1].root.exists()


@pytest.mark.parametrize("features", [[], ["current", "current"], ["hardness"], ["source"], ["porosity"]])
def test_feature_spec_rejects_empty_duplicates_and_leakage(features):
    with pytest.raises(ValueError):
        validate_spec(features)


@pytest.mark.parametrize("value", [None, True, float("nan"), float("inf"), -1, "1 A"])
def test_invalid_numeric_feature_is_not_imputed(value):
    with pytest.raises(ValueError):
        feature_record({"current": value}, ["current"])


def test_feature_order_and_category_normalization():
    assert list(feature_record({"alloy": " 6a01 ", "process": "gtaw"}, ["process", "alloy"]).items()) == [
        ("process", "TIG"), ("alloy", "6A01")]


def test_metrics_empty_and_undefined_r2():
    assert evaluate([], []) == {"status": "no_data", "sample_count": 0, "mae": None, "rmse": None, "r2": None}
    assert evaluate([1], [1])["r2"] is None
    assert evaluate([1, 1], [1, 1])["r2"] is None
    assert evaluate([0, 2], [0, 2])["r2"] == 1
    assert evaluate([0, 2], [1, 1])["mae"] == 1
    with pytest.raises(ValueError):
        evaluate([], [1])
    with pytest.raises(ValueError):
        evaluate([float("nan")], [0])


def begin(registry):
    return registry.begin_training(algorithm="random_forest", feature_list=["alloy"], target="hardness",
                                   data_version="test-metadata-only", data_sha256="not-experimental",
                                   parameters={}, random_state=42, dataset_summary={})


def complete(registry, metadata):
    # Serialization sentinel, not a trained estimator. Temporary test registry only.
    return registry.finish_training(metadata["model_version"], {"protocol_test_only": True},
                                    metrics=evaluate([], []), duration_seconds=0,
                                    feature_domain={"alloy": {"values": ["TEST_ONLY"]}}, split={}, dependencies={})


def test_registry_roundtrip_status_metadata_and_integrity(empty, monkeypatch):
    _, registry = empty
    metadata = begin(registry)
    version = metadata["model_version"]
    assert registry.get(version)["status"] == "training"
    assert registry.list_models(trained_only=True) == []
    saved = complete(registry, metadata)
    assert saved["trained_at"] and saved["feature_list"] == ["alloy"]
    assert saved["target"] == "hardness" and saved["training_duration_seconds"] == 0
    assert registry.load_model(version) == {"protocol_test_only": True}
    assert len(registry.list_models(target="hardness", trained_only=True)) == 1
    with pytest.raises(ValueError):
        complete(registry, metadata)
    (registry.root / version / "model.pkl").write_bytes(b"corrupted")
    unpickle = Mock(side_effect=AssertionError("must reject before deserializing"))
    monkeypatch.setattr(pickle, "loads", unpickle)
    with pytest.raises(ValueError, match="校验失败"):
        registry.load_model(version)
    unpickle.assert_not_called()


def test_failed_run_does_not_become_predictable(empty):
    _, registry = empty
    metadata = begin(registry)
    registry.fail_training(metadata["model_version"], "protocol-test failure", 0)
    assert registry.list_models()[0]["status"] == "failed"
    assert predict({}, registry=registry, target="hardness")["status"] == "no_model"


@pytest.mark.parametrize("version", ["../outside", "a/b", "a\\b", "", ".."])
def test_registry_rejects_path_traversal(empty, version):
    with pytest.raises(ValueError):
        empty[1].get(version)


def test_corrupt_metadata_isolated(empty):
    registry = empty[1]
    folder = registry.root / "broken"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text("{", encoding="utf-8")
    assert registry.list_models() == []
    assert registry.warnings
    response = predict({}, registry=registry)
    assert response["status"] == "no_model" and response["warnings"]


def test_prediction_contract_and_failure_paths(empty, monkeypatch):
    registry = empty[1]
    metadata = complete(registry, begin(registry))
    version = metadata["model_version"]
    assert predict({}, registry=registry, target="hardness")["status"] == "invalid_input"
    assert predict({"alloy": "UNKNOWN"}, registry=registry, target="hardness")["status"] == "out_of_domain"
    assert predict({}, registry=registry, model_version=version)["status"] == "invalid_input"
    # Protocol-only inference stub; not an estimator and never fitted.
    model = Mock()
    model.predict.return_value = [1]
    model.uncertainty.return_value = {"available": False, "method": None, "standard_deviation": None,
                                      "reason": "protocol-test only"}
    monkeypatch.setattr(registry, "load_model", lambda *args: model)
    result = predict({"alloy": "TEST_ONLY"}, registry=registry, target="hardness")
    assert result["status"] == "ok"
    assert result["predicted_performance"] == {"hardness": {"value": 1.0, "unit": "HV"}}
    assert result["confidence"]["value"] is None and not result["confidence"]["available"]
    model.uncertainty.return_value = {"available": True, "method": "protocol-test", "standard_deviation": [0], "reason": "test"}
    assert predict({"alloy": "TEST_ONLY"}, registry=registry, target="hardness")["confidence"]["standard_deviation"] == 0
    model.predict.return_value = [float("nan")]
    result = predict({"alloy": "TEST_ONLY"}, registry=registry, target="hardness")
    assert result["status"] == "model_unavailable" and not result["predicted_performance"]
    model.fit.assert_not_called()


def test_missing_artifact_returns_structured_failure(empty):
    registry = empty[1]
    metadata = complete(registry, begin(registry))
    (registry.root / metadata["model_version"] / "model.pkl").unlink()
    result = predict({"alloy": "TEST_ONLY"}, registry=registry, target="hardness")
    assert result["status"] == "model_unavailable" and result["predicted_performance"] == {}


def test_model_page_empty_and_navigation(empty, monkeypatch):
    manager, registry = empty
    monkeypatch.setattr("modeling.registry.ModelRegistry", lambda: registry)
    monkeypatch.setattr("modeling.dataset.DataManager", lambda: manager)
    block_ml_imports(monkeypatch)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    app.switch_page("pages/4_模型管理.py").run()
    assert not app.exception and not app.error
    assert app.title[0].value == "模型管理"
    assert any(x.value == "暂无训练模型" for x in app.info)
    assert [x.value for x in app.metric][:3] == ["0", "0", "0"]
    assert app.button[0].disabled
    for algorithm in ALGORITHMS:
        app.selectbox[0].set_value(algorithm).run()
        assert not app.exception and app.button[0].disabled
    app.multiselect[0].set_value([]).run()
    assert not app.exception and app.warning
    assert not manager.root.exists() and not registry.root.exists()
    app.switch_page("app.py").run()
    assert not app.exception


def test_model_page_shows_registered_states_without_loading_artifacts(empty, monkeypatch):
    manager, registry = empty
    complete(registry, begin(registry))
    failure = begin(registry)
    registry.fail_training(failure["model_version"], "test failure", 0)
    begin(registry)
    monkeypatch.setattr("modeling.registry.ModelRegistry", lambda: registry)
    monkeypatch.setattr("modeling.dataset.DataManager", lambda: manager)
    monkeypatch.setattr(registry, "load_model", Mock(side_effect=AssertionError("page must not deserialize models")))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()
    app.switch_page("pages/4_模型管理.py").run()
    assert not app.exception and not app.error
    assert [x.value for x in app.metric][:3] == ["1", "1", "1"]
    assert {"MAE", "RMSE", "R²", "target", "model_version"} <= set(app.dataframe[0].value.columns)
