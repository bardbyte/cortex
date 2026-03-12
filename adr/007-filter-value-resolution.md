# ADR-007: Filter Value Resolution — Auto-Extracted Value Catalog

**Status:** Proposed
**Date:** March 10, 2026
**Decision Makers:** Saheb, Abhishek
**Reviewers:** Sulabh, Ashok, Architecture Board

---

## Context

### The Problem

Every NL2SQL system must translate user language into exact filter values. This is the gap between what a user says and what the database contains:

| User Says | Dimension | Exact DB Value | How Would LLM Know? |
|-----------|-----------|---------------|---------------------|
| "Millennials" | generation | "Millennial" | Maybe — it's close |
| "small business" | bus_seg | "OPEN" | No — "OPEN" is an Amex-internal code |
| "consumer" | bus_seg | "CPS" | No — "CPS" is an abbreviation |
| "basic card" | basic_supp_in | "B" | No — single-letter code |
| "revolving" | rel_type | "AA" | No — internal relationship code |
| "yes" | is_replacement | "Yes" | Maybe — Looker yesno syntax |
| "dining" | oracle_mer_hier_lvl3 | "Eating Places, Restaurants" | No — exact BQ category string |

The current pipeline (ADR-005) relies on Gemini Flash to extract both the **dimension name** and the **filter value** in a single LLM call. This works for obvious cases ("Millennials" → generation) but fails silently for coded values ("small business" → bus_seg = "OPEN"). A silent failure means the query runs, returns zero rows, and the user thinks there's no data.

### Current State

The retrieval orchestrator (`src/retrieval/orchestrator.py`) contains a hardcoded `FILTER_VALUE_MAP` — a manually curated Python dictionary mapping ~40 user terms to their BQ equivalents across 7 dimensions. This was built by reading LookML descriptions and Ayush's data dictionary.

**Why this doesn't scale:**
- Every new BU requires a developer to manually enumerate all categorical values and their synonyms
- New values added to BQ (new campaigns, new product codes, new merchant categories) are invisible until someone updates the map
- No feedback loop — when the system fails to match, no one learns from the failure
- At 100+ tables across 3 BUs, the manual map becomes unmaintainable

### What We Need

A system that:
1. Automatically knows every distinct value in every filterable dimension — without asking teams
2. Matches user natural language to exact DB values — without relying on the LLM
3. Learns new synonyms from user interactions — without developer intervention
4. Scales to any number of BUs — without linear human effort

---

## Decision Drivers

- **Determinism over probabilistic matching.** Filter value resolution must be exact — a fuzzy embedding match that returns "Millennial" 93% of the time means 7% of queries silently return wrong results. This step needs to be deterministic.
- **Zero-effort BU onboarding.** Adding Marketing or Risk as new BUs should not require enumerating every categorical value. The system must auto-discover values from the data.
- **Amex approval constraints.** Solution must run on approved infrastructure (PostgreSQL, BigQuery). No new external services.
- **LLM calls are expensive at scale.** Each SafeChain round-trip is ~200-500ms. Adding an LLM call for filter resolution defeats the sub-second retrieval target.

---

## Options Considered

### Option A: LLM-Only Resolution

**Description:** Rely entirely on Gemini Flash (via the entity extraction prompt in ADR-005) to extract both the dimension name and the correctly formatted filter value. Enrich the prompt with available dimension descriptions and sample values.

**Pros:**
- Zero infrastructure — no new tables, no extraction pipeline
- Works immediately for obvious cases ("Millennials" → "Millennial")
- Flexible — handles novel phrasings without predefined mappings

**Cons:**
- Cannot resolve coded values ("small business" → "OPEN") without extensive few-shot examples in the prompt
- Prompt grows linearly with the number of dimensions × values — at 250+ values across 3 BUs, the prompt exceeds practical limits
- Non-deterministic — same input may produce different outputs across calls
- No feedback loop — failed matches are invisible
- Adds ~200ms SafeChain latency for a dedicated resolution call, or overloads the combined intent+entity call

**Effort:** Small (prompt engineering only)
**Reversibility:** Easy

### Option B: Manual Filter Value Map (Current State)

**Description:** Developer-maintained Python dictionary mapping user terms to BQ values. Currently implemented as `FILTER_VALUE_MAP` in `src/retrieval/orchestrator.py`.

**Pros:**
- Deterministic — exact lookups, no ambiguity
- Fast — in-memory dict lookup, <1ms
- Simple to understand and debug
- Works well for v1 (7 views, 13 filterable dimensions)

