"""
vector_store.py — ChromaDB embedded vector store for the RAG pipeline.

ChromaDB runs in-process (no separate server needed for dev).
Hybrid retrieval: ChromaDB cosine similarity + optional BM25 re-ranking for
exact Arabic/legal term matching.
"""

from __future__ import annotations

import logging
import os
import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from app.config import settings

from .chunker import LegalChunk
from .embedder import Embedder

logger = logging.getLogger(__name__)

COLLECTION_NAME = "tax_law_jordan"  # Legacy v1 collection; never delete it automatically.


def _default_persist_dir() -> str:
    return settings.CHROMA_PERSIST_DIR


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float
    metadata: dict

    @property
    def citation(self) -> str:
        source = self.metadata.get("source_title") or self.metadata.get("source_file", "")
        art = self.metadata.get("article_number", "")
        clause = self.metadata.get("clause", "")
        page = self.metadata.get("page_number", "")
        year = self.metadata.get("law_year", "")
        status = self.metadata.get("source_status", "")
        parts = [source, f"المادة {art}" if art else "", clause,
                 f"ص. {page}" if page else "", str(year) if year else "",
                 "مصدر تجريبي" if status == "demo" else ""]
        return " - ".join(str(part) for part in parts if part)


class VectorStore:
    def __init__(self, persist_dir: str | None = None, *, embedder: Embedder | None = None, client=None) -> None:
        if persist_dir is None:
            persist_dir = _default_persist_dir()
        if client is None:
            try:
                import chromadb
                from chromadb.config import Settings
            except ImportError as exc:
                raise RuntimeError("chromadb is not installed. Run: uv add chromadb") from exc
            os.makedirs(persist_dir, exist_ok=True)
            client = chromadb.PersistentClient(
                path=persist_dir, settings=Settings(anonymized_telemetry=False),
            )
        self._client = client
        self._embedder = embedder or Embedder.get()
        identity = {
            "schema_version": settings.RAG_COLLECTION_VERSION,
            "embedding_model": self._embedder.model_name,
            "embedding_revision": self._embedder.revision,
            "embedding_dimension": self._embedder.dim,
        }
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
        self.collection_name = f"{COLLECTION_NAME}_v{settings.RAG_COLLECTION_VERSION}_{digest}"
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine", **identity},
        )
        stored = self._collection.metadata or {}
        if any(stored.get(key) != value for key, value in identity.items()):
            raise RuntimeError(f"Incompatible RAG collection manifest: {self.collection_name}")
        logger.info(
            "VectorStore ready. Collection '%s' has %d documents.",
            self.collection_name,
            self._collection.count(),
        )

    def upsert_source(self, chunks: list[LegalChunk], *, source_hash: str,
                      source_title: str = "", source_status: str = "unreviewed",
                      source_url: str = "") -> int:
        """Upsert one source revision, retiring old chunks without deleting them."""
        if not chunks:
            return 0
        source_file = chunks[0].source_file
        if any(chunk.source_file != source_file for chunk in chunks):
            raise ValueError("upsert_source accepts one source file at a time")
        if source_status not in {"demo", "unreviewed", "reviewed"}:
            raise ValueError("Unknown source review status")
        existing = self._collection.get(where={"source_file": source_file}, include=["metadatas"])
        old_ids = existing["ids"]
        new_ids = [_chunk_id(chunk, index, source_hash) for index, chunk in enumerate(chunks)]
        active = [(old_id, meta) for old_id, meta in zip(old_ids, existing["metadatas"])
                  if meta.get("active") is True]
        if (set(old_id for old_id, _ in active) == set(new_ids)
                and all(meta.get("source_title") == source_title
                        and meta.get("source_status") == source_status
                        and meta.get("source_url") == source_url for _, meta in active)):
            return 0

        texts = [c.text for c in chunks]
        metadatas = [{**c.to_chroma_document()["metadata"],
                      "source_hash": source_hash, "source_title": source_title,
                      "source_status": source_status, "source_url": source_url,
                      "active": True} for c in chunks]
        embeddings = self._embedder.embed_passages(texts)
        if any(len(vector) != self._embedder.dim for vector in embeddings):
            raise ValueError("Embedding dimension differs from the collection manifest")

        self._collection.upsert(
            ids=new_ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        obsolete = [(old_id, meta) for old_id, meta in zip(old_ids, existing["metadatas"])
                    if old_id not in set(new_ids) and meta.get("active") is True]
        if obsolete:
            self._collection.update(
                ids=[item[0] for item in obsolete],
                metadatas=[{**item[1], "active": False} for item in obsolete],
            )
        logger.info("Upserted %d chunks from %s into '%s'.", len(chunks), source_file, self.collection_name)
        return len(chunks)

    def activate_source_revision(self, source_file: str, source_hash: str) -> int:
        """Switch a source back to an indexed revision without deleting newer evidence."""
        existing = self._collection.get(where={"source_file": source_file}, include=["metadatas"])
        rows = list(zip(existing["ids"], existing["metadatas"]))
        if not any(meta.get("source_hash") == source_hash for _, meta in rows):
            raise ValueError("Source revision not found")
        changed = [(old_id, {**meta, "active": meta.get("source_hash") == source_hash})
                   for old_id, meta in rows if meta.get("active") != (meta.get("source_hash") == source_hash)]
        if changed:
            self._collection.update(
                ids=[item[0] for item in changed],
                metadatas=[item[1] for item in changed],
            )
        return sum(meta.get("source_hash") == source_hash for _, meta in rows)

    def upsert_chunks(self, chunks: list[LegalChunk]) -> int:
        """Compatibility helper; source-aware ingestion should call upsert_source."""
        grouped: dict[str, list[LegalChunk]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk.source_file, []).append(chunk)
        return sum(self.upsert_source(group, source_hash=hashlib.sha256(
            "\n".join(chunk.text for chunk in group).encode()).hexdigest())
            for group in grouped.values())

    def query(
        self,
        question: str,
        top_k: int = 5,
        source_type_filter: Optional[str] = None,
        use_bm25_rerank: bool = True,
    ) -> list[RetrievedChunk]:
        if top_k <= 0 or self._collection.count() == 0:
            return []
        query_vec = self._embedder.embed_query(question)
        if len(query_vec) != self._embedder.dim:
            raise ValueError("Query embedding dimension differs from the collection manifest")

        # Unreviewed material may be staged or indexed for audit, but must
        # never become answer evidence. Demo fixtures remain queryable and
        # visibly labeled until a reviewed legal corpus replaces them.
        conditions: list[dict] = [
            {"active": True},
            {"source_status": {"$in": ["demo", "reviewed"]}},
        ]
        if source_type_filter:
            conditions.append({"source_type": source_type_filter})
        where_filter = {"$and": conditions}

        n_candidates = top_k * 2 if use_bm25_rerank else top_k
        results = self._collection.query(
            query_embeddings=[query_vec],
            n_results=min(n_candidates, self._collection.count()),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        retrieved: list[RetrievedChunk] = []
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i]
            similarity = 1.0 - distance
            meta = results["metadatas"][0][i]
            chunk_id = results["ids"][0][i]
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=doc,
                    score=round(similarity, 4),
                    metadata=meta,
                )
            )

        if use_bm25_rerank and len(retrieved) > top_k:
            retrieved = _bm25_rerank(question, retrieved, top_k)
        else:
            retrieved = retrieved[:top_k]

        return retrieved

    def count(self) -> int:
        return self._collection.count()

def _chunk_id(chunk: LegalChunk, index: int, source_hash: str) -> str:
    payload = f"{chunk.source_file}\n{source_hash}\n{index}\n{chunk.text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bm25_rerank(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.debug("rank_bm25 not installed — skipping BM25 rerank.")
        return candidates[:top_k]

    def _tokenize(text: str) -> list[str]:
        import re
        return re.findall(r"\w+", text.lower())

    corpus = [_tokenize(c.text) for c in candidates]
    bm25 = BM25Okapi(corpus)
    query_tokens = _tokenize(query)
    bm25_scores = bm25.get_scores(query_tokens)

    max_bm25 = float(max(bm25_scores)) if len(bm25_scores) > 0 else 1.0
    if max_bm25 <= 0:
        max_bm25 = 1.0
    norm_bm25 = [float(s) / max_bm25 for s in bm25_scores]

    combined = []
    for i, chunk in enumerate(candidates):
        combined_score = 0.6 * chunk.score + 0.4 * norm_bm25[i]
        combined.append((combined_score, chunk))

    combined.sort(key=lambda x: x[0], reverse=True)
    result = []
    for score, chunk in combined[:top_k]:
        chunk.score = round(score, 4)
        result.append(chunk)
    return result
