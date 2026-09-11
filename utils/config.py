from functools import lru_cache
from typing import Any

import yaml

from utils.paths import project_path


@lru_cache(maxsize=1)
def load_settings() -> dict[str, Any]:
    with project_path("config", "settings.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)

