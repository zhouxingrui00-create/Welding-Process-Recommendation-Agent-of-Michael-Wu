import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import Mock

import pytest
import requests

from agent.input_normalizer import normalize_request
from agent.recommender import WeldingRecommender
from services.llm.config import ModelConfig, load_model_config
from services.llm.router import LLMRouter
from services.logging_service import ModelCallLogger


@pytest.fixture
def router(tmp_path):
    return LLMRouter(ModelConfig(cloud_base_url="https://example.invalid/v1", cloud_model="cloud-test",
                                 api_key="test-credential", local_model="local-test"),
                     logger=ModelCallLogger(tmp_path))


def response(data, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


def cloud_response(text="解释需要试焊和WPS/PQR验证。"):
    return response({"choices": [{"message": {"content": text}}]})


def test_cloud_success_protocol_and_no_fallback(router, monkeypatch):
    post = Mock(return_value=cloud_response())
    monkeypatch.setattr(requests, "post", post)
    result = router.explain({"source": "test"})
    assert result.available and result.model == "cloud-test"
    assert not result.fallback_used
    assert post.call_count == 1
    args, kwargs = post.call_args
    assert args[0] == "https://example.invalid/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-credential"
    assert kwargs["json"]["model"] == "cloud-test"
    assert "不得新增" in kwargs["json"]["messages"][0]["content"]
    assert kwargs["timeout"] == (3, 30)
    assert kwargs["allow_redirects"] is False


@pytest.mark.parametrize("failure,code", [
    (requests.ConnectionError("test-credential"), "network"),
    (requests.Timeout("test-credential"), "timeout"),
    (response({}, 401), "authentication"),
    (response({}, 403), "authentication"),
    (response({}, 429), "http_error"),
    (response({}, 500), "http_error"),
    (response({}, 302), "http_error"),
    (response({}), "invalid_response"),
    (response([]), "invalid_response"),
    (cloud_response(" "), "empty_response"),
    (cloud_response(None), "empty_response"),
    (RuntimeError("test-credential"), "internal_error"),
])
def test_cloud_failure_falls_back(router, monkeypatch, failure, code):
    post = Mock(side_effect=[failure, response({"response": "本地解释。"})])
    monkeypatch.setattr(requests, "post", post)
    result = router.generate("test")
    assert result.available and result.provider == "ollama" and result.fallback_used
    assert router.status()["openai-compatible"]["error_code"] == code
    assert post.call_args.args[0].endswith("/api/generate")
    assert post.call_args.kwargs["headers"] is None
    assert post.call_args.kwargs["json"]["stream"] is False
    assert post.call_args.kwargs["timeout"] == (3, 90)


def test_bad_json_falls_back(router, monkeypatch):
    invalid = response({})
    invalid.json.side_effect = ValueError("test-credential")
    monkeypatch.setattr(requests, "post", Mock(side_effect=[invalid, response({"response": "OK"})]))
    assert router.generate("test").fallback_used


def test_both_fail_rules_continue_and_logs_redacted(router, monkeypatch):
    monkeypatch.setattr(requests, "post", Mock(side_effect=requests.ConnectionError("test-credential")))
    request = normalize_request({"alloy": "6061", "temper": "T6", "thickness_mm": 3,
                                 "joint_type": "对接", "position": "平焊"})
    agent = WeldingRecommender(llm_service=router)
    baseline = agent.recommend(request, use_llm=False, write_log=False).to_dict()
    actual = agent.recommend(request, write_log=False).to_dict()
    assert actual["llm_status"]["message"] == "AI解释模块不可用"
    assert actual["explanation"] == baseline["explanation"]
    for key in baseline.keys() - {"llm_status"}:
        assert actual[key] == baseline[key]
    content = next(router.logger.log_dir.glob("*.jsonl")).read_text(encoding="utf-8")
    assert "test-credential" not in content
    assert "test-credential" not in str(router.status())
    records = [json.loads(line) for line in content.splitlines()]
    assert [r["provider"] for r in records] == ["openai-compatible", "ollama"]
    assert all(not r["success"] and r["elapsed_ms"] >= 0 and r["started_at"] for r in records)


def test_cloud_recovery_is_retried_next_call(router, monkeypatch):
    monkeypatch.setattr(requests, "post", Mock(side_effect=[response({}, 503), response({"response": "OK"}), cloud_response()]))
    assert router.generate("test").fallback_used
    assert router.generate("test").provider == "openai-compatible"


def test_local_only_and_disabled_fallback(router, monkeypatch):
    post = Mock(return_value=response({"response": "OK"}))
    monkeypatch.setattr(requests, "post", post)
    local = LLMRouter(replace(router.config, provider="ollama"), logger=router.logger)
    assert local.generate("test").provider == "ollama"
    assert post.call_count == 1 and post.call_args.args[0].endswith("/api/generate")
    post.reset_mock()
    post.side_effect = requests.Timeout()
    no_fallback = LLMRouter(replace(router.config, fallback_enabled=False), logger=router.logger)
    assert no_fallback.generate("test").message == "AI解释模块不可用"
    assert post.call_count == 1


@pytest.mark.parametrize("payload", [{"response": ""}, {"response": None}, {"error": "model not found"}, []])
def test_local_bad_output_degrades(router, monkeypatch, payload):
    monkeypatch.setattr(requests, "post", Mock(side_effect=[response({}, 401), response(payload)]))
    assert not router.generate("test").available


def test_probe_calls_both_and_does_not_change_active_model(router, monkeypatch):
    post = Mock(side_effect=[cloud_response(), cloud_response("OK"), response({"response": "OK"})])
    monkeypatch.setattr(requests, "post", post)
    router.generate("test")
    status = router.test_connections()
    assert all(s["available"] for s in status.values())
    assert router.model == "cloud-test"
    assert all(call.kwargs["timeout"] == (3, 15) for call in post.call_args_list[1:])


def test_logging_failure_does_not_break_generation(router, monkeypatch):
    monkeypatch.setattr(requests, "post", Mock(return_value=cloud_response()))
    monkeypatch.setattr(router.logger, "write", Mock(side_effect=OSError("disk full")))
    assert router.generate("test").available
    assert router.log_error


def test_generation_timeout_separate_from_probe_and_no_stale_attempts(router, monkeypatch):
    router = LLMRouter(replace(router.config, cloud_seconds=120), logger=router.logger)
    post = Mock(side_effect=[cloud_response(), response({"response": "OK"}),
                             requests.Timeout(), response({"response": "OK"}), cloud_response()])
    monkeypatch.setattr(requests, "post", post)
    router.test_connections()
    result = router.generate("test")
    assert result.fallback_used
    assert [item["error_code"] for item in result.attempts] == ["timeout", ""]
    result = router.generate("test")
    assert len(result.attempts) == 1 and result.attempts[0]["available"]
    assert [call.kwargs["timeout"][1] for call in post.call_args_list] == [15, 15, 120, 90, 120]


def test_env_and_yaml_precedence_reload_and_secret_repr(tmp_path, monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    path, env = tmp_path / "models.yaml", tmp_path / ".env"
    path.write_text("cloud:\n  model: yaml-model\nlocal:\n  model: custom-local\ntimeout:\n  cloud_seconds: 9\n", encoding="utf-8")
    env.write_text('LLM_MODEL="env-model"\nLLM_API_KEY=test-secret\nLLM_BASE_URL=https://example.invalid/v1\n', encoding="utf-8")
    config = load_model_config(path, env)
    assert config.cloud_model == "env-model" and config.cloud_seconds == 9
    assert config.local_model == "custom-local"
    assert config.api_key == "test-secret" and "test-secret" not in repr(config)
    monkeypatch.setenv("LLM_MODEL", "process-model")
    assert load_model_config(path, env).cloud_model == "process-model"
    monkeypatch.delenv("LLM_MODEL")
    env.write_text("", encoding="utf-8")
    assert load_model_config(path, env).cloud_model == "yaml-model"
    assert not load_model_config(path, env).api_key


def test_configuration_failure_keeps_rule_path(monkeypatch, tmp_path):
    monkeypatch.setattr("services.llm.router.load_model_config", Mock(side_effect=ValueError("bad config")))
    router = LLMRouter(logger=ModelCallLogger(tmp_path))
    monkeypatch.setattr(requests, "post", Mock(side_effect=requests.ConnectionError()))
    assert router.config_error
    assert router.generate("test").message == "AI解释模块不可用"


def test_missing_key_skips_cloud_network(router, monkeypatch):
    router = LLMRouter(replace(router.config, api_key=""), logger=router.logger)
    post = Mock(return_value=response({"response": "OK"}))
    monkeypatch.setattr(requests, "post", post)
    assert router.generate("test").fallback_used
    assert post.call_count == 1 and post.call_args.args[0].endswith("/api/generate")


@pytest.mark.parametrize("text,accepted", [("需试焊和WPS/PQR验证。", True), ("建议设置为 180 A。", False)])
def test_agent_preserves_structured_result_and_safety_check(router, monkeypatch, text, accepted):
    monkeypatch.setattr(requests, "post", Mock(return_value=cloud_response(text)))
    request = normalize_request({"alloy": "6061", "temper": "T6", "thickness_mm": 3,
                                 "joint_type": "对接", "position": "平焊"})
    agent = WeldingRecommender(llm_service=router)
    baseline = agent.recommend(request, use_llm=False, write_log=False).to_dict()
    actual = agent.recommend(request, write_log=False).to_dict()
    for key in ("method", "parameters", "risks", "knowledge", "validation", "material", "conflicts"):
        assert actual[key] == baseline[key]
    assert actual["explanation"] == (text if accepted else baseline["explanation"])


@pytest.mark.parametrize("timeout", [0, -1, ".nan", ".inf", "invalid"])
def test_invalid_timeout_rejected(tmp_path, monkeypatch, timeout):
    path = tmp_path / "config.yaml"
    path.write_text(f"timeout:\n  cloud_seconds: {timeout}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_model_config(path, tmp_path / ".env")


def test_real_http_transport_for_both_protocols_and_fallback(tmp_path):
    """Local HTTP fixture verifies serialization/transport, not a real model."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, payload))
            cloud = self.path == "/v1/chat/completions"
            authenticated = self.headers.get("Authorization") == "Bearer fixture-key"
            self.send_response(200 if not cloud or authenticated else 401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"choices": [{"message": {"content": "cloud OK"}}]} if cloud else {"response": "local OK"}
            self.wfile.write(json.dumps(data).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        config = ModelConfig(cloud_base_url=url + "/v1", cloud_model="fixture-cloud", api_key="fixture-key", local_base_url=url)
        router = LLMRouter(config, logger=ModelCallLogger(tmp_path))
        assert router.generate("test").text == "cloud OK"
        assert all(s["available"] for s in router.test_connections().values())
        wrong_key = LLMRouter(replace(config, api_key="wrong-key"), logger=router.logger)
        result = wrong_key.generate("test")
        assert result.text == "local OK" and result.fallback_used
        assert [c[0] for c in calls] == ["/v1/chat/completions", "/v1/chat/completions", "/api/generate", "/v1/chat/completions", "/api/generate"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