**Cons:**
- Requires developer to manually enumerate every value and synonym for every dimension
- New values in BQ (new campaigns, products) are invisible until someone updates the code
- Scales linearly with human effort — 3 BUs × ~50 dimensions = significant ongoing maintenance
- No learning — repeated user failures don't improve the system
- Business knowledge locked in code, not accessible to stewards

**Effort:** Small per BU (but recurring)
**Reversibility:** Easy

### Option C: Auto-Extracted Value Catalog with Learned Synonyms

**Description:** Three-layer resolution system:

1. **Auto-extraction:** For every string/yesno dimension in curated LookML views, run `SELECT DISTINCT` on the latest BQ partition. Store results in a `dimension_value_catalog` table in the same PostgreSQL instance as pgvector and AGE. Refresh daily via datagroup trigger.

2. **Deterministic matching:** At query time, match user filter terms against the catalog using exact match → fuzzy match (Levenshtein distance, case normalization, plural stripping) → synonym match. No LLM involved.

3. **Learned synonyms:** When no match is found, the system presents candidate values to the user. The user's selection is logged and queued for steward approval as a new synonym. Over time, the system learns the business vocabulary organically.

**Pros:**
- Zero human effort for initial value extraction — auto-discovered from BQ
- Deterministic matching — exact, fuzzy, then synonym, in that order
- Self-improving — learns from failed matches without developer intervention
- Scales to any BU — same extraction script, no manual enumeration
- Same PostgreSQL instance — no new infrastructure
- Stewards can add synonyms through the same enrichment workflow as business terms (ADR-006)

**Cons:**
- Requires BQ queries to extract values (low cost: ~$0.01/dimension, ~$1.50 for 3 BUs)
- Daily refresh adds ~46 scheduled queries (trivial operational overhead)
- High-cardinality dimensions (card_prod_id with 500+ values, cmgn_cd with 1000+ values) need special handling — catalog these but don't fuzzy-match against them
- Synonym learning requires a review workflow (steward approval queue)

**Effort:** Medium (value extraction pipeline + catalog table + matching function + synonym learning)
**Reversibility:** Easy — fall back to Option B's hardcoded map

---

## Decision

**Chosen option: Option C — Auto-Extracted Value Catalog with Learned Synonyms**

**Rationale:**

Option A fails on coded values, which represent the majority of Amex dimensional data (business segments, relationship types, product codes are all internal codes that no LLM can guess). Option B works for v1 but creates unsustainable maintenance burden as we scale to 3 BUs and 100+ tables. Option C is the only approach that:

- Handles coded values without manual enumeration (auto-extracted from BQ)
- Requires zero LLM calls (deterministic matching)
- Improves over time without developer effort (learned synonyms)
- Scales linearly with compute, not human effort

The cost ($168/year for daily refresh across 3 BUs) is negligible. The infrastructure is already in place (same PostgreSQL instance).

---

## Design

### Schema

```sql
-- Same PostgreSQL instance as pgvector (ADR-004) and AGE
CREATE TABLE dimension_value_catalog (
    id              SERIAL PRIMARY KEY,
    dimension_name  TEXT NOT NULL,        -- "bus_seg"
    view_name       TEXT NOT NULL,        -- "custins_customer_insights_cardmember"
    model_name      TEXT NOT NULL,        -- "finance"
    raw_value       TEXT NOT NULL,        -- "OPEN"
    display_label   TEXT,                 -- "OPEN (Small Business)" from description
    frequency       INT DEFAULT 0,       -- row count in BQ (for ranking)
    synonyms        TEXT[] DEFAULT '{}',  -- steward-added: ["small business", "SMB"]
    is_high_cardinality BOOLEAN DEFAULT FALSE,  -- skip fuzzy matching
    last_extracted  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (dimension_name, view_name, raw_value)
);

CREATE INDEX idx_dvc_dimension ON dimension_value_catalog (dimension_name);
CREATE INDEX idx_dvc_synonyms ON dimension_value_catalog USING GIN (synonyms);

-- Synonym learning queue (pending steward review)
CREATE TABLE synonym_suggestions (
    id              SERIAL PRIMARY KEY,
    user_term       TEXT NOT NULL,        -- "small businesses"
    matched_value   TEXT NOT NULL,        -- "OPEN"
    dimension_name  TEXT NOT NULL,        -- "bus_seg"
    view_name       TEXT NOT NULL,
    occurrence_count INT DEFAULT 1,       -- how many users selected this
    status          TEXT DEFAULT 'pending',  -- pending | approved | rejected
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    reviewed_by     TEXT
);
```

### Extraction Pipeline

