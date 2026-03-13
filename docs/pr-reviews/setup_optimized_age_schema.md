# PR Review: `scripts/setup_optimized_age_schema.py`

**Reviewer:** Saheb (Staff Engineer)
**Date:** 2026-03-12
**Verdict:** Changes Requested

---

## Summary
- This script creates the Apache AGE graph schema (`lookml_schema`), property indexes on AGE internal tables, three hybrid relational tables (`explore_field_index`, `explore_partition_filters`, `business_term_index`), and a tsvector trigger for full-text search. It is intended to run once after PostgreSQL+AGE is installed.
- Architecture impact: **Medium** -- this defines the physical schema that the entire graph search and hybrid retrieval system depends on. Mistakes here ripple into every query downstream.

---

### Blocking Issues

**[BLOCKING] Line 110 -- Malformed WHERE clause produces invalid SQL for `idx_field_name`**

```python
f"""CREATE INDEX IF NOT EXISTS idx_field_name
    ON ({vertex_table}) (properties->>'name'::agtype)
    {_where_label_equals('Dimension')} OR {_where_label_equals('Measure')}""",
```

This generates: `WHERE label = 'Dimension' OR WHERE label = 'Measure'`. That is not valid SQL. Two `WHERE` keywords cannot appear in a single clause. The correct form is `WHERE label = 'Dimension' OR label = 'Measure'`, or use `WHERE label IN ('Dimension', 'Measure')`. As written, this index creation will **fail at runtime on every execution**. The error is silently swallowed by the `except` block on line 157-159, so the operator sees `x idx_field_name: <error>` but the script proceeds, leaving the schema missing a critical index for field name lookups.

**Fix:** Replace line 110 with something that uses the `_where_label_in` helper:
```python
(
    "idx_field_name",
    f"""CREATE INDEX IF NOT EXISTS idx_field_name
        ON ({vertex_table}) (properties->>'name'::agtype)
        {_where_label_in("'Dimension', 'Measure'", label_col)}""",
),
```
Or fix `_where_label_equals` to return only the predicate (not the `WHERE` keyword) and compose the clause manually.

---

**[BLOCKING] Lines 35-37 -- `create_graph` unconditionally drops then recreates the graph, destroying production data**

The docstring says "(idempotent)" but the behavior is destructive: it calls `drop_graph('lookml_schema', true)` and then `create_graph`. If someone re-runs this script against a database that already has LookML data loaded into the graph, **all graph data is destroyed**. Combined with the fact that `main()` calls this first and `create_hybrid_tables()` also does `DROP TABLE IF EXISTS ... CASCADE`, re-running this script wipes everything.

This is the opposite of idempotent. Idempotent means "running twice produces the same result as running once." This produces data loss on the second run.

**Why this matters:** The docstring on line 12 says "Empty database or willingness to drop existing 'lookml_schema' graph" but this is buried in a file-level comment. In a team of 6+ people, someone will run this in a shared environment and destroy data.

**Fix:** Add a `--force` / `--clean` CLI flag that defaults to off. Without it, attempt `create_graph` and handle the "already exists" case gracefully. With it, drop and recreate.
```python
import argparse

def create_graph(force: bool = False):
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("LOAD 'age'"))
        conn.execute(text('SET search_path = ag_catalog, "$user", public'))
        
        if force:
            try:
                conn.execute(text("SELECT drop_graph('lookml_schema', true)"))
                print("  Dropped existing graph")
            except Exception:
                conn.rollback()
        
        try:
            conn.execute(text("SELECT create_graph('lookml_schema')"))
            conn.commit()
            print("  Graph 'lookml_schema' created!")
        except Exception:
            conn.rollback()
            print("  Graph 'lookml_schema' already exists (use --force to recreate)")
```

---

**[BLOCKING] Lines 170-226 -- `DROP TABLE IF EXISTS ... CASCADE` followed by `CREATE TABLE IF NOT EXISTS` is both destructive AND contradictory**

