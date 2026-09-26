"""
app.rag — Retrieval-augmented generation utilities for the tax law knowledge base.
"""

from __future__ import annotations

from .chunker import LegalChunk, SourceType, chunk_guidance_document, chunk_legal_document
from .embedder import Embedder
from .retriever import build_context_block, retrieve, retrieve_with_context
from .vector_store import RetrievedChunk, VectorStore

__all__ = [
    "LegalChunk",
    "SourceType",
    "chunk_legal_document",
    "chunk_guidance_document",
    "Embedder",
    "VectorStore",
    "RetrievedChunk",
    "retrieve",
    "retrieve_with_context",
    "build_context_block",
]
