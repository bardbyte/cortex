# ADR-004: Semantic Layer Representation Strategy (pgvector + AGE)

**Date:** March 6, 2026
**Status:** Accepted
**Decider:** Saheb
**Consulted:** Sulabh, Abhishek, Ravi J

---

## Decision

We will use **PostgreSQL with pgvector + Apache AGE** as the unified storage layer for the Cortex hybrid retrieval system, replacing the original Neo4j + Vertex AI Search design. FAISS remains for in-memory few-shot matching. All components run locally within the Amex network.

This ADR documents:
1. The technology choice (pgvector + AGE over Neo4j + Vertex AI)
2. How LookML metadata from views and explores is stored and represented across the three retrieval channels
3. A complete end-to-end query walkthrough using actual Finance BU data

---

## Context

The [Cortex Hybrid Retrieval Design Doc](../../docs/design/cortex-hybrid-retrieval-design.md) specifies a three-channel retrieval system: Vector Search (semantic matching), Graph Search (structural validation), and Few-Shot Match (pattern reuse). The design doc is technology-agnostic on the storage layer. This ADR makes the technology concrete.

### Why Not the Original Design (Neo4j + Vertex AI Search)?

| Concern | Neo4j + Vertex AI Search | pgvector + AGE |
|---------|------------------------|----------------|
| Amex approval | Neo4j not approved. Vertex AI Search requires cloud API exception. | PostgreSQL approved. pgvector and AGE are extensions — same approval path. |
| Infrastructure | 3 separate systems (Vertex AI Search, Neo4j, FAISS) | 2 systems (PostgreSQL, FAISS) |
| Deployment | Cloud-dependent (Vertex AI), requires GCP networking | Fully local. Runs within Amex network, no cloud egress. |
| Query language | Vector: REST API. Graph: Cypher. | Vector: SQL. Graph: Cypher (AGE supports Cypher natively). |
| Operational cost | Neo4j Enterprise license + Vertex AI Search pricing | PostgreSQL (free) + extensions (free) |
| Team expertise | Team knows SQL, would need Neo4j training | Team knows SQL, AGE Cypher is compatible with Neo4j Cypher |
| Single-query capability | Not possible across systems | Can combine vector similarity + graph traversal in one SQL query |

**Decision rationale:** pgvector + AGE gives us the same retrieval capabilities with fewer moving parts, lower cost, full local deployment, and Amex approval. The Cypher queries from the design doc port to AGE with minimal changes.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CORTEX RETRIEVAL STORAGE                         │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    PostgreSQL Instance (local)                     │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────┐  ┌──────────────────────────────┐  │  │
│  │  │  pgvector Extension       │  │  Apache AGE Extension         │  │  │
│  │  │                           │  │                               │  │  │
│  │  │  Table: field_embeddings  │  │  Graph: lookml_schema         │  │  │
│  │  │  ┌─────────────────────┐ │  │  ┌───────────────────────┐   │  │  │
│  │  │  │ id (PK)             │ │  │  │ (:Model)              │   │  │  │
│  │  │  │ field_key (unique)  │ │  │  │ (:Explore)            │   │  │  │
│  │  │  │ embedding (vector)  │ │  │  │ (:View)               │   │  │  │
│  │  │  │ content (text)      │ │  │  │ (:Dimension)          │   │  │  │
│  │  │  │ field_name          │ │  │  │ (:Measure)            │   │  │  │
│  │  │  │ field_type          │ │  │  │ (:BusinessTerm)       │   │  │  │
│  │  │  │ view_name           │ │  │  │                       │   │  │  │
│  │  │  │ explore_name        │ │  │  │ [:CONTAINS]           │   │  │  │
│  │  │  │ model_name          │ │  │  │ [:BASE_VIEW]          │   │  │  │
│  │  │  │ group_label         │ │  │  │ [:JOINS]              │   │  │  │
│  │  │  │ tags (text[])       │ │  │  │ [:HAS_DIMENSION]      │   │  │  │
│  │  │  │ measure_type        │ │  │  │ [:HAS_MEASURE]        │   │  │  │
│  │  │  └─────────────────────┘ │  │  │ [:ALWAYS_FILTER_ON]   │   │  │  │
│  │  │                           │  │  │ [:MAPS_TO]            │   │  │  │
│  │  │  Index: HNSW on          │  │  └───────────────────────┘   │  │  │
│  │  │  embedding column        │  │                               │  │  │
│  │  └──────────────────────────┘  └──────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────────────────┐                                          │
│  │  FAISS (in-memory)        │                                          │
│  │                           │                                          │
│  │  Index: golden_queries    │                                          │
│  │  ┌─────────────────────┐ │                                          │
│  │  │ embedding (vector)  │ │                                          │
│  │  │ query_text          │ │                                          │
│  │  │ model               │ │                                          │
│  │  │ explore             │ │                                          │
│  │  │ dimensions[]        │ │                                          │
│  │  │ measures[]          │ │                                          │
│  │  │ filters{}           │ │                                          │
│  │  └─────────────────────┘ │                                          │
│  └──────────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Channel 1: Vector Search (pgvector)

