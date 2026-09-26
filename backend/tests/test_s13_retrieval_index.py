"""Offline contracts for versioned collections and reversible source revisions."""

import hashlib
import uuid

import chromadb
import pytest

from app.rag.chunker import LegalChunk, SourceType
from app.rag.vector_store import VectorStore
from scripts import ingest_knowledge_base


class FakeEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.revision = "test-revision"
        self.dim = 3

    def _vector(self, value: str) -> list[float]:
        return [1.0, 0.0, 0.0] if "تعليم" in value or "school" in value else [0.0, 1.0, 0.0]

    def embed_query(self, value: str) -> list[float]:
        return self._vector(value)

    def embed_passages(self, values: list[str]) -> list[list[float]]:
        return [self._vector(value) for value in values]


def chunk(text: str, source: str = "law/demo.md") -> LegalChunk:
    return LegalChunk(
        text=text, text_ar=text, source_file=source,
        source_type=SourceType.LAW, article_number="10", page_number=3,
        law_year=2026,
    )


def test_repeated_ingest_replacement_rollback_and_citation():
    client = chromadb.EphemeralClient()
    model = f"test/e5-{uuid.uuid4().hex}"
    store = VectorStore(embedder=FakeEmbedder(model), client=client)
    assert store.query("school") == []
    first = [chunk("تعليم الأولاد ونفقات المدرسة")]
    assert store.upsert_source(first, source_hash="v1", source_title="مصدر تجريبي", source_status="demo") == 1
    assert store.upsert_source(first, source_hash="v1", source_title="مصدر تجريبي", source_status="demo") == 0
    assert store.count() == 1
    result = store.query("school", use_bm25_rerank=False)
    assert len(result) == 1
    assert "المادة 10" in result[0].citation
    assert "ص. 3" in result[0].citation
    assert "مصدر تجريبي" in result[0].citation

    second = [chunk("تعليم جديد للمدارس")]
    assert store.upsert_source(second, source_hash="v2", source_title="مصدر تجريبي", source_status="demo") == 1
    assert store.count() == 2  # v1 retained, inactive
    assert [row.text for row in store.query("school", use_bm25_rerank=False)] == [second[0].text]
    assert store.upsert_source(second, source_hash="v2", source_title="مصدر تجريبي", source_status="demo") == 0
    assert store.activate_source_revision("law/demo.md", "v1") == 1
    assert [row.text for row in store.query("school", use_bm25_rerank=False)] == [first[0].text]

    other = VectorStore(embedder=FakeEmbedder(f"test/other-{uuid.uuid4().hex}"), client=client)
    assert other.collection_name != store.collection_name
    assert other.count() == 0
    assert store.count() == 2


def test_manifest_mismatch_and_bad_embedding_dimension_rejected():
    client = chromadb.EphemeralClient()
    fake = FakeEmbedder(f"test/e5-{uuid.uuid4().hex}")
    store = VectorStore(embedder=fake, client=client)
    store._collection.modify(metadata={"embedding_model": "wrong"})
    with pytest.raises(RuntimeError, match="Incompatible"):
        VectorStore(embedder=fake, client=client)

    fresh = VectorStore(embedder=FakeEmbedder(f"test/e5-{uuid.uuid4().hex}"), client=client)
    fresh._embedder.embed_passages = lambda values: [[1.0, 0.0] for _ in values]
    with pytest.raises(ValueError, match="dimension"):
        fresh.upsert_source([chunk("تعليم")], source_hash=hashlib.sha256(b"x").hexdigest())
    assert fresh.count() == 0


def test_unreviewed_source_is_not_answer_evidence():
    client = chromadb.EphemeralClient()
    store = VectorStore(embedder=FakeEmbedder(f"test/e5-{uuid.uuid4().hex}"), client=client)
    store.upsert_source([chunk("تعليم غير مراجع", "law/unreviewed.md")],
                        source_hash="draft", source_status="unreviewed")
    assert store.query("تعليم", use_bm25_rerank=False) == []

    store.upsert_source([chunk("تعليم تجريبي", "law/demo.md")],
                        source_hash="demo", source_status="demo")
    rows = store.query("تعليم", use_bm25_rerank=False)
    assert len(rows) == 1
    assert rows[0].metadata["source_status"] == "demo"
    assert "مصدر تجريبي" in rows[0].citation


def test_pdf_page_and_commentary_provenance(tmp_path, monkeypatch):
    law_dir = tmp_path / "law"
    law_dir.mkdir()
    path = law_dir / "source.pdf"
    path.write_bytes(b"%PDF synthetic test input")
    monkeypatch.setattr(ingest_knowledge_base, "_extract_pdf_pages", lambda _: [
        "المادة 9 " + "نص تعليمي للتجربة " * 8,
        "المادة 10 " + "نص طبي للتجربة " * 8,
    ])
    chunks = ingest_knowledge_base.ingest_file(
        path, SourceType.LAW, "legal", 2026, tmp_path, "2026-01-01",
    )
    assert {item.page_number for item in chunks} == {1, 2}
    assert all(item.effective_date == "2026-01-01" for item in chunks)
    assert all(item.to_chroma_document()["metadata"]["page_number"] for item in chunks)

    commentary_dir = tmp_path / "expert_commentary"
    commentary_dir.mkdir()
    commentary = commentary_dir / "note.md"
    commentary.write_text("This is a synthetic expert note about tax procedures. " * 4, encoding="utf-8")
    notes = ingest_knowledge_base.ingest_file(
        commentary, SourceType.EXPERT_COMMENTARY, "guidance", None, tmp_path,
    )
    assert notes and all(item.source_type == SourceType.EXPERT_COMMENTARY for item in notes)
