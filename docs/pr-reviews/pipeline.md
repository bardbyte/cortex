# PR Review: `src/retrieval/pipeline.py`

**Reviewer:** Saheb (Staff Engineer)
**Date:** 2026-03-12
**Verdict:** Changes Requested

---

## Summary
- This module is the core scoring engine for Cortex: it takes extracted entities from a user query, validates their candidate fields against the LookML graph topology, and ranks explores by how well they support the query.
- **Architecture impact: High** -- this is the decision function that determines which LookML explore gets selected. A bug here means wrong SQL for every query.

---

### Blocking Issues

**[BLOCKING] pipeline.py:213 -- Coverage calculation is hardcoded to 1.0; the formula is wrong**

The coverage calculation reads:

```python
coverage = (total_entities / total_entities) if total_entities > 0 else 0
```

This is always `1.0` for every explore, regardless of how many entities it actually supports. The docstring at line 148 says `coverage = supported_entities / total_entities`, which means the intended formula is:

```python
coverage = supported_entities_count / total_entities
```

This is not a cosmetic issue. Coverage feeds into `FinalScore = (RawScore + coverage) - MissingPenalty` on line 216. When coverage is always 1.0, every explore gets the same +1.0 bonus regardless of entity support. This defeats the purpose of the coverage signal and distorts the ranking. An explore supporting 1 of 5 entities gets the same coverage bonus as one supporting 5 of 5.

**Fix:**
```python
coverage = supported_entities_count / total_entities if total_entities > 0 else 0.0
```

Note: you also have `supported_entities = sum(entity_contrib.values())` on line 211 which shadows the semantic intent -- this variable is actually `raw_score` (the sum of weighted similarities), not a count. See the next issue.

---

**[BLOCKING] pipeline.py:210-212 -- `supported_entities` variable is misleading and masks a second bug**

```python
supported_entity_ids = list(entity_contrib.keys())
supported_entities = sum(entity_contrib.values())   # line 211
raw_score = sum(entity_contrib.values())             # line 212
```

`supported_entities` and `raw_score` are computed identically -- both are `sum(entity_contrib.values())`. The variable `supported_entities` is never used again. It looks like the original intent was for `supported_entities` to be a count (matching the docstring), but it got implemented as a sum of weighted similarities instead. This is dead code that masks the coverage bug above.

**Fix:** Remove line 211 entirely. The count you need is `supported_entities_count = len(supported_entity_ids)` which is already computed at line 214.

---

**[BLOCKING] pipeline.py:233-256 -- `_get_explore_names` has multiple logic errors in the else branch**

This function is the bridge between raw AGE agtype results and usable explore names. The `else` branch (lines 246-254) has several problems:

1. **Line 247:** `getattr(explore, "name", str)` -- the fallback is the `str` *class*, not a string value. If the explore object has no `name` attribute, `obj_name` becomes `<class 'str'>`. Then `isinstance(obj_name, dict)` is always False, so this line accomplishes nothing, but it is a latent trap.

2. **Line 248-249:** If `obj_name` happens to be a dict, it appends the *dict* to `names` (a `list[str]`). This would cause type errors downstream when comparing strings to dicts.

3. **Line 253-254:** `if isinstance(explore, str): names.append(name)` -- but `name` here is the variable from line 250 (`explore.get("name")` which would have thrown `AttributeError` on a string). If this branch runs when `explore` is a string, `name` may be `None` (from the dict check that silently set it), and you would append `None` to the names list. Even if `name` had a valid value from a dict explore processed in a *previous* loop iteration, it would be the wrong name.

4. **Overall control flow:** The `else` branch tries to handle three types (objects with `.name`, dicts, and raw strings) but does so in sequence without `elif`, meaning a single `explore` could hit multiple branches and append multiple (possibly incorrect) names.

**Fix:** Rewrite this function with explicit type dispatch:

```python
def _get_explore_names(matched_explores: list) -> list[str]:
    """Extract explore names from AGE graph results.
    
    AGE returns agtype values that typically serialize as 
    '{...properties...}::vertex' strings.
    """
    names = []
    for explore in matched_explores:
        name = None
        if isinstance(explore, str) and explore.endswith("::vertex"):
            try:
                parsed = json.loads(explore[: -len("::vertex")])
                if isinstance(parsed, dict):
                    name = parsed.get("properties", {}).get("name")
            except json.JSONDecodeError:
                pass
        elif isinstance(explore, dict):
            name = explore.get("name") or explore.get("properties", {}).get("name")
        elif isinstance(explore, str):
            # Raw string explore name (unlikely but defensive)
            name = explore
        else:
            # Object with .name attribute
            attr_name = getattr(explore, "name", None)
            if isinstance(attr_name, str):
                name = attr_name
        
        if isinstance(name, str) and name:
            names.append(name)
    return names
```

---

**[BLOCKING] pipeline.py:170 -- Filter entities with candidates are silently dropped from scoring**

At line 170:
```python
if entity_type not in ("measure", "dimension", "filter"):
    continue
```

