#!/usr/bin/env python3
"""Crawling and Markdown Cleaning/Normalization Utilities."""

import asyncio
import hashlib
import re
from typing import List
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

EXCLUDE_SOURCE_NORMALIZATION = ["gsm-general-terms-vi", "gsm-merchant-helps-vi"]


def clean_markdown_text(text: str) -> str:
    """Clean raw markdown text: strip images, links, raw URLs, and HTML elements."""
    if not text:
        return ""
    # Strip markdown images ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Convert markdown links [text](url) -> text
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # Strip raw http(s) URLs
    text = re.sub(r"https?://\S+", "", text)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize multiple blank lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def normalize_markdown(raw_text: str, default_title: str = "Chính sách Green SM", source_id: str = None) -> tuple[str, str, str]:
    """Normalize raw text into canonical markdown with heading hierarchy.

    Returns:
        (title, canonical_markdown, content_hash)
    """
    cleaned = clean_markdown_text(raw_text)
    if not cleaned:
        return default_title, f"# {default_title}\n\n*(Không có nội dung)*", hashlib.sha256(b"").hexdigest()

    lines = cleaned.splitlines()
    title = default_title
    body_lines = []

    if source_id in EXCLUDE_SOURCE_NORMALIZATION:
        content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        return title, cleaned, content_hash

    found_title = False
    for i, line in enumerate(lines):
        line_s = line.strip()
        if line_s.startswith("# "):
            title = line_s[2:].strip()
            found_title = True
            body_lines = lines[i+1:]
            break
        elif line_s and not found_title:
            title = line_s
            found_title = True
            body_lines = lines[i+1:]
            break

    normalized_lines = [f"# {title}\n"]

    for line in body_lines:
        s = line.strip()
        if not s:
            normalized_lines.append("")
            continue
        
        if re.match(r"^\d+\.\s+", s):
            normalized_lines.append(f"\n## {s}")
        elif re.match(r"^\d+\.\d+\.\s+", s):
            normalized_lines.append(f"\n### {s}")
        elif s.startswith("### "):
            normalized_lines.append(f"\n### {s[4:].strip()}")
        elif s.startswith("## "):
            normalized_lines.append(f"\n## {s[3:].strip()}")
        elif s.startswith("# "):
            normalized_lines.append(f"\n## {s[2:].strip()}")
        else:
            normalized_lines.append(s)

    normalized_markdown = "\n".join(normalized_lines).strip()
    content_hash = hashlib.sha256(normalized_markdown.encode("utf-8")).hexdigest()

    return title, normalized_markdown, content_hash


async def crawl_help_ids(min_id: int = 411, max_id: int = 483, concurrency: int = 5) -> List[tuple]:
    """Crawl Green SM help documents concurrently by ID range (411..483).

    Returns a list of (help_id, clean_markdown) tuples sorted by help_id.
    """
    sem = asyncio.Semaphore(concurrency)
    items: List[tuple] = []

    async with AsyncWebCrawler() as crawler:
        async def fetch_one(help_id: int):
            async with sem:
                url = f"https://www.greensm.com/vn-vi/helps?id={help_id}"
                try:
                    config = CrawlerRunConfig(
                        cache_mode=CacheMode.BYPASS, 
                        delay_before_return_html=0.8,
                        only_text=True,
                        css_selector=f'#qa-{help_id}',
                    )
                    result = await crawler.arun(url=url, config=config)
                    md = getattr(result, "markdown", "") or ""
                    if isinstance(md, object) and hasattr(md, "raw_markdown"):
                        md = md.raw_markdown
                    cleaned = clean_markdown_text(str(md or ""))
                    if cleaned:
                        print(f"[Crawl4AI] Fetched help id={help_id} ({len(cleaned)} chars)")
                        items.append((help_id, cleaned))
                except Exception as exc:
                    print(f"[Crawl4AI Error] help id={help_id}: {exc}")

        tasks = [fetch_one(hid) for hid in range(min_id, max_id + 1)]
        await asyncio.gather(*tasks)

    items.sort(key=lambda x: x[0])
    return items


async def crawl_one_term(url: str) -> str:
    """Crawl a single general term page section by term ID."""
    term = int(url.split("=")[1]) if "=" in url else 16
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        delay_before_return_html=0.8,
        css_selector=f'#question-{term}',
        only_text=True
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        md = getattr(result, "markdown", "") or ""
        if isinstance(md, object) and hasattr(md, "raw_markdown"):
            md = md.raw_markdown
        return clean_markdown_text(str(md or ""))


async def crawl_policy_page(url: str) -> str:
    """Crawl a standard policy page using Crawl4AI with noise exclusion filters."""
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        delay_before_return_html=1.0,
        only_text=True,
        excluded_tags=["header", "footer", "nav", "aside", "form", "script", "style"],
        remove_overlay_elements=True,
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        md = getattr(result, "markdown", "") or ""
        if isinstance(md, object) and hasattr(md, "raw_markdown"):
            md = md.raw_markdown
        return clean_markdown_text(str(md or ""))