### Purpose
Semantic field matching — bridging the gap between business language ("total spend") and LookML field names (`billed_business`).

### Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE field_embeddings (
    id              SERIAL PRIMARY KEY,
    field_key       TEXT UNIQUE NOT NULL,  -- "finance.finance_cardmember_360.custins.billed_business"
    embedding       vector(768) NOT NULL,  -- text-embedding-005 output
    content         TEXT NOT NULL,          -- the text that was embedded
    field_name      TEXT NOT NULL,          -- "billed_business"
    field_type      TEXT NOT NULL,          -- "dimension" | "measure"
    measure_type    TEXT,                   -- "sum" | "average" | "count_distinct" | null
    view_name       TEXT NOT NULL,          -- "custins_customer_insights_cardmember"
    explore_name    TEXT NOT NULL,          -- "finance_cardmember_360"
    model_name      TEXT NOT NULL,          -- "finance"
    label           TEXT,                   -- "Billed Business"
    group_label     TEXT,                   -- "Spending"
    tags            TEXT[],                 -- '{"cluster_key"}'
    hidden          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for approximate nearest neighbor search
CREATE INDEX ON field_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### Per-Field Document Construction

Each LookML dimension and measure becomes one row. The `content` column — the text that gets embedded — follows this template:

```
{field_name} is a {field_type} ({measure_type}) in the {view_name} view,
accessible through the {explore_name} explore in the {model_name} model.
{label}: {description}
```

**Example — `billed_business` dimension from `custins_customer_insights_cardmember.view.lkml`:**

```
field_key: "finance.finance_cardmember_360.custins_customer_insights_cardmember.billed_business"

content (embedded):
  "billed_business is a dimension (number) in the custins_customer_insights_cardmember view,
   accessible through the finance_cardmember_360 explore in the finance model.
   Billed Business: Total billed business amount for the card member, representing total
   spend charged to the card. Also known as: total spend, billing volume, charged amount,
   billed amount, card spend."
```

**Why per-field, not per-view:** When a user asks about "total spend", per-field chunking returns `billed_business` (the exact field). Per-view chunking returns the entire 163-line `custins_customer_insights_cardmember` view — 15+ fields, most irrelevant. At 100K+ fields across 100+ tables, precision is everything.

### Query Pattern

```sql
-- Vector similarity search for "total spend by generation"
-- Searches for the two extracted entities separately

-- Entity 1: "total spend"
SELECT field_key, field_name, view_name, explore_name, label,
       1 - (embedding <=> $1) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
  AND model_name = 'finance'  -- if model already identified
ORDER BY embedding <=> $1
LIMIT 20;

-- $1 = embedding of "total spend. Also known as: total spend, spending,
--       purchase amount, billed business"
```

