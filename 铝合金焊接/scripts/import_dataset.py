"""Import or inspect a research data file without invoking any Agent/model code."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data_manager import DataManager, DataValidationError, ImportFormatError


def main():
    parser = argparse.ArgumentParser(description="科研数据导入：校验、单位换算、版本入库")
    parser.add_argument("file", type=Path)
    parser.add_argument("--dataset", choices=["research", "demo"], default="research")
    parser.add_argument("--root", type=Path, help="仓库目录；默认 data/research")
    parser.add_argument("--sheet", help="Excel 工作表名；默认第一张")
    parser.add_argument("--encoding", default="utf-8-sig", choices=["utf-8-sig", "gb18030"])
    parser.add_argument("--assume-canonical-units", action="store_true", help="明确声明无单位数值使用 Schema 标准单位")
    parser.add_argument("--dry-run", action="store_true", help="只检查，不创建数据版本")
    args = parser.parse_args()
    manager = DataManager(args.root)
    options = dict(dataset=args.dataset, sheet=args.sheet, encoding=args.encoding,
                   assume_canonical_units=args.assume_canonical_units)
    try:
        if args.dry_run:
            report = manager.preview_bytes(args.file.read_bytes(), args.file.name, **options)
            result = report.summary()
            code = 0 if report.ok else 2
        else:
            result = manager.import_file(args.file, **options)
            code = 0
    except DataValidationError as exc:
        result, code = exc.report.summary(), 2
    except (ImportFormatError, OSError, ValueError) as exc:
        result, code = {"ok": False, "error": str(exc)}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
