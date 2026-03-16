#!/bin/bash
# Run the full Cortex orchestrator: verify deps → unit tests → integration tests → start server → API tests
# Usage: bash scripts/run_orchestrator.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

PORT=8080
BASE_URL="http://localhost:$PORT"

echo "============================================================"
echo "  Cortex Orchestrator — Full Stack Test"
echo "============================================================"

# ── Step 1: Check prerequisites ──────────────────────────────────
echo ""
echo "[1/5] Checking prerequisites..."

# Python
python3 --version || { echo "FAIL: python3 not found"; exit 1; }

# PostgreSQL (Docker)
if docker exec pgage pg_isready -U postgres > /dev/null 2>&1; then
    echo "  PostgreSQL: OK"
else
    echo "  PostgreSQL: NOT RUNNING"
    echo "  Starting Docker services..."
    docker compose -f docker-compose.local.yaml up -d
    for i in $(seq 1 15); do
        if docker exec pgage pg_isready -U postgres > /dev/null 2>&1; then
            echo "  PostgreSQL: OK (started)"
            break
        fi
        if [ "$i" -eq 15 ]; then
            echo "  FAIL: PostgreSQL won't start. Run: docker compose -f docker-compose.local.yaml up -d"
            exit 1
        fi
        sleep 2
    done
fi

# SafeChain
python3 -c "from ee_config.config import Config; Config.from_env(); print('  SafeChain: OK')" 2>/dev/null || {
    echo "  FAIL: SafeChain not available. Check CONFIG_PATH and ee_config."
    exit 1
}

# pgvector has data
ROW_COUNT=$(python3 -c "
from src.connectors.postgres_age_client import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    r = conn.execute(text('SELECT count(*) FROM field_embeddings'))
    print(r.scalar())
" 2>/dev/null)
echo "  pgvector field_embeddings: $ROW_COUNT rows"
if [ "$ROW_COUNT" = "0" ] || [ -z "$ROW_COUNT" ]; then
    echo "  FAIL: No embeddings loaded. Run: bash scripts/setup_local.sh"
    exit 1
fi

echo "  All prerequisites OK."

# ── Step 2: Unit tests ───────────────────────────────────────────
echo ""
echo "[2/5] Running unit tests..."
python3 scripts/test_orchestrator_local.py 2>&1

# ── Step 3: Integration tests (retrieval pipeline) ───────────────
echo ""
echo "[3/5] Running integration tests (retrieval + scoring + filters)..."
python3 -c "
import time, logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore

queries = [
    'Total billed business by generation',
    'How many attrited customers by card product',
    'Top 5 travel verticals by gross sales',
]

for q in queries:
    t0 = time.time()
    result = retrieve_with_graph_validation(q, top_k=5)
    ms = (time.time() - t0) * 1000
    top = get_top_explore(result)
    print(f'  {q}')
    print(f'    -> {top.get(\"top_explore_name\", \"NONE\")} | conf={top.get(\"confidence\", 0):.3f} | action={top.get(\"action\")} | {ms:.0f}ms')
    print()
"

# ── Step 4: Start server in background ───────────────────────────
echo ""
echo "[4/5] Starting API server on port $PORT..."

# Kill any existing server on this port
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
sleep 1

uvicorn src.api.server:app --host 0.0.0.0 --port $PORT --log-level info &
SERVER_PID=$!

# Wait for server to be ready
echo "  Waiting for server (PID $SERVER_PID)..."
for i in $(seq 1 30); do
    if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
        echo "  Server is ready!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  FAIL: Server didn't start in 60s. Check logs above."
        kill $SERVER_PID 2>/dev/null
        exit 1
    fi
    sleep 2
done

# ── Step 5: API tests ────────────────────────────────────────────
echo ""
echo "[5/5] Running API tests (SSE streaming, trace, follow-up, feedback)..."
python3 scripts/test_orchestrator_local.py --api-only --url "$BASE_URL" 2>&1
API_EXIT=$?

# ── Cleanup ──────────────────────────────────────────────────────
echo ""
echo "Shutting down server (PID $SERVER_PID)..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

echo ""
if [ $API_EXIT -eq 0 ]; then
    echo "============================================================"
    echo "  ALL TESTS PASSED"
    echo "============================================================"
else
    echo "============================================================"
    echo "  SOME TESTS FAILED — check output above"
    echo "============================================================"
    exit 1
fi
