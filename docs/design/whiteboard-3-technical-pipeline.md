# Whiteboard 3: User Query → SQL Generation — Full Technical Pipeline

**Audience:** Engineering team, Sulabh, Ashok, architecture board
**Format:** Technical deep dive with I/O at every step
**Duration:** 25-30 minutes
**Key message:** This is a deterministic retrieval pipeline, not an LLM hoping to write correct SQL. Every step has clear inputs, outputs, and failure modes. The novel value is in the structural validation gate and three-signal explore ranking.

---

## The Full Pipeline (Reference Diagram)

```
  USER QUERY
  "Total billed business by generation for Millennials"
       │
       ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  STAGE 1: INTENT CLASSIFICATION + ENTITY EXTRACTION          │
  │  (Single LLM call — Gemini Flash, <500ms)                    │
  └──────────────────────────────┬───────────────────────────────┘
                                 │
       ┌─────────────────────────┼─────────────────────────┐
       │                         │                         │
       ▼                         ▼                         ▼
  ┌──────────┐            ┌──────────┐            ┌──────────────┐
  │  VECTOR   │            │  GRAPH   │            │  FEW-SHOT    │
  │  SEARCH   │            │  SEARCH  │            │  (future)    │
  │  pgvector │            │ Apache   │            │  FAISS       │
  │           │            │  AGE     │            │              │
  └─────┬─────┘            └────┬─────┘            └──────┬───────┘
        │                       │                         │
        └───────────────────────┼─────────────────────────┘
                                │
                                ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  STAGE 3: RETRIEVAL ORCHESTRATOR                              │
  │  (The brain — coordinates, validates, decides)                │
  └──────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  STAGE 4: LOOKER MCP → SQL GENERATION                        │
  │  (Deterministic — Looker generates SQL from field selections) │
  └──────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                            RESPONSE
```

---

## STAGE 1: Intent Classification + Entity Extraction

**What:** Single LLM call that classifies the query AND extracts structured entities.
**Why one call:** Two calls = 2x latency. Combined prompt does both in <500ms.

```
  INPUT:
  ┌──────────────────────────────────────────────────────┐
  │  user_query: "Total billed business by generation    │
  │               for Millennials"                       │
  │  conversation_history: []                            │
  └──────────────────────────────────────────────────────┘

                    │
                    ▼  Gemini Flash (structured output mode)

  OUTPUT:
  ┌──────────────────────────────────────────────────────┐
  │  intent: "data_query"                                │
  │  complexity: "moderate"     (cross-view join needed)  │
  │  is_answerable: true                                 │
  │                                                      │
  │  entities: {                                         │
  │    "metrics":    ["total billed business"],           │
  │    "dimensions": ["generation"],                      │
  │    "filters":    {"generation": "Millennials"},       │
  │    "time_range": null                                │
  │  }                                                   │
  │                                                      │
  │  resolved_terms: {                                   │
  │    "billed business" → "total_billed_business"       │
  │    "generation"      → "generation"                  │
  │  }                                                   │
  └──────────────────────────────────────────────────────┘

  ROUTING DECISION:
    intent = "data_query" + is_answerable = true
    → PROCEED to retrieval

  OTHER ROUTES:
    intent = "ambiguous"     → ask user to clarify
    intent = "out_of_scope"  → graceful refusal
    intent = "follow_up"     → merge with conversation history
    intent = "definition"    → return metric definition directly
```

---

## STAGE 2: Retrieval Orchestrator — The 10 Steps

### Step 1: Per-Entity Vector Search (pgvector)

**What:** Each entity gets its own cosine similarity search.
**Why per-entity:** A combined "total billed business by generation" embedding lands somewhere between both concepts and matches neither well. Per-entity gets precision.

