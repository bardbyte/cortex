#!/usr/bin/env python3
"""Create optimized AGE graph schema with all indexes and hybrid tables.

This is the master setup script — run once after PostgreSQL+AGE is installed.

Usage:
    python scripts/setup_optimized_age_schema.py

Prerequisites:
  - PostgreSQL 13+ with AGE extension installed
  - Postgres environment variables in .env
  - Empty database or willingness to drop existing 'lookml_schema' graph
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.connectors.postgres_age_client import get_engine
from sqlalchemy import text


def create_graph():
    """Create the 'lookml_schema' graph (idempotent)."""
    print("\n Creating graph...")
    engine = get_engine()

    with engine.connect() as conn:
        # Load AGE and set search path
        conn.execute(text("LOAD 'age'"))
        conn.execute(text('SET search_path = ag_catalog, "$user", public'))

        # Drop and recreate (for clean setup)
        try:
            conn.execute(text("SELECT drop_graph('lookml_schema', true)"))
            print("  Dropped existing graph")
        except Exception as e:
            conn.rollback()
            print(f"  No existing graph to drop: {e}")

        conn.execute(text("SELECT create_graph('lookml_schema')"))
        conn.commit()
        print("  Graph 'lookml_schema' created!")


def create_property_indexes():
    """Create critical property indexes."""
    print("\n Creating property indexes...")
    engine = get_engine()

    graph_schema = "lookml_schema"
    vertex_table = f'"{graph_schema}"._ag_label_vertex'
    edge_table = f'"{graph_schema}"._ag_label_edge'

    def get_table_columns(conn, schema: str, table: str) -> set[str]:
        """Get column names for a table."""
        text_query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
        """
        result = conn.execute(text(text_query).bindparams(schema=schema, table=table))
        return {row[0] for row in result.fetchall()}

    with engine.connect() as conn:
        conn.execute(text('SET search_path = ag_catalog, "$user", public'))

        vertex_cols = get_table_columns(conn, graph_schema, "_ag_label_vertex")
        edge_cols = get_table_columns(conn, graph_schema, "_ag_label_edge")
        label_col = "label" if "label" in vertex_cols else None
        edge_label_col = "label" if "label" in edge_cols else None

        if label_col is None:
            print("  A Vertex label column not found; creating unfiltered indexes")
        if edge_label_col is None:
            print("  A Edge label column not found; skipping edge label index")

        def _where_label_equals(values: str) -> str:
            if label_col is None:
                return ""
            return f"WHERE {label_col} = '{values}'"

        def _where_label_in(values: list, label_col: str) -> str:
            if label_col is None:
                return ""
            return f"WHERE {label_col} IN ({values})"

        indexes = [
            # idx_explore_name
            (
                "idx_explore_name",
                f"""CREATE INDEX IF NOT EXISTS idx_explore_name
                    ON ({vertex_table}) (properties->>'name'::agtype)
                    {_where_label_equals('Explore')}""",
            ),
            # idx_view_name
            (
                "idx_view_name",
                f"""CREATE INDEX IF NOT EXISTS idx_view_name
                    ON ({vertex_table}) (properties->>'name'::agtype)
                    {_where_label_equals('View')}""",
            ),
            # idx_field_name
            (
                "idx_field_name",
                f"""CREATE INDEX IF NOT EXISTS idx_field_name
                    ON ({vertex_table}) (properties->>'name'::agtype)
                    {_where_label_equals('Dimension')} OR {_where_label_equals('Measure')}""",
            ),
            # idx_business_term
            (
                "idx_business_term",
                f"""CREATE INDEX IF NOT EXISTS idx_business_term
                    ON ({vertex_table}) (properties->>'term'::agtype)
                    {_where_label_equals('BusinessTerm')}""",
            ),
            # idx_business_term_synonyms
            (
                "idx_business_term_synonyms",
                f"""CREATE INDEX IF NOT EXISTS idx_business_term_synonyms
                    ON ({vertex_table}) USING gin(properties->>'synonyms'::agtype)
                    {_where_label_equals('BusinessTerm')}""",
            ),
            # idx_dimension_partition
            (
                "idx_dimension_partition",
                f"""CREATE INDEX IF NOT EXISTS idx_dimension_partition
                    ON ({vertex_table}) (properties->>'is_partition_key'::agtype)
                    {_where_label_equals('Dimension')}""",
            ),
        ]

        if label_col is not None:
            indexes.append(
                (
                    "idx_vertex_label",
                    f"""CREATE INDEX IF NOT EXISTS idx_vertex_label
                        ON ({vertex_table}) ({label_col})""",
                )
            )

        if edge_label_col is not None:
            indexes.append(
                (
                    "idx_edge_label",
                    f"""CREATE INDEX IF NOT EXISTS idx_edge_label
                        ON ({edge_table}) ({edge_label_col})""",
                )
            )

        for idx_name, idx_sql, *description in indexes:
            try:
                conn.execute(text(idx_sql))
                print(f"  + {idx_name}: {description[0] if description else 'created'}")
            except Exception as e:
                conn.rollback()
                print(f"  x {idx_name}: {e}")

        conn.commit()
        print("  All indexes created!")


