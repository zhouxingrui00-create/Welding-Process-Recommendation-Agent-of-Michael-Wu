from utils.config import load_settings


def test_settings_load() -> None:
    settings = load_settings()
    assert settings["app"]["title"]
    assert settings["ollama"]["model"]


def test_seed_json_files_exist() -> None:
    from services.data_service import DataService

    service = DataService()
    assert len(service.material_db["materials"]) >= 6
    assert service.process_db["records"]

