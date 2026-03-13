# PR Review: `scripts/load_lookml_to_pgvector.py`

**Reviewer:** Saheb (Staff Engineer)
**Date:** 2026-03-12
**Verdict:** Changes Requested

---

## Summary

This 585-line script is the full LookML-to-pgvector ingestion pipeline: it regex-parses `.lkml` files, generates embeddings via SafeChain, and upserts records into a `field_embeddings` table with HNSW indexing. Architecture impact is **high** -- this is the sole data source for the vector retrieval path that the entire Cortex query pipeline depends on, and it contains multiple runtime-crashing bugs, a security issue, and a dimension mismatch that would silently produce garbage search results.

---

## Critical Issues

### 1. [BLOCKING] Line 123 -- Reference to undefined variable `e` in non-exception branch

```python
# Line 119-124
if record.embedding and len(record.embedding) > 0:
    success_count += 1
else:
    error_count += 1
    logger.error("... error=%s", idx, len(records), record.field_key, str(e))  # <-- `e` is not defined here
    record.embedding = None
```

The `else` branch (embedding returned empty/falsy but no exception raised) references `str(e)` -- but `e` is only defined in the `except Exception as e` block below. This is a `NameError` that will crash the entire embedding pipeline the first time the SafeChain model returns an empty embedding vector. Since this is the batch embedding path, one bad record kills the whole ingestion run.

**Fix:** Remove `str(e)` or replace with a descriptive message:
```python
else:
    error_count += 1
    logger.error("[%d/%d] Empty embedding returned for field_key=%s", idx, len(records), record.field_key)
    record.embedding = None
```

---

### 2. [BLOCKING] Lines 234-240 -- `SQL_RETRIEVE_TOP_K_BY_DISTANCE` uses named params but `exec_driver_sql` expects positional `%s`

The SQL constant in `config/constants.py:95-101` uses SQLAlchemy-style named parameters (`:embedding`, `:limit`):

```sql
ORDER BY embedding <=> :embedding
LIMIT :limit;
```

But `retrieve_records` calls `conn.exec_driver_sql()` at line 237, which is a raw DBAPI call expecting `%s` positional placeholders. This will raise a `ProgrammingError` at runtime -- vector retrieval is completely broken.

**Fix:** Either switch to `conn.execute(text(SQL_RETRIEVE_TOP_K_BY_DISTANCE).bindparams(...))` (matching how `src/retrieval/vector.py` does it at line 254), or change the SQL constant to use `%s` placeholders and keep `exec_driver_sql`. Given that the downstream consumer (`vector.py`) already uses `text().bindparams()`, align on that pattern:

```python
def retrieve_records(self, query_embed: list[float], k: int = 5):
    embedding_literal = "[" + ", ".join(str(x) for x in query_embed) + "]"
    with self.get_engine().connect() as conn:
        results = conn.execute(
            text(SQL_RETRIEVE_TOP_K_BY_DISTANCE).bindparams(
                embedding=embedding_literal,
                limit=k,
            )
        ).fetchall()
    return results
```

---

### 3. [BLOCKING] Line 150 -- Password exposed in `lru_cache`-d connection string

```python
@lru_cache(maxsize=1)
def get_connection_string(cls):
    return f"postgresql+psycopg2://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.DBNAME}"
```

Two problems. First, the password is interpolated directly into the URL string without URL-encoding. If the password contains `@`, `/`, `%`, or `#` characters, the connection URL will be malformed. Second, this cached string with plaintext credentials persists in memory for the process lifetime and will appear in any stack trace, `repr()`, or debug dump. The `get_engine()` method at line 153 already uses `URL.create()` which handles escaping properly -- this `get_connection_string` method is dead code but is a credential exposure risk if anyone ever calls it.

**Fix:** Delete `get_connection_string` entirely. It is unused (the `get_engine` method correctly uses `URL.create`). If a connection string is needed elsewhere, derive it from the `URL` object which handles escaping.

---

### 4. [BLOCKING] VECTOR(1024) vs 768-dimension embedding mismatch

`config/constants.py:39` declares the table column as `VECTOR(1024)`:
```sql
embedding VECTOR(1024),
```

But `config/retrieval.yaml:15` configures the embedding model as `embedding_dim: 768`, and the design docs reference 768-dimensional vectors (`text-embedding-005`). If the BGE model configured in SafeChain produces 768-dim vectors, pgvector will reject every insert with a dimension mismatch error. If it produces 1024-dim vectors, then the retrieval config is wrong and cosine similarity scores will be meaningless.