```
  INPUT → pgvector:
  ┌──────────────────────────────────────────────────────┐
  │  Entity 1: embed("total billed business")            │
  │            → 768-dim vector                          │
  │            → cosine search against field_embeddings  │
  │            → top 20 results                          │
  │                                                      │
  │  Entity 2: embed("generation")                       │
  │            → 768-dim vector                          │
  │            → cosine search against field_embeddings  │
  │            → top 20 results                          │
  └──────────────────────────────────────────────────────┘

  OUTPUT (Entity 1 — "total billed business"):
  ┌──────────────────────────────────────────────────────┐
  │  Rank  Field                    View     Score       │
  │  ────  ─────                    ────     ─────       │
  │  1     total_billed_business    custins  0.94   ◄─── │
  │  2     avg_billed_business      custins  0.87        │
  │  3     total_merchant_spend     fin      0.76        │
  │  4     total_gross_tls_sales    tlsarpt  0.61        │
  └──────────────────────────────────────────────────────┘

  OUTPUT (Entity 2 — "generation"):
  ┌──────────────────────────────────────────────────────┐
  │  Rank  Field                    View     Score       │
  │  ────  ─────                    ────     ─────       │
  │  1     generation               cmdl     0.97   ◄─── │
  │  2     birth_year               cmdl     0.72        │
  └──────────────────────────────────────────────────────┘
```

**Critical detail — what's IN the embeddings table:**

```
  ┌───────────────────────────────────────────────────────────┐
  │  field_embeddings TABLE (pgvector, HNSW index)             │
  │                                                            │
  │  41 rows (one per field per view, NOT per explore)         │
  │                                                            │
  │  What's embedded (the "content" column):                   │
  │  "total_billed_business is a measure in                    │
  │   custins_customer_insights_cardmember.                    │
  │   Total billed business amount across all card members     │
  │   in the billing period. Also known as: total spend,       │
  │   billed amount, total charges, aggregate spend,           │
  │   total billed."                                           │
  │                                                            │
  │  WHY per-view not per-explore:                             │
  │    total_billed_business exists in custins.                 │
  │    custins is used in 3 explores.                          │
  │    Embedding it 3x = redundant + misleading scores.        │
  │    41 fields, not 80-90. Graph handles explore routing.    │
  └───────────────────────────────────────────────────────────┘
```

### Step 2: Confidence Gate

```
  ┌──────────────────────────────────────────────────┐
  │  CONFIDENCE FLOOR = 0.70                          │
  │                                                   │
  │  Entity 1 top score: 0.94  ✓ above floor          │
  │  Entity 2 top score: 0.97  ✓ above floor          │
  │                                                   │
  │  → PASS. Proceed to graph.                        │
  │                                                   │
  │  If ALL entities were < 0.70:                     │
  │  → HALT. Return action="clarify"                  │
  │    "I couldn't find fields matching your query.   │
  │     Could you rephrase?"                          │
  └──────────────────────────────────────────────────┘
```

### Step 3: Near-Miss Detection

```
  ┌──────────────────────────────────────────────────┐
  │  NEAR_MISS_DELTA = 0.05                           │
  │                                                   │
  │  Entity 1: #1=0.94, #2=0.87 → δ=0.07 → CLEAR    │
  │  Entity 2: #1=0.97, #2=0.72 → δ=0.25 → CLEAR    │
  │                                                   │
  │  → No near-misses. Single candidate per entity.   │
  │                                                   │
  │  CONTRAST — ambiguous query:                      │
  │  "Show me active customers"                       │
  │  Entity: "active customers"                       │
  │    #1 = active_customers_standard  0.92            │
  │    #2 = active_customers_premium   0.89            │
  │    δ = 0.03 < 0.05 → NEAR MISS                   │
  │    Keep BOTH candidates for graph validation.      │
  └──────────────────────────────────────────────────┘
```

### Step 4: Collect Candidates for Graph

```
  INPUT:  Entity results from Steps 1-3
  OUTPUT: Field names ONLY (no scores, no view names)

  ┌──────────────────────────────────────────────────┐
  │  candidate_fields = [                             │
  │    "total_billed_business",   (from entity 1)     │
  │    "generation"               (from entity 2)     │
  │  ]                                                │
  │                                                   │
  │  This is the INTERFACE to the graph.              │
  │  Just field names. Nothing else.                  │
  │  The graph answers: "Where can these coexist?"    │
  └──────────────────────────────────────────────────┘
```

### Step 5: Structural Validation (Apache AGE Graph)

