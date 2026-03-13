# PR Review: `src/retrieval/graph_search.py`

**Reviewer:** Saheb (Staff Engineer)
**Date:** 2026-03-12
**Verdict:** Changes Requested

## PR Summary

- **What this file does:** Implements graph search via PostgreSQL AGE for structural validation -- checking that LookML fields can actually be queried together through the same explore. This is the "structural validation gate" described in the architecture docs as "the single most important quality check in the system."
- **Architecture impact:** HIGH. This module is a critical dependency for both `orchestrator.py` (which calls `validate_fields_in_explore` and `get_partition_filters`) and `pipeline.py` (which calls `find_explores_for_view`). It is currently a 68-line stub that implements 1 of the 3+ functions the system requires.

---

## Blocking Issues

### [BLOCKING] graph_search.py:50-51 -- SQL injection via inadequate escaping in Cypher query

**What:** The `escaped_view` and `escaped_graph` values are constructed by replacing single quotes (`'` to `''`), then interpolated into an f-string that builds both a SQL outer shell AND a Cypher inner query. This escaping is insufficient for two reasons:

1. **The `graph_name` parameter goes into a SQL identifier position** (`'{escaped_graph}'::name`). SQL identifier injection requires different escaping than value escaping. A `graph_name` like `lookml_schema'; DROP TABLE explore_field_index; --` would break out of the AGE function call. The `''` replacement does not prevent semicolon injection or other SQL metacharacters.

2. **The `view_name` parameter is inside a Cypher `$$`-delimited block.** Within `$$` blocks, PostgreSQL does not interpret `''` as an escaped quote -- `$$` blocks are literal strings. The `''` escaping is applying SQL escaping rules to a context that uses Cypher escaping rules (which are different: Cypher uses backslash escaping). A crafted `view_name` containing `'})` followed by Cypher injection could alter the query structure.

**Why this matters:** This is a financial services application at American Express with PII data in the graph. Even if `view_name` originates from internal vector search results today, defensive coding is required because:
- The function signature is public with a `str` parameter -- any caller can pass arbitrary input.
- Internal data sources can be compromised (e.g., a poisoned LookML field name loaded by `load_lookml_to_age.py`).
- At Amex, this would fail a security review and block deployment.

**How to fix:**

```python
import re

_IDENTIFIER_RE = re.compile(r'^[a-z_][a-z0-9_]*$', re.IGNORECASE)

def _validate_identifier(value: str, label: str) -> str:
    """Reject anything that isn't a simple alphanumeric identifier."""
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid {label}: {value!r}. Must match [a-z_][a-z0-9_]*")
    return value

def find_explores_for_view(view_name: str, graph_name: str = "lookml_schema") -> list[dict]:
    safe_view = _validate_identifier(view_name, "view_name")
    safe_graph = _validate_identifier(graph_name, "graph_name")
    # ... then use safe_view / safe_graph in the query
```

