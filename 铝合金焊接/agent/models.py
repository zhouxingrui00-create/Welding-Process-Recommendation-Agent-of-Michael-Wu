from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SUPPORTED_ALLOYS = ("6061", "6063", "5083", "5052", "2024", "7075")
SUPPORTED_JOINTS = ("对接", "搭接", "T形接头", "角接")
SUPPORTED_POSITIONS = ("平焊", "横焊", "立焊", "仰焊")
SUPPORTED_METHODS = ("自动推荐", "TIG", "MIG", "激光焊", "FSW")


@dataclass(frozen=True)
class WeldingRequest:
    alloy: str
    temper: str
    thickness_mm: float
    joint_type: str
    position: str
    preferred_method: str = "自动推荐"
    allow_preheat: bool = False
    high_strength: bool = False
    low_distortion: bool = False
    crack_focus: bool = False
    notes: str = ""

    @property
    def material_id(self) -> str:
        return f"{self.alloy}-{self.temper}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    request: WeldingRequest
    material: dict[str, Any]
    method: dict[str, Any]
    parameters: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    validation: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    llm_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

