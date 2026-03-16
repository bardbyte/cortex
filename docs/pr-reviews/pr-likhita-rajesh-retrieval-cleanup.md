# PR Review: `feature/likhita-rajesh-retrieval-implementation`

**Reviewer:** Saheb
**Branch:** `feature/likhita-rajesh-retrieval-implementation` → `main`
**Date:** 2026-03-16

---

Good foundation work. The entity extraction → vector search → graph validation pipeline structure is solid. I've been building the orchestration layer on top of this in `saheb/orchestrator-v1` and found several issues that need to be fixed before merging to main. Fixing these now will prevent conflicts when I merge the orchestrator on top.

---

## File: `src/retrieval/pipeline.py`

### P0 — Coverage calculation bug (line ~253)

```python
# CURRENT (BUG — always returns 1.0):
coverage = (total_entities / total_entities) if total_entities > 0 else 0

# FIX:
coverage = (supported_entities_count / total_entities) if total_entities > 0 else 0
```

This is a correctness bug. Coverage is supposed to measure what fraction of the user's requested entities an explore can serve. Right now it's hardcoded to 1.0 for every explore, which means the scoring formula can't distinguish between an explore that matches 1/4 entities and one that matches 4/4.

### P0 — New `EntityExtractor()` created per request (line ~68)

```python
# CURRENT (expensive — creates new LLM + embedding clients every call):
extractor = EntityExtractor(llm_model_idx=llm_model_idx)

# FIX — accept optional extractor parameter:
def retrieve_with_graph_validation(
    query: str,
    top_k: int = 5,
    llm_model_idx: str = "",
    penalty_constant: float = 0.15,
    extractor: EntityExtractor | None = None,  # ADD THIS
) -> PipelineResult:
    ...
    if extractor is None:
        extractor = EntityExtractor(llm_model_idx=llm_model_idx)
    raw_results = extractor.process_query(query, top_k)
```

On corp, `EntityExtractor.__init__` calls SafeChain `model()` twice (LLM + embeddings). Each call is ~50ms. For a demo this is fine, but when the orchestrator calls this per-request it adds up. Accept an optional singleton so the caller can reuse it.

### P1 — Add `pre_extracted` parameter support

The orchestrator already extracts entities during intent classification (Phase 1). If we extract again in retrieval, that's a wasted LLM call (~300ms). Add support for pre-extracted entities:

```python
def retrieve_with_graph_validation(
    query: str,
    top_k: int = 5,
    llm_model_idx: str = "",
    penalty_constant: float = 0.15,
    extractor: EntityExtractor | None = None,
    pre_extracted: "ExtractedEntities | None" = None,  # ADD THIS
) -> PipelineResult:
    ...
    if extractor is None:
        extractor = EntityExtractor(llm_model_idx=llm_model_idx)
    if pre_extracted is not None:
        raw_results = extractor.process_query(query, top_k, pre_extracted=pre_extracted)
    else:
        raw_results = extractor.process_query(query, top_k)
```

This requires a matching change in `vector.py` (see below).

### P1 — `get_top_explore()` return type should include confidence and action

The orchestrator needs to know whether to proceed, disambiguate, or ask for clarification. Add these fields:

```python
def get_top_explore(pipeline_result: PipelineResult) -> dict[str, Any]:
    if not pipeline_result.explores:
        return {
            "top_explore_name": None,
            "confidence": 0.0,
            "action": "clarify",
            "message": "Could not identify a matching data source.",
        }

    top = pipeline_result.explores[0]

    # Confidence as relative score (0-1)
    max_possible = ...  # see scoring improvements below
    confidence = min(top.score / max_possible, 1.0) if max_possible > 0 else 0.0

    # Near-miss detection
    is_near_miss = False
    if len(pipeline_result.explores) >= 2:
        second = pipeline_result.explores[1]
        if second.score > 0 and top.score / second.score < 1.18:  # within 18%
            is_near_miss = True

    # Action routing
    if confidence < 0.3:
        action = "clarify"
    elif is_near_miss:
        action = "disambiguate"
    else:
        action = "proceed"

    return {
        "top_explore_name": top.name,
        "confidence": round(confidence, 4),
        "action": action,
        "is_near_miss": is_near_miss,
        "retrieval_metadata": { ... },
    }
```

### P2 — `_get_explore_names()` parsing is fragile (bottom of file)

The `else` branch has issues:
- `obj_name = getattr(explore, "name", str)` — passing `str` as default returns the type, not a string
- `if isinstance(obj_name, dict): names.append(obj_name)` — appends a dict to a string list
- `if isinstance(explore, str): names.append(name)` — `name` could be `None` here

Replace with a defensive version:

```python
def _get_explore_names(matched_explores: list) -> list[str]:
    names = []
    for explore in matched_explores:
        if isinstance(explore, str) and explore.endswith("::vertex"):
            try:
                parsed = json.loads(explore[: -len("::vertex")])
                name = parsed.get("properties", {}).get("name")
                if isinstance(name, str):
                    names.append(name)
            except (json.JSONDecodeError, AttributeError):
                continue
        elif isinstance(explore, dict):
            name = explore.get("name")
            if isinstance(name, str):
                names.append(name)
    return names
```

---

## File: `src/retrieval/vector.py`

### P0 — Sequential embedding calls (N API calls instead of 1)

Each entity gets its own `embed_text()` call. For a query with 3 measures + 2 dimensions, that's 5 sequential embedding API calls (~200ms each on corp). Batch them:

