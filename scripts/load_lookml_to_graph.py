#!/usr/bin/env python3
"""Load LookML structure into hybrid tables (explore_field_index + explore_partition_filters).

This script populates the relational acceleration tables that the pipeline uses
for hot-path field validation. These tables are 10-50x faster than AGE graph
queries for the "is field X in explore Y?" question.

Usage:
    python scripts/load_lookml_to_graph.py

Prerequisites:
  - PostgreSQL running with tables created by setup_optimized_age_schema.py
  - LookML files in lookml/ directory
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.connectors.postgres_age_client import get_engine
from scripts.load_lookml_to_pgvector import LookMLParser

logger = logging.getLogger(__name__)

# Partition filter fields per explore (from model's always_filter declarations)
EXPLORE_PARTITION_FILTERS = {
    "finance_cardmember_360": "partition_date",
    "finance_merchant_profitability": "partition_date",
    "finance_travel_sales": "booking_date",
    "finance_card_issuance": "issuance_date",
    "finance_customer_risk": "partition_date",
}


def populate_explore_field_index():
    """Populate explore_field_index from parsed LookML."""
    parser = LookMLParser()
    explores = parser.parse_model_explores()
    views = parser.parse_views()
    engine = get_engine()

    total = 0

    with engine.begin() as conn:
        # Clear existing data
        conn.execute(text("DELETE FROM explore_field_index"))

        for explore_name, explore_info in explores.items():
            for view_name in explore_info.view_names:
                view_info = views.get(view_name)
                if not view_info:
                    continue

                for field in view_info.fields:
                    is_partition = "partition_key" in field.tags
                    conn.execute(
                        text("""
                            INSERT INTO explore_field_index
                                (explore_name, field_name, field_type, view_name, is_hidden, is_partition_key)
                            VALUES (:explore_name, :field_name, :field_type, :view_name, :is_hidden, :is_partition_key)
                            ON CONFLICT (explore_name, field_name) DO UPDATE SET
                                field_type = EXCLUDED.field_type,
                                view_name = EXCLUDED.view_name,
                                is_hidden = EXCLUDED.is_hidden,
                                is_partition_key = EXCLUDED.is_partition_key
                        """).bindparams(
                            explore_name=explore_name,
                            field_name=field.name,
                            field_type=field.field_type,
                            view_name=view_name,
                            is_hidden=field.hidden,
                            is_partition_key=is_partition,
                        )
                    )
                    total += 1

    print(f"  Loaded {total} field mappings into explore_field_index")
    return total


def populate_partition_filters():
    """Populate explore_partition_filters from known model configuration."""
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM explore_partition_filters"))

        for explore_name, filter_field in EXPLORE_PARTITION_FILTERS.items():
            conn.execute(
                text("""
                    INSERT INTO explore_partition_filters (explore_name, required_filters)
                    VALUES (:explore_name, :required_filters)
                    ON CONFLICT (explore_name) DO UPDATE SET
                        required_filters = EXCLUDED.required_filters,
                        updated_at = NOW()
                """).bindparams(
                    explore_name=explore_name,
                    required_filters=filter_field,
                )
            )

    print(f"  Loaded {len(EXPLORE_PARTITION_FILTERS)} partition filter configs")


def verify():
    """Verify the hybrid tables are populated."""
    engine = get_engine()

    with engine.connect() as conn:
        efi_count = conn.execute(text("SELECT COUNT(*) FROM explore_field_index")).fetchone()[0]
        epf_count = conn.execute(text("SELECT COUNT(*) FROM explore_partition_filters")).fetchone()[0]

        # Show explore coverage
        explores = conn.execute(text(
            "SELECT explore_name, COUNT(*) as field_count FROM explore_field_index "
            "WHERE NOT is_hidden GROUP BY explore_name ORDER BY explore_name"
        )).fetchall()

    print(f"\n  explore_field_index: {efi_count} total rows")
    print(f"  explore_partition_filters: {epf_count} explores configured")
    print(f"\n  Per-explore visible field counts:")
    for row in explores:
        print(f"    {row[0]:<40} {row[1]} fields")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("=" * 60)
    print("Loading LookML into Hybrid Tables")
    print("=" * 60)

    print("\n[1/3] Populating explore_field_index...")
    populate_explore_field_index()

    print("\n[2/3] Populating explore_partition_filters...")
    populate_partition_filters()

    print("\n[3/3] Verifying...")
    verify()

    print("\n" + "=" * 60)
    print("Done! Hybrid tables ready for retrieval pipeline.")
    print("=" * 60)


if __name__ == "__main__":
    main()
