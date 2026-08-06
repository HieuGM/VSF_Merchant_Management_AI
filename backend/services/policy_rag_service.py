"""CrewAI Chroma retrieval over policy chunks stored authoritatively in PostgreSQL."""
from __future__ import annotations

import json
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
        self._rag_client = rag_client

    def sync_index(self) -> int:
        """Upsert all normalized chunks; ingestion itself intentionally lives elsewhere."""
        records = []
        for chunk, document in self._chunk_rows():
            records.append(
                {
                    "doc_id": chunk.chunk_id,
                    "content": chunk.content,
                    "metadata": {
                        "document_id": document.document_id,
                        "category": document.category,
                        "section_path": json.dumps(chunk.section_path, ensure_ascii=False),
                    },
                }
            )
        if records:
            self._client().add_documents(
                collection_name=self._settings.rag_collection,
                documents=records,
            )
        return len(records)

    def search(
        self,
        query: str,
        *,
        categories: list[str] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        filters = categories or []
        metadata_filter = (
            {"category": filters[0]}
            if len(filters) == 1
            else {"category": {"$in": filters}}
            if filters
            else None
        )
        matches = self._client().search(
            collection_name=self._settings.rag_collection,
            query=query,
            limit=top_k,
            score_threshold=self._settings.rag_score_threshold,
            metadata_filter=metadata_filter,
        )
        chunk_ids = [str(match["id"]) for match in matches]
        stored = {
            chunk.chunk_id: (chunk, document)
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

    def _chunk_rows(
        self,
        chunk_ids: list[str] | None = None,
    ) -> list[tuple[PolicyDocumentChunk, PolicyDocument]]:
        statement = (
            select(PolicyDocumentChunk, PolicyDocument)
            .join(
                PolicyDocument,
                PolicyDocument.document_id == PolicyDocumentChunk.document_id,
            )
            .order_by(PolicyDocument.document_id, PolicyDocumentChunk.chunk_index)
        )
        if chunk_ids is not None:
            if not chunk_ids:
                return []
            statement = statement.where(PolicyDocumentChunk.chunk_id.in_(chunk_ids))
        return list(self._db.execute(statement).all())

    def _client(self) -> Any:
        if self._rag_client is not None:
            return self._rag_client
        if not self._settings.policy_rag_configured:
            raise RuntimeError("Policy RAG embedding model and API key are not configured")

        from chromadb.config import Settings as ChromaSettings
        from chromadb.utils.embedding_functions.openai_embedding_function import (
            OpenAIEmbeddingFunction,
        )
        from crewai.rag.chromadb.config import ChromaDBConfig
        from crewai.rag.factory import create_client

        embedding = OpenAIEmbeddingFunction(
            api_key=self._settings.rag_embedding_api_key,
            api_base=self._settings.rag_embedding_base_url,
            model_name=self._settings.rag_embedding_model,
            dimensions=self._settings.rag_embedding_dimensions,
        )
        config = ChromaDBConfig(
            settings=ChromaSettings(
                persist_directory=self._settings.rag_chroma_path,
                is_persistent=True,
                anonymized_telemetry=False,
            ),
            embedding_function=embedding,
            score_threshold=self._settings.rag_score_threshold,
        )
        self._rag_client = create_client(config)
        return self._rag_client
