import pytest

from agent.input_normalizer import normalize_request, split_material_designation


BASE = {
    "alloy": "6061",
    "temper": "T6",
    "thickness_mm": 3,
    "joint_type": "对接",
    "position": "平焊",
    "preferred_method": "自动推荐",
}


def test_split_combined_designation() -> None:
    assert split_material_designation("6061-T6") == ("6061", "T6")


def test_normalizes_valid_request() -> None:
    result = normalize_request(BASE)
    assert result.material_id == "6061-T6"
    assert result.thickness_mm == 3.0


@pytest.mark.parametrize("value", [0, -1, 100.1, "abc"])
def test_rejects_invalid_thickness(value) -> None:
    payload = {**BASE, "thickness_mm": value}
    with pytest.raises(ValueError):
        normalize_request(payload)

