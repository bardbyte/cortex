Now I have everything I need. Let me write this comprehensive breakdown.

---

# Cortex Pipeline: Full First-Principles Breakdown

## PART 1: Step-by-Step Trace with Exact I/O

**Query:** "Total billed business by generation for small businesses"

This query is interesting because it exercises every hard problem simultaneously: semantic matching ("billed business"), derived dimension ("generation" is a CASE statement on birth_year), coded filter value ("small businesses" maps to bus_seg = "OPEN"), cross-view join (custins + cmdl), and mandatory partition filter injection.

---

### STEP 0: User Query Arrives

**Component:** ChatGPT Enterprise connector (or CLI)

**Input:**
```
raw_string: "Total billed business by generation for small businesses"
type: str
bytes: 56
```

**Output (CortexState initialized):**
```python
CortexState(
    user_query="Total billed business by generation for small businesses",
    conversation_history=[],
    intent="",
    entities={},
    retrieval_result={},
    # ... all other fields at defaults
)
```

**Latency budget:** <1ms (string assignment)

**Failure modes:** None at this step. The string is opaque.

**Invariant:** `len(state.user_query) > 0`

---

### STEP 1: Intent Classification + Entity Extraction

**Component:** Gemini Flash via SafeChain (single LLM call, per ADR-005)

**Input to LLM:**
```python
prompt = CLASSIFY_AND_EXTRACT_PROMPT.format(
    business_terms_context="""
    Available terms: billed business (total spend), active customers,
    generation (demographic cohort), business segment (CPS/OPEN/GCS/GMNS),
    customer tenure, card product, merchant category, ...
    """,
    previous_context="None (first turn)",
    query="Total billed business by generation for small businesses"
)
```

**Output from LLM (structured JSON):**
```json
{
  "intent": "data_query",
  "confidence": 0.96,
  "entities": {
    "metrics": ["total billed business"],
    "dimensions": ["generation"],
    "filter_terms": ["small businesses"],
    "time_range": null,
    "sort": null,
    "limit": null
  }
}
```

**Latency budget:** ~200-400ms (SafeChain round-trip to Gemini Flash)

**What CortexState gets:**
```python
state.intent = "data_query"
state.complexity = "moderate"        # cross-view + filter
state.is_answerable = True
state.entities = {
    "metrics": ["total billed business"],
    "dimensions": ["generation"],
    "filter_terms": ["small businesses"],  # RAW user terms per ADR-007
    "time_range": None,
}
```

**Failure modes:**
| Failure | Probability | Impact | Detection |
|---------|-------------|--------|-----------|
| LLM classifies as `out_of_scope` | Low | Query dropped | Confidence < 0.7 triggers fallback to ReAct |
| "small businesses" extracted as dimension instead of filter | Medium | Wrong field selection | Evaluation catches: precision/recall on filter extraction |
| "generation" missed entirely | Low | Missing GROUP BY | Dimension recall < 1.0 in golden eval |
| LLM hallucinates entity not in query | Low | Extra field in query | Dimension precision < 1.0 |

**Mathematical invariant:**
```
For a correct extraction:
  |extracted_metrics ∩ expected_metrics| / |expected_metrics| >= 0.9  (recall)
  |extracted_metrics ∩ expected_metrics| / |extracted_metrics| >= 0.9  (precision)
Same for dimensions and filter_terms.
```

**The key insight here:** ADR-007 changes the LLM's job. It no longer guesses "bus_seg = OPEN". It just extracts the raw phrase "small businesses" and passes it to the deterministic value catalog. This is the right decomposition: LLMs are good at linguistic parsing, bad at knowing Amex internal codes.

---

### STEP 2: Per-Entity Vector Search (pgvector)

**Component:** `RetrievalOrchestrator._vector_search_per_entity()` calling `vector.search()`

**The orchestrator makes 3 separate vector searches** (one per entity: 1 metric + 1 dimension + 1 filter term):

#### Search 2a: Metric "total billed business"

**Input:**
```python
# Text sent to embedding model:
embed_text = "total billed business"

# Embedding call:
embedding = embed_fn("total billed business")
# Returns: list[float] of length 768
# e.g. [0.0234, -0.1567, 0.0892, ..., 0.0445]  (768 values)
```

**SQL executed:**
```sql
SELECT field_key, field_name, field_type, view_name, explore_name,
       model_name, label, group_label, tags, content,
       1 - (embedding <=> '[0.0234,-0.1567,...,0.0445]'::vector) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
  AND model_name = 'finance'
ORDER BY embedding <=> '[0.0234,-0.1567,...,0.0445]'::vector
LIMIT 20;
```

**Output:**
```python
[
    FieldCandidate(
        field_name="total_billed_business",
        field_type="measure",
        data_type="number",
        view="custins_customer_insights_cardmember",
        explore="finance_cardmember_360",
        model="finance",
        description="Sum of all billed business across card members...",
        score=0.96,
        source="vector",
        group_label="Spending",
        synonyms=["total spend", "billing volume", "charged amount"],
    ),
    FieldCandidate(
        field_name="avg_billed_business",
        field_type="measure",
        ...
        score=0.91,
        source="vector",
    ),
    FieldCandidate(
        field_name="billed_business",   # the dimension, not the measure
        field_type="dimension",
        ...
        score=0.89,
        source="vector",
    ),
    FieldCandidate(
        field_name="total_merchant_spend",
        ...
        score=0.82,
        source="vector",
    ),
    # ... up to 20 results
]
```

**Wrapped in:**
```python
EntitySearchResult(
    entity_text="total billed business",
    entity_role="metric",
    candidates=[...],  # the 20 FieldCandidates above
    top_score=0.96,
    near_miss=False,   # 0.96 - 0.91 = 0.05, right at NEAR_MISS_DELTA
)
```

#### Search 2b: Dimension "generation"

**Embedding input:** "generation"

**Top results:**
```python
EntitySearchResult(
    entity_text="generation",
    entity_role="dimension",
    candidates=[
        FieldCandidate(field_name="generation", view="cmdl_card_main",
                       explore="finance_cardmember_360", score=0.95, ...),
        FieldCandidate(field_name="birth_year", view="cmdl_card_main",
                       explore="finance_cardmember_360", score=0.78, ...),
    ],
    top_score=0.95,
    near_miss=False,  # 0.95 - 0.78 = 0.17 >> 0.05
)
```

#### Search 2c: Filter term "small businesses"

**Embedding input:** "small businesses"

**Top results (this is where vector search is WEAK):**
```python
EntitySearchResult(
    entity_text="small businesses",
    entity_role="filter",
    candidates=[
        FieldCandidate(field_name="bus_seg", view="custins_customer_insights_cardmember",
                       explore="finance_cardmember_360", score=0.84,
                       description="Business segment: CPS, OPEN, Commercial..."),
        FieldCandidate(field_name="business_org", view="custins_customer_insights_cardmember",
                       explore="finance_cardmember_360", score=0.79, ...),
        FieldCandidate(field_name="business_revenue", view="custins_customer_insights_cardmember",
                       explore="finance_cardmember_360", score=0.76, ...),
    ],
    top_score=0.84,
    near_miss=True,  # 0.84 - 0.79 = 0.05, exactly at NEAR_MISS_DELTA
)
```

**Latency:** ~30ms per search x 3 searches = ~90ms total (parallelizable to ~30ms)

**Failure modes:**
| Failure | Probability | Impact |
|---------|-------------|--------|
| "total billed business" matches `billed_business` (dimension) instead of `total_billed_business` (measure) | Low | Wrong field type, wrong SQL aggregation |
| "small businesses" matches `business_revenue` instead of `bus_seg` | Medium | Wrong dimension entirely |
| Embedding model drift (fine-tuned model degrades) | Low | Gradual accuracy decline across all queries |

**Mathematical invariant:**
```
For every EntitySearchResult r:
  r.top_score == r.candidates[0].score
  r.candidates is sorted by score descending
  all(0.0 <= c.score <= 1.0 for c in r.candidates)
  len(r.candidates) <= MAX_VECTOR_RESULTS (20)

For near_miss detection:
  r.near_miss == True  iff  len(r.candidates) >= 2
                        and  r.candidates[0].score - r.candidates[1].score < NEAR_MISS_DELTA (0.05)
```

**Why per-entity search matters (not a single combined embedding):** If you embed the full query "Total billed business by generation for small businesses" as one vector, the resulting embedding is a weighted average of all concepts. It might be 0.85 similar to `total_billed_business` and 0.80 similar to `generation` -- worse than each individually. Per-entity search gets 0.96 and 0.95 respectively. The precision gain is significant.

---

### STEP 3: Confidence Gate

**Component:** `RetrievalOrchestrator._all_below_confidence_floor()`

**Input:** The 3 `EntitySearchResult` objects from Step 2

**Logic:**
```python
all_below = all(r.top_score < 0.70 for r in entity_results)
# 0.96 < 0.70? No.  →  all_below = False  →  Continue.
```

**Output:** `False` (at least one entity has score >= 0.70)

**Latency:** <0.1ms (pure comparison)

