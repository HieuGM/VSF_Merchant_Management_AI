"""Policy RAG — Chroma retrieval backed by PostgreSQL chunk authoritative store."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.settings import Settings, get_settings
from database.models import PolicyDocument, PolicyDocumentChunk
from models.policy_rag import PolicyChunkEvidence, PolicySearchResult


class PolicyRagService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        rag_client: Any = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._rag_client = rag_client  # injected in tests to avoid real Chroma

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_index(self) -> int:
        """Re-embed and upsert all chunks into Chroma (maintenance job)."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self._settings.rag_embedding_api_key,
            base_url=self._settings.rag_embedding_base_url,
        )
        rows = self._chunk_rows()
        if not rows:
            return 0

        texts = [chunk.content for chunk, _ in rows]
        resp = client.embeddings.create(
            model=self._settings.rag_embedding_model,
            input=texts,
        )
        embeddings = [e.embedding for e in resp.data]

        collection = self._collection()
        ids = [chunk.chunk_id for chunk, _ in rows]
        metadatas = [
            {
                "document_id": doc.document_id,
                "category": doc.category,
                "section_path": json.dumps(chunk.section_path, ensure_ascii=False),
            }
            for chunk, doc in rows
        ]
        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(rows)

    def search(
        self,
        query: str,
        *,
        categories: list[str] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        collection = self._collection()
        # Map common category aliases to stored DB categories
        category_map = {
            "policy": "merchant_code_of_conduct",
            "terms": "general_terms",
            "regulations": "platform_regulations",
            "compliance": "merchant_code_of_conduct",
            "violations": "merchant_code_of_conduct",
            "handbook": "merchant_handbook",
            "faq": "merchant_faq",
            "operations": "merchant_operations",
            "privacy": "privacy",
            "agreement": "service_agreement",
        }

        valid_db_categories = {
            "terms_index", "general_terms", "platform_regulations", "privacy",
            "service_agreement", "consumer_protection", "merchant_code_of_conduct",
            "merchant_handbook", "merchant_landing", "merchant_faq", "merchant_operations"
        }

        mapped_filters = []
        for cat in (categories or []):
            cat_clean = cat.strip().lower()
            if cat_clean in valid_db_categories:
                mapped_filters.append(cat_clean)
            elif cat_clean in category_map:
                mapped_filters.append(category_map[cat_clean])

        where: dict | None = None
        if len(mapped_filters) == 1:
            where = {"category": mapped_filters[0]}
        elif mapped_filters:
            where = {"category": {"$in": list(set(mapped_filters))}}

        # Embed query
        query_embedding = self._embed_query(query)

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["distances", "metadatas", "documents"],
        }
        if where:
            kwargs["where"] = where

        result = collection.query(**kwargs)

        # Fallback: if category filter returned no results, query without category filter
        if (not result.get("ids") or not result["ids"][0]) and where:
            kwargs.pop("where", None)
            result = collection.query(**kwargs)

        ids = result["ids"][0] if result["ids"] else []
        distances = result["distances"][0] if result["distances"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        documents = result["documents"][0] if result["documents"] else []

        # Cosine distance in Chroma (hnsw:space=cosine) ranges from 0 (identical) to 2 (opposite).
        # Cosine similarity = 1.0 - distance.
        threshold = max(0.2, min(self._settings.rag_score_threshold, 0.45))
        matches = [
            {"id": cid, "score": max(0.0, 1.0 - dist), "text": doc, "meta": meta}
            for cid, dist, doc, meta in zip(ids, distances, documents, metadatas)
            if max(0.0, 1.0 - dist) >= threshold
        ]
        # Fallback: if threshold filtered out everything, keep top results
        if not matches and ids:
            matches = [
                {"id": cid, "score": max(0.0, 1.0 - dist), "text": doc, "meta": meta}
                for cid, dist, doc, meta in zip(ids[:top_k], distances[:top_k], documents[:top_k], metadatas[:top_k])
            ]

        # Hydrate from PostgreSQL for authoritative metadata
        chunk_ids = [m["id"] for m in matches]
        stored = {
            str(chunk.chunk_id): (chunk, document)
            for chunk, document in self._chunk_rows(chunk_ids)
        }

        evidence = []
        for match in matches:
            pair = stored.get(str(match["id"]))
            if pair is None:
                continue
            chunk, document = pair
            evidence.append(
                PolicyChunkEvidence(
                    chunk_id=chunk.chunk_id,
                    document_id=document.document_id,
                    title=document.title,
                    source_url=document.source_url,
                    category=document.category,
                    policy_updated_at=document.policy_updated_at,
                    section_path=list(chunk.section_path or []),
                    text=chunk.content,
                    relevance=float(match["score"]),
                )
            )

        return PolicySearchResult(
            count=len(evidence),
            results=evidence,
        ).model_dump(mode="json")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _chunk_rows(
        self,
        chunk_ids: list[str] | None = None,
    ) -> list[tuple[PolicyDocumentChunk, PolicyDocument]]:
        stmt = (
            select(PolicyDocumentChunk, PolicyDocument)
            .join(PolicyDocument, PolicyDocument.document_id == PolicyDocumentChunk.document_id)
            .order_by(PolicyDocument.document_id, PolicyDocumentChunk.chunk_index)
        )
        if chunk_ids is not None:
            if not chunk_ids:
                return []
            stmt = stmt.where(PolicyDocumentChunk.chunk_id.in_(chunk_ids))
        return list(self._db.execute(stmt).all())

    def _collection(self) -> Any:
        """Return Chroma collection (cached on self._rag_client)."""
        if self._rag_client is not None:
            return self._rag_client
        if not self._settings.policy_rag_configured:
            raise RuntimeError("Policy RAG embedding model and API key are not configured")

        import chromadb
        from chromadb.config import Settings as ChromaSettings

        # Chroma path is relative to backend dir
        backend_root = Path(__file__).resolve().parents[1]
        chroma_path = backend_root / self._settings.rag_chroma_path
        chroma_path.mkdir(parents=True, exist_ok=True)

        chroma = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._rag_client = chroma.get_or_create_collection(
            name=self._settings.rag_collection,
            metadata={"hnsw:space": "cosine"},
        )
        return self._rag_client

    def _embed_query(self, query: str) -> list[float]:
        """Embed a single query string for retrieval."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self._settings.rag_embedding_api_key,
            base_url=self._settings.rag_embedding_base_url,
        )
        resp = client.embeddings.create(
            model=self._settings.rag_embedding_model,
            input=[query],
        )
        return resp.data[0].embedding
