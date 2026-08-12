#!/usr/bin/env python3
"""Main policy crawler and ingestion orchestrator for Xanh SM policies.

Pipeline steps:
1. Crawl raw content using crawl_utils (Crawl4AI) and save to data/policy/raw/
2. Normalize raw markdown into canonical markdown and save to data/policy/processed/
3. Force reindex canonical markdown into PostgreSQL DB & ChromaDB Vector Store via PolicyRagService
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import yaml

# Path & Environment Setup
ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import utilities from crawl_utils
from crawl_utils import (
    normalize_markdown,
    crawl_help_ids,
    crawl_one_term,
    crawl_policy_page,
)

# Import DB and Policy RAG Service
from database.connection import get_db_session
from services.policy_rag_service import PolicyRagService

# Configuration paths
SOURCES_YAML = ROOT / "scripts" / "crawl" / "xanhsm_policy_sources.yaml"
RAW_DIR = ROOT / "data" / "policy" / "raw"
PROCESSED_DIR = ROOT / "data" / "policy" / "processed"
MANIFEST_PATH = RAW_DIR / "fetch_manifest.jsonl"

EXCLUDE_FOOTER = """CÔNG TY CỔ PHẦN DI CHUYỂN XANH VÀ THÔNG MINH GSM
Hotline: 1555
Email: 
Tòa Văn phòng Symphony, đường Chu Huy Mân, khu đô thị Vinhomes Riverside, Phường Phúc Lợi, Thành phố Hà Nội, Việt Nam
GREEN SMTrang chủVề Green SMGiới thiệu ứng dụng Green SM
Người dùngGreen SM CarGreen SM MiniGreen SM PremiumGreen SM LimoGreen AirportGreen TourGreen Liên TỉnhGreen SM BikeGreen SM FoodGreen SM ExpressGreen SM VanGói hội viênThẻ quà tặng
Doanh nghiệpGreen BusinessGreen SM MerchantThẻ doanh nghiệp
Green Partner
Green Ads
Khám pháTài xế Ô tôTài xế Xe máyGreen SM PlatformTrung tâm Tài xế
Tổng hợpTin tứcTrung tâm hỗ trợTuyển dụngƯu đãi
MẠNG XÃ HỘI
Việt Nam
Mã số doanh nghiệp: 0110269067 do Sở Tài chính thành phố Hà Nội cấp lần đầu ngày 01/03/2023.  
Giấy phép vận tải số 9620/GPKDVT do Sở Xây dựng thành phố Hà Nội cấp lần thứ tư ngày 23/09/2025.  
Văn bản xác nhận hoạt động bưu chính số 6150/XN-BTTTT do Bộ Thông Tin và Truyền Thông cấp ngày 13/12/2023.

© 2026 GSM. All rights reserved | Điều khoản & Pháp lý | Chính sách bảo vệ dữ liệu cá nhân | Cài đặt cookies