**Fix:** Verify the actual output dimension of the SafeChain BGE model (model index `'2'`). Then make `constants.py` and `retrieval.yaml` agree. If BGE outputs 768:
```sql
embedding VECTOR(768),
```

---

### 5. [BLOCKING] Line 307 -- `__iter__` calls nonexistent method `_get_records_for_docker`

```python
def __iter__(self):
    return iter(self._get_records_for_docker())
```

The method is named `get_records_for_docker` (no leading underscore) at line 309. This `__iter__` call will raise `AttributeError` at runtime.

**Fix:**
```python
def __iter__(self):
    return iter(self.get_records_for_docker())
```

---

### 6. [BLOCKING] Line 572 -- `parser` variable used before definition in `pipeline` mode

```python
if args.mode == "pipeline":
    pg_ops = PostgresOperations()
    pg_ops.create_table()
    pg_ops.create_index()
    records = parser.get_records_for_docker(include_embeddings=True)  # <-- `parser` is undefined
```

The `parser` variable is only created inside the `if args.mode == "parse"` and `if args.mode == "embed"` branches. The `pipeline` branch references it without ever constructing a `LookMLParser`. This is an `UnboundLocalError` -- the pipeline mode (the most important mode) is completely broken.

**Fix:**
```python
if args.mode == "pipeline":
    parser = LookMLParser(model_path=model_path, views_dir=views_dir)
    pg_ops = PostgresOperations()
    ...
```

---

## Major Issues

### 7. [IMPORTANT] Lines 139-167 -- Duplicated `PostgresConfig` diverges from canonical `postgres_age_client.py`

`PostgresConfig` reimplements engine creation logic that already exists in `src/connectors/postgres_age_client.py`. The two implementations have a subtle divergence: `postgres_age_client.py` reads `POSTGRES_DB` (line 48) while `constants.py` reads `POSTGRES_DBNAME` (line 28). The `.env.example` provides both (`POSTGRES_DB=postgres` and `POSTGRES_DBNAME=postgres`), but if someone only sets one, the script and the rest of the codebase will connect to different databases.

Additionally, `postgres_age_client.get_engine()` is `@lru_cache`-d (singleton), handles SSL mode, and wraps errors cleanly. `PostgresConfig.get_engine()` creates a new engine on every call (no caching), which means `PostgresOperations` methods like `wait_for_postgres` (20 retries x `get_engine()`) and `ingest_records` each create a fresh connection pool -- that is a connection pool leak under repeated use.

**Fix:** Delete `PostgresConfig` and import `get_engine` from `src.connectors.postgres_age_client`:
```python
from src.connectors.postgres_age_client import get_engine

class PostgresOperations:
    def get_engine(self) -> Engine:
        return get_engine()
```

---

### 8. [IMPORTANT] Lines 202-232 -- Record-by-record upsert without batching

`ingest_records` issues one `exec_driver_sql` call per record inside a single transaction. For the current ~41 fields this is tolerable, but as the LookML model grows to 100+ tables (the stated target), this becomes painfully slow. More critically, if any single record fails mid-loop, the entire transaction rolls back and you lose all progress with no indication of which record caused the failure.

**Fix:** Use `executemany` or batch inserts, and add per-record error handling:
```python
def ingest_records(self, records: list[FieldEmbeddingRecord]):
    valid_records = [r for r in records if r.embedding is not None]
    params = [self._record_to_tuple(r) for r in valid_records]
    with self.get_engine().begin() as conn:
        conn.exec_driver_sql(SQL_UPSERT_FIELD_EMBEDDING_RECORD, params)  # executemany
    logger.info("Inserted/updated %d records", len(params))
```

---

### 9. [IMPORTANT] Lines 246-257 -- `verify()` method has logic error with `SQL_SAMPLE_FIELD_EMBEDDINGS`

```python
count_row = conn.exec_driver_sql(SQL_SAMPLE_FIELD_EMBEDDINGS).fetchone()
count = int(count_row[0]) if count_row else 0
```

`SQL_SAMPLE_FIELD_EMBEDDINGS` is `SELECT id, field_key, content, ... LIMIT 5` -- it returns data rows, not a count. `count_row[0]` is the `id` column of the first row, not a count. This silently overwrites the actual count with a record ID, producing misleading verification output.

**Fix:** Remove the redundant re-assignment or use a separate count query:
```python
if count > 0:
    with self.get_engine().connect() as conn:
        summary["sample"] = conn.exec_driver_sql(SQL_SAMPLE_FIELD_EMBEDDINGS).fetchall()
        summary["self_match"] = conn.exec_driver_sql(SQL_VERIFY_VECTOR_SELF_MATCH).fetchall()
```

