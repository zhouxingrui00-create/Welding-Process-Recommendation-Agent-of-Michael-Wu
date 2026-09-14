from __future__ import annotations

import streamlit as st

from agent.input_normalizer import normalize_request
from services.export_service import to_json, to_markdown
from services.model_session import get_recommender
from services.material_manager import MaterialManager
from utils.config import load_settings


settings = load_settings()
st.set_page_config(page_title=settings["app"]["title"], page_icon="🧰", layout="wide")


def format_parameter_value(param: dict) -> str:
    value = param.get("value")
    if isinstance(value, dict) and "min" in value and "max" in value:
        number = str(value["min"]) if value["min"] == value["max"] else f"{value['min']}–{value['max']}"
    else:
        number = str(value)
    return f"{number} {param.get('unit', '')}".strip()


st.title(settings["app"]["title"])
st.caption("规则 + 可追溯数据 + 本地RAG · 联网AI解释 + Ollama备用")
st.warning("本软件仅用于学习、科研和工艺初选，不替代正式 WPS/PQR、焊接工艺评定、工程规范或持证工程师审核。")

temper_options = {
    "6061": ["T6", "T4", "O"],
    "6063": ["T6", "T4", "O"],
    "5083": ["H111", "H116", "H321", "O", "H系列"],
    "5052": ["H32", "H34", "O", "H系列"],
    "2024": ["T3", "T4"],
    "7075": ["T6", "T651"],
    "6A01": ["未知"],
}

with st.sidebar:
    st.header("材料与焊接条件")
    alloy = st.selectbox("铝合金牌号", list(temper_options))
    if alloy == "6A01":
        available_tempers = MaterialManager().get_tempers(alloy)
        temper = st.text_input("材料状态（可留空）", help="按实际材料填写；留空表示未知，不推定为 T6。")
        if available_tempers:
            st.caption("已收录状态：" + "、".join(available_tempers))
    else:
        temper = st.selectbox("材料状态", temper_options[alloy])
    thickness = st.number_input(
        "板厚 (mm)", min_value=0.1, max_value=float(settings["app"]["max_thickness_mm"]), value=3.0, step=0.1
    )
    joint = st.selectbox("接头形式", ["对接", "搭接", "T形接头", "角接"])
    position = st.selectbox("焊接位置", ["平焊", "横焊", "立焊", "仰焊"])
    method = st.selectbox("希望采用的焊接方法", ["自动推荐", "TIG", "MIG", "激光焊", "FSW"])
    allow_preheat = st.checkbox("允许预热")
    high_strength = st.checkbox("要求较高强度")
    low_distortion = st.checkbox("特别要求低变形")
    crack_focus = st.checkbox("特别关注裂纹", value=True)
    notes = st.text_area("备注（可选）", max_chars=2000)
    use_llm = st.checkbox("使用 AI 生成解释", value=True, help="优先联网 API，失败后使用 Ollama；关闭后只输出规则解释。")
    submitted = st.button("生成焊接工艺推荐", type="primary", use_container_width=True)

    with st.expander("模型状态"):
        st.caption(f"最近调用模型：{get_recommender().llm.model}")
        st.page_link("pages/1_模型设置.py", label="模型设置 / 测试连接", icon="⚙️")
    st.page_link("pages/2_6A01专项分析.py", label="6A01专项分析")
    st.page_link("pages/3_科研数据管理.py", label="科研数据管理", icon="🗃️")
    st.page_link("pages/4_模型管理.py", label="模型管理", icon="📈")

if submitted:
    try:
        request = normalize_request(
            {
                "alloy": alloy,
                "temper": temper,
                "thickness_mm": thickness,
                "joint_type": joint,
                "position": position,
                "preferred_method": method,
                "allow_preheat": allow_preheat,
                "high_strength": high_strength,
                "low_distortion": low_distortion,
                "crack_focus": crack_focus,
                "notes": notes,
            },
            max_thickness_mm=float(settings["app"]["max_thickness_mm"]),
        )
        with st.spinner("正在执行规则筛选、数据库查询、知识检索和AI解释…"):
            recommendation = get_recommender().recommend(request, use_llm=use_llm)
        st.session_state["recommendation"] = recommendation.to_dict()
        st.session_state["_model_config_changed"] = False
    except (ValueError, LookupError) as exc:
        st.error(str(exc))
    except Exception as exc:  # 页面必须可降级，并给出可诊断信息
        st.exception(exc)

result = st.session_state.get("recommendation")
if not result:
    st.info("请在左侧填写条件并生成推荐。AI 模型不可用时，规则、数据库、RAG和导出仍可工作。")
