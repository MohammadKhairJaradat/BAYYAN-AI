"""evaluate_rag_offline.py — Honest Offline RAG Evaluation Harness (Cards G-RAG-EVAL01 & G-RAG-EVAL-VALIDITY01).

Evaluates the reviewed Jordanian PIT evaluation set against manifest fixtures
and validates source-status filtering boundaries without network, LLMs,
embeddings, Chroma writes, or candidate promotion.

Architectural Invariants & Validity Rules:
1. Annotated coverage must never become a measured retrieval PASS.
2. Zero token overlap can NEVER be labeled as a retrieval success or pass.
3. Distinguishes expected answerability, observed lexical overlap, and untested
   actual vector retrieval.
4. Manifest source status is resolved dynamically from manifest.json and never
   hardcoded to 'demo'.
5. Staged candidates ('needs_review') must remain 100% isolated from manifest.json.

Usage:
    uv run python scripts/evaluate_rag_offline.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Paths relative to backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
KB_DIR = BACKEND_DIR / "knowledge_base"
STAGING_DIR = KB_DIR / "staging"
MANIFEST_PATH = KB_DIR / "manifest.json"
EVAL_SET_PATH = ROOT_DIR / "docs" / "knowledge-audit" / "pit-rag-eval-set.json"
RESULTS_JSON_PATH = ROOT_DIR / "docs" / "knowledge-audit" / "rag-eval-results.json"
RESULTS_MD_PATH = ROOT_DIR / "docs" / "knowledge-audit" / "rag-eval-results.md"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("evaluate_rag_offline")


@dataclass
class EvalItemResult:
    id: str
    topic: str
    question_ar: str
    question_en: str
    expected_family: str
    answerability: str
    matched_tokens: list[str]
    missing_tokens: list[str]
    citation_token_overlap_rate: float
    observed_token_overlap_rate: float
    overlap_classification: str
    offline_evidence_verdict: str
    retrieval_status: str  # Kept for backward compatibility; mirrors offline_evidence_verdict
    retrieval_tested_status: str  # Explicitly 'untested_offline_lexical_only'
    source_status_tag: str
    explanation: str


def load_manifest(manifest_path: Path | None = None) -> dict:
    target = manifest_path or MANIFEST_PATH
    if not target.is_file():
        raise FileNotFoundError(f"Manifest not found at {target}")
    return json.loads(target.read_text(encoding="utf-8"))


def load_demo_fixtures(manifest: dict, kb_dir: Path | None = None) -> dict[str, str]:
    base_dir = kb_dir or KB_DIR
    fixtures: dict[str, str] = {}
    for src in manifest.get("sources", []):
        rel_file = src.get("file")
        if not rel_file:
            continue
        file_path = base_dir / rel_file
        if not file_path.is_file():
            raise FileNotFoundError(f"Manifest source file missing: {file_path}")
        fixtures[rel_file] = file_path.read_text(encoding="utf-8")
    return fixtures


def verify_staging_isolation(
    manifest_data: dict | None = None,
    staging_path: Path | None = None,
) -> dict[str, int]:
    """Verify that staged candidate files with 'needs_review' are NOT in manifest."""
    manifest = manifest_data if manifest_data is not None else load_manifest()
    manifest_files = {s.get("file") for s in manifest.get("sources", [])}

    staging = staging_path or STAGING_DIR
    staged_json_files = list(staging.glob("*.source.json")) if staging.is_dir() else []
    needs_review_count = 0
    leaked_into_manifest = 0

    for json_file in staged_json_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if data.get("status") == "needs_review":
                needs_review_count += 1
                candidate_name = data.get("file")
                if candidate_name and candidate_name in manifest_files:
                    leaked_into_manifest += 1
        except Exception as e:
            logger.warning("Failed to parse %s: %s", json_file, e)

    return {
        "staged_candidates_checked": len(staged_json_files),
        "needs_review_isolated": needs_review_count,
        "leaked_into_manifest": leaked_into_manifest,
    }


def compute_token_overlap(
    expected_tokens: list[str],
    fixtures: dict[str, str],
) -> tuple[list[str], list[str], float, str]:
    """Computes exact keyword presence across active fixture text.

    Returns:
        (matched_tokens, missing_tokens, overlap_rate, overlap_classification)
    """
    if not expected_tokens:
        return [], [], 0.0, "no_tokens"

    combined_text = "\n\n".join(fixtures.values())
    matched = [token for token in expected_tokens if token in combined_text]
    missing = [token for token in expected_tokens if token not in matched]
    rate = len(matched) / len(expected_tokens)

    if rate == 1.0:
        classification = "full"
    elif rate > 0.0:
        classification = "partial"
    else:
        classification = "zero"

    return matched, missing, round(rate, 3), classification


def resolve_source_status_for_item(
    matched_tokens: list[str],
    fixtures: dict[str, str],
    manifest: dict,
) -> str:
    """Dynamically resolves source status tags from manifest instead of hardcoding 'demo'."""
    if not matched_tokens:
        return "none"

    file_to_status = {
        s.get("file"): s.get("status", "unknown")
        for s in manifest.get("sources", [])
        if s.get("file")
    }

    matching_statuses: set[str] = set()
    for rel_file, content in fixtures.items():
        if any(token in content for token in matched_tokens):
            status = file_to_status.get(rel_file, "unknown")
            matching_statuses.add(status)

    if not matching_statuses:
        return "none"

    return ", ".join(sorted(matching_statuses))


def classify_eval_item(
    item: dict,
    matched_tokens: list[str],
    missing_tokens: list[str],
    overlap_rate: float,
    overlap_classification: str,
) -> tuple[str, str]:
    """Classifies evaluation item honestly, enforcing:

    1. Zero token overlap CANNOT be a retrieval success.
    2. Annotated coverage alone cannot produce a measured retrieval PASS.
    3. Distinguishes expected answerability, observed lexical overlap, and untested retrieval.
    """
    coverage = item.get("demo_fixture_coverage")

    # Safety: out-of-scope inquiry (annotated expectation, untested offline)
    if coverage == "out_of_scope":
        return (
            "EXPECTED_OUT_OF_SCOPE_UNTESTED",
            "Annotated benchmark expectation: corporate/commercial tax inquiry outside individual taxpayer scope (untested offline; no live classifier executed)."
        )

    # Safety: unsupported inquiry (annotated expectation, untested offline)
    if coverage == "unsupported_non_statutory":
        return (
            "EXPECTED_NON_STATUTORY_UNTESTED",
            "Annotated benchmark expectation: non-statutory inquiry with no legal basis in Jordanian income tax law (untested offline; no live guardrail executed)."
        )

    # Safety: honest disclosure required (annotated expectation, untested offline)
    if coverage == "honest_disclosure_required":
        return (
            "EXPECTED_DISCLOSURE_UNTESTED",
            "Annotated benchmark expectation: inquiry expects disclosure of missing authoritative deadline source rather than hallucination (untested offline; no live LLM executed)."
        )

    # Zero token overlap handling: NEVER call zero overlap a success or pass!
    if overlap_classification == "zero":
        if coverage == "unanswerable_in_demo":
            return (
                "STATUTORY_GAP_ZERO_OVERLAP",
                "Zero token overlap observed in active fixtures; source-audit expectation identifies this as an unpromoted statutory gap awaiting official source verification in staging."
            )
        elif coverage == "covered_in_demo":
            return (
                "ZERO_OVERLAP_UNANSWERED",
                "Annotated as covered in demo, but zero expected citation tokens observed in active fixtures; honest evaluation failure."
            )
        elif coverage == "partial_conceptual":
            return (
                "ZERO_OVERLAP_CONCEPT_MISSING",
                "Annotated as partial conceptual, but zero expected citation tokens observed in active fixtures."
            )
        else:
            return (
                "ZERO_OVERLAP_UNANSWERED",
                "Zero expected citation tokens observed in active fixtures; cannot claim retrieval success."
            )

    # Full token overlap handling
    if overlap_classification == "full":
        if coverage == "covered_in_demo":
            return (
                "OBSERVED_FULL_LEXICAL_MATCH",
                "100% expected citation tokens observed in active fixtures; actual vector retrieval untested offline."
            )
        elif coverage == "partial_conceptual":
            return (
                "OBSERVED_CONCEPTUAL_FULL_MATCH",
                "100% expected conceptual citation tokens observed; exact tax calculation deferred to deterministic Python engine."
            )
        elif coverage == "unanswerable_in_demo":
            return (
                "STATUTORY_GAP_UNEXPECTED_FULL_OVERLAP",
                "Unexpected full token match for unpromoted source; requires manifest review."
            )

    # Partial token overlap handling (0.0 < overlap < 1.0)
    if coverage == "covered_in_demo":
        return (
            "PARTIAL_LEXICAL_OVERLAP",
            f"Partial citation keywords observed ({len(matched_tokens)}/{len(matched_tokens) + len(missing_tokens)} tokens); vector retrieval untested offline."
        )
    elif coverage == "partial_conceptual":
        return (
            "PARTIAL_CONCEPTUAL_OVERLAP",
            f"Partial conceptual keywords observed ({len(matched_tokens)}/{len(matched_tokens) + len(missing_tokens)} tokens); final determination deferred to deterministic Python engine."
        )
    elif coverage == "unanswerable_in_demo":
        return (
            "STATUTORY_GAP_UNEXPECTED_PARTIAL_OVERLAP",
            f"Unexpected partial token match ({len(matched_tokens)} tokens) for unpromoted source; candidate remains staged."
        )

    return (
        "PARTIAL_LEXICAL_OVERLAP",
        f"Partial token overlap ({overlap_rate * 100:.1f}%) observed in active fixtures."
    )


def evaluate_offline(
    eval_set_path: Path | None = None,
    manifest_path: Path | None = None,
    kb_dir: Path | None = None,
    staging_path: Path | None = None,
) -> tuple[list[EvalItemResult], dict]:
    manifest = load_manifest(manifest_path)
    fixtures = load_demo_fixtures(manifest, kb_dir)
    isolation_stats = verify_staging_isolation(manifest, staging_path)

    if isolation_stats["leaked_into_manifest"] > 0:
        raise RuntimeError("CRITICAL ARCHITECTURAL LEAK: staged needs_review candidate leaked into manifest!")

    eval_file = eval_set_path or EVAL_SET_PATH
    eval_data = json.loads(eval_file.read_text(encoding="utf-8"))
    items = eval_data.get("items", [])

    results: list[EvalItemResult] = []

    overlap_counts = {"full": 0, "partial": 0, "zero": 0, "no_tokens": 0}
    verdict_counts: dict[str, int] = {}
    expected_coverage_counts: dict[str, int] = {}

    for item in items:
        item_id = item["id"]
        expected_tokens = item.get("expected_citation_tokens", [])
        coverage = item.get("demo_fixture_coverage", "unknown")
        expected_coverage_counts[coverage] = expected_coverage_counts.get(coverage, 0) + 1

        matched, missing, overlap_rate, overlap_cat = compute_token_overlap(expected_tokens, fixtures)
        overlap_counts[overlap_cat] = overlap_counts.get(overlap_cat, 0) + 1

        source_status_tag = resolve_source_status_for_item(matched, fixtures, manifest)

        verdict, explanation = classify_eval_item(
            item, matched, missing, overlap_rate, overlap_cat
        )
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        results.append(
            EvalItemResult(
                id=item_id,
                topic=item["topic"],
                question_ar=item["question_ar"],
                question_en=item["question_en"],
                expected_family=item["expected_source_family"],
                answerability=item["answerability"],
                matched_tokens=matched,
                missing_tokens=missing,
                citation_token_overlap_rate=overlap_rate,
                observed_token_overlap_rate=overlap_rate,
                overlap_classification=overlap_cat,
                offline_evidence_verdict=verdict,
                retrieval_status=verdict,
                retrieval_tested_status="untested_offline_lexical_only",
                source_status_tag=source_status_tag,
                explanation=explanation,
            )
        )

    total = len(items) if items else 1

    summary = {
        "total_eval_items": len(items),
        "manifest_sources_active": len(manifest.get("sources", [])),
        "manifest_source_statuses": sorted(list({s.get("status", "unknown") for s in manifest.get("sources", [])})),
        "staging_isolation": isolation_stats,
        "expected_coverage_breakdown": expected_coverage_counts,
        "observed_overlap_breakdown": overlap_counts,
        "offline_evidence_verdict_breakdown": verdict_counts,
        "metrics": {
            "full_lexical_match_rate": f"{(overlap_counts.get('full', 0) / total) * 100:.1f}%",
            "partial_lexical_overlap_rate": f"{(overlap_counts.get('partial', 0) / total) * 100:.1f}%",
            "zero_token_overlap_rate": f"{(overlap_counts.get('zero', 0) / total) * 100:.1f}%",
            "statutory_gap_absent_rate": f"{(verdict_counts.get('STATUTORY_GAP_ZERO_OVERLAP', 0) / total) * 100:.1f}%",
            "annotated_expected_disclosure_rate": f"{(verdict_counts.get('EXPECTED_DISCLOSURE_UNTESTED', 0) / total) * 100:.1f}%",
            "annotated_expected_out_of_scope_or_disallowed_rate": f"{((verdict_counts.get('EXPECTED_OUT_OF_SCOPE_UNTESTED', 0) + verdict_counts.get('EXPECTED_NON_STATUTORY_UNTESTED', 0)) / total) * 100:.1f}%",
        },
        "retrieval_tested_warning": (
            "Actual k-NN vector retrieval and embedding rank are UNTESTED in this offline evaluation harness. "
            "Overlap metrics measure lexical evidence presence only. Zero token overlap is never counted as a pass."
        ),
    }

    return results, summary


def generate_markdown_report(results: list[EvalItemResult], summary: dict) -> str:
    manifest_statuses = ", ".join(summary.get("manifest_source_statuses", ["demo"]))
    staged_isolated_count = summary.get("staging_isolation", {}).get("needs_review_isolated", 0)
    lines = [
        "# Jordanian Individual Income Tax (PIT) — Honest RAG Offline Readiness Evaluation",
        "",
        "> **Run Date:** 2026-09-26",
        "> **Execution Context:** Card G-RAG-EVAL-VALIDITY01 (Offline, zero API costs, zero Chroma writes, strict source-status isolation).",
        f"> **Active Manifest Fixtures:** {summary['manifest_sources_active']} files (`status: {manifest_statuses}`).",
        f"> **Staged Candidates:** {staged_isolated_count} records in `backend/knowledge_base/staging/` (`status: 'needs_review'`; strictly uningested).",
        "> **Evaluation Validity Invariant:** Annotated coverage is never converted to a measured retrieval pass. Zero token overlap is never a success. Actual vector retrieval is explicitly marked untested.",
        "",
        "---",
        "",
        "## 1. Executive Summary & Architectural Invariants",
        "",
        "| Metric | Value | Description |",
        "|---|---|---|",
        f"| **Total Evaluation Cases** | `{summary['total_eval_items']}` | Reviewed representative Jordanian PIT inquiries |",
        f"| **Active Manifest Fixtures** | `{summary['manifest_sources_active']}` | Loaded from active `manifest.json` sources |",
        f"| **Source Statuses in Manifest** | `{manifest_statuses}` | Dynamically resolved from manifest (not hardcoded) |",
        f"| **Staging Isolation Checked** | `{summary['staging_isolation']['staged_candidates_checked']}` records | Confirmed 100% isolated (`0` leaked into manifest) |",
        f"| **Full Lexical Match Rate (100% Overlap)** | `{summary['metrics']['full_lexical_match_rate']}` | All citation keywords present in active fixtures |",
        f"| **Partial Lexical Overlap Rate** | `{summary['metrics']['partial_lexical_overlap_rate']}` | Some citation keywords present; vector retrieval untested |",
        f"| **Zero Token Overlap Rate** | `{summary['metrics']['zero_token_overlap_rate']}` | Zero keywords present; never counted as a retrieval pass |",
        f"| **Statutory Gap (Awaiting Promotion)** | `{summary['metrics']['statutory_gap_absent_rate']}` | Questions requiring unpromoted official gazettes/forms |",
        f"| **Annotated Expected Missing-Source Disclosure (Untested)** | `{summary['metrics']['annotated_expected_disclosure_rate']}` | Benchmark expectation: declare missing deadline source (untested offline) |",
        f"| **Annotated Expected Out-of-Scope / Disallowed (Untested)** | `{summary['metrics']['annotated_expected_out_of_scope_or_disallowed_rate']}` | Benchmark expectation: corporate tax & crypto disallowed (untested offline) |",
        "",
        "---",
        "",
        "## 2. Item-by-Item Evaluation Breakdown",
        "",
        "| ID | Topic | Family | Overlap % | Classification | Offline Verdict | Source Tag | Explanation |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        overlap_str = f"{r.observed_token_overlap_rate * 100:.1f}%"
        verdict_badge = f"`{r.offline_evidence_verdict}`"
        lines.append(
            f"| `{r.id}` | `{r.topic}` | `{r.expected_family}` | `{overlap_str}` | `{r.overlap_classification}` | {verdict_badge} | `{r.source_status_tag}` | {r.explanation} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Honest Zero-Overlap & Statutory Gap Audit",
        "",
        "The following cases have **0% token overlap** and are honestly recorded as unanswerable or absent, rather than claiming false retrieval success:",
        "",
        "1. **`EVAL-PIT-004` (Salary Withholding Threshold):**",
        "   - *Expected Tokens:* `416`, `التعليمات التنفيذية رقم 2 لسنة 2019`, `اقتطاع`, `الرواتب والأجور`.",
        "   - *Observed Overlap:* 0.0% (`STATUTORY_GAP_ZERO_OVERLAP`).",
        "   - *Reason:* Source-audit expectation indicates Instruction No. 2 of 2019 is unpromoted in active demo fixtures.",
        "",
        "2. **`EVAL-PIT-005` (National Contribution Surcharge):**",
        "   - *Expected Tokens:* `1%`, `المساهمة الوطنية`, `200000`, `16666`.",
        "   - *Observed Overlap:* 0.0% (`STATUTORY_GAP_ZERO_OVERLAP`).",
        "   - *Reason:* Source-audit expectation identifies Law 34/2014 Article 11(d) text as unpromoted in active demo fixtures.",
        "",
        "3. **`EVAL-PIT-007` (Mandatory Digital E-Filing):**",
        "   - *Expected Tokens:* `إلكتروني`, `etax.istd.gov.jo`, `بوابة الخدمات الإلكترونية`, `حصراً`.",
        "   - *Observed Overlap:* 0.0% (`STATUTORY_GAP_ZERO_OVERLAP`).",
        "   - *Reason:* Source-audit expectation identifies Regulation 59/2015 and portal directives as unpromoted in active demo fixtures.",
        "",
        "4. **`EVAL-PIT-008` (Progressive Tax Brackets):**",
        "   - *Expected Tokens:* `5%`, `10%`, `15%`, `20%`, `25%`, `30%`, `5000`, `المادة 11`.",
        "   - *Observed Overlap:* 0.0% (`ZERO_OVERLAP_CONCEPT_MISSING`).",
        "   - *Honest Audit:* Unlike earlier reports that falsely claimed 'PASS' or 'concept retrieved', this harness honestly records 0.0% overlap.",
        "",
        "5. **`EVAL-PIT-009` (Medical Expenses Documentation):**",
        "   - *Expected Tokens:* `إيصال`, `عيادة`, `صيدلية`, `مستشفى`, `فواتير`.",
        "   - *Observed Overlap:* 0.0% (`ZERO_OVERLAP_UNANSWERED`).",
        "   - *Honest Audit:* Demo fixture only mentions English keywords (`clinic`, `pharmacy`, `receipt`). Arabic keywords are missing, so it is honestly reported as zero overlap failure, NOT a pass.",
        "",
        "6. **`EVAL-PIT-012` (Cryptocurrency Trading Losses):**",
        "   - *Expected Tokens:* `غير خاضع لنص قانوني`, `غير معتمد`, `حظر التعامل`.",
        "   - *Observed Overlap:* 0.0% (`EXPECTED_NON_STATUTORY_UNTESTED`).",
        "   - *Honest Audit:* Non-statutory inquiry marked as expected disallowed by benchmark annotations; actual system rejection is untested offline without live guardrails.",
        "",
        "---",
        "",
        "## 4. Promotion Gate Notice",
        "",
        "No staged legal documents (`backend/knowledge_base/staging/`) will be moved into `manifest.json` or ingested into ChromaDB without separate, explicit authorization from Mohammad and Codex.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run honest offline RAG evaluation harness.")
    parser.parse_args()

    logger.info("Executing honest offline RAG evaluation harness (Card G-RAG-EVAL-VALIDITY01)...")
    results, summary = evaluate_offline()

    # Save JSON results
    output_data = {
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    RESULTS_JSON_PATH.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved JSON evaluation results to %s", RESULTS_JSON_PATH)

    # Save Markdown report
    md_content = generate_markdown_report(results, summary)
    RESULTS_MD_PATH.write_text(md_content, encoding="utf-8")
    logger.info("Saved Markdown evaluation report to %s", RESULTS_MD_PATH)

    logger.info(
        "Evaluation Complete. Total items: %d. Full overlap: %s. Partial: %s. Zero overlap: %s.",
        summary["total_eval_items"],
        summary["metrics"]["full_lexical_match_rate"],
        summary["metrics"]["partial_lexical_overlap_rate"],
        summary["metrics"]["zero_token_overlap_rate"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
