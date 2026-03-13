# PR Review: Configuration & Infrastructure Files

**Reviewer:** Saheb (Staff Engineer)
**Date:** 2026-03-12
**Verdict:** Changes Requested

**Files:** `config/constants.py`, `config/config.yml`, `docker-compose.yaml`, `docker_spin.py`, `Dockerfile`, `.env.example`

---

## Summary

These files establish the foundational configuration layer for the Cortex pipeline: PostgreSQL connection management, SQL constants for pgvector operations, SafeChain/IDaaS model configuration, and Docker orchestration for AGE+pgvector. The infrastructure design is sound in intent, but there are multiple correctness bugs that will cause runtime failures, a security configuration that must not reach any shared environment, and critical dependency gaps that will break fresh installs.

---

## Critical Issues

### 1. [BLOCKING] `config/constants.py`:95-101 vs `scripts/load_lookml_to_pgvector.py`:237-240 -- Mixed SQL parameter styles will cause runtime failure

`SQL_RETRIEVE_TOP_K_BY_DISTANCE` uses named parameters (`:embedding`, `:limit`) which is the SQLAlchemy `text()` bind-parameter style. But `load_lookml_to_pgvector.py:237` calls it via `conn.exec_driver_sql()`, which bypasses SQLAlchemy's parameter binding and sends the query directly to the DB driver (psycopg2), which expects `%s` positional placeholders or `%(name)s` pyformat placeholders. This query will fail at runtime with a `psycopg2.ProgrammingError`.

The same SQL constant `SQL_UPSERT_FIELD_EMBEDDING_RECORD` correctly uses `%s` placeholders and is correctly called with `exec_driver_sql` -- so the pattern is understood, just not applied consistently.

**Fix:** Either change the SQL to use `%s` placeholders and keep `exec_driver_sql`, or switch the call site to `conn.execute(text(SQL_...).bindparams(...))`. Recommend the latter for consistency with how `vector.py` uses `SQL_SEARCH_SIMILAR_FIELDS`.

---

### 2. [BLOCKING] `docker-compose.yaml`:10 -- `POSTGRES_HOST_AUTH_METHOD=trust` allows unauthenticated access to the database

This disables all password authentication for PostgreSQL. Any process on the Docker network (or on `localhost:5432` from the host) can connect as any user without credentials. Combined with the port binding to `0.0.0.0:5432`, any machine on the network can connect. With `restart: always`, this database will silently accept connections from anyone on the corporate network whenever the engineer's laptop is on VPN.

**Fix:** Remove trust auth and set a password. The `.env.example` already defines `POSTGRES_PASSWORD=postgres`, so use it:

```yaml
environment:
  - POSTGRES_USER=postgres
  - POSTGRES_DB=postgres
  - POSTGRES_PASSWORD=postgres
# Remove POSTGRES_HOST_AUTH_METHOD=trust entirely
ports:
  - "127.0.0.1:5432:5432"   # bind to localhost only
```

---

### 3. [BLOCKING] Missing `sqlalchemy` and `psycopg2-binary` from project dependencies

The `pyproject.toml` does not declare `sqlalchemy` or `psycopg2-binary` (or `psycopg`) as dependencies. Both `load_lookml_to_pgvector.py` and `postgres_age_client.py` import from `sqlalchemy` and use the `psycopg2` driver string. A fresh `pip install -e .` will fail immediately.

**Fix:** Add to `pyproject.toml`:

```toml
dependencies = [
    "sqlalchemy>=2.0.0",
    "psycopg2-binary>=2.9.9",
    "pgvector>=0.3.0",
]
```

Note: The prior PR review at `docs/pr-reviews/postgres_age_client.md` already flagged the psycopg2 vs psycopg3 question. Decide which driver you want.

---

### 4. [BLOCKING] `config/constants.py`:112-117 -- `SQL_VERIFY_VECTOR_SELF_MATCH` computes self-distance, which is always 0

```sql
ORDER BY embedding <=> embedding
```

This computes the cosine distance of each row's embedding against *itself*, which is always 0. Every row ties at distance 0, so PostgreSQL returns arbitrary rows. This does not verify vector search correctness.

**Fix:** To actually verify vector search works, query with a known embedding and check that the expected field comes back first:

```sql
SELECT field_key, embedding <=> (SELECT embedding FROM field_embeddings LIMIT 1) AS distance
FROM field_embeddings
ORDER BY embedding <=> (SELECT embedding FROM field_embeddings LIMIT 1)
LIMIT 5;
```

---

## Major Issues

### 5. [IMPORTANT] `config/config.yml`:1-5 -- IDaaS endpoint URL and API scopes hardcoded in plain-text YAML

