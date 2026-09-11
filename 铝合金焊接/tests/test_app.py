from pathlib import Path
from unittest.mock import Mock

import requests

from streamlit.testing.v1 import AppTest


def test_6a01_page_starts_empty_and_navigation_preserves_result(monkeypatch):
    monkeypatch.setattr(requests, "post", Mock(side_effect=requests.ConnectionError()))
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    next(box for box in app.selectbox if box.label == "铝合金牌号").select("6A01").run()
    next(box for box in app.checkbox if box.label == "使用 AI 生成解释").uncheck().run()
    app.button[0].click().run()
    assert not app.exception
    original = app.session_state["recommendation"]
    assert original["request"]["temper"] == "未知"
    assert original["parameters"] == []
    app.switch_page("pages/2_6A01专项分析.py").run()
    assert not app.exception
    assert app.title[0].value == "6A01专项分析"
    assert [metric.value for metric in app.metric] == ["0", "0", "0"]
    assert any("暂无 6A01" in item.value for item in app.info)
    app.button[0].click().run()
    assert not app.exception
    app.switch_page("app.py").run()
    assert not app.exception
    assert app.session_state["recommendation"] == original


def test_6a01_page_starts_with_missing_database(monkeypatch, tmp_path):
    from services.material_manager import MaterialManager
    monkeypatch.setattr("services.material_manager.MaterialManager", lambda: MaterialManager(tmp_path))
    path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(path), default_timeout=10).run()
    app.switch_page("pages/2_6A01专项分析.py").run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["0", "0", "0"]


def test_streamlit_app_starts_without_exception(monkeypatch) -> None:
    monkeypatch.setattr(requests, "post", Mock(side_effect=requests.ConnectionError()))
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "离线铝合金焊接工艺推荐智能体"
    app.button[0].click().run(timeout=15)
    assert not app.exception
    assert len(app.tabs) == 4


def test_model_settings_shows_both_failures_and_reloads(monkeypatch) -> None:
    monkeypatch.setattr(requests, "post", Mock(side_effect=requests.ConnectionError()))
    app_path = Path(__file__).resolve().parents[1] / "pages" / "1_模型设置.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "模型设置"
    assert app.metric[0].value == "尚未调用"
    next(button for button in app.button if button.label == "测试连接").click().run()
    assert not app.exception
    assert any("AI解释模块不可用" in item.value for item in app.warning)
    assert {item.value for item in app.subheader} == {"API 状态", "Ollama 状态"}
    next(button for button in app.button if button.label == "重新加载配置").click().run()
    assert not app.exception
    assert any(item.value == "尚未测试连接。" for item in app.info)


def test_settings_success_and_page_navigation_preserve_recommendation(monkeypatch) -> None:
    from services.llm.config import ModelConfig

    config = ModelConfig(cloud_base_url="https://example.invalid/v1", api_key="test-only", cloud_model="cloud-test")
    monkeypatch.setattr("services.llm.router.load_model_config", lambda: config)

    def post(url, **kwargs):
        result = Mock(status_code=200)
        result.json.return_value = ({"choices": [{"message": {"content": "需要试焊和WPS/PQR验证。"}}]}
                                    if url.endswith("/chat/completions") else {"response": "OK"})
        return result

    monkeypatch.setattr(requests, "post", post)
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.button[0].click().run()
    original = app.session_state["recommendation"]
    app.switch_page("pages/1_模型设置.py").run()
    assert not app.exception
    assert app.metric[0].value == "cloud-test"
    next(button for button in app.button if button.label == "测试连接").click().run()
    assert not app.exception and len(app.success) == 2
    assert app.metric[0].value == "cloud-test"
    app.switch_page("app.py").run()
    assert not app.exception and len(app.tabs) == 4
    assert app.session_state["recommendation"] == original


def test_timeout_details_and_config_reload_without_losing_result(monkeypatch):
    from dataclasses import replace
    from services.llm.config import ModelConfig

    configs = [ModelConfig(cloud_base_url="https://example.invalid/v1", api_key="test-only", cloud_model="cloud-test")]
    monkeypatch.setattr("services.llm.router.load_model_config", lambda: configs[0])

    def post(url, **kwargs):
        if url.endswith("/chat/completions"):
            raise requests.Timeout()
        raise requests.ConnectionError()

    monkeypatch.setattr(requests, "post", post)
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    app.button[0].click().run()
    assert not app.exception
    assert any("联网 API" in item.value and "超时" in item.value for item in app.caption)
    assert any("Ollama" in item.value and "无法连接" in item.value for item in app.caption)
    original = app.session_state["recommendation"]
    old_router = app.session_state["_recommender"].llm
    app.run()
    assert app.session_state["_recommender"].llm is old_router
    configs[0] = replace(configs[0], cloud_seconds=120)
    app.run()
    assert not app.exception
    assert app.session_state["_recommender"].llm.config.cloud_seconds == 120
    assert app.session_state["_recommender"].llm is not old_router
    assert app.session_state["recommendation"] == original
    assert any("模型配置已更新" in item.value for item in app.info)
    success = Mock(status_code=200)
    success.json.return_value = {"choices": [{"message": {"content": "需要试焊和WPS/PQR验证。"}}]}
    monkeypatch.setattr(requests, "post", Mock(return_value=success))
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["recommendation"]["llm_status"]["available"]
    assert not app.session_state["_model_config_changed"]