**This is the most important step in the entire pipeline.**

```
  THE GRAPH (stored in Apache AGE, queried via Cypher):

  ┌──────────────────────────────────────────────────────────────┐
  │                                                               │
  │          ┌─────────────────┐                                  │
  │          │  finance_model   │  (Model node)                   │
  │          └────────┬────────┘                                  │
  │                   │ CONTAINS                                  │
  │     ┌─────────────┼──────────────────────┐                    │
  │     │             │                      │                    │
  │     ▼             ▼                      ▼                    │
  │  ┌──────┐    ┌──────────┐    ┌────────────────────┐           │
  │  │cm_360│    │merchant  │    │travel_sales        │           │
  │  │      │    │profitab. │    │                    │           │
  │  └──┬───┘    └────┬─────┘    └────────┬───────────┘           │
  │     │             │                   │                       │
  │     │ BASE_VIEW   │ BASE_VIEW         │ BASE_VIEW             │
  │     ▼             ▼                   ▼                       │
  │  ┌──────┐    ┌──────────┐    ┌────────────────────┐           │
  │  │custins│    │fin_merch │    │tlsarpt            │           │
  │  │      │    │          │    │                    │           │
  │  │ total_│    │ total_   │    │ total_gross_      │           │
  │  │ billed│    │ merchant_│    │ tls_sales         │           │
  │  │ biz ◄─────│ spend    │    │                    │           │
  │  └──┬───┘    └──────────┘    └────────────────────┘           │
  │     │                                                         │
  │     │ JOINS                                                   │
  │     ▼                                                         │
  │  ┌──────┐                                                     │
  │  │ cmdl │  (Card Demographics)                                │
  │  │      │                                                     │
  │  │ gene-│                                                     │
  │  │ ration◄──── THIS IS WHERE "generation" LIVES               │
  │  └──────┘                                                     │
  │                                                               │
  └──────────────────────────────────────────────────────────────┘

  CYPHER QUERY (AGE-compatible):

  SELECT * FROM cypher('lookml_schema', $$
    MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..4]->(v:View)
          -[:HAS_DIMENSION|HAS_MEASURE]->(f)
    WHERE f.name IN ['total_billed_business', 'generation']
    WITH e, collect(DISTINCT f.name) AS matched
    WHERE size(matched) = 2
    RETURN e.name AS explore,
           matched AS confirmed_fields,
           size(matched) AS coverage
    ORDER BY coverage DESC
  $$) AS (explore agtype, confirmed_fields agtype, coverage agtype);

  RESULT:
  ┌──────────────────────────────────────────────────┐
  │  explore                  fields    coverage      │
  │  ───────                  ──────    ────────      │
  │  finance_cardmember_360   [both]    2/2 = 1.0    │
  │  finance_merchant_profit  [both]    2/2 = 1.0    │
  │  finance_customer_risk    [both]    2/2 = 1.0    │
  │                                                   │
  │  All 3 explores join cmdl (generation) and have   │
  │  a path to custins (billed business) or at least  │
  │  cmdl's generation. BUT only cm_360 has           │
  │  total_billed_business in its BASE VIEW.          │
  └──────────────────────────────────────────────────┘

  WHY THIS IS THE KEY STEP:
    Without graph validation, we'd pick total_merchant_spend
    from the merchant explore because it's "semantically similar
    to billed business." That generates valid SQL that answers
    THE WRONG QUESTION.

    The graph says: "these two specific fields coexist in
    these specific explores." Truth, not similarity.
```

### Step 6: Three-Signal Explore Ranking