```python
# src/retrieval/value_catalog.py

EXTRACTION_QUERY = """
SELECT {column} AS raw_value, COUNT(*) AS frequency
FROM `{project}.{dataset}.{table}`
WHERE {partition_column} = (
    SELECT MAX({partition_column})
    FROM `{project}.{dataset}.{table}`
)
AND {column} IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
LIMIT 50;
"""

def extract_values_for_view(bq_client, view_lkml: dict) -> list[dict]:
    """Auto-extract distinct values for all string/yesno dimensions in a view.

    Reads the parsed LookML view definition, identifies filterable dimensions
    (type: string, type: yesno, not hidden, cardinality < 500), and runs
    SELECT DISTINCT on the latest BQ partition for each.

    Args:
        bq_client: Authenticated BigQuery client.
        view_lkml: Parsed LookML view dict (from lkml parser).

    Returns:
        List of dicts ready for INSERT into dimension_value_catalog.
    """
    ...

def refresh_catalog(bq_client, pg_conn, lookml_views: list[dict]):
    """Full catalog refresh. Run daily via datagroup trigger.

    1. Parse all LookML views
    2. Identify filterable string/yesno dimensions (skip hidden, skip high-cardinality)
    3. Run extraction query per dimension
    4. UPSERT into dimension_value_catalog
    5. Mark dimensions with >200 distinct values as is_high_cardinality

    Cost estimate: ~$0.01 per dimension. Finance BU (13 dims) = $0.13.
    """
    ...
```

### Resolution Function

```python
def resolve_filter_value(
    pg_conn,
    user_term: str,
    candidate_dimensions: list[str] | None = None,
) -> list[dict]:
    """Match a user's filter term to exact BQ values. No LLM.

    Three-pass resolution:
      1. EXACT:  "CPS" → bus_seg = "CPS" (case-insensitive)
      2. FUZZY:  "Millennials" → generation = "Millennial" (Levenshtein ≤ 2)
      3. SYNONYM: "small business" → bus_seg = "OPEN" (synonym array match)

    Args:
        pg_conn: PostgreSQL connection (same instance as pgvector/AGE).
        user_term: The raw term from entity extraction (e.g., "Millennials").
        candidate_dimensions: Optional list to narrow search (from vector results).

    Returns:
        List of {dimension_name, raw_value, match_type, confidence} dicts,
        ranked by match quality. Empty list if no match found.
    """
    results = []

    # Pass 1: Exact match (case-insensitive)
    exact = _exact_match(pg_conn, user_term, candidate_dimensions)
    if exact:
        return exact  # Exact match = done, no ambiguity

    # Pass 2: Fuzzy match (Levenshtein, plural strip, case fold)
    fuzzy = _fuzzy_match(pg_conn, user_term, candidate_dimensions)
    if fuzzy:
        return fuzzy

    # Pass 3: Synonym match
    synonym = _synonym_match(pg_conn, user_term, candidate_dimensions)
    if synonym:
        return synonym

    # No match — return empty, orchestrator will ask the user
    return []
```

### Entity Extraction Change (ADR-005 Amendment)

The combined intent + entity extraction prompt changes to output **raw filter terms** instead of resolved dimension:value pairs:

```
CURRENT (ADR-005):
  "entities": {
    "filters": [{"field": "generation", "operator": "=", "value": "Millennial"}]
  }
  ↑ LLM must guess BOTH the dimension AND the exact value

PROPOSED:
  "entities": {
    "filter_terms": ["Millennials", "small business"]
  }
  ↑ LLM just extracts the user's words. No guessing.
  ↑ Value catalog handles dimension identification + value resolution.
```

This simplifies the LLM's job from "understand Amex internal codes" to "identify which words are filter conditions" — a task LLMs are good at.

### Integration With Orchestrator

The value catalog lookup happens in the orchestrator (ADR-004) between vector search and graph validation:

```
Step 1: Per-entity vector search (pgvector)
Step 2: Confidence gate
Step 3: Near-miss detection
Step 4: Collect candidates for graph
    ↓
Step 4.5: VALUE CATALOG RESOLUTION  ← NEW
    For each filter_term from entity extraction:
    1. resolve_filter_value(user_term, candidate_dimensions)
    2. If match → add to filters with exact dimension:value
    3. If no match → ask user to select from available values
    4. If user selects → log as synonym suggestion
    ↓
Step 5: Graph validation (AGE)
...
```

The `candidate_dimensions` parameter narrows the search — if vector search already found `generation` and `bus_seg` as relevant dimensions, the catalog only searches those dimensions' values instead of all 250+ values across all dimensions.

---

## Scale Analysis

### Finance BU (Current)

