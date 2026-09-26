"""test_rag_eval_offline.py — Tests for honest offline RAG evaluation harness (Card G-RAG-EVAL-VALIDITY01).

Verifies:
1. Synthetic full lexical overlap (100%) produces OBSERVED_FULL_LEXICAL_MATCH.
2. Synthetic partial lexical overlap produces PARTIAL_LEXICAL_OVERLAP and identifies missing tokens.
3. Synthetic zero lexical overlap (0%) can NEVER produce a PASS or success verdict.
4. Staging isolation detects candidate leaks into manifest.
5. Workspace staging isolation is 100% clean (0 leaked staged candidates).
6. Manifest source statuses are resolved dynamically and not hardcoded to 'demo'.
7. Live repo evaluation produces truthful reports distinguishing expected vs observed.
"""

from pathlib import Path
import json
import pytest

from scripts.evaluate_rag_offline import (
    compute_token_overlap,
    classify_eval_item,
    resolve_source_status_for_item,
    verify_staging_isolation,
    evaluate_offline,
    load_manifest,
)


def test_full_overlap_synthetic_fixture():
    """Verify 100% keyword match produces OBSERVED_FULL_LEXICAL_MATCH."""
    expected_tokens = ["إعفاء شخصي", "المادة 9", "9000"]
    synthetic_fixtures = {
        "law/test_fixture.md": "المادة 9 تنص على إعفاء شخصي مقداره 9000 دينار للمكلف المقيم."
    }

    matched, missing, rate, cat = compute_token_overlap(expected_tokens, synthetic_fixtures)
    assert rate == 1.0
    assert cat == "full"
    assert set(matched) == set(expected_tokens)
    assert missing == []

    item = {"demo_fixture_coverage": "covered_in_demo"}
    verdict, explanation = classify_eval_item(item, matched, missing, rate, cat)
    assert verdict == "OBSERVED_FULL_LEXICAL_MATCH"
    assert "vector retrieval untested" in explanation.lower()


def test_partial_overlap_synthetic_fixture():
    """Verify partial keyword match produces PARTIAL_LEXICAL_OVERLAP and reports missing tokens."""
    expected_tokens = ["التعليم", "العلاج", "المرابحة", "فواتير"]
    synthetic_fixtures = {
        "guidance/test_fixture.md": "تشمل النفقات المقبولة نفقات التعليم والعلاج بموجب سند رسمي."
    }

    matched, missing, rate, cat = compute_token_overlap(expected_tokens, synthetic_fixtures)
    assert rate == 0.5
    assert cat == "partial"
    assert set(matched) == {"التعليم", "العلاج"}
    assert set(missing) == {"المرابحة", "فواتير"}

    item = {"demo_fixture_coverage": "covered_in_demo"}
    verdict, explanation = classify_eval_item(item, matched, missing, rate, cat)
    assert verdict == "PARTIAL_LEXICAL_OVERLAP"
    assert "2/4" in explanation


def test_zero_overlap_can_never_be_called_success_or_pass():
    """CRITICAL INVARIANT: Zero token overlap cannot be called a retrieval success or pass."""
    expected_tokens = ["5%", "10%", "15%", "20%", "25%", "30%", "5000", "المادة 11"]
    synthetic_fixtures = {
        "law/empty_fixture.md": "هذا ملف تجريبي عام لا يتضمن أرقام الشرائح التصاعدية."
    }

    matched, missing, rate, cat = compute_token_overlap(expected_tokens, synthetic_fixtures)
    assert rate == 0.0
    assert cat == "zero"
    assert matched == []
    assert len(missing) == len(expected_tokens)

    # Even if the item annotation says 'covered_in_demo', zero overlap MUST fail honestly
    item = {"demo_fixture_coverage": "covered_in_demo"}
    verdict, explanation = classify_eval_item(item, matched, missing, rate, cat)

    # Must be an honest failure, never a PASS
    assert verdict == "ZERO_OVERLAP_UNANSWERED"
    assert "PASS" not in verdict
    assert "SUCCESS" not in verdict
    assert "honest evaluation failure" in explanation.lower()


def test_staging_isolation_detects_leak(tmp_path: Path):
    """Verify that verify_staging_isolation catches a candidate leaked into manifest."""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    # Create a candidate record marked needs_review
    candidate_meta = {
        "file": "candidate_law.pdf",
        "status": "needs_review",
        "title": "Unreviewed Law Candidate",
    }
    (staging_dir / "candidate_law.source.json").write_text(
        json.dumps(candidate_meta), encoding="utf-8"
    )

    # Synthetic manifest where candidate_law.pdf leaked into sources
    leaked_manifest = {
        "schema_version": 1,
        "sources": [
            {"file": "law/demo.md", "status": "demo"},
            {"file": "candidate_law.pdf", "status": "needs_review"},  # Leaked!
        ],
    }

    stats = verify_staging_isolation(manifest_data=leaked_manifest, staging_path=staging_dir)
    assert stats["staged_candidates_checked"] == 1
    assert stats["needs_review_isolated"] == 1
    assert stats["leaked_into_manifest"] == 1