This allows `filter` type entities through, but looking at `vector.py` lines 336-346, filter entities are created *without* a `candidates` list. So at line 175, `candidates = entity.get("candidates", [])` returns `[]`, the inner loop never runs, but `entity_ids.append(entity_id)` at line 174 *does* execute for filters. This means:

- Filters increase `total_entities` (line 204)
- Filters can never contribute to any explore's score (no candidates)
- Every explore gets penalized for "missing" the filter entity

This creates a systematic ranking bias: queries with filters always have inflated `missing_penalty` values, punishing all explores equally for something no explore can satisfy. For a query like "Millennial customers with billed business over $100k", the filter entity inflates `total_entities` from 2 to 3, adding 0.15 penalty to every explore.

Similarly, `time_range` entities (line 348 in vector.py) have type `"time_range"` which gets filtered out by the type check at line 170, so they are excluded correctly but inconsistently -- the code happens to work by accident.

**Fix:** Either:
- (a) Skip filter entities from scoring by removing `"filter"` from the allowed types, or  
- (b) Add vector search candidates to filter entities upstream in `vector.py`, or  
- (c) Only count entities that have candidates toward `total_entities`:

```python
if entity_type not in ("measure", "dimension"):
    continue
```

Option (a) is the simplest and matches the current data flow.

---

### Important Issues

**[IMPORTANT] pipeline.py:186-189 -- Graph errors are silently swallowed; no visibility into failure rate**

```python
try:
    matched_explores = find_explores_for_view(view_name)
except Exception as e:
    logger.debug("Error querying graph for view=%s: %s", view_name, e)
    matched_explores = []
```

Using `logger.debug` for a graph query failure means these errors will be invisible in production (default log level is INFO or WARNING). If the graph database goes down, every single candidate silently gets `matched_explores = []`, every `support_flag` becomes 0.0, and the pipeline returns an empty result with no indication of *why*. This is a silent failure mode that will be extremely difficult to diagnose.

**Fix:**
```python
except Exception as e:
    logger.warning(
        "Graph query failed for view=%s, candidate will be excluded: %s",
        view_name, e,
    )
    matched_explores = []
```

Also consider: if *all* graph queries fail (graph is down), the function should detect this pattern and raise rather than returning an empty result that looks like "no explores match."

---

**[IMPORTANT] pipeline.py:186-187 -- N+1 graph query problem will not scale**

`find_explores_for_view(view_name)` is called inside a nested loop: for each entity, for each candidate. If you have 5 entities with 5 candidates each, that is 25 separate database round-trips to the graph. Many candidates will share the same `view_name`, so you are issuing duplicate queries.

At current scale this might be tolerable, but as the field_embeddings table grows and you add more entities, this will become a latency bottleneck.

**Fix:** Add memoization within the scoring call:

```python
def _score_explores(entities, penalty_constant):
    view_explore_cache: dict[str, set[str]] = {}
    
    def _get_graph_explores(view_name: str) -> set[str]:
        if view_name not in view_explore_cache:
            try:
                matched = find_explores_for_view(view_name)
                view_explore_cache[view_name] = set(_get_explore_names(matched))
            except Exception as e:
                logger.warning("Graph query failed for view=%s: %s", view_name, e)
                view_explore_cache[view_name] = set()
        return view_explore_cache[view_name]
    ...
```

---

**[IMPORTANT] pipeline.py:261 -- `%(levelnames)s` is a typo; demo will crash**

```python
logging.basicConfig(level=logging.INFO, format="%(levelnames)s %(name)s: %(message)s")
```

The correct format key is `%(levelname)s` (no trailing 's'). This will raise a `KeyError` when any log message is emitted, crashing the demo. The same typo exists in `vector.py:395`.

**Fix:**
```python
format="%(levelname)s %(name)s: %(message)s"
```

---

**[IMPORTANT] graph_search.py:50-63 -- SQL injection risk in Cypher query construction**

```python
escaped_view = view_name.replace("'", "''")
escaped_graph = graph_name.replace("'", "''")
sql = f"""
SELECT * FROM ag_catalog.cypher('{escaped_graph}'::name, $$
    MATCH (e:Explore)-[:BASE_VIEW]->(v:View {{name: '{escaped_view}'}})
    ...
$$::cstring) AS (explore agtype);
"""
```

The single-quote escaping is a minimal defense, but Cypher injection inside `$$..$$` dollar-quoted blocks is a real risk. The `view_name` comes from vector search results (which come from the database), so the attack surface is lower than direct user input. But if an attacker can control field_embeddings data (e.g., via the LookML loader), they can inject Cypher. The `$$` dollar-quoting means single-quote escaping inside the Cypher string is the only barrier.

For production at Amex, this should use parameterized queries if AGE supports them, or at minimum validate that `view_name` matches an expected pattern (alphanumeric + underscores).

**Fix:** Add input validation:
```python
import re

def _validate_identifier(value: str, label: str) -> str:
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value
```

