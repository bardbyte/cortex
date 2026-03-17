# Patent Landscape Analysis — Cortex NL2SQL Pipeline

**Author:** Saheb | **Date:** March 16, 2026
**Status:** Ready for Lakshmi Review
**Revenue Target:** 10–20 filings × $2,500 = $25,000–$50,000

---

## Executive Summary

This document identifies 15 patentable inventions from the Cortex NL2SQL pipeline. After prior art search across Google Patents, USPTO, and academic literature, **none of the 15 ideas have direct prior art** in their specific form. The key differentiator across all disclosures: Cortex is the first system to combine **semantic layer structural signals** (LookML explore ownership, base view declarations, join topology) with **vector similarity search** for intent-to-schema routing. Existing NL2SQL systems (C3.ai, Salesforce Einstein, AWS QuickSight Q, Google Duet AI) rely on either pure vector similarity or LLM-only reasoning — none exploit the semantic layer's structural metadata as a scoring signal.

---

## Prior Art Landscape

### Closest Existing Patents
| Patent/System | What It Does | How Cortex Differs |
|---|---|---|
| US11,636,115 (Salesforce) | NL→SQL using schema metadata | No semantic layer signals, no multiplicative scoring, no explore routing |
| US11,341,145 (Google) | Query understanding for BI tools | Column matching only, no base-view ownership concept |
| US20230100194 (C3.ai) | NL2SQL with entity extraction | No LookML structural signals, no confidence-gated actions |
| ThoughtSpot Search | Token-based column matching | Additive scoring, no coverage exponent, no near-miss detection |
| Looker Explore Assistant | LLM generates Looker queries | No retrieval pipeline, no scoring formula, relies on LLM reasoning alone |

### Academic Prior Art
| Paper | Year | Gap vs Cortex |
|---|---|---|
| RESDSQL (Li et al.) | 2023 | Schema linking via ranking, no semantic layer, no structural signals |
| DIN-SQL (Pourreza & Rafiei) | 2023 | Decomposed NL2SQL, no explore routing, no confidence actions |
| CHESS (Talaei et al.) | 2024 | Schema filtering + SQL generation, no LookML, no multiplicative formula |
| MAC-SQL (Wang et al.) | 2024 | Multi-agent NL2SQL, no semantic layer integration |

**Key finding:** No existing system uses a **semantic layer** (Looker, dbt, etc.) as a **structural scoring signal** for schema routing. This is the foundational novelty across all 15 disclosures.

---

## Patent Disclosures

### Priority 0 — File Immediately ($12,500)

#### Patent #1: Multiplicative Explore Routing via Semantic Layer Structural Signals
**Claim:** A method for routing natural language queries to database schemas using a multiplicative scoring formula that combines vector similarity with semantic layer structural metadata.

**Formula:** `score = coverage³ × mean_sim × base_view_bonus × desc_sim_bonus × filter_penalty`

**Novel aspects:**
- Coverage exponent (³) penalizes partial matches non-linearly — no prior art uses coverage as a multiplicative factor
- Base view bonus uses semantic layer `from:` declarations (structural ownership) as a scoring signal
- Multiplicative composition ensures any zero signal kills the score (vs additive where weak signals can compensate)

**Prior art concern:** Low. Multiplicative scoring exists in IR (BM25 components), but applying it to semantic-layer-aware schema routing is novel.

#### Patent #2: Near-Miss Detection and Disambiguation in Schema Routing
**Claim:** A method for detecting ambiguous schema routing situations where the top-2 candidate schemas score within a configurable ratio threshold, triggering a disambiguation workflow instead of proceeding with a potentially incorrect selection.

**Novel aspects:**
- Ratio-based detection (score₂/score₁ ≥ 0.85) rather than absolute threshold
- Automatic action escalation: proceed → disambiguate → clarify → no_match
- Preserves both candidates with their scored rationale for user presentation

**Prior art concern:** Low. Confusion detection exists in dialogue systems, but not in schema routing with scored explore candidates.

#### Patent #3: Extraction Quality Gate for LLM-Powered Entity Extraction
**Claim:** A method for assessing the reliability of LLM-generated entity extraction by tracking retry counts and applying graduated confidence penalties to downstream scoring.

**Novel aspects:**
- Retry count as a reliability signal (0 retries = reliable, 1 = degraded, 2+ = unreliable)
- Graduated penalty: confidence × 0.7 for 1 failure, × 0.5 for 2+ failures
- Action escalation: extraction_failures ≥ 2 → action="clarify" regardless of score
- Prevents the system from confidently routing on garbage extraction

**Prior art concern:** Low. LLM output validation exists, but using retry count as a confidence penalty for downstream scoring is novel.

#### Patent #4: Five-Pass Cascading Filter Value Resolution
**Claim:** A method for resolving ambiguous filter values in natural language queries through a cascading sequence of resolution strategies with increasing fuzziness.

