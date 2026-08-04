# Green SM policy RAG corpus

This pipeline converts curated, first-party Green SM web pages and linked
documents into normalized Markdown and citation-ready JSONL chunks.

## Why Docling

Docling is the default parser because the corpus mixes HTML, tables, PDFs and
office documents. It also has a native `CrewDoclingSource` adapter in CrewAI
1.15.5. MinerU is a useful optional fallback for difficult scanned PDFs, but it
should not be the web crawler or the system of record.

## Run

From the repository root:

```bash
cd backend
uv sync
cd ..
backend/.venv/bin/python data/policy/crawler.py
```

Outputs are written to `data/policy/corpus/`:

- `documents/*.md`: normalized documents with provenance front matter;
- `chunks.jsonl`: stable chunk IDs, text and retrieval metadata;
- `crawl_manifest.json`: per-source success, checksum and crawl time.

Existing documents are cached. Use `--force` to refresh all sources:

```bash
backend/.venv/bin/python data/policy/crawler.py --force
```

Edit `sources.yaml` to add approved sources. The crawler intentionally accepts
only HTTPS URLs from Green SM domains. Follow robots.txt, website terms,
copyright rules, and an appropriate request rate when expanding discovery.

## CrewAI integration

Attach the normalized corpus to a crew or agent:

```python
from pathlib import Path
from data.policy.crawler import build_crewai_source

policy_knowledge = build_crewai_source(Path("data/policy/corpus"))

crew = Crew(
    agents=[...],
    tasks=[...],
    knowledge_sources=[policy_knowledge],
)
```

The chatbot answer contract should require `source_url`, `title`, and
`crawled_at` citations and should say when evidence is missing or conflicting.
Do not ask an LLM to invent a consolidated corporate policy: generated
summaries are secondary material and must remain traceable to the official
source chunks.

## Optional MinerU fallback

For a scanned document that Docling cannot parse, run MinerU separately, save
its Markdown output under `corpus/documents/`, and keep the same front matter
fields. This keeps CrewAI independent of the extraction backend. MinerU can run
locally or through its API; review data-residency requirements before uploading
internal documents.
