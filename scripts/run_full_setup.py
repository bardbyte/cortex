#!/usr/bin/env python3
"""Master setup script — runs ALL ingestion steps and verifies everything.

One command to rule them all:
    python scripts/run_full_setup.py

Steps:
  0. Verify environment variables + connectivity + embedding model
  1. Create hybrid tables (explore_field_index, explore_partition_filters)
  2. Truncate old pgvector records + re-ingest with new per-view format
  3. Populate hybrid tables from LookML
  4. Build filter catalog (config/filter_catalog.json)
  5. Full verification (verify_changes.py)
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

# ─── Formatting ────────────────────────────────────────────────────

BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"

step_results: list[tuple[str, bool, str]] = []


def banner(msg: str):
    w = 64
    print(f"\n{CYAN}{'═' * w}")
    print(f"  {msg}")
    print(f"{'═' * w}{RESET}")


def step_header(num: int, total: int, name: str):
    print(f"\n{BOLD}[{num}/{total}] {name}{RESET}")
    print(f"{DIM}{'─' * 50}{RESET}")


def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}!{RESET} {msg}")


def info(msg: str):
    print(f"  {DIM}→{RESET} {msg}")


def record(name: str, success: bool, detail: str = ""):
    step_results.append((name, success, detail))


# ─── Step 0: Environment & Connectivity ────────────────────────────

def step_0_env_check() -> bool:
    step_header(0, 5, "Environment & Connectivity Check")

    # Load .env
    try:
        from dotenv import find_dotenv, load_dotenv
        env_path = find_dotenv()
        if env_path:
            load_dotenv(env_path, override=False)
            ok(f".env loaded: {env_path}")
        else:
            fail(".env file not found")
            return False
    except ImportError:
        fail("python-dotenv not installed — pip install python-dotenv")
        return False

    # Check + auto-fix required env vars
    required = ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        fail(f"Missing env vars: {', '.join(missing)}")
        return False
    for v in required:
        ok(f"{v}={os.getenv(v)}")

    # POSTGRES_DBNAME (used by constants.py) and POSTGRES_DB (used by postgres_age_client)
    dbname = os.getenv("POSTGRES_DBNAME")
    db = os.getenv("POSTGRES_DB") or os.getenv("POSTGRES_DATABASE")

    if dbname:
        ok(f"POSTGRES_DBNAME={dbname}")
    elif db:
        os.environ["POSTGRES_DBNAME"] = db
        warn(f"POSTGRES_DBNAME missing — auto-set from POSTGRES_DB={db}")
    else:
        fail("Neither POSTGRES_DBNAME nor POSTGRES_DB is set")
        return False

    if db:
        ok(f"POSTGRES_DB={db}")
    elif dbname:
        os.environ["POSTGRES_DB"] = dbname
        warn(f"POSTGRES_DB missing — auto-set from POSTGRES_DBNAME={dbname}")

    if not os.getenv("CONFIG_PATH"):
        default = str(REPO_ROOT / "config" / "config.yml")
        if Path(default).exists():
            os.environ["CONFIG_PATH"] = default
            warn(f"CONFIG_PATH auto-set to {default}")
        else:
            fail(f"CONFIG_PATH not set and {default} doesn't exist")
            return False
    else:
        ok(f"CONFIG_PATH={os.getenv('CONFIG_PATH')}")

    # Test PostgreSQL
    try:
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text as sa_text
        with get_engine().connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        ok("PostgreSQL connection: OK")
    except Exception as e:
        fail(f"PostgreSQL connection FAILED: {e}")
        return False

    # Test constants.py import
    try:
        from config.constants import POSTGRES_HOST as _h, POSTGRES_PORT as _p
        ok("config/constants.py: imports OK")
    except Exception as e:
        fail(f"config/constants.py import failed: {e}")
        return False

    # Test SafeChain + embedding model (real API call)
    try:
        from src.adapters.model_adapter import get_model
        info("Testing SafeChain embedding model (single API call)...")
        embed_client = get_model("2")
        test_vec = embed_client.embed_query("test query")
        dim = len(test_vec)
        ok(f"SafeChain + BGE embedding: {dim}-dim vectors")
        if dim != 1024:
            warn(f"Expected 1024-dim, got {dim} — check config.yml model '2'")
    except Exception as e:
        fail(f"SafeChain embedding FAILED: {e}")
        fail("Check: CONFIG_PATH, config.yml model entries, CIBIS credentials in .env")
        return False

    return True


# ─── Step 1: Create Hybrid Tables ──────────────────────────────────

def step_1_create_hybrid_tables() -> bool:
    step_header(1, 5, "Create Hybrid Tables")

    try:
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text as sa_text
        engine = get_engine()

        # 1a: Recreate AGE graph
        info("Recreating lookml_schema graph...")
        with engine.connect() as conn:
            conn.execute(sa_text("LOAD 'age'"))
            conn.execute(sa_text('SET search_path = ag_catalog, "$user", public'))
            try:
                conn.execute(sa_text("SELECT drop_graph('lookml_schema', true)"))
                conn.commit()
                ok("Dropped existing graph")
            except Exception:
                conn.rollback()
                ok("No existing graph to drop (clean slate)")

            conn.execute(sa_text("SELECT create_graph('lookml_schema')"))
            conn.commit()
            ok("Graph 'lookml_schema' created")

        # 1b: Create tables via individual DDL statements
        #     (avoids $$ parsing issues with multi-statement text() blocks)
        info("Creating hybrid tables...")

        ddl_statements = [
            # ── explore_field_index ──
            "DROP TABLE IF EXISTS explore_field_index CASCADE",
            """CREATE TABLE explore_field_index (
                explore_name VARCHAR(255) NOT NULL,
                field_name VARCHAR(255) NOT NULL,
                field_type VARCHAR(28) NOT NULL,
                view_name VARCHAR(255) NOT NULL,
                is_hidden BOOLEAN DEFAULT false,
                is_partition_key BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (explore_name, field_name)
            )""",
            "CREATE INDEX idx_efi_explore ON explore_field_index(explore_name)",
            "CREATE INDEX idx_efi_field ON explore_field_index(field_name)",
            """CREATE INDEX idx_efi_visible
               ON explore_field_index(explore_name, field_name)
               WHERE NOT is_hidden""",

            # ── explore_partition_filters ──
            "DROP TABLE IF EXISTS explore_partition_filters CASCADE",
            """CREATE TABLE explore_partition_filters (
                explore_name VARCHAR(255) PRIMARY KEY,
                required_filters VARCHAR(255) NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )""",

            # ── business_term_index ──
            "DROP TABLE IF EXISTS business_term_index CASCADE",
            """CREATE TABLE business_term_index (
                term_id SERIAL PRIMARY KEY,
                canonical_term VARCHAR(255) NOT NULL,
                synonyms TEXT[],
                field_name VARCHAR(255) NOT NULL,
                field_description TEXT,
                property TEXT,
                tsv TSVECTOR,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            "CREATE INDEX idx_bti_tsv ON business_term_index USING gin(tsv)",
            "CREATE INDEX idx_bti_field ON business_term_index(field_name)",
        ]

        with engine.begin() as conn:
            for stmt in ddl_statements:
                conn.execute(sa_text(stmt))

        ok("explore_field_index: created + indexed")
        ok("explore_partition_filters: created")
        ok("business_term_index: created + indexed")

        # 1c: Add tsvector trigger (separate because of $$ syntax)
        try:
            with engine.begin() as conn:
                # Use raw connection to avoid SQLAlchemy text() parsing issues with $$
                raw = conn.connection.dbapi_connection
                cursor = raw.cursor()
                cursor.execute("""
                    CREATE OR REPLACE FUNCTION business_term_tsv_trigger()
                    RETURNS trigger AS $$
                    BEGIN
                        NEW.tsv :=
                            setweight(to_tsvector('english', COALESCE(NEW.canonical_term, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.field_description, '')), 'B');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql
                """)
                cursor.execute("""
                    DROP TRIGGER IF EXISTS tsvector_update ON business_term_index
                """)
                cursor.execute("""
                    CREATE TRIGGER tsvector_update
                    BEFORE INSERT OR UPDATE ON business_term_index
                    FOR EACH ROW EXECUTE FUNCTION business_term_tsv_trigger()
                """)
            ok("tsvector trigger: created")
        except Exception as e:
            warn(f"tsvector trigger skipped (non-critical): {e}")

        # 1d: Verify
        with engine.connect() as conn:
            for tbl in ["explore_field_index", "explore_partition_filters", "business_term_index"]:
                exists = conn.execute(sa_text(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :t"
                ).bindparams(t=tbl)).scalar()
                if not exists:
                    fail(f"Table {tbl} NOT FOUND after creation")
                    return False

        ok("All 3 hybrid tables verified")
        return True

    except Exception as e:
        fail(f"Hybrid table creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─── Step 2: Truncate + Re-ingest pgvector ─────────────────────────

def step_2_reingest_pgvector() -> bool:
    step_header(2, 5, "Truncate + Re-ingest pgvector (per-view format)")

    try:
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text as sa_text
        engine = get_engine()

        # 2a: Check old state
        with engine.connect() as conn:
            old_count = conn.execute(sa_text("SELECT COUNT(*) FROM field_embeddings")).scalar()
        info(f"Current records: {old_count} (old per-explore format)")

        # 2b: Truncate
        info("Truncating old records...")
        with engine.begin() as conn:
            conn.execute(sa_text("TRUNCATE field_embeddings"))
        ok(f"Truncated {old_count} old records")

        # 2c: Run pipeline subprocess
        info("Running: parse LookML → generate embeddings → ingest to pgvector")
        info("This calls SafeChain for ~129 embeddings — may take 2-5 minutes...")
        print()

        t0 = time.time()
        result = subprocess.run(
            [sys.executable, "-m", "scripts.load_lookml_to_pgvector", "--mode", "pipeline"],
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
            timeout=600,
        )
        elapsed = time.time() - t0

        print()

        if result.returncode != 0:
            fail(f"Pipeline exited with code {result.returncode}")
            fail("Check the output above for the actual error")
            return False

        ok(f"Pipeline completed in {elapsed:.1f}s")

        # 2d: Verify new state
        with engine.connect() as conn:
            new_count = conn.execute(sa_text(
                "SELECT COUNT(*) FROM field_embeddings"
            )).scalar()

            types = conn.execute(sa_text(
                "SELECT field_type, COUNT(*) FROM field_embeddings GROUP BY field_type ORDER BY field_type"
            )).fetchall()

            bad_types = conn.execute(sa_text(
                "SELECT COUNT(*) FROM field_embeddings WHERE field_type = 'view'"
            )).scalar()

            sample = conn.execute(sa_text(
                "SELECT field_key, LEFT(content, 90) FROM field_embeddings LIMIT 3"
            )).fetchall()

            content_check = conn.execute(sa_text(
                "SELECT content FROM field_embeddings LIMIT 1"
            )).scalar() or ""

        ok(f"New record count: {new_count} (was {old_count})")

        type_str = ", ".join(f"{t}={c}" for t, c in types)
        ok(f"Field types: {type_str}")

        if bad_types > 0:
            fail(f"{bad_types} records have field_type='view' — old ingestion bug")
            return False
        else:
            ok("No field_type='view' records")

        if "is a measure" in content_check or "is a dimension" in content_check:
            fail(f"Content still in OLD format: '{content_check[:70]}...'")
            return False
        else:
            ok("Content is high-signal new format")

        for fk, content in sample:
            info(f"{fk} → {content}...")

        if new_count < 50:
            warn(f"Only {new_count} records — expected ~129. Some embeddings may have failed.")
            warn("Re-run this script to retry. Records with failed embeddings are skipped.")

        return True

    except subprocess.TimeoutExpired:
        fail("Pipeline timed out after 10 minutes — SafeChain may be unresponsive")
        return False
    except Exception as e:
        fail(f"Re-ingest failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─── Step 3: Populate Hybrid Tables ────────────────────────────────

def step_3_populate_hybrid_tables() -> bool:
    step_header(3, 5, "Populate Hybrid Tables from LookML")

    try:
        t0 = time.time()
        result = subprocess.run(
            [sys.executable, "scripts/load_lookml_to_graph.py"],
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        elapsed = time.time() - t0

        if result.returncode != 0:
            fail(f"load_lookml_to_graph.py failed (exit code {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-10:]:
                    fail(f"  {line}")
            return False

        for line in result.stdout.strip().split("\n"):
            if line.strip():
                info(line.strip())

        ok(f"Completed in {elapsed:.1f}s")

        # Verify
        from src.connectors.postgres_age_client import get_engine
        from sqlalchemy import text as sa_text

        with get_engine().connect() as conn:
            efi_count = conn.execute(sa_text(
                "SELECT COUNT(*) FROM explore_field_index"
            )).scalar()
            epf_count = conn.execute(sa_text(
                "SELECT COUNT(*) FROM explore_partition_filters"
            )).scalar()
            explores = conn.execute(sa_text(
                "SELECT explore_name, COUNT(*) FROM explore_field_index "
                "WHERE NOT is_hidden GROUP BY explore_name ORDER BY explore_name"
            )).fetchall()

        ok(f"explore_field_index: {efi_count} rows")
        ok(f"explore_partition_filters: {epf_count} rows")

        for name, cnt in explores:
            info(f"  {name}: {cnt} visible fields")

        if efi_count == 0:
            fail("explore_field_index is EMPTY — LookML parsing produced no results")
            return False
        if epf_count == 0:
            fail("explore_partition_filters is EMPTY — partition configs not loaded")
            return False

        return True

    except subprocess.TimeoutExpired:
        fail("Timed out after 2 minutes")
        return False
    except Exception as e:
        fail(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─── Step 4: Build Filter Catalog ──────────────────────────────────

def step_4_build_filter_catalog() -> bool:
    step_header(4, 5, "Build Filter Catalog")

    try:
        t0 = time.time()
        result = subprocess.run(
            [sys.executable, "-m", "scripts.load_lookml_to_pgvector", "--mode", "catalog"],
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        elapsed = time.time() - t0

        if result.returncode != 0:
            fail(f"Catalog build failed (exit code {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    fail(f"  {line}")
            return False

        for line in result.stdout.strip().split("\n"):
            if any(kw in line for kw in ["Value", "Synonym", "Yesno", "Partition", "Written", "CATALOG"]):
                info(line.strip())

        catalog_path = REPO_ROOT / "config" / "filter_catalog.json"
        if not catalog_path.exists():
            fail("config/filter_catalog.json was NOT created")
            return False

        catalog = json.loads(catalog_path.read_text())
        vm = len(catalog.get("value_map", {}))
        syn = len(catalog.get("synonyms", {}))
        pf = len(catalog.get("partition_fields", {}))
        ev = len(catalog.get("explore_views", {}))
        ok(f"filter_catalog.json: {vm} value maps, {syn} synonym groups, {pf} partitions, {ev} explores")
        ok(f"Completed in {elapsed:.1f}s")
        return True

    except Exception as e:
        fail(f"Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─── Step 5: Full Verification ─────────────────────────────────────

def step_5_verify() -> bool:
    step_header(5, 5, "Full Verification")

    try:
        result = subprocess.run(
            [sys.executable, "scripts/verify_changes.py"],
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=120,
        )

        for line in result.stdout.strip().split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if "PASS" in stripped:
                ok(stripped.replace("PASS", "").strip())
            elif "FAIL" in stripped:
                fail(stripped.replace("FAIL", "").strip())
            elif "RESULTS" in stripped or "===" in stripped:
                print(f"  {stripped}")
            elif stripped.startswith("["):
                info(stripped)

        return result.returncode == 0

    except Exception as e:
        fail(f"Verification failed: {e}")
        return False


# ─── Main ──────────────────────────────────────────────────────────

def main():
    total_start = time.time()

    banner("Cortex Full Setup")
    print(f"  {DIM}Repo:   {REPO_ROOT}{RESET}")
    print(f"  {DIM}Python: {sys.executable}{RESET}")
    print(f"  {DIM}Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}{RESET}")

    steps = [
        ("Environment Check",      step_0_env_check),
        ("Create Hybrid Tables",   step_1_create_hybrid_tables),
        ("Re-ingest pgvector",     step_2_reingest_pgvector),
        ("Populate Hybrid Tables", step_3_populate_hybrid_tables),
        ("Build Filter Catalog",   step_4_build_filter_catalog),
    ]

    stopped_early = False
    for name, func in steps:
        success = func()
        record(name, success)
        if not success:
            fail(f"STOPPED at '{name}'. Fix the error above and re-run.")
            warn("Running verification anyway for diagnostics...")
            verify_ok = step_5_verify()
            record("Full Verification", verify_ok)
            stopped_early = True
            break

    if not stopped_early:
        verify_ok = step_5_verify()
        record("Full Verification", verify_ok)

    # ── Final Summary ──
    total_elapsed = time.time() - total_start
    banner("RESULTS")

    all_passed = True
    for name, success, detail in step_results:
        status = f"{GREEN}PASS{RESET}" if success else f"{RED}FAIL{RESET}"
        suffix = f"  {DIM}{detail}{RESET}" if detail else ""
        print(f"  [{status}] {name}{suffix}")
        if not success:
            all_passed = False

    print(f"\n  {DIM}Total time: {total_elapsed:.1f}s{RESET}")

    if all_passed:
        print(f"\n  {GREEN}{BOLD}ALL SYSTEMS GO.{RESET}")
        print(f"  {DIM}pgvector ......... new per-view format, ~129 records{RESET}")
        print(f"  {DIM}hybrid tables .... explore_field_index + partition_filters{RESET}")
        print(f"  {DIM}filter catalog ... config/filter_catalog.json{RESET}")
        print(f"\n  {BOLD}Next step:{RESET} run the pipeline")
        print(f"  {CYAN}python -m src.cli.main{RESET}")
    else:
        print(f"\n  {RED}{BOLD}Fix the failures above, then re-run:{RESET}")
        print(f"  {CYAN}python scripts/run_full_setup.py{RESET}")

    print()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
