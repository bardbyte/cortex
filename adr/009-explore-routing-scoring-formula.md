# ADR-009: Explore Routing via LookML Structural Hierarchy

**Date:** March 13, 2026
**Status:** Accepted
**Decider:** Saheb
**Consulted:** Likhita, Rajesh
**Reviewers:** Sulabh, Ashok

---

## The Insight

LookML already encodes a natural hierarchy for how queries should be routed. We didn't invent this — we formalized what the model file already says:

```
  MEASURES define what you're analyzing         (highest routing signal)
       ↓
  DIMENSIONS define how you're slicing it       (secondary signal)
       ↓
  BASE VIEWS define where the data lives        (structural ground truth)
       ↓
  EXPLORES define which analytical lens to use  (the routing target)
```

A measure lives in a view. A view is the base view of exactly one explore. Therefore, **the measure tells you the explore.** That's the entire idea.

---

## The Problem

Our vector search already finds the right fields — 100% accuracy on measures and dimensions. But a field like `total_billed_business` lives in `custins`, and `custins` is reachable from 4 of 5 explores through JOINs:

```
                        ┌── finance_cardmember_360       (BASE view = custins)
                        │
  total_billed_business ├── finance_merchant_profitability (JOIN to custins)
  (lives in custins)    ├── finance_travel_sales           (JOIN to custins)
                        └── finance_customer_risk          (JOIN to custins)
```

All four explores can technically serve this field. Only one was **designed** for it — the one whose `from:` clause points to `custins`. The routing formula must encode that structural difference.

---

## The Formula

```
score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus
```

Four signals, multiplicatively composed. Each encodes a different kind of evidence:

