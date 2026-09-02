from __future__ import annotations

import re
from typing import Any

from agent.models import (
    SUPPORTED_ALLOYS,
    SUPPORTED_JOINTS,
    SUPPORTED_METHODS,
    SUPPORTED_POSITIONS,
    WeldingRequest,
)


TEMPER_ALIASES = {
    "H": "H系列",
    "H系": "H系列",
    "H系列": "H系列",
    "T3/T4": "T4",
}


def split_material_designation(value: str) -> tuple[str, str | None]:
    cleaned = value.strip().upper().replace("—", "-").replace("－", "-")
    match = re.fullmatch(r"(\d{4})(?:-?([A-Z]\d*))?", cleaned)
    if not match:
        raise ValueError("材料牌号格式无效，应类似 6061 或 6061-T6。")
    return match.group(1), match.group(2)


def normalize_request(payload: dict[str, Any], max_thickness_mm: float = 100.0) -> WeldingRequest:
    alloy, embedded_temper = split_material_designation(str(payload.get("alloy", "")))
    temper = str(payload.get("temper") or embedded_temper or "").strip().upper()
    temper = TEMPER_ALIASES.get(temper, temper)
    try:
        thickness = float(payload.get("thickness_mm"))
    except (TypeError, ValueError) as exc:
        raise ValueError("板厚必须是数字，单位为 mm。") from exc

    if alloy not in SUPPORTED_ALLOYS:
        raise ValueError(f"当前演示库暂不支持 {alloy}。")
    if not temper:
        raise ValueError("必须选择材料状态。")
    if not (0 < thickness <= max_thickness_mm):
        raise ValueError(f"板厚必须大于 0 且不超过 {max_thickness_mm:g} mm。")

    joint = str(payload.get("joint_type", ""))
    position = str(payload.get("position", ""))
    method = str(payload.get("preferred_method", "自动推荐"))
    if joint not in SUPPORTED_JOINTS:
        raise ValueError("不支持的接头形式。")
    if position not in SUPPORTED_POSITIONS:
        raise ValueError("不支持的焊接位置。")
    if method not in SUPPORTED_METHODS:
        raise ValueError("不支持的焊接方法。")

    return WeldingRequest(
        alloy=alloy,
        temper=temper,
        thickness_mm=round(thickness, 3),
        joint_type=joint,
        position=position,
        preferred_method=method,
        allow_preheat=bool(payload.get("allow_preheat", False)),
        high_strength=bool(payload.get("high_strength", False)),
        low_distortion=bool(payload.get("low_distortion", False)),
        crack_focus=bool(payload.get("crack_focus", False)),
        notes=str(payload.get("notes", "")).strip()[:2000],
    )

