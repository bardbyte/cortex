# Cortex: Hybrid Retrieval Architecture for Enterprise NL-to-SQL

**Author:** Saheb | **Date:** March 3, 2026 | **Status:** Approved
**Reviewers:** Sulabh, Ashok (Architecture Board)
**ADRs:** [001-ADK over LangGraph](../../cortex/adr/001-adk-over-langgraph.md), [002-Looker Project per BU](../../cortex/adr/002-looker-project-per-bu.md)

---

## 1. Overview

### Problem Statement

American Express analysts across 3 business units need to query a 5+ PB BigQuery warehouse containing 8,000+ datasets. Today, this requires knowing SQL, understanding the physical schema, and knowing which of hundreds of tables and thousands of columns contain the data they need. This creates a bottleneck: only engineers can answer data questions, and response times are measured in days.

The naive solution — give an LLM the schema and ask it to write SQL — fails catastrophically at enterprise scale. The best models achieve 91% accuracy on simple schemas (5 tables) but **collapse to 21-36% on real enterprise schemas** with thousands of columns [1][2]. The failure mode is not SQL syntax — modern LLMs write valid SQL. The failure is **schema linking**: selecting the right tables, columns, and joins from a massive search space.

### Proposed Solution

Cortex is a hybrid retrieval system that translates natural language questions into correct SQL by solving the schema linking problem through three orthogonal retrieval channels (semantic, structural, behavioral), fused via Reciprocal Rank Fusion, and validated against a knowledge graph before SQL generation. Looker's MCP generates all SQL deterministically — no LLM-generated SQL.

### Scope

**In scope:** Hybrid retrieval architecture, fusion logic, structural validation, Looker MCP integration, evaluation methodology.

**Out of scope:** Intent classification (separate design), ChatGPT Enterprise integration (frontend), deployment architecture (separate doc), Conversational Analytics API comparison (separate spike).

---

## 2. Background & Context

### Why Enterprise NL-to-SQL Is an Unsolved Problem

The gap between academic benchmarks and production reality is the defining challenge:

| Benchmark | Schema Complexity | Best Accuracy | Source |
|-----------|------------------|---------------|--------|
| Spider 1.0 | ~5 tables, clean schemas | 91.2% | [1] |
| Spider 2.0 | 1000+ columns, BigQuery/Snowflake | 21-36% | [2] |
| BIRD | Real databases, dirty values | 72.4% | [3] |
| Uber internal | Production warehouse | ~50% table selection | [4] |

The 91% → 36% collapse from Spider 1.0 to Spider 2.0 is entirely attributable to schema complexity. When the model must choose from thousands of columns instead of dozens, it fails. This is not a model capability problem — it is an information retrieval problem.

**Uber's CIDR 2024 paper** [4] is the most honest production assessment. Their internal NL-to-SQL system achieved only **50% overlap with ground-truth tables** — not 50% SQL accuracy, but 50% accuracy on just finding the right tables. Their conclusion: "NL2SQL is a solved problem... not."

### The Schema Linking Decomposition

Every NL-to-SQL error traces to one of three root causes:

```
ERROR TYPE 1: WRONG FIELDS (50-60% of errors)
  User: "total spend"
  System picks: revenue.gross_amount (wrong table, wrong metric)
  Correct: transactions.total_amount

ERROR TYPE 2: INCOMPATIBLE FIELDS (20-30% of errors)
  User: "spend by merchant category"
  System picks: transactions.total_amount + risk_scores.merchant_type
  Problem: These are in different explores with no join path
  Correct: transactions.total_amount + merchants.category_name (same explore)

ERROR TYPE 3: MISSING CONTEXT (10-20% of errors)
  User: "last quarter"
  System generates: WHERE date > '2025-10-01'
  Problem: No partition filter on 5PB table. Query costs $5,000.
  Correct: WHERE partition_date BETWEEN '2025-10-01' AND '2025-12-31'
```

Our retrieval architecture is designed to eliminate each error type with a dedicated mechanism:
- **Vector search** targets Error Type 1 (semantic field matching)
- **Graph validation** targets Error Type 2 (structural compatibility)
- **Few-shot matching** targets Error Types 1 and 3 (proven patterns include correct filters)

### Prior Art and Industry Approaches

