from app.rag.vector_store import RetrievedChunk, _bm25_rerank


def _retrieved(text: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=text[:12],
        text=text,
        score=score,
        metadata={"source_file": "demo.md"},
    )


def test_bm25_rerank_handles_numpy_score_arrays():
    chunks = [
        _retrieved("school fees and education deductions"),
        _retrieved("filing deadline and tax return"),
        _retrieved("personal exemption and family exemption"),
    ]

    result = _bm25_rerank("school fees deduction", chunks, top_k=2)

    assert len(result) == 2
    assert result[0].text == "school fees and education deductions"
