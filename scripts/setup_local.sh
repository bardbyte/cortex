#!/bin/bash
# Local development setup script for Cortex retrieval pipeline
# Usage: bash scripts/setup_local.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "============================================================"
echo "Cortex Local Development Setup"
echo "============================================================"

# Step 1: Install local Python dependencies
echo ""
echo "[1/6] Installing local Python dependencies..."
pip install -e ".[local]" 2>&1 | tail -5

# Step 2: Start Docker (PostgreSQL + AGE + pgvector)
echo ""
echo "[2/6] Starting Docker services..."
docker compose -f docker-compose.local.yaml up -d --build
echo "Waiting for PostgreSQL to be healthy..."
for i in $(seq 1 30); do
    if docker exec pgage pg_isready -U postgres > /dev/null 2>&1; then
        echo "  PostgreSQL is ready!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ERROR: PostgreSQL failed to start"
        exit 1
    fi
    sleep 2
done

# Step 3: Create schema (vector extension + tables + indexes)
echo ""
echo "[3/6] Setting up database schema..."
python scripts/setup_optimized_age_schema.py 2>&1

# Step 4: Load LookML into hybrid tables (explore_field_index)
echo ""
echo "[4/6] Loading LookML into hybrid tables..."
python scripts/load_lookml_to_graph.py 2>&1

# Step 5: Parse LookML → generate embeddings → load into pgvector
echo ""
echo "[5/6] Generating embeddings and loading into pgvector..."
echo "  (This downloads BGE-large-en-v1.5 on first run — ~1.3 GB)"
python -m scripts.load_lookml_to_pgvector --mode pipeline 2>&1

# Step 6: Run e2e accuracy test
echo ""
echo "[6/6] Running E2E accuracy test..."
python scripts/run_e2e_test.py 2>&1

echo ""
echo "============================================================"
echo "Setup complete! All systems operational."
echo "============================================================"