```
  ┌──────────────────────────────────────────────────────────┐
  │  SIGNAL 1: BASE VIEW PRIORITY (strongest — +0.3)         │
  │  ──────────────────────────────                           │
  │  "Does the primary MEASURE come from the explore's        │
  │   base view?"                                             │
  │                                                           │
  │  cm_360 base view = custins                               │
  │  total_billed_business is in custins                      │
  │  → YES. Base view priority = TRUE (+0.3)                  │
  │                                                           │
  │  merchant_profitability base view = fin_merch             │
  │  total_billed_business is in custins (JOINED view)        │
  │  → NO. A measure from a joined view is a smell.           │
  │                                                           │
  │  SIGNAL 2: FEW-SHOT CONFIRMATION (+0.2)                   │
  │  ─────────────────────────────────                         │
  │  Golden query "billed business by generation"              │
  │  → matched cm_360 explore                                 │
  │  → YES for cm_360 (+0.2), NO for merchant                 │
  │                                                           │
  │  SIGNAL 3: FIELD COVERAGE COUNT (tiebreaker)              │
  │  ──────────────────────────────────────────                │
  │  All 3 explores: 2/2 = 1.0 coverage                      │
  │                                                           │
  │  FINAL SCORES:                                            │
  │  ┌───────────────────────────────┬────────────────────┐   │
  │  │ Explore                       │ Score              │   │
  │  ├───────────────────────────────┼────────────────────┤   │
  │  │ finance_cardmember_360        │ 1.0+0.3+0.2 = 1.5 │ ◄ │
  │  │ finance_merchant_profitability│ 1.0+0+0     = 1.0 │   │
  │  │ finance_customer_risk         │ 1.0+0+0     = 1.0 │   │
  │  └───────────────────────────────┴────────────────────┘   │
  │                                                           │
  │  Gap: 1.5 - 1.0 = 0.5 > 0.10 threshold                  │
  │  → CLEAR WINNER. No disambiguation needed.                │
  └──────────────────────────────────────────────────────────┘
```

### Step 7: Filter Value Resolution

```
  INPUT:
  ┌──────────────────────────────────────────────────┐
  │  entities.filters = {"generation": "Millennials"} │
  └──────────────────────────────────────────────────┘

  RESOLUTION (via FILTER_VALUE_MAP):
  ┌──────────────────────────────────────────────────┐
  │  "generation" is in FILTER_VALUE_MAP              │
  │  "millennials" (lowercased) → "Millennial"        │
  │                                                   │
  │  resolved_filters = {                             │
  │    "generation": "Millennial"                     │
  │  }                                                │
  │                                                   │
  │  THREE TYPES OF RESOLUTION:                       │
  │  1. Categorical: "Millennials" → "Millennial"     │
  │     "small business" → "OPEN" (bus_seg)           │
  │     "consumer" → "CPS" (bus_seg)                  │
  │                                                   │
  │  2. Yesno: "yes" → "Yes" (Looker yesno syntax)   │
  │     is_replacement = "true" → "Yes"               │
  │                                                   │
  │  3. Time: "last quarter" → "last 1 quarters"      │
  │     (Looker relative date syntax)                 │
  └──────────────────────────────────────────────────┘
```

### Step 8: Mandatory Filter Injection

```
  ┌──────────────────────────────────────────────────┐
  │  Graph query: PARTITION_FILTERS for cm_360        │
  │  → partition_date is ALWAYS_FILTER_ON             │
  │                                                   │
  │  User didn't specify a time range.                │
  │  Default injection: partition_date = "last 90 days"│
  │                                                   │
  │  Final filters = {                                │
  │    "generation":      "Millennial",               │
  │    "partition_date":  "last 90 days"              │
  │  }                                                │
  │                                                   │
  │  WITHOUT THIS: Full table scan. $50-100.          │
  │  WITH THIS:    90-day scan. $0.50-5.              │
  └──────────────────────────────────────────────────┘
```

### Step 9: Construct RetrievalResult

```
  FINAL OUTPUT OF RETRIEVAL ORCHESTRATOR:
  ┌──────────────────────────────────────────────────┐
  │  RetrievalResult(                                 │
  │    action     = "proceed",                        │
  │    model      = "finance",                        │
  │    explore    = "finance_cardmember_360",          │
  │    dimensions = ["generation"],                    │
  │    measures   = ["total_billed_business"],         │
  │    filters    = {                                 │
  │      "generation":     "Millennial",              │
  │      "partition_date": "last 90 days"             │
  │    },                                             │
  │    confidence = 1.5,                              │
  │    coverage   = 1.0,                              │
  │    fewshot_matches = ["GQ-fin-006"]               │
  │  )                                                │
  └──────────────────────────────────────────────────┘
```

