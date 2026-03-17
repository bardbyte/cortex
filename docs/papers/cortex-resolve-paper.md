# CortexResolve: Structural Scoring and Self-Improving Filter Resolution for Enterprise NL2SQL over Semantic Layers

**Authors:** [Anonymized for review]
**Affiliation:** Fortune 50 Financial Services Company
**Target Venue:** VLDB Industry Track 2027 / HILDA @ SIGMOD 2027
**Status:** Draft

---

## Abstract

Natural language to SQL (NL2SQL) systems consistently underperform in enterprise environments where data is organized across multiple overlapping schemas in a semantic modeling layer. Two critical sub-problems — schema routing (selecting which schema to query) and filter value resolution (mapping natural language terms to database-internal codes) — account for the majority of production errors but are absent from standard benchmarks like Spider and BIRD. We present CortexResolve, a system deployed at a Fortune 50 financial services company over 5+ petabytes of data in Google BigQuery, comprising three contributions: (1) a multiplicative structural scoring formula that uses semantic layer ownership signals (base view declarations) to route queries to the correct schema, improving routing accuracy from 33% to 83%; (2) a four-pass deterministic filter value resolution system with a Wilson-score-based synonym learning loop that requires zero LLM calls at query time; and (3) a confidence-gated three-action routing system that uses ratio-based near-miss detection to decide whether to proceed, disambiguate, or request clarification. We evaluate on a 12-query golden dataset across 6 schemas and analyze the system's failure modes, latency characteristics, and scaling properties for deployment across 50+ schemas and 3 business units.

---

## 1. Introduction

The promise of NL2SQL — asking questions of databases in natural language — has attracted sustained attention from both academia and industry. Systems like Spider [1], BIRD [2], and their successors have pushed accuracy on standard benchmarks above 85%. Yet practitioners consistently report that these results do not transfer to enterprise deployments [3].

The gap is not in SQL generation quality. Modern LLMs can produce syntactically correct SQL for complex queries. The gap is in what happens *before* SQL generation: understanding which data source to query, and how to translate the user's natural language filter terms into the exact values stored in the database.

### 1.1 The Schema Routing Problem

Enterprise analytical platforms organize data into multiple overlapping schemas — referred to as "explores" in Looker, "datasets" in dbt, or "analytical contexts" generically. A single field like `total_billed_business` may be reachable from 4 of 6 schemas through SQL JOIN paths. When a user asks "show me total billed business by generation," the system must determine which schema was *designed* for this analysis versus which merely *joins to* the relevant table.

This problem does not exist in Spider or BIRD, which assume a single database with unambiguous tables. In enterprise Looker environments with 50+ explores, incorrect schema routing is the single largest source of NL2SQL errors — and the hardest to detect, because the query executes successfully and returns plausible-looking data from the wrong analytical context.

### 1.2 The Filter Value Resolution Problem

When a user says "show me spend for small businesses," the system must resolve "small businesses" to the exact database value `bus_seg = 'OPEN'`. This mapping is organization-specific — no LLM training data contains American financial services industry segment codes. LLM-based resolution produces non-deterministic results: the same query may resolve to different values across invocations [3].

### 1.3 The Binary Failure Mode Problem

