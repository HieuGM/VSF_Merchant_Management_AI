"""Build a citation-ready Green SM policy corpus with Docling.

Docling does the document parsing (HTML, PDF, DOCX, tables and OCR).  CrewAI is
only used after the normalized documents have been persisted, which makes the
crawl resumable and keeps provenance available outside the vector database.

Run from the repository root:
    backend/.venv/bin/python data/policy/crawler.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("sources.yaml")
DEFAULT_OUTPUT = Path(__file__).with_name("corpus")
ALLOWED_DOMAINS = {"greensm.com", "www.greensm.com", "cdn.xanhsm.com"}


@dataclass(frozen=True)
class PolicySource:
    source_id: str
    title: str
    url: str
    category: str
    audience: str
    locale: str
    authority: str = "official"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PolicySource":
        required = ("id", "title", "url", "category", "audience", "locale")
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ValueError(f"Source is missing required fields: {', '.join(missing)}")
        source = cls(
            source_id=str(value["id"]),
            title=str(value["title"]),
            url=str(value["url"]),
            category=str(value["category"]),
            audience=str(value["audience"]),
            locale=str(value["locale"]),
            authority=str(value.get("authority", "official")),
        )
        source.validate()
        return source

    def validate(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOMAINS:
            raise ValueError(
                f"{self.source_id}: only HTTPS URLs from {sorted(ALLOWED_DOMAINS)} "
                f"are allowed, got {self.url!r}"
            )
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.source_id):
            raise ValueError(f"Invalid source id: {self.source_id!r}")

    def metadata(self, crawled_at: str) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_url": self.url,
            "category": self.category,
            "audience": self.audience,
            "locale": self.locale,
            "authority": self.authority,
            "crawled_at": crawled_at,
        }


def load_sources(path: Path) -> list[PolicySource]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = [PolicySource.from_dict(item) for item in payload.get("sources", [])]
    if not sources:
        raise ValueError(f"No sources configured in {path}")
    ids = [source.source_id for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("Every source id must be unique")
    return sources


def _docling_components() -> tuple[Any, Any]:
    try:
        from docling.document_converter import DocumentConverter
        from docling_core.transforms.chunker.hierarchical_chunker import (
            HierarchicalChunker,
        )
    except ImportError as exc:
        raise RuntimeError(
            "Docling is not installed. Run `cd backend && uv sync` first."
        ) from exc
    return DocumentConverter, HierarchicalChunker


def _frontmatter(metadata: dict[str, str]) -> str:
    serialized = yaml.safe_dump(
        metadata, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    return f"---\n{serialized}\n---\n\n"


def _chunk_records(
    source: PolicySource,
    doc: Any,
    crawled_at: str,
    chunker_cls: Any,
) -> Iterable[dict[str, Any]]:
    metadata = source.metadata(crawled_at)
    for index, chunk in enumerate(chunker_cls().chunk(doc)):
        text = chunk.text.strip()
        if not text:
            continue
        digest = hashlib.sha256(
            f"{source.source_id}:{index}:{text}".encode("utf-8")
        ).hexdigest()[:20]
        yield {
            "chunk_id": f"{source.source_id}-{digest}",
            "text": text,
            "metadata": {**metadata, "chunk_index": index},
        }


def crawl(
    sources: list[PolicySource],
    output_dir: Path,
    *,
    force: bool = False,
    max_pages: int = 500,
    max_file_size_mb: int = 50,
) -> dict[str, int]:
    DocumentConverter, HierarchicalChunker = _docling_components()
    converter = DocumentConverter()
    documents_dir = output_dir / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = output_dir / "chunks.jsonl"
    records: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    counts = {"converted": 0, "cached": 0, "failed": 0, "chunks": 0}

    for source in sources:
        markdown_path = documents_dir / f"{source.source_id}.md"
        if markdown_path.exists() and not force:
            counts["cached"] += 1
            results.append(
                {**source.metadata("unknown"), "status": "cached", "path": str(markdown_path)}
            )
            continue

        crawled_at = datetime.now(timezone.utc).isoformat()
        try:
            conversion = converter.convert(
                source.url,
                raises_on_error=True,
                max_num_pages=max_pages,
                max_file_size=max_file_size_mb * 1024 * 1024,
            )
            markdown = conversion.document.export_to_markdown().strip()
            if not markdown:
                raise ValueError("Docling returned an empty document")
            markdown_path.write_text(
                _frontmatter(source.metadata(crawled_at)) + markdown + "\n",
                encoding="utf-8",
            )
            source_chunks = list(
                _chunk_records(
                    source, conversion.document, crawled_at, HierarchicalChunker
                )
            )
            records.extend(source_chunks)
            counts["converted"] += 1
            counts["chunks"] += len(source_chunks)
            results.append(
                {
                    **source.metadata(crawled_at),
                    "status": "converted",
                    "path": str(markdown_path),
                    "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    "chunks": len(source_chunks),
                }
            )
        except Exception as exc:  # continue the batch and report every failed URL
            counts["failed"] += 1
            results.append(
                {
                    **source.metadata(crawled_at),
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[failed] {source.source_id}: {exc}", file=sys.stderr)

    # A forced run replaces the corpus. A normal run preserves already-built chunks.
    if not force and chunks_path.exists():
        records = [
            json.loads(line)
            for line in chunks_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ] + records
    deduplicated = {record["chunk_id"]: record for record in records}
    chunks_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in deduplicated.values()
        ),
        encoding="utf-8",
    )
    (output_dir / "crawl_manifest.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "results": results,
                "counts": {**counts, "chunks_total": len(deduplicated)},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {**counts, "chunks_total": len(deduplicated)}


def build_crewai_source(output_dir: Path = DEFAULT_OUTPUT) -> Any:
    """Return a CrewAI knowledge source backed by the normalized local corpus."""
    try:
        from crewai.knowledge.source.crew_docling_source import CrewDoclingSource
    except ImportError as exc:
        raise RuntimeError("CrewAI with Docling support is not installed") from exc
    files = sorted((output_dir / "documents").glob("*.md"))
    if not files:
        raise FileNotFoundError(
            f"No normalized documents found in {output_dir}; run this crawler first"
        )
    return CrewDoclingSource(
        file_paths=files,
        metadata={"corpus": "green-sm-policy", "authority": "official"},
        collection_name="green-sm-policy",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="recrawl existing sources")
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--max-file-size-mb", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stats = crawl(
        load_sources(args.manifest),
        args.output,
        force=args.force,
        max_pages=args.max_pages,
        max_file_size_mb=args.max_file_size_mb,
    )
    print(json.dumps(stats, ensure_ascii=False))
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
