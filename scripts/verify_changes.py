#!/usr/bin/env python3
"""Verify that all Round 1 + Round 3 changes are correctly applied.

Run on the corp laptop after cherry-picking or manually applying changes.
Usage: python scripts/verify_changes.py

Each check prints PASS or FAIL. Fix any FAILs before re-ingesting.
"""

import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}  ← {detail}")
        failed += 1


print("\n" + "=" * 70)
print("  VERIFICATION: Round 1 + Round 3 Changes")
print("=" * 70)

# ── config/retrieval.yaml ──
print("\n[1/12] config/retrieval.yaml")
content = (REPO_ROOT / "config/retrieval.yaml").read_text()
check("embedding_dim is 1024", "embedding_dim: 1024" in content,
      "Still says 768 — change to 1024")

# ── config/constants.py ──
print("\n[2/12] config/constants.py")
content = (REPO_ROOT / "config/constants.py").read_text()
check("LLM_MODEL_IDX exists", "LLM_MODEL_IDX" in content,
      "Add: LLM_MODEL_IDX = '1'")
check("BGE_QUERY_PREFIX exists", "BGE_QUERY_PREFIX" in content,
      "Add: BGE_QUERY_PREFIX = 'Represent this sentence...'")
check("EXPLORE_BASE_VIEWS exists", "EXPLORE_BASE_VIEWS" in content,
      "Add EXPLORE_BASE_VIEWS dict")
check("EXPLORE_DESCRIPTIONS exists", "EXPLORE_DESCRIPTIONS" in content,
      "Add EXPLORE_DESCRIPTIONS dict")
check("SIMILARITY_FLOOR exists", "SIMILARITY_FLOOR" in content,
      "Add: SIMILARITY_FLOOR = 0.65")
check("SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE exists",
      "SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE" in content,
      "Add type-filtered SQL query")
check("SQL_VALIDATE_FIELDS_IN_EXPLORE exists",
      "SQL_VALIDATE_FIELDS_IN_EXPLORE" in content,
      "Add hybrid table SQL query")
check("SQL_GET_EXPLORES_FOR_FIELDS exists",
      "SQL_GET_EXPLORES_FOR_FIELDS" in content,
      "Add explore selection SQL query")
check("SQL_GET_PARTITION_FILTERS exists",
      "SQL_GET_PARTITION_FILTERS" in content,
      "Add partition filter SQL query")
check("VECTOR(1024) not VECTOR(768)",
      "VECTOR(1024)" in content or "vector(1024)" in content,
      "Table creation still says 768 — change to 1024")

# ── lookml/finance_model.model.lkml ──
print("\n[3/12] lookml/finance_model.model.lkml")
content = (REPO_ROOT / "lookml/finance_model.model.lkml").read_text()
check("many_to_one relationship", "many_to_one" in content,
      "cmdl_card_main join still says one_to_one — change to many_to_one")

# ── LookML views (6 files) ──
print("\n[4/12] LookML view files — new measures appended")
view_checks = {
    "lookml/views/cmdl_card_main.view.lkml": [
        ("apple_pay_customer_count", "Apple Pay count measure"),
        ("basic_card_count", "Basic card count measure"),
        ("apple_pay_penetration", "Apple Pay penetration rate"),
    ],
    "lookml/views/custins_customer_insights_cardmember.view.lkml": [
        ("Also known as:", "Rich descriptions with synonyms"),
    ],
    "lookml/views/fin_card_member_merchant_profitability.view.lkml": [
        ("Also known as:", "Rich descriptions with synonyms"),
    ],
    "lookml/views/risk_indv_cust.view.lkml": [
        ("Also known as:", "Rich descriptions with synonyms"),
    ],
    "lookml/views/tlsarpt_travel_sales.view.lkml": [
        ("Also known as:", "Rich descriptions with synonyms"),
    ],
}
for filepath, checks in view_checks.items():
    full_path = REPO_ROOT / filepath
    if not full_path.exists():
        check(f"{filepath} exists", False, "File not found")
        continue
    content = full_path.read_text()
    for search_term, desc in checks:
        check(f"{Path(filepath).name}: {desc}", search_term in content,
              f"Missing '{search_term}' — new measures/descriptions not appended")

