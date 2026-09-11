"""Schema-only fixtures stay in tmp_path; no experimental measurements are seeded."""
import json

import pytest

from agent.input_normalizer import normalize_request, split_material_designation
from agent.models import WeldingRequest
from agent.recommender import WeldingRecommender
from services.data_service import DataService
from services.material_manager import COLLECTIONS, RECORD_FIELDS, MaterialManager
from services.rag_service import RagService, hash_embed
from utils.paths import project_path


def write_payload(root, kind, payload):
    folder = root / "6A01"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{kind}.json").write_text(json.dumps(payload), encoding="utf-8")


def request_6a01(**updates):
    return normalize_request({
        "alloy": "6a01", "thickness_mm": 3, "joint_type": "对接", "position": "平焊", **updates,
    })


def test_shipped_database_has_no_experimental_records():
    manager = MaterialManager()
    summary = manager.get_summary("6a01")
    assert summary["material"]["alloy"] == "6A01"
    assert summary["counts"] == dict.fromkeys(COLLECTIONS, 0)
    assert summary["tempers"] == summary["welding_methods"] == []
    assert summary["model_status"]["available"] is False
    assert summary["model_status"]["training_samples"] is None
    assert manager.get_knowledge("6A01") == []
    for kind in COLLECTIONS:
        payload = json.loads(project_path("data", "materials", "6A01", f"{kind}.json").read_text(encoding="utf-8"))
        assert payload["records"] == []
        assert set(RECORD_FIELDS) <= payload["record_template"].keys()


@pytest.mark.parametrize("payload", [None, {}, {"records": None}, {"records": []},
                                     {"records": [None, dict.fromkeys(RECORD_FIELDS)]}])
def test_nullable_empty_collections(tmp_path, payload):
    for kind in ("material", *COLLECTIONS):
        write_payload(tmp_path, kind, payload)
    manager = MaterialManager(tmp_path)
    assert manager.get_summary("6A01")["counts"] == dict.fromkeys(COLLECTIONS, 0)
    assert manager.get_welding_cases("6A01", temper="T6", welding_method="TIG") == []


def test_missing_files_and_root_are_safe(tmp_path):
    manager = MaterialManager(tmp_path / "absent")
    assert manager.list_materials() == []
    assert manager.get_summary("6A01")["counts"] == dict.fromkeys(COLLECTIONS, 0)
    result = WeldingRecommender(data_service=DataService(manager)).recommend(
        request_6a01(), use_llm=False, write_log=False,
    )
    assert result.parameters == []
    assert result.material["fusion_risk_level"] == "未知"


def test_invalid_json_and_wrong_record_shapes_warn_without_crashing(tmp_path):
    write_payload(tmp_path, "properties", {"records": "invalid"})
    write_payload(tmp_path, "welding_cases", {"records": [42, {"alloy": "6061", "temper": "T6"}]})
    write_payload(tmp_path, "literature", [])
    (tmp_path / "6A01" / "material.json").write_text("{unfinished", encoding="utf-8")
    summary = MaterialManager(tmp_path).get_summary("6A01")
    assert summary["counts"] == dict.fromkeys(COLLECTIONS, 0)
    assert len(summary["warnings"]) == 5


def test_metadata_queries_and_live_reload(tmp_path):
    # Routing fixtures only: no process settings or measured properties.
    rows = [
        {"id": "schema-test-tig", "temper": "T6", "welding_method": "TIG"},
        {"id": "schema-test-fsw", "temper": "T4", "welding_method": "FSW", "source": None},
        {"id": "empty-template", "alloy": "6A01"},
    ]
    write_payload(tmp_path, "welding_cases", {"records": rows})
    manager = MaterialManager(tmp_path)
    assert manager.get_tempers("6A01") == ["T4", "T6"]
    assert manager.get_welding_methods("6A01") == ["FSW", "TIG"]
    hits = manager.get_welding_cases("6a01", temper="t6", welding_method="tig")
    assert [row["id"] for row in hits] == ["schema-test-tig"]
    assert hits[0]["mechanical_properties"] is None
    assert manager.get_welding_cases("6A01", thickness_mm=3) == []
    write_payload(tmp_path, "welding_cases", {"records": []})
    assert manager.get_welding_cases("6A01") == []
    assert manager.get_tempers("6A01") == []


@pytest.mark.parametrize("value", ["6A01", "6a01-T6", "6A01T6", "6A01－T6"])
def test_6a01_normalization(value):
    alloy, temper = split_material_designation(value)
    assert alloy == "6A01"
    request = request_6a01(alloy=value)
    assert request.temper == (temper or "未知")


@pytest.mark.parametrize("value", ["../6A01", "C:/6A01", "6A01/../6061"])
def test_material_path_is_not_user_controlled(tmp_path, value):
    with pytest.raises(ValueError):
        MaterialManager(tmp_path).get_material(value)


def test_6a01_empty_recommendation_has_no_borrowed_parameters():
    result = WeldingRecommender().recommend(request_6a01(), use_llm=False, write_log=False)
    assert result.parameters == []
    assert result.material["filler_options"] == []
    assert result.material["data_priority"] == ["6A01", "6xxx", "通用铝合金"]
    assert result.knowledge
    assert result.knowledge[0]["material_scope"] == "6xxx"
    assert all("03_2024" not in hit["source"] for hit in result.knowledge)
    assert any("回退" in notice for notice in result.notices)


def test_priority_is_applied_before_rag_top_k(tmp_path):
    service = RagService()
    service.index_path = tmp_path / "index.json"
    query = "6A01 焊接"
    query_vector = hash_embed(query, service.dimensions)
    records = []
    for text, score_factor in (("通用铝合金焊接资料", 1), ("6xxx 系列资料", .5),
                               ("6A01 专项资料", .1), ("7075 专项资料", 1)):
        records.append({"id": text, "source": text, "text": text,
                        "vector": [value * score_factor for value in query_vector]})
    service.index_path.write_text(json.dumps({"dimensions": service.dimensions, "records": records}))
    hits = service.search(query, top_k=3, material_priority="6A01")
    assert [hit["material_scope"] for hit in hits] == ["6A01", "6xxx", "通用铝合金"]
    assert service.search(query, top_k=1, material_priority="6A01")[0]["priority"] == 0
    # Existing material calls keep their original similarity-only ranking.
    assert service.search("6061 焊接", top_k=1)[0]["source"] != "6A01 专项资料"


def test_specialized_records_precede_fallback_in_recommender(tmp_path):
    write_payload(tmp_path, "literature", {"records": [{"id": "routing-fixture", "title": "接口路由测试占位", "source": None}]})
    manager = MaterialManager(tmp_path)
    result = WeldingRecommender(data_service=DataService(manager)).recommend(
        request_6a01(), use_llm=False, write_log=False,
    )
    assert result.knowledge[0]["material_scope"] == "6A01"
    assert "来源待补充" in result.knowledge[0]["source"]
    assert result.parameters == []


@pytest.mark.parametrize("alloy", ["6061", "6063", "5083", "5052", "2024", "7075"])
def test_legacy_materials_remain_identical(alloy):
    service = DataService()
    legacy = next(item for item in service.material_db["materials"] if item["alloy"] == alloy)
    assert service.material_manager.get_material(alloy) == legacy
    request = WeldingRequest(alloy, legacy["supported_tempers"][0], 3, "对接", "平焊")
    material = service.get_material(request)
    assert material == {**legacy, "temper_warning": ""}
