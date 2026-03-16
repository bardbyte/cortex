#!/usr/bin/env python3
"""Inspect the current Docker/PostgreSQL state before applying any changes.

Run this on the corp laptop BEFORE making any code changes.
It gives a full picture of what's running, what's in the database,
and what needs to happen next.

Usage:
    python scripts/inspect_docker_state.py

No dependencies beyond what's already installed (sqlalchemy, psycopg2, dotenv).
"""

import os
import sys
import subprocess
import json
from pathlib import Path

# ── Setup ──
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

# Try loading .env
try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())
except ImportError:
    pass

SECTION = 0


def section(title):
    global SECTION
    SECTION += 1
    print(f"\n{'=' * 70}")
    print(f"  [{SECTION}] {title}")
    print(f"{'=' * 70}\n")


def run_cmd(cmd, silent=False):
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        if not silent and result.returncode != 0 and result.stderr:
            print(f"  stderr: {result.stderr.strip()[:200]}")
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "(timeout)", 1
    except Exception as e:
        return f"(error: {e})", 1


# ══════════════════════════════════════════════════════════════════════
# SECTION 1: Docker containers
# ══════════════════════════════════════════════════════════════════════
section("Docker Containers Running")

output, rc = run_cmd("docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'")
if rc == 0 and output:
    print(output)
else:
    print("  No Docker containers running or docker not available.")
    print(f"  (exit code: {rc})")

# Also check stopped containers
output_all, _ = run_cmd("docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' --filter 'status=exited'")
if output_all and output_all.strip():
    print("\n  Stopped containers:")
    print(f"  {output_all}")

# ══════════════════════════════════════════════════════════════════════
# SECTION 2: Docker compose config
# ══════════════════════════════════════════════════════════════════════
section("Docker Compose Config")

compose_files = list(REPO_ROOT.glob("docker-compose*.y*ml"))
if compose_files:
    for cf in compose_files:
        print(f"  Found: {cf.name}")
        content = cf.read_text()
        # Extract postgres env vars
        for line in content.split("\n"):
            stripped = line.strip()
            if any(k in stripped.upper() for k in ["POSTGRES_", "PGHOST", "PGPORT", "PGUSER", "PGPASS", "PGDATA"]):
                print(f"    {stripped}")
            if "image:" in stripped:
                print(f"    {stripped}")
            if "ports:" in stripped or (":" in stripped and "5432" in stripped):
                print(f"    {stripped}")
else:
    print("  No docker-compose files found in repo root.")


# ══════════════════════════════════════════════════════════════════════
# SECTION 3: Environment variables
# ══════════════════════════════════════════════════════════════════════
section("Environment Variables")

env_file = REPO_ROOT / ".env"
if env_file.exists():
    print(f"  .env file found at: {env_file}")
    content = env_file.read_text()
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Mask passwords
        if "PASSWORD" in line.upper() or "SECRET" in line.upper() or "KEY" in line.upper():
            key = line.split("=", 1)[0]
            print(f"    {key}=****")
        else:
            print(f"    {line}")
else:
    print("  NO .env file found!")

# Check critical env vars
print("\n  Critical env vars (resolved):")
critical_vars = [
    "POSTGRES_HOST", "PGHOST",
    "POSTGRES_PORT", "PGPORT",
    "POSTGRES_DB", "POSTGRES_DBNAME", "POSTGRES_DATABASE", "PGDATABASE",
    "POSTGRES_USER", "PGUSER",
    "CONFIG_PATH",
    "MCP_TOOLBOX_URL",
    "CORTEX_MODEL_NAME",
]
for var in critical_vars:
    val = os.getenv(var)
    if val:
        if "PASSWORD" in var.upper() or "SECRET" in var.upper():
            print(f"    {var} = ****")
        else:
            print(f"    {var} = {val}")


# ══════════════════════════════════════════════════════════════════════
# SECTION 4: Config files
# ══════════════════════════════════════════════════════════════════════
section("Config Files")