| System | Approach | Retrieval Method | Reported Accuracy | Limitation |
|--------|----------|-----------------|-------------------|------------|
| Databricks AI/BI Genie | LLM + Unity Catalog metadata | Table/column description matching | 85-90% with semantic layer | Tied to Databricks ecosystem |
| Snowflake Cortex Analyst | Verified semantic model + LLM | Certified field definitions | "Production-grade" (no public number) | Requires Snowflake semantic model |
| Google Conv. Analytics | Gemini + Looker semantic layer | Internal model understanding | Not published | Single-explore limit, 5K row cap [5] |
| ThoughtSpot Sage | LLM + proprietary search index | Natural language search over TML | ~80% on supported queries | Closed ecosystem |
| Uber QueryGPT | LLM + schema enrichment | Table/column matching | ~50% table accuracy [4] | No structural validation |

**Key insight from prior art:** Every production system that achieves >85% accuracy uses a semantic layer (Databricks Unity Catalog, Snowflake semantic model, Looker LookML). The semantic layer is not optional — it is the primary accuracy mechanism. Raw schema descriptions are insufficient.

**Our advantage:** Looker's LookML is the most mature semantic layer in our stack, and Looker MCP eliminates SQL generation errors entirely. Our engineering effort focuses exclusively on retrieval — the 75-80% of the error budget that others still struggle with.

### Research Foundation

The hybrid retrieval approach is grounded in recent NL-to-SQL research:

- **CHASE-SQL** [6]: Demonstrated that multi-agent decomposition with query-aware schema filtering achieves 73.0% on BIRD, beating single-pass approaches by 5-8%.
- **LinkAlign** [7]: "Using a perfect schema — one that includes only the necessary tables and columns — yields significantly higher accuracy." Schema linking is the bottleneck.
- **Bidirectional schema retrieval** [8]: Approaches that narrow the gap between "full schema" and "perfect schema" settings improve accuracy by ~50%.
- **TailorSQL** [9]: Few-shot examples provide 2x accuracy improvement on enterprise schemas. In-context learning with domain-specific examples is the strongest single intervention.
- **HybridRAG** [10]: Combining vector retrieval with knowledge graphs consistently outperforms either alone, with the graph providing structural grounding that prevents semantic hallucination.

---

