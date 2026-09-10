"""Probe configured real services with neutral prompts; no welding data is sent."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.llm.router import LLMRouter


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    router = LLMRouter()
    statuses = router.test_connections()
    print(json.dumps({"config_error": router.config_error, "services": statuses}, ensure_ascii=False, indent=2))
    return 0 if all(status["available"] for status in statuses.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