The file contains the full IDaaS token URL (`https://oneidentityapi-dev.aexp.com/...`) and detailed API scope paths. While the actual credentials (CIBIS keys) are in `.env`, the scope paths reveal internal API surface area. If this repo is ever shared beyond the immediate team (e.g., Accenture), these URLs expose the internal gateway structure.

**Fix:** Move the IDaaS URL to `.env` and reference it via env var substitution, or add a comment explicitly noting this is dev-only.

---

### 6. [IMPORTANT] `docker_spin.py`:43 -- Uses deprecated `docker-compose` (v1 CLI) instead of `docker compose` (v2 plugin)

`docker-compose` (hyphenated, standalone binary) was deprecated in July 2023 and has been EOL. Docker Desktop and modern Docker Engine only ship the `docker compose` plugin. Additionally, `run_cmd` on line 28 uses `docker compose` (no hyphen) while `start_with_compose` on line 43 uses `docker-compose` (with hyphen). This inconsistency means some commands succeed while others fail.

**Fix:**
```python
def start_with_compose(self):
    subprocess.run(["docker", "compose", "up", "-d"], check=True)
```

---

### 7. [IMPORTANT] `config/constants.py`:39 -- Embedding dimension hardcoded to 1024, potential mismatch with actual model

The table schema declares `VECTOR(1024)` which is correct for BGE-large-en. However, the CLAUDE.md context references `text-embedding-005` (768 dimensions). If anyone switches the embedding model without updating this schema, all inserts will fail with a dimension mismatch error.

**Fix:** Add a constant and a comment tying the dimension to the model:

```python
# BGE-large-en embedding dimension. If you change the embedding model,
# you MUST update this value AND recreate the field_embeddings table.
EMBEDDING_DIM = 1024
```

---

### 8. [IMPORTANT] `docker-compose.yaml`:16 -- Volume mounts to `/var/lib/postgresql` instead of `/var/lib/postgresql/data`

The standard PostgreSQL Docker image expects the data directory at `/var/lib/postgresql/data`. Mounting the volume at `/var/lib/postgresql` may interfere with the container's directory structure on some image variants.

**Fix:**
```yaml
volumes:
  - pgage-data:/var/lib/postgresql/data
```

---

### 9. [IMPORTANT] `.env.example`:17-18 -- Both `POSTGRES_DB` and `POSTGRES_DBNAME` defined, creating confusion

`constants.py` reads `POSTGRES_DBNAME`. `docker-compose.yaml` uses `POSTGRES_DB`. `postgres_age_client.py` reads `POSTGRES_DB` with fallback to `POSTGRES_DATABASE`. If someone sets only one, different parts of the codebase will connect to different databases (or crash).

**Fix:** Standardize on `POSTGRES_DB` (the Docker convention) everywhere. Update `constants.py` to match.

---

## Minor Issues

- `docker-compose.yaml` -- No health check on the `pgage` service. The `cortex-setup` and `ageviewer` services use `depends_on: pgage` but without a health check, they may start before PostgreSQL accepts connections.

- `docker_spin.py`:6 -- Imports `LookMLParser` and `PostgresOperations` at the top level but never uses them in `DockerManager`. These dead imports will cause import failures if `safechain` is not installed.

- `docker_spin.py`:27 -- `run_cmd` method has `-> None` return type but actually returns `result.stdout.strip()` (a string).

- `config/constants.py`:23 -- `DEFAULT_REQUIRED_LOOKER_MODELS` is defined but only referenced in a comment. Dead code if not used elsewhere.

- `Dockerfile`:7 -- `postgresql-18-pgvector` assumes PostgreSQL 18. If the AGE base image ships with a different PG major version, the `apt-get install` will fail.

- `config/config.yml`:36-37 -- MCP server configured with `http://localhost:5000/scp` (note: `scp`, not `mcp`). Verify this isn't a typo.

- `config/constants.py`:54-58 -- HNSW index parameters `m=16, ef_construction=64` are reasonable for small datasets (<100K rows). Document that these should be tuned if the field count grows beyond ~50K.

---

## Positive Notes

- `config/constants.py` -- Centralizing all SQL statements as constants is the right pattern. Makes SQL reviewable in one place and prevents inline SQL scattered across the codebase.
- `docker-compose.yaml` -- Clean service naming, proper use of named volumes and networks, and the `cortex-setup` service under a `tools` profile is thoughtful separation of one-time setup from always-running services.
- `.env.example` -- The explicit "NEVER commit .env to version control" header and proper `.gitignore` entry shows security awareness.
- `src/connectors/postgres_age_client.py` -- The env var alias pattern (`_require_env("POSTGRES_DB", "POSTGRES_DATABASE", "PGDATABASE")`) is production-grade thinking that should be adopted in `constants.py` too.

---