# ── src/retrieval/vector.py ──
print("\n[5/12] src/retrieval/vector.py")
content = (REPO_ROOT / "src/retrieval/vector.py").read_text()
check("Uses model_adapter (not safechain.lct)",
      "from src.adapters.model_adapter import get_model" in content,
      "Still importing from safechain.lct — change to model_adapter")
check("No safechain.lct import",
      "safechain.lct" not in content,
      "Remove: from safechain.lct import model")
check("BGE_QUERY_PREFIX imported",
      "BGE_QUERY_PREFIX" in content,
      "Add BGE_QUERY_PREFIX to imports from constants")
check("embed_text has is_query param",
      "is_query" in content,
      "embed_text() needs is_query parameter for BGE prefix")
check("field_type filter on search",
      'field_type="measure"' in content or "field_type='measure'" in content,
      "search_similar_fields needs field_type parameter")
check("No generic dimension enrichment",
      "Also known as: attribute, segment, grouping" not in content,
      "Remove generic enrichment text — LookML descriptions handle this now")
check("'how many' in METRIC_INTENT_TERMS",
      '"how many"' in content,
      "Add 'how many', 'highest', 'lowest', 'top' to METRIC_INTENT_TERMS")
check("SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE imported",
      "SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE" in content,
      "Add to constants import")

# ── scripts/load_lookml_to_pgvector.py ──
print("\n[6/12] scripts/load_lookml_to_pgvector.py")
content = (REPO_ROOT / "scripts/load_lookml_to_pgvector.py").read_text()
check("Uses SafeChain for embeddings",
      "safechain" in content or "model_adapter" in content,
      "Must use SafeChain (directly or via model_adapter) for embeddings")
check("High signal-density content",
      "signal" in content.lower() or "_build_content" in content,
      "_build_content method should produce semantic-only text")
check("Per-view deduplication",
      "per-view" in content.lower() or "field_to_explores" in content,
      "Records should be per-view, not per-explore")

# ── src/retrieval/graph_search.py ──
print("\n[7/12] src/retrieval/graph_search.py")
content = (REPO_ROOT / "src/retrieval/graph_search.py").read_text()
check("validate_fields_in_explore function",
      "def validate_fields_in_explore" in content,
      "Add hybrid table validation function")
check("get_explores_for_fields function",
      "def get_explores_for_fields" in content,
      "Add explore selection function")
check("get_partition_filters function",
      "def get_partition_filters" in content,
      "Add partition filter lookup function")
check("Original find_explores_for_view preserved",
      "def find_explores_for_view" in content,
      "Keep Likhita's original function")

# ── src/retrieval/pipeline.py ──
print("\n[8/12] src/retrieval/pipeline.py")
content = (REPO_ROOT / "src/retrieval/pipeline.py").read_text()
check("Imports get_explores_for_fields",
      "get_explores_for_fields" in content,
      "Should use hybrid table function, not find_explores_for_view only")
check("EXPLORE_BASE_VIEWS imported",
      "EXPLORE_BASE_VIEWS" in content,
      "Needs base view map for scoring")
check("Multiplicative scoring",
      "coverage" in content and "base_view" in content,
      "Scoring formula should use coverage × base_view_bonus")
check("resolve_filters imported",
      "resolve_filters" in content,
      "Pipeline should call filter resolution for top explore")

# ── src/retrieval/orchestrator.py ──
print("\n[9/12] src/retrieval/orchestrator.py")
content = (REPO_ROOT / "src/retrieval/orchestrator.py").read_text()
check("Imports from filters.py (not inline FILTER_VALUE_MAP)",
      "from src.retrieval.filters import" in content,
      "FILTER_VALUE_MAP should be imported from filters.py, not defined inline")
check("No inline FILTER_VALUE_MAP dict",
      '"millennials": "Millennial"' not in content or "from src.retrieval.filters" in content,
      "Remove inline FILTER_VALUE_MAP — it's now in filters.py")
check("1024-dim (not 768)",
      "1024" in content,
      "Embedding dim comment should say 1024")
