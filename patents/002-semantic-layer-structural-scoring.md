# Patent Disclosure: Semantic Layer Structural Scoring for Natural Language to Database Schema Routing

**Disclosure ID:** CORTEX-PAT-002
**Date:** March 16, 2026
**Inventor(s):** Saheb (primary), Likhita (contributor — intent classification integration), Abhishek (contributor)
**Status:** Draft — For review with Lakshmi before formal filing
**Internal Reference:** ADR-009, Patent Landscape Analysis (Patent #1, #5, #8)

---

## 1. Title

**Multiplicative Structural Scoring Method for Routing Natural Language Queries to Database Schemas Using Semantic Layer Ownership Declarations**

---

## 2. Technical Field

This disclosure relates to natural language interfaces for databases, specifically to systems and methods for selecting the correct database schema (explore, view, or table set) from among multiple candidates when translating a natural language query into a structured database query. More particularly, this disclosure addresses the use of structural metadata from a semantic modeling layer — specifically base view ownership declarations — as a scoring signal in a multiplicative formula that combines vector similarity search with schema-structural evidence to route queries to the correct analytical context.

---

## 3. Background / Problem Statement

### 3.1 The Schema Routing Problem

Enterprise analytical platforms organize data into multiple overlapping schemas (referred to herein as "explores," "views," "datasets," or "analytical contexts"). A single database field — for example, a measure representing total revenue — may be reachable from several schemas through different join paths. When a user issues a natural language query such as "show me total revenue by product category," the system must determine which schema to query. This is the **schema routing problem**.

The schema routing problem is distinct from, and upstream of, the SQL generation problem. If the system selects the wrong schema, even a perfectly generated SQL query will return incorrect results. Schema routing errors are **silent failures** — the query executes successfully, returns plausible-looking data, but from the wrong analytical context.

### 3.2 Why Schema Routing Is Hard in Enterprise Environments

In enterprise data warehouses with 5+ petabytes and thousands of tables, the schema routing problem has specific characteristics that distinguish it from academic NL2SQL benchmarks:

1. **Field reachability through joins.** A field like `total_billed_business` may reside in table `custins` but be reachable from 4 of 5 schemas through SQL JOIN operations. Simple field-name matching produces 4 candidates instead of 1.

2. **Semantic overlap.** Multiple schemas may contain semantically similar fields (e.g., `total_billed_business` in a customer schema and `total_merchant_spend` in a merchant schema) that are plausible matches for the same natural language term.

3. **Scale of ambiguity.** At enterprise scale (hundreds of schemas, thousands of fields), the probability of ambiguous routing increases combinatorially. With N schemas and M shared fields, the number of ambiguous routing situations grows as O(N × M).

4. **Silent failure cost.** In financial services, a query routed to the wrong schema may produce numbers that differ by orders of magnitude from the correct answer. At the scale of a Fortune 50 financial institution, a single incorrect query result presented to leadership can drive incorrect business decisions.

### 3.3 Semantic Modeling Layers and Structural Metadata

Modern data platforms use **semantic modeling layers** (e.g., Looker LookML, dbt semantic layer, AtScale) that sit between the raw database and the analytical consumer. These layers define:

- **Explores** (or "datasets"): Named analytical contexts that define which tables to query together
- **Views**: Abstracted representations of database tables with business-friendly field names
- **Base view declarations**: A critical structural property (`from:` in LookML) that specifies which view is the **primary data source** for an explore — the table the explore was **designed** to analyze
- **Join declarations**: Which views are secondarily connected to the explore for enrichment
- **Field definitions**: Measures (aggregations) and dimensions (grouping/filtering attributes)
- **Descriptions**: Natural language documentation of each explore's analytical purpose

The base view declaration (`from:`) is the key structural signal exploited by this invention. It encodes the **semantic modeler's intent**: the explore `finance_cardmember_360` was designed to analyze customer insights (base view = `custins_customer_insights_cardmember`), not merchant profitability, even though merchant data is reachable through joins. This intent signal is invisible to systems that treat all reachable fields as equivalent.

### 3.4 Existing Approaches and Their Limitations

| Approach | Representative System | Scoring Method | Limitation |
|----------|----------------------|----------------|------------|
| LLM-only reasoning | Looker Explore Assistant, Google Duet AI | No explicit scoring — LLM selects schema via in-context reasoning | Non-deterministic; degrades with schema count; cannot explain selection rationale; prone to hallucination on ambiguous queries |
| Column name matching | ThoughtSpot Search | Additive token-based scoring: `score = sum(token_matches)` | Weak signals compensate for zero signals; an explore with 0% coverage but many token matches can outscore a full-coverage explore |
| Vector similarity only | RESDSQL (Li et al., AAAI 2023), DIN-SQL (Pourreza & Rafiei, 2023) | Cross-encoder classification probability or cosine similarity ranking | No structural metadata; treats all schema elements as semantically equivalent regardless of ownership; cannot distinguish base-view fields from joined fields |
| Schema graph routing | DBCopilot (EDBT 2025) | Differentiable search index on schema graph | Trained routing model; no semantic layer ownership signals; requires training data; no multiplicative penalty for partial coverage |
| Schema filtering + generation | CHESS (Talaei et al., 2024) | LLM-based schema pruning with adaptive complexity | No semantic layer signals; LLM-dependent selection; no structural ownership concept; no deterministic scoring formula |
| NL2SQL with schema metadata | US11,636,115 (Salesforce, 2023) | Schema metadata used for column matching | No semantic layer base-view ownership; no multiplicative composition; no coverage exponent |
| BI query understanding | US11,341,145 (Google, 2022) | Column-level matching for BI tool queries | No explore-level routing; no base-view ownership; no multiplicative formula |
| Schema disambiguation | Odin (EMNLP 2025) | LLM logit probability scoring of candidate SQL queries | Operates post-SQL-generation; does not use semantic layer structural signals; requires generating multiple full SQL queries before scoring |

**Critical gap in all existing approaches:** No existing system uses the semantic modeling layer's **base view ownership declaration** (`from:` in LookML, or equivalent in dbt/AtScale) as a scoring signal for schema routing. All existing approaches treat fields reachable through joins as equivalent to fields from the primary data source.

---

## 4. Summary of the Invention

A computer-implemented method and system for routing natural language queries to the correct database schema in a multi-schema environment, comprising:

1. **Entity extraction** from the natural language query, identifying measures (aggregation targets), dimensions (grouping/filtering attributes), and filters (constraint predicates), each classified by type

2. **Vector similarity search** to find candidate database fields matching each extracted entity, using embedding-based cosine similarity over field descriptions in a semantic field index

3. **Schema candidate enumeration** by grouping matched fields by the schemas (explores) that contain them, including fields reachable through join relationships

4. **Multiplicative structural scoring** of each candidate schema using a five-signal formula:

   ```
   score = coverage³ × mean_similarity × base_view_bonus × desc_sim_bonus × filter_penalty
   ```

   Where:
   - `coverage³` is the fraction of user-requested entities that the schema can serve, raised to the third power, creating a steep non-linear penalty for incomplete coverage
   - `mean_similarity` is the arithmetic mean of the best cosine similarity score for each matched entity
   - `base_view_bonus` is a multiplier (1.0 to 2.0) computed from the fraction of matched fields that originate from the schema's declared base view (primary data source), with measures weighted 2× relative to dimensions and a similarity floor to prevent low-quality matches from receiving the structural bonus
   - `desc_sim_bonus` is a tiebreaker multiplier (1.0 to ~1.2) based on the cosine similarity between the user's query embedding and the schema's natural language description embedding
   - `filter_penalty` is a multiplier (0.1 to 1.0) based on the fraction of user-specified filter dimensions that exist in the candidate schema's field index

5. **Multiplicative composition** ensuring that any single zero-value signal eliminates the candidate schema entirely (jointly necessary conditions, not independently sufficient)

6. **Relative confidence normalization** producing a scale-invariant confidence score

7. **Near-miss detection** using a ratio-based threshold on the top two candidates to identify genuinely ambiguous queries

---

## 5. Detailed Description

### 5.1 System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  STAGE 1: ENTITY EXTRACTION                                         │
│                                                                      │
│  Input:  "What is the total billed business by merchant category?"  │
│  Output: E1: measure "total billed business"                        │
│          E2: dimension "merchant category"                           │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  STAGE 2: VECTOR SIMILARITY SEARCH (per entity, type-filtered)      │
│                                                                      │
│  E1 → [{field: total_billed_business, view: custins, sim: 0.88},   │
│         {field: total_merchant_spend, view: fin_merchant, sim: 0.78}]│
│  E2 → [{field: oracle_mer_hier_lvl3, view: fin_merchant, sim: 0.77}]│
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  STAGE 3: SCHEMA CANDIDATE ENUMERATION                              │
│                                                                      │
│  finance_cardmember_360:         {E1: 0.88 from custins}            │
│  finance_merchant_profitability: {E1: 0.78, E2: 0.77 from merchant} │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  STAGE 4: MULTIPLICATIVE STRUCTURAL SCORING  *** THIS INVENTION *** │
│                                                                      │
│  score = coverage³ × mean_sim × base_view_bonus                     │
│          × desc_sim_bonus × filter_penalty                           │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  STAGE 5: ACTION DETERMINATION                                      │
│                                                                      │
│  proceed | disambiguate | clarify | no_match                        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 The Scoring Formula

The core invention is the multiplicative structural scoring formula:

```
score = coverage³ × mean_similarity × base_view_bonus × desc_sim_bonus × filter_penalty
```

Each of the five signals captures a different category of evidence for schema fitness. The signals are **multiplicatively composed**, meaning that a zero value on any single signal eliminates the candidate entirely. This distinguishes the invention from additive scoring approaches where a high score on one dimension can compensate for a zero on another.

### 5.3 Signal 1: Coverage Cubed (coverage³)

**Definition:**

```
coverage = matched_entities / total_entities
coverage_score = coverage³
```

**The cubic exponent** creates a steep non-linear penalty for incomplete coverage:

| Coverage | Linear | Cubic | Penalty |
|----------|--------|-------|---------|
| 1.00 | 1.000 | 1.000 | None |
| 0.80 | 0.800 | 0.512 | 49% |
| 0.67 | 0.670 | 0.300 | 70% |
| 0.50 | 0.500 | 0.125 | 88% |
| 0.00 | 0.000 | 0.000 | 100% |

**Rationale for cubic:** A linear coverage score creates insufficient separation. In a 2-entity query where one explore covers both (1.0) and another covers one (0.5), linear gives 2× separation — easily overwhelmed by slightly higher similarity. Cubic gives 8× separation (1.0 vs. 0.125), ensuring the full-match explore dominates.

**Why 3 and not 2 or 4:** With exponent 2, missing 1 of 3 entities yields 0.44 — still competitive. With exponent 4, the penalty is so severe that a single low-similarity entity match can flip the ranking. Exponent 3 produces the steepest cliff that still allows high-quality partial matches to score non-trivially.

### 5.4 Signal 2: Mean Similarity (mean_similarity)

```
mean_similarity = (1/N) × Σ(max_similarity_per_entity)
```

For each entity that the explore can serve, take the highest cosine similarity score among all candidate fields for that entity. Compute the arithmetic mean across all served entities.

### 5.5 Signal 3: Base View Bonus — The Core Novel Signal

**Definition:**

```
base_view_bonus = 1.0 + weighted_base_view_ratio

weighted_base_view_ratio = Σ(wᵢ × is_base_viewᵢ) / Σ(wᵢ)

wᵢ = 2.0 if entityᵢ is a measure, 1.0 if entityᵢ is a dimension
is_base_viewᵢ = 1 if entityᵢ's best match comes from the explore's
                    declared base view AND similarityᵢ ≥ 0.65
                0 otherwise
```

**Range:** 1.0 (no entities from base view) to 2.0 (all entities from base view).

**How it works:** Every explore in a semantic modeling layer has a **base view declaration** — the `from:` property in LookML. This specifies the explore's primary data source.

```lookml
explore: finance_cardmember_360 {
  from: custins_customer_insights_cardmember    # ← base view
  join: cmdl_card_main { ... }                  # ← joined (secondary)
  join: risk_indv_cust { ... }                  # ← joined (secondary)
}
```

The field `total_billed_business` resides in `custins`. It is reachable from 4 explores through joins:

```
                        ┌── finance_cardmember_360        (BASE view = custins) ✓
                        │
total_billed_business ──┼── finance_merchant_profitability (JOIN to custins)
(lives in custins)      ├── finance_travel_sales           (JOIN to custins)
                        └── finance_customer_risk           (JOIN to custins)
```

Only one was **designed** for it. The base view bonus encodes this structural difference.

**Measure weighting (2×):** Measures receive double the weight because the measure determines the analytical grain. A user asking for "total billed business" wants the explore designed for billed business analysis, even if the dimension comes from a universally joined table.

**Similarity floor (0.65):** Prevents low-quality vector matches from being amplified by the structural bonus. Calibrated on observed distributions: genuine matches cluster above 0.65; noise below 0.60.

**Why this is novel:** No existing NL2SQL system uses the semantic modeling layer's base view ownership declaration as a scoring signal. All existing approaches treat fields reachable through joins as equivalent to fields from the primary data source.

### 5.6 Signal 4: Description Similarity Bonus (desc_sim_bonus)

```
desc_sim_bonus = 1.0 + 0.2 × max(cosine_sim(query_embedding, explore_desc_embedding), 0.0)
```

**Range:** 1.0 to ~1.2. This is a **tiebreaker**, not a primary signal. The 0.2 coefficient is intentionally small.

### 5.7 Signal 5: Filter Penalty (filter_penalty)

```
filter_penalty = max(matched_filter_hints / total_filter_hints, 0.1)
```

**Range:** 0.1 to 1.0. Floor of 0.1 prevents hallucinated filter hints from zeroing all scores.

### 5.8 Multiplicative Composition: Mathematical Properties

**Property 1 — Zero Annihilation:** If any signal is zero, score is zero. Enforces jointly necessary conditions.

**Property 2 — Monotonic in each factor:** Improving any single signal strictly improves the score. No perverse incentives.

**Property 3 — Resistance to compensatory trading:** Unlike additive composition (a + b + c), multiplicative prevents a high value on one signal from compensating for a low value on another. An explore with similarity = 0.95 and coverage = 0.1 scores additively as 1.05 but multiplicatively as 0.95 × 0.001 = 0.00095.

### 5.9 Worked Example: Base View Bonus Resolves Ambiguity

**Query:** *"Total billed business by generation"*

Both `finance_cardmember_360` (base = custins) and `finance_merchant_profitability` (base = fin_merchant) can serve this query. "Generation" comes from `cmdl_card_main`, joined to all explores.

```
=== finance_cardmember_360 (base_view = custins) ===
coverage³ = (2/2)³ = 1.000
mean_sim  = (0.88 + 0.82) / 2 = 0.850
base_view: E1 from custins = base → match (weight 2.0)
           E2 from cmdl ≠ base → no match (weight 1.0)
           ratio = 2.0/3.0 = 0.667
           bonus = 1.0 + 0.667 = 1.667
desc_sim_bonus = 1.160
filter_penalty = 1.0
SCORE = 1.000 × 0.850 × 1.667 × 1.160 × 1.0 = 1.643

=== finance_merchant_profitability (base_view = fin_merchant) ===
coverage³ = (2/2)³ = 1.000
mean_sim  = (0.75 + 0.82) / 2 = 0.785
base_view: E1 from fin_merchant = base → match (weight 2.0)
           E2 from cmdl ≠ base → no match (weight 1.0)
           ratio = 2.0/3.0 = 0.667
           bonus = 1.0 + 0.667 = 1.667
desc_sim_bonus = 1.124
filter_penalty = 1.0
SCORE = 1.000 × 0.785 × 1.667 × 1.124 × 1.0 = 1.471

Near-miss ratio = 1.471 / 1.643 = 0.895 > 0.85 → NEAR MISS
Action = disambiguate (correctly identifies genuine ambiguity)
```

### 5.10 Comparative Results: Multiplicative vs. Additive

| Metric | Additive (baseline) | Multiplicative (invention) |
|--------|--------------------|-----------------------------|
| Routing accuracy | ~33% (4/12) | 83% (10/12) |
| Wrong explore wins via compensation | 5/12 | 0/12 |
| Partial-match outscores full-match | 3/12 | 0/12 |
| Ambiguous cases correctly identified | 0/12 | 2/12 |

### 5.11 Scalability Analysis

| Scale | Explores | Operations | Latency |
|-------|----------|------------|---------|
| Current (1 BU) | 5 | 10-20 | <1ms |
| May 2026 (3 BUs) | 15 | 30-60 | <1ms |
| 2027 target (10 BUs) | 50 | 100-200 | <1ms |
| Max (100 BUs) | 500 | 1,000-2,000 | <2ms |

---

## 6. Claims (Draft — For Patent Attorney Review)

### Independent Claims

**Claim 1:** A computer-implemented method for routing a natural language query to a database schema in a multi-schema database environment, the method comprising:
- (a) receiving a natural language query and extracting one or more semantic entities therefrom, each entity classified by type as a measure, dimension, or filter;
- (b) for each extracted entity, performing a vector similarity search against a semantic field index to identify candidate database fields, each candidate associated with a schema, a view, and a cosine similarity score;
- (c) grouping the candidate fields by schema and computing, for each candidate schema, a routing score using a multiplicative formula comprising at least:
  - (i) a **coverage signal** representing the fraction of extracted entities that the candidate schema can serve, raised to a power greater than one to create a non-linear penalty for incomplete coverage;
  - (ii) a **similarity signal** representing the mean cosine similarity of the best-matching field for each served entity; and
  - (iii) a **structural ownership signal** derived from a base view declaration in a semantic modeling layer, the structural ownership signal being greater when matched fields originate from the schema's declared base view than when they originate from secondarily joined views;
- (d) selecting the candidate schema with the highest routing score as the target schema for the natural language query.

**Claim 2:** The method of Claim 1, wherein the structural ownership signal is computed as:
```
base_view_bonus = 1.0 + weighted_base_view_ratio
```
where `weighted_base_view_ratio` is the ratio of weighted base-view matches to total weighted entities, with measures receiving a weight of 2.0 and dimensions receiving a weight of 1.0, and wherein a base-view match is only counted when the entity's cosine similarity exceeds a predetermined similarity floor.

**Claim 3:** The method of Claim 1, wherein the multiplicative formula further comprises:
- (iv) a **description similarity signal** computed as the cosine similarity between the natural language query's embedding and the candidate schema's natural language description embedding; and
- (v) a **filter penalty signal** based on the fraction of user-specified filter dimensions that exist in the candidate schema's field index, with a floor value to prevent complete elimination when filter extraction produces erroneous references.

**Claim 4:** The method of Claim 1, further comprising:
- (e) computing a near-miss ratio as the score of the second-highest-scoring schema divided by the score of the highest-scoring schema;
- (f) when the near-miss ratio exceeds a predetermined threshold, classifying the routing as ambiguous and triggering a disambiguation workflow rather than proceeding with the highest-scoring schema.

### Dependent Claims

**Claim 5:** The method of Claim 1, wherein the coverage signal uses a cubic exponent (power = 3).

**Claim 6:** The method of Claim 2, wherein the similarity floor for base-view matching is set to 0.65.

**Claim 7:** The method of Claim 1, wherein the multiplicative composition enforces jointly necessary conditions such that a zero value on any single signal eliminates the candidate schema regardless of the values of other signals.

**Claim 8:** The method of Claim 1, further comprising computing a scale-invariant confidence score by dividing each candidate schema's routing score by the maximum observed routing score across all candidates, with a quality floor to prevent degenerate normalization.

**Claim 9:** The method of Claim 1, wherein the semantic modeling layer is LookML and the base view declaration is the `from:` property, or dbt semantic layer, or any semantic layer system that declares a primary data source for an analytical context.

**Claim 10:** A system for routing natural language queries to database schemas, the system comprising a processor, memory storing instructions to perform the method of Claim 1, a semantic field index, a schema metadata store, and a relational field index.

---

## 7. Prior Art Analysis

### Known Prior Art

| Reference | Overlap | Distinguishing Element |
|-----------|---------|----------------------|
| US11,636,115 (Salesforce, 2023) | Uses schema metadata for NL-to-SQL | No semantic layer base-view ownership; no multiplicative composition; no coverage exponent |
| US11,341,145 (Google, 2022) | Column-level matching for BI queries | No explore-level routing; no base-view ownership |
| US20230100194 (C3.ai, 2023) | Entity extraction with schema mapping | No LookML signals; no multiplicative formula |
| ThoughtSpot Search | Token-based scoring | Additive; no structural ownership; no coverage exponent |
| DBCopilot (EDBT 2025) | Schema routing via differentiable search index | Trained neural model, not structural ownership signals; requires training data |
| RESDSQL (AAAI 2023) | Cross-encoder schema linking | No semantic layer; no base-view ownership |
| CHESS (Talaei et al., 2024) | LLM-based schema pruning | No deterministic formula; no structural ownership |
| Odin (EMNLP 2025) | LLM logit scoring for schema ambiguity | Post-SQL-generation; no semantic layer signals |
| BM25 (Robertson et al., 1994) | Multiplicative term-document scoring | Application domain entirely different; no structural metadata from semantic layers |

### Novel Elements Not Found in Any Prior Art

1. **Base view ownership as a scoring signal** from the semantic modeling layer's `from:` declaration
2. **Weighted base-view ratio with measure dominance** (2× weight for measures)
3. **Similarity-gated structural bonus** (0.65 floor prevents amplification of noise)
4. **Coverage cubed in multiplicative composition** for schema routing
5. **Five-signal multiplicative formula** combining coverage, similarity, structural ownership, description, and filter signals
6. **Ratio-based near-miss detection** for schema routing disambiguation

---

## 8. Potential Publication

**Title:** "Structural Scoring: Exploiting Semantic Layer Ownership Signals for Schema Routing in Enterprise NL2SQL"

**Target Venues:**
- VLDB Industry Track 2027
- HILDA (Human-in-the-Loop Data Analytics) @ SIGMOD 2027

---

## 9. Business Impact

- **Accuracy:** 33% → 83% routing accuracy on enterprise evaluation set
- **Cost avoidance:** Correct routing prevents wrong-table BigQuery scans ($50-100 per misrouted query on 5+ PB tables)
- **Competitive advantage:** No competitor uses semantic layer structural ownership for routing
- **Scalability:** O(E × N), sub-millisecond, supports 500+ explores without retraining
- **Deterministic reproducibility:** Critical for regulated financial services (auditable, repeatable)

---

## 10. Next Steps

1. **Saheb:** Review with Lakshmi (patent liaison)
2. **Lakshmi:** Assess patentability, formal prior art search
3. **Saheb + Lakshmi:** Draft formal application with patent attorney
4. **Coordinate with CORTEX-PAT-001** (filter resolution) — continuation patent strategy
5. **Log as Innovation & Influence accomplishment**

---

## Appendix: Research Sources

### Academic Papers
- DBCopilot (EDBT 2025) — Schema routing via differentiable search index
- RESDSQL (Li et al., AAAI 2023) — Schema linking via cross-encoder ranking
- DIN-SQL (Pourreza & Rafiei, NeurIPS 2023) — Decomposed NL2SQL
- CHESS (Talaei et al., 2024) — Contextual schema filtering
- Odin (EMNLP 2025) — NL2SQL recommender for schema ambiguity
- "NL2SQL is a solved problem... Not!" (CIDR 2024, Microsoft)
- BM25 (Robertson et al., 1994) — Probabilistic IR scoring

### Patents Analyzed
- US11,636,115 (Salesforce, 2023) — NL-to-SQL using schema metadata
- US11,341,145 (Google, 2022) — Query understanding for BI tools
- US20230100194 (C3.ai, 2023) — Entity extraction NL2SQL