### Corpus Statistics (Finance BU)

| Metric | Count |
|--------|-------|
| Total fields indexed | 52 |
| Dimensions | 34 |
| Measures | 18 |
| Hidden fields (excluded) | 11 |
| Visible fields in corpus | 41 |
| Views | 7 |
| Explores | 5 |

---

## Channel 2: Graph Search (Apache AGE)

### Purpose
Structural validation — ensuring that candidate fields from vector search can actually be queried together within a single Looker explore. Vector search has no understanding of join paths; the graph encodes them.

### Graph Schema

```sql
-- Load AGE extension
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Create the LookML schema graph
SELECT create_graph('lookml_schema');
```

**Nodes and edges mirror the LookML structure:**

```
(:Model {name, connection})
  -[:CONTAINS]->
(:Explore {name, label, description, group_label, sql_always_where})
  -[:BASE_VIEW]->
(:View {name, sql_table_name})

(:Explore)-[:JOINS {sql_on, relationship, type}]->(:View)

(:View)-[:HAS_DIMENSION]->(:Dimension {name, type, label, description, tags, hidden})
(:View)-[:HAS_MEASURE]->(:Measure {name, type, label, description, measure_type, tags, hidden})

(:Explore)-[:ALWAYS_FILTER_ON]->(:Dimension)

(:BusinessTerm {term, synonyms})-[:MAPS_TO]->(:Dimension|:Measure)
```

**Finance BU graph loaded from LookML files:**

```
Nodes:
  1 Model (finance)
  5 Explores (finance_cardmember_360, finance_merchant_profitability,
              finance_travel_sales, finance_card_issuance, finance_customer_risk)
  7 Views (custins, cmdl, fin_card_member, tlsarpt, risk_indv, gihr, ace_org)
  34 Dimensions
  18 Measures
  17+ BusinessTerms

Edges:
  5 CONTAINS (model → explores)
  5 BASE_VIEW (explore → primary view)
  12 JOINS (explore → joined views)
  34 HAS_DIMENSION (view → dimensions)
  18 HAS_MEASURE (view → measures)
  5 ALWAYS_FILTER_ON (explore → partition dimensions)
  17+ MAPS_TO (business term → fields)
```

### Core Cypher Queries (AGE-compatible)

**1. Validate fields in explore** — "Can these fields be queried together?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
  WHERE ALL(field IN ['billed_business', 'generation']
    WHERE (v)-[:HAS_DIMENSION|HAS_MEASURE]->({name: field}))
  RETURN e.name AS explore, collect(DISTINCT v.name) AS views
$$) AS (explore agtype, views agtype);
```

**Result:** `finance_cardmember_360` — because `billed_business` is in `custins` (base view) and `generation` is in `cmdl` (joined view).

**2. Get required filters for an explore** — "What must I filter on?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore {name: 'finance_cardmember_360'})-[:ALWAYS_FILTER_ON]->(d:Dimension)
  RETURN d.name AS required_filter, d.tags AS tags
$$) AS (required_filter agtype, tags agtype);
```

**Result:** `partition_date` with tags `["partition_key"]`

**3. Resolve business term** — "What does 'active customers' map to?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (bt:BusinessTerm)-[:MAPS_TO]->(f)
  WHERE bt.term =~ '(?i).*active customer.*'
  RETURN bt.term, labels(f)[0] AS field_type, f.name, f.label, f.description
$$) AS (term agtype, field_type agtype, name agtype, label agtype, description agtype);
```

**Result:** Two matches — `active_customers_standard` ("billed business > $50") and `active_customers_premium` ("billed business > $100"). The descriptions disambiguate.

**4. Find join path between two views** — "How do custins and cmdl connect?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:JOINS {type: j_type, relationship: rel}]->(v:View {name: 'cmdl_card_main'})
  WHERE (e)-[:BASE_VIEW]->(:View {name: 'custins_customer_insights_cardmember'})
  RETURN e.name, j_type, rel
$$) AS (explore agtype, join_type agtype, relationship agtype);
```

