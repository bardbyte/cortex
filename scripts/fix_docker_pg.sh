#!/bin/bash
# Diagnose and fix Docker + PostgreSQL connectivity for Cortex
# Usage: bash scripts/fix_docker_pg.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Cortex — Docker + PostgreSQL Diagnostic & Fix${NC}"
echo -e "${BOLD}============================================================${NC}"
echo ""

# ── Step 1: Docker Desktop process ──────────────────────────────
echo -e "${BOLD}[1/7] Docker Desktop process${NC}"
if pgrep -f "Docker Desktop" > /dev/null 2>&1 || pgrep -f "com.docker.backend" > /dev/null 2>&1; then
    echo -e "  ${GREEN}Docker Desktop is running${NC}"
else
    echo -e "  ${RED}Docker Desktop is NOT running${NC}"
    echo -e "  ${YELLOW}Starting Docker Desktop...${NC}"
    open -a Docker
    echo "  Waiting 30s for Docker Desktop to initialize..."
    sleep 30
fi

# ── Step 2: Docker socket ───────────────────────────────────────
echo ""
echo -e "${BOLD}[2/7] Docker socket connectivity${NC}"

# Try all known socket paths
SOCKET_PATHS=(
    "$HOME/.docker/run/docker.sock"
    "$HOME/Library/Containers/com.docker.docker/Data/docker.raw.sock"
    "/var/run/docker.sock"
)

WORKING_SOCKET=""
for sock in "${SOCKET_PATHS[@]}"; do
    if [ -S "$sock" ]; then
        echo -e "  Found socket: ${GREEN}$sock${NC}"
        if DOCKER_HOST="unix://$sock" docker info > /dev/null 2>&1; then
            echo -e "  ${GREEN}Socket works!${NC}"
            WORKING_SOCKET="$sock"
            break
        else
            echo -e "  ${YELLOW}Socket exists but docker info failed${NC}"
        fi
    else
        echo -e "  ${DIM}Not found: $sock${NC}"
    fi
done

if [ -z "$WORKING_SOCKET" ]; then
    echo -e "  ${RED}No working Docker socket found.${NC}"
    echo -e "  ${YELLOW}Try: Quit Docker Desktop completely, reopen it, wait 30s, re-run this script.${NC}"
    exit 1
fi

# Set DOCKER_HOST for this session
export DOCKER_HOST="unix://$WORKING_SOCKET"
echo -e "  Using: DOCKER_HOST=unix://$WORKING_SOCKET"

# ── Step 3: Persist DOCKER_HOST ─────────────────────────────────
echo ""
echo -e "${BOLD}[3/7] Persisting DOCKER_HOST in ~/.zshrc${NC}"

EXPORT_LINE="export DOCKER_HOST=unix://$WORKING_SOCKET"
if grep -q "DOCKER_HOST" ~/.zshrc 2>/dev/null; then
    # Update existing line
    sed -i '' "s|.*DOCKER_HOST.*|$EXPORT_LINE|" ~/.zshrc
    echo -e "  ${GREEN}Updated existing DOCKER_HOST in ~/.zshrc${NC}"
else
    echo "" >> ~/.zshrc
    echo "# Docker Desktop socket (set by cortex fix_docker_pg.sh)" >> ~/.zshrc
    echo "$EXPORT_LINE" >> ~/.zshrc
    echo -e "  ${GREEN}Added DOCKER_HOST to ~/.zshrc${NC}"
fi

# ── Step 4: Docker context ──────────────────────────────────────
echo ""
echo -e "${BOLD}[4/7] Docker context & version${NC}"
docker version --format '  Server: {{.Server.Version}}  Client: {{.Client.Version}}' 2>/dev/null || echo -e "  ${YELLOW}Could not get version${NC}"
echo ""
echo "  Contexts:"
docker context ls 2>/dev/null | head -5 | sed 's/^/    /'

# ── Step 5: Container state ─────────────────────────────────────
echo ""
echo -e "${BOLD}[5/7] Container state${NC}"

PGAGE_STATUS=$(docker ps -a --filter name=pgage --format '{{.Status}}' 2>/dev/null)
if [ -z "$PGAGE_STATUS" ]; then
    echo -e "  ${YELLOW}pgage container does not exist — will create${NC}"
    NEED_CREATE=true
elif echo "$PGAGE_STATUS" | grep -q "Up"; then
    echo -e "  ${GREEN}pgage: $PGAGE_STATUS${NC}"
    NEED_CREATE=false