def test_workspace_staging_isolation_is_clean():
    """Verify workspace staging isolation: exactly 0 staged candidates leaked into manifest.json."""
    stats = verify_staging_isolation()
    if stats["staged_candidates_checked"] == 0:
        pytest.skip("Staged candidate documents are gitignored and not present in clean checkout")
    assert stats["staged_candidates_checked"] >= 2
    assert stats["needs_review_isolated"] >= 2
    assert stats["leaked_into_manifest"] == 0


def test_dynamic_source_status_not_hardcoded_demo():
    """Verify resolve_source_status_for_item dynamically inspects manifest source status."""
    matched_tokens = ["ضريبة الدخل", "المادة 1"]
    fixtures = {
        "law/official_gazette_55.md": "المادة 1 من قانون ضريبة الدخل."
    }
    synthetic_manifest = {
        "schema_version": 1,
        "sources": [
            {
                "file": "law/official_gazette_55.md",
                "status": "official_gazette",
            }
        ],
    }

    status_tag = resolve_source_status_for_item(matched_tokens, fixtures, synthetic_manifest)
    assert status_tag == "official_gazette"
    assert status_tag != "demo"


def test_evaluate_offline_live_suite():
    """Verify evaluate_offline runs cleanly on active workspace, enforcing validity invariants."""
    from scripts.evaluate_rag_offline import EVAL_SET_PATH
    if not EVAL_SET_PATH.is_file():
        pytest.skip("Offline evaluation benchmark set not included in repository checkout")
    results, summary = evaluate_offline()

    assert summary["total_eval_items"] == 12
    assert summary["staging_isolation"]["leaked_into_manifest"] == 0
    assert summary["manifest_sources_active"] >= 2

    # Check each result satisfies honesty invariants
    for r in results:
        assert r.retrieval_tested_status == "untested_offline_lexical_only"
        assert r.citation_token_overlap_rate == r.observed_token_overlap_rate

        # If overlap is 0.0, verdict can NEVER be a PASS or SUCCESS
        if r.observed_token_overlap_rate == 0.0:
            assert "PASS" not in r.offline_evidence_verdict
            assert "SUCCESS" not in r.offline_evidence_verdict
            assert r.overlap_classification == "zero"

        # If overlap is full (1.0), verdict must acknowledge untested vector retrieval
        if r.overlap_classification == "full":
            assert r.observed_token_overlap_rate == 1.0
            assert "vector retrieval untested" in r.explanation.lower()


def test_unmeasured_verdicts_are_labeled_untested_expectations():
    """Verify out-of-scope, non-statutory, and disclosure cases do NOT claim live system execution."""
    cases = [
        ("out_of_scope", "EXPECTED_OUT_OF_SCOPE_UNTESTED"),
        ("unsupported_non_statutory", "EXPECTED_NON_STATUTORY_UNTESTED"),
        ("honest_disclosure_required", "EXPECTED_DISCLOSURE_UNTESTED"),
    ]
    for coverage, expected_verdict in cases:
        item = {"demo_fixture_coverage": coverage}
        verdict, explanation = classify_eval_item(item, [], ["token"], 0.0, "zero")
        assert verdict == expected_verdict
        assert "UNTESTED" in verdict
        assert "PASS" not in verdict
        assert "SUCCESS" not in verdict
        assert "REJECTED" not in verdict  # Must not claim actual rejection occurred
        assert "untested" in explanation.lower()
        assert "expectation" in explanation.lower()


def test_statutory_gap_phrased_as_source_audit_expectation():
    """Verify zero overlap on unanswerable demo items is phrased as a source-audit expectation."""
    item = {"demo_fixture_coverage": "unanswerable_in_demo"}
    verdict, explanation = classify_eval_item(item, [], ["token"], 0.0, "zero")
    assert verdict == "STATUTORY_GAP_ZERO_OVERLAP"
    assert "source-audit expectation" in explanation.lower()
    assert "PASS" not in verdict
    assert "SUCCESS" not in verdict


def test_markdown_report_dynamically_derives_staged_count():
    """Verify generate_markdown_report derives staged candidate count from staging_isolation stats."""
    from scripts.evaluate_rag_offline import generate_markdown_report

    synthetic_summary = {
        "total_eval_items": 1,
        "manifest_sources_active": 3,
        "manifest_source_statuses": ["demo"],
        "staging_isolation": {
            "staged_candidates_checked": 7,
            "needs_review_isolated": 7,
            "leaked_into_manifest": 0,
        },
        "metrics": {
            "full_lexical_match_rate": "0.0%",
            "partial_lexical_overlap_rate": "0.0%",
            "zero_token_overlap_rate": "100.0%",
            "statutory_gap_absent_rate": "0.0%",
            "annotated_expected_disclosure_rate": "0.0%",
            "annotated_expected_out_of_scope_or_disallowed_rate": "0.0%",
        },
    }
    report = generate_markdown_report([], synthetic_summary)
    assert "> **Staged Candidates:** 7 records in `backend/knowledge_base/staging/`" in report
    assert "2 records" not in report