**Result:** `finance_cardmember_360`, `left_outer`, `one_to_one` — joined on `cust_ref`.

**5. Get partition filters** — "What must the agent enforce?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:ALWAYS_FILTER_ON]->(d:Dimension)
  RETURN e.name, d.name AS partition_field
$$) AS (explore agtype, partition_field agtype);
```

---

## Channel 3: Few-Shot Match (FAISS)

### Purpose
Pattern matching against golden queries — proven query-to-field mappings that exploit the power-law distribution of enterprise questions (80% are variations of 20% of patterns).

### Corpus Structure

```json
{
  "id": "GQ-fin-001",
  "natural_language": "What was total billed business for Millennial customers last quarter?",
  "embedding": [0.12, -0.34, ...],
  "model": "finance",
  "explore": "finance_cardmember_360",
  "dimensions": ["cmdl_card_main.generation"],
  "measures": ["custins_customer_insights_cardmember.total_billed_business"],
  "filters": {
    "custins_customer_insights_cardmember.partition_date": "last quarter",
    "cmdl_card_main.generation": "Millennial"
  }
}
```

### Why FAISS Instead of pgvector

The golden query corpus is small (50-2000 entries), entirely in-memory, and accessed on every query. FAISS with IVF gives <5ms latency in-memory vs. 10-30ms for a pgvector round-trip. At this corpus size, the network hop to PostgreSQL is the bottleneck, not the search. FAISS stays.

### Configuration
- Embedding: `text-embedding-005` (same model as vector search)
- Index: FAISS IVF with 256 centroids
- Top-K: 5 similar queries
- Threshold: cosine similarity > 0.85
- Corpus refresh: on golden dataset update

---

## LookML-to-Storage Pipeline

When a LookML project is deployed, a sync pipeline updates all three stores:

```
LookML Files (git push)
    │
    ├──→ Parse LookML (lkml parser)
    │       │
    │       ├──→ Extract fields → embed → INSERT INTO field_embeddings (pgvector)
    │       │
    │       ├──→ Extract structure → CREATE nodes/edges (AGE graph)
    │       │
    │       └──→ Map business terms → CREATE BusinessTerm nodes (AGE graph)
    │
    └──→ Golden queries unchanged (FAISS corpus updated separately)
```

**Sync trigger:** Git webhook on LookML repository push (per ADR-002, each BU has its own repo).

**Idempotent sync:** Full rebuild on each deploy. At Finance BU scale (7 views, 52 fields), full rebuild takes <5 seconds. At 100+ tables, switch to incremental diff.

---

## End-to-End Walkthrough: Actual Finance BU Query

**User question:** "What was total billed business for Millennial customers last quarter?"

### Step 1: Entity Extraction (Gemini Flash, ~200ms)

```json
{
  "metrics": ["total billed business"],
  "dimensions": ["Millennial"],
  "time_range": "last quarter",
  "filters": [
    {"field": "generation", "value": "Millennial", "operator": "="}
  ]
}
```

The entity extractor identifies:
- "total billed business" → metric (needs to find a measure)
- "Millennial" → dimension value filter (generation = Millennial)
- "last quarter" → time filter

### Step 2: Vector Search — pgvector (~30ms)

**Query 1:** Embed "total billed business. Also known as: total spend, billing volume"

```sql
SELECT field_key, field_name, label, explore_name, view_name,
       1 - (embedding <=> $1) AS similarity