Trải nghiệm ứng dụng ngay"""


# ----------------------------------------------------------------------
# 1. Crawl Handlers
# ----------------------------------------------------------------------

def help_page_crawler(source_id: str = "gsm-merchant-helps-vi", min_id: int = 411, max_id: int = 483) -> dict:
    """Crawl Green SM help pages by ID range and merge into 1 combined raw markdown file."""
    out_dir = RAW_DIR / source_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[Crawl4AI:help] Crawling help pages (id={min_id}..{max_id}) for {source_id}...")
    help_items = asyncio.run(crawl_help_ids(min_id=min_id, max_id=max_id))
    
    if not help_items:
        print("FAILED: No markdown content retrieved.")
        return {"status": "failed"}

    merged_md_parts = [f"# Hướng dẫn và Hỗ trợ Đối tác Green SM ({source_id})\n"]
    for help_id, md_text in help_items:
        merged_md_parts.append(f"\n## {md_text}")

    combined_md = "\n\n---\n\n".join(merged_md_parts)
    body = combined_md.encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    fetched_at = datetime.now(timezone.utc).isoformat()
    ts = fetched_at.replace(":", "-").replace("+", "").replace(".", "-")[:19]

    md_path = out_dir / f"{ts}-{digest[:16]}.md"
    md_path.write_text(combined_md, encoding="utf-8")

    meta = {
        "source_id": source_id,
        "source_url": "https://www.greensm.com/vn-vi/helps",
        "fetched_at": fetched_at,
        "sha256": digest,
        "raw_path": str(md_path.relative_to(ROOT)),
        "crawler": "crawl_utils.crawl_help_ids",
        "status": "fetched",
        "total_items": len(help_items),
    }
    (out_dir / f"{ts}-{digest[:16]}-metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False) + "\n")

    print(f"OK: Merged {len(help_items)} help items into single raw file: {md_path.name}")
    return {"status": "fetched", "items": len(help_items)}


def general_terms_crawler(source_id: str, urls_with_titles: list[tuple[str, str]]) -> dict:
    """Fetch all general term sections and merge into 1 single combined raw markdown file."""
    out_dir = RAW_DIR / source_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    merged_parts = []
    fetched_count = 0
    
    for url, title in urls_with_titles:
        print(f"[Crawl4AI:term] Fetching term ({url}) …", end=" ", flush=True)
        md_content = asyncio.run(crawl_one_term(url))
        if md_content and len(md_content) > 200:
            merged_parts.append(f"\n# {title}\n\n{md_content}")
            fetched_count += 1
            print("OK")
        else:
            print("EMPTY")

    if not fetched_count:
        print("FAILED: No term content retrieved.")
        return {"status": "failed"}

    combined_md = "\n\n---\n\n".join(merged_parts)
    body = combined_md.encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    fetched_at = datetime.now(timezone.utc).isoformat()
    ts = fetched_at.replace(":", "-").replace("+", "").replace(".", "-")[:19]

    md_path = out_dir / f"{ts}-{digest[:16]}.md"
    md_path.write_text(combined_md, encoding="utf-8")

    meta = {
        "source_id": source_id,
        "source_url": "https://www.greensm.com/vn-vi/terms-policies/general",
        "fetched_at": fetched_at,
        "sha256": digest,
        "raw_path": str(md_path.relative_to(ROOT)),
        "crawler": "crawl_utils.crawl_one_term",
        "status": "fetched",
        "total_terms": fetched_count,
    }
    (out_dir / f"{ts}-{digest[:16]}-metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, ensure_ascii=False) + "\n")

    print(f"OK: Merged {fetched_count} term sections into single raw file: {md_path.name}")
    return {"status": "fetched", "items": fetched_count}


def policy_page_crawler(source_id: str, url: str) -> dict:
    """Crawl standard policy page and store raw content."""
    out_dir = RAW_DIR / source_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Crawl4AI:policy] Fetching {source_id} ({url})...", end=" ", flush=True)
    fetched_at = datetime.now(timezone.utc).isoformat()

    try:
        cleaned_md = asyncio.run(crawl_policy_page(url))
        if not cleaned_md:
            print("FAILED: Empty markdown content retrieved.")
            return {"status": "failed"}

        cleaned_md = cleaned_md.replace(EXCLUDE_FOOTER, "")
        body = cleaned_md.encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()
        ts = fetched_at.replace(":", "-").replace("+", "").replace(".", "-")[:19]

        md_file = out_dir / f"{ts}-{digest[:16]}.md"
        md_file.write_text(cleaned_md, encoding="utf-8")
        meta = {
            "source_id": source_id,
            "source_url": url,
            "fetched_at": fetched_at,
            "sha256": digest,
            "raw_path": str(md_file.relative_to(ROOT)),
            "crawler": "crawl_utils.crawl_policy_page",
            "status": "fetched",
        }
        (out_dir / f"{ts}-{digest[:16]}-metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, ensure_ascii=False) + "\n")

        print(f"OK: Saved raw content to {md_file.name}")
        return {"status": "fetched"}
    except Exception as exc:
        print(f"FAILED: {exc}")
        return {"status": "failed", "error": str(exc)}


# ----------------------------------------------------------------------
# 2. Process & Forced Ingest Pipeline
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 2. Stage Processors (Bronze, Silver, Golden, Store)
# ----------------------------------------------------------------------

CHUNKS_DIR = ROOT / "data" / "policy" / "chunks"


def run_bronze_stage(sources: list[dict]):
    """Bronze Stage: Crawl raw HTML/markdown from web pages into data/policy/raw/."""
    print(f"\n=== Bronze Stage: Crawling {len(sources)} source entries ===")
    processed_sources = set()
    
    general_terms_entries = [s for s in sources if s.get("category") == "general_terms"]
    if general_terms_entries:
        urls_with_titles = [(s.get("canonical_url", ""), s.get("title", "")) for s in general_terms_entries]
        general_terms_crawler(source_id="gsm-general-terms-vi", urls_with_titles=urls_with_titles)
        processed_sources.add("gsm-general-terms-vi")

    for source in sources:
        sid = source.get("id")
        if sid in processed_sources:
            continue

        category = source.get("category", "")
        url = source.get("canonical_url", "")

        if category == "merchant_faq" or sid == "gsm-merchant-helps-vi":
            help_page_crawler(source_id=sid)
            processed_sources.add(sid)
        elif category != "general_terms":
            policy_page_crawler(source_id=sid, url=url)
            processed_sources.add(sid)


def run_silver_stage(source_filter: str | None = None) -> list[dict]:
    """Silver Stage: Read raw files, clean & normalize into canonical markdown under data/policy/processed/."""
    print("\n=== Silver Stage: Cleaning & Normalizing Canonical Markdown ===")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    
    if not RAW_DIR.exists():
        print("No raw policy data directory found.")
        return results

    for source_dir in sorted(RAW_DIR.iterdir()):
        if not source_dir.is_dir():
            continue

        source_id = source_dir.name
        if source_filter and source_id != source_filter:
            continue

        out_source_dir = PROCESSED_DIR / source_id
        out_source_dir.mkdir(parents=True, exist_ok=True)

        md_files = sorted(source_dir.glob("*.md"))
        for md_file in md_files:
            raw_content = md_file.read_text(encoding="utf-8")
            title, canonical_md, digest = normalize_markdown(
                raw_content, default_title=f"Chính sách {source_id}", source_id=source_id
            )

            out_file = out_source_dir / md_file.name
            out_file.write_text(canonical_md, encoding="utf-8")
            print(f"[Silver] Saved canonical markdown to {out_file.relative_to(ROOT)}")

            results.append({
                "source_id": source_id,
                "file_name": md_file.name,
                "title": title,
                "processed_path": str(out_file.relative_to(ROOT)),
                "content_hash": digest,
                "canonical_md": canonical_md,
            })

    return results


def run_golden_stage(silver_docs: list[dict] | None = None, source_filter: str | None = None) -> list[dict]:
    """Golden Stage: Structure-aware LlamaIndex node parsing and export to data/policy/chunks/*.json."""
    print("\n=== Golden Stage: Parsing Structure-Aware Chunks & Exporting JSON ===")
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    db_gen = get_db_session()
    db = next(db_gen)

    golden_results = []

    try:
        rag_service = PolicyRagService(db=db)

        # If silver_docs not supplied, read from PROCESSED_DIR
        if silver_docs is None:
            silver_docs = []
            for source_dir in sorted(PROCESSED_DIR.iterdir()):
                if not source_dir.is_dir():
                    continue
                source_id = source_dir.name
                if source_filter and source_id != source_filter:
                    continue

                for md_file in sorted(source_dir.glob("*.md")):
                    canonical_md = md_file.read_text(encoding="utf-8")
                    title = canonical_md.splitlines()[0].replace("#", "").strip() if canonical_md else source_id
                    digest = hashlib.sha256(canonical_md.encode("utf-8")).hexdigest()
                    silver_docs.append({
                        "source_id": source_id,
                        "file_name": md_file.name,
                        "title": title,
                        "processed_path": str(md_file.relative_to(ROOT)),
                        "content_hash": digest,
                        "canonical_md": canonical_md,
                    })

        for item in silver_docs:
            source_id = item["source_id"]
            title = item["title"]
            canonical_md = item["canonical_md"]
            category = "merchant_faq" if "helps" in source_id or "faq" in source_id else "general_terms"

            nodes = rag_service._parse_markdown_nodes(source_id, title, category, canonical_md, None, source_id)
            chunk_records = []

            for idx, node in enumerate(nodes):
                text_content = node.get_content()
                cid = hashlib.sha256(f"{source_id}:{idx}:{item['content_hash']}".encode("utf-8")).hexdigest()
                sec_path = node.metadata.get("section_path", [])
                sec_title = node.metadata.get("section_title")
                sec_level = node.metadata.get("section_level")

                chunk_records.append({
                    "chunk_id": cid,
                    "chunk_index": idx,
                    "section_title": sec_title,
                    "section_level": sec_level,
                    "section_path": sec_path,
                    "token_count": len(text_content.split()),
                    "content": text_content,
                })

            out_chunks_dir = CHUNKS_DIR / source_id
            out_chunks_dir.mkdir(parents=True, exist_ok=True)
            out_json = out_chunks_dir / f"{Path(item['file_name']).stem}-chunks.json"

            json_payload = {
                "document_id": source_id,
                "title": title,
                "category": category,
                "total_chunks": len(chunk_records),
                "chunks": chunk_records,
            }
            out_json.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[Golden] Saved {len(chunk_records)} chunks to {out_json.relative_to(ROOT)}")
            golden_results.append(json_payload)

    finally:
        db.close()

    return golden_results


def run_store_stage(silver_docs: list[dict] | None = None, source_filter: str | None = None):
    """Store Stage: Force reindex processed markdown and chunks into PostgreSQL DB & ChromaDB Vector Store."""
    print("\n=== Store Stage: Forced Reindexing into PostgreSQL DB & ChromaDB Vector Store ===")
    
    if silver_docs is None:
        silver_docs = run_silver_stage(source_filter=source_filter)

    db_gen = get_db_session()
    db = next(db_gen)

    try:
        rag_service = PolicyRagService(db=db)

        for item in silver_docs:
            source_id = item["source_id"]
            title = item["title"]
            canonical_md = item["canonical_md"]
            digest = item["content_hash"]
            category = "merchant_faq" if "helps" in source_id or "faq" in source_id else "general_terms"
            source_url = f"https://www.greensm.com/vn-vi/{source_id}"

            print(f"[Store] Forced reindexing {source_id} into PostgreSQL & ChromaDB...")
            res = rag_service.ingest_document(
                document_id=source_id,
                title=title,
                category=category,
                source_url=source_url,
                document_text=canonical_md,
                content_hash=digest,
            )
            print(f" -> Store Result: {res}")
    finally:
        db.close()


# ----------------------------------------------------------------------
# 3. Main Pipeline Entrypoint
# ----------------------------------------------------------------------

def main():
    parser = ArgumentParser(description="Crawl & Ingest Xanh SM policy & help pages")
    parser.add_argument("--source", dest="source_filter", help="Only process specific source_id")
    parser.add_argument(
        "--stage",
        choices=["bronze", "silver", "golden", "all"],
        default="all",
        help="Stage to execute: bronze (crawl raw), silver (normalize), golden (chunk json), all",
    )
    parser.add_argument(
        "--store",
        action="store_true",
        default=False,
        help="Store document & chunks into PostgreSQL DB and ChromaDB vector store",
    )
    args = parser.parse_args()

    payload = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8")) or {}
    sources = payload.get("sources", [])

    if args.source_filter:
        sources = [s for s in sources if s.get("id") == args.source_filter]

    # Execute requested stage(s)
    silver_docs = None

    if args.stage in ["bronze", "all"]:
        run_bronze_stage(sources)

    if args.stage in ["silver", "all"]:
        silver_docs = run_silver_stage(source_filter=args.source_filter)

    if args.stage in ["golden", "all"]:
        run_golden_stage(silver_docs=silver_docs, source_filter=args.source_filter)

    if args.store:
        run_store_stage(silver_docs=silver_docs, source_filter=args.source_filter)


if __name__ == "__main__":
    main()