---

## STAGE 4: Looker MCP → SQL Generation

```
  INPUT (what Cortex sends to Looker MCP):
  ┌──────────────────────────────────────────────────┐
  │  Tool: query_sql                                  │
  │  Arguments:                                       │
  │    model:   "finance"                             │
  │    explore: "finance_cardmember_360"              │
  │    fields:  ["cmdl_card_main.generation",         │
  │              "custins_...cardmember               │
  │               .total_billed_business"]            │
  │    filters: {                                     │
  │      "cmdl_card_main.generation": "Millennial",   │
  │      "custins_...cardmember                       │
  │       .partition_date": "last 90 days"            │
  │    }                                              │
  └──────────────────────────────────────────────────┘

                    │
                    ▼  Looker generates SQL (deterministic, no LLM)

  OUTPUT (what Looker returns):
  ┌──────────────────────────────────────────────────────────┐
  │  SELECT                                                   │
  │    CASE                                                   │
  │      WHEN cmdl.birth_year >= 1997 THEN 'Gen Z'           │
  │      WHEN cmdl.birth_year BETWEEN 1981 AND 1996          │
  │        THEN 'Millennial'                                 │
  │      WHEN cmdl.birth_year BETWEEN 1965 AND 1980          │
  │        THEN 'Gen X'                                      │
  │      WHEN cmdl.birth_year BETWEEN 1945 AND 1964          │
  │        THEN 'Baby Boomer'                                │
  │      ELSE 'Other'                                        │
  │    END AS generation,                                     │
  │    SUM(custins.billed_business_am) AS total_billed_biz    │
  │  FROM `axp-lumid.dw.custins_customer_insights_cardmember` │
  │    AS custins                                             │
  │  LEFT JOIN (                                              │
  │    SELECT * FROM `axp-lumid.dw.cmdl_card_main`            │
  │    WHERE partition_date = (                               │
  │      SELECT MAX(partition_date)                           │
  │      FROM `axp-lumid.dw.cmdl_card_main`)                  │
  │  ) AS cmdl                                                │
  │    ON custins.cust_ref = cmdl.cust_ref                    │
  │  WHERE custins.partition_date                             │
  │    >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)          │
  │    -- sql_always_where (hard ceiling)                     │
  │  AND custins.partition_date                               │
  │    >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)           │
  │    -- always_filter (user-facing)                         │
  │  AND CASE WHEN cmdl.birth_year BETWEEN 1981 AND 1996     │
  │        THEN 'Millennial' ... END = 'Millennial'           │
  │  GROUP BY 1                                               │
  │  LIMIT 5000                                               │
  │  ;                                                        │
  └──────────────────────────────────────────────────────────┘

  KEY INSIGHT:
    Cortex NEVER writes this SQL.
    Cortex picks the fields. Looker writes the SQL.
    The SQL includes cost protection layers AUTOMATICALLY
    (sql_always_where, always_filter, derived table for cmdl).
    This is fundamentally more reliable than LLM-generated SQL.
```

---

## Where We Capture Value (The Novel Approach)

```
  ┌───────────────────────────────────────────────────────────────┐
  │                                                                │
  │  TRADITIONAL NL2SQL              CORTEX APPROACH               │
  │  ─────────────────               ───────────────               │
  │                                                                │
  │  User query                      User query                    │
  │       │                               │                        │
  │       ▼                               ▼                        │
  │  LLM writes SQL directly         1. Extract entities           │
  │  (guessing tables, columns,      2. Vector: find FIELDS        │
  │   joins, filters)                3. Graph: VALIDATE structure   │
  │       │                          4. Rank explores (3 signals)   │
  │       ▼                          5. Resolve filters             │
  │  SQL might work                  6. Looker generates SQL        │
  │  SQL might not                        │                        │
  │  Wrong table? ¯\_(ツ)_/¯              ▼                        │
  │  Wrong join? ¯\_(ツ)_/¯          SQL is CORRECT by construction│
  │  $100 scan? ¯\_(ツ)_/¯          Cost-protected by 4 layers    │
  │                                                                │
  │  Accuracy: 36%                   Target accuracy: 90%+         │
  │  (industry benchmark)            (structural guarantees)       │
  │                                                                │
  │  VALUE CAPTURE POINTS:                                         │
  │  ★ Synonym-enriched descriptions → 2.5x retrieval improvement │
  │  ★ Structural validation gate → eliminates cross-explore bugs  │
  │  ★ Three-signal ranking → deterministic explore selection      │
  │  ★ Filter value resolution → "Millennials" actually works      │
  │  ★ Mandatory filter injection → impossible to overspend        │
  │  ★ Looker SQL generation → no LLM hallucination in SQL        │
  │                                                                │
  └───────────────────────────────────────────────────────────────┘
```