## 3. Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CORTEX RETRIEVAL SYSTEM                         │
│                                                                         │
│  User Query: "What was total spend by merchant category last quarter?"  │
│      │                                                                  │
│      ▼                                                                  │
│  ┌──────────────────────────────────────────┐                           │
│  │  ENTITY EXTRACTION                        │                           │
│  │  metrics: ["total spend"]                 │                           │
│  │  dimensions: ["merchant category"]        │                           │
│  │  time_range: "last quarter"               │                           │
│  │                                           │                           │
│  │  Synonym resolution (from taxonomy):      │                           │
│  │  "total spend" → "Total Transaction Amt"  │                           │
│  └──────────────┬───────────────────────────┘                           │
│                 │                                                        │
│                 ▼                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  THREE-CHANNEL PARALLEL RETRIEVAL  (no LLM calls — <300ms)      │   │
│  │                                                                  │   │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │   │
│  │  │  VECTOR SEARCH   │ │  GRAPH SEARCH    │ │  FEW-SHOT MATCH │   │   │
│  │  │  (Vertex AI)     │ │  (Neo4j)         │ │  (FAISS)        │   │   │
│  │  │                  │ │                  │ │                  │   │   │
│  │  │  Semantic match  │ │  Structural      │ │  Pattern match   │   │   │
│  │  │  on enriched     │ │  validation:     │ │  against golden  │   │   │
│  │  │  field           │ │  "Which explores │ │  query corpus    │   │   │
│  │  │  descriptions    │ │  contain BOTH    │ │                  │   │   │
│  │  │                  │ │  a spend measure │ │  Returns:        │   │   │
│  │  │  Returns:        │ │  AND a merchant  │ │  Top-K similar   │   │   │
│  │  │  Top-20 fields   │ │  dimension?"     │ │  past queries    │   │   │
│  │  │  by similarity   │ │                  │ │  with known-good │   │   │
│  │  │                  │ │  Returns:        │ │  field mappings  │   │   │
│  │  │  Addresses:      │ │  Structurally    │ │                  │   │   │
│  │  │  Error Type 1    │ │  valid combos    │ │  Addresses:      │   │   │
│  │  │  (wrong fields)  │ │                  │ │  Error Types 1+3 │   │   │
│  │  │                  │ │  Addresses:      │ │  (wrong fields,  │   │   │
│  │  │                  │ │  Error Type 2    │ │   missing ctx)   │   │   │
│  │  │                  │ │  (incompatible)  │ │                  │   │   │
│  │  └────────┬─────────┘ └───────┬──────────┘ └───────┬──────────┘   │   │
│  │           │                   │                     │              │   │
│  │           └───────────────────┼─────────────────────┘              │   │
│  │                               ▼                                    │   │
│  │           ┌──────────────────────────────────┐                    │   │
│  │           │  RECIPROCAL RANK FUSION (RRF)     │                    │   │
│  │           │                                    │                    │   │
│  │           │  Weighted merge of 3 ranked lists  │                    │   │
│  │           │    graph:   1.5 (structural truth)  │                    │   │
│  │           │    fewshot: 1.2 (proven patterns)   │                    │   │
│  │           │    vector:  1.0 (semantic signal)   │                    │   │
│  │           └──────────────┬───────────────────┘                    │   │
│  │                          ▼                                         │   │
│  │           ┌──────────────────────────────────┐                    │   │
│  │           │  STRUCTURAL VALIDATION GATE       │                    │   │
│  │           │  (Neo4j Cypher)                   │                    │   │
│  │           │                                    │                    │   │
│  │           │  "Are ALL fused fields reachable   │                    │   │
│  │           │   from a SINGLE explore?"          │                    │   │
│  │           │                                    │                    │   │
│  │           │  YES (1 explore)  → proceed        │                    │   │
│  │           │  YES (N explores) → disambiguate   │                    │   │
│  │           │  NO               → clarify        │                    │   │
│  │           └──────────────┬───────────────────┘                    │   │
│  └──────────────────────────┼───────────────────────────────────────┘   │
│                             ▼                                           │
│  ┌──────────────────────────────────────────┐                           │
│  │  OUTPUT: RetrievalResult                  │                           │
│  │  {                                        │                           │
│  │    action: "proceed",                     │                           │
│  │    model: "finance",                      │                           │
│  │    explore: "transactions",               │                           │
│  │    dimensions: ["merchants.category"],    │                           │
│  │    measures: ["transactions.total_amt"],  │                           │
│  │    filters: {partition_date: "Q4 2025"},  │                           │
│  │    confidence: 0.94                       │                           │
│  │  }                                        │                           │
│  └──────────────────────────┬───────────────┘                           │
│                             ▼                                           │
│  ┌──────────────────────────────────────────┐                           │
│  │  LOOKER MCP → DETERMINISTIC SQL           │                           │
│  │  → BigQuery execution → formatted answer  │                           │
│  └──────────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow (Step by Step)

1. **Entity Extraction** — Gemini Flash extracts metrics, dimensions, filters, time ranges from natural language. Taxonomy synonym index resolves business terms to canonical names.
2. **Vector Search** — Extracted entities are embedded via `text-embedding-005` and searched against a Vertex AI Search corpus of per-field documents. Returns top-20 fields ranked by semantic similarity.
3. **Graph Search** — Neo4j Cypher query finds all explores that contain fields matching the extracted entities. Returns structurally valid field combinations grouped by explore.
4. **Few-shot Match** — FAISS similarity search against a corpus of golden query embeddings. Returns top-K historical queries with known-correct field mappings.
5. **RRF Fusion** — Three ranked lists merged using Reciprocal Rank Fusion with configurable weights. Graph results weighted highest (1.5x) because structural validity is non-negotiable.
6. **Structural Validation Gate** — Final Neo4j check: "Can ALL fused fields be reached from a single explore via valid join paths?" This is the quality gate that prevents Error Type 2. If multiple valid explores exist, disambiguation is triggered.
7. **Looker MCP** — Validated {model, explore, dimensions, measures, filters} passed to Looker MCP `query_sql`. SQL generated deterministically from LookML — no LLM SQL generation.

---

## 4. Detailed Design

### 4.1 Vector Search (Vertex AI Search)

**Purpose:** Semantic field matching — bridging the lexical gap between business language and LookML field names.

**Corpus Construction:**

