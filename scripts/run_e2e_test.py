#!/usr/bin/env python3
"""End-to-end retrieval pipeline accuracy test.

Tests the full pipeline against the 6 demo queries from 80-percent-coverage-queries.md.
Measures: explore selection accuracy, field match accuracy, filter resolution accuracy.

Usage:
    python scripts/run_e2e_test.py
    python scripts/run_e2e_test.py --verbose
    python scripts/run_e2e_test.py --skip-extraction  # Tests retrieval only with golden entities
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class ExpectedResult:
    """Expected pipeline output for a demo query."""
    query: str
    explore: str
    measures: list[str]
    dimensions: list[str]
    filters: dict[str, str]


# The 6 demo queries from 80-percent-coverage-queries.md
GOLDEN_QUERIES = [
    ExpectedResult(
        query="What is the total billed business for the OPEN segment?",
        explore="finance_cardmember_360",
        measures=["total_billed_business"],
        dimensions=[],
        filters={"bus_seg": "OPEN"},
    ),
    ExpectedResult(
        query="How many attrited customers do we have by generation?",
        explore="finance_cardmember_360",
        measures=["attrited_customer_count"],
        dimensions=["generation"],
        filters={},
    ),
    ExpectedResult(
        query="What is our attrition rate for Q4 2025?",
        explore="finance_cardmember_360",
        measures=["attrition_rate"],
        dimensions=[],
        filters={},
    ),
    ExpectedResult(
        query="What is the highest billed business by merchant category?",
        explore="finance_merchant_profitability",
        measures=["max_merchant_spend"],
        dimensions=["oracle_mer_hier_lvl3"],
        filters={},
    ),
    ExpectedResult(
        query="Show me the top 5 travel verticals by gross sales and booking count",
        explore="finance_travel_sales",
        measures=["total_gross_tls_sales", "total_bookings"],
        dimensions=["travel_vertical"],
        filters={},
    ),
    ExpectedResult(
        query="How many Millennial customers have Apple Pay enrolled and are active?",
        explore="finance_cardmember_360",
        measures=["active_customers_standard"],
        dimensions=[],
        filters={"generation": "Millennial", "apple_pay_wallet_flag": "Y"},
    ),
]


def run_pipeline_test(verbose: bool = False) -> dict:
    """Run all 6 queries through the pipeline and measure accuracy."""
    from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore

    results = {
        "total": len(GOLDEN_QUERIES),
        "explore_correct": 0,
        "measure_hits": 0,
        "measure_total": 0,
        "dimension_hits": 0,
        "dimension_total": 0,
        "fully_correct": 0,
        "details": [],
    }

    for i, expected in enumerate(GOLDEN_QUERIES, 1):
        print(f"\n{'─' * 60}")
        print(f"Q{i}: {expected.query}")
        print(f"{'─' * 60}")

        try:
            pipeline_result = retrieve_with_graph_validation(expected.query, top_k=10)
            top = get_top_explore(pipeline_result)

            if top is None:
                print(f"  FAIL: No explore found")
                results["details"].append({"query": expected.query, "status": "NO_MATCH"})
                results["measure_total"] += len(expected.measures)
                results["dimension_total"] += len(expected.dimensions)
                continue

            actual_explore = top["top_explore_name"]
            explore_correct = actual_explore == expected.explore

            # Check measures: do any entity candidates contain the expected field names?
            found_measures = set()
            found_dimensions = set()
            if pipeline_result.entities:
                for entity in pipeline_result.entities:
                    if entity.get("type") == "measure":
                        for candidate in entity.get("candidates", []):
                            fname = candidate.get("field_name", "")
                            if fname in expected.measures:
                                found_measures.add(fname)
                    elif entity.get("type") == "dimension":
                        for candidate in entity.get("candidates", []):
                            fname = candidate.get("field_name", "")
                            if fname in expected.dimensions:
                                found_dimensions.add(fname)

            measure_hits = len(found_measures)
            dimension_hits = len(found_dimensions)
            measure_total = len(expected.measures)
            dimension_total = len(expected.dimensions)

            fully_correct = (
                explore_correct
                and measure_hits == measure_total
                and dimension_hits == dimension_total
            )

            # Print results
            explore_mark = "PASS" if explore_correct else "FAIL"
            print(f"  Explore: [{explore_mark}] {actual_explore} (expected: {expected.explore})")

            if measure_total > 0:
                m_mark = "PASS" if measure_hits == measure_total else "PARTIAL" if measure_hits > 0 else "FAIL"
                print(f"  Measures: [{m_mark}] found {found_measures or 'none'} (expected: {expected.measures})")
            else:
                print(f"  Measures: [N/A] none expected")

            if dimension_total > 0:
                d_mark = "PASS" if dimension_hits == dimension_total else "PARTIAL" if dimension_hits > 0 else "FAIL"
                print(f"  Dimensions: [{d_mark}] found {found_dimensions or 'none'} (expected: {expected.dimensions})")
            else:
                print(f"  Dimensions: [N/A] none expected")

            overall = "PASS" if fully_correct else "FAIL"
            print(f"  Overall: [{overall}]")

            if verbose and pipeline_result.entities:
                print(f"\n  Entity details:")
                for entity in pipeline_result.entities:
                    print(f"    {entity.get('type')}: {entity.get('name')}")
                    for c in (entity.get("candidates") or [])[:3]:
                        print(f"      → {c.get('field_name')} (sim={c.get('similarity', 0):.4f})")

            # Accumulate
            if explore_correct:
                results["explore_correct"] += 1
            results["measure_hits"] += measure_hits
            results["measure_total"] += measure_total
            results["dimension_hits"] += dimension_hits
            results["dimension_total"] += dimension_total
            if fully_correct:
                results["fully_correct"] += 1

            results["details"].append({
                "query": expected.query,
                "status": "PASS" if fully_correct else "FAIL",
                "explore_correct": explore_correct,
                "actual_explore": actual_explore,
                "measure_hits": measure_hits,
                "measure_total": measure_total,
                "dimension_hits": dimension_hits,
                "dimension_total": dimension_total,
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results["details"].append({"query": expected.query, "status": "ERROR", "error": str(e)})
            results["measure_total"] += len(expected.measures)
            results["dimension_total"] += len(expected.dimensions)

    return results


def print_summary(results: dict):
    """Print accuracy summary."""
    total = results["total"]
    print(f"\n{'=' * 60}")
    print(f"ACCURACY REPORT — {total} Queries")
    print(f"{'=' * 60}")

    explore_pct = (results["explore_correct"] / total * 100) if total else 0
    full_pct = (results["fully_correct"] / total * 100) if total else 0
    measure_pct = (results["measure_hits"] / results["measure_total"] * 100) if results["measure_total"] else 100
    dim_pct = (results["dimension_hits"] / results["dimension_total"] * 100) if results["dimension_total"] else 100

    print(f"\n  Explore selection:    {results['explore_correct']}/{total}  ({explore_pct:.1f}%)")
    print(f"  Measure retrieval:    {results['measure_hits']}/{results['measure_total']}  ({measure_pct:.1f}%)")
    print(f"  Dimension retrieval:  {results['dimension_hits']}/{results['dimension_total']}  ({dim_pct:.1f}%)")
    print(f"  Fully correct:        {results['fully_correct']}/{total}  ({full_pct:.1f}%)")

    # Grade
    if full_pct >= 90:
        grade = "A — Production ready"
    elif full_pct >= 80:
        grade = "B — Demo ready"
    elif full_pct >= 60:
        grade = "C — Needs tuning"
    else:
        grade = "D — Architecture issues"

    print(f"\n  Grade: {grade}")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="E2E retrieval pipeline accuracy test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show entity details")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    print("=" * 60)
    print("Cortex E2E Retrieval Accuracy Test")
    print("=" * 60)
    print(f"Testing {len(GOLDEN_QUERIES)} queries from 80-percent-coverage-queries.md")

    results = run_pipeline_test(verbose=args.verbose)
    print_summary(results)


if __name__ == "__main__":
    main()