**Failure mode:** If the floor is set too high (e.g., 0.95), legitimate queries get rejected. If too low (e.g., 0.50), garbage queries pass through.

**Mathematical invariant:**
```
confidence_gate_passes iff ∃ r ∈ entity_results : r.top_score >= SIMILARITY_FLOOR
```

**The SIMILARITY_FLOOR = 0.70 is empirically set for v1.** With 41 fields and well-enriched descriptions (synonyms in every field description), anything below 0.70 is genuinely unrelated. This threshold needs recalibration when:
- Adding BUs with overlapping terminology
- Changing the embedding model
- Exceeding 200 fields (more semantic neighbors = lower absolute scores)

---

### STEP 4: Near-Miss Detection

**Component:** `RetrievalOrchestrator._detect_near_misses()`

**Input:** The 3 `EntitySearchResult` objects

**Logic per entity:**
```
"total billed business": top=0.96, runner_up=0.91, delta=0.05 → near_miss=False
                         (delta=0.05 is NOT < NEAR_MISS_DELTA=0.05, it's equal)
                         Actually: 0.05 < 0.05 is False → near_miss=False

"generation":            top=0.95, runner_up=0.78, delta=0.17 → near_miss=False

"small businesses":      top=0.84, runner_up=0.79, delta=0.05 → near_miss=False
                         (same edge case: equal to threshold)
```

**Note:** There is a subtle bug potential here. The code uses strict `<` not `<=`. At delta=0.05 exactly, near_miss is False. This is the intended behavior: the threshold means "strictly closer than delta." If you want to include the boundary, change to `<=`. For this query, bus_seg vs business_org is not flagged as a near miss.

**Output:** All `EntitySearchResult` objects have `near_miss=False` (no modification)

**Latency:** <0.1ms

**Invariant:**
```
∀ r: r.near_miss == True → len(r.candidates) >= 2 ∧ (r.candidates[0].score - r.candidates[1].score < δ)
```

---

### STEP 4.5: Value Catalog Resolution (ADR-007)

**Component:** `resolve_filter_value()` (from the value catalog table)

**Input:**
```python
user_term = "small businesses"          # from entities.filter_terms[0]
candidate_dimensions = ["bus_seg", "business_org"]  # from vector search top results
```

**Three-pass resolution:**

**Pass 1: Exact match**
```sql
SELECT dimension_name, raw_value, 'exact' AS match_type
FROM dimension_value_catalog
WHERE LOWER(raw_value) = LOWER('small businesses')
  AND dimension_name IN ('bus_seg', 'business_org')
LIMIT 5;
```
Result: **Empty.** No BQ value literally says "small businesses."

**Pass 2: Fuzzy match (Levenshtein)**
```sql
SELECT dimension_name, raw_value, 'fuzzy' AS match_type,
       levenshtein(LOWER(raw_value), LOWER('small businesses')) AS distance
FROM dimension_value_catalog
WHERE dimension_name IN ('bus_seg', 'business_org')
  AND is_high_cardinality = FALSE
  AND levenshtein(LOWER(raw_value), LOWER('small businesses')) <= 2
ORDER BY distance ASC
LIMIT 5;
```
Result: **Empty.** "OPEN" has Levenshtein distance of 13 from "small businesses." No fuzzy match.

**Pass 3: Synonym match**
```sql
SELECT dimension_name, raw_value, 'synonym' AS match_type
FROM dimension_value_catalog
WHERE dimension_name IN ('bus_seg', 'business_org')
  AND 'small businesses' = ANY(synonyms)  -- or ILIKE match against array
LIMIT 5;
```
Result:
```python
[{
    "dimension_name": "bus_seg",
    "raw_value": "OPEN",
    "match_type": "synonym",
    "display_label": "OPEN (Small Business)",
    "confidence": 1.0,
}]
```

This works because the value catalog has `synonyms: ["small business", "SMB"]` for the OPEN row in bus_seg, either from initial seeding (current FILTER_VALUE_MAP) or from learned synonyms.

**Output:**
```python
resolved_filter = {"bus_seg": "OPEN"}
```

**Latency:** ~5-15ms (3 SQL queries against small table, ~250 rows at 3 BUs)

**Failure modes:**
| Failure | Probability | Impact | Detection |
|---------|-------------|--------|-----------|
| "small businesses" has no synonym entry | Medium (cold start) | No filter applied, full segment returned | Zero-row check + missing filter alert |
| "small businesses" matches wrong dimension (business_org) | Low | Filter on wrong column | candidate_dimensions narrows search |
| Fuzzy match returns wrong value | Medium (for short strings) | Silent wrong results | Levenshtein threshold caps at 2 |

**Mathematical invariant:**
```
resolve(term) returns results in priority order: exact > fuzzy > synonym
If exact returns results, fuzzy and synonym are never executed.
∀ fuzzy_result: levenshtein(result.raw_value, term) <= 2
∀ synonym_result: term ∈ result.synonyms (exact membership, case-insensitive)
```

---

### STEP 5: Collect Candidates for Graph

**Component:** `RetrievalOrchestrator._collect_candidates_for_graph()`

**Input:** The 3 `EntitySearchResult` objects

**Logic:**
```python
# For each entity, take top candidate (and runner-up if near_miss)
# No near_misses in this query, so just top candidates:
candidate_fields = [
    "total_billed_business",  # from metric entity, top candidate
    "generation",             # from dimension entity, top candidate
    "bus_seg",                # from filter entity, top candidate
]
```

**Output:** `["total_billed_business", "generation", "bus_seg"]`

**Latency:** <0.1ms

**Invariant:**
```
len(candidate_fields) >= len(entity_results)  (at least one field per entity)
len(candidate_fields) <= 2 * len(entity_results)  (at most two per entity, if near_miss)
no duplicates: len(set(candidate_fields)) == len(candidate_fields)
```

---

### STEP 6: Graph Structural Validation (Apache AGE)

**Component:** `graph_search.validate_fields_in_explore()`

**Input:** `candidate_fields = ["total_billed_business", "generation", "bus_seg"]`

**AGE Cypher query executed:**
```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
        -[:HAS_DIMENSION|HAS_MEASURE]->(f)
  WHERE f.name IN ['total_billed_business', 'generation', 'bus_seg']
  WITH e, collect(DISTINCT f.name) AS matched
  WHERE size(matched) = 3
  RETURN e.name AS explore,
         matched AS confirmed_fields,
         size(matched) AS coverage
  ORDER BY coverage DESC
$$) AS (explore agtype, confirmed_fields agtype, coverage agtype);
```

**What the graph traversal does internally:**

```
Start at each Explore node.
For finance_cardmember_360:
  BASE_VIEW → custins_customer_insights_cardmember
    HAS_MEASURE → total_billed_business  ✓ (found 1/3)
    HAS_DIMENSION → bus_seg              ✓ (found 2/3)
  JOINS → cmdl_card_main
    HAS_DIMENSION → generation           ✓ (found 3/3)
  Coverage: 3/3 = 1.0                    ★ FULL MATCH

For finance_merchant_profitability:
  BASE_VIEW → fin_card_member_merchant_profitability
    HAS_MEASURE → total_merchant_spend (not total_billed_business) ✗
  JOINS → custins_customer_insights_cardmember
    HAS_MEASURE → total_billed_business  ✓ (found 1/3)
    HAS_DIMENSION → bus_seg              ✓ (found 2/3)
  JOINS → cmdl_card_main
    HAS_DIMENSION → generation           ✓ (found 3/3)
  Coverage: 3/3 = 1.0 BUT total_billed_business comes from JOINED view, not base view.

For finance_travel_sales:
  Does not contain bus_seg → partial match only
  Coverage < 3/3 → filtered out by WHERE size(matched) = 3
```

**Output:**
```python
[
    {
        "explore": "finance_cardmember_360",
        "confirmed_fields": ["total_billed_business", "generation", "bus_seg"],
        "coverage": 3,
        "model": "finance",
        "base_view_match": True,  # total_billed_business is in BASE_VIEW (custins)
    },
    {
        "explore": "finance_merchant_profitability",
        "confirmed_fields": ["total_billed_business", "generation", "bus_seg"],
        "coverage": 3,
        "model": "finance",
        "base_view_match": False,  # total_billed_business is in JOINED view (custins)
    },
]
```

Two explores match. But `finance_cardmember_360` has the measure in its base view. This is the base_view_priority signal.

**Latency:** ~10ms

**Failure modes:**
| Failure | Probability | Impact |
|---------|-------------|--------|
| AGE graph is stale (LookML deployed but graph not synced) | Medium | Valid fields rejected | 
| Graph query returns wrong explores due to incorrect edge loading | Low | SQL runs against wrong data source |
| No explore matches all 3 fields | Low (for finance BU) | action="no_match" returned |

**Mathematical invariant:**
```
∀ explore in results:
  coverage == |confirmed_fields ∩ candidate_fields|
  coverage == |candidate_fields|  (because WHERE size(matched) = N)

This is exact set containment:
  candidate_fields ⊆ fields_reachable_from(explore)
```

