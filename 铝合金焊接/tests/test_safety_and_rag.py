from agent.safety_checker import ParameterSafetyChecker
from services.rag_service import RagService


def test_safety_checker_blocks_untraceable_parameter() -> None:
    safe, notices = ParameterSafetyChecker().check(
        [{"name": "电流范围", "value": {"min": 1, "max": 2}, "unit": "A"}]
    )
    assert safe == []
    assert notices


def test_llm_parameter_like_number_is_rejected() -> None:
    valid, _ = ParameterSafetyChecker.validate_llm_explanation("建议设置为 180 A。")
    assert valid is False
    valid, _ = ParameterSafetyChecker.validate_llm_explanation("6061-T6需要关注热影响区软化。")
    assert valid is True


def test_local_rag_keeps_source_metadata() -> None:
    service = RagService()
    service.build_index()
    hits = service.search("7075 热裂纹 FSW")
    assert hits
    assert hits[0]["source"]
    assert "text" in hits[0]


def test_rag_flags_numeric_conflicts_across_sources() -> None:
    conflicts = RagService.detect_potential_conflicts(
        [
            {"source": "a.md", "text": "建议电流 100-120 A。"},
            {"source": "b.md", "text": "建议电流 140-160 A。"},
        ]
    )
    assert conflicts