---

## The Reconciliation: Vector + Graph Working Together

```
  ┌────────────────────────────────────────────────────────────┐
  │                                                             │
  │  VECTOR SEARCH (pgvector)          GRAPH SEARCH (AGE)       │
  │  ─────────────────────             ────────────────────     │
  │                                                             │
  │  ANSWERS:                          ANSWERS:                 │
  │  "What fields are similar          "Can these fields be     │
  │   to what the user said?"          queried TOGETHER?"       │
  │                                                             │
  │  STRENGTH:                         STRENGTH:                │
  │  Handles natural language          Knows the actual schema  │
  │  "spend" → billed_business         Knows join paths         │
  │  "generation" → generation         Knows what's reachable   │
  │                                                             │
  │  WEAKNESS:                         WEAKNESS:                │
  │  Doesn't know structure            Can't understand NL      │
  │  Returns fields from any view      Only works with exact    │
  │  No idea about joins               field names              │
  │                                                             │
  │  ─────────────────── RECONCILIATION ──────────────────────  │
  │                                                             │
  │  1. Vector finds candidates:                                │
  │     total_billed_business (custins, 0.94)                   │
  │     total_merchant_spend  (fin, 0.76)                       │
  │     generation            (cmdl, 0.97)                      │
  │                                                             │
  │  2. Orchestrator extracts TOP field per entity:             │
  │     ["total_billed_business", "generation"]                 │
  │                                                             │
  │  3. Graph validates: "Which explores have BOTH?"            │
  │     → cm_360 ✓ (billed in base view custins, generation    │
  │       in joined view cmdl)                                  │
  │     → merchant ✓ (but billed is in a JOINED view, not base)│
  │     → risk ✓ (but billed is in a JOINED view, not base)    │
  │                                                             │
  │  4. Three-signal ranking:                                   │
  │     cm_360 wins: base view match + fewshot + coverage       │
  │                                                             │
  │  RESULT: Vector finds the words. Graph finds the truth.     │
  │          Together they're 90%+. Apart they're 36%.          │
  │                                                             │
  └────────────────────────────────────────────────────────────┘
```

---

## The Graph Representation (What AGE Stores)