**Why this is the most important step:** Without graph validation, vector search returns `total_billed_business` (custins) + `generation` (cmdl) + `bus_seg` (custins), but has no idea whether these three fields can be queried together. They can -- but only through `finance_cardmember_360`, which joins custins and cmdl via cust_ref. The graph encodes this join structure. Without it, you might try to query `bus_seg` through `finance_travel_sales`, which does not have that field, generating SQL that fails.

---

### STEP 7: Few-Shot Search (FAISS)

**Component:** `fewshot.search()` (FAISS in-memory index)

**Input:**
```python
query_text = "total billed business generation"  # metrics + dimensions concatenated
```

**FAISS search:** Embed query_text, search IVF index for top 5 similar golden queries.

**Output:**
```python
[
    GoldenQuery(
        id="GQ-fin-003",
        natural_language="Show me average billed business by generation",
        model="finance",
        explore="finance_cardmember_360",
        dimensions=["cmdl_card_main.generation"],
        measures=["custins_customer_insights_cardmember.avg_billed_business"],
        filters={"custins_customer_insights_cardmember.partition_date": "last 90 days"},
        complexity="moderate",
    ),
    GoldenQuery(
        id="GQ-fin-006",
        natural_language="Total billed business by generation",
        model="finance",
        explore="finance_cardmember_360",
        dimensions=["cmdl_card_main.generation"],
        measures=["custins_customer_insights_cardmember.total_billed_business"],
        ...
    ),
]
```

**Apply to explores:** `finance_cardmember_360` gets `fewshot_confirmed = True`.

**Latency:** ~5ms (in-memory FAISS, no network hop)

**Failure modes:**
| Failure | Impact |
|---------|--------|
| Golden corpus empty (cold start) | fewshot signal absent, explore ranking relies on base_view + coverage only |
| Golden query matches wrong explore | Wrong fewshot_confirmed, score boost on wrong explore |

**Invariant:**
```
len(fewshot_results) <= MAX_FEWSHOT_RESULTS (5)
∀ result: cosine_similarity(embed(query_text), result.embedding) >= 0.85
```

---

### STEP 8: Three-Signal Explore Ranking

**Component:** `RetrievalOrchestrator._rank_explores()`

**Input:**
```python
explores = [
    ExploreCandidate(explore="finance_cardmember_360",
                     coverage=1.0, base_view_priority=True, fewshot_confirmed=True),
    ExploreCandidate(explore="finance_merchant_profitability",
                     coverage=1.0, base_view_priority=False, fewshot_confirmed=False),
]
```

**Scoring formula:**
```
score = coverage + (0.3 if base_view_priority) + (0.2 if fewshot_confirmed)

finance_cardmember_360:
  score = 1.0 + 0.3 + 0.2 = 1.5

finance_merchant_profitability:
  score = 1.0 + 0.0 + 0.0 = 1.0
```

**Output (sorted):**
```python
[
    ExploreCandidate(explore="finance_cardmember_360", score=1.5, ...),
    ExploreCandidate(explore="finance_merchant_profitability", score=1.0, ...),
]
```

**Disambiguation check:**
```python
gap = 1.5 - 1.0 = 0.5
needs_disambiguation = (0.5 < DISAMBIGUATION_THRESHOLD)  # 0.5 < 0.10? No.
# No disambiguation needed. Clear winner.
```

**Latency:** <0.1ms

**Mathematical invariant:**
```
score ∈ [0.0, 1.5]  (coverage max 1.0 + 0.3 + 0.2)
explores is sorted by score descending
disambiguation iff |explores[0].score - explores[1].score| < 0.10
```

**Why this scoring works:** The three signals are intentionally non-overlapping in what they measure:
- Coverage = "does this explore have the fields?" (necessary but not sufficient)
- Base view priority = "are the fields in the right place?" (structural correctness)
- Few-shot = "have we seen this pattern work before?" (empirical confirmation)

The weights (0.3, 0.2) are set so that base_view_priority alone can break ties between 100% coverage explores, and few-shot alone can break ties between explores with equal coverage and base_view status.

---

### STEP 9: Filter Assembly

**Component:** `RetrievalOrchestrator._resolve_filters()` + `_get_mandatory_filters()`

**Input:**
```python
entities = {
    "filter_terms": ["small businesses"],
    "time_range": None,
}
# Value catalog already resolved: "small businesses" → bus_seg = "OPEN"
resolved_from_catalog = {"bus_seg": "OPEN"}

explore = "finance_cardmember_360"
```

**Mandatory filter lookup (AGE):**
```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore {name: 'finance_cardmember_360'})-[:ALWAYS_FILTER_ON]->(d:Dimension)
  RETURN d.name AS filter_field, d.tags AS tags
$$) AS (filter_field agtype, tags agtype);
```

Result: `[{"filter_field": "partition_date", "tags": ["partition_key"]}]`

Since user provided no time_range, mandatory filter defaults to "last 90 days."

**Final assembled filters:**
```python
filters = {
    "custins_customer_insights_cardmember.bus_seg": "OPEN",
    "custins_customer_insights_cardmember.partition_date": "last 90 days",
}
```

**Latency:** ~10ms (one AGE query + dict merge)

**Failure modes:**
| Failure | Impact |
|---------|--------|
| Mandatory filter lookup fails | Fallback to `{"partition_date": "last 90 days"}` (safe default) |
| Value catalog returns no match for "small businesses" | bus_seg filter missing, query returns all segments |
| Multiple mandatory filters needed but only one returned | BQ scans more data than necessary |

**Invariant:**
```
"partition_date" ∈ filters.keys()  (ALWAYS — mandatory filter guarantee)
∀ filter_value: value is deterministically resolved (not LLM-guessed)
```

---

### STEP 10: RetrievalResult Construction

**Component:** `RetrievalOrchestrator.retrieve()` final assembly

**Output:**
```python
RetrievalResult(
    action="proceed",
    model="finance",
    explore="finance_cardmember_360",
    dimensions=["cmdl_card_main.generation"],
    measures=["custins_customer_insights_cardmember.total_billed_business"],
    filters={
        "custins_customer_insights_cardmember.bus_seg": "OPEN",
        "custins_customer_insights_cardmember.partition_date": "last 90 days",
    },
    confidence=1.5,    # explore score
    coverage=1.0,      # all fields found
    fewshot_matches=["GQ-fin-006", "GQ-fin-003"],
)
```

**CortexState update:**
```python
state.retrieval_result = asdict(retrieval_result)
```

**Latency:** <0.1ms (dataclass construction)

**Invariant:**
```
action == "proceed" → model != "" ∧ explore != "" ∧ len(measures) > 0
action == "disambiguate" → len(alternatives) >= 2
action == "clarify" → confidence < SIMILARITY_FLOOR
action == "no_match" → confidence == 0.0
```

---

### STEP 11: Augmented System Prompt + Looker MCP Tool Call

**Component:** `CortexOrchestrator._build_augmented_prompt()` + ADK ReAct loop with MCPToolAgent

**The augmented prompt injected into the LLM:**
```
## Retrieved Context (from Cortex retrieval pipeline)

I have already identified the correct Looker fields for this query:

- Model: finance
- Explore: finance_cardmember_360
- Dimensions: cmdl_card_main.generation
- Measures: custins_customer_insights_cardmember.total_billed_business
- Required filters: {"custins_customer_insights_cardmember.bus_seg": "OPEN",
                     "custins_customer_insights_cardmember.partition_date": "last 90 days"}
- Confidence: 1.5

Action: Use query-sql directly with these exact fields. Do NOT explore or
discover — the retrieval pipeline has already validated that these fields exist
in this explore and can be queried together.
```

**Looker MCP tool call (generated by LLM from augmented prompt):**
```json
{
  "tool": "query_sql",
  "arguments": {
    "model_name": "finance",
    "explore_name": "finance_cardmember_360",
    "fields": [
      "cmdl_card_main.generation",
      "custins_customer_insights_cardmember.total_billed_business"
    ],
    "filters": {
      "custins_customer_insights_cardmember.bus_seg": "OPEN",
      "custins_customer_insights_cardmember.partition_date": "last 90 days"
    },
    "sorts": [
      "custins_customer_insights_cardmember.total_billed_business desc"
    ],
    "limit": "500"
  }
}
```

**CortexState update:**
```python
state.looker_query_spec = {
    "model": "finance",
    "explore": "finance_cardmember_360",
    "fields": ["cmdl_card_main.generation",
               "custins_customer_insights_cardmember.total_billed_business"],
    "filters": {
        "custins_customer_insights_cardmember.bus_seg": "OPEN",
        "custins_customer_insights_cardmember.partition_date": "last 90 days",
    },
    "sorts": ["custins_customer_insights_cardmember.total_billed_business desc"],
}
```

**Latency:** ~200-500ms (LLM reads augmented prompt, decides to call query_sql, MCP executes)