**Five passes:**
1. Exact match against known enumeration values
2. Case-insensitive match
3. Prefix match (e.g., "Mill" → "Millennial")
4. Fuzzy match (Levenshtein distance ≤ 2)
5. LLM-assisted semantic resolution (e.g., "young people" → "Millennial, Gen Z")

**Novel aspects:**
- Deterministic passes before LLM (cheaper, faster, more predictable)
- Each pass produces a confidence score that feeds back into the scoring formula
- Cascade stops at first successful resolution (short-circuit optimization)

**Prior art concern:** Low. Fuzzy matching cascades exist in search, but applied to filter value resolution in NL2SQL with LLM fallback is novel.

#### Patent #5: Base View Ownership Scoring Using Semantic Layer Declarations
**Claim:** A method for scoring candidate database schemas by comparing matched fields against the schema's declared base view (the `from:` property in LookML), distinguishing primary fields from joined fields.

**Novel aspects:**
- Uses the semantic layer's `from:` declaration as ground truth for field ownership
- Fields from the base view get a 1.5× bonus; joined fields get 1.0×
- Similarity floor (0.65) prevents low-quality vector matches from getting structural bonus
- Encodes the semantic layer author's intent (which view the explore was DESIGNED to analyze)

**Prior art concern:** Low. No prior art combines semantic layer base view declarations with vector similarity scoring.

---

### Priority 1 — File Within 30 Days ($17,500)

#### Patent #6: Explore Description Semantic Matching for Tiebreaking
**Claim:** A method for breaking ties between equally-scored candidate schemas by computing the semantic similarity between the user's query and each schema's natural language description.

**Novel aspects:**
- Uses the semantic layer's explore descriptions (authored by data modelers) as a tiebreaking signal
- Embedding-based comparison between query and explore description
- Only activates when base_view_bonus cannot discriminate (tiebreaker, not primary signal)

**Prior art concern:** Medium. Description matching exists in document retrieval, but applying it as a tiebreaker in schema routing is somewhat novel.

#### Patent #7: Confidence-Gated Action State Machine for NL2SQL
**Claim:** A system that determines whether to execute a query, request disambiguation, ask for clarification, or report no match based on a multi-signal confidence score with explicit thresholds.

**Action states:**
- `proceed` (confidence ≥ 0.6, no near-miss, extraction reliable)
- `disambiguate` (near-miss detected, present top-2 with rationale)
- `clarify` (extraction unreliable OR confidence < 0.3)
- `no_match` (no explores score above minimum threshold)

**Novel aspects:**
- Multi-signal confidence (not just similarity) drives action selection
- Extraction quality feeds into action gating
- Near-miss detection is a separate signal from confidence threshold

**Prior art concern:** Low. Confidence thresholds exist, but the specific 4-state machine with extraction quality + near-miss + score signals is novel.

#### Patent #8: Coverage-Cubed Entity Completeness Scoring
**Claim:** A method for scoring candidate schemas by the fraction of user-requested entities they can serve, raised to the third power to create a non-linear penalty for missing entities.

**Formula:** `coverage = (matched_entities / total_entities)³`

**Novel aspects:**
- Cubic exponent creates steep penalty: 80% coverage → 0.51 score, 60% → 0.22
- Prevents partial-match explores from competing with full-match explores
- Mathematically ensures that missing even one entity is severely penalized

**Prior art concern:** Low. Coverage ratios exist in IR, but cubic exponentiation for schema routing completeness is novel.

#### Patent #9: Hybrid Retrieval Orchestration with Deterministic Pre-processing
**Claim:** A system architecture that separates NL2SQL processing into three phases: deterministic pre-processing (entity extraction, vector search, explore scoring, filter resolution), LLM-powered execution (SQL generation via tool use), and post-processing (result formatting, follow-up generation).

**Novel aspects:**
- Phase 1 is entirely deterministic and cacheable — no LLM calls after entity extraction
- Phase 2 uses tool-use pattern (Looker MCP) rather than direct SQL generation
- PipelineTrace captures every decision for evaluation and replay
- Streaming architecture surfaces each step to the UI in real-time

**Prior art concern:** Medium. Staged NL2SQL pipelines exist, but the specific 3-phase split with deterministic retrieval + MCP tool execution is novel.

#### Patent #10: Filter-Aware Explore Penalty Scoring
**Claim:** A method for penalizing candidate schemas that cannot serve user-specified filter conditions by checking filter field availability before explore selection.

**Novel aspects:**
- Checks filter field_hints against explore_field_index BEFORE scoring (not after selection)
- Binary penalty: explore supports filter → 1.0, doesn't → 0.5
- Prevents explore selection that would lose user's filter intent
- Uses ILIKE pattern matching against semantic layer field catalog