else:
    request = result["request"]
    material = result["material"]
    method_result = result["method"]
    if material["fusion_risk_level"] == "高":
        st.error(f"高风险材料：{request['alloy']}-{request['temper']} 的传统熔焊风险高，禁止直接套用普通 TIG/MIG 参数。")

    summary_tab, params_tab, risks_tab, sources_tab = st.tabs(["综合推荐", "工艺参数", "风险分析", "知识来源"])

    with summary_tab:
        left, right = st.columns(2)
        with left:
            st.subheader("材料分析")
            st.markdown(
                f"**合金体系：** {material['series']} / {material['alloy_system']}  \n"
                f"**强化机制：** {material['strengthening']}  \n"
                f"**焊接性：** {material['weldability']}  \n"
                f"**主要风险：** {'、'.join(material['primary_risks'])}"
            )
        with right:
            st.subheader("推荐焊接方法")
            st.metric("首选方法", method_result["primary"])
            st.write(f"备选方法：{'、'.join(method_result['alternatives'])}")
            st.write(f"推荐原因：{method_result['reason']}")

        st.subheader("工艺解释")
        if material.get("specialized_data"):
            st.caption("资料查询优先级：" + " → ".join(material["data_priority"]))
            with st.expander("6A01 专项材料资料与相关案例"):
                st.json(material["specialized_data"])
                st.json(material["related_cases"])
        if st.session_state.get("_model_config_changed"):
            st.info("模型配置已更新。以下仍是上次生成的结果，请点击左侧“生成焊接工艺推荐”重新生成解释。")
        st.write(result["explanation"])
        if result["llm_status"]["available"]:
            st.caption(f"解释由模型 {result['llm_status']['model']} 整理；结构化参数未由模型生成。")
        else:
            st.info(f"当前使用规则解释：{result['llm_status']['message']}")
            for attempt in result["llm_status"].get("attempts", []):
                if not attempt["available"]:
                    provider = "联网 API" if attempt["provider"] == "openai-compatible" else "Ollama"
                    st.caption(f"{provider}（{attempt['model']}）：{attempt['message']} 耗时 {attempt['elapsed_ms'] / 1000:.1f} 秒。")

        if result["notices"]:
            st.subheader("数据与系统提示")
            for notice in result["notices"]:
                st.warning(notice)
        if result["conflicts"]:
            st.error("检测到来源冲突：" + "；".join(result["conflicts"]))

        st.subheader("验证建议")
        for item in result["validation"]:
            st.write(f"- {item}")

        st.subheader("导出推荐结果")
        export_left, export_right = st.columns(2)
        with export_left:
            st.download_button(
                "下载 Markdown",
                data=to_markdown(result),
                file_name=f"welding-recommendation-{request['alloy']}-{request['temper']}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with export_right:
            st.download_button(
                "下载 JSON",
                data=to_json(result),
                file_name=f"welding-recommendation-{request['alloy']}-{request['temper']}.json",
                mime="application/json",
                use_container_width=True,
            )

    with params_tab:
        st.info("只有命中结构化数据库且具备来源、适用条件和可信度的项目才会显示。标为示例的数据仅可作为试焊起点。")
        if not result["parameters"]:
            st.warning("数据不足 / 需要焊接工艺评定验证。")
        for param in result["parameters"]:
            marker = "（示例数据）" if param.get("example_data") else ""
            with st.expander(f"{param['name']}：{format_parameter_value(param)} {marker}", expanded=True):
                st.write(f"适用条件：{param['applicable_conditions']}")
                st.write(f"可信度：{param['confidence']}")
                if param.get("note"):
                    st.write(f"注意：{param['note']}")
                source = param["source"]
                if source.get("url"):
                    st.markdown(f"来源：[{source['title']}]({source['url']})")
                else:
                    st.write(f"来源：{source['title']}")

    with risks_tab:
        for risk in result["risks"]:
            if risk["level"] == "高":
                st.error(f"{risk['name']}：{risk['message']}")
            else:
                st.warning(f"{risk['name']}：{risk['message']}")

    with sources_tab:
        st.caption("以下片段来自本地知识库。页码仅在PDF能够抽取时显示；Markdown/TXT没有页码。")
        if not result["knowledge"]:
            st.info("当前没有检索到知识片段；可把PDF、TXT或Markdown放入 knowledge/source_docs 后重建索引。")
        for index, item in enumerate(result["knowledge"], start=1):
            page = f" · 第 {item['page']} 页" if item.get("page") else ""
            st.markdown(f"**{index}. {item['source']}{page} · 相关度 {item['score']:.3f}**")
            if item.get("material_scope"):
                st.caption(f"资料层级：{item['material_scope']}")
            st.write(item["text"])
