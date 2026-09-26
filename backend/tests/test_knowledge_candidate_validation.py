"""Offline source-record gates for the not-yet-indexed legal corpus."""

import hashlib
import json

import pytest

from scripts.validate_knowledge_candidates import validate_record


def _record(tmp_path):
    source = tmp_path / "law.pdf"
    source.write_bytes(b"%PDF synthetic candidate")
    record = {
        "status": "needs_review",
        "title": "Test source",
        "publisher": "Jordan Income and Sales Tax Department",
        "source_url": "https://istd.gov.jo/test.pdf",
        "rights_note": "Rights pending review",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "file": source.name,
        "bytes": source.stat().st_size,
        "retrieved_on": "2026-09-25",
    }
    path = tmp_path / "law.source.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return source, path, record


def test_candidate_hash_and_reviewed_gate(tmp_path):
    source, path, record = _record(tmp_path)
    assert validate_record(path, tmp_path)["status"] == "needs_review"

    source.write_bytes(b"%PDF changed content")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_record(path, tmp_path)

    source.write_bytes(b"%PDF synthetic candidate")
    record["status"] = "reviewed"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="reviewed source missing source_issue"):
        validate_record(path, tmp_path)

    record.update({
        "source_issue": "Gazette 5547",
        "rights_basis": "Reviewed for internal use",
        "reviewed_by": "human reviewer",
        "reviewed_on": "2026-09-25",
        "effective_from": "2019-01-01",
        "tax_year_start": 2019,
        "tax_year_end": None,
    })
    path.write_text(json.dumps(record), encoding="utf-8")
    assert validate_record(path, tmp_path)["status"] == "reviewed"