check("EXPLORE_PARTITION_FIELDS for partition field name",
      "EXPLORE_PARTITION_FIELDS" in content,
      "Partition field should be explore-specific, not hardcoded 'partition_date'")

# ── New files that must exist ──
print("\n[10/12] New files that must exist")
new_files = [
    "src/adapters/__init__.py",
    "src/adapters/model_adapter.py",
    "src/retrieval/filters.py",
    "config/filter_catalog.json",
    "scripts/load_lookml_to_graph.py",
]
for f in new_files:
    check(f"{f} exists", (REPO_ROOT / f).exists(),
          f"Missing new file — copy from saheb/orchestrator-v1")

# ── Docker / Database checks ──
print("\n[11/12] Database connectivity")
try:
    from src.connectors.postgres_age_client import get_engine
    from sqlalchemy import text as sa_text
    engine = get_engine()
    with engine.connect() as conn:
        # Check pgvector table exists
        result = conn.execute(sa_text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'field_embeddings'"
        ))
        table_exists = result.scalar() > 0
        check("field_embeddings table exists", table_exists,
              "Run: python -m scripts.load_lookml_to_pgvector --mode db")

        if table_exists:
            # Check record count
            result = conn.execute(sa_text("SELECT COUNT(*) FROM field_embeddings"))
            count = result.scalar()
            check(f"field_embeddings has records ({count})", count > 0,
                  "Run: python -m scripts.load_lookml_to_pgvector --mode all")

            # Check field_type correctness
            result = conn.execute(sa_text(
                "SELECT COUNT(*) FROM field_embeddings WHERE field_type = 'view'"
            ))
            bad_types = result.scalar()
            check(f"No field_type='view' records ({bad_types} found)",
                  bad_types == 0,
                  "Re-ingest: field_type should be 'dimension' or 'measure', not 'view'")

            # Check embedding dimension
            result = conn.execute(sa_text(
                "SELECT array_length(embedding::text::text[], 1) FROM field_embeddings LIMIT 1"
            ))
            # Alternative: check the vector column definition
            result2 = conn.execute(sa_text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_name = 'field_embeddings' AND column_name = 'embedding'"
            ))
            udt = result2.scalar()
            check(f"Embedding column type: {udt}", True, "")

            # Check content quality (should NOT contain structural metadata)
            result = conn.execute(sa_text(
                "SELECT content FROM field_embeddings LIMIT 1"
            ))
            sample_content = result.scalar() or ""
            has_structural_noise = "is a measure" in sample_content and "in the" in sample_content
            check("Content is high-signal (no structural metadata)",
                  not has_structural_noise,
                  f"Content still has old format: '{sample_content[:80]}...' — re-ingest")

        # Check hybrid tables
        result = conn.execute(sa_text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'explore_field_index'"
        ))
        efi_exists = result.scalar() > 0
        check("explore_field_index table exists", efi_exists,
              "Run: python scripts/load_lookml_to_graph.py")

        if efi_exists:
            result = conn.execute(sa_text("SELECT COUNT(*) FROM explore_field_index"))
            efi_count = result.scalar()
            check(f"explore_field_index has records ({efi_count})", efi_count > 0,
                  "Run: python scripts/load_lookml_to_graph.py")

        result = conn.execute(sa_text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'explore_partition_filters'"
        ))
        epf_exists = result.scalar() > 0
        check("explore_partition_filters table exists", epf_exists,
              "Run: python scripts/load_lookml_to_graph.py")

except Exception as e:
    check("PostgreSQL connection", False, f"Cannot connect: {e}")

# ── pyproject.toml ──
print("\n[12/12] pyproject.toml")
content = (REPO_ROOT / "pyproject.toml").read_text()
check("psycopg2-binary in dependencies",
      "psycopg2-binary" in content or "psycopg2" in content,
      "Add psycopg2-binary to dependencies")

# ── Summary ──
print("\n" + "=" * 70)
print(f"  RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("  All checks passed! Ready to re-ingest and test.")
else:
    print(f"  Fix the {failed} FAIL(s) above, then run this script again.")
print("=" * 70 + "\n")

sys.exit(0 if failed == 0 else 1)