config_files = [
    "config/config.yml",
    "config/retrieval.yaml",
    "config/filter_catalog.json",
    "config/taxonomy.yaml",
]
for cf in config_files:
    full_path = REPO_ROOT / cf
    if full_path.exists():
        size = full_path.stat().st_size
        print(f"  EXISTS  {cf} ({size} bytes)")
        # Show key contents for config.yml
        if cf == "config/config.yml":
            content = full_path.read_text()
            for line in content.split("\n"):
                stripped = line.strip()
                if "model_name" in stripped or "api_base" in stripped or "model_url" in stripped:
                    print(f"          {stripped}")
    else:
        print(f"  MISSING {cf}")


# ══════════════════════════════════════════════════════════════════════
# SECTION 5: PostgreSQL connection + database state
# ══════════════════════════════════════════════════════════════════════
section("PostgreSQL Connection & Database State")

try:
    from sqlalchemy import text as sa_text
    from src.connectors.postgres_age_client import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        # Basic connectivity
        result = conn.execute(sa_text("SELECT version()"))
        pg_version = result.scalar()
        print(f"  Connected! PostgreSQL version:")
        print(f"    {pg_version[:80]}")

        # Current database
        db_name = conn.execute(sa_text("SELECT current_database()")).scalar()
        print(f"\n  Database: {db_name}")

        # All tables
        result = conn.execute(sa_text("""
            SELECT table_name,
                   pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as size
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = result.fetchall()
        print(f"\n  Tables ({len(tables)}):")
        for row in tables:
            print(f"    {row[0]:<40} {row[1]}")

        # Extensions
        result = conn.execute(sa_text("""
            SELECT extname, extversion FROM pg_extension
            WHERE extname IN ('vector', 'age', 'pgcrypto', 'uuid-ossp')
            ORDER BY extname
        """))
        exts = result.fetchall()
        print(f"\n  Extensions:")
        for row in exts:
            print(f"    {row[0]:<20} v{row[1]}")
        if not exts:
            print("    (none of vector/age found)")

        # AGE graph
        try:
            conn.execute(sa_text("LOAD 'age'"))
            conn.execute(sa_text("SET search_path = ag_catalog, \"$user\", public"))
            result = conn.execute(sa_text("SELECT name FROM ag_catalog.ag_graph"))
            graphs = [row[0] for row in result.fetchall()]
            print(f"\n  AGE Graphs: {graphs if graphs else '(none)'}")
        except Exception as e:
            print(f"\n  AGE: Not available ({e})")

except Exception as e:
    print(f"  FAILED to connect: {e}")
    print(f"\n  Troubleshooting:")
    print(f"    1. Is Docker running? (check section 1)")
    print(f"    2. Do .env POSTGRES_* vars match docker-compose? (check sections 2-3)")
    print(f"    3. Is the port mapped correctly? (check docker ps ports)")


# ══════════════════════════════════════════════════════════════════════
# SECTION 6: field_embeddings table (pgvector)
# ══════════════════════════════════════════════════════════════════════
section("field_embeddings (pgvector)")

try:
    engine = get_engine()
    with engine.connect() as conn:
        # Check if table exists
        exists = conn.execute(sa_text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'field_embeddings'
        """)).scalar()

        if not exists:
            print("  Table does NOT exist. Needs: python -m scripts.load_lookml_to_pgvector --mode db")
        else:
            # Record count
            count = conn.execute(sa_text("SELECT COUNT(*) FROM field_embeddings")).scalar()
            print(f"  Total records: {count}")

            if count > 0:
                # Column info
                result = conn.execute(sa_text("""
                    SELECT column_name, data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'field_embeddings'
                    ORDER BY ordinal_position
                """))
                cols = result.fetchall()
                print(f"\n  Schema ({len(cols)} columns):")
                for col in cols:
                    type_display = col[2] if col[2] != col[1] else col[1]
                    print(f"    {col[0]:<25} {type_display}")

                # Embedding dimension (check from vector column)
                try:
                    result = conn.execute(sa_text("""
                        SELECT atttypmod FROM pg_attribute
                        WHERE attrelid = 'field_embeddings'::regclass
                        AND attname = 'embedding'
                    """))
                    typmod = result.scalar()
                    if typmod and typmod > 0:
                        print(f"\n  Embedding dimension: {typmod}")
                    else:
                        print(f"\n  Embedding dimension: (dynamic/unset)")
                except Exception:
                    print(f"\n  Embedding dimension: (could not determine)")

                # field_type distribution
                result = conn.execute(sa_text("""
                    SELECT field_type, COUNT(*)
                    FROM field_embeddings
                    GROUP BY field_type
                    ORDER BY field_type
                """))
                types = result.fetchall()
                print(f"\n  field_type distribution:")
                for row in types:
                    flag = " <-- WRONG (should be 'dimension')" if row[0] == "view" else ""
                    print(f"    {row[0]:<15} {row[1]} records{flag}")

                # Unique views
                result = conn.execute(sa_text("""
                    SELECT view_name, COUNT(*)
                    FROM field_embeddings
                    GROUP BY view_name
                    ORDER BY view_name
                """))
                views = result.fetchall()
                print(f"\n  Records per view:")
                for row in views:
                    print(f"    {row[0]:<45} {row[1]} fields")

                # Unique explores
                result = conn.execute(sa_text("""
                    SELECT explore_name, COUNT(*)
                    FROM field_embeddings
                    GROUP BY explore_name
                    ORDER BY explore_name
                """))
                explores = result.fetchall()
                print(f"\n  Records per explore:")
                for row in explores:
                    print(f"    {row[0]:<45} {row[1]} fields")

                # Per-explore vs per-view dedup check
                unique_field_view = conn.execute(sa_text("""
                    SELECT COUNT(DISTINCT (view_name, field_name)) FROM field_embeddings
                """)).scalar()
                print(f"\n  Deduplication check:")
                print(f"    Total records:              {count}")
                print(f"    Unique (view, field) pairs:  {unique_field_view}")
                if count > unique_field_view * 1.5:
                    print(f"    STATUS: Per-EXPLORE records (duplicated) -- needs re-ingestion")
                else:
                    print(f"    STATUS: Per-VIEW records (deduplicated) -- good")

                # Sample content (first 3 records)
                result = conn.execute(sa_text("""
                    SELECT field_key, field_name, field_type, view_name,
                           LEFT(content, 120) as content_preview
                    FROM field_embeddings
                    ORDER BY field_key
                    LIMIT 5
                """))
                samples = result.fetchall()
                print(f"\n  Sample records (first 5):")
                for row in samples:
                    print(f"    field_key:  {row[0]}")
                    print(f"    field_name: {row[1]}")
                    print(f"    field_type: {row[2]}")
                    print(f"    view_name:  {row[3]}")
                    print(f"    content:    {row[4]}...")
                    print()

                # Content format check
                result = conn.execute(sa_text("""
                    SELECT content FROM field_embeddings LIMIT 10
                """))
                contents = [row[0] for row in result.fetchall()]
                old_format_count = sum(
                    1 for c in contents
                    if "is a measure" in c or "is a dimension" in c or "in the" in c.lower()[:50]
                )
                new_format_count = sum(
                    1 for c in contents
                    if "Also known as:" in c or (": " in c[:40] and "is a " not in c)
                )
                print(f"  Content format analysis (sampled {len(contents)} records):")
                print(f"    Old format (structural metadata in text): {old_format_count}")
                print(f"    New format (semantic-only with synonyms):  {new_format_count}")
                if old_format_count > new_format_count:
                    print(f"    STATUS: Old format -- needs re-ingestion with enhanced script")
                else:
                    print(f"    STATUS: New format -- good")

                # Index check
                result = conn.execute(sa_text("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'field_embeddings'
                """))
                indexes = result.fetchall()
                print(f"\n  Indexes on field_embeddings:")
                for row in indexes:
                    print(f"    {row[0]}")
                    print(f"      {row[1][:100]}")

except Exception as e:
    print(f"  Cannot inspect: {e}")


# ══════════════════════════════════════════════════════════════════════
# SECTION 7: Hybrid tables (explore_field_index, explore_partition_filters)
# ══════════════════════════════════════════════════════════════════════
section("Hybrid Tables (explore_field_index, explore_partition_filters)")

try:
    engine = get_engine()
    with engine.connect() as conn:
        for table_name in ["explore_field_index", "explore_partition_filters"]:
            exists = conn.execute(sa_text(f"""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = '{table_name}'
            """)).scalar()

            if not exists:
                print(f"  {table_name}: DOES NOT EXIST")
                print(f"    Needs: python scripts/setup_optimized_age_schema.py")
                continue

            count = conn.execute(sa_text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"  {table_name}: {count} rows")

            if table_name == "explore_field_index" and count > 0:
                result = conn.execute(sa_text("""
                    SELECT explore_name, COUNT(*) as total,
                           SUM(CASE WHEN NOT is_hidden THEN 1 ELSE 0 END) as visible
                    FROM explore_field_index
                    GROUP BY explore_name
                    ORDER BY explore_name
                """))
                explores = result.fetchall()
                print(f"    Per-explore breakdown:")
                for row in explores:
                    print(f"      {row[0]:<40} {row[2]} visible / {row[1]} total")

            if table_name == "explore_partition_filters" and count > 0:
                result = conn.execute(sa_text("""
                    SELECT explore_name, required_filters
                    FROM explore_partition_filters
                    ORDER BY explore_name
                """))
                filters = result.fetchall()
                print(f"    Configured partitions:")
                for row in filters:
                    print(f"      {row[0]:<40} {row[1]}")

except Exception as e:
    print(f"  Cannot inspect: {e}")


# ══════════════════════════════════════════════════════════════════════
# SECTION 8: LookML files check
# ══════════════════════════════════════════════════════════════════════
section("LookML Files")

lookml_dir = REPO_ROOT / "lookml"
if lookml_dir.exists():
    model_files = list(lookml_dir.glob("*.model.lkml"))
    view_files = list((lookml_dir / "views").glob("*.view.lkml")) if (lookml_dir / "views").exists() else []

    print(f"  Model files: {len(model_files)}")
    for f in model_files:
        print(f"    {f.name}")

    print(f"\n  View files: {len(view_files)}")
    for f in sorted(view_files):
        content = f.read_text()
        dim_count = content.count("dimension:")
        measure_count = content.count("measure:")
        has_descriptions = "Also known as:" in content
        has_case = "CASE WHEN" in content
        print(
            f"    {f.name:<50} "
            f"dims={dim_count:<3} measures={measure_count:<3} "
            f"{'descriptions' if has_descriptions else '           '} "
            f"{'CASE' if has_case else '    '}"
        )
else:
    print("  lookml/ directory not found")


# ══════════════════════════════════════════════════════════════════════
# SECTION 9: SafeChain / model access
# ══════════════════════════════════════════════════════════════════════
section("SafeChain / Model Access")

config_path = os.getenv("CONFIG_PATH", "")
if config_path:
    full_config = REPO_ROOT / config_path if not Path(config_path).is_absolute() else Path(config_path)
    print(f"  CONFIG_PATH: {config_path}")
    print(f"  Resolved: {full_config}")
    print(f"  Exists: {full_config.exists()}")
else:
    print("  CONFIG_PATH not set — auto-searching...")
    for c in [REPO_ROOT / "config" / "config.yml", REPO_ROOT / "config.yml"]:
        if c.exists():
            print(f"  Found: {c}")
            break

# SafeChain import + connectivity check
from safechain.lcel import model
print("  safechain.lcel: OK")
from ee_config.config import Config
Config.from_env()
print("  ee_config.config: OK (initialized)")


# ══════════════════════════════════════════════════════════════════════
# SECTION 10: Python environment
# ══════════════════════════════════════════════════════════════════════
section("Python Environment")

print(f"  Python: {sys.version}")
print(f"  Path: {sys.executable}")

key_packages = [
    "sqlalchemy", "psycopg2", "dotenv", "yaml",
    "safechain", "ee_config",
]
print(f"\n  Key packages:")
for pkg in key_packages:
    try:
        mod = __import__(pkg.replace("-", "_").split(".")[0])
        version = getattr(mod, "__version__", "?")
        print(f"    {pkg:<25} {version}")
    except ImportError:
        print(f"    {pkg:<25} NOT INSTALLED")


# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════
section("SUMMARY — What Needs to Happen")

print("  Copy the FULL output above and paste it to Claude.")
print("  It will tell you exactly what to do next.")
print()
print("  Quick self-check:")
print("    - Docker running?          Check section 1")
print("    - .env correct?            Check section 3")
print("    - config.yml exists?       Check section 4")
print("    - PostgreSQL connected?    Check section 5")
print("    - field_embeddings exist?  Check section 6")
print("    - Hybrid tables exist?     Check section 7")
print("    - LookML has descriptions? Check section 8")
print("    - SafeChain importable?    Check section 9")