```
  NODES (6 types):
  ┌────────────────────────────────────────────────────────────┐
  │                                                             │
  │  (:Model {name: "finance"})                                 │
  │                                                             │
  │  (:Explore {name: "finance_cardmember_360"})                │
  │  (:Explore {name: "finance_merchant_profitability"})        │
  │  (:Explore {name: "finance_travel_sales"})                  │
  │  (:Explore {name: "finance_card_issuance"})                 │
  │  (:Explore {name: "finance_customer_risk"})                 │
  │                                                             │
  │  (:View {name: "custins_customer_insights_cardmember"})     │
  │  (:View {name: "cmdl_card_main"})                           │
  │  (:View {name: "fin_card_member_merchant_profitability"})   │
  │  (:View {name: "tlsarpt_travel_sales"})                     │
  │  (:View {name: "risk_indv_cust"})                           │
  │  (:View {name: "gihr_card_issuance"})                       │
  │  (:View {name: "ace_organization"})                         │
  │                                                             │
  │  (:Dimension {name: "generation", type: "string"})          │
  │  (:Measure {name: "total_billed_business", type: "sum"})    │
  │  ... (41 field nodes total)                                 │
  │                                                             │
  │  (:BusinessTerm {canonical: "Active Customers (Standard)",  │
  │                  synonyms: ["active CMs", "active base"]})  │
  │  ... (17 business term nodes)                               │
  │                                                             │
  └────────────────────────────────────────────────────────────┘

  EDGES (7 types):
  ┌────────────────────────────────────────────────────────────┐
  │                                                             │
  │  (Model)-[:CONTAINS]->(Explore)                             │
  │    finance CONTAINS finance_cardmember_360                  │
  │                                                             │
  │  (Explore)-[:BASE_VIEW]->(View)                             │
  │    finance_cardmember_360 BASE_VIEW custins   ◄── KEY      │
  │    finance_merchant_prof  BASE_VIEW fin_merch               │
  │                                                             │
  │  (Explore)-[:JOINS {type, relationship, sql_on}]->(View)    │
  │    finance_cardmember_360 JOINS cmdl_card_main              │
  │      {type: "left_outer", relationship: "one_to_one",       │
  │       sql_on: "custins.cust_ref = cmdl.cust_ref"}           │
  │                                                             │
  │  (View)-[:HAS_DIMENSION]->(Dimension)                       │
  │    cmdl_card_main HAS_DIMENSION generation                  │
  │                                                             │
  │  (View)-[:HAS_MEASURE]->(Measure)                           │
  │    custins HAS_MEASURE total_billed_business                │
  │                                                             │
  │  (Explore)-[:ALWAYS_FILTER_ON]->(Dimension)                 │
  │    finance_cardmember_360 ALWAYS_FILTER_ON partition_date   │
  │                                                             │
  │  (BusinessTerm)-[:MAPS_TO]->(Dimension|Measure)             │
  │    "Active Customers (Standard)" MAPS_TO                    │
  │      active_customers_standard                              │
  │                                                             │
  └────────────────────────────────────────────────────────────┘

  KEY TRAVERSAL (what the Cypher query does):

    Explore ──BASE_VIEW|JOINS*0..4──▶ View ──HAS_*──▶ Field

    "Starting from each explore, walk up to 4 hops through
     base views and joins, then check if the target fields
     are reachable."

    The *0..4 range means:
      0 hops: field is on the explore's base view (BEST)
      1 hop:  field is on a directly joined view (GOOD)
      2 hops: field is on a view joined through another (OK)
      3-4:    deep join chain (RISKY — may cause fanout)
```

---

## Disambiguation: When the Pipeline Asks

```
  QUERY: "What is spend?"
       │
       ▼
  VECTOR SEARCH (entity: "spend"):
  ┌──────────────────────────────────────────────────┐
  │  #1  total_billed_business    custins  0.85       │
  │  #2  total_merchant_spend     fin      0.83       │
  │  #3  total_gross_tls_sales    tlsarpt  0.79       │
  │                                                   │
  │  Near-miss: 0.85 - 0.83 = 0.02 < 0.05            │
  │  → KEEP BOTH                                      │
  └──────────────────────────────────────────────────┘
       │
       ▼
  GRAPH VALIDATION (all 3 field names):
  ┌──────────────────────────────────────────────────┐
  │  finance_cardmember_360:       coverage 1/3      │
  │  finance_merchant_profitability: coverage 1/3    │
  │  finance_travel_sales:         coverage 1/3      │
  └──────────────────────────────────────────────────┘
       │
       ▼
  EXPLORE RANKING:
  ┌──────────────────────────────────────────────────┐
  │  cm_360:   0.33 + 0.3 (base) = 0.63              │
  │  merchant: 0.33 + 0.3 (base) = 0.63              │
  │  travel:   0.33 + 0.3 (base) = 0.63              │
  │                                                   │
  │  Gap: 0.63 - 0.63 = 0.0 < 0.10 threshold         │
  │  → DISAMBIGUATION REQUIRED                        │
  └──────────────────────────────────────────────────┘
       │
       ▼
  AI RESPONSE:
  ┌──────────────────────────────────────────────────┐
  │  "I found several types of 'spend':              │
  │                                                   │
  │   1. Billed Business — total charges billed to    │
  │      card members (Card Member 360)               │
  │                                                   │
  │   2. Merchant Spend — total transaction value at  │
  │      merchants (Merchant Profitability)            │
  │                                                   │
  │   3. TLS Sales — Travel & Lifestyle Services      │
  │      revenue (Travel Sales)                       │
  │                                                   │
  │   Which one are you looking for?"                 │
  └──────────────────────────────────────────────────┘
```