FROM field_embeddings
WHERE hidden = FALSE
ORDER BY embedding <=> $1
LIMIT 10;
```

**Results (ranked by similarity):**

| Rank | Field | View | Explore | Similarity |
|------|-------|------|---------|-----------|
| 1 | `total_billed_business` | custins | finance_cardmember_360 | 0.96 |
| 2 | `avg_billed_business` | custins | finance_cardmember_360 | 0.91 |
| 3 | `billed_business` (dim) | custins | finance_cardmember_360 | 0.89 |
| 4 | `total_merchant_spend` | fin_card_member | finance_merchant_profitability | 0.82 |
| 5 | `total_gross_tls_sales` | tlsarpt | finance_travel_sales | 0.71 |

**Query 2:** Embed "Millennial generation. Also known as: generational segment, age group"

| Rank | Field | View | Explore | Similarity |
|------|-------|------|---------|-----------|
| 1 | `generation` | cmdl | finance_cardmember_360 | 0.95 |
| 2 | `birth_year` | cmdl | finance_cardmember_360 | 0.78 |

### Step 3: Graph Search — AGE (~10ms)

**Query:** "Which explores contain BOTH `total_billed_business` AND `generation`?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
  WHERE ALL(field IN ['total_billed_business', 'generation']
    WHERE (v)-[:HAS_DIMENSION|HAS_MEASURE]->({name: field}))
  RETURN e.name AS explore, collect(DISTINCT v.name) AS views_used
$$) AS (explore agtype, views_used agtype);
```

**Result:**
```
explore: "finance_cardmember_360"
views_used: ["custins_customer_insights_cardmember", "cmdl_card_main"]
```

Only ONE explore contains both fields. No disambiguation needed.

**Get required filters:**
```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore {name: 'finance_cardmember_360'})-[:ALWAYS_FILTER_ON]->(d)
  RETURN d.name AS required_filter
$$) AS (required_filter agtype);
```

**Result:** `partition_date` — the query MUST include this filter.

### Step 4: Few-Shot Match — FAISS (~5ms)

Embed the full query "What was total billed business for Millennial customers last quarter?" and search the golden corpus.

**Top match (similarity: 0.93):**
```json
{
  "id": "GQ-fin-003",
  "natural_language": "Show me average billed business by generation",
  "model": "finance",
  "explore": "finance_cardmember_360",
  "dimensions": ["cmdl_card_main.generation"],
  "measures": ["custins_customer_insights_cardmember.avg_billed_business"],
  "filters": {"custins_customer_insights_cardmember.partition_date": "last 90 days"}
}
```

This confirms: same explore, similar fields, and reminds the system to include `partition_date` filter.

### Step 5: RRF Fusion (~1ms)

Merge three ranked lists with weights: graph=1.5, fewshot=1.2, vector=1.0

**Fused result (top fields):**

