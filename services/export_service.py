from __future__ import annotations

import json
from typing import Any


def _format_value(param: dict[str, Any]) -> str:
    value = param.get("value")
    if isinstance(value, dict) and "min" in value and "max" in value:
        rendered = str(value["min"]) if value["min"] == value["max"] else f"{value['min']}–{value['max']}"
    else:
        rendered = str(value)
    return f"{rendered} {param.get('unit', '')}".strip()


def to_markdown(result: dict[str, Any]) -> str:
    request = result["request"]
    material = result["material"]
    method = result["method"]
    lines = [
        "# 铝合金焊接工艺初选推荐",
        "",
        "> 学习、科研和工艺初选辅助结果；不替代 WPS/PQR、工艺评定或工程规范。",
        "",
        "## 输入条件",
        "",
        f"- 材料：{request['alloy']}-{request['temper']}",
        f"- 板厚：{request['thickness_mm']} mm",
        f"- 接头/位置：{request['joint_type']} / {request['position']}",
        f"- 希望方法：{request['preferred_method']}",
        "",
        "## 材料分析",
        "",
        f"- 合金体系：{material['series']}，{material['alloy_system']}",
        f"- 强化机制：{material['strengthening']}",
        f"- 焊接性：{material['weldability']}",
        "",
        "## 推荐方法",
        "",
        f"- 首选：{method['primary']}",
        f"- 备选：{'、'.join(method['alternatives'])}",
        f"- 理由：{method['reason']}",
        "",
        "## 工艺参数",
        "",
    ]
    for param in result["parameters"]:
        lines.append(
            f"- {param['name']}：{_format_value(param)}；可信度：{param['confidence']}；"
            f"来源：{param['source']['title']}；条件：{param['applicable_conditions']}"
        )
    lines.extend(["", "## 风险", ""])
    lines.extend(f"- {risk['name']}：{risk['message']}" for risk in result["risks"])
    lines.extend(["", "## 工艺解释", "", result["explanation"], "", "## 验证建议", ""])
    lines.extend(f"- {item}" for item in result["validation"])
    lines.extend(["", "## 知识来源", ""])
    for source in result["knowledge"]:
        page = f"，第 {source['page']} 页" if source.get("page") else ""
        lines.append(f"- {source['source']}{page}：{source['text']}")
    return "\n".join(lines)


def to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)