**Prior art concern:** Low. Filter validation exists in SQL planners, but pre-selection penalty based on filter field availability in the semantic layer is novel.

#### Patent #11: Semantic Layer Auto-Derivation from Enrichment Metadata
**Claim:** A method for automatically generating semantic layer definitions (LookML views, explores, join relationships) from a metadata enrichment store, maintaining semantic consistency across business units.

**Novel aspects:**
- Enrichment store → LookML generation pipeline
- Preserves business vocabulary in generated descriptions
- Handles partition filter injection automatically
- Git-based workflow for review and deployment

**Prior art concern:** Medium. LookML generation tools exist (lookml-gen), but generation from an enrichment metadata store with partition awareness is novel.

#### Patent #12: Real-Time Pipeline Transparency via Streaming Traces
**Claim:** A system for streaming NL2SQL pipeline decision traces to a user interface in real-time, showing entity extraction, field matching, explore scoring, and SQL generation as they happen.

**Novel aspects:**
- SSE-based streaming of pipeline steps (not just final results)
- Each step includes reasoning, scores, and alternatives considered
- Gemini-style "thinking" display for NL2SQL pipeline transparency
- PipelineTrace is both a UI element and an evaluation artifact

**Prior art concern:** Medium. Streaming exists (ChatGPT), but streaming the internal reasoning of a retrieval pipeline (not just LLM tokens) is somewhat novel.

---

### Priority 2 — File Within 90 Days ($7,500)

#### Patent #13: LookML Explorer — Visual Query Capability Discovery
**Claim:** A user interface that visually presents the semantic layer's structure (explores, dimensions, measures, relationships) to help users discover what questions they can ask before asking them.

**Novel aspects:**
- Converts LookML topology into an interactive capability map
- Shows dimension-measure compatibility based on explore join structure
- "Question builder" that constructs queries from visual selection
- Reduces blank-page anxiety in conversational NL2SQL interfaces

**Prior art concern:** Medium-High. Looker's field picker and ThoughtSpot's search tokens are related. Novelty is in the conversational AI context.

#### Patent #14: Golden Dataset Evaluation Framework for NL2SQL Pipelines
**Claim:** A methodology for evaluating NL2SQL pipeline accuracy using a golden dataset with multi-dimensional scoring (intent accuracy, field selection accuracy, explore selection accuracy, SQL execution success, result correctness).

**Novel aspects:**
- Multi-dimensional scoring beyond just SQL execution success
- Separate evaluation of retrieval quality vs. generation quality
- Automated regression testing with per-component metrics

**Prior art concern:** High. NL2SQL benchmarks exist (Spider, BIRD). Novelty is limited to the semantic-layer-specific evaluation dimensions.

#### Patent #15: Adaptive Query Reformulation Based on Retrieval Confidence
**Claim:** A method for automatically reformulating user queries when the retrieval pipeline's confidence score falls below a threshold, using the scored alternatives to guide reformulation.

**Novel aspects:**
- Uses scored explore candidates to generate targeted clarification questions
- Reformulation is guided by what the system CAN answer (not generic "please rephrase")
- Near-miss candidates inform the disambiguation options presented

**Prior art concern:** Medium. Query reformulation exists in search, but guided by scored schema candidates is novel.

---

## Filing Priority Matrix

| Priority | Count | Revenue | Timeline | First Filing |
|----------|-------|---------|----------|-------------|
| P0 | 5 | $12,500 | Immediately | Patents #1–#5 |
| P1 | 7 | $17,500 | Within 30 days | Patents #6–#12 |
| P2 | 3 | $7,500 | Within 90 days | Patents #13–#15 |
| **Total** | **15** | **$37,500** | | |

## Next Steps

1. **Review with Lakshmi** — Schedule 30-min session to walk through P0 disclosures (#1–#5)
2. **Draft patent disclosures** — Use Amex's internal patent disclosure form for each
3. **Keep Abhishek in loop** — CC on all patent discussions (per Lakshmi protocol)
4. **Continue mining** — As orchestrator and UI are built, expect 5–10 more patentable ideas
5. **Track in tracking/accomplishments.md** — Each filing counts for Innovation & Influence bucket

---

## Appendix: Search Methodology

- **Google Patents:** Searched "NL2SQL schema routing", "semantic layer query routing", "explore scoring natural language", "multiplicative schema matching"
- **USPTO:** Searched Class 707 (Data Processing: Database and File Management), Class 704 (Data Processing: Speech Signal Processing, Linguistics, Language Translation)
- **Academic:** Searched ACL Anthology, arXiv cs.DB, cs.CL for NL2SQL + semantic layer papers (2022–2026)
- **Commercial:** Reviewed public documentation and patent filings from Salesforce Einstein, Google Duet AI, C3.ai, ThoughtSpot, Looker, dbt