Allowlisting is the only reliable defense when you cannot use parameterized queries (and AGE's `ag_catalog.cypher()` does not support Cypher-level parameterization through SQL bind variables).

---

### [BLOCKING] graph_search.py -- Missing functions required by downstream consumers

**What:** The orchestrator (`orchestrator.py:403`) calls `graph_search.validate_fields_in_explore(conn, candidate_fields)` and (`orchestrator.py:592`) calls `graph_search.get_partition_filters(conn, explore)`. Neither function exists in this file. The docstring (lines 1-30) promises four capabilities:

1. "Can these fields actually be queried together?" -- **Not implemented**
2. "What explore contains BOTH a spend measure AND a merchant dimension?" -- **Not implemented**
3. "What's the join path between these two views?" -- **Not implemented**
4. "What partition filters are required?" -- **Not implemented**

Only `find_explores_for_view` is implemented, which answers a simpler question ("which explores connect to this view?"). That function IS used by `pipeline.py`, but the two functions the new orchestrator needs do not exist.

**Why this matters:** The orchestrator is the intended production path. Without `validate_fields_in_explore` and `get_partition_filters`, calling `orchestrator.retrieve()` will throw `AttributeError` at runtime. The structural validation gate -- described in the docstring as "the single most important quality check" -- is non-functional.

**How to fix:** Implement both functions. Here are signatures that match the orchestrator's expectations:

```python
def validate_fields_in_explore(
    conn,
    candidate_fields: list[str],
    graph_name: str = "lookml_schema",
) -> list[dict]:
    """Check which explores contain ALL candidate fields.
    
    Returns list of dicts with keys: explore, model, coverage, base_view_match.
    Uses hybrid table explore_field_index for fast lookup,
    falls back to AGE Cypher if hybrid table is empty.
    """
    # Hot path: query explore_field_index relational table
    # Fallback: Cypher MATCH (e:Explore)-[:CONTAINS|JOINS*1..4]->(v:View)-[:HAS_DIMENSION|HAS_MEASURE]->(f {name: ...})
    ...

def get_partition_filters(
    conn,
    explore_name: str,
    graph_name: str = "lookml_schema",
) -> list[dict]:
    """Return required partition filters for an explore.
    
    Returns list of dicts with key: filter_field.
    Uses hybrid table explore_partition_filters for fast lookup.
    """
    ...
```

The hybrid tables (`explore_field_index`, `explore_partition_filters`) already exist in the schema setup script -- use them for the hot path. This avoids Cypher overhead for the most common queries.

---

### [BLOCKING] graph_search.py:53,66-67 -- Missing transaction management (no commit/rollback)

**What:** The function opens a connection via `engine.connect()` and executes queries but never calls `conn.commit()` or handles `conn.rollback()`. With SQLAlchemy 2.0 (`future=True` is set on the engine in `postgres_age_client.py:95`), connections use "begin-on-first-use" autobegin behavior. The `LOAD 'age'` and `SET search_path` statements from `init_age_session` begin a transaction. If the Cypher query fails, the transaction is left in an aborted state, and the connection is returned to the pool in a broken state.

**Why this matters:** The next caller that gets this connection from the pool will get `InFailedSqlTransaction` errors, causing cascading failures. This is especially dangerous with `pool_pre_ping=True` -- pre-ping checks don't always detect aborted transactions, only closed connections.

**How to fix:**

```python
def find_explores_for_view(view_name: str, graph_name: str = "lookml_schema") -> list[dict]:
    safe_view = _validate_identifier(view_name, "view_name")
    safe_graph = _validate_identifier(graph_name, "graph_name")
    
    engine = get_engine()
    with engine.connect() as conn:
        try:
            init_age_session(conn)
            sql = f"""..."""
            result = conn.execute(text(sql))
            rows = [row[0] for row in result.fetchall()]
            conn.commit()  # Explicitly close the transaction
            return rows
        except Exception:
            conn.rollback()
            raise
```

Or even simpler, use `engine.begin()` which auto-commits on success and auto-rolls-back on exception:

```python
with engine.begin() as conn:
    init_age_session(conn)
    ...
```

---

## Important Issues

### [IMPORTANT] graph_search.py:56-63 -- Cypher UNION semantics may be incorrect for AGE

**What:** The query uses `UNION` between two `MATCH ... RETURN` clauses inside a single `ag_catalog.cypher()` call. Apache AGE's Cypher support is a subset of openCypher. Not all AGE versions support `UNION` inside `cypher()`. If unsupported, this query will fail silently or throw an opaque error.

Additionally, even if `UNION` is supported, both branches return `DISTINCT e` separately before the union, which is redundant -- `UNION` (without `ALL`) already deduplicates.

**Why this matters:** This is the only implemented function in the module. If it doesn't work on your AGE version, you have zero graph search capability.

**How to fix:** Use a single `MATCH` with a variable-length relationship pattern:

```python
sql = f"""
SELECT * FROM ag_catalog.cypher('{safe_graph}'::name, $$
    MATCH (e:Explore)-[:BASE_VIEW|JOINS]->(v:View {{name: '{safe_view}'}})
    RETURN DISTINCT e
$$::cstring) AS (explore agtype);
"""
```

This is simpler, avoids the UNION compatibility question, and is semantically identical. Test this against your specific AGE version (1.3.x vs 1.5.x have different Cypher support).

---

### [IMPORTANT] graph_search.py:67 -- Return type is `list[dict]` but actually returns `list[agtype]`

**What:** The type hint says `list[dict]` but `row[0]` from an AGE Cypher query returns `agtype` objects, not Python dicts. The caller in `pipeline.py:192` (`_get_explore_names`) handles this correctly by parsing the raw AGE string format (`{...}::vertex`), but the caller in `orchestrator.py:408-415` treats the return value as `list[dict]` and calls `.get("explore")`, `.get("model")`, etc. -- which would fail on raw `agtype` values.

**Why this matters:** The two callers have incompatible expectations for the return type. One of them will crash at runtime.

**How to fix:** Parse AGE agtype results into proper Python dicts inside `graph_search.py` so callers get a clean interface:

```python
import json

def _parse_age_vertex(raw) -> dict:
    """Convert AGE agtype vertex to a Python dict."""
    s = str(raw)
    if s.endswith("::vertex"):
        s = s[:-len("::vertex")]
    try:
        parsed = json.loads(s)
        return parsed.get("properties", parsed)
    except (json.JSONDecodeError, AttributeError):
        return {"raw": s}

# In find_explores_for_view:
return [_parse_age_vertex(row[0]) for row in result.fetchall()]
```

This keeps the parsing logic in one place instead of forcing every caller to know AGE's wire format.

---

### [IMPORTANT] graph_search.py:47 -- Creating a new engine per call instead of accepting a connection

**What:** `find_explores_for_view` calls `get_engine()` and opens its own connection. But `validate_fields_in_explore` (the function the orchestrator expects) takes a `conn` parameter -- the orchestrator passes `self.pg_conn` so that vector search and graph search share the same connection/transaction.

The existing `find_explores_for_view` creates a separate connection, which means:
1. It cannot participate in the same transaction as vector search.
2. It creates unnecessary connection pool pressure.
3. It's inconsistent with the connection-passing pattern used throughout the retrieval system.

**Why this matters:** The orchestrator design (ADR-004 per the docstring) explicitly shares a connection across retrieval channels so that AGE session state (`LOAD 'age'`, `SET search_path`) is initialized once. Opening a new connection per call means re-initializing AGE each time and doubling pool usage.

**How to fix:** Accept an optional connection parameter, fall back to creating one if not provided:

```python
def find_explores_for_view(
    view_name: str,
    conn=None,
    graph_name: str = "lookml_schema",
) -> list[dict]:
    owns_conn = conn is None
    if owns_conn:
        engine = get_engine()
        conn = engine.connect()
        init_age_session(conn)
    try:
        # ... query logic ...
    finally:
        if owns_conn:
            conn.close()
```

---

### [IMPORTANT] graph_search.py -- No logging anywhere in the module

**What:** Every other retrieval module (`vector.py`, `orchestrator.py`, `fusion.py`, `pipeline.py`, `fewshot.py`) uses `logging.getLogger(__name__)`. This module has zero logging. No query timing, no result counts, no error context.

**Why this matters:** When the structural validation gate misbehaves in production (and it will -- this is the module described as "75% of your error budget"), you will have no observability into what Cypher query was executed, how long it took, or why it returned zero results. You will be debugging blind.

**How to fix:**

```python
import logging
import time

logger = logging.getLogger(__name__)

# Inside the function:
logger.debug("Graph query: find explores for view=%s graph=%s", view_name, graph_name)
t0 = time.perf_counter()
result = conn.execute(text(sql))
rows = [_parse_age_vertex(row[0]) for row in result.fetchall()]
logger.info(
    "find_explores_for_view(%s) returned %d explores in %.3fs",
    view_name, len(rows), time.perf_counter() - t0,
)
```

---

## Suggestions

### [SUGGESTION] graph_search.py -- Add the hybrid table hot-path strategy described in the docstring

The docstring (lines 20-29) describes a three-tier strategy: (1) hybrid relational tables for hot-path lookups, (2) graph index for partition filters, (3) pure graph fallback. The implementation only uses pure graph. The hybrid tables (`explore_field_index`, `explore_partition_filters`) are already created by the schema setup script. Using them would be a significant performance improvement -- a relational `WHERE field_name IN (...)` against an indexed table is orders of magnitude faster than Cypher traversal for the common case.

```python
def validate_fields_in_explore(conn, candidate_fields: list[str], graph_name: str = "lookml_schema") -> list[dict]:
    """Hot path: check explore_field_index. Fallback: Cypher."""
    placeholders = ", ".join(f":f{i}" for i in range(len(candidate_fields)))
    sql = text(f"""
        SELECT explore_name, COUNT(DISTINCT field_name) as coverage,
               bool_or(is_partition_key) as has_partition
        FROM explore_field_index
        WHERE field_name IN ({placeholders})
          AND NOT is_hidden
        GROUP BY explore_name
        ORDER BY coverage DESC
    """).bindparams(**{f"f{i}": f for i, f in enumerate(candidate_fields)})
    
    result = conn.execute(sql)
    return [
        {"explore": row.explore_name, "coverage": row.coverage, ...}
        for row in result.fetchall()
    ]
```

### [SUGGESTION] graph_search.py -- Add retry logic for transient AGE failures

AGE can throw transient errors during graph traversals, especially under concurrent load (lock contention on the vertex/edge tables). A simple single-retry with a short backoff would prevent unnecessary `no_match` results from reaching the user.

### [SUGGESTION] graph_search.py -- Consider connection timeout

The Cypher query has no timeout. On a large graph with pathological traversal patterns, it could run indefinitely. Consider adding `statement_timeout` for safety:

```python
conn.execute(text("SET statement_timeout = '5s'"))
```

---

## What's Good

### [PRAISE] The docstring (lines 1-30) is excellent

This is one of the best module docstrings I've seen. It explains the "why" (not just the "what"), describes the graph schema, outlines the implementation strategy with three tiers, and lists prerequisites. This is the kind of documentation that saves hours of onboarding time. The clear articulation of "questions vector search CANNOT answer" is exactly the framing that helps the team understand why this module exists.

### [PRAISE] Correct use of `$$`-delimited strings for Cypher

Using dollar-quoting (`$$...$$`) for the Cypher block is the correct pattern for AGE. It avoids the nested-quoting nightmare of wrapping Cypher in SQL strings. The cast to `::cstring` is also correct.

### [PRAISE] The graph schema design (Model -> Explore -> View -> Dimension/Measure) is sound

The six node types and six edge types in the docstring map cleanly to LookML's actual structure. The distinction between `BASE_VIEW` and `JOINS` edges is critical for the base-view-priority signal in the orchestrator, and having it encoded in the graph is the right call.

---