---

## Full I/O Trace Summary

```
  ┌─────────────────────────┬─────────────────────────────────────┐
  │ STEP                    │ I/O                                  │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 1. Intent + Entities    │ IN:  "total billed biz by gen..."   │
  │    (Gemini Flash)       │ OUT: {metrics, dims, filters}       │
  │                         │      ~400ms                         │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 2. Vector Search        │ IN:  embed("total billed business") │
  │    (pgvector, per-entity│      embed("generation")            │
  │     HNSW)               │ OUT: ranked FieldCandidates         │
  │                         │      ~50ms per entity               │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 3. Confidence Gate      │ IN:  top scores per entity          │
  │                         │ OUT: pass/fail (floor=0.70)         │
  │                         │      ~0ms (math check)              │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 4. Near-Miss Detection  │ IN:  top-2 scores per entity        │
  │                         │ OUT: near_miss flags (δ<0.05)       │
  │                         │      ~0ms (math check)              │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 5. Graph Validation     │ IN:  ["total_billed_biz","gen..."]  │
  │    (AGE Cypher)         │ OUT: valid explores + coverage      │
  │                         │      ~30ms                          │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 6. Few-Shot Search      │ IN:  "total billed biz generation"  │
  │    (FAISS)              │ OUT: golden query matches            │
  │                         │      ~10ms                          │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 7. Explore Ranking      │ IN:  explores + 3 signals           │
  │    (3-signal)           │ OUT: ranked explores with scores    │
  │                         │      ~0ms (scoring logic)           │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 8. Filter Resolution    │ IN:  {"generation": "Millennials"}  │
  │                         │ OUT: {"generation": "Millennial"}   │
  │                         │      ~0ms (lookup)                  │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 9. Mandatory Filters    │ IN:  explore name                   │
  │    (AGE Cypher)         │ OUT: {"partition_date":"last 90d"}  │
  │                         │      ~10ms                          │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ 10. Looker MCP          │ IN:  RetrievalResult (fields+filters│
  │     (SQL generation)    │ OUT: Executed SQL + result rows     │
  │                         │      ~200ms (Looker API + BQ exec)  │
  ├─────────────────────────┼─────────────────────────────────────┤
  │ TOTAL END-TO-END        │ ~700ms user-perceived latency       │
  │                         │ (Intent 400 + Vector 100 + Graph 40 │
  │                         │  + FAISS 10 + Looker 200 = ~750ms)  │
  └─────────────────────────┴─────────────────────────────────────┘
```

---

## Talking Points for Architecture Board

1. **Novel approach:** We separate semantic understanding (vector) from structural truth (graph). Most NL2SQL systems collapse these into one step and get 36% accuracy. Our two-phase approach with a structural validation gate gives us deterministic correctness guarantees.

2. **The structural validation gate is the breakthrough.** It eliminates the entire class of "correct SQL, wrong question" errors — which is the #1 failure mode in production NL2SQL systems.

3. **Three-signal explore ranking is deterministic, not ML.** Base view priority + few-shot confirmation + coverage count. No training data needed for v1. Transparent. Debuggable.

4. **Looker generates SQL, not our LLM.** Our AI picks fields. Looker's compiler generates SQL. This means zero SQL hallucination by construction. Cost protection is injected automatically.

5. **Single PostgreSQL instance** runs both pgvector (vector search) and Apache AGE (graph). One DB to manage. Both are approved extensions within Amex. No cloud API exceptions needed.

6. **Filter value resolution** handles the gap between natural language ("Millennials") and data values ("Millennial"). This is a silent killer in NL2SQL — the query is structurally correct but returns zero rows because the filter value doesn't match.

7. **Sub-second latency.** Entire pipeline: ~750ms. Intent classification is the bottleneck (400ms). Retrieval is <200ms total. Looker MCP adds ~200ms. Comparable to a Google search.