else
    echo -e "  ${YELLOW}pgage: $PGAGE_STATUS (not running)${NC}"
    NEED_CREATE=false
fi

# Show all cortex-related containers
echo ""
echo "  All containers:"
docker ps -a --filter name=pgage --filter name=age --filter name=cortex \
    --format '    {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo "    (none)"

# ── Step 6: Start/restart PostgreSQL ────────────────────────────
echo ""
echo -e "${BOLD}[6/7] Ensuring PostgreSQL is running${NC}"

if [ "$NEED_CREATE" = true ] || ! echo "$PGAGE_STATUS" | grep -q "Up"; then
    echo "  Starting docker compose..."
    docker compose -f docker-compose.local.yaml up -d 2>&1 | sed 's/^/    /'

    echo "  Waiting for PostgreSQL to accept connections..."
    for i in $(seq 1 20); do
        if docker exec pgage pg_isready -U postgres > /dev/null 2>&1; then
            echo -e "  ${GREEN}PostgreSQL is ready!${NC}"
            break
        fi
        if [ "$i" -eq 20 ]; then
            echo -e "  ${RED}PostgreSQL didn't start after 40s${NC}"
            echo ""
            echo "  Container logs (last 20 lines):"
            docker logs pgage --tail 20 2>&1 | sed 's/^/    /'
            exit 1
        fi
        sleep 2
    done
else
    echo -e "  ${GREEN}Already running${NC}"
fi

# Verify port mapping
echo ""
echo "  Port mapping:"
docker port pgage 2>/dev/null | sed 's/^/    /'

# ── Step 7: Test connectivity from host ─────────────────────────
echo ""
echo -e "${BOLD}[7/7] Testing host → PostgreSQL connectivity${NC}"

# Load .env
if [ -f .env ]; then
    PG_HOST=$(grep POSTGRES_HOST .env | cut -d= -f2)
    PG_PORT=$(grep POSTGRES_PORT .env | cut -d= -f2)
    PG_USER=$(grep POSTGRES_USER .env | cut -d= -f2)
    PG_DB=$(grep POSTGRES_DB .env | head -1 | cut -d= -f2)
    echo "  .env: host=$PG_HOST port=$PG_PORT user=$PG_USER db=$PG_DB"
else
    echo -e "  ${RED}.env not found${NC}"
    PG_HOST="127.0.0.1"
    PG_PORT="5433"
    PG_USER="postgres"
    PG_DB="postgres"
fi

# Test with psql inside container
echo ""
echo "  Testing inside container:"
if docker exec pgage psql -U postgres -c "SELECT 1 AS ok;" > /dev/null 2>&1; then
    echo -e "    ${GREEN}psql inside container: OK${NC}"
else
    echo -e "    ${RED}psql inside container: FAILED${NC}"
fi

# Test from host via Python
echo ""
echo "  Testing from host (Python psycopg2):"
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(host='$PG_HOST', port=$PG_PORT, user='$PG_USER', dbname='$PG_DB')
    cur = conn.cursor()
    cur.execute('SELECT 1')
    print('    Host → PostgreSQL ($PG_HOST:$PG_PORT): OK')
    conn.close()
except Exception as e:
    print(f'    Host → PostgreSQL ($PG_HOST:$PG_PORT): FAILED — {e}')
" 2>&1

# Check pgvector data
echo ""
echo "  Checking pgvector embeddings:"
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(host='$PG_HOST', port=$PG_PORT, user='$PG_USER', dbname='$PG_DB')
    cur = conn.cursor()
    cur.execute('SELECT count(*) FROM field_embeddings')
    count = cur.fetchone()[0]
    print(f'    field_embeddings: {count} rows')
    if count == 0:
        print('    WARNING: No embeddings! Run: python scripts/load_lookml_to_pgvector.py')
    else:
        print('    Embeddings intact — your data is safe.')
    conn.close()
except Exception as e:
    print(f'    Could not check embeddings: {e}')
" 2>&1

# ── Summary ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Summary${NC}"
echo -e "${BOLD}============================================================${NC}"
echo -e "  DOCKER_HOST: unix://$WORKING_SOCKET"
echo -e "  PostgreSQL:  $PG_HOST:$PG_PORT"
echo -e "  Persisted:   ~/.zshrc (open new terminal or run: source ~/.zshrc)"
echo ""
echo -e "  ${GREEN}Ready to run:${NC}"
echo -e "    python scripts/cortex_chat.py"
echo ""