**Failure modes:**
| Failure | Impact | Mitigation |
|---------|--------|------------|
| LLM ignores augmented prompt, explores on its own | Adds 3-5 extra calls, ~2s latency | System prompt says "Do NOT explore" + confidence threshold |
| LLM reformats field names wrong (drops view prefix) | Looker API error | Field names are fully qualified in prompt |
| Looker MCP server unreachable | Query fails | Retry with exponential backoff |

---

### STEP 12: SQL Generated by Looker

**Component:** Looker SQL generation engine (deterministic, no LLM)

**Looker generates:**
```sql
SELECT
  CASE
    WHEN cmdl_card_main.birth_year >= 1997 THEN 'Gen Z'
    WHEN cmdl_card_main.birth_year BETWEEN 1981 AND 1996 THEN 'Millennial'
    WHEN cmdl_card_main.birth_year BETWEEN 1965 AND 1980 THEN 'Gen X'
    WHEN cmdl_card_main.birth_year BETWEEN 1945 AND 1964 THEN 'Baby Boomer'
    ELSE 'Other'
  END AS `cmdl_card_main.generation`,
  COALESCE(SUM(custins_customer_insights_cardmember.billed_business), 0)
    AS `custins_customer_insights_cardmember.total_billed_business`
FROM `axp-lumid.dw.custins_customer_insights_cardmember`
  AS custins_customer_insights_cardmember
LEFT JOIN (
  SELECT * FROM `axp-lumid.dw.cmdl_card_main`
  WHERE partition_date = (
    SELECT MAX(partition_date) FROM `axp-lumid.dw.cmdl_card_main`
  )
) AS cmdl_card_main
  ON custins_customer_insights_cardmember.cust_ref = cmdl_card_main.cust_ref
WHERE
  -- LAYER 1: sql_always_where (hidden hard ceiling, 365 days)
  custins_customer_insights_cardmember.partition_date
    >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
  -- LAYER 2: always_filter (user-visible, "last 90 days")
  AND custins_customer_insights_cardmember.partition_date
    >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  -- User filter: business segment
  AND custins_customer_insights_cardmember.bus_seg = 'OPEN'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 500
```

**Key observations:**
1. Looker injected `sql_always_where` (365-day cap) automatically. The agent did not add this.
2. Looker resolved `"last 90 days"` into proper date arithmetic.
3. The `cmdl_card_main` join uses the derived_table (latest snapshot only) -- defined in the LookML view.
4. The CASE statement for `generation` is from the LookML dimension definition, not LLM-generated.
5. Looker may route this to the `monthly_members_by_generation` aggregate table since the dimensions and measures match the pre-computed rollup.

**Latency:** ~500ms (Looker generates SQL) + ~1-3s (BQ execution)

**CortexState update:**
```python
state.generated_sql = "<the SQL above>"
state.query_results = {
    "rows": [
        {"generation": "Millennial", "total_billed_business": 4523000000},
        {"generation": "Gen X",      "total_billed_business": 3891000000},
        {"generation": "Baby Boomer","total_billed_business": 2134000000},
        {"generation": "Gen Z",      "total_billed_business": 1567000000},
        {"generation": "Other",      "total_billed_business": 234000000},
    ],
    "columns": ["generation", "total_billed_business"],
    "row_count": 5,
    "bytes_scanned": 2500000000,  # ~2.5GB (with partition pruning)
}
```

---

### STEP 13: Response to User

**Component:** LLM formats results into natural language

**Output:**
```
Total billed business for small business (OPEN segment) customers by generation:

| Generation   | Total Billed Business |
|-------------|----------------------|
| Millennial   | $4.52B               |
| Gen X        | $3.89B               |
| Baby Boomer  | $2.13B               |
| Gen Z        | $1.57B               |
| Other        | $234M                |

Data period: Last 90 days
Segment: Small Business (OPEN)
Source: finance_cardmember_360 explore
```

**CortexState final:**
```python
state.formatted_response = "<the above>"
state.follow_up_suggestions = [
    "Break this down by card product",
    "Show me the trend over last 4 quarters",
    "Compare with Consumer (CPS) segment",
]
```

---

### TOTAL LATENCY BREAKDOWN

```
Step                          | Time     | System          | LLM Call?
------------------------------|----------|-----------------|----------
1. Intent + Entity Extraction | ~300ms   | Gemini Flash    | YES (1 call)
2. Vector Search (3 entities) | ~30ms    | pgvector        | No
3. Confidence Gate            | <0.1ms   | Python          | No
4. Near-Miss Detection        | <0.1ms   | Python          | No
4.5. Value Catalog Resolution | ~10ms    | PostgreSQL      | No
5. Collect Candidates         | <0.1ms   | Python          | No
6. Graph Validation           | ~10ms    | AGE/PostgreSQL  | No
7. Few-Shot Search            | ~5ms     | FAISS (memory)  | No
8. Explore Ranking            | <0.1ms   | Python          | No
9. Filter Assembly            | ~10ms    | AGE/PostgreSQL  | No
10. Result Construction       | <0.1ms   | Python          | No
                              |          |                 |
RETRIEVAL SUBTOTAL            | ~365ms   |                 | 1 LLM call
                              |          |                 |
11. Augmented Prompt + MCP    | ~500ms   | Gemini + Looker | YES (1 call)
12. BQ Execution              | ~1-3s    | BigQuery        | No
13. Response Formatting       | ~200ms   | Gemini Flash    | YES (1 call)
                              |          |                 |
TOTAL                         | ~2-4s    |                 | 3 LLM calls
```

Compared to the old PoC (no retrieval): 5-6 LLM calls, ~8-12s, unreliable field selection.

---

## PART 2: ASCII Whiteboard Diagrams

### Diagram 1: Full Pipeline (High Level)

```
 USER QUERY
 "Total billed business by generation for small businesses"
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: INTENT + ENTITY EXTRACTION                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Gemini Flash (SafeChain) — 1 LLM call, ~300ms           │  │
│  │                                                           │  │
│  │  IN:  raw query string                                    │  │
│  │  OUT: intent=data_query                                   │  │
│  │       metrics=["total billed business"]                   │  │
│  │       dimensions=["generation"]                           │  │
│  │       filter_terms=["small businesses"]                   │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: RETRIEVAL ORCHESTRATOR  (~65ms, NO LLM)               │
│                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│   │ pgvector │    │  Apache  │    │  FAISS   │                  │
│   │ (vector) │    │  AGE     │    │ (fewshot)│                  │
│   │  ~30ms   │    │ (graph)  │    │   ~5ms   │                  │
│   │          │    │  ~10ms   │    │          │                  │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘                  │
│        │               │               │                         │
│        ▼               ▼               ▼                         │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │  FUSION + STRUCTURAL VALIDATION + VALUE CATALOG          │  │
│   │                                                          │  │
│   │  Vector: "what fields match semantically?"               │  │
│   │  Graph:  "can these fields be queried together?"         │  │
│   │  FAISS:  "have we seen this pattern before?"             │  │
│   │  Catalog: "small businesses" → bus_seg = "OPEN"          │  │
│   │                                                          │  │
│   │  → Three-signal scoring → Best explore selected          │  │
│   │  → Mandatory partition filter injected                   │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  OUT: RetrievalResult                                            │
│    action="proceed"                                              │
│    model="finance"                                               │
│    explore="finance_cardmember_360"                              │
│    dimensions=["cmdl_card_main.generation"]                      │
│    measures=["custins.total_billed_business"]                    │
│    filters={bus_seg:"OPEN", partition_date:"last 90 days"}       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3: LOOKER MCP (SQL GENERATION — DETERMINISTIC, NO LLM)  │
│                                                                  │
│  RetrievalResult → query_sql tool call → Looker generates SQL   │
│                                                                  │
│  Looker auto-injects:                                            │
│    ✓ sql_always_where (365-day hard cap)                        │
│    ✓ always_filter (partition_date)                              │
│    ✓ JOIN on cust_ref (custins ⟕ cmdl)                          │
│    ✓ CASE statement for generation dimension                    │
│    ✓ May route to aggregate_table if pattern matches            │
│                                                                  │
│  OUT: SQL string + BQ execution → result rows                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 4: RESPONSE                                               │
│                                                                  │
│  LLM formats result rows into natural language + table           │
│  Generates follow-up suggestions                                 │
│  Stores state for follow-up handling                             │
└─────────────────────────────────────────────────────────────────┘
```

### Diagram 2: Retrieval Orchestrator Detail

