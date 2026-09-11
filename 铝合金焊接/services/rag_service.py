from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from utils.config import load_settings
from utils.paths import project_path


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def _tokens(text: str) -> Iterable[str]:
    normalized = re.sub(r"\s+", " ", text.lower())
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    for size in (1, 2, 3):
        for index in range(max(0, len(chinese) - size + 1)):
            yield f"zh:{chinese[index:index + size]}"
    for word in re.findall(r"[a-z0-9][a-z0-9_.+/-]*", normalized):
        yield f"word:{word}"


def hash_embed(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "little")
        index = raw % dimensions
        sign = 1.0 if (raw >> 8) & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    cleaned = re.sub(r"[ \t]+", " ", text).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        if end < len(cleaned):
            boundary = max(cleaned.rfind("\n", start, end), cleaned.rfind("。", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunks.append(cleaned[start:end].strip())
        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _read_documents(path: Path) -> Iterable[tuple[str, int | None, str]]:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        for page_number, page in enumerate(reader.pages, start=1):
            yield path.name, page_number, page.extract_text() or ""
    else:
        yield path.name, None, path.read_text(encoding="utf-8", errors="replace")


class RagService:
    def __init__(self) -> None:
        settings = load_settings()["rag"]
        self.source_dir = project_path(*settings["source_dir"].split("/"))
        self.index_dir = project_path(*settings["index_dir"].split("/"))
        self.chunk_size = int(settings["chunk_size"])
        self.chunk_overlap = int(settings["chunk_overlap"])
        self.top_k = int(settings["top_k"])
        self.dimensions = int(settings["embedding_dimensions"])
        self.index_path = self.index_dir / "knowledge_index.json"

    def build_index(self) -> dict[str, Any]:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        files = sorted(
            path for path in self.source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        for path in files:
            relative_source = str(path.relative_to(self.source_dir)).replace("\\", "/")
            for filename, page, text in _read_documents(path):
                for chunk_number, chunk in enumerate(
                    _split_text(text, self.chunk_size, self.chunk_overlap), start=1
                ):
                    records.append(
                        {
                            "id": f"{relative_source}#p{page or 0}-c{chunk_number}",
                            "source": relative_source,
                            "filename": filename,
                            "page": page,
                            "chunk": chunk_number,
                            "text": chunk,
                            "vector": hash_embed(chunk, self.dimensions),
                        }
                    )
        payload = {
            "schema_version": "1.0",
            "embedding": "deterministic-hashed-char-ngram-v1",
            "dimensions": self.dimensions,
            "records": records,
        }
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return {"files": len(files), "chunks": len(records), "index_path": str(self.index_path)}

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            self.build_index()
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def search(self, query: str, top_k: int | None = None,
               material_priority: str | None = None) -> list[dict[str, Any]]:
        index = self._load_index()
        query_vector = hash_embed(query, int(index["dimensions"]))
        scored: list[dict[str, Any]] = []
        for record in index["records"]:
            scope = self._material_scope(record, material_priority) if material_priority else None
            if material_priority and scope is None:
                continue
            score = sum(left * right for left, right in zip(query_vector, record["vector"]))
            if score <= 0:
                continue
            item = {key: value for key, value in record.items() if key != "vector"}
            item["score"] = round(score, 4)
            if scope is not None:
                item["priority"], item["material_scope"] = scope
            scored.append(item)
        scored.sort(key=lambda item: (item.get("priority", 0), -item["score"]))
        return scored[: top_k or self.top_k]

    @staticmethod
    def _material_scope(record: dict[str, Any], alloy: str) -> tuple[int, str] | None:
        alloy = alloy.upper()
        text = f"{record.get('source', '')} {record.get('text', '')}".upper()
        if re.search(rf"(?<![A-Z0-9]){re.escape(alloy)}(?![A-Z0-9])", text):
            return 0, alloy
        series = f"{alloy[0]}xxx"
        if series.upper() in text or f"{alloy[0]}系" in text:
            return 1, series
        # Explicitly different grades/series are not generic fallback knowledge.
        if re.search(r"(?<![A-Z0-9])[1-8](?:\d{3}|[A-Z]\d{2}|XXX)(?![A-Z0-9])", text):
            return None
        return 2, "通用铝合金"

    @staticmethod
    def detect_potential_conflicts(results: list[dict[str, Any]]) -> list[str]:
        """保守标记不同来源中同类关键参数的不同数值，交给人工核对适用条件。"""
        patterns = {
            "电流": r"(?:电流|current)[^。；\n]{0,30}?(\d+(?:\.\d+)?(?:\s*[-–~至]\s*\d+(?:\.\d+)?)?)\s*A\b",
            "电压": r"(?:电压|voltage)[^。；\n]{0,30}?(\d+(?:\.\d+)?(?:\s*[-–~至]\s*\d+(?:\.\d+)?)?)\s*V\b",
            "气体流量": r"(?:气体流量|gas flow)[^。；\n]{0,30}?(\d+(?:\.\d+)?(?:\s*[-–~至]\s*\d+(?:\.\d+)?)?)\s*(?:L/min|ft³/h|cfh)\b",
            "温度": r"(?:预热|层间|temperature)[^。；\n]{0,30}?(\d+(?:\.\d+)?)\s*(?:℃|°C|°F)",
        }
        conflicts: list[str] = []
        for label, pattern in patterns.items():
            found: dict[str, set[str]] = {}
            for item in results:
                values = set(re.findall(pattern, item.get("text", ""), flags=re.IGNORECASE))
                if values:
                    found.setdefault(item.get("source", "未知来源"), set()).update(values)
            all_values = {value for values in found.values() for value in values}
            if len(found) > 1 and len(all_values) > 1:
                detail = "；".join(f"{source}: {', '.join(sorted(values))}" for source, values in found.items())
                conflicts.append(f"知识片段中的{label}数值可能冲突（也可能适用条件不同），需人工复核：{detail}")
        return conflicts
