"""Research inventory UI. This page has no Agent/model service dependencies."""
import json
import math
import sqlite3

import pandas as pd
import streamlit as st

from data_manager import DataManager, DataValidationError, ImportFormatError, FIELDS, UNITS, json_schema
from data_manager.schema import schema_rows

st.set_page_config(page_title="科研数据管理", page_icon="🗃️", layout="wide")
st.title("科研数据管理")
st.caption("CSV · Excel · JSON ｜ 原始文件留存 · 单位校验 · 数据版本 · 质量统计")
st.info("当前仅建设数据基础设施。导入不会触发模型训练、预测或优化。缺失测量保持为空。")
manager = DataManager()
dataset = st.radio("数据仓库", ["research", "demo"], horizontal=True,
                   format_func=lambda value: "正式科研数据" if value == "research" else "Demo 导入测试（不计入正式数据）")
if dataset == "demo":
    st.warning("本仓库仅存放 schema_test 测试记录，数量不代表实验数量。")

with st.expander("字段 Schema 与导入约定"):
    st.dataframe(pd.DataFrame(schema_rows()), hide_index=True, use_container_width=True)
    st.caption("alloy、experiment_id、source 必填。数值请使用 thickness[mm] 列名、thickness_unit 列或带单位单元格。"
               "JSON 也支持 {value, unit} 和顶层 units。硬度只接受 HV，咬边为深度 mm，气孔为百分数。"
               "record_kind 默认 experimental；测试记录须填写 schema_test。")
    st.download_button("下载 JSON Schema", json.dumps(json_schema(), ensure_ascii=False, indent=2),
                       "experiment.schema.json", "application/json")
    headers = [f"{f}[{UNITS[f]}]" if f in UNITS else f for f in FIELDS]
    st.download_button("下载空白 CSV 模板", (",".join(headers + ["record_kind"]) + "\n").encode("utf-8-sig"),
                       "experiment_template.csv", "text/csv")

st.subheader("导入与检查")
uploaded = st.file_uploader("选择 CSV、Excel 或 JSON 文件", type=["csv", "xlsx", "xls", "json"])
options = st.columns(2)
sheet = options[0].text_input("Excel 工作表名（留空使用第一张）")
encoding = options[1].selectbox("文本编码", ["utf-8-sig", "gb18030"])
assume_units = st.checkbox("我确认：文件中未标注单位的数值使用 Schema 标准单位", value=False)
st.caption("单位冲突、无效数值、必填缺失和重复编号会阻止整批导入。可选字段缺失、疑似重复测量和统计异常只标记复核。")
if uploaded is not None:
    content = uploaded.getvalue()
    try:
        report = manager.preview_bytes(content, uploaded.name, dataset=dataset, sheet=sheet or None,
                                       encoding=encoding, assume_canonical_units=assume_units)
        check = report.summary()
        cols = st.columns(3)
        cols[0].metric("待导入记录", check["input_count"])
        cols[1].metric("阻断错误", check["error_count"])
        cols[2].metric("复核提示", check["warning_count"])
        if check["issues"]:
            st.dataframe(pd.DataFrame(check["issues"]), hide_index=True, use_container_width=True)
        if check["issues_truncated"]:
            st.caption("问题详情最多显示 2000 项；上方计数及缺失统计包含全部问题。")
        st.download_button("下载检查报告", json.dumps(check, ensure_ascii=False, indent=2), "validation_report.json", "application/json")
        with st.expander("标准化预览（前 100 条）"):
            st.dataframe(pd.DataFrame(report.records[:100]), hide_index=True, use_container_width=True)
        if st.button("导入并创建版本", type="primary", disabled=not report.ok):
            metadata = manager.import_bytes(content, uploaded.name, dataset=dataset, sheet=sheet or None,
                                           encoding=encoding, assume_canonical_units=assume_units)
            st.success(f"已创建 {metadata['dataset_version']}，新增 {metadata['added_count']} 条，累计 {metadata['record_count']} 条。")
    except (ImportFormatError, DataValidationError, ValueError, OSError, sqlite3.Error) as exc:
        st.error(str(exc))
        if isinstance(exc, DataValidationError):
            st.json(exc.report.summary())

st.subheader("数据概览")
try:
    versions = manager.versions(dataset)
    version = st.selectbox("查看数据版本", [v["version"] for v in versions],
                           format_func=lambda v: f"v{v:06d}") if versions else None
    summary = manager.summary(dataset, version=version)
    columns = st.columns(4)
    columns[0].metric("数据量" if dataset == "research" else "测试占位记录数", summary["record_count"])
    columns[1].metric("字段完整度", f"{summary['overall_completeness']:.2f}%")
    columns[2].metric("dataset_version", f"v{version:06d}" if version else "尚无版本")
    details = manager.version_detail(dataset, version) if version else None
    columns[3].metric("更新时间 (UTC)", details["metadata"]["updated_at"][:19].replace("T", " ") if details else "—")
    st.caption("完整度 = 已填写的核心字段单元格 / (记录数 × 17)。含来源字段，0 视为已填写；完整度不代表科研质量或可训练性。")
    charts = st.columns(2)
    for column, key, label in ((charts[0], "alloy_distribution", "材料分布"), (charts[1], "process_distribution", "焊接方法分布")):
        column.write(f"**{label}**")
        if summary[key]:
            column.bar_chart(pd.DataFrame(list(summary[key].items()), columns=[label, "记录数"]).set_index(label))
        else:
            column.info("暂无数据")
    st.dataframe(pd.DataFrame([{"字段": f, "完整度 (%)": p} for f, p in summary["completeness"].items()]),
                 hide_index=True, use_container_width=True)
    if summary["record_count"]:
        st.subheader("记录查看")
        filters = st.columns(2)
        alloy = filters[0].selectbox("材料筛选", [None, *summary["alloy_distribution"]], format_func=lambda v: v or "全部")
        process = filters[1].selectbox("方法筛选", [None, *[v for v in summary["process_distribution"] if v != "未提供"]],
                                       format_func=lambda v: v or "全部")
        count = manager.summary(dataset, version=version, alloy=alloy, process=process)["record_count"]
        page_count = max(1, math.ceil(count / 100))
        page = st.number_input("页码（每页 100 条）", min_value=1, max_value=page_count, value=1, step=1)
        st.caption(f"匹配 {count} 条，共 {page_count} 页；显示标准单位值。")
        st.dataframe(pd.DataFrame(manager.records(dataset, version=version, alloy=alloy, process=process,
                                                  offset=(page-1)*100)), hide_index=True, use_container_width=True)
    else:
        st.info("暂无记录。可以先检查文件，再导入并创建首个版本。")
    if versions:
        with st.expander("历史版本与来源审计"):
            st.dataframe(pd.DataFrame(versions).drop(columns=["canonical_units"]), hide_index=True, use_container_width=True)
            st.json(details["report"])
            st.download_button("下载本版本导入原文件", manager.original_file(dataset, version), details["metadata"]["filename"])
            st.download_button("下载版本元数据", json.dumps(details["metadata"], ensure_ascii=False, indent=2),
                               f"{dataset}_v{version:06d}.json", "application/json")
except (OSError, sqlite3.Error, LookupError) as exc:
    st.error(f"读取数据仓库失败：{exc}")

st.page_link("app.py", label="返回主页")
