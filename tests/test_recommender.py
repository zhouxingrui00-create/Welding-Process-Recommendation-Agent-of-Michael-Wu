from agent.input_normalizer import normalize_request
from agent.recommender import WeldingRecommender


def make_request(**updates):
    payload = {
        "alloy": "6061",
        "temper": "T6",
        "thickness_mm": 3,
        "joint_type": "对接",
        "position": "平焊",
        "preferred_method": "自动推荐",
        "high_strength": True,
        "low_distortion": True,
        "crack_focus": True,
    }
    payload.update(updates)
    return normalize_request(payload)


def test_acceptance_case_returns_traceable_rule_result() -> None:
    result = WeldingRecommender().recommend(make_request(), use_llm=False, write_log=False)
    assert result.material["alloy"] == "6061"
    assert result.method["primary"] == "TIG"
    assert result.knowledge
    assert result.parameters
    assert all(item.get("source_id") for item in result.parameters)
    assert "WPS/PQR" in result.explanation


def test_tig_numeric_row_only_matches_fillet_conditions() -> None:
    result = WeldingRecommender().recommend(
        make_request(joint_type="T形接头", high_strength=False, low_distortion=False),
        use_llm=False,
        write_log=False,
    )
    current = next(item for item in result.parameters if item["name"] == "电流范围")
    assert current["value"] == {"min": 135, "max": 175}
    assert current["example_data"] is True


def test_7075_auto_prefers_fsw_and_never_gets_arc_parameters() -> None:
    result = WeldingRecommender().recommend(
        make_request(alloy="7075", temper="T6", high_strength=True),
        use_llm=False,
        write_log=False,
    )
    assert result.method["primary"] == "FSW"
    assert result.material["fusion_risk_level"] == "高"
    assert not any(item["name"] == "电流范围" for item in result.parameters)


def test_explicit_7075_tig_is_flagged_without_parameters() -> None:
    result = WeldingRecommender().recommend(
        make_request(alloy="7075", temper="T6", preferred_method="TIG"),
        use_llm=False,
        write_log=False,
    )
    assert result.method["primary"] == "TIG"
    assert result.parameters == []
    assert any("高风险" in notice for notice in result.notices)