```
                    ENTITIES (from Stage 1)
                    ┌─────────────────────────┐
                    │ metrics: [total billed]  │
                    │ dims:    [generation]     │
                    │ filters: [small biz]     │
                    └────────────┬─────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │ PER-ENTITY             │                        │
        ▼                        ▼                        ▼
  ┌──────────┐           ┌──────────┐           ┌──────────────┐
  │ embed()  │           │ embed()  │           │   embed()    │
  │ "total   │           │"genera-  │           │"small busi-  │
  │  billed  │           │  tion"   │           │   nesses"    │
  │business" │           │          │           │              │
  └────┬─────┘           └────┬─────┘           └──────┬───────┘
       │                      │                        │
       ▼                      ▼                        ▼
  ┌────────────────────────────────────────────────────────────┐
  │                    pgvector SEARCH                          │
  │  SELECT ... 1-(embedding <=> $1) AS similarity             │
  │  FROM field_embeddings WHERE hidden=FALSE                  │
  │  ORDER BY embedding <=> $1 LIMIT 20                        │
  │                                                            │
  │  41 field embeddings × 768 dimensions × HNSW index         │
  └────────────────────────────────────────────────────────────┘
       │                      │                        │
       ▼                      ▼                        ▼
  total_billed_biz:0.96  generation:0.95         bus_seg:0.84
  avg_billed_biz:0.91    birth_year:0.78         business_org:0.79
       │                      │                        │
       └──────────┬───────────┘                        │
                  │                                    │
       ┌──────────▼───────────┐            ┌───────────▼──────────┐
       │  CONFIDENCE GATE     │            │  VALUE CATALOG        │
       │  any score >= 0.70?  │            │  "small businesses"   │
       │  0.96 >= 0.70 ✓     │            │  exact? No            │
       │  PASS                │            │  fuzzy? No            │
       └──────────┬───────────┘            │  synonym? YES         │
                  │                        │  → bus_seg = "OPEN"   │
       ┌──────────▼───────────┐            └───────────┬──────────┘
       │  NEAR-MISS CHECK     │                        │
       │  δ = top - runner_up │                        │
       │  0.05, 0.17, 0.05   │                        │
       │  None < 0.05        │                        │
       │  No near-misses      │                        │
       └──────────┬───────────┘                        │
                  │                                    │
       ┌──────────▼───────────┐                        │
       │ COLLECT CANDIDATES   │                        │
       │ [total_billed_biz,   │                        │
       │  generation,         │                        │
       │  bus_seg]            │                        │
       └──────────┬───────────┘                        │
                  │                                    │
       ┌──────────▼──────────────────────────────────┐ │
       │         AGE GRAPH VALIDATION                 │ │
       │                                              │ │
       │  MATCH (e:Explore)-[:BASE_VIEW|JOINS]->      │ │
       │        (v:View)-[:HAS_*]->(f)                │ │
       │  WHERE f.name IN [3 candidates]              │ │
       │                                              │ │
       │  finance_cardmember_360: 3/3 ★ base_view ✓  │ │
       │  finance_merchant_prof:  3/3   base_view ✗   │ │
       └──────────┬──────────────────────────────────┘ │
                  │                                    │
       ┌──────────▼───────────┐                        │
       │  FEWSHOT (FAISS)     │                        │
       │  "total billed       │                        │
       │   business            │                        │
       │   generation"        │                        │
       │  → GQ-fin-006 (0.93) │                        │
       │  → confirms cm360    │                        │
       └──────────┬───────────┘                        │
                  │                                    │
       ┌──────────▼───────────────────────────────┐    │
       │  THREE-SIGNAL RANKING                     │    │
       │                                           │    │
       │  cm360:  1.0 + 0.3 + 0.2 = 1.5  ★ WIN   │    │
       │  merch:  1.0 + 0.0 + 0.0 = 1.0          │    │
       │                                           │    │
       │  gap = 0.5 > 0.10 → no disambiguation    │    │
       └──────────┬───────────────────────────────┘    │
                  │                                    │
       ┌──────────▼───────────────────┬────────────────▼──┐
       │  FILTER ASSEMBLY              │                    │
       │  mandatory: partition_date    │  from catalog:     │
       │            = "last 90 days"   │  bus_seg = "OPEN"  │
       └──────────┬───────────────────┴────────────────────┘
                  │
                  ▼
         RetrievalResult(action="proceed", ...)
```

### Diagram 3: Filter Resolution Flow

```
  USER SAYS: "small businesses"
       │
       ▼
  ┌─────────────────────────────────────────────────────┐
  │  ENTITY EXTRACTION (LLM)                             │
  │  Job: "identify which words are filter conditions"   │
  │  NOT: "resolve to exact database values"             │
  │                                                      │
  │  OUT: filter_terms=["small businesses"]              │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  VECTOR SEARCH (pgvector)                            │
  │  Embed "small businesses" → 768-dim vector           │
  │  Search field_embeddings for similar DIMENSIONS      │
  │                                                      │
  │  Result: bus_seg (0.84), business_org (0.79)         │
  │  → candidate_dimensions = [bus_seg, business_org]    │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  VALUE CATALOG (dimension_value_catalog table)       │
  │                                                      │
  │  Pass 1: EXACT                                       │
  │  SELECT WHERE LOWER(raw_value)                       │
  │    = LOWER('small businesses')                       │
  │  AND dimension_name IN ('bus_seg','business_org')    │
  │  → EMPTY                                             │
  │                                                      │
  │  Pass 2: FUZZY (Levenshtein ≤ 2)                     │
  │  SELECT WHERE levenshtein(raw_value,                 │
  │    'small businesses') <= 2                          │
  │  → EMPTY (nearest: "OPEN" = distance 13)             │
  │                                                      │
  │  Pass 3: SYNONYM                                     │
  │  SELECT WHERE 'small businesses'                     │
  │    = ANY(synonyms)                                   │
  │  → MATCH: bus_seg, raw_value="OPEN",                 │
  │    synonyms=["small business","SMB"]                  │
  │                                                      │
  │  RESOLVED: bus_seg = "OPEN"                          │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
          filter = {"bus_seg": "OPEN"}

  ┌──────────────────────────────────────────┐
  │  MANDATORY FILTER (AGE graph)             │
  │  finance_cardmember_360                   │
  │  -[:ALWAYS_FILTER_ON]->                  │
  │  partition_date                            │
  │                                           │
  │  No user time_range → default 90 days    │
  └──────────────────────┬───────────────────┘
                         │
                         ▼
          FINAL FILTERS:
          {
            bus_seg: "OPEN",
            partition_date: "last 90 days"
          }
```

### Diagram 4: Data Stores and What Lives Where

```
┌──────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Instance (local)                     │
│                                                                   │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│  │  pgvector Extension   │  │  Apache AGE Extension             │  │
│  │                       │  │                                    │  │
│  │  field_embeddings     │  │  Graph: lookml_schema              │  │
│  │  ┌─────────────────┐ │  │                                    │  │
│  │  │ 41 rows (v1)    │ │  │  NODES:                            │  │
│  │  │                 │ │  │  ┌──────────┐     ┌──────────┐    │  │
│  │  │ field_key (PK)  │ │  │  │ Model(1) │────▶│Explore(5)│    │  │
│  │  │ embedding[768]  │ │  │  └──────────┘     └────┬─────┘    │  │
│  │  │ field_name      │ │  │                  BASE_VIEW│JOINS   │  │
│  │  │ field_type      │ │  │                    ┌─────▼─────┐  │  │
│  │  │ view_name       │ │  │                    │  View(7)  │  │  │
│  │  │ explore_name    │ │  │                    └─────┬─────┘  │  │
│  │  │ model_name      │ │  │              HAS_DIM│  │HAS_MEAS │  │
│  │  │ content (text)  │ │  │                 ┌───▼──▼───┐     │  │
│  │  │ HNSW index      │ │  │                 │ Dim(34)  │     │  │
│  │  └─────────────────┘ │  │                 │ Meas(18) │     │  │
│  │                       │  │                 └──────────┘     │  │
│  │  ANSWERS:             │  │                                    │  │
│  │  "What fields match   │  │  ALSO:                             │  │
│  │   semantically?"      │  │  BusinessTerm(17+) -[:MAPS_TO]->  │  │
│  │                       │  │  Explore -[:ALWAYS_FILTER_ON]->    │  │
│  │  SEARCHED BY:         │  │                                    │  │
│  │  cosine similarity    │  │  ANSWERS:                          │  │
│  │  one query per entity │  │  "Can these fields be queried      │  │
│  └──────────────────────┘  │   together? Join path? Required     │  │
│                             │   filters?"                        │  │
│  ┌──────────────────────┐  │                                    │  │
│  │dimension_value_catalog│  │  SEARCHED BY:                      │  │
│  │  ┌─────────────────┐ │  │  Cypher queries via AGE SQL        │  │
│  │  │ ~70 rows (v1)   │ │  │  wrapper                           │  │
│  │  │ ~250 rows (3BU) │ │  └──────────────────────────────────┘  │
│  │  │                 │ │                                         │
│  │  │ dimension_name  │ │                                         │
│  │  │ raw_value       │ │                                         │
│  │  │ display_label   │ │                                         │
│  │  │ frequency       │ │                                         │
│  │  │ synonyms[]      │ │                                         │
│  │  │ is_high_card    │ │                                         │
│  │  └─────────────────┘ │                                         │
│  │                       │                                         │
│  │  ANSWERS:             │                                         │
│  │  "What exact BQ value │                                         │
│  │   does 'small biz'    │                                         │
│  │   map to?"            │                                         │
│  └──────────────────────┘                                         │
└───────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  FAISS (in-memory)    │
│                       │
│  golden_queries index │
│  ┌─────────────────┐ │
│  │ ~50-200 entries  │ │
│  │ embedding[768]   │ │
│  │ model            │ │
│  │ explore          │ │
│  │ dimensions[]     │ │
│  │ measures[]       │ │
│  │ filters{}        │ │
│  └─────────────────┘ │
│                       │
│  ANSWERS:             │
│  "Have we seen a      │
│   query like this     │
│   before? What fields │
│   did it use?"        │
│                       │
│  SEARCHED BY:         │
│  FAISS IVF inner      │
│  product, <5ms        │
└──────────────────────┘
```