| Signal | What it captures | Range | Why multiplicative |
|--------|-----------------|-------|-------------------|
| `coverage³` | Can this explore serve ALL the entities? | 0.0 – 1.0 | If coverage = 0, score must be 0 (can't route here) |
| `mean_sim` | How well do the field descriptions match? | 0.0 – 1.0 | If similarity = 0, no match (score must be 0) |
| `base_view_bonus` | Is this explore's home table the primary data source? | 1.0 – 2.0 | The structural signal — doubles score when fields come from the base view |
| `desc_sim_bonus` | Does the explore's description match the query? | 1.0 – ~1.2 | Tiebreaker when structural signal can't discriminate |

### Why Multiplicative, Not Additive

Additive: `a + b + c` — a high score on one dimension compensates for zero on another. An explore with 0% coverage but great description match would still score well. That's wrong — you can't route to an explore that can't serve the query's fields.

Multiplicative: `a × b × c` — any zero kills the whole score. This is correct: coverage, similarity, and structural match are all *jointly necessary*, not independently sufficient.

### Base View Bonus: The Core Mechanism

Every explore has a `from:` declaration in LookML — its **base view**. This is the SQL `FROM` table, the analytical grain, the reason the explore exists.

```python
# Derived from LookML model file `from:` declarations
EXPLORE_BASE_VIEWS = {
    "finance_cardmember_360":        "custins_customer_insights_cardmember",
    "finance_merchant_profitability": "fin_card_member_merchant_profitability",
    "finance_travel_sales":          "tlsarpt_travel_sales",
    "finance_card_issuance":         "gihr_card_issuance",
    "finance_customer_risk":         "risk_indv_cust",
}
```

When computing the bonus, **measures count 2x and dimensions count 1x**, because the measure defines the analytical grain:

```
Query: "Total billed business by generation"
  E1: measure   "total billed business" → custins        (weight = 2.0)
  E2: dimension "generation"            → cmdl_card_main (weight = 1.0)

  finance_cardmember_360  (base = custins):
    E1 from base view ✓ (sim 0.78 ≥ 0.65 floor) → weighted match = 2.0
    E2 from joined view                           → weighted match = 0.0
    base_view_ratio = 2.0 / 3.0 = 0.67 → bonus = 1.67x

  finance_merchant_profitability (base = fin_merchant):
    Neither entity from base view → bonus = 1.0x

  cardmember_360 wins by 1.67x on structure alone.
```

A base-view match only counts if `similarity ≥ 0.65` — this prevents a low-quality vector match from getting amplified by structural signal.

### Description Similarity: The Tiebreaker

When all entities come from a universally-joined view (like `cmdl_card_main` — demographics, joined in all 5 explores), the base_view_bonus is 1.0 for everyone. The formula needs a fallback signal.

Each explore has a `description` in LookML. We embed these once, then compare against the query:

```
Query: "Generation breakdown of Apple Pay enrollment"

  All entities from cmdl_card_main → base_view_bonus = 1.0 for ALL explores

  Explore descriptions:
    cardmember_360:        "customer activity, demographics, segmentation..." → sim = 0.82
    merchant_profitability: "merchant category, ROC metrics, dining..."       → sim = 0.61

  desc_sim_bonus: cardmember_360 = 1.16  vs  merchant = 1.12
  → Correct routing via description match alone.
```

The coefficient is 0.2 — intentionally small. This is a tiebreaker, not a primary signal.

---

## Worked Example: End to End

**Query:** *"What is the highest billed business by merchant category?"*

```
Step 1: Entity Extraction
  ┌─────────────────────────────────────────────┐
  │  E1: measure   "max merchant spend"  w=2.0  │
  │  E2: dimension "merchant category"   w=1.0  │
  └─────────────────────────────────────────────┘

Step 2: Vector Search (field_type filtered)
  ┌─────────────────────────────────────────────────────────────┐
  │  E1 → max_merchant_spend    view=fin_merchant   sim=0.7810 │
  │  E2 → oracle_mer_hier_lvl3  view=fin_merchant   sim=0.7706 │
  └─────────────────────────────────────────────────────────────┘

Step 3: Scoring
  ┌──────────────────────────────────────────────────────────────────┐
  │  finance_merchant_profitability (base = fin_merchant)            │
  │    coverage      = 2/2 = 1.0         → 1.0³ = 1.000            │
  │    mean_sim      = 0.776                                        │
  │    base_view     = fin_merchant ✓ (both entities from base!)    │
  │    bv_ratio      = (2.0+1.0)/(2.0+1.0) = 1.0 → bonus = 2.0x   │
  │    desc_sim      ≈ 1.14                                         │
  │    ─────────────────────────────────                            │
  │    score = 1.0 × 0.776 × 2.0 × 1.14 = 1.769  ← WINNER        │
  ├──────────────────────────────────────────────────────────────────┤
  │  finance_cardmember_360                                         │
  │    coverage = 0/2 = 0.0 → score = 0.0  (doesn't join fin_merch)│
  └──────────────────────────────────────────────────────────────────┘

Result: merchant_profitability wins ✓
```

---

## Current Results

```
  Explore selection:    6/6  (100.0%)
  Measure retrieval:    7/7  (100.0%)
  Dimension retrieval:  3/3  (100.0%)
  Fully correct:        6/6  (100.0%)
```

---

## Filter/WHERE Clause Resolution

Once the explore is selected, the pipeline must resolve filter expressions from natural language into Looker-compatible filter values. This is the gap between "found the right fields" and "produced a correct query."

### The Problem

The LLM extracts filters as `{field_hint: "generation", values: ["Millennial"], operator: "="}`. These raw values must be translated to exact LookML values before Looker can execute the query. "millennials" ≠ "Millennial" in SQL.

Additionally, each explore has a **mandatory partition filter** with a **different field name**:

```
  finance_cardmember_360        → partition_date   (always_filter)
  finance_merchant_profitability → partition_date
  finance_travel_sales          → booking_date     ← DIFFERENT
  finance_card_issuance         → issuance_date    ← DIFFERENT
  finance_customer_risk         → partition_date
```

Hardcoding `partition_date` for all explores produces wrong SQL for 2 of 5 explores.

### The Architecture

```
  Entity Extraction (vector.py)
       │
       │  Filters extracted as {field_hint, values[], operator}
       │  BUT not resolved — raw user language
       ▼
  Explore Scoring (pipeline.py, Steps 1-3)
       │
       │  Top explore selected via multiplicative formula
       ▼
  Filter Resolution (filters.py, Step 4)    ← NEW
       │
       │  5-pass value resolution:
       │    Pass 1: Exact match       "millennial" → "Millennial"     (conf: 1.0)
       │    Pass 2: Synonym           "Gen Y" → "Millennial"          (conf: 0.85)
       │    Pass 3: Fuzzy (Lev ≤ 2)   "Millenial" → "Millennial"     (conf: 0.89)
       │    Pass 4: Embedding sim      (TODO — for creative phrasings)
       │    Pass 5: Passthrough        unresolved, flag for user      (conf: 0.3)
       │
       │  + Mandatory partition filter injected per-explore
       │  + Multi-value accumulation ("Gold,Platinum" for IN clauses)
       │  + Negation detection ("not Gold" → "-GOLD" Looker syntax)
       │  + Numeric range parsing ("between 1000 and 5000" → "[1000,5000]")
       │  + Time normalization ("Q4 2025" → "2025-10-01 to 2025-12-31")
       ▼
  PipelineResult with filters dict ready for Looker MCP
```

**Key design choice:** Synonyms are checked BEFORE fuzzy matching. Domain knowledge is more precise than edit distance — "Gen Y" must resolve to "Millennial" (synonym), not "Gen Z" (Levenshtein distance 1).

**Safety guard:** Fuzzy matching skips inputs shorter than 3 characters. Short strings have enormous Levenshtein neighborhoods — "y" is distance 1 from "no" and distance 2 from "yes", producing false positives.

### Worked Example: Query 6

**Query:** *"How many Millennial customers have Apple Pay enrolled and are active?"*

```
Step 4: Filter Resolution (explore = finance_cardmember_360)

  Filter 1: generation = "Millennial"
    Pass 1 (exact): "millennial" found in FILTER_VALUE_MAP → "Millennial" ✓
    Confidence: 1.0

  Filter 2: apple_pay_wallet_flag = "enrolled"
    Pass 1 (exact): "enrolled" found in FILTER_VALUE_MAP → "Y" ✓
    Confidence: 1.0

  Filter 3: is_active_standard = "yes"
    Yesno shortcut: "yes" → "Yes" ✓
    Confidence: 1.0

  Mandatory: partition_date = "last 90 days" (auto-injected)

  Final Looker filters:
    {
      "partition_date": "last 90 days",
      "generation": "Millennial",
      "apple_pay_wallet_flag": "Y",
      "is_active_standard": "Yes"
    }
```

### What the Filter System Handles Today

| Filter Type | Example | Status |
|-------------|---------|--------|
| Categorical equality | `bus_seg = "OPEN"` | Working (Pass 1) |
| Yes/No | `is_active = "Yes"` | Working (yesno shortcut) |
| Time range | `partition_date = "last 90 days"` | Working (explore-aware injection) |
| Typos | `"Millenial"` → `"Millennial"` | Working (Pass 3 fuzzy) |
| Synonyms | `"Gen Y"` → `"Millennial"` | Working (Pass 2 synonym) |
| Multi-value (OR) | `"Gold,Platinum"` | Working (comma accumulation) |
| Mandatory partition | Auto-injected per explore | Working (EXPLORE_PARTITION_FIELDS) |

### Filter Capabilities Status

| Feature | Status | Implementation |
|---------|--------|---------------|
| Negation | DONE | `_detect_negation()` strips prefixes, Looker `-VALUE` syntax |
| Numeric ranges | DONE | `resolve_numeric_filter()` → `[N,M]`, `>N`, `<N` |
| Time normalization | DONE | `normalize_time_expression()` handles Q4/relative/year |
| Multi-value OR | DONE | Comma accumulation in `to_looker_filters()` |
| Embedding similarity | TODO (P1) | Pass 4 for creative phrasings and high-cardinality dims |
| Relative comparisons | Out of scope | "above average" requires subquery |
| Implicit filters | Out of scope | "high-value customers" requires business rule engine |

---

## Scalability Analysis: From 5 Explores to 10,000 Datasets

### The Compression Insight

10,000 datasets x 150 columns = 1.5M raw BQ columns. That number is a red herring. What matters is **curated LookML fields** — what we actually expose to users.

Measured curation ratio: **4.6%** (`cmdl_card_main` exposes 23 of 500+ BQ columns). The semantic layer is a compression function. The scale problem is 20x smaller than the raw numbers suggest.

| Scale | BUs | Explores | Views | Total Fields | Filterable Dims | Value Map Entries | Memory |
|-------|-----|----------|-------|-------------|----------------|------------------|--------|
| Current (1 BU) | 1 | 5 | 7 | 113 | 12 | ~70 | 15 KB |
| May 2026 (3 BUs) | 3 | 15 | 21 | ~340 | ~36 | ~1,700 | 400 KB |
| 2027 target (10 BUs) | 10 | 50 | 70 | ~1,130 | ~120 | ~5,800 | 1.3 MB |
| Max scale (100 BUs) | 100 | 500 | 700 | ~11,300 | ~1,200 | ~58,000 | 13 MB |

### Runtime Resolution: Never a Bottleneck

The 5-pass cascade is **O(1) per filter** at any catalog size because lookup is per-dimension (`FILTER_VALUE_MAP[dim].get(val)`), not across all dimensions. Adding 100 new dimensions doesn't slow resolution of existing ones.

Filter resolution is **0.01%-0.2% of total query latency** (50us-800us vs 400ms LLM call). The multiplicative scoring formula is O(E x N) where E = explores, N = entities — at 500 explores x 5 entities, that's 2,500 multiplications. Still sub-millisecond.

### No Phase Transition

There is no point where the approach fundamentally breaks. The curve is smooth:

- Python dict handles 58K entries in 13MB with O(1) lookup
- Memory is linear in catalog size, and 13MB is negligible
- Lookup time is constant regardless of catalog growth

The three issues to address are all bounded:

1. **Namespace collisions at 3 BUs** (P0, 2-4 hours) — **IMPLEMENTED** (view.dim composite keys)
2. **BQ SELECT DISTINCT for raw-column dims** (P0, 3-5 days, Ravikanth) — 8 of 11 filterable dims are just `${TABLE}.column_name` with no LookML-derivable values
3. **Pass 4 embedding similarity for high-cardinality dims** (P1, 3-5 days) — dims with 100+ values need fuzzy semantic matching, not enumeration

### Build-Time Scaling

| Operation | Current (5 explores) | 3 BUs (15 explores) | 100 BUs (500 explores) |
|-----------|---------------------|---------------------|----------------------|
| LookML parse | 0.2s | 0.6s | 3.5s |
| BQ SELECT DISTINCT | N/A (not yet) | ~1 min (36 dims, 10 concurrent) | ~9 min (1,200 dims, 10 concurrent) |
| Filter catalog generation | 0.1s | 0.3s | 2.0s |

**Incremental builds:** In steady state, 0-3 views change per day. Full rebuild is never needed after initial setup — `--mode catalog` processes only changed views when run incrementally.

### The Abhishek Challenge: Final Verdict

**"Right about manual synonyms, wrong about synonyms as a concept."**

Manual `SYNONYM_MAP`: 3 groups, 13 entries. Phase transition at ~100 dimensions — he's correct that manual curation doesn't survive. One developer can't know the vocabulary of 10 BUs.

Auto-derived from LookML descriptions: **23 groups, zero maintenance.** The `"Also known as:"` convention in LookML `description` fields is parsed by `--mode catalog` and generates synonym groups automatically. Adding a BU = add "Also known as:" to descriptions + run `--mode catalog`. No code changes, no manual mapping.

**The real scaling bottleneck isn't filter resolution — it's upstream entity extraction accuracy.** Going from 12 filterable dimensions to 120 makes the LLM's classification problem 10x harder. Filter resolution will keep working at any scale; the question is whether the LLM can identify the right dimension in the first place when there are 120 candidates instead of 12.

**The response to Abhishek:** "The hardcoded map didn't survive past Phase 1 — we've already moved to auto-derivation. 23 synonym groups are generated from LookML with zero manual maintenance. The architecture scales to 100 BUs with a 13MB in-memory catalog and sub-millisecond lookup. The constraint we should worry about is entity extraction accuracy at high dimension counts, not filter resolution."

### Architecture Changes by Scale Trigger

| Change | Priority | Scale Trigger | Effort | Risk if Skipped |
|--------|----------|--------------|--------|-----------------|
| Namespace value map (view.dim keys) | P0 | 3 BUs | 2-4 hours | Incorrect filter resolution across BUs — **DONE** |
| BQ SELECT DISTINCT (Phase 2) | P0 | 3 BUs | 3-5 days | 8/11 dims stuck on hardcoded, can't auto-derive |
| Embedding similarity (Pass 4) | P1 | 10 BUs | 3-5 days | High-cardinality dims always go to passthrough |
| PostgreSQL catalog table | P2 | 30 BUs | 2-3 days | 1.3s startup time (acceptable) |
| Model-level sharding | P3 | 100 BUs | 1-2 days | Unnecessary for foreseeable future |

### Auto-Derivation Pipeline: What's Built vs What's Planned

**Current state (Phase 1, DONE):**

- `python -m scripts.load_lookml_to_pgvector --mode catalog` generates `config/filter_catalog.json`
- LookML CASE values: 3 dims auto-derived (generation, travel_vertical, air_trip_type)
- "Also known as:" synonyms: 23 dimension groups auto-derived
- Yesno dimensions: 8 auto-derived (100% coverage)
- Partition fields: 5 auto-derived (100% coverage)
- Explore-to-view mappings: auto-derived for namespace resolution
- `filters.py` merges auto-derived + hardcoded at import time

**Phase 2 (PLANNED, 3-5 days):**

- BQ `SELECT DISTINCT` for raw-column dimensions
- Fills the 8 dims where LookML SQL is just `${TABLE}.column_name`
- Scheduled job aligned with `daily_refresh` datagroup
- Incremental: only re-query BQ for dims whose table has refreshed

**Phase 3 (PLANNED, when at 3 BUs):**

- Learning loop: log Pass 5 (passthrough) resolutions
- Weekly steward review of unresolved terms
- Confirmed mappings auto-added to catalog
- Completeness: starts at 80%, asymptotically approaches 100%

### The Assumption That Could Break Everything

If Renuka's Lumi auto-generates LookML views from BQ `INFORMATION_SCHEMA` (100% of columns instead of 4.6%), all numbers in the scale table go 20x. The 13MB catalog becomes 260MB. The 1,200 filterable dims become 24,000. The entity extraction problem becomes intractable.

**Fix:** Tag dims as `tags: ["filterable"]` in LookML to restore curation. The filter catalog only processes dims with this tag (or dims in explores with `always_filter`). This must be agreed with Renuka before Lumi auto-generation goes live.

---

## Where This Breaks at Scale

### Problem 1: Shared Base Views (50+ explores)

Today all 5 explores have unique base views. When BU2 adds explores, some will share:

```
  finance_cardmember_360:              base = custins
  marketing_cardmember_segmentation:   base = custins  ← SAME

  Query about billed business → both get base_view_bonus = 2.0 → TIE
```

**Impact:** At 50 explores with ~25 unique base views, roughly half of queries hit a tie.

**Fix:** `desc_sim_bonus` handles mild overlap. For heavy overlap (5+ explores on same base), we need a stronger signal — likely query-log-based explore frequency or explicit `canonical: yes` tagging in LookML.

**Trigger to revisit:** More than 3 explores share the same base view.

### Problem 2: Hardcoded Mappings Don't Scale

`EXPLORE_BASE_VIEWS` and `EXPLORE_DESCRIPTIONS` are dicts in `constants.py`. At 50 explores, someone will forget to update them. The forgotten explore silently gets `base_view_bonus = 1.0` forever.

**Fix:** Auto-derive from LookML at pipeline setup. The parser already extracts this:

```
LookML Model File
    │  LookMLParser.parse_model_explores()
    │  (already extracts base_view from `from:` clause)
    ▼
explore_metadata TABLE (new)
    ┌──────────────────────────┬──────────────────────┬────────────────────┐
    │ explore_name             │ base_view            │ description        │
    ├──────────────────────────┼──────────────────────┼────────────────────┤
    │ finance_cardmember_360   │ custins_customer_... │ "Comprehensive..." │
    │ finance_merchant_profit  │ fin_card_member_...  │ "Analyze card..."  │
    │ ...                      │ ...                  │ ...                │
    └──────────────────────────┴──────────────────────┴────────────────────┘
    │
    │  _load_explore_base_views()  ← cached at pipeline init, fallback to dict
    ▼
Pipeline scoring (no hardcoded dict needed)
```

**Implementation:** Add `explore_metadata` table to schema setup. Populate from `parse_model_explores()` during `setup_local.sh`. Pipeline loads at init with `@lru_cache`, falling back to the hardcoded dict if the table doesn't exist.

### Problem 3: Magic Numbers Need Calibration

| Parameter | Value | Reasoning | Calibration |
|-----------|-------|-----------|-------------|
| Coverage exponent | 3 | Steep penalty for partial matches | Grid search {2, 3, 4} on golden dataset |
| Measure weight | 2.0 | Measures define analytical grain | Validate on 30+ mixed-entity queries |
| Desc sim coefficient | 0.2 | Must be tiebreaker, not primary | Sensitivity analysis on expanded set |
| Similarity floor | 0.65 | Observed: good >0.65, noise <0.60 | ROC curve on golden dataset |

**Dependency:** Golden dataset (66+ queries from Animesh) required before calibration. Current values are structurally reasoned defaults.

### Problem 4: Comma-Separated Explore Names

The vector store has `explore_name = "explore_1,explore_2,...,explore_30"`. At 50 explores, this is a long string being parsed in the hot path. Not a correctness issue, but architecturally fragile.

**Fix:** The `explore_field_index` relational table already stores (explore, field) pairs correctly. Use it as the source of truth for "which explores contain this field" instead of parsing CSV from pgvector results. This is a refactor, not a redesign.

---

## What Needs to Happen Next

| Priority | Task | Owner | Status |
|----------|------|-------|--------|
| **P0** | ~~Delete duplicate FILTER_VALUE_MAP from `orchestrator.py`~~ | Rajesh | DONE |
| **P0** | ~~Namespace value map (view.dim composite keys)~~ | Rajesh | DONE |
| **P0** | ~~Negation detection ("not Gold" → "-GOLD")~~ | Likhita | DONE |
| **P0** | ~~Time normalization ("Q4 2025" → "2025-10-01 to 2025-12-31")~~ | Ayush | DONE |
| **P0** | ~~Numeric range parsing ("between 1000 and 5000" → "[1000,5000]")~~ | Ayush | DONE |
| **P0** | ~~Auto-derive filter catalog from LookML (Phase 1)~~ | Ravikanth | DONE |
| **P0** | Expand golden set to 30+ queries (all 5 explores) — include filter test cases | Animesh | In progress |
| **P0** | Implement `explore_metadata` auto-derivation (base_view, description, partition_field) | Rajesh | Schema DDL |
| **P0** | BQ SELECT DISTINCT for raw-column dims (Phase 2) | Ravikanth | 3-5 days |
| **P1** | Calibrate 4 scoring magic numbers via grid search | Likhita | Blocked on golden dataset |
| **P1** | Replace CSV explore_name parsing with explore_field_index lookup | Rajesh | — |
| **P1** | Implement Pass 4 embedding similarity for high-cardinality dims | Ravikanth | 3-5 days |
| **P2** | LookML CI check: explore descriptions must be non-empty, >20 words | Ayush | — |
| **P2** | Shared-base-view stress test (simulate 50 explores) | Likhita | Blocked on BU2 model files |
| **P2** | PostgreSQL catalog table (replace in-memory dict at 30 BUs) | Ravikanth | Not yet needed |

---

## Key Files

| File | Role |
|------|------|
| `src/retrieval/pipeline.py` | 5-step pipeline: entity extraction → desc similarity → scoring → **filter resolution** → return |
| `src/retrieval/filters.py` | Filter resolution engine: 5-pass value resolution, partition field injection, multi-value handling |
| `config/constants.py` | EXPLORE_BASE_VIEWS, EXPLORE_DESCRIPTIONS, SIMILARITY_FLOOR |
| `config/filter_catalog.json` | Auto-derived filter catalog (generated by `--mode catalog`) |
| `scripts/load_lookml_to_pgvector.py` | LookML parser, per-view embedding strategy, `--mode catalog` for filter auto-derivation |
| `scripts/run_e2e_test.py` | 6-query golden set accuracy test |
| `lookml/finance_model.model.lkml` | Source of truth for `always_filter` partition field declarations |

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────────┐
│  EXPLORE ROUTING                                                     │
│  score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus    │
│                                                                      │
│  coverage³         Missing 1 of 3 → 0.67³ = 0.30 (harsh penalty)   │
│  mean_sim          Good: >0.70   Marginal: 0.60-0.70                │
│  base_view_bonus   Up to 2.0x if measure from `from:` view          │
│                    Measures 2x, dims 1x. Floor: sim ≥ 0.65          │
│  desc_sim_bonus    Tiebreaker (0.2 coeff) when base view ties       │
├─────────────────────────────────────────────────────────────────────┤
│  FILTER RESOLUTION                                                   │
│  Pass 1: Exact    → FILTER_VALUE_MAP lookup         (conf: 1.0)    │
│  Pass 2: Synonym  → SYNONYM_MAP → value map         (conf: 0.85)   │
│  Pass 3: Fuzzy    → Levenshtein ≤ 2, len ≥ 3        (conf: ~0.85)  │
│  Pass 4: Embed    → cosine sim to known values       (TODO)         │
│  Pass 5: Pass     → unresolved, flag for user        (conf: 0.3)   │
│                                                                      │
│  Auto-derivation:  --mode catalog → filter_catalog.json              │
│  Namespace:        value maps keyed by view.dimension,               │
│                    flattened for backward compat                      │
│  Capabilities:     negation ✓  numeric ✓  time ✓  multi-value ✓     │
│                                                                      │
│  Partition fields:  cardmember/merchant/risk → partition_date        │
│                     travel → booking_date                            │
│                     issuance → issuance_date                         │
│  Multi-value:       "Gold,Platinum" (comma-separated for IN clause) │
└─────────────────────────────────────────────────────────────────────┘
```