Look at this pattern repeated three times:
```sql
DROP TABLE IF EXISTS explore_field_index CASCADE;
CREATE TABLE IF NOT EXISTS explore_field_index (...);
```

The `IF NOT EXISTS` on the `CREATE` is meaningless because you just dropped the table. More importantly, the `CASCADE` will drop any views, foreign keys, or other objects that depend on these tables. In a shared development database, this is a landmine.

And the indexes on lines 184-187 (`CREATE INDEX idx_efi_explore ...`) do NOT use `IF NOT EXISTS`, so if somehow the table survived the `DROP`, these would fail on re-run.

**Fix:** Either make it truly idempotent (use `CREATE TABLE IF NOT EXISTS` without the `DROP`, and `CREATE INDEX IF NOT EXISTS` on all indexes), or make it explicitly destructive with a CLI guard (same `--force` flag).

---

**[BLOCKING] Lines 85-88 -- `_where_label_in` is dead code with a latent injection surface**

```python
def _where_label_in(values: list, label_col: str) -> str:
    if label_col is None:
        return ""
    return f"WHERE {label_col} IN ({values})"
```

Two problems:
1. The type hint says `list` but the function just f-string interpolates it directly. If you pass a Python list like `['Dimension', 'Measure']`, the output is `WHERE label IN (['Dimension', 'Measure'])` which is invalid SQL (square brackets).
2. This function is never called anywhere. Line 110 uses `_where_label_equals` twice with `OR` instead of calling `_where_label_in`. Dead code that would also produce wrong output if used.

**Fix:** Either delete it (dead code) or fix it and use it for the `idx_field_name` case:
```python
def _where_label_in(values: list[str], label_col: str | None) -> str:
    if label_col is None:
        return ""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"WHERE {label_col} IN ({quoted})"
```

---

### Important Issues

**[IMPORTANT] Lines 186-187 -- Composite index `idx_efi_composite` duplicates the primary key**

```sql
PRIMARY KEY (explore_name, field_name)
...
CREATE INDEX idx_efi_composite ON explore_field_index(explore_name, field_name)
    WHERE NOT is_hidden;
```

The primary key already creates a unique B-tree index on `(explore_name, field_name)`. The partial index `idx_efi_composite` with `WHERE NOT is_hidden` is the only thing that makes it different, but this is worth calling out: you also have `idx_efi_explore` on `(explore_name)` alone, which is redundant because the PK index can serve prefix scans on `explore_name`. You are paying write amplification for 4 indexes (PK + 3 explicit) on a table that will be bulk-loaded.

**Fix:** Drop `idx_efi_explore` since the PK already covers `explore_name`-only lookups. Keep `idx_efi_composite` only if the `WHERE NOT is_hidden` partial filter is actually used in queries. Check `graph_search.py` and the retrieval layer.

---

**[IMPORTANT] Line 203 -- `field_name VARCHAR(20)` in `business_term_index` is almost certainly too short**

LookML field names follow the pattern `view_name.field_name`. At Amex with 8,000+ datasets, field names like `transaction_enriched.merchant_category_code` are 45+ characters. `VARCHAR(20)` will silently truncate or throw an error on insert, depending on PostgreSQL's configuration. Compare with `explore_field_index` which uses `VARCHAR(255)` for the same concept.

**Why this matters:** This will surface as a runtime error during `build_hybrid_indexes.py` when actual LookML field names are loaded, and it will be confusing to debug because the schema setup "succeeded."

**Fix:** Change to `VARCHAR(255)` to match the other tables, or better yet, use `TEXT` since PostgreSQL has no performance difference between `VARCHAR(n)` and `TEXT`.

---

**[IMPORTANT] Lines 214-221 -- The tsvector trigger ignores the `synonyms` column**

The trigger builds the tsvector from `canonical_term` (weight A) and `field_description` (weight B), but the `synonyms TEXT[]` column is not included. The whole point of the `business_term_index` table is to enable full-text search that matches synonyms. If a user searches for "spend" but the canonical term is "transaction_amount" with synonym "spend", this trigger won't match.