Each LookML dimension and measure becomes one document. Per-field chunking is intentional — per-view chunking returns 50 irrelevant fields alongside the 2 you need, destroying retrieval precision.

```
Document ID: "finance.transactions.total_amount"

Content (embedded):
  "total_amount is a sum measure in the transactions view, accessible
   through the transactions explore in the finance model. It represents
   the total transaction amount in USD. Also known as: total spend,
   spending, purchase amount, transaction value."

Structured Metadata (filterable):
  field_name: "total_amount"
  field_type: "measure"
  measure_type: "sum"
  view: "transactions"
  explore: "transactions"
  model: "finance"
  group_label: "Transaction Amounts"
```

**Why per-field, not per-view:** Research on chunking strategies for structured data [7][8] consistently shows that fine-grained retrieval units improve precision. When the corpus is per-view, a search for "spend" returns the entire transactions view (50 fields). When per-field, it returns `total_amount`, `daily_spend`, and `avg_transaction_amount` — the fields you actually need. At 100K+ fields, this precision difference is the gap between 70% and 90% retrieval accuracy.

**Configuration:**
- Embedding model: `text-embedding-005`
- Top-K: 20 candidates per entity
- Latency target: <100ms P95
- Corpus refresh: triggered on LookML deploy

### 4.2 Graph Search (Neo4j)

**Purpose:** Structural validation — the knowledge graph encodes LookML's model/explore/view/join structure, enabling queries that vector search fundamentally cannot answer.

**Graph Schema:**

```
(:Model)-[:CONTAINS]->(:Explore)-[:BASE_VIEW]->(:View)
(:Explore)-[:JOINS {sql_on, relationship}]->(:View)
(:View)-[:HAS_DIMENSION]->(:Dimension {name, type, description})
(:View)-[:HAS_MEASURE]->(:Measure {name, type, description})
(:Explore)-[:ALWAYS_FILTER_ON]->(:Dimension)
(:BusinessTerm)-[:MAPS_TO]->(:Dimension|:Measure)
```

**Five Core Queries:**

| Query | Input | Output | Error Type Addressed |
|-------|-------|--------|---------------------|
| `validate_fields_in_explore` | List of field names | Explores containing ALL fields | Type 2 (incompatible fields) |
| `get_explore_schema` | Explore name | All reachable fields | Type 1 (wrong fields) |
| `resolve_business_term` | Business term | LookML field(s) | Type 1 (synonym resolution) |
| `get_partition_filters` | Explore name | Required `always_filter` dimensions | Type 3 (missing filters) |
| `find_join_path` | Two views | Join path with relationship type | Type 2 (join validation) |

**Why Neo4j, not a relational DB:** LookML's structure is inherently a graph — models contain explores, explores join views, views contain fields, fields have relationships. Graph traversal queries (e.g., "find all fields reachable from explore X through views joined with Y") are O(1) in graph databases and O(n^2) in relational. At 100+ models with complex join paths, this matters.

### 4.3 Few-Shot Match (FAISS)

**Purpose:** Pattern matching against known-correct query-to-field mappings. Exploits the power-law distribution of enterprise queries: 80% of questions are variations of 20% of patterns.

**Corpus:**

```json
{
  "id": "GQ-fin-042",
  "natural_language": "What was total spend by merchant category last quarter?",
  "embedding": [0.12, -0.34, ...],
  "model": "finance",
  "explore": "transactions",
  "dimensions": ["merchants.category_name"],
  "measures": ["transactions.total_amount"],
  "filters": {"transactions.partition_date": "last quarter"}
}
```

**Why this channel exists:**

Research quantifies the impact:
- **TailorSQL** [9] demonstrates 2x accuracy improvement from few-shot examples on enterprise schemas
- **Query Capsules** [11] show 4.58-5.79% execution accuracy lift on Spider/BIRD benchmarks
- **In-context learning** [12] with domain-specific examples is the strongest single intervention for complex schemas

**Flywheel effect:** Every validated query (user thumbs-up or analyst correction) becomes a new golden query. The system improves with use. At month 1, the corpus has ~50 queries (launch set). At month 6, it has ~500 (from analyst usage). At month 12, it has ~2,000+ with coverage of most common question patterns. This is the data moat — unique to Amex, impossible for a general-purpose system to replicate.