---

## PART 3: What Ayush Needs for the Demo UI

The Engineering View should be a step-by-step timeline that expands as the pipeline progresses. Each panel corresponds to a pipeline stage and renders the intermediate data.

### UI Panel Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  CORTEX ENGINEERING VIEW                                         │
│                                                                  │
│  Query: "Total billed business by generation for small biz"     │
│  Status: ✓ Complete  |  Total: 2.3s  |  LLM Calls: 3           │
│                                                                  │
│  ┌─── STEP 1: CLASSIFICATION ──── 312ms ───────────────────┐   │
│  │  Intent: data_query (0.96)                                │   │
│  │  Entities:                                                │   │
│  │    Metrics:    [total billed business]                    │   │
│  │    Dimensions: [generation]                               │   │
│  │    Filters:    [small businesses] (raw)                   │   │
│  │    Time Range: null                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── STEP 2: VECTOR SEARCH ──── 28ms ─────────────────────┐   │
│  │  Entity: "total billed business" (metric)                 │   │
│  │    #1 total_billed_business  custins  0.96 ████████████▌  │   │
│  │    #2 avg_billed_business    custins  0.91 ███████████▎   │   │
│  │    #3 billed_business        custins  0.89 ██████████▊    │   │
│  │                                                           │   │
│  │  Entity: "generation" (dimension)                         │   │
│  │    #1 generation      cmdl     0.95 ████████████▍        │   │
│  │    #2 birth_year      cmdl     0.78 █████████▊           │   │
│  │                                                           │   │
│  │  Entity: "small businesses" (filter)                      │   │
│  │    #1 bus_seg         custins  0.84 ██████████▌           │   │
│  │    #2 business_org    custins  0.79 █████████▊            │   │
│  │                                                           │   │
│  │  Confidence Gate: PASS (max=0.96 >= 0.70)                 │   │
│  │  Near Misses: None                                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── STEP 3: VALUE CATALOG ──── 8ms ──────────────────────┐   │
│  │  "small businesses"                                       │   │
│  │    Pass 1 (exact):   no match                             │   │
│  │    Pass 2 (fuzzy):   no match                             │   │
│  │    Pass 3 (synonym): ✓ bus_seg = "OPEN"                   │   │
│  │                      match_type=synonym                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── STEP 4: GRAPH VALIDATION ──── 11ms ──────────────────┐   │
│  │  Candidate fields: [total_billed_business,                │   │
│  │                     generation, bus_seg]                   │   │
│  │                                                           │   │
│  │  Explore                    Coverage  Base  Fewshot       │   │
│  │  ─────────────────────────  ────────  ────  ───────       │   │
│  │  finance_cardmember_360     3/3 100%   ✓     ✓            │   │
│  │  finance_merchant_profit    3/3 100%   ✗     ✗            │   │
│  │                                                           │   │
│  │  Winner: finance_cardmember_360 (score: 1.5)              │   │
│  │  Gap to #2: 0.5 (no disambiguation needed)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── STEP 5: FILTERS ──── 9ms ───────────────────────────┐    │
│  │  User filters:                                            │   │
│  │    bus_seg = "OPEN" (resolved from "small businesses")    │   │
│  │  Mandatory filters:                                       │   │
│  │    partition_date = "last 90 days" (from graph)           │   │
│  │  Final:                                                   │   │
│  │    {bus_seg: "OPEN", partition_date: "last 90 days"}      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─── STEP 6: LOOKER MCP ──── 1843ms ─────────────────────┐   │
│  │  Tool: query_sql                                          │   │
│  │  Model: finance                                           │   │
│  │  Explore: finance_cardmember_360                          │   │
│  │  Fields: [cmdl_card_main.generation,                      │   │
│  │           custins...total_billed_business]                 │   │
│  │  Filters: {bus_seg:"OPEN", partition_date:"last 90 days"} │   │
│  │                                                           │   │
│  │  [▼ Show Generated SQL]                                   │   │
│  │  [▼ Show Raw Results]                                     │   │
│  │                                                           │   │
│  │  Rows: 5  |  Bytes Scanned: 2.5 GB                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### JSON Contract for Each Panel

**Panel 1 (Classification):**
```json
{
  "step": "classification",
  "latency_ms": 312,
  "intent": "data_query",
  "intent_confidence": 0.96,
  "entities": {
    "metrics": ["total billed business"],
    "dimensions": ["generation"],
    "filter_terms": ["small businesses"],
    "time_range": null
  }
}
```

**Panel 2 (Vector Search):**
```json
{
  "step": "vector_search",
  "latency_ms": 28,
  "searches": [
    {
      "entity": "total billed business",
      "role": "metric",
      "results": [
        {"field": "total_billed_business", "view": "custins", "score": 0.96},
        {"field": "avg_billed_business", "view": "custins", "score": 0.91},
        {"field": "billed_business", "view": "custins", "score": 0.89}
      ],
      "near_miss": false
    },
    {
      "entity": "generation",
      "role": "dimension",
      "results": [
        {"field": "generation", "view": "cmdl", "score": 0.95},
        {"field": "birth_year", "view": "cmdl", "score": 0.78}
      ],
      "near_miss": false
    },
    {
      "entity": "small businesses",
      "role": "filter",
      "results": [
        {"field": "bus_seg", "view": "custins", "score": 0.84},
        {"field": "business_org", "view": "custins", "score": 0.79}
      ],
      "near_miss": false
    }
  ],
  "confidence_gate": {"passed": true, "max_score": 0.96, "floor": 0.70}
}
```

**Panel 3 (Value Catalog):**
```json
{
  "step": "value_catalog",
  "latency_ms": 8,
  "resolutions": [
    {
      "user_term": "small businesses",
      "passes": [
        {"type": "exact", "matched": false},
        {"type": "fuzzy", "matched": false},
        {"type": "synonym", "matched": true, "dimension": "bus_seg", "value": "OPEN"}
      ],
      "resolved": {"dimension": "bus_seg", "value": "OPEN"}
    }
  ]
}
```

**Panel 4 (Graph Validation):**
```json
{
  "step": "graph_validation",
  "latency_ms": 11,
  "candidate_fields": ["total_billed_business", "generation", "bus_seg"],
  "explores": [
    {
      "name": "finance_cardmember_360",
      "coverage": 1.0,
      "base_view_priority": true,
      "fewshot_confirmed": true,
      "score": 1.5
    },
    {
      "name": "finance_merchant_profitability",
      "coverage": 1.0,
      "base_view_priority": false,
      "fewshot_confirmed": false,
      "score": 1.0
    }
  ],
  "winner": "finance_cardmember_360",
  "disambiguation_needed": false,
  "gap": 0.5
}
```

**Panel 5 (Filters):**
```json
{
  "step": "filter_assembly",
  "latency_ms": 9,
  "user_filters": {"bus_seg": "OPEN"},
  "mandatory_filters": {"partition_date": "last 90 days"},
  "final_filters": {
    "custins_customer_insights_cardmember.bus_seg": "OPEN",
    "custins_customer_insights_cardmember.partition_date": "last 90 days"
  }
}
```

**Panel 6 (Looker MCP):**
```json
{
  "step": "looker_mcp",
  "latency_ms": 1843,
  "tool": "query_sql",
  "model": "finance",
  "explore": "finance_cardmember_360",
  "fields": [
    "cmdl_card_main.generation",
    "custins_customer_insights_cardmember.total_billed_business"
  ],
  "filters": {
    "custins_customer_insights_cardmember.bus_seg": "OPEN",
    "custins_customer_insights_cardmember.partition_date": "last 90 days"
  },
  "generated_sql": "SELECT ...",
  "result_rows": 5,
  "bytes_scanned": 2500000000
}
```

**What Ayush should implement:**
1. A vertical timeline component that renders these panels in order
2. Each panel is collapsible (collapsed by default for non-engineering users)
3. Score bars are simple percentage-width divs (score/1.0 * 100%)
4. SQL panel has syntax highlighting (Prism.js or similar)
5. The engineering view is a toggle -- the default user view shows only the final answer
6. Emit all this data as structured events from the pipeline (each step logs to a `PipelineTrace` object that the UI subscribes to)

---

## PART 4: How Animesh Evaluates This Pipeline

### First Principles of AI Pipeline Evaluation

The fundamental question is: **What does "correct" mean at each step, and how do you measure it without requiring infinite labeled data?**

Three irreducible truths about evaluation:
1. **You cannot evaluate what you cannot define.** Each step needs a formal correctness predicate.
2. **End-to-end correctness does not imply per-step correctness.** A pipeline can get the right answer for wrong reasons (lucky cancellation of errors). Per-step evaluation catches this.
3. **Statistical significance requires sample sizes that depend on the metric and the variance.** You cannot evaluate with 10 queries and claim 90% accuracy.