**Fix:**
```sql
CREATE OR REPLACE FUNCTION business_term_tsv_trigger() RETURNS trigger AS $$
BEGIN
    NEW.tsv :=
        setweight(to_tsvector('english', COALESCE(NEW.canonical_term, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(array_to_string(NEW.synonyms, ' '), '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.field_description, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Note: synonyms get weight 'A' because they are as important as the canonical term for matching purposes.

---

**[IMPORTANT] Lines 247-263 -- `verify_setup` does not check results, only that queries don't throw**

```python
result = conn.execute(text(check_sql))
print(f"  + {check_name}")
```

The result is never inspected. `SELECT to_regclass('explore_field_index')` returns `NULL` if the table doesn't exist -- it doesn't throw an exception. So this verification will print `+ Explore table exists` even when the table is missing. Similarly, the graph check returns an empty result set if the graph doesn't exist.

**Fix:**
```python
for check_name, check_sql in checks:
    try:
        result = conn.execute(text(check_sql))
        row = result.fetchone()
        if row is None or row[0] is None:
            print(f"  x {check_name}: NOT FOUND")
            all_passed = False
        else:
            print(f"  + {check_name}: {row[0]}")
    except Exception as e:
        conn.rollback()
        print(f"  x {check_name}: {e}")
        all_passed = False
```

Also missing from verification:
- None of the property indexes are verified
- The tsvector trigger is not verified
- The `business_term_index` and `explore_partition_filters` tables are not checked
- No count of expected indexes vs. actual indexes

---

**[IMPORTANT] Lines 153-161 -- Individual index failures are swallowed, then `conn.commit()` is called**

The loop catches exceptions per-index and calls `conn.rollback()`, but then after the loop, line 161 calls `conn.commit()`. After a `rollback()`, the transaction is reset, so subsequent `CREATE INDEX` statements within the same connection are in a new implicit transaction. But the `conn.commit()` on line 161 only commits whatever happened after the last rollback. This means:
- If index 3/6 fails, indexes 1-2 are rolled back
- Indexes 4-6 (if they succeed) are committed
- Indexes 1-2 are lost

This is a subtle data integrity issue. The operator sees "All indexes created!" but only some actually exist.

**Fix:** Use SAVEPOINTs for each index, or execute each in its own transaction, or accumulate failures and report at the end:
```python
failed = []
for idx_name, idx_sql, *description in indexes:
    try:
        conn.execute(text("SAVEPOINT idx_save"))
        conn.execute(text(idx_sql))
        conn.execute(text("RELEASE SAVEPOINT idx_save"))
        print(f"  + {idx_name}")
    except Exception as e:
        conn.execute(text("ROLLBACK TO SAVEPOINT idx_save"))
        failed.append(idx_name)
        print(f"  x {idx_name}: {e}")

conn.commit()
if failed:
    print(f"  WARNING: {len(failed)} indexes failed: {failed}")
else:
    print("  All indexes created!")