**Configuration:**
- Embedding: `text-embedding-005` (same as vector search for consistency)
- Index: FAISS IVF with 256 centroids
- Top-K: 5 similar queries
- Similarity threshold: cosine > 0.85

### 4.4 Reciprocal Rank Fusion

**Purpose:** Merge three ranked lists into one, weighted by channel reliability.

**Algorithm:**

```python
def reciprocal_rank_fusion(ranked_lists, weights, k=60):
    """
    RRF score for field f = sum over channels c:
      weight_c / (k + rank_c(f))
    """
    scores = defaultdict(float)
    for channel, ranked_list in ranked_lists.items():
        w = weights[channel]
        for rank, field in enumerate(ranked_list):
            scores[field.key] += w / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])
```

**Weight rationale:**

| Channel | Weight | Rationale |
|---------|--------|-----------|
| Graph | 1.5 | Structural truth is non-negotiable. If the graph says fields are incompatible, they are. |
| Few-shot | 1.2 | Proven patterns with verified correctness. Higher signal, lower noise. |
| Vector | 1.0 | Broad recall but no structural understanding. Highest recall, lowest precision. |

**Why RRF over learned fusion:** RRF requires no training data — critical at launch when we have no query logs. It is also interpretable: we can explain exactly why a field was selected. Learned fusion (e.g., a trained reranker) is a future optimization once we have sufficient golden query volume.

**Why RRF over simple weighted average:** RRF is rank-based, not score-based. This matters because scores from different retrieval systems are not comparable (cosine similarity from vector search vs. graph match count vs. FAISS distance). RRF normalizes by rank position, making cross-channel fusion mathematically sound [13].

### 4.5 Structural Validation Gate

**Purpose:** Final quality gate before SQL generation. The single most important component in the system.

```cypher
// Given candidate fields from RRF, find explores containing ALL of them
MATCH (e:Explore)-[:BASE_VIEW|JOINS*0..3]->(v:View)
WHERE ALL(field IN $candidate_fields
  WHERE (v)-[:HAS_DIMENSION|HAS_MEASURE]->({name: field}))
RETURN e.name, collect(DISTINCT v.name) AS views
```

**Decision logic:**

| Condition | Action | User Experience |
|-----------|--------|----------------|
| 1 explore matches | `proceed` | Generate SQL |
| N explores match | `disambiguate` | "Did you mean revenue from Finance or Marketing?" |
| 0 explores match | `clarify` | "I can find spend and merchant separately. Could you clarify which data source?" |
| Fields span models | `decompose` | Break into sub-queries per model |

**Why this gate is non-negotiable:**

Without structural validation, the system can produce queries that are syntactically valid but semantically wrong. Example: "spend by risk score" could match `transactions.total_amount` (finance model) and `scores.risk_rating` (risk model) — both are semantically relevant but cannot be joined. The structural validation gate catches this in <10ms via graph traversal.

---

## 5. Evaluation & Success Criteria

### Accuracy Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Field Precision** | Correct fields / selected fields | >90% |
| **Field Recall** | Correct fields / expected fields | >85% |
| **Explore Accuracy** | Correct explore selected | >95% |
| **End-to-End Accuracy** | Query returns correct answer | >90% |
| **Structural Validity** | All selected fields in same explore | 100% |

### Latency Targets

| Stage | P50 | P95 | Notes |
|-------|-----|-----|-------|
| Entity extraction | 200ms | 500ms | Gemini Flash |
| Vector search | 30ms | 100ms | Vertex AI Search |
| Graph search | 10ms | 50ms | Neo4j local |
| Few-shot match | 5ms | 20ms | FAISS in-memory |
| RRF fusion | 1ms | 5ms | CPU-only computation |
| Structural validation | 10ms | 30ms | Neo4j Cypher |
| **Total retrieval** | **~60ms** | **<300ms** | **No LLM in loop** |
| Looker MCP (SQL gen) | 500ms | 1s | Network call |
| BigQuery execution | 1s | 5s | Depends on data volume |
| **Total pipeline** | **~2s** | **<8s** | |

### Evaluation Methodology

**Golden dataset:** 50 queries per BU (150 total at full scale), stratified by complexity:
- Simple (40%): single metric, one dimension, one filter
- Moderate (40%): multiple dimensions, time ranges, aggregation
- Complex (20%): cross-domain, ambiguous terms, multi-hop