---

### Minor Issues / Suggestions

**[SUGGESTION] pipeline.py:68 -- EntityExtractor is re-instantiated on every call**

`retrieve_with_graph_validation` creates a new `EntityExtractor` on every invocation. The `EntityExtractor.__init__` calls `model(llm_model_idx)` which likely initializes an LLM client. If these clients are expensive to create (HTTP sessions, auth handshakes), this adds unnecessary latency.

**Fix:** Accept an optional `extractor` parameter or use a module-level factory with caching.

---

**[SUGGESTION] pipeline.py:46-50 -- `llm_model_idx` parameter name is unclear**

The name `llm_model_idx` suggests an integer index, but the type is `str` with a default of `""`. Looking at `vector.py`, the constant is `EMBED_MODEL_IDX = '2'`. The empty string default here means the `EntityExtractor.__init__` will use `EMBED_MODEL_IDX` as the default. This is confusing because the pipeline's default (`""`) and the extractor's default (`'2'`) are different, and the caller cannot tell what model they will get.

**Fix:** Either pass `None` as the sentinel (making the default explicit) or import and use `EMBED_MODEL_IDX` directly.

---

**[SUGGESTION] pipeline.py:42 -- `PipelineResult.entities` type does not match usage**

`entities: list[dict[str, Any]] | None = None` but in practice (line 80) it is always set to a list (possibly empty). Using `None` as a default creates ambiguity: callers must check both `None` and empty list. Since the pipeline always populates this field, default it to an empty list:

```python
entities: list[dict[str, Any]] = field(default_factory=list)
```

---

**[NIT] pipeline.py:159 -- Commented-out code**

```python
# explore_support: dict[str, dict[str, float]] = {}
```

Dead commented-out code. Remove it.

---

**[NIT] pipeline.py:77 -- Log message says [2/3] and [3/3] but step 2 does both validation and scoring**

The log says "[1/3] Extracting... [2/3] Validating and scoring... [3/3] Complete" but step 3 is just "format and return." The numbering is misleading since there are really only 2 substantive steps.

---

### What is Good

**[PRAISE]** The `ScoredExplore` and `PipelineResult` dataclasses (lines 26-43) are well-designed. Using dataclasses instead of raw dicts for the pipeline output provides type safety, IDE support, and self-documenting structure. This is the right pattern.

**[PRAISE]** The scoring algorithm's core idea (lines 146-150) is sound: weighting entity contributions by similarity and entity importance, then penalizing missing entities, is a principled approach to explore ranking. Once the coverage bug is fixed, the formula `FinalScore = RawScore + coverage - MissingPenalty` gives you three interpretable levers to tune.

**[PRAISE]** The `max()` aggregation on line 202 (`explore_support[entity_id] = max(...)`) correctly handles the case where multiple candidates from the same explore contribute to the same entity -- taking the best match rather than summing avoids double-counting.

**[PRAISE]** The separation between `retrieve_with_graph_validation` (returns full result) and `retrieve_top_explore` (convenience wrapper) is a clean API design that supports both debugging/evaluation use cases and production hot-path use cases.

---

### Summary of Severity

| Severity | Count | Summary |
|----------|-------|---------|
| BLOCKING | 4 | Coverage always 1.0; `_get_explore_names` has multiple logic errors; filter entities inflate penalty; dead/misleading variable |
| IMPORTANT | 3 | Silent graph failures; N+1 query problem; logging format typo crashes demo |
| SUGGESTION | 3 | Extractor re-instantiation; unclear parameter naming; Optional vs empty list |
| NIT | 2 | Commented-out code; misleading step numbering |

The coverage bug and the `_get_explore_names` errors are the highest priority. Together they mean the scoring algorithm is not computing what the docstring says it computes, and the graph validation results may not be parsed correctly. Both of these directly affect whether the right explore is selected, which is the single most important decision in the pipeline.

---

### No Tests

There are no unit tests for `_score_explores` or `_get_explore_names`. Given that these are the most critical functions in the retrieval pipeline and contain the bugs identified above, this is a significant gap. I would strongly recommend adding tests before fixing the bugs -- write the tests first to capture the current (broken) behavior, then fix the code and verify the tests pass with the corrected expectations.

---

### AI Code Tracking

```markdown
### PR-review: pipeline.py unified retrieval pipeline
**Date:** 2026-03-12
**Author:** Unknown (review of existing file)
**Reviewer:** Saheb
**Files Changed:** 1 (pipeline.py, with context from vector.py, graph_search.py)
**Lines Changed:** 282 (full file)
**AI-Generated Lines:** Unknown
**Human-Written Lines:** Unknown
**AI Tool Used:** Unknown
**Review Verdict:** Changes Requested
**Key Feedback:** Coverage formula is hardcoded to 1.0 (always returns same bonus regardless of entity support), and _get_explore_names has multiple logic errors in the else branch that can append None, wrong types, or wrong names to the result list. Both bugs directly affect explore ranking correctness.
```