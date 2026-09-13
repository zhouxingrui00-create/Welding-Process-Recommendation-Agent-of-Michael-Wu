"""Append-only SQLite versions, atomic batch imports, and paginated read APIs."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from utils.paths import project_path
from .importers import read_table
from .schema import FIELDS, SCHEMA_VERSION, UNITS
from .validation import ValidationReport, check_duplicates, check_outliers, validate


class DataValidationError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__(f"导入被阻止：{report.summary()['error_count']} 项错误，未写入数据或版本。")


class DataManager:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else project_path("data", "research")
        self.db_path = self.root / "datasets.sqlite3"

    @staticmethod
    def _dataset(dataset):
        if dataset not in ("research", "demo"):
            raise ValueError("dataset 必须是 research 或 demo。")

    @contextmanager
    def _connection(self, write=False):
        if not write and not self.db_path.exists():
            yield None
            return
        if write:
            self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.db_path), timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            if write:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript('''
                    CREATE TABLE IF NOT EXISTS versions (
                        dataset TEXT NOT NULL, version INTEGER NOT NULL, metadata TEXT NOT NULL,
                        report TEXT NOT NULL, original BLOB NOT NULL,
                        PRIMARY KEY(dataset, version));
                    CREATE TABLE IF NOT EXISTS records (
                        id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, version INTEGER NOT NULL,
                        source TEXT NOT NULL, experiment_id TEXT NOT NULL,
                        alloy TEXT NOT NULL, process TEXT, record TEXT NOT NULL, input_row INTEGER NOT NULL,
                        UNIQUE(dataset, source, experiment_id),
                        FOREIGN KEY(dataset, version) REFERENCES versions(dataset, version));
                    CREATE INDEX IF NOT EXISTS records_version ON records(dataset, version);
                    CREATE INDEX IF NOT EXISTS records_material ON records(dataset, alloy, process);
                ''')
                connection.execute("BEGIN IMMEDIATE")
            else:
                connection.execute("BEGIN")  # Keep multi-query summaries on one consistent snapshot.
            yield connection
            if write:
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _existing(connection, dataset):
        if connection is None:
            return iter(())
        return (json.loads(row[0]) for row in connection.execute(
            "SELECT record FROM records WHERE dataset=?", (dataset,)))

    def preview_bytes(self, content: bytes, filename: str, *, dataset="research",
                      sheet=None, encoding="utf-8-sig", assume_canonical_units=False) -> ValidationReport:
        self._dataset(dataset)
        table = read_table(content, filename, sheet=sheet, encoding=encoding)
        report = validate(table, dataset=dataset, assume_canonical_units=assume_canonical_units)
        with self._connection() as connection:
            check_duplicates(report, self._existing(connection, dataset))
            check_outliers(report, self._existing(connection, dataset))
        return report

    def import_file(self, path: Path | str, **options) -> dict:
        path = Path(path)
        return self.import_bytes(path.read_bytes(), path.name, **options)

    def import_bytes(self, content: bytes, filename: str, *, dataset="research", sheet=None,
                     encoding="utf-8-sig", assume_canonical_units=False) -> dict:
        self._dataset(dataset)
        table = read_table(content, filename, sheet=sheet, encoding=encoding)
        report = validate(table, dataset=dataset, assume_canonical_units=assume_canonical_units)
        if not report.ok:
            raise DataValidationError(report)
        # Recheck duplicates under the same write lock as the commit (no preview/commit race).
        with self._connection(write=True) as connection:
            check_duplicates(report, self._existing(connection, dataset))
            check_outliers(report, self._existing(connection, dataset))
            if not report.ok:
                raise DataValidationError(report)
            latest = connection.execute("SELECT MAX(version) FROM versions WHERE dataset=?", (dataset,)).fetchone()[0] or 0
            existing_count = connection.execute("SELECT COUNT(*) FROM records WHERE dataset=?", (dataset,)).fetchone()[0]
            version = latest + 1
            metadata = {"dataset": dataset, "dataset_version": f"v{version:06d}", "version": version,
                        "parent_version": f"v{latest:06d}" if latest else None,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "record_count": existing_count + len(report.records), "added_count": len(report.records),
                        "schema_version": SCHEMA_VERSION, "filename": Path(filename).name,
                        "file_sha256": sha256(content).hexdigest(), "sheet": table.sheet,
                        "encoding": encoding, "assume_canonical_units": assume_canonical_units,
                        "canonical_units": UNITS, "warning_count": report.summary()["warning_count"]}
            connection.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?)",
                               (dataset, version, json.dumps(metadata, ensure_ascii=False),
                                json.dumps(report.summary(), ensure_ascii=False), content))
            connection.executemany('''INSERT INTO records
                (dataset, version, source, experiment_id, alloy, process, record, input_row)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                ((dataset, version, record["source"], record["experiment_id"], record["alloy"],
                  record["process"], json.dumps(record, ensure_ascii=False, allow_nan=False), row)
                 for row, record in zip(report.row_numbers, report.records)))
        return metadata

    def versions(self, dataset="research") -> list[dict]:
        self._dataset(dataset)
        with self._connection() as connection:
            if connection is None:
                return []
            return [json.loads(row[0]) for row in connection.execute(
                "SELECT metadata FROM versions WHERE dataset=? ORDER BY version DESC", (dataset,))]

    @staticmethod
    def _where(dataset, version=None, alloy=None, process=None):
        query, params = "dataset=?", [dataset]
        if version is not None:
            if not isinstance(version, int) or version < 1:
                raise ValueError("版本号必须为正整数。")
            query += " AND version<=?"
            params.append(version)
        for name, value in (("alloy", alloy), ("process", process)):
            if value is not None:
                query += f" AND {name}=?"
                params.append(value)
        return query, params

    def records(self, dataset="research", *, version=None, alloy=None, process=None,
                limit=100, offset=0) -> list[dict]:
        self._dataset(dataset)
        if not 1 <= limit <= 10000 or offset < 0:
            raise ValueError("limit 应在 1–10000 内，offset 不能为负。")
        where, params = self._where(dataset, version, alloy, process)
        with self._connection() as connection:
            self._require_version(connection, dataset, version)
            if connection is None:
                return []
            return [dict(json.loads(row["record"]), imported_version=f"v{row['version']:06d}",
                         input_row=row["input_row"])
                    for row in connection.execute(
                        f"SELECT record,version,input_row FROM records WHERE {where} ORDER BY id LIMIT ? OFFSET ?",
                        [*params, limit, offset])]

    def summary(self, dataset="research", *, version=None, alloy=None, process=None):
        self._dataset(dataset)
        where, params = self._where(dataset, version, alloy, process)
        result = {"record_count": 0, "completeness": dict.fromkeys(FIELDS, 0),
                  "alloy_distribution": {}, "process_distribution": {}, "overall_completeness": 0}
        with self._connection() as connection:
            self._require_version(connection, dataset, version)
            if connection is None:
                return result
            result["record_count"] = connection.execute(f"SELECT COUNT(*) FROM records WHERE {where}", params).fetchone()[0]
            count = result["record_count"]
            # Field names come exclusively from the fixed contract, never user SQL input.
            columns = ",".join(f"COUNT(json_extract(record, '$.{name}'))" for name in FIELDS)
            filled = connection.execute(f"SELECT {columns} FROM records WHERE {where}", params).fetchone()
            result["completeness"] = {name: round(value / count * 100, 2) if count else 0
                                      for name, value in zip(FIELDS, filled)}
            result["overall_completeness"] = round(sum(filled) / (count * len(FIELDS)) * 100, 2) if count else 0
            for name in ("alloy", "process"):
                result[name + "_distribution"] = {row[0] or "未提供": row[1] for row in connection.execute(
                    f"SELECT {name}, COUNT(*) FROM records WHERE {where} GROUP BY {name}", params)}
        return result

    @staticmethod
    def _require_version(connection, dataset, version):
        if version is not None and (connection is None or connection.execute(
                "SELECT 1 FROM versions WHERE dataset=? AND version=?", (dataset, version)).fetchone() is None):
            raise LookupError("版本不存在。")

    def version_detail(self, dataset, version):
        self._dataset(dataset)
        with self._connection() as connection:
            if connection is None:
                raise LookupError("没有数据版本。")
            row = connection.execute("SELECT metadata,report FROM versions WHERE dataset=? AND version=?", (dataset, version)).fetchone()
            if row is None:
                raise LookupError("版本不存在。")
            return {"metadata": json.loads(row[0]), "report": json.loads(row[1])}

    def original_file(self, dataset, version) -> bytes:
        self._dataset(dataset)
        with self._connection() as connection:
            row = connection.execute("SELECT original FROM versions WHERE dataset=? AND version=?", (dataset, version)).fetchone() if connection else None
            if row is None:
                raise LookupError("版本不存在。")
            return bytes(row[0])