---

### Per-Step Evaluation Functions

#### Step 1: Intent Classification

**Correctness predicate:**
```
correct(predicted_intent, expected_intent) = (predicted_intent == expected_intent)
```

This is a **multi-class classification** problem with 6 classes: `data_query`, `schema_browse`, `saved_content`, `follow_up`, `clarification`, `out_of_scope`.

**Metrics:**
- **Accuracy** = correct / total (overall)
- **Per-class precision** = TP / (TP + FP) for each intent
- **Per-class recall** = TP / (TP + FN) for each intent
- **Confusion matrix** (6x6) -- the most informative artifact

**Why accuracy alone is insufficient:** If 85% of queries are `data_query`, a dumb classifier that always returns `data_query` gets 85% accuracy. Per-class precision/recall expose this.

**Golden dataset requirement:**
- Minimum: 30 examples per class (for 95% CI width of ~18% per class)
- Target: 50 examples per class = 300 total labeled queries
- The class distribution should reflect realistic usage, BUT you need minimum coverage per class

**Statistical reasoning:**
For a binomial proportion p with n samples, the 95% confidence interval width is approximately:
```
CI_width ≈ 2 * 1.96 * sqrt(p(1-p)/n)
```
At p=0.95 (target accuracy) and n=200:
```
CI_width ≈ 2 * 1.96 * sqrt(0.95*0.05/200) ≈ 0.060
```
So with 200 queries, a measured 95% accuracy actually means 92%-98%. To narrow to +/-2%, you need n=456.

**For the demo (50 queries):** You get +/-12% confidence interval. That is fine for a demo. Not fine for production claims.

---

#### Step 2: Entity Extraction

**Correctness predicate (per entity type):**
```
metric_recall    = |predicted_metrics ∩ expected_metrics| / |expected_metrics|
metric_precision = |predicted_metrics ∩ expected_metrics| / |predicted_metrics|
```

Same for dimensions, filter_terms.

**Metrics:**
- **Recall** per entity type (did we find all expected entities?)
- **Precision** per entity type (did we avoid hallucinating extra entities?)
- **F1** = 2 * (P * R) / (P + R) -- harmonic mean, penalizes imbalance
- **Exact match** = all entities exactly correct (strict but informative)

**Golden dataset structure:**
```json
{
  "id": "EE-001",
  "query": "Total billed business by generation for small businesses",
  "expected": {
    "metrics": ["total billed business"],
    "dimensions": ["generation"],
    "filter_terms": ["small businesses"],
    "time_range": null
  }
}
```

**Minimum size:** 100 queries covering:
- Simple (1 metric, 0 dims, 0 filters): 25
- Moderate (1 metric, 1-2 dims, 0-1 filters): 35
- Complex (1+ metrics, 2+ dims, 1+ filters): 25
- Edge cases (ambiguous, multi-intent, follow-up): 15

---

#### Step 3: Vector Search (per entity)

**Correctness predicate:**
```
For each entity e with expected field f_expected:
  hit@K(e) = 1 if f_expected ∈ top_K_results(e) else 0
  MRR(e) = 1 / rank(f_expected) if f_expected in results else 0
```

**Metrics:**
- **Recall@K** = fraction of entities where expected field appears in top-K
- **MRR (Mean Reciprocal Rank)** = average of 1/rank across all entities
- **Precision@1** = fraction of entities where top-1 result is correct

**Why MRR matters more than Recall@K:** At K=20, Recall@20 might be 0.98 (almost everything is somewhere in top 20). But if the correct field is at rank 15, the orchestrator might pick a wrong field at rank 1. MRR penalizes this.

**Golden dataset structure:**
```json
{
  "id": "VS-001",
  "entity_text": "total billed business",
  "entity_role": "metric",
  "expected_field": "total_billed_business",
  "expected_view": "custins_customer_insights_cardmember",
  "expected_explore": "finance_cardmember_360"
}
```

**Minimum size:** At least 3 entities per golden query x 50 queries = 150 entity evaluations.

---

#### Step 4: Value Catalog Resolution

**Correctness predicate:**
```
correct(user_term) = (resolved_dimension == expected_dimension) 
                   AND (resolved_value == expected_value)
```

**Metrics:**
- **Resolution accuracy** = correct resolutions / total filter terms
- **Match type distribution** = what fraction resolved via exact vs fuzzy vs synonym
- **False positive rate** = wrong value resolved (worst failure -- silent wrong results)
- **Coverage** = fraction of filter terms that get any resolution (vs. empty)

**Golden dataset structure:**
```json
{
  "id": "VC-001",
  "user_term": "small businesses",
  "expected_dimension": "bus_seg",
  "expected_value": "OPEN",
  "expected_match_type": "synonym"
}
```

**Minimum size:** All filterable dimensions (13 for Finance) x 3-5 synonym variants each = ~50-65 test cases. This is exhaustive for v1.

---

#### Step 5: Graph Validation

**Correctness predicate:**
```
correct(candidate_fields) = (expected_explore ∈ returned_explores)
                          AND (returned_explores[0] == expected_explore)  # ranked first
```

**Metrics:**
- **Explore accuracy** = fraction of queries where correct explore is top-ranked
- **False validation rate** = fraction of queries where an incorrect explore validates (fields exist but in wrong context)

**This step is nearly deterministic** -- given correct candidate fields, the graph either contains the edge paths or it does not. The main failure mode is stale graphs (LookML changed, graph not re-loaded). Testing here is more about graph integrity than algorithmic correctness.

---

#### Step 6: Full Retrieval (end-to-end retrieval, before Looker MCP)

**Correctness predicate:**
```
correct(retrieval_result, golden_query) =
    (result.model == golden.model)
    AND (result.explore == golden.explore)
    AND (set(result.dimensions) == set(golden.dimensions))
    AND (set(result.measures) == set(golden.measures))
    AND (result.filters ⊇ golden.filters)  # superset OK (mandatory filters added)
```

**Metrics (from `golden.py`):**
- `model_accuracy` = fraction of queries with correct model
- `explore_accuracy` = fraction with correct explore
- `avg_dimension_recall` and `avg_dimension_precision`
- `avg_measure_recall` and `avg_measure_precision`
- **Composite: Field Selection Accuracy** = fraction where ALL fields are exactly correct

The existing `evaluate_retrieval()` in `golden.py` already computes most of these. What is missing:
- Filter evaluation (not currently measured)
- Action correctness (was "proceed" correct, or should it have been "disambiguate"?)

**Recommended addition to `golden.py`:**
```python
# Filter evaluation
pred_filters = set(predicted.get("filters", {}).items())
exp_filters = set(expected.filters.items())
result["filter_recall"] = len(pred_filters & exp_filters) / len(exp_filters) if exp_filters else 1.0
result["filter_precision"] = len(pred_filters & exp_filters) / len(pred_filters) if pred_filters else 1.0

# Action correctness
result["action_correct"] = predicted.get("action") == "proceed"  # for data_query golden queries
```

---

#### Step 7: End-to-End (query to answer)

**Correctness predicate (layered, most strict to least):**

**Level 1: Execution Success** -- did the SQL run without error?
```
execution_success(query) = (looker_mcp_returns_rows AND no_sql_error)
```

**Level 2: Result Correctness** -- are the numbers right?
```
result_correct(predicted_rows, expected_rows) = 
    (set(predicted_columns) == set(expected_columns))
    AND (predicted_values ≈ expected_values within tolerance)
```

This is the hardest to evaluate because expected_values change daily (live data). Two approaches:
- **Frozen snapshot:** Run golden queries against a fixed BQ partition date and hardcode expected values
- **Relative correctness:** Run the golden query's known-correct SQL directly and compare to pipeline output. If both return same rows, the pipeline is correct.

**Level 3: User Satisfaction** -- does the answer help?
```
satisfaction(query) = thumbs_up / (thumbs_up + thumbs_down)
```
This requires live users. Not available until May launch. For now, focus on Levels 1 and 2.

---

### Golden Dataset Structure (Complete)

```json
{
  "id": "GQ-fin-001",
  "natural_language": "Total billed business by generation for small businesses",
  "complexity": "moderate",
  "domain": "spending_analysis",
  
  "expected_intent": "data_query",
  
  "expected_entities": {
    "metrics": ["total billed business"],
    "dimensions": ["generation"],
    "filter_terms": ["small businesses"],
    "time_range": null
  },
  
  "expected_retrieval": {
    "model": "finance",
    "explore": "finance_cardmember_360",
    "dimensions": ["cmdl_card_main.generation"],
    "measures": ["custins_customer_insights_cardmember.total_billed_business"],
    "filters": {
      "custins_customer_insights_cardmember.bus_seg": "OPEN",
      "custins_customer_insights_cardmember.partition_date": "last 90 days"
    }
  },
  
  "expected_sql_contains": [
    "SUM(custins_customer_insights_cardmember.billed_business)",
    "bus_seg = 'OPEN'",
    "cmdl_card_main"
  ],
  
  "validated": true,
  "validated_by": "Animesh",
  "validation_date": "2026-03-15"
}
```