| Field | RRF Score | Source Channels |
|-------|-----------|----------------|
| `custins.total_billed_business` | 0.087 | vector(#1) + graph(#1) + fewshot(partial) |
| `cmdl.generation` | 0.082 | vector(#1) + graph(#1) + fewshot(#1) |
| `custins.partition_date` | 0.071 | graph(required) + fewshot(#1) |
| `custins.avg_billed_business` | 0.031 | vector(#2) |

### Step 6: Structural Validation Gate — AGE (~10ms)

**Final check:** "Are `total_billed_business`, `generation`, and `partition_date` all reachable from ONE explore?"

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
  WHERE ALL(field IN ['total_billed_business', 'generation', 'partition_date']
    WHERE (v)-[:HAS_DIMENSION|HAS_MEASURE]->({name: field}))
  RETURN e.name
$$) AS (explore agtype);
```

**Result:** `finance_cardmember_360` — VALID. Proceed.

### Step 7: Construct RetrievalResult

```python
RetrievalResult(
    action="proceed",
    confidence=0.94,
    model="finance",
    explore="finance_cardmember_360",
    dimensions=["cmdl_card_main.generation"],
    measures=["custins_customer_insights_cardmember.total_billed_business"],
    filters={
        "custins_customer_insights_cardmember.partition_date": "last quarter",
        "cmdl_card_main.generation": "Millennial",
    },
)
```

### Step 8: Looker MCP → SQL → Answer (~1.5s)

The `RetrievalResult` is passed to Looker MCP's `query_sql` tool:

```
Tool: query_sql
Args:
  model: "finance"
  explore: "finance_cardmember_360"
  dimensions: ["cmdl_card_main.generation"]
  measures: ["custins_customer_insights_cardmember.total_billed_business"]
  filters:
    custins_customer_insights_cardmember.partition_date: "last quarter"
    cmdl_card_main.generation: "Millennial"
```

Looker generates deterministic SQL (no LLM involved):

```sql
SELECT
  CASE
    WHEN cmdl_card_main.birth_year >= 1997 THEN 'Gen Z'
    WHEN cmdl_card_main.birth_year BETWEEN 1981 AND 1996 THEN 'Millennial'
    WHEN cmdl_card_main.birth_year BETWEEN 1965 AND 1980 THEN 'Gen X'
    WHEN cmdl_card_main.birth_year BETWEEN 1945 AND 1964 THEN 'Baby Boomer'
    ELSE 'Other'
  END AS generation,
  SUM(custins_customer_insights_cardmember.billed_business) AS total_billed_business
FROM `amex-project.finance_dataset.custins_customer_insights_cardmember`
  AS custins_customer_insights_cardmember
LEFT JOIN `amex-project.finance_dataset.cmdl_card_main`
  AS cmdl_card_main
  ON custins_customer_insights_cardmember.cust_ref = cmdl_card_main.cust_ref
WHERE
  -- Layer 1: sql_always_where (hidden, hard ceiling)
  custins_customer_insights_cardmember.partition_date
    >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
  -- Layer 2: always_filter (user-visible, injected by Looker)
  AND custins_customer_insights_cardmember.partition_date
    >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 QUARTER), QUARTER)
  AND custins_customer_insights_cardmember.partition_date
    < DATE_TRUNC(CURRENT_DATE(), QUARTER)
  -- User filter
  AND (CASE
    WHEN cmdl_card_main.birth_year BETWEEN 1981 AND 1996 THEN 'Millennial'
    ELSE NULL END) = 'Millennial'
GROUP BY 1
```

**Note:** Looker automatically injected `sql_always_where` (365-day cap) and resolved "last quarter" into proper date bounds. The AI agent did NOT generate this SQL — Looker did, deterministically from the LookML definitions.

### Total Latency Breakdown

| Stage | Time | System |
|-------|------|--------|
| Entity extraction | ~200ms | Gemini Flash (via SafeChain) |
| Vector search | ~30ms | pgvector (local PG) |
| Graph search | ~10ms | AGE (local PG) |
| Few-shot match | ~5ms | FAISS (in-memory) |
| RRF fusion | ~1ms | Python (CPU) |
| Structural validation | ~10ms | AGE (local PG) |
| **Total retrieval** | **~260ms** | **No LLM in retrieval path** |
| Looker MCP (SQL gen) | ~500ms | Network call |
| BigQuery execution | ~1-3s | Depends on data |
| **Total pipeline** | **~2-4s** | |

---

## Consequences

### Positive
- Single PostgreSQL instance handles both vector and graph — operational simplicity
- Fully local deployment — no cloud API dependencies, no network egress
- Amex-approved technology stack — no exception requests needed
- AGE supports Cypher — design doc queries port with minimal changes
- Combined queries possible (vector search filtered by graph relationships in one SQL statement)

### Negative
- pgvector HNSW is less optimized than dedicated vector DBs (Pinecone, Weaviate) at >1M vectors — acceptable at our scale (~50K fields at full 100-table deployment)
- AGE is less mature than Neo4j for complex graph algorithms — we only need traversal queries, not PageRank or community detection
- Team needs to learn AGE Cypher syntax (minor differences from Neo4j Cypher)

### Risks
- AGE extension stability — mitigated by simple graph queries (no advanced algorithms)
- pgvector performance at scale — mitigated by HNSW index; benchmark at 50K vectors before committing

---

## Appendix: Finance BU Field Embedding Catalog

All 41 visible fields that are embedded in pgvector for the Finance BU:

| View | Field | Type | Explore |
|------|-------|------|---------|
| custins | total_customers | measure | finance_cardmember_360 |
| custins | active_customers_standard | measure | finance_cardmember_360 |
| custins | active_customers_premium | measure | finance_cardmember_360 |
| custins | total_billed_business | measure | finance_cardmember_360 |
| custins | avg_billed_business | measure | finance_cardmember_360 |
| custins | avg_customer_tenure | measure | finance_cardmember_360 |
| custins | customers_with_authorized_users | measure | finance_cardmember_360 |
| custins | billed_business | dimension | finance_cardmember_360 |
| custins | is_active_standard | dimension | finance_cardmember_360 |
| custins | is_active_premium | dimension | finance_cardmember_360 |
| custins | customer_tenure | dimension | finance_cardmember_360 |
| custins | customer_tenure_tier | dimension | finance_cardmember_360 |
| custins | has_authorized_users | dimension | finance_cardmember_360 |
| custins | partition_date | dimension | finance_cardmember_360 |
| cmdl | total_card_members | measure | finance_cardmember_360 |
| cmdl | total_replacements | measure | finance_cardmember_360 |
| cmdl | replacement_rate | measure | finance_cardmember_360 |
| cmdl | generation | dimension | finance_cardmember_360 |
| cmdl | card_type | dimension | finance_cardmember_360 |
| cmdl | card_design | dimension | finance_cardmember_360 |
| cmdl | cl_rpt_are | dimension | finance_cardmember_360 |
| cmdl | is_replacement | dimension | finance_cardmember_360 |
| cmdl | birth_year | dimension | finance_cardmember_360 |
| fin | avg_roc_global | measure | finance_merchant_profitability |
| fin | total_merchant_spend | measure | finance_merchant_profitability |
| fin | total_restaurant_spend | measure | finance_merchant_profitability |
| fin | dining_customer_count | measure | finance_merchant_profitability |
| fin | oracle_mer_hier_lvl3 | dimension | finance_merchant_profitability |
| fin | merchant_name | dimension | finance_merchant_profitability |
| fin | is_dining_at_restaurant | dimension | finance_merchant_profitability |
| tlsarpt | total_gross_tls_sales | measure | finance_travel_sales |
| tlsarpt | total_bookings | measure | finance_travel_sales |
| tlsarpt | avg_hotel_cost_per_night | measure | finance_travel_sales |
| tlsarpt | avg_booking_value | measure | finance_travel_sales |
| tlsarpt | total_hotel_nights | measure | finance_travel_sales |
| tlsarpt | travel_vertical | dimension | finance_travel_sales |
| tlsarpt | air_trip_type | dimension | finance_travel_sales |
| risk | revolve_index | measure | finance_customer_risk |
| risk | total_risk_customers | measure | finance_customer_risk |
| risk | revolving_customer_count | measure | finance_customer_risk |
| risk | avg_risk_rank | measure | finance_customer_risk |
| gihr | total_issuances | measure | finance_card_issuance |
| gihr | non_cm_initiated_issuances | measure | finance_card_issuance |
| gihr | cm_initiated_issuances | measure | finance_card_issuance |
| gihr | pct_non_cm_initiated | measure | finance_card_issuance |
| gihr | cmgn_cd | dimension | finance_card_issuance |
| gihr | lis_type | dimension | finance_card_issuance |
| gihr | is_not_cm_initiated | dimension | finance_card_issuance |
| gihr | is_cm_initiated | dimension | finance_card_issuance |
| ace | org_level | dimension | finance_card_issuance |
| ace | org_name | dimension | finance_card_issuance |
| ace | org_type | dimension | finance_card_issuance |