| Metric | Count |
|--------|-------|
| Filterable string/yesno dimensions | 13 |
| High-cardinality (skip fuzzy) | 2 (card_prod_id, cmgn_cd) |
| Low-cardinality (catalog + fuzzy) | 11 |
| Total distinct values cataloged | ~70 |
| Extraction cost per refresh | $0.13 |
| Catalog table rows | ~70 |

### 3 BUs (Target — May 2026)

| Metric | Count |
|--------|-------|
| Filterable dimensions | ~46 |
| High-cardinality | ~6 |
| Low-cardinality | ~40 |
| Total distinct values | ~250 |
| Extraction cost per refresh | ~$0.46 |
| Annual refresh cost (daily) | ~$168 |
| Catalog table rows | ~250 |

### Enterprise Scale (Future — 8,000+ datasets)

Even at full enterprise scale, the catalog only grows with **curated LookML views**, not raw BQ tables. If every BU has ~50 filterable dimensions with ~10 values each:

| Metric | Count |
|--------|-------|
| BUs onboarded | 10 |
| Filterable dimensions | ~500 |
| Total distinct values | ~2,500 |
| Extraction cost per refresh | ~$5 |
| Annual refresh cost | ~$1,825 |
| Catalog table rows | ~2,500 |

2,500 rows. A trivial table by any measure. The extraction queries are partition-filtered (scanning one day of data per dimension), making each query sub-second and sub-penny.

---

## Consequences

### Positive
- Filter resolution becomes deterministic — no LLM guessing for coded values
- Zero-effort BU onboarding — extraction script runs on any LookML view automatically
- System improves over time — synonym learning from user interactions
- Simplifies the LLM's job — entity extraction only needs to identify filter phrases, not resolve them
- Same PostgreSQL instance — no new infrastructure, no new approvals
- Debuggable — every match has a type (exact/fuzzy/synonym) and can be traced

### Negative
- Adds one table and one extraction pipeline to maintain
- Daily BQ queries add ~$168/year cost (negligible but non-zero)
- Synonym review queue requires steward attention (but this is incremental, not upfront)
- High-cardinality dimensions (card_prod_id) still require users to know exact values

### Neutral
- Replaces the hardcoded `FILTER_VALUE_MAP` in orchestrator.py — that code is deleted
- Amends ADR-005 entity extraction contract — `filters` becomes `filter_terms`

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Fuzzy match returns wrong value (e.g., "Gen" matches "Gen Z" and "Gen X") | Medium | Medium | Return all fuzzy matches ranked by Levenshtein distance; disambiguate if multiple matches within threshold |
| High-cardinality dimension values change frequently (new campaigns) | Medium | Low | Daily refresh catches new values within 24 hours |
| Synonym learning produces incorrect mappings | Low | Medium | Steward approval gate — no synonym goes live without review |
| BQ extraction queries fail (permission, schema change) | Low | Low | Fallback to stale catalog (last successful refresh) + alert |
| User term matches values in multiple dimensions | Medium | Medium | Use vector search candidate_dimensions to narrow; if still ambiguous, ask user |

---

## Validation Plan

**Success criteria:**
- Filter resolution accuracy ≥ 95% on golden dataset queries that include filters
- Zero silent failures (wrong value passed, zero rows returned) on the 35 demo queries
- Value catalog refresh completes in < 60 seconds for all Finance BU dimensions
- Synonym learning captures ≥ 80% of new term mappings within first 2 weeks of usage

**Timeline to evaluate:**
- Week 1: Extraction pipeline + catalog table + exact/fuzzy match deployed
- Week 2: Synonym learning enabled, tested with demo queries
- Week 3: Evaluate against golden dataset, tune Levenshtein threshold

**What would trigger reconsidering:**
- If fuzzy matching produces > 5% false positives (wrong dimension matched) → tighten to exact + synonym only
- If BQ extraction costs exceed $50/month at scale → switch to sampling instead of full DISTINCT
- If synonym learning queue overwhelms stewards → add auto-approval for high-confidence matches (occurrence_count > 10)

---

## Related Decisions

- **ADR-004** (Semantic Layer Representation): Value catalog lives in the same PostgreSQL instance as pgvector and AGE. Extraction pipeline triggers alongside the LookML sync pipeline.
- **ADR-005** (Intent & Entity Classification): Entity extraction contract amended — `filters` field replaced with `filter_terms` (raw user phrases). The LLM no longer guesses dimension:value mappings.
- **ADR-006** (Metric Governance): Synonym enrichment follows the same steward workflow as business term definitions. Stewards manage synonyms through the same interface.
- **Orchestrator** (`src/retrieval/orchestrator.py`): `FILTER_VALUE_MAP` dict is replaced by `resolve_filter_value()` function querying the catalog. New step 4.5 added between vector search and graph validation.
