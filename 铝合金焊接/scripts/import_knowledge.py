from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.rag_service import RagService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="重建离线铝合金焊接知识库索引")
    parser.parse_args()
    result = RagService().build_index()
    print(f"索引完成：{result['files']} 个文件，{result['chunks']} 个片段")
    print(f"索引位置：{result['index_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