**Evaluation loop:**
```bash
python scripts/run_eval.py --dataset=tests/golden_queries/finance/
```

Reports: field precision/recall, explore accuracy, end-to-end accuracy, per-complexity breakdown, failure analysis.

---

## 6. Failure Modes & Mitigations

| Failure Mode | Impact | Detection | Mitigation |
|-------------|--------|-----------|------------|
| Vector search returns irrelevant fields | Low accuracy | Field precision drops in golden eval | Improve field descriptions, add taxonomy synonyms |
| Neo4j is unreachable | No structural validation | Health check, circuit breaker | Fall back to vector-only with confidence penalty |
| FAISS corpus is empty (cold start) | No few-shot signal | Corpus size check at startup | System still works on vector + graph; few-shot is additive |
| Multiple explores score equally | User sees disambiguation | Disambiguation rate metric | Improve taxonomy to resolve ambiguity earlier |
| No explore matches | User gets clarification request | Clarification rate metric | Investigate gap in graph coverage or taxonomy |
| Partition filter missing | Expensive BigQuery query ($$$) | Pre-execution dry-run | Graph stores `ALWAYS_FILTER_ON` edges; block queries without them |
| Stale graph (LookML changed) | Wrong structural validation | Compare graph timestamp vs LookML deploy | Trigger graph reload on LookML deploy |

### Cost Control

On a 5+ PB warehouse, an unfiltered query can scan terabytes. Cost control is not optional.

1. **Partition filter enforcement:** Graph stores `ALWAYS_FILTER_ON` edges. Every query is checked.
2. **BigQuery dry-run:** Before execution, `jobs.insert` with `dryRun=true` estimates bytes scanned.
3. **Budget gate:** If estimated cost exceeds per-query budget (configurable), query is blocked with explanation.
4. **Audit trail:** Every query logs: user, question, selected fields, SQL, bytes scanned, cost.

---

## 7. Rollout Plan

### Phase 1: Prove the Loop (Weeks 1-3)
- Deploy Looker MCP on GKE
- Load Finance BU LookML into Neo4j
- Index Finance BU fields into Vertex AI Search
- Wire up ADK pipeline skeleton
- **Exit criteria:** ONE query works end-to-end

### Phase 2: Reliable Retrieval (Weeks 3-6)
- Build golden dataset (50 queries, Finance BU)
- Implement structural validation gate
- Implement RRF fusion with all 3 channels
- Map business terms to taxonomy (30+ entries)
- **Exit criteria:** >85% retrieval accuracy on golden dataset

### Phase 3: Handle the Edges (Weeks 6-10)
- Disambiguation flow for ambiguous queries
- Boundary detection and graceful refusal
- Complexity-aware routing (simple queries skip retrieval)
- 3-layer caching (exact, semantic, metadata)
- **Exit criteria:** >90% end-to-end accuracy

### Phase 4: Production Ready (Weeks 10-14)
- Expand to 3 BUs
- Feedback loop (user corrections → taxonomy + golden dataset)
- Observability dashboards (latency, accuracy, cost)
- Cost control gates verified at scale
- **Exit criteria:** May 2026 production launch

### Rollback Strategy

Each channel is independently deployable and the fusion layer handles missing channels gracefully:
- **Kill few-shot:** Set weight to 0 in `config/retrieval.yaml`. System continues on vector + graph.
- **Kill vector search:** System degrades to graph-only (lower recall, same precision).
- **Kill graph validation:** This should never be killed — it is the safety gate. If Neo4j is down, the circuit breaker blocks queries rather than allowing unvalidated SQL.

---

## 8. Open Questions

| # | Question | Owner | Status |
|---|----------|-------|--------|
| 1 | Conversational Analytics API GA timeline and pricing | Google (support call) | Pending |
| 2 | Looker MCP roadmap: cross-explore support, filter enforcement | Google (support call) | Pending |
| 3 | Custom terminology support in Conversational Analytics | Google (support call) | Pending |
| 4 | AI firewall exception for SafeChain/Cortex LLM traffic | Abhishek → InfoSec | Blocker |
| 5 | Embedding fine-tuning with Amex query-field pairs | Google (support call) | Pending |
| 6 | Production support SLA for Looker MCP | Google (support call) | Pending |