---

### Minimum Golden Dataset Size (Statistical Reasoning)

**The core question:** If the true pipeline accuracy is p, how many test cases n do you need to distinguish p=0.90 from p=0.85 with 95% confidence?

Using a two-sided binomial test:
```
n >= (z_{alpha/2})^2 * p(1-p) / E^2

Where:
  z_{0.025} = 1.96
  p = 0.90 (target accuracy)
  E = 0.05 (acceptable error margin)

n >= (1.96)^2 * 0.90 * 0.10 / (0.05)^2
n >= 3.8416 * 0.09 / 0.0025
n >= 138.3
n = 139 minimum
```

**Recommendation by phase:**

| Phase | Queries | Purpose | Statistical Power |
|-------|---------|---------|-------------------|
| Demo (March) | 25 (from demo_queries.md) | Smoke test, find obvious bugs | CI: +/-20% (too wide for claims) |
| Milestone 1 (April) | 50 per explore = 250 total | Per-explore accuracy | CI: +/-8% per explore |
| Production (May) | 150 diverse queries | Overall pipeline accuracy | CI: +/-5% (can claim "90%+/-5%") |
| Steady state | 300+ | Statistical significance for all metrics | CI: +/-3% |

---

### Evaluation Framework Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    EVALUATION FRAMEWORK                        │
│                                                                │
│  ┌────────────────────┐     ┌────────────────────────────┐   │
│  │  Golden Dataset     │     │  Pipeline Under Test        │   │
│  │  (JSON files)       │────▶│  predict_fn(query) →        │   │
│  │                     │     │  RetrievalResult             │   │
│  │  GQ-fin-001.json    │     │                              │   │
│  │  GQ-fin-002.json    │     │  OR end_to_end_fn(query) →   │   │
│  │  ...                │     │  SQL results                  │   │
│  └────────────────────┘     └──────────────┬───────────────┘   │
│                                            │                    │
│                              ┌─────────────▼────────────────┐  │
│                              │  EVALUATOR                    │  │
│                              │                               │  │
│                              │  Per-step metrics:            │  │
│                              │    intent_accuracy             │  │
│                              │    entity_recall/precision     │  │
│                              │    vector_mrr                  │  │
│                              │    explore_accuracy            │  │
│                              │    filter_accuracy             │  │
│                              │    field_selection_accuracy    │  │
│                              │                               │  │
│                              │  End-to-end metrics:          │  │
│                              │    execution_success_rate      │  │
│                              │    result_correctness          │  │
│                              │                               │  │
│                              │  Breakdown by:                │  │
│                              │    complexity (simple/mod/cx)  │  │
│                              │    explore                     │  │
│                              │    failure mode                │  │
│                              └──────────────┬────────────────┘  │
│                                             │                   │
│                              ┌──────────────▼────────────────┐  │
│                              │  REPORT                        │  │
│                              │                                │  │
│                              │  Aggregate:                    │  │
│                              │    model_accuracy: 100%        │  │
│                              │    explore_accuracy: 94%       │  │
│                              │    dim_recall: 0.92            │  │
│                              │    measure_recall: 0.96        │  │
│                              │    filter_accuracy: 0.88       │  │
│                              │    e2e_success: 0.90           │  │
│                              │                                │  │
│                              │  Failures:                     │  │
│                              │    GQ-fin-023: wrong explore   │  │
│                              │    GQ-fin-041: missing filter  │  │
│                              └────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

### What Animesh Should Research

**Frameworks and papers to study:**

1. **BIRD-SQL Benchmark** -- The current gold standard for text-to-SQL evaluation. Uses execution accuracy (does the generated SQL return the same result set as the reference SQL?) rather than exact SQL match. Cortex should adopt this: compare result sets, not SQL strings, because Looker might generate different-but-equivalent SQL.

2. **Spider Benchmark** -- Earlier text-to-SQL benchmark. Uses "exact set match" for SQL clauses. Less relevant for Cortex because Looker generates the SQL, but the field selection accuracy metric is directly analogous.

3. **RAGAS (Retrieval Augmented Generation Assessment)** -- Framework for evaluating RAG pipelines. Relevant metrics: context precision, context recall, faithfulness, answer relevance. The "context precision/recall" maps directly to our field selection precision/recall.

4. **TailorSQL (2024)** -- Shows that few-shot examples improve NL2SQL by 2x. Validates our FAISS golden query approach. Their evaluation methodology (decomposed metrics per SQL clause) is worth adopting.

5. **Bootstrapping evaluation sets with LLMs** -- Use Gemini to generate candidate golden queries from explore schemas, then human-validate. This is the "synthetic generation" path mentioned in `golden.py`. Key insight: LLM-generated test cases are biased toward LLM-solvable queries. Supplement with adversarial cases (coded values, ambiguous terms, edge cases).

**The evaluation hierarchy Animesh should implement:**

```
Level 0: Smoke test (25 demo queries, manual pass/fail)
         → Are we in the right ballpark?

Level 1: Component evaluation (per-step metrics on 100+ queries)
         → Which step is the weakest link?

Level 2: Regression test (automated, runs on every PR)
         → Did this change break anything?

Level 3: A/B comparison (old pipeline vs new, same queries)
         → Is the change actually better?

Level 4: Live monitoring (production queries with thumbs up/down)
         → Is the system working for real users?
```

**Animesh's deliverables in order:**
1. Define the golden query JSON schema (extend `GoldenQuery` to include all expected intermediate outputs)
2. Write 25 golden queries from the demo_queries.md with full expected outputs at every step
3. Extend `evaluate_retrieval()` to include filter evaluation
4. Build `evaluate_classification()` for intent + entity extraction
5. Build the automated runner that outputs a report table
6. Expand to 50 queries per explore (250 total) by April
7. Add execution accuracy testing (compare Looker SQL output to reference query)

---

### Summary: The Key Invariants

These are the mathematical properties that, if they hold, guarantee pipeline correctness:

```
INVARIANT 1 (Entity Completeness):
  ∀ concept c in user_query that maps to a LookML field:
    c ∈ entities.metrics ∪ entities.dimensions ∪ entities.filter_terms

INVARIANT 2 (Vector Precision):
  ∀ entity e, the expected field f:
    rank(f, vector_results(e)) <= K  (K=20)
    score(f, vector_results(e)) >= SIMILARITY_FLOOR (0.70)

INVARIANT 3 (Structural Validity):
  ∀ field f in RetrievalResult.dimensions ∪ RetrievalResult.measures:
    ∃ path from RetrievalResult.explore to f in the AGE graph
    via edges [:BASE_VIEW|:JOINS*0..3] → [:HAS_DIMENSION|:HAS_MEASURE]

INVARIANT 4 (Filter Determinism):
  ∀ filter_term t resolved to (dimension d, value v):
    v ∈ SELECT DISTINCT d FROM BigQuery table
    (the resolved value actually exists in the data)

INVARIANT 5 (Partition Safety):
  ∀ RetrievalResult r where r.action == "proceed":
    ∃ partition_filter ∈ r.filters
    (no query ever runs without a partition filter)

INVARIANT 6 (Explore Uniqueness):
  RetrievalResult.action == "proceed" →
    exactly one explore selected with score gap > DISAMBIGUATION_THRESHOLD

INVARIANT 7 (Confidence Monotonicity):
  If confidence_gate fails, action ∈ {"clarify", "no_match"}
  If confidence_gate passes AND graph validates, action ∈ {"proceed", "disambiguate"}
  (confidence never increases after graph validation reduces the candidate set)
```

If Invariants 1-5 hold on every query in the golden dataset, the pipeline is correct by construction. Invariant 3 is the most critical -- it is the structural validation gate, and it is what separates Cortex from naive NL2SQL systems.

---

**Relevant files for this analysis:**

- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/retrieval/orchestrator.py` -- The 10-step retrieval brain with all thresholds and scoring
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/retrieval/models.py` -- FieldCandidate, RetrievalResult, GoldenQuery contracts
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/pipeline/state.py` -- CortexState lifecycle across all stages
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/retrieval/vector.py` -- pgvector schema and query templates
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/retrieval/graph_search.py` -- AGE Cypher queries and graph schema
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/retrieval/fusion.py` -- RRF formula and weights
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/retrieval/fewshot.py` -- FAISS golden query matching
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/evaluation/golden.py` -- Evaluation runner (needs filter eval addition)
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/adr/007-filter-value-resolution.md` -- Value catalog design
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/adr/004-semantic-layer-representation.md` -- pgvector + AGE architecture
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/adr/005-intent-entity-classification.md` -- Intent classification design
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/finance_model.model.lkml` -- The actual LookML model with 4-layer cost protection
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/custins_customer_insights_cardmember.view.lkml` -- Main view with measures
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/cmdl_card_main.view.lkml` -- Demographics view with generation dimension
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/demo_queries.md` -- 25 demo queries for initial testing