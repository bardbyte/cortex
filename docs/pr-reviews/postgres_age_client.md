# PR Review: `src/connectors/postgres_age_client.py`

**Reviewer:** Saheb (Staff Engineer)
**Date:** 2026-03-12
**Verdict:** Changes Requested

---

## Summary

108-line utility module that builds a SQLAlchemy engine from environment variables and provides an AGE session initializer. Used by `graph_search.py`, `vector.py`, and setup scripts. Compact and reasonably well-structured, but has several correctness bugs: a credential leak in exception handling, a string formatting defect, and a thread-safety issue with the caching strategy.

---

## Critical Issues

### 1. [BLOCKING] Line 100 -- Credential leak via exception re-raise

`str(exc)` on SQLAlchemy engine creation errors can include the full connection URL (host, username, password). The `from exc` clause chains the original exception, so anyone catching upstream and logging the traceback gets the password.

```python
# Current (line 97-101)
except Exception as exc:
    raise RuntimeError(
        f"Failed to create PostgreSQL engine from environment configuration. "
        f"Driver/url setup error: {exc.__class__.__name__}: {exc}"
    ) from exc
```

**Fix:**
```python
except Exception as exc:
    raise RuntimeError(
        f"Failed to create PostgreSQL engine from environment configuration. "
        f"Error type: {exc.__class__.__name__}. "
        f"Check POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, "
        f"and POSTGRES_PASSWORD environment variables."
    ) from None  # Break the chain to avoid leaking credentials
```

### 2. [BLOCKING] Lines 38-41 -- Missing space produces garbled error message

Implicit string concatenation between the two f-strings produces:
```
Missing required environment variables: POSTGRES_HOST(aliases checked: POSTGRES_HOST, PGHOST)
```

Note "HOST(aliases" -- no separator.

**Fix:** Add a space after `{names[0]}`:
```python
raise RuntimeError(
    f"Missing required environment variable. "
    f"Checked: {', '.join(names)}. None were set."
)
```

---

## Major Issues

### 3. Lines 74-96 -- `lru_cache` on `get_engine()` is not thread-safe and prevents engine disposal

`lru_cache` makes it impossible to: (1) dispose the engine for graceful shutdown, (2) refresh credentials if passwords rotate, (3) test properly without leaking implementation details via `cache_clear()`.

**Fix:** Use module-level `_engine` with a threading lock and expose `dispose_engine()`.

### 4. Lines 104-107 -- `init_age_session` has no error handling

If AGE extension is not installed, `LOAD 'age'` throws a hard-to-interpret error. No type annotation on the `connection` parameter either.

**Fix:**
```python
from sqlalchemy.engine import Connection

def init_age_session(conn: Connection) -> None:
    try:
        conn.execute(text("LOAD 'age'"))
        conn.execute(text('SET search_path = ag_catalog, "$user", public'))
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize Apache AGE session. "
            "Verify AGE extension is installed: CREATE EXTENSION IF NOT EXISTS age;"
        ) from exc
```

### 5. Line 65 -- Driver `postgresql+psycopg2` may not match installed psycopg version

If psycopg3 is installed (as project docs suggest), this will fail at runtime. Confirm which driver is installed and use `postgresql+psycopg` for v3.

---

## Minor Issues

- **Line 87:** `load_dotenv` called inside cached `get_engine` is a hidden side effect. Move to module level.
- **Line 82:** Docstring mentions `POSTGRES_DBNAME` but code doesn't check it. Add to `_require_env` aliases.
- **Lines 58-60:** SSL default should be `require` for enterprise. Default `None` means unencrypted connections.
- Missing `__all__` export list.

---

## Positive Notes

- `_clean_env_value` / `get_env` / `_require_env` layering with env var aliases is thoughtful.
- `URL.create()` instead of string concatenation avoids special-character-in-password bugs.
- `pool_pre_ping=True` catches stale connections. Good production instinct.
- Module docstring explicitly calls out the security intent.
