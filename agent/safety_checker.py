from __future__ import annotations

import re
from typing import Any


NUMERIC_PARAMETER_NAMES = {
    "电流范围",
    "电压范围",
    "焊接速度",
    "气体流量",
    "预热温度",
    "层间温度",
    "焊丝直径",
    "钨极直径",
    "AC频率",
}


class ParameterSafetyChecker:
    """只允许带来源、条件与可信度的数据库参数进入最终结果。"""

    def check(self, parameters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        safe: list[dict[str, Any]] = []
        notices: list[str] = []
        for param in parameters:
            required = (param.get("source_id"), param.get("confidence"), param.get("applicable_conditions"))
            if not all(required):
                notices.append(f"已拦截缺少追溯信息的参数：{param.get('name', '未知参数')}")
                continue
            if param.get("name") in NUMERIC_PARAMETER_NAMES and param.get("value") in (None, "", []):
                notices.append(f"{param['name']}：数据不足，未输出数值。")
                continue
            safe.append(param)
        return safe, notices

    @staticmethod
    def validate_llm_explanation(explanation: str) -> tuple[bool, str]:
        """解释区禁止出现可能被误读为新工艺设定值的数值+关键单位。"""
        critical_value = re.compile(
            r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:[-–~至]\s*\d+(?:\.\d+)?)?\s*"
            r"(?:A\b|V\b|Hz\b|rpm\b|mm/min\b|m/min\b|L/min\b|℃|°C)",
            re.IGNORECASE,
        )
        if critical_value.search(explanation):
            return False, "本地模型解释包含参数型数值，已由安全检查拦截并改用规则解释。"
        return True, ""

