"""End-to-end pipeline test — run on corp machine, paste output back to Claude.

Prerequisites:
    python scripts/run_full_setup.py   (creates tables, loads embeddings)

Usage:
    python -m scripts.test_pipeline_e2e
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback

# Suppress pipeline INFO noise — only show warnings/errors
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

# ── Test Cases ───────────────────────────────────────────────────────
# Each: (query, expected_explore, description)

TEST_CASES = [
    # The 6 demo queries
    (
        "What is the total billed business for the OPEN segment?",
        "finance_cardmember_360",
        "Base-view measure (custins) + filter on bus_seg",
    ),
    (
        "How many attrited customers do we have by generation?",
        "finance_cardmember_360",
        "Custins measure + cmdl dimension + filter on basic_cust_noa",
    ),
    (
        "What is our attrition rate for Q4 2025?",
        "finance_cardmember_360",
        "Custins rate measure + time range",
    ),
    (
        "What is the highest billed business by merchant category?",
        "finance_merchant_profitability",
        "Merchant base-view measure + merchant dimension",
    ),
    (
        "Show me the top 5 travel verticals by gross sales and booking count",
        "finance_travel_sales",
        "Travel base-view measures + travel dimension",
    ),
    (
        "How many Millennial customers have Apple Pay enrolled and are active?",
        "finance_cardmember_360",
        "Custins/cmdl measures + generation filter + digital filter",
    ),

    # Stress tests — edge cases from the mathematical audit
    (
        "Show me customer count by card type",
        "finance_cardmember_360",
        "EDGE: Both entities from shared views (custins + cmdl). Tests base_view_bonus.",
    ),
    (
        "What is the revolve index by generation?",
        "finance_customer_risk",
        "Risk base-view measure + shared dimension. Tests base_view_bonus on risk.",
    ),
    (
        "How many new cards were issued by campaign last quarter?",
        "finance_card_issuance",
        "Issuance-specific measure + dimension. Should be unambiguous.",
    ),
    (
        "What is the cancellation rate by travel vertical?",
        "finance_travel_sales",
        "Travel-specific measure + dimension. Should be unambiguous.",
    ),
    (
        "Show me dining spend by generation for Millennial customers",
        "finance_merchant_profitability",
        "Merchant measure + shared dim + filter. Tests filter_penalty.",
    ),
    (
        "Total billed business by generation",
        "finance_cardmember_360",
        "EDGE: 'billed business' in custins (base) AND merchant (base). Tests P1 weighting.",
    ),
]


def run_tests():
    """Run all test cases and collect results."""

    print("=" * 90)
    print("CORTEX PIPELINE E2E TEST")
    print("=" * 90)

    # ── Quick DB sanity check (no SafeChain, just table existence) ───
    print("\n[1/4] DB SANITY CHECK")
    print("-" * 40)
    try:
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            emb_count = conn.execute(text("SELECT count(*) FROM field_embeddings")).fetchone()[0]
            efi_count = conn.execute(text("SELECT count(*) FROM explore_field_index")).fetchone()[0]
        print(f"  field_embeddings:   {emb_count} records")
        print(f"  explore_field_index: {efi_count} rows")
        if emb_count == 0:
            print("\n  field_embeddings is EMPTY. Run: python scripts/run_full_setup.py")
            sys.exit(1)
        if efi_count == 0:
            print("\n  explore_field_index is EMPTY. Run: python scripts/run_full_setup.py")
            sys.exit(1)
    except Exception as e:
        print(f"  DB check failed: {e}")
        print("  Run: python scripts/run_full_setup.py")
        sys.exit(1)

    # ── Embedding data shape ─────────────────────────────────────────
    print("\n[2/4] EMBEDDING DATA SHAPE")
    print("-" * 40)
    try:
        with engine.connect() as conn:
            # explore_name format check
            comma_row = conn.execute(text(
                "SELECT explore_name FROM field_embeddings WHERE explore_name LIKE '%,%' LIMIT 1"
            )).fetchone()
            fmt = f"COMMA-SEPARATED (e.g., {comma_row[0][:80]})" if comma_row else "SINGLE VALUE"
            print(f"  explore_name format: {fmt}")

            # Count per explore
            rows = conn.execute(text(
                "SELECT explore_name, count(*) as cnt "
                "FROM field_embeddings GROUP BY explore_name ORDER BY cnt DESC"
            )).fetchall()
            print(f"\n  Embeddings per explore_name:")
            for row in rows:
                print(f"    {row[0]:<60} {row[1]:>4} records")
    except Exception as e:
        print(f"  Error: {e}")

    # ── Full pipeline runs ───────────────────────────────────────────
    print(f"\n\n[3/4] FULL PIPELINE RUNS ({len(TEST_CASES)} queries)")
    print("=" * 90)

    from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore

    results = []

    for i, (query, expected, desc) in enumerate(TEST_CASES, 1):
        print(f"\n{'─' * 90}")
        print(f"TEST {i}/{len(TEST_CASES)}: {desc}")
        print(f"  Query:    {query}")
        print(f"  Expected: {expected}")

        try:
            t0 = time.time()
            pipeline_result = retrieve_with_graph_validation(query, top_k=5)
            elapsed = time.time() - t0

            top_output = get_top_explore(pipeline_result)

            actual = top_output.get("top_explore_name", "NONE")
            passed = actual == expected
            action = top_output.get("action", "?")
            confidence = top_output.get("confidence", 0.0)

            status = "PASS" if passed else "FAIL"
            print(f"  Result:   {actual}")
            print(f"  Status:   {status}  |  action={action}  |  confidence={confidence:.4f}  |  {elapsed:.1f}s")

            # Entity details
            if pipeline_result.entities:
                print(f"\n  Entities extracted ({len(pipeline_result.entities)}):")
                for ent in pipeline_result.entities:
                    etype = ent.get("type", "?")
                    ename = ent.get("name", "?")
                    if etype in ("measure", "dimension"):
                        candidates = ent.get("candidates", [])
                        top3 = candidates[:3]
                        sims = [f"{c.get('explore','?')[:30]}:{c.get('similarity',0):.4f}" for c in top3]
                        print(f"    [{etype:>9}] {ename:<30} top3: {', '.join(sims)}")
                    elif etype == "filter":
                        print(f"    [   filter] {ename:<30} op={ent.get('operator','?')} values={ent.get('values',[])}")
                    elif etype == "time_range":
                        print(f"    [     time] {ent.get('values', [])}")

            # Scored explores
            if pipeline_result.explores:
                print(f"\n  Explore scores ({len(pipeline_result.explores)} scored):")
                for j, exp in enumerate(pipeline_result.explores[:5]):
                    marker = " <── WINNER" if j == 0 else ""
                    marker += " NEAR-MISS" if exp.is_near_miss else ""
                    base = f"(base: {exp.base_view_name})" if exp.base_view_name else "(no base view)"
                    print(
                        f"    #{j+1} {exp.name:<40} "
                        f"score={exp.score:.4f}  raw={exp.raw_score:.4f}  "
                        f"cov={exp.coverage:.2f}  conf={exp.confidence:.4f}  "
                        f"{base}{marker}"
                    )

                if len(pipeline_result.explores) >= 2:
                    top_s = pipeline_result.explores[0].score
                    run_s = pipeline_result.explores[1].score
                    ratio = run_s / top_s if top_s > 0 else 0
                    sep = top_s / run_s if run_s > 0 else float("inf")
                    print(f"\n  Separation: {sep:.1f}x  |  Near-miss ratio: {ratio:.4f}  (threshold: 0.92)")

            # Filters
            if pipeline_result.filters:
                rf = pipeline_result.filters
                if rf.resolved_filters:
                    print(f"\n  Resolved filters ({len(rf.resolved_filters)}):")
                    for f in rf.resolved_filters:
                        neg = " [NEG]" if f.is_negated else ""
                        print(f"    {f.field_name}  {f.operator}  '{f.value}'{neg}  (pass {f.resolution_pass}, conf={f.confidence:.0%})")
                if rf.mandatory_filters:
                    print(f"  Mandatory filters: {len(rf.mandatory_filters)}")
                if rf.unresolved:
                    print(f"  UNRESOLVED filters: {rf.unresolved}")

            if pipeline_result.clarify_reason:
                print(f"\n  Clarify reason: {pipeline_result.clarify_reason}")

            results.append({
                "query": query,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "confidence": confidence,
                "action": action,
                "elapsed_s": round(elapsed, 1),
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()
            results.append({
                "query": query,
                "expected": expected,
                "actual": "ERROR",
                "passed": False,
                "confidence": 0.0,
                "action": "error",
                "elapsed_s": 0,
                "error": str(e),
            })

    # ── Summary ──────────────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("[4/4] SUMMARY")
    print("=" * 90)

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    accuracy = passed_count / total * 100 if total else 0

    print(f"\n  {passed_count}/{total} passed ({accuracy:.0f}%)\n")
    print(f"  {'#':<4} {'Pass':<6} {'Conf':<8} {'Time':<7} {'Expected':<40} {'Actual':<40}")
    print(f"  {'─'*4} {'─'*5} {'─'*7} {'─'*6} {'─'*39} {'─'*39}")

    for i, r in enumerate(results, 1):
        status = "OK" if r["passed"] else "FAIL"
        print(
            f"  {i:<4} {status:<6} {r['confidence']:<8.4f} {r['elapsed_s']:<7.1f} "
            f"{r['expected']:<40} {r['actual']:<40}"
        )

    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\n  FAILURES ({len(failures)}):")
        for r in failures:
            print(f"    - {r['query']}")
            print(f"      Expected: {r['expected']}, Got: {r['actual']}")
            if r.get("error"):
                print(f"      Error: {r['error']}")

    print("\n" + "=" * 90)
    print("PASTE EVERYTHING ABOVE BACK TO CLAUDE FOR ANALYSIS")
    print("=" * 90)


if __name__ == "__main__":
    run_tests()
