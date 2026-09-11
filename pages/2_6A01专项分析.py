"""6A01 inventory and raw record browser; no experimental/model output generation."""
import streamlit as st

from agent.models import SUPPORTED_METHODS
from services.material_manager import MaterialManager, has_data


st.set_page_config(page_title="6A01专项分析", page_icon="🔬", layout="wide")
st.title("6A01专项分析")
st.caption("资料优先级：6A01 专项数据库 → 6xxx 系列 → 通用铝合金知识")
st.button("重新读取材料数据")  # Each rerun reads local JSON; no stale session cache.
manager = MaterialManager()
summary = manager.get_summary("6A01")

st.subheader("材料信息")
material = summary["material"]
labels = {
    "alloy": "材料牌号", "temper": "状态", "chemical_composition": "化学成分",
    "thickness_mm": "厚度 (mm)", "welding_method": "焊接方法",
    "welding_parameters": "焊接参数", "microstructure": "组织信息",
    "mechanical_properties": "力学性能", "defects": "缺陷信息", "source": "来源信息",
}
for field, label in labels.items():
    value = material.get(field)
    if isinstance(value, (dict, list)) and has_data(value):
        with st.expander(label):
            st.json(value)
    else:
        st.write(f"**{label}：** {value if has_data(value) else '待补充'}")
st.caption("已收录状态：" + ("、".join(summary["tempers"]) or "暂无状态数据"))

st.subheader("已有数据数量")
columns = st.columns(3)
for column, (kind, label) in zip(columns, (
    ("properties", "性能记录"), ("welding_cases", "焊接案例"), ("literature", "文献记录"),
)):
    column.metric(label, summary["counts"][kind])
st.caption("按已填写记录计数；空模板不计入。记录数量不代表已审核数量或训练样本数量。")
if not any(summary["counts"].values()):
    st.info("暂无 6A01 实验或文献记录。空数据库可以正常使用，等待导入真实数据。")

st.subheader("支持焊接方法")
st.write("已有资料涉及：" + ("、".join(summary["welding_methods"]) or "暂无方法数据"))
st.caption("接口可按方法查询：" + "、".join(SUPPORTED_METHODS[1:]) + "；也可保存其他方法名称。接口能力不代表已验证工艺。")

st.subheader("未来模型状态")
st.write(summary["model_status"]["status"])
st.caption("预留 ProcessPredictionModel 接口。尚无 6A01 训练样本集、模型权重或性能评估；导入记录不会自动训练模型。")

st.subheader("资料查询")
temper_choice = st.selectbox("按状态筛选案例", ["全部"] + summary["tempers"])
method_choice = st.selectbox("按焊接方法筛选案例", ["全部"] + summary["welding_methods"])
cases = manager.get_welding_cases(
    "6A01", None if temper_choice == "全部" else temper_choice,
    None if method_choice == "全部" else method_choice,
)
for label, records in (
    ("焊接案例", cases), ("性能记录", manager.get_properties("6A01")),
    ("文献记录", manager.get_literature("6A01")),
):
    with st.expander(f"{label}（{len(records)}）"):
        if records:
            st.json(records)
        else:
            st.info("暂无匹配记录。")
for warning in manager.warnings:
    st.warning(warning)
st.page_link("app.py", label="返回焊接工艺推荐")