---

### 10. [IMPORTANT] Lines 224 -- Tags type mismatch: Python `list[str]` vs SQL `TEXT`

The `FieldEmbeddingRecord.tags` field is `list[str]`, but `constants.py:49` defines the column as `tags TEXT` (not `TEXT[]`). When psycopg2 tries to bind a Python list to a `TEXT` column via `exec_driver_sql`, it will either fail with a type error or produce a stringified `"['tag1', 'tag2']"` representation that cannot be properly queried later. The ADR at `adr/004-semantic-layer-representation.md:116` specifies `TEXT[]` for tags.

**Fix:** Either change the DDL to `tags TEXT[]` to match the ADR and the Python type, or serialize tags to a JSON string before insertion. The former is correct:
```sql
tags TEXT[],
```

---

### 11. [IMPORTANT] Line 395 -- `field_type` incorrectly set to `"view"` for dimensions

```python
field_type=field.field_type if field.field_type == "measure" else "view",
```

For dimensions, `field_type` is set to `"view"` instead of `"dimension"`. This means the downstream consumer (`src/retrieval/vector.py`) which reads `field_type` and `measure_type` to distinguish dimensions from measures will misclassify every dimension as a "view" type. This corrupts the entity resolution pipeline.

**Fix:**
```python
field_type=field.field_type,  # "dimension" or "measure"
measure_type=field.data_type if field.field_type == "measure" else None,
```

---

### 12. [IMPORTANT] Line 527 -- `logging.basicConfig` format string has two bugs

```python
logging.basicConfig(level=logging.INFO, format="%(levelnames)s %(name)s | Query: {args.query} | Top-K: {args.top_k}")
```

(a) `%(levelnames)s` should be `%(levelname)s` -- the trailing `s` makes it an invalid log record attribute, which causes a `KeyError` on every log emission. (b) The f-string interpolation `{args.query}` is inside a regular string (no `f` prefix), so it will literally print `{args.query}` instead of the actual query value.

**Fix:**
```python
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
```

---

### 13. [IMPORTANT] Line 80 -- Module-level side effect: `_bootstrap_environment()` runs on import

`_bootstrap_environment()` is called at module top-level (line 80), which means importing this module from anywhere (e.g., `docker_spin.py` imports `LookMLParser` and `PostgresOperations`) triggers `.env` loading and potentially overwrites `CONFIG_PATH`. This is fragile in test environments and makes the module hard to import safely.

**Fix:** Move the call into `_demo_run()` or guard it:
```python
if __name__ == "__main__":
    _bootstrap_environment()
    _demo_run()
```

---

## Minor Issues

- **Line 180:** `wait_for_postgres` creates a new engine on each retry. After fixing issue #7, the cached engine from `postgres_age_client` will solve this, but also consider `connect_args={"connect_timeout": 5}` to fail fast.

- **Line 468:** The `_iter_blocks` regex does not handle LookML names with `+` prefix (e.g., `view: +extension_name {`). This will silently skip any LookML refinements.

- **Lines 499:** `_extract_quoted_value` uses `re.S` (DOTALL) which makes `.*?` match across newlines. If a LookML file has a missing closing quote, this regex will greedily consume content across multiple fields.

- **Line 203:** `"Starting ingestion: %d records with %d records"` -- the same count is printed twice. Copy-paste artifact.

- **Line 576:** `from src.retrieval.vector import EntityExtractor` is imported but never used. Dead import.

- **Line 313:** `record.created_at = datetime.datetime.now(datetime.timezone.utc)` sets the same timestamp for every record in the batch. Consider setting it once before the loop.

- The `SQL_VERIFY_VECTOR_SELF_MATCH` query (`ORDER BY embedding <=> embedding`) computes self-distance which is always 0 for every row. This does not verify anything meaningful.

---

## Positive Notes

- The `FieldEmbeddingRecord` and `FieldInfo` dataclasses are well-structured -- proper use of `dataclass` with typed fields and sensible defaults.
- The LookML parser's `_find_matching_brace` correctly handles nested braces with depth counting rather than regex. Good defensive coding.
- Using `exec_driver_sql` with `%s` positional params for the upsert avoids SQL injection by design.
- The three-mode CLI (`parse`, `embed`, `db`, `pipeline`) is a good developer experience pattern -- debug each stage independently.
- Good use of `ON CONFLICT (field_key) DO UPDATE` for upsert semantics -- makes the ingestion pipeline idempotent.

---