Current NL2SQL systems operate in a binary mode: they either return results or fail. This creates false confidence (wrong data returned without uncertainty signals) and unnecessary failure (reasonable candidates exist but the system didn't know to ask). No existing system uses a principled mechanism to decide between proceeding, disambiguating, and requesting clarification.

### 1.4 Contributions

We present CortexResolve, a production NL2SQL pipeline that addresses all three problems:

1. **Multiplicative structural scoring** using semantic layer ownership signals (LookML base view declarations) for schema routing, achieving 83% accuracy vs. 33% for additive baselines.

2. **Self-improving deterministic filter resolution** via four-pass matching (exact → fuzzy → synonym → semantic) with zero LLM calls, coupled with a Wilson-score-based synonym learning loop.

3. **Confidence-gated three-action routing** using ratio-based near-miss detection to determine proceed/disambiguate/clarify actions, eliminating false-confident errors.

---

## 2. Background and Related Work

### 2.1 NL2SQL Landscape

The NL2SQL field has evolved through several benchmark generations: Spider [1] (single-database, cross-domain), BIRD [2] (realistic values, external knowledge), and enterprise-focused evaluations. Floratou et al. [3] argue that enterprise NL2SQL remains unsolved, identifying value grounding, schema complexity, and ambiguity handling as the key gaps.

### 2.2 Semantic Layers

Semantic modeling layers (Looker LookML [4], dbt Semantic Layer, Cube, AtScale) define business-friendly abstractions over database tables. They introduce the concept of *explores* — pre-joined analytical contexts with governed field definitions. Each explore declares a *base view* (`from:` in LookML) — the primary table the explore was designed to analyze. Joined views provide enrichment but are secondary.

This structural metadata — base view ownership, join relationships, field type classifications — is a rich signal source that no existing NL2SQL system exploits for routing.

### 2.3 Schema Linking and Routing

Schema linking — mapping natural language mentions to database schema elements — is a prerequisite for NL2SQL. RESDSQL [5] uses cross-encoder ranking. DIN-SQL [6] decomposes the problem. DBCopilot [7] introduces a differentiable search index for schema routing. CHESS [8] uses LLM-based adaptive pruning. None of these systems use semantic layer structural metadata or multiplicative scoring.

### 2.4 Ambiguity and Disambiguation

AmbiSQL [9] provides a taxonomy of NL2SQL ambiguity types. Sphinteract [10] proposes the SRA (Suggest-Resolve-Acknowledge) paradigm. PRACTIQ [11] uses slot-filling dialogue for conversational text-to-SQL. FISQL [12] introduces interactive feedback. These works address ambiguity classification and resolution but do not provide operational confidence-based routing with ratio-based near-miss detection.

### 2.5 Active Learning and Feedback

RubikSQL [13] proposes lifelong learning for NL2SQL via DAAC index. HILDA 2025 work [14] shows that past user feedback improves text-to-SQL accuracy by 14.9%. SQL-Trail [15] uses multi-turn RL for refinement. Our synonym learning loop is complementary — it operates at the value level (not query level) and uses Wilson score confidence [16] for promotion decisions.

---

## 3. System Architecture

CortexResolve operates as a three-phase pipeline:

```
                    ┌─────────────────────────┐
                    │   Natural Language Query │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │  PHASE 1: CLASSIFY       │
                    │  + EXTRACT               │
                    │                          │
                    │  LLM extracts:           │
                    │  - Measures              │
                    │  - Dimensions            │
                    │  - Filters + timeframes  │
                    │  - Intent classification │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │  PHASE 2: RETRIEVE       │
                    │  + SCORE                 │
                    │                          │
                    │  1. Batch embed entities │
                    │  2. pgvector search      │
                    │  3. Graph validation     │
                    │  4. Structural scoring   │
                    │  5. Filter resolution    │
                    │  6. Confidence + routing │
                    └───────────┬─────────────┘
                                │
                  ┌─────────────┼─────────────┐
                  │             │             │
            ┌─────▼────┐ ┌─────▼────┐ ┌──────▼─────┐
            │ PROCEED  │ │DISAMBIG. │ │  CLARIFY   │
            │          │ │          │ │            │
            │ Phase 3: │ │ Present  │ │ Ask user   │
            │ Generate │ │ options  │ │ to rephrase│
            │ SQL via  │ │ to user  │ │            │
            │ MCP      │ │          │ │            │
            └──────────┘ └──────────┘ └────────────┘
```

**Technology stack:**
- LLM: Gemini 2.5 Flash (entity extraction, SQL generation) via SafeChain wrapper
- Embeddings: BGE-large-en-v1.5 [17] via SafeChain
- Vector search: pgvector with HNSW index (m=16, ef_construction=64)
- Graph: Apache AGE for LookML relationship validation
- SQL execution: Looker MCP (Model Context Protocol)
- Streaming: Server-Sent Events (SSE) for progressive disclosure
- Frontend: ChatGPT Enterprise

---

## 4. Structural Scoring for Explore Routing

### 4.1 Problem Formulation

Given a natural language query Q and a set of explores E = {e₁, ..., eₙ}, find:

```
e* = argmax score(Q, eᵢ)
         eᵢ ∈ E
```

Each explore eᵢ has: a set of fields Fᵢ (measures and dimensions), a base view bᵢ (the `from:` clause), a set of joined views Jᵢ, and a natural language description dᵢ.

### 4.2 The Additive Baseline (33% Accuracy)

Our initial implementation used an additive scoring formula:

```
score_additive = w₁ × coverage + w₂ × mean_similarity + w₃ × text_match
```

This achieved 33% routing accuracy (4/12 on our golden dataset). The root cause: additive composition allows **compensatory trading** — a high similarity on one field can overwhelm zero coverage. An explore matching 1 of 4 entities with high similarity can outscore an explore matching 4 of 4 with moderate similarity.

### 4.3 The Multiplicative Formula (83% Accuracy)

We replaced the additive formula with:

```
score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus × filter_penalty
```

**Signal 1: Coverage Cubed.** `coverage = matched_entities / total_entities`. The cubic exponent creates a multiplicative gate:

| Coverage | Linear | Cubic |
|----------|--------|-------|
| 1.00 | 1.000 | 1.000 |
| 0.75 | 0.750 | 0.422 |
| 0.50 | 0.500 | 0.125 |
| 0.25 | 0.250 | 0.016 |

At cubic, an explore covering only half the entities receives 12.5% of the coverage score — effectively eliminated from competition.

**Signal 2: Mean Similarity.** Arithmetic mean of the best cosine similarity per matched entity, using BGE-large-en-v1.5 embeddings with the query instruction prefix ("Represent this sentence for searching relevant passages: "). The prefix is critical — omitting it reduces recall by ~15% due to the asymmetric training of the BGE model.

**Signal 3: Base View Bonus (Novel).** This is the core technical contribution.

```
base_view_bonus = 1.0 + weighted_base_view_ratio

weighted_base_view_ratio = Σ(wᵢ × is_base_viewᵢ) / Σ(wᵢ)

wᵢ = 2.0 if measure, 1.0 if dimension
is_base_viewᵢ = 1 if field's view = explore's from: view AND sim ≥ 0.65
```

Every explore in LookML declares a base view via `from:`. This specifies the table the explore was *designed* to analyze. Fields from joined views are secondary. The base view bonus encodes the semantic modeler's intent: a field from the base view is "owned" by the explore; a field from a joined view is "borrowed."

Measures are weighted 2× because the measure determines the analytical grain. A user asking for "total billed business" wants the explore designed for billed business analysis, regardless of which table provides the grouping dimension.

The similarity floor (0.65) prevents low-quality vector matches from being amplified by the structural bonus.

**Signal 4: Description Similarity Bonus.** `desc_sim_bonus = 1.0 + 0.2 × sim(query, explore_desc)`. A tiebreaker with intentionally small coefficient (0.2). Activates when all entities come from universally joined views.

**Signal 5: Filter Penalty.** `filter_penalty = max(matched_filters / total_filters, 0.1)`. Penalizes explores that lack dimensions referenced in the user's filter terms. Floor of 0.1 prevents hallucinated filter terms from zeroing all scores.

### 4.4 Why Multiplicative Works

The multiplicative structure enforces **jointly necessary conditions**:
- Zero coverage → zero score (explore can't serve the query)
- Zero similarity → zero score (fields don't match semantically)
- No base view match → bonus of 1.0 (neutral, not zero — joined fields are still valid)

This prevents the compensatory trading that plagued the additive formula. An explore with 95% similarity but 10% coverage scores 0.95 × 0.001 = 0.00095 (multiplicative) vs. 1.05 (additive). The multiplicative score correctly reflects that covering 10% of the query makes the explore almost certainly wrong.

### 4.5 The 7 Gap Fixes

We identified 7 specific gaps between the additive baseline and production-ready scoring:

| # | Gap | Fix | Accuracy Impact |
|---|-----|-----|-----------------|
| 1 | Coverage always 1.0 (bug: total/total) | Fix to supported/total | Broke ties between 6 explores |
| 2 | No LookML structural signal | Base view bonus from `from:` | Resolved 3 misroutes |
| 3 | Additive formula | Multiplicative formula | Zero-coverage explores eliminated |
| 4 | Measures weighted = dimensions | 2× weight for measures | Fixed spend-vs-retention confusion |
| 5 | No explore description matching | desc_sim_bonus | Broke 2 near-ties |
| 6 | No filter validation in scoring | filter_penalty | Fixed 1 misroute |
| 7 | Sequential embedding (5 API calls) | Batch embedding (1 call) | Latency only (~800ms saved) |

---

## 5. Self-Improving Filter Value Resolution

### 5.1 The Coded Value Problem

Enterprise databases use internal codes that bear no semantic relationship to business terminology. Examples from our deployment:

| User Term | Database Value | Dimension |
|-----------|---------------|-----------|
| "small business" | `OPEN` | `bus_seg` |
| "consumer" | `CPS` | `bus_seg` |
| "Millennial" | `Millennial` | `generation` |
| "high tenure" | `20 or above` | `customer_tenure_tier` |

LLMs cannot reliably resolve these mappings because the codes are organization-specific. LLM-based resolution is also non-deterministic: "small business" may resolve to `OPEN` in one invocation and `SMB` in another.

### 5.2 Four-Pass Deterministic Resolution

Our system resolves filter values through four sequential passes, requiring **zero LLM calls** at query time:

**Pass 1 — Exact Match.** Case-insensitive hash lookup in the dimension value catalog. O(1) per lookup. Resolves ~60% of filter terms.

**Pass 2 — Fuzzy Match.** Levenshtein distance ≤ 2 and trigram similarity. Handles typos ("millenial" → "Millennial") and minor variations. Resolves ~15% of remaining terms.

**Pass 3 — Synonym Match.** Array containment check against the synonyms column in the value catalog (`user_term = ANY(synonyms)`). Resolves "small business" → `OPEN` via the synonym `["small business", "SMB", "small biz"]`. Resolves ~15% of remaining terms.

**Pass 4 — Semantic Match.** Cosine similarity on value embeddings using the same BGE model. Handles paraphrases that aren't in the synonym list. Resolves ~5% of remaining terms.

Total latency: <15ms across all four passes. The remaining ~5% are unresolvable (the user referenced a value that doesn't exist) — these trigger the learning loop.

### 5.3 Wilson-Score Synonym Learning Loop

When no match is found across all four passes, the system presents candidate values to the user. The user's selection is logged as a synonym suggestion.

```
synonym_suggestion = {
  user_term: "small biz",
  dimension: "bus_seg",
  value: "OPEN",
  times_selected: 3,
  times_shown: 4,
  distinct_users: 3
}
```

Suggestions accumulate positive signals (selected) and negative signals (shown but not selected). Promotion to active synonym requires exceeding a confidence threshold computed via the Wilson score lower bound [16]:

```
wilson_lower(k, n) = (p̂ + z²/2n - z√(p̂(1-p̂)/n + z²/4n²)) / (1 + z²/n)

where k = times_selected, n = times_shown, p̂ = k/n, z = 1.96
```

This is superior to count-based thresholds because:
- 3/3 selections = Wilson lower 0.44 (not 100% — small sample)
- 7/10 = Wilson lower 0.40 (lower than 3/3 because of 3 rejections)
- 15/16 = Wilson lower 0.77 (approaching threshold)
- 20/20 = Wilson lower 0.87 (exceeds 0.80 threshold)

### 5.4 Three-Phase Synonym Lifecycle

**Phase 1 — Cold Start.** LLM generates synonym candidates from dimension descriptions. Steward reviews. ~15 minutes per business unit.

**Phase 2 — Steward-Gated.** All user-initiated suggestions routed to steward queue. Appropriate for <100 users.

**Phase 3 — Bayesian Auto-Approval.** Wilson lower > 0.8 AND distinct_users ≥ 5 → auto-promoted. Conflicting mappings always route to steward. Reduces steward burden by ~90%.

### 5.5 Graph-Structural Candidate Narrowing

The resolution system does not search the entire value catalog. It uses vector search results to narrow the search space:

1. User says "small businesses"
2. Vector search returns candidate dimensions: `[bus_seg (0.84), business_org (0.79)]`
3. Value catalog searches only these 2 dimensions (not all 250)
4. After resolution (`bus_seg = "OPEN"`), graph validation confirms the dimension is reachable from the selected explore

This reduces search space by 90%+ and prevents resolved filters from being applied to structurally invalid query paths.

---

## 6. Confidence-Gated Action Routing

### 6.1 Three Actions, Not Two

We replace the binary succeed/fail pattern with three distinct actions:

| Action | Trigger | System State | User Experience |
|--------|---------|-------------|-----------------|
| **Proceed** | High confidence, no near-miss | Clear winner | Results returned directly |
| **Disambiguate** | Near-miss detected | Strong candidates, can't pick | Multiple-choice selection |
| **Clarify** | Low confidence | No strong candidates | Free-text conversation |

### 6.2 Ratio-Based Near-Miss Detection

```
ratio = score₂ / score₁
is_near_miss = (ratio ≥ 0.85)
```

The ratio measures the *gap* between the top two candidates. This is scale-invariant — it works whether scores range from 0.1-0.3 or 0.7-0.9. An absolute threshold would fail at different score scales.

At ratio ≥ 0.85, the top two candidates are within 18% of each other. A ~15% perturbation in any single scoring signal could change the ranking. In our observed data:
- Correct routing: ratios of 0.20 to 0.77 (clear separation)
- Genuine ambiguity: ratios of 0.85 to 0.95 (close competition)

### 6.3 Relative Confidence Normalization

```
max_theoretical = max(1.0, top_score × 1.2)
confidence = top_score / max_theoretical
```

We normalize against the observed maximum rather than a theoretical maximum. This is self-calibrating: adding or removing scoring signals doesn't require recalibrating a denominator. The quality floor (1.0) prevents degenerate normalization when all scores are near zero.

### 6.4 Integration with SSE Streaming

Each action produces a distinct Server-Sent Events stream. The `proceed` stream includes `sql_generated`, `results`, and `follow_ups` events. The `disambiguate` stream includes option descriptions and scores. The `clarify` stream includes rephrasing suggestions. The frontend renders each stream differently without parsing the full response.

---

## 7. Evaluation

### 7.1 Golden Dataset

We evaluate on 12 queries across 6 explores in a Looker model over financial data:

| Query | Expected Explore | Entities | Difficulty |
|-------|-----------------|----------|------------|
| "Total billed business by generation" | finance_cardmember_360 | 2 | Ambiguous — measure in 2 base views |
| "Highest billed business by merchant category" | finance_merchant_profitability | 2 | Clear — both from one base view |
| "Travel gross sales by vertical" | finance_travel_sales | 2 | Clear |
| "Card product issuance volume" | card_product_explore | 1 | Clear |
| "Customer churn rate by tenure tier" | attrition_explore | 2 | Clear |
| "Spend by generation for Millennials" | finance_cardmember_360 | 2+1 filter | Filter resolution needed |
| "Show me the data" | N/A | 0 | Vague — should clarify |
| ... (5 more) | | | |

### 7.2 Results

| System Configuration | Routing Accuracy | False Confidence | Avg Latency |
|---------------------|-----------------|------------------|-------------|
| Additive baseline | 33% (4/12) | 67% (8/12) | 1.2s |
| + Coverage bug fix | 42% (5/12) | 58% (7/12) | 1.2s |
| + Multiplicative formula | 58% (7/12) | 33% (4/12) | 1.2s |
| + Base view bonus | 75% (9/12) | 17% (2/12) | 1.2s |
| **+ All 7 fixes** | **83% (10/12)** | **0%** | **0.4s** |
| + Action routing | 83% proceed correctly + 17% correct disambiguate/clarify | **0%** | 0.4s |

### 7.3 Failure Mode Analysis

**Failure 1: LLM extraction failure.** Query: "show me the data for card products." Gemini 2.5 Flash returned zero measures (malformed JSON). With zero entities, all explores score zero.

*Fix:* Synthetic entity injection — when extraction returns zero entities, inject the raw query as a single measure entity. This produces low but non-zero scores that correctly route to `clarify` action.

**Failure 2: Genuine ambiguity.** Query: "total billed business by generation." The measure `total_billed_business` exists in both `custins` (base of cardmember_360) and `fin_merchant` (base of merchant_profitability). Near-miss ratio = 0.895 ≥ 0.85.

*This is correct behavior.* The system detects genuine ambiguity and asks the user to choose. The 83% "proceed" accuracy plus 17% "correct disambiguation" yields 100% correct action routing.

### 7.4 Latency Analysis

| Component | Latency | Notes |
|-----------|---------|-------|
| Entity extraction (LLM) | ~300ms | Gemini 2.5 Flash |
| Batch embedding | ~200ms | BGE, 1 API call for all entities |
| pgvector search | ~50ms | HNSW, m=16, ef_construction=64 |
| Structural scoring | <1ms | Arithmetic operations only |
| Filter resolution | <15ms | 4-pass deterministic |
| SQL generation (LLM) | ~1s | Gemini via Looker MCP |
| **Total** | **~1.6s** | End-to-end, proceed action |

The scoring formula itself is never the bottleneck. Batch embedding (gap fix #7) reduced embedding time from ~1s to ~200ms.

### 7.5 Scale Projections

| Scale | Explores | Fields | Scoring Ops | Projected Issues |
|-------|----------|--------|-------------|------------------|
| Current | 6 | ~120 | 12-24 | None |
| May 2026 (3 BUs) | 15 | ~300 | 30-60 | Embedding space overlap |
| 2027 target | 50+ | ~1000 | 100-200 | Namespace collisions |

At 50+ explores, we project:
- **Embedding space pollution:** "total spend" matches 15+ explores. Mitigation: pre-filter by `model_name`.
- **Cross-BU namespace collisions:** Multiple BUs define `cust_ref` with different semantics. Mitigation: prefix embeddings with `[BU_name]`.
- **HNSW tuning:** Current m=16, ef_construction=64 tuned for ~120 fields. At 1000+, bump to m=32, ef_construction=128.

---

## 8. Deployment Lessons

### 8.1 LookML as the Source of Structural Truth

The `from:` clause insight — that the base view declaration encodes the semantic modeler's intent about which fields an explore "owns" — was the single most impactful discovery. This structural signal is present in every LookML model but invisible to systems that treat all reachable fields as equivalent.

### 8.2 BGE Query Prefix Matters

The BGE-large-en-v1.5 model [17] was trained with asymmetric prefixes: queries get "Represent this sentence for searching relevant passages:" while documents are embedded without prefix. Omitting the prefix reduced recall by ~15% in our measurements. This is a common deployment mistake in production embedding systems.

### 8.3 Batch Embedding for Production

Sequential per-entity embedding API calls (5 calls × 200ms = 1s) were replaced with a single batch call (200ms total). This required switching from `embed_query()` to `embed_documents()` in the LangChain interface, with the query prefix applied manually before batching.

### 8.4 Connection Pooling

The PostgreSQL engine (for pgvector and Apache AGE) must be a singleton with connection pooling (`pool_size=5, pool_pre_ping=True`). Without pooling, each query opens a new connection (~100ms overhead on corporate networks).

---

## 9. Limitations and Future Work

**Small evaluation set.** Our golden dataset contains only 12 queries across 6 explores. While each query was carefully constructed to exercise different failure modes, 12 queries cannot provide statistical confidence bounds. We plan to expand to 100+ queries covering all 50+ explores.

**Synonym learning not yet deployed.** The four-pass resolution and synonym learning loop are designed and implemented but not yet validated in production. The Wilson score thresholds and phase transition criteria are based on simulation, not observed user behavior.

**Single enterprise context.** All results are from one organization's Looker model. The base view bonus depends on LookML's `from:` clause — generalizability to dbt semantic layer or other modeling tools is untested.

**No LLM-only baseline.** We did not compare against GPT-4 or Claude for schema routing (providing all explore descriptions in-context and asking the LLM to select). This comparison would strengthen our claims about the value of structural signals.

**Future directions:**
- Context-dependent synonyms (same term, different meanings in different explores)
- Implicit feedback (user reformulates query → previous route was likely wrong)
- Cross-BU transfer learning (synonyms learned in one BU applied to similar fields in another)
- Adaptive threshold calibration (adjusting 0.85 near-miss threshold based on observed false-positive/negative rates)

---

## 10. Conclusion

Enterprise NL2SQL systems fail not because LLMs can't generate SQL, but because they can't reliably determine *which data source to query* and *how to translate filter terms*. CortexResolve addresses these upstream problems with three mechanisms: multiplicative structural scoring that exploits semantic layer ownership signals, deterministic filter resolution with a self-improving synonym learning loop, and confidence-gated action routing that replaces the binary succeed/fail pattern.

The key insight is that semantic modeling layers like LookML contain rich structural metadata — base view declarations, join relationships, field type classifications — that no prior NL2SQL system exploits. By combining this structural evidence with vector similarity in a multiplicative formula, we achieve 83% routing accuracy on enterprise data, up from 33% with an additive baseline.

These techniques are not specific to our deployment. Any NL2SQL system built on a semantic modeling layer (Looker, dbt, Cube, AtScale) can benefit from structural scoring, and any system facing coded enterprise values can benefit from deterministic resolution with a learning loop. We hope this work encourages the NL2SQL community to look beyond single-table benchmarks toward the structural complexity of real enterprise data platforms.

---

## References

[1] Yu, T., Zhang, R., Yang, K., et al. "Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task." EMNLP 2018.

[2] Li, J., Hui, B., Qu, G., et al. "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs." NeurIPS 2023.

[3] Floratou, A., Kul, G., et al. "NL2SQL is a solved problem... Not!" CIDR 2024.

[4] Google Cloud. "LookML Reference." Looker Documentation, 2024.

[5] Li, H., Zhang, J., Li, C., Chen, H. "RESDSQL: Decoupling Schema Linking and Skeleton Parsing for Text-to-SQL." AAAI 2023.

[6] Pourreza, M., Rafiei, D. "DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction." NeurIPS 2023.

[7] Wang, T., et al. "DBCopilot: Scaling Natural Language Querying to Massive Databases." EDBT 2025.

[8] Talaei, S., et al. "CHESS: Contextual Harnessing for Efficient SQL Synthesis." arXiv 2024.

[9] "AmbiSQL: Towards a Comprehensive Benchmark for Evaluating Ambiguity in Text-to-SQL." arXiv Aug 2025.

[10] "Sphinteract: Schema-aware Conversational NL2SQL through Interactive Disambiguation." VLDB 2025.

[11] "PRACTIQ: A Practical Conversational Text-to-SQL Dataset with Ambiguity Resolution." NAACL 2025.

[12] "FISQL: An Interactive Text-to-SQL Framework with Feedback." EDBT 2025.

[13] "RubikSQL: A Lifelong Learning NL2SQL System with Dynamic Adaptation." Alibaba, arXiv 2025.

[14] "Leveraging Past User Feedback for Improving Text-to-SQL." HILDA @ SIGMOD 2025.

[15] "SQL-Trail: Multi-Turn Reinforcement Learning for SQL Refinement." arXiv Jan 2026.

[16] Wilson, E.B. "Probable Inference, the Law of Succession, and Statistical Inference." Journal of the American Statistical Association, 1927.

[17] Xiao, S., Liu, Z., Zhang, P., Muennighoff, N. "C-Pack: Packaged Resources to Advance General Chinese Embedding." arXiv 2023.

[18] "Interactive Text-to-SQL Generation via Expected Information Gain." arXiv Jul 2025.

[19] "Continual Learning from Human Feedback for NL2SQL." arXiv Nov 2025.

[20] Gan, Y., et al. "Towards Robustness of Text-to-SQL Models against Synonym Substitution." ACL 2021.
