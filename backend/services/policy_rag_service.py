"""Policy RAG — PostgreSQL chunk authoritative store & LlamaIndex Vector Store retrieval."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_community.retrievers import BM25Retriever
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.llms import MockLLM
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from core.settings import Settings, get_settings
from database.models import PolicyDocument, PolicyDocumentChunk
from models.policy_rag import PolicyChunkEvidence, PolicySearchResult

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# Default lightweight embedding model for fast local tests
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RETRIEVAL_LIMIT = 20
RESULT_LIMIT = 5


class _RankedRetriever(BaseRetriever):
    def __init__(self, retrieve: Any) -> None:
        super().__init__()
        self._retrieve_nodes = retrieve

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._retrieve_nodes(query_bundle.query_str)


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
        self._embed_model_obj: Any = None

    # ------------------------------------------------------------------
    # Public Ingestion & Sync API
    # ------------------------------------------------------------------

    def ingest_document(
        self,
        *,
        document_id: str,
        title: str,
        category: str,
        source_url: str,
        document_text: str,
        content_hash: str | None = None,
        policy_updated_at: datetime | None = datetime(2025, 7, 31, 0, 0, 0, tzinfo=timezone.utc)
    ) -> dict[str, Any]:
        """Forced reindex of policy document in both PostgreSQL and ChromaDB."""
        now = datetime.now(timezone.utc)

        if not content_hash:
            content_hash = hashlib.sha256(document_text.encode("utf-8")).hexdigest()

        # 1. Force delete existing chunks in PostgreSQL for this document
        self._db.execute(
            delete(PolicyDocumentChunk).where(PolicyDocumentChunk.document_id == document_id)
        )
        
        # 2. Force delete existing vectors in ChromaDB collection for this document
        try:
            collection = self._collection()
            collection.delete(where={"document_id": document_id})
        except Exception as exc:
            print(f"[PolicyRAG Warning] Error clearing vectors for {document_id}: {exc}")

        # 3. Create or Update PolicyDocument in PostgreSQL
        existing_doc = self._db.execute(
            select(PolicyDocument).where(PolicyDocument.document_id == document_id)
        ).scalar_one_or_none()

        if existing_doc:
            existing_doc.title = title
            existing_doc.source_url = source_url
            existing_doc.category = category
            existing_doc.document_text = document_text
            existing_doc.policy_updated_at = policy_updated_at
            existing_doc.content_hash = content_hash
            existing_doc.created_at = now
            doc_obj = existing_doc
        else:
            doc_obj = PolicyDocument(
                document_id=document_id,
                title=title,
                source_url=source_url,
                category=category,
                document_text=document_text,
                policy_updated_at=policy_updated_at,
                content_hash=content_hash,
                created_at=now,
            )
            self._db.add(doc_obj)

        self._db.flush()

        # 4. Chunking with LlamaIndex MarkdownNodeParser + SentenceSplitter
        nodes = self._parse_markdown_nodes(document_id, title, category, document_text, policy_updated_at, source_url)
        chunk_objs = []

        for idx, node in enumerate(nodes):
            text_content = node.get_content()
            c_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
            cid = hashlib.sha256(f"{document_id}:{idx}:{content_hash}".encode("utf-8")).hexdigest()

            sec_path = node.metadata.get("section_path", [])
            sec_title = node.metadata.get("section_title")
            sec_level = node.metadata.get("section_level")
            tok_count = len(text_content.split())

            chunk_item = PolicyDocumentChunk(
                chunk_id=cid,
                document_id=document_id,
                content=text_content,
                section_path=sec_path,
                section_title=sec_title,
                section_level=sec_level,
                token_count=tok_count,
                chunk_index=idx,
                content_hash=c_hash,
                created_at=now,
            )
            chunk_objs.append(chunk_item)
            self._db.add(chunk_item)

        self._db.commit()

        # 5. Vector Store Upsert (batch_size=32 for memory efficiency)
        if chunk_objs:
            self._upsert_document_chunks(chunk_objs, doc_obj, batch_size=32)

        print(f"[PolicyRAG] Forced reindexed {document_id} with {len(chunk_objs)} chunks.")
        return {"status": "reindexed", "document_id": document_id, "chunks": len(chunk_objs)}

    def _upsert_document_chunks(
        self,
        chunks: list[PolicyDocumentChunk],
        doc: PolicyDocument,
        batch_size: int = 32,
    ) -> None:
        """Embed and upsert chunks for a single document in small batches to save RAM."""
        if not chunks:
            return
        collection = self._collection()
        embedder = self._get_embedder()

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]
            embeddings = embedder.get_text_embedding_batch(texts)
            ids = [c.chunk_id for c in batch]
            metadatas = [
                {
                    "document_id": doc.document_id,
                    "category": doc.category,
                    "section_path": json.dumps(c.section_path or [], ensure_ascii=False),
                    "section_title": c.section_title or "",
                }
                for c in batch
            ]
            if hasattr(collection, "upsert"):
                collection.upsert(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )

    def sync_index(self, batch_size: int = 32) -> int:
        """Re-embed and upsert all chunks into Vector Store in memory-safe batches."""
        rows = self._chunk_rows()
        if not rows:
            return 0

        if self._rag_client is not None:
            self._rag_client.add_documents(documents=[
                {
                    "doc_id": chunk.chunk_id,
                    "content": chunk.content,
                    "metadata": {
                        "document_id": document.document_id,
                        "category": document.category,
                        "section_path": json.dumps(chunk.section_path or [], ensure_ascii=False),
                    },
                }
                for chunk, document in rows
            ])
            return len(rows)

        collection = self._collection()
        embedder = self._get_embedder()

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            texts = [c.content for c, _ in batch]
            embeddings = embedder.get_text_embedding_batch(texts)
            ids = [c.chunk_id for c, _ in batch]
            metadatas = [
                {
                    "document_id": doc.document_id,
                    "category": doc.category,
                    "section_path": json.dumps(c.section_path or [], ensure_ascii=False),
                    "section_title": c.section_title or "",
                }
                for c, doc in batch
            ]
            if hasattr(collection, "upsert"):
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
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fuse the top BM25 and dense policy chunks with reciprocal rank fusion."""
        rows = self._chunk_rows(categories=categories)
        if not rows:
            return self._hydrate_matches([])
        bm25 = BM25Retriever.from_texts(
            [chunk.content for chunk, _ in rows],
            ids=[chunk.chunk_id for chunk, _ in rows],
            k=RETRIEVAL_LIMIT,
        )

        def lexical_nodes(text: str) -> list[NodeWithScore]:
            return [
                self._ranked_node(doc.id, 1 / rank)
                for rank, doc in enumerate(bm25.invoke(text), start=1)
            ]

        fused = QueryFusionRetriever(
            [_RankedRetriever(lexical_nodes), _RankedRetriever(self._dense_nodes)],
            llm=MockLLM(),
            mode=FUSION_MODES.RECIPROCAL_RANK,
            similarity_top_k=RESULT_LIMIT,
            num_queries=1,
            use_async=False,
        ).retrieve(query)
        return self._hydrate_matches(
            [{"id": item.node.node_id, "score": item.score or 0.0} for item in fused]
        )

    def _dense_nodes(self, query: str) -> list[NodeWithScore]:
        if self._rag_client is not None and not hasattr(self._rag_client, "query"):
            matches = self._rag_client.search(query=query, top_k=RETRIEVAL_LIMIT)
            return [
                self._ranked_node(item["id"], float(item.get("score", 0.0)))
                for item in matches
            ]

        result = self._collection().query(
            query_embeddings=[self._get_embedder().get_query_embedding(query)],
            n_results=RETRIEVAL_LIMIT,
            include=["distances", "documents"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        documents = result.get("documents", [[]])[0]
        return [
            self._ranked_node(chunk_id, max(0.0, 1.0 - distance))
            for chunk_id, distance, _ in zip(ids, distances, documents)
        ]

    @staticmethod
    def _ranked_node(chunk_id: str, score: float) -> NodeWithScore:
        node = TextNode(id_=chunk_id, text="", metadata={"chunk_id": chunk_id})
        return NodeWithScore(node=node, score=score)

    def _hydrate_matches(self, matches: list[dict[str, Any]]) -> dict[str, Any]:
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
    # Internal Helpers
    # ------------------------------------------------------------------

    def _parse_markdown_nodes(self, document_id: str, title: str, category: str, text: str, policy_updated_at: datetime, source_url: str) -> list[Any]:
        """Parse canonical markdown into LlamaIndex structure-aware nodes."""
        doc = Document(
            id_=document_id,
            text=text,
            metadata={"document_title": title, "category": category, "policy_update_at": policy_updated_at, "source_url": source_url},
        )

        md_parser = MarkdownNodeParser.from_defaults(include_metadata=True)
        sec_nodes = md_parser.get_nodes_from_documents([doc])

        splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=64)
        final_nodes = []

        for sec in sec_nodes:
            sec_header = sec.metadata.get("header_path", "")
            sec_path = [p.strip() for p in sec_header.split(" > ") if p.strip()]
            sub_nodes = splitter.get_nodes_from_documents([sec])

            for sn in sub_nodes:
                sn.metadata["section_path"] = sec_path
                sn.metadata["section_title"] = sec_path[-1] if sec_path else title
                sn.metadata["section_level"] = len(sec_path)
                final_nodes.append(sn)

        return final_nodes if final_nodes else [doc]

    def _get_embedder(self) -> Any:
        """Return HuggingFace BGE lightweight embedding model instance."""
        if self._embed_model_obj is not None:
            return self._embed_model_obj
        self._embed_model_obj = HuggingFaceEmbedding(
            model_name=self._settings.rag_embedding_model,
            local_files_only=True,
        )
        return self._embed_model_obj

    def _chunk_rows(
        self,
        chunk_ids: list[str] | None = None,
        categories: list[str] | None = None,
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
        if categories:
            stmt = stmt.where(PolicyDocument.category.in_(categories))
        return list(self._db.execute(stmt).all())

    def _collection(self) -> Any:
        if self._rag_client is not None:
            return self._rag_client

        backend_root = Path(__file__).resolve().parents[1]
        chroma_path = backend_root / self._settings.rag_chroma_path
        chroma_path.mkdir(parents=True, exist_ok=True)

        chroma = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        
        collection_name = self._settings.rag_collection
        self._rag_client = chroma.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._rag_client
