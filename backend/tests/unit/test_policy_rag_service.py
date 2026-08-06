from datetime import datetime, timezone

from database.models import PolicyDocument, PolicyDocumentChunk
from services.policy_rag_service import PolicyRagService


class FakeRagClient:
    def __init__(self) -> None:
        self.added = []

    def add_documents(self, **kwargs):
        self.added.extend(kwargs["documents"])

    def search(self, **_kwargs):
        return [
            {
                "id": "chunk-fees-1",
                "content": "stale vector copy",
                "metadata": {},
                "score": 0.87,
            },
            {
                "id": "missing-chunk",
                "content": "stale record",
                "metadata": {},
                "score": 0.80,
            },
        ]


def test_policy_rag_hydrates_chroma_ids_from_postgres(db_session):
    updated = datetime(2026, 7, 1, tzinfo=timezone.utc)
    db_session.add(
        PolicyDocument(
            document_id="platform-fees-vi",
            title="Chính sách phí nền tảng",
            source_url="https://www.greensm.com/vn-vi/policy/fees",
            category="fees",
            policy_updated_at=updated,
            content_hash="doc-hash",
        )
    )
    db_session.add(
        PolicyDocumentChunk(
            chunk_id="chunk-fees-1",
            document_id="platform-fees-vi",
            content="Mức phí áp dụng được công bố trong phụ lục hợp đồng.",
            section_path=["Phí dịch vụ"],
            chunk_index=0,
            content_hash="chunk-hash",
        )
    )
    db_session.flush()
    client = FakeRagClient()

    result = PolicyRagService(db_session, rag_client=client).search(
        "phí nền tảng",
        categories=["fees"],
    )

    assert result["count"] == 1
    assert result["results"][0] == {
        "chunk_id": "chunk-fees-1",
        "document_id": "platform-fees-vi",
        "title": "Chính sách phí nền tảng",
        "source_url": "https://www.greensm.com/vn-vi/policy/fees",
        "category": "fees",
        "policy_updated_at": "2026-07-01T00:00:00Z",
        "section_path": ["Phí dịch vụ"],
        "text": "Mức phí áp dụng được công bố trong phụ lục hợp đồng.",
        "relevance": 0.87,
    }


def test_policy_rag_syncs_minimal_chunk_metadata(db_session):
    db_session.add(
        PolicyDocument(
            document_id="merchant-handbook-vi",
            title="Sổ tay đối tác",
            source_url="https://www.greensm.com/vn-vi/merchant-handbook",
            category="merchant-operations",
            content_hash="doc-hash",
        )
    )
    db_session.add(
        PolicyDocumentChunk(
            chunk_id="chunk-handbook-1",
            document_id="merchant-handbook-vi",
            content="Nội dung chính sách.",
            section_path=["Vận hành", "Đơn hàng"],
            chunk_index=0,
            content_hash="chunk-hash",
        )
    )
    db_session.flush()
    client = FakeRagClient()

    count = PolicyRagService(db_session, rag_client=client).sync_index()

    assert count == 1
    assert client.added == [
        {
            "doc_id": "chunk-handbook-1",
            "content": "Nội dung chính sách.",
            "metadata": {
                "document_id": "merchant-handbook-vi",
                "category": "merchant-operations",
                "section_path": '["Vận hành", "Đơn hàng"]',
            },
        }
    ]