---

## 9. Appendix

### A. Competitive Position: Cortex vs Conversational Analytics

| Capability | Conversational Analytics (GA Nov 2025) | Cortex |
|------------|---------------------------------------|--------|
| NL-to-SQL via Looker | Yes | Yes (via Looker MCP) |
| Cross-explore queries | No (single explore per query) [5] | Yes (graph-validated) |
| Custom business terminology | No | Yes (taxonomy + synonym resolution) |
| Partition filter enforcement | Not documented | Yes (graph-enforced) |
| Cost control / dry-run | Not documented | Yes (pre-execution gate) |
| ChatGPT Enterprise frontend | No (Looker UI only) | Yes |
| SafeChain / CIBIS compliance | No | Yes (mandatory at Amex) |
| Accuracy on complex queries | Unknown (no public benchmarks) | Targeting >90% |
| Pricing | Free until Sept 2026, then TBD | Internal infrastructure cost |

**Strategic position:** Cortex is the enterprise control layer. When Conversational Analytics improves, it becomes another tool Cortex can call — not a replacement.

### B. Glossary

| Term | Definition |
|------|-----------|
| **Explore** | Looker concept: a queryable view of data defined in LookML, with specific dimensions, measures, and join relationships |
| **LookML** | Looker's modeling language, defining the semantic layer: what data means, how it joins, how it aggregates |
| **MCP** | Model Context Protocol — standard for AI tool integration. Looker MCP exposes 33 tools for programmatic Looker access |
| **RRF** | Reciprocal Rank Fusion — algorithm for merging multiple ranked lists without requiring comparable scores |
| **SafeChain** | Amex internal LLM gateway. All AI model calls must route through SafeChain for CIBIS authentication |
| **Structural validation** | Verification that all selected fields can be queried together within a single Looker explore |

### C. References

[1] Yu, T. et al. "Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task." EMNLP 2018. https://yale-lily.github.io/spider

[2] Lei, F. et al. "Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows." ICLR 2025 (Oral). https://spider2-sql.github.io/ — Best model accuracy: 21-36% on enterprise schemas.

[3] Li, J. et al. "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs." NeurIPS 2024. https://bird-bench.github.io/

[4] Floratou, A. et al. "NL2SQL is a Solved Problem... Not!" CIDR 2024. https://www.cidrdb.org/cidr2024/papers/p74-floratou.pdf — Uber's internal system: 50% table selection accuracy.

[5] Google Cloud. "Conversational Analytics API Known Limitations." https://docs.cloud.google.com/gemini/docs/conversational-analytics-api/known-limitations

[6] Pourreza, M. & Rafiei, D. "CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection in Text-to-SQL." 2024. 73.0% on BIRD benchmark.

[7] Li, X. et al. "LinkAlign: Scalable Schema Linking for Real-World Large-Scale Multi-Database Text-to-SQL." EMNLP 2025. https://aclanthology.org/2025.emnlp-main.51/

[8] Chen, Y. et al. "Rethinking Schema Linking in Text-to-SQL: A Bidirectional Retrieval Approach." 2025. https://arxiv.org/abs/2510.14296

[9] Wang, Z. et al. "TailorSQL: A Tailored Framework for Enterprise Text-to-SQL." SIGMOD 2025. 2x accuracy from few-shot examples.

[10] "HybridRAG: Integrating Knowledge Graphs and Vector Retrieval." https://memgraph.com/blog/why-hybridrag — Graph+vector consistently outperforms either alone.

[11] "Retrieval-Augmented NL2SQL with Query Capsules." ACM 2025. 4.58-5.79% execution accuracy improvement.

[12] Brown, T. et al. "Language Models are Few-Shot Learners." NeurIPS 2020. Foundation for in-context learning approaches.

[13] Cormack, G. et al. "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods." SIGIR 2009. https://dl.acm.org/doi/10.1145/1571941.1572114

[14] Google Cloud. "Connecting Looker to Gemini with MCP Toolbox and ADK." December 2025. https://cloud.google.com/blog/products/business-intelligence/connecting-looker-to-gemini-enterprise-with-mcp-toolbox-and-adk

[15] Tunguz, T. "Why AI Can't Crack Your Database." 2025. https://tomtunguz.com/spider-2-benchmark-trends/