```python
# ADD this method to EntityExtractor:
def embed_texts_batch(self, texts: list[str], is_query: bool = True) -> list[list[float]]:
    """Batch-embed multiple texts in a single API call."""
    if not texts:
        return []
    if is_query:
        texts = [BGE_QUERY_PREFIX + t for t in texts]
    return self.embedding_client.embed_documents(texts)
```

Then refactor `process_query()` to collect all texts first, batch embed, then distribute:

```python
# Collect all texts
embed_jobs = []
for m in extracted.measures:
    embed_jobs.append((m, "measure"))
for d in extracted.dimensions:
    embed_jobs.append((d, "dimension"))

# One API call
all_texts = [job[0] for job in embed_jobs]
all_embeddings = self.embed_texts_batch(all_texts)

# Distribute embeddings back to entities
for (text, entity_type), embedding in zip(embed_jobs, all_embeddings):
    matches = self.search_similar_fields(text, embedding, limit=top_k)
    ...
```

Note: `embed_documents()` is the LangChain batch method. `embed_query()` is single-text. SafeChain supports both through the same embedding client.

### P1 — Add `pre_extracted` parameter to `process_query()`

```python
def process_query(
    self, query: str, top_k: int = 5,
    pre_extracted: ExtractedEntities | None = None,  # ADD THIS
) -> dict[str, Any]:
    if pre_extracted is not None:
        extracted = self._normalize_terms(query, pre_extracted)
    else:
        extracted = self.extract_entities(query)
        extracted = self._normalize_terms(query, extracted)
    ...
```

### P1 — BGE query prefix missing

The BGE embedding model used via SafeChain is `BAAI/bge-large-en-v1.5`. It requires the prefix `"Represent this sentence for searching relevant passages: "` prepended to queries (but NOT to documents in the DB). Without it, recall drops ~15%.

```python
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def embed_text(self, text: str, is_query: bool = True) -> list[float]:
    if is_query:
        text = BGE_QUERY_PREFIX + text
    return self.embedding_client.embed_query(text)
```

### P2 — Dimension enrichment suffix is too generic

```python
# CURRENT:
enriched_text = f"{dimension_text}. Also known as: attribute, segment, grouping"
```

This adds the same generic suffix to every dimension, which dilutes the embedding. Either remove it or make it context-aware. For now, just remove it — the embedding model handles dimensions fine without it.

---

## File: `config/constants.py`

### P1 — Add `EXPLORE_DESCRIPTIONS`

The scoring pipeline needs human-readable explore descriptions for description-similarity scoring. Add:

```python
EXPLORE_DESCRIPTIONS: dict[str, str] = {
    "attrition_explore": "Customer attrition, churn, retention, card cancellation metrics by demographics and product",
    "card_product_explore": "Card product issuance, volume, mix by product type and tier",
    # ... one line per explore in the Looker model
}
```

I'll provide the full list — you can copy it from `saheb/orchestrator-v1:config/constants.py`.

### P1 — Add `POSTGRES_GRAPH_PATH`

Graph search needs this for AGE schema:

```python
POSTGRES_GRAPH_PATH = os.getenv("POSTGRES_GRAPH_PATH", "lookml_schema")
```

---

## File: `src/connectors/postgres_age_client.py`

### P1 — Engine should be cached (singleton)

```python
# CURRENT:
def get_engine():
    ...
    return create_engine(url)  # New engine every call

# FIX — module-level singleton:
_engine = None

def get_engine():
    global _engine
    if _engine is None:
        ...
        _engine = create_engine(url, pool_size=5, pool_pre_ping=True)
    return _engine
```

Without this, every pgvector query opens a new connection pool. On corp with network latency to PostgreSQL, this adds ~100ms per call.

---

## File: `scripts/load_lookml_to_pgvector.py`

### P1 — Use `%s` parameterized queries for embedding insert

Verify that the embedding serialization works correctly with pgvector. We hit a bug where the `VECTOR(1024)` type needed the embedding formatted as `[0.1, 0.2, ...]` string, not a Python list. The `psycopg2` adapter handles this if you pass the string directly:

```python
embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
```

Make sure this is consistent between the insert script and the search query.

---

## File: `docker-compose.yaml`

### P2 — Add `docker-compose.local.yaml` for local dev

The main `docker-compose.yaml` references `artifactory.aexp.com` images which aren't available outside corp. Add a `docker-compose.local.yaml` that uses public images:

```yaml
services:
  pgage:
    build:
      context: .
      dockerfile: Dockerfile.local
    ports:
      - "5433:5432"  # Different host port to avoid conflicts
```

This is already on `saheb/orchestrator-v1` — you can copy it from there.

---

## Summary: What to do

| Priority | File | Change | Effort |
|----------|------|--------|--------|
| P0 | pipeline.py | Fix coverage bug (always 1.0) | 1 line |
| P0 | vector.py | Batch embedding (N calls → 1) | ~30 lines |
| P0 | pipeline.py | Accept optional `extractor` param | 5 lines |
| P1 | vector.py | Add `pre_extracted` param | 10 lines |
| P1 | vector.py | BGE query prefix | 5 lines |
| P1 | pipeline.py | Add confidence + action to `get_top_explore` | 20 lines |
| P1 | constants.py | Add EXPLORE_DESCRIPTIONS | Copy from my branch |
| P1 | postgres_age_client.py | Singleton engine | 10 lines |
| P2 | pipeline.py | Fix `_get_explore_names` parsing | 15 lines |
| P2 | vector.py | Remove generic dimension suffix | 1 line |

**P0s block the demo. P1s block orchestrator integration. P2s are cleanup.**

Once these are done, merge to main. I'll rebase the orchestrator branch on top.