```

---

**[IMPORTANT] Lines 192-194 -- `explore_partition_filters.required_filters` is a single `VARCHAR(255)` for what should be an array**

An explore can have multiple required partition filters (e.g., `partition_date` AND `region`). Storing them as a single `VARCHAR(255)` means you either:
- Comma-delimit them (and then parse on read, which is fragile)
- Only support one filter (which is wrong)

Look at the `FieldCandidate` model in `src/retrieval/models.py` -- `filters` is `dict[str, str]`. The schema should match the data model.

**Fix:**
```sql
CREATE TABLE IF NOT EXISTS explore_partition_filters (
    explore_name VARCHAR(255) PRIMARY KEY,
    required_filters TEXT[] NOT NULL,    -- array of filter field names
    filter_defaults JSONB DEFAULT '{}',  -- optional default values
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### Suggestions

**[SUGGESTION] Lines 25-46 -- Each function creates its own `engine = get_engine()` connection, but `get_engine` is cached**

While `get_engine()` is `@lru_cache`'d (so no duplicate engines), each function opens and closes its own connection. For a schema setup script that runs sequentially, it would be cleaner to pass a single connection through. This also makes transactional boundaries clearer and would allow the entire setup to be wrapped in a single transaction (or explicitly not).

---

**[SUGGESTION] Lines 94-96 -- The `(properties->>'name'::agtype)` cast syntax may be incorrect for AGE**

In Apache AGE, properties are stored as `agtype`. The expression `properties->>'name'::agtype` first extracts `name` as text via `->>`, then casts the result to `agtype`. This is likely not what you want for an index expression -- you're indexing the text value, so the cast back to `agtype` is either a no-op or will cause unexpected behavior. Verify this against the AGE documentation. The correct form is likely just `(properties->>'name')` for a text index, or `(properties->'name')` for an `agtype` index.

---

**[SUGGESTION] Line 254 -- `idx_explore_index` query is defined but never executed**

```python
idx_explore_index = "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_explore_name'"
```

This variable is assigned but never used in the `verify_setup` function. It looks like someone intended to verify that the property indexes were created but forgot to add it to the `checks` list.

---

**[SUGGESTION] Lines 27, 167, 244 -- `print()` statements with emoji for a setup script**

The emoji characters in `print("\n Creating graph...")` etc. could cause encoding issues in CI/CD environments or terminal sessions without UTF-8 support. For a setup script that might run in Docker containers or CI pipelines, use plain ASCII markers like `[OK]`, `[FAIL]`, `[INFO]`, or switch to the `logging` module.

---

**[NIT] Line 76 -- Grammar: "A Vertex" should be just "Vertex" or "The vertex"**

```python
print("  A Vertex label column not found; creating unfiltered indexes")
```

Reads awkwardly. Same on line 78 ("A Edge" should be "An edge" if you keep the article).

---

### What's Good

**[PRAISE]** The `get_table_columns` helper on lines 57-65 uses parameterized queries (`:schema`, `:table`) instead of f-strings. This is correct and safe. It shows the author knows how to do parameterized SQL -- which makes the f-string usage elsewhere a conscious design choice (AGE's Cypher API requires string interpolation since `ag_catalog.cypher()` doesn't support bind parameters). Good awareness of the constraint.

**[PRAISE]** The hybrid table design -- having `explore_field_index` as a denormalized relational cache alongside the graph -- is architecturally sound. The design doc confirms this: graph for structural validation, relational tables for hot-path lookups. This avoids the "everything must go through the graph" anti-pattern that would kill query latency.

**[PRAISE]** The tsvector trigger with weighted terms (A for canonical, B for description) is the right approach for full-text search ranking. Weight differentiation means exact term matches rank higher than description matches, which is what you want for field resolution.

**[PRAISE]** The `CREATE TABLE IF NOT EXISTS` for `explore_partition_filters` with partition filter tracking is forward-looking. This directly addresses Error Type 3 from the design doc (missing partition filters = $5,000 accidental BQ scans). Making partition filters a first-class schema concept is smart.

---

### Summary of Required Actions

| Priority | Count | Summary |
|----------|-------|---------|
| BLOCKING | 4 | Invalid SQL on idx_field_name, destructive drop-recreate, dead/broken `_where_label_in`, DROP+CREATE contradiction |
| IMPORTANT | 5 | Redundant index, VARCHAR(20) truncation, tsvector missing synonyms, verify_setup doesn't verify, transaction rollback semantics, partition_filters schema |
| SUGGESTION | 4 | Connection reuse, agtype cast, dead variable, print encoding |
| NIT | 1 | Grammar |

**Review Verdict: Changes Requested.** The 4 blocking issues (especially the malformed SQL on line 110 and the destructive-masquerading-as-idempotent pattern) must be fixed before this can be merged. The VARCHAR(20) and missing synonyms in the tsvector trigger will cause downstream failures when actual LookML data is loaded.

---