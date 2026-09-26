"""Validate local candidate source records without indexing or provider calls.

Run from backend/: uv run python scripts/validate_knowledge_candidates.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

STAGING = Path(__file__).resolve().parents[1] / "knowledge_base" / "staging"
STATUSES = {"needs_review", "reviewed", "rejected"}


def _date(value: object, field: str) -> None:
    if value is not None:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be an ISO date or null")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO date") from exc


def validate_record(path: Path, staging: Path = STAGING) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("source record must be an object")
    if record.get("status") not in STATUSES:
        raise ValueError("invalid review status")
    for field in ("title", "publisher", "source_url", "rights_note", "sha256", "file"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ValueError(f"missing {field}")
    parsed = urlparse(record["source_url"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source_url must be an HTTPS URL")
    name = record["file"]
    if Path(name).name != name:
        raise ValueError("file must be a single filename inside staging")
    source = staging / name
    if not source.is_file():
        raise ValueError(f"candidate file missing: {name}")
    content = source.read_bytes()
    if hashlib.sha256(content).hexdigest() != record["sha256"].lower():
        raise ValueError(f"SHA-256 mismatch: {name}")
    if record.get("bytes") != len(content):
        raise ValueError(f"byte length mismatch: {name}")
    for field in ("retrieved_on", "published_on", "effective_from", "effective_to", "reviewed_on"):
        _date(record.get(field), field)

    if record["status"] == "reviewed":
        for field in ("source_issue", "rights_basis", "reviewed_by"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"reviewed source missing {field}")
        for field in ("effective_from", "reviewed_on"):
            if not record.get(field):
                raise ValueError(f"reviewed source missing {field}")
        year = record.get("tax_year_start")
        if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2100:
            raise ValueError("reviewed source needs tax_year_start")
        end = record.get("tax_year_end")
        if end is not None and (not isinstance(end, int) or end < year):
            raise ValueError("tax_year_end must be null or no earlier than tax_year_start")
        if not parsed.hostname.endswith(".gov.jo"):
            raise ValueError("reviewed legal source must use a Jordanian government URL")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate unindexed knowledge-base candidates")
    parser.add_argument("--dir", type=Path, default=STAGING)
    args = parser.parse_args()
    records = sorted(args.dir.glob("*.source.json"))
    if not records:
        raise SystemExit("No source records found")
    for record_path in records:
        record = validate_record(record_path, args.dir)
        print(f"ok {record['status']}: {record_path.name}")
    print(f"Validated {len(records)} candidate record(s); no indexing performed")


if __name__ == "__main__":
    main()