def create_hybrid_tables():
    """Create hybrid optimization tables."""
    print("\n Creating hybrid optimization tables...")
    engine = get_engine()

    hybrid_ddl = """
    -- Explore-Field mapping table (for instant field validation)
    DROP TABLE IF EXISTS explore_field_index CASCADE;
    CREATE TABLE IF NOT EXISTS explore_field_index (
        explore_name VARCHAR(255) NOT NULL,
        field_name VARCHAR(255) NOT NULL,
        field_type VARCHAR(28) NOT NULL,
        view_name VARCHAR(255) NOT NULL,
        is_hidden BOOLEAN DEFAULT false,
        is_partition_key BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (explore_name, field_name)
    );

    CREATE INDEX idx_efi_explore ON explore_field_index(explore_name);
    CREATE INDEX idx_efi_field ON explore_field_index(field_name);
    CREATE INDEX idx_efi_composite ON explore_field_index(explore_name, field_name)
    WHERE NOT is_hidden;

    -- Partition filter cache (for instant required filter lookup)
    DROP TABLE IF EXISTS explore_partition_filters CASCADE;
    CREATE TABLE IF NOT EXISTS explore_partition_filters (
        explore_name VARCHAR(255) PRIMARY KEY,
        required_filters VARCHAR(255) NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW()
    );

    -- Business term index (for full-text search)
    DROP TABLE IF EXISTS business_term_index CASCADE;
    CREATE TABLE IF NOT EXISTS business_term_index (
        term_id SERIAL PRIMARY KEY,
        canonical_term VARCHAR(255) NOT NULL,
        synonyms TEXT[],
        field_name VARCHAR(20) NOT NULL,
        field_description TEXT,
        property TEXT,
        tsv TSVECTOR,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX idx_bti_tsv ON business_term_index USING gin(tsv);
    CREATE INDEX idx_bti_field ON business_term_index(field_name);

    -- Auto-update tsvector trigger
    CREATE OR REPLACE FUNCTION business_term_tsv_trigger() RETURNS trigger AS $$
    BEGIN
        NEW.tsv :=
            setweight(to_tsvector('english', COALESCE(NEW.canonical_term, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(NEW.field_description, '')), 'B');
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS tsvector_update ON business_term_index;
    CREATE TRIGGER tsvector_update BEFORE INSERT OR UPDATE ON business_term_index
    FOR EACH ROW EXECUTE FUNCTION business_term_tsv_trigger();
    """

    with engine.connect() as conn:
        try:
            # Execute the entire DDL block as one statement
            # (don't split on semicolons — it breaks $$ function definitions)
            conn.execute(text(hybrid_ddl))
            conn.commit()
            print("  + explore_field_index created")
            print("  + explore_partition_filters created")
            print("  + business_term_index created")
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Error creating tables: {e}")


def verify_setup():
    """Verify the setup is correct."""
    print("\n Verifying setup...")
    engine = get_engine()

    checks = [
        ("Graph exists", "SELECT name FROM ag_catalog.ag_graph WHERE name = 'lookml_schema'"),
        ("Vertex table exists", "SELECT to_regclass('lookml_schema._ag_label_vertex')"),
        ("Edge table exists", "SELECT to_regclass('lookml_schema._ag_label_edge')"),
        ("Explore table exists", "SELECT to_regclass('explore_field_index')"),
    ]

    idx_explore_index = "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_explore_name'"

    with engine.connect() as conn:
        for check_name, check_sql in checks:
            try:
                result = conn.execute(text(check_sql))
                print(f"  + {check_name}")
            except Exception as e:
                conn.rollback()
                print(f"  x {check_name}: {e}")


def print_next_steps():
    """Print next steps for the user."""
    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Load LookML data:")
    print("     python scripts/load_lookml_to_age.py --lookml-dir=Looker/")
    print("  2. Populate hybrid tables:")
    print("     python scripts/build_hybrid_indexes.py")
    print("  3. Test queries:")
    print("     python scripts/test_graph_queries.py")
    print("  4. Check performance:")
    print("     python scripts/benchmark_queries.py")
    print("  5. Set POSTGRES_GRAPH_PATH=lookml_schema in .env")
    print("     + Restart application")
    print("\n" + "=" * 60)


def main():
    """Main setup orchestration."""
    print("=" * 60)
    print("PostgreSQL AGE Optimized Schema Setup")
    print("=" * 60)

    try:
        # Step 1: Create graph
        create_graph()

        # Step 2: Create property indexes
        create_property_indexes()

        # Step 3: Create hybrid tables
        create_hybrid_tables()

        # Step 4: Verify
        verify_setup()

        # Step 5: Print next steps
        print_next_steps()

    except Exception as e:
        print(f"\n Setup failed: {e}")
        print("\nTroubleshooting:")
        print("  - Ensure PostgreSQL is running")
        print("  - Ensure AGE extension is installed (CREATE EXTENSION age)")
        print("  - Check POSTGRES_GRAPH_PATH=lookml_schema in .env")
        print("  - Check connection with: python examples/verify_setup.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
