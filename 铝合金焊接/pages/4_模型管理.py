"""ML inventory only: page visits never train, predict, or write research data."""
import sqlite3

import pandas as pd
import streamlit as st

from modeling.backends import ALGORITHMS
from modeling.dataset import load_dataset
from modeling.feature_engineering import DEFAULT_FEATURES, TARGETS
from modeling.registry import ModelRegistry

st.set_page_config(page_title="模型管理", page_icon="📈", layout="wide")
st.title("模型管理")
st.caption("焊接参数 → 力学性能 ｜ 模型版本 · 训练状态 · 评价指标")
st.info("当前为机器学习框架阶段，训练未启用。页面不会训练模型或生成实验数据。")

registry = ModelRegistry()
st.subheader("已有模型")
try:
    models = registry.list_models()
    for warning in registry.warnings:
        st.warning(warning)
    cols = st.columns(3)
    cols[0].metric("已训练模型", sum(m["status"] == "trained" for m in models))
    cols[1].metric("训练中", sum(m["status"] == "training" for m in models))
    cols[2].metric("训练失败", sum(m["status"] == "failed" for m in models))
    if not any(m["status"] == "trained" for m in models):
        st.info("暂无训练模型")
    if models:
        labels = {"trained": "已训练", "training": "训练中", "failed": "训练失败"}
        rows = [{"model_version": m["model_version"], "模型": ALGORITHMS[m["algorithm"]],
                 "训练状态": labels[m["status"]], "target": m["target"], "数据版本": m["data_version"],
                 "训练完成时间 (UTC)": m["trained_at"], "训练耗时 (秒)": m["training_duration_seconds"],
                 "MAE": m["metrics"].get("mae"), "RMSE": m["metrics"].get("rmse"),
                 "R²": m["metrics"].get("r2")} for m in models]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("空白指标表示尚未评价或指标不适用。训练中表示任务已开始；进程中断后需人工核查。")
        selected = st.selectbox("查看模型版本", [m["model_version"] for m in models])
        detail = next(m for m in models if m["model_version"] == selected)
        with st.expander("特征、评价与版本详情", expanded=True):
            st.write("特征列表：" + "、".join(detail["feature_list"]))
            st.json(detail)
        if detail["status"] == "trained" and not (registry.root / selected / "model.pkl").is_file():
            st.warning("模型文件缺失，该版本暂不可预测。")
except (OSError, ValueError, KeyError, TypeError) as exc:
    st.warning(f"模型目录暂不可读取：{exc}")

st.subheader("训练准备")
st.selectbox("未来模型类型", list(ALGORITHMS), format_func=ALGORITHMS.get)
target = st.selectbox("目标力学性能", TARGETS,
                      format_func=lambda t: {"tensile_strength": "抗拉强度 (MPa)", "hardness": "硬度 (HV)", "elongation": "延伸率 (%)"}[t])
features = st.multiselect("输入特征", DEFAULT_FEATURES, default=list(DEFAULT_FEATURES))
try:
    dataset = load_dataset(feature_list=features, target=target)
    cols = st.columns(3)
    cols[0].metric("正式数据记录", dataset.total_records)
    cols[1].metric("完整可用记录", len(dataset.inputs))
    cols[2].metric("训练状态", "未启用")
    if not dataset.inputs:
        st.info("暂无可训练数据。请先在科研数据管理中导入有来源、含所选特征及目标实测值的正式记录。")
    st.caption("Demo 不参与训练；缺失值不填补。单个版本对应一项力学性能；不将性能或来源字段作为输入。")
    with st.expander("数据可用性检查"):
        st.json(dataset.summary())
except (OSError, sqlite3.Error, ValueError, LookupError) as exc:
    st.warning(f"暂无法检查训练数据：{exc}")
st.button("开始训练（当前阶段未启用）", disabled=True)
st.page_link("pages/3_科研数据管理.py", label="前往科研数据管理")
st.page_link("app.py", label="返回主页")
