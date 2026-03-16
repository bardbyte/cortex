"""End-to-end pipeline test — run on corp machine, paste output back to Claude.

Usage:
    python -m scripts.test_pipeline_e2e

Requires: pgvector + AGE Docker stack running, SafeChain/CIBIS access, .env configured.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from dataclasses import asdict

# ── Setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,  # Suppress pipeline INFO noise
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

    # Stress tests — edge cases from the audit
    (
        "Show me customer count by card type",
        "finance_cardmember_360",
        "EDGE: Both entities from shared views (custins + cmdl). Tests base_view_bonus discrimination.",
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
        "EDGE: 'billed business' exists in custins (base) AND merchant (base). Tests P1 measure weighting.",
    ),
]


def run_tests():
    """Run all test cases and collect results."""

    print("=" * 90)
    print("CORTEX PIPELINE E2E TEST")
    print("=" * 90)

    # ── Step 0: Connectivity checks ──────────────────────────────────
    print("\n[0/4] CONNECTIVITY CHECKS")
    print("-" * 40)

    # Check pgvector
    try:
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT count(*) FROM field_embeddings")).fetchone()
            embedding_count = row[0]
        print(f"  pgvector:    OK ({embedding_count} embeddings)")
    except Exception as e:
        print(f"  pgvector:    FAIL — {e}")
        print("\n  Cannot proceed without pgvector. Exiting.")
        sys.exit(1)

    # Check explore_field_index
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT count(*) FROM explore_field_index")).fetchone()
            field_index_count = row[0]
        print(f"  field_index: OK ({field_index_count} rows)")
    except Exception as e:
        print(f"  field_index: FAIL — {e}")
        field_index_count = 0

    # Check SafeChain / LLM
    try:
        from src.adapters.model_adapter import get_model
        from config.constants import LLM_MODEL_IDX, EMBED_MODEL_IDX

        llm = get_model(LLM_MODEL_IDX)
        test_response = llm.invoke("Reply with exactly: OK")
        print(f"  SafeChain:   OK (LLM responded: {test_response[:20].strip()!r})")
    except Exception as e:
        print(f"  SafeChain:   FAIL — {e}")
        print("\n  Cannot proceed without SafeChain. Exiting.")
        sys.exit(1)

    # Check embedding model
    try:
        emb = get_model(EMBED_MODEL_IDX)
        test_emb = emb.embed_query("test")
        print(f"  Embeddings:  OK (dim={len(test_emb)})")
    except Exception as e:
        print(f"  Embeddings:  FAIL — {e}")
        print("\n  Cannot proceed without embeddings. Exiting.")
        sys.exit(1)

    # ── Step 1: Sample embeddings ────────────────────────────────────
    print("\n[1/4] EMBEDDING SAMPLE (first 5 records)")
    print("-" * 40)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT field_key, field_name, field_type, explore_name, view_name "
                "FROM field_embeddings ORDER BY id LIMIT 5"
            )).fetchall()
        for row in rows:
            print(f"  {row[0]:<50} type={row[2]:<12} explore={row[3]:<35} view={row[4]}")

        # Check explore_name format (comma-separated or single?)
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT explore_name FROM field_embeddings WHERE explore_name LIKE '%,%' LIMIT 1"
            )).fetchone()
        if row:
            print(f"\n  explore_name format: COMMA-SEPARATED (e.g., {row[0][:80]})")
        else:
            print(f"\n  explore_name format: SINGLE VALUE (one row per explore)")

        # Count per explore
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT explore_name, count(*) as cnt "
                "FROM field_embeddings GROUP BY explore_name ORDER BY cnt DESC"
            )).fetchall()
        print("\n  Embeddings per explore_name:")
        for row in rows:
            print(f"    {row[0]:<60} {row[1]:>4} records")

    except Exception as e:
        print(f"  Error sampling embeddings: {e}")

    # ── Step 2: Entity extraction test ───────────────────────────────
    print("\n[2/4] ENTITY EXTRACTION (raw LLM output)")
    print("-" * 40)

    from src.retrieval.vector import EntityExtractor
    extractor = EntityExtractor()

    for query, expected, desc in TEST_CASES[:3]:  # Just first 3 to save tokens
        print(f"\n  Query: {query}")
        try:
            extracted = extractor.extract_entities(query)
            print(f"    measures:   {extracted.measures}")
            print(f"    dimensions: {extracted.dimensions}")
            print(f"    time_range: {extracted.time_range}")
            print(f"    filters:    {extracted.filters}")
        except Exception as e:
            print(f"    EXTRACTION FAILED: {e}")

    # ── Step 3: Full pipeline runs ───────────────────────────────────
    print("\n\n[3/4] FULL PIPELINE RUNS")
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

            # Result
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

            # Scored explores (all, not just top)
            if pipeline_result.explores:
                print(f"\n  Explore scores ({len(pipeline_result.explores)} scored):")
                for j, exp in enumerate(pipeline_result.explores[:5]):  # Top 5
                    marker = " <── WINNER" if j == 0 else ""
                    marker += " ⚠ NEAR-MISS" if exp.is_near_miss else ""
                    base = f"(base: {exp.base_view_name})" if exp.base_view_name else "(no base view)"
                    print(
                        f"    #{j+1} {exp.name:<40} "
                        f"score={exp.score:.4f}  raw={exp.raw_score:.4f}  "
                        f"cov={exp.coverage:.2f}  conf={exp.confidence:.4f}  "
                        f"{base}{marker}"
                    )

                # Separation ratio
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
                        print(f"    {f.field}  {f.operator}  {f.values}")
                if rf.mandatory_filters:
                    print(f"  Mandatory filters: {len(rf.mandatory_filters)}")
                if rf.unresolved:
                    print(f"  UNRESOLVED filters: {rf.unresolved}")

            # Clarify reason
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

    # ── Step 4: Summary ──────────────────────────────────────────────
    print("\n\n" + "=" * 90)
    print("[4/4] SUMMARY")
    print("=" * 90)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    accuracy = passed / total * 100 if total else 0

    print(f"\n  {passed}/{total} passed ({accuracy:.0f}%)\n")
    print(f"  {'#':<4} {'Pass':<6} {'Confidence':<12} {'Time':<8} {'Expected':<40} {'Actual':<40}")
    print(f"  {'─'*4} {'─'*5} {'─'*11} {'─'*7} {'─'*39} {'─'*39}")

    for i, r in enumerate(results, 1):
        status = "OK" if r["passed"] else "FAIL"
        print(
            f"  {i:<4} {status:<6} {r['confidence']:<12.4f} {r['elapsed_s']:<8.1f} "
            f"{r['expected']:<40} {r['actual']:<40}"
        )

    # Failures detail
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
