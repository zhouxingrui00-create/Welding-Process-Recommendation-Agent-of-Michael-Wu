import streamlit as st

from services.llm.router import LLMRouter
from services.model_session import get_recommender


st.set_page_config(page_title="模型设置", page_icon="⚙️", layout="wide")
st.title("模型设置")
st.caption("联网 API 优先；失败后自动切换 Ollama。模型均不可用时继续规则推荐。")

agent = get_recommender()
if st.button("重新加载配置", help="修改 .env 或 config/model_config.yaml 后点击；仅刷新当前会话。"):
    agent.llm = LLMRouter()
router = agent.llm
config = router.config

st.metric("当前使用模型（最近一次推荐调用）", router.model)
if router.config_error:
    st.warning(router.config_error)
st.write(f"提供方：{config.provider}")
st.write(f"云端模型：{config.cloud_model or '未配置'}")
st.write(f"本地模型：{config.local_model}")
st.write(f"API Key：{'已配置' if config.api_key else '未配置'}")
st.write(f"自动切换 Ollama：{'开启' if config.fallback_enabled else '关闭'}")
st.caption(
    f"连接超时 {config.connect_seconds:g} 秒 · 云端读取超时 {config.cloud_seconds:g} 秒 · "
    f"本地读取超时 {config.local_seconds:g} 秒 · 连接测试读取超时 {config.test_seconds:g} 秒"
)

st.info("在项目 .env 中填写 LLM_PROVIDER、LLM_BASE_URL、LLM_API_KEY、LLM_MODEL。"
        "Base URL 应包含服务商要求的 API 前缀（如 /v1），无需填写 /chat/completions。"
        "本地模型、超时和降级策略在 config/model_config.yaml 中设置。")
st.caption("测试连接会分别向两端发送一条简短生成请求，联网 API 可能产生少量费用。首次加载本地模型较慢时，可调整 test_seconds。")
if st.button("测试连接", type="primary"):
    with st.spinner("正在测试 API 和 Ollama 实际生成能力…"):
        router.test_connections()
if router.log_error:
    st.warning(router.log_error)

for column, (provider, status) in zip(st.columns(2), router.status().items()):
    with column:
        st.subheader("API 状态" if provider == "openai-compatible" else "Ollama 状态")
        show = st.info if status["available"] is None else st.success if status["available"] else st.warning
        show(status["message"])
        st.write(f"模型：{status['model'] or '未配置'}")
        if status["checked_at"]:
            st.caption(f"检查时间：{status['checked_at']} · 响应时间：{status['elapsed_ms']:g} ms")
            if status["error_code"]:
                st.caption(f"错误类型：{status['error_code']}")

states = router.status()
if all(item["available"] is False for item in states.values()):
    st.warning("AI解释模块不可用；规则推荐仍可正常运行。")
