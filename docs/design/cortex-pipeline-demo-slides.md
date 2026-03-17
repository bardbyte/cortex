# Cortex Pipeline — Demo Walkthrough (2 Slides)

**Audience:** Kalyan, Jeff, Abhishek | **Tone:** "Here's what the AI actually does — step by step."

---

## SLIDE 1: The Pipeline — From Question to SQL in 5 Steps

```
 USER ASKS: "What is the total billed business for the OPEN segment?"
 ─────────────────────────────────────────────────────────────────────

 STEP 1                          STEP 2                           STEP 3
 INTENT CLASSIFICATION           SEMANTIC SEARCH                  EXPLORE SCORING
 ~~~~~~~~~~~~~~~~~~~~~~~~~~      ~~~~~~~~~~~~~~~~~~~~~~~~~~       ~~~~~~~~~~~~~~~~~~~~~~~~~~
 Gemini 2.5 Flash analyzes       Extracts entities + embeds       Scores 5 candidate data
 the question:                   with BGE-large → searches        sources using structural
                                 pgvector (1024-dim vectors)      LookML signals:
 Intent:  data_query
 Metrics: ["total billed         ┌─────────────────────────┐      score = coverage³
           business"]            │ "total billed business"  │            × mean_similarity
 Dims:    ["segment"]            │    ↓ embed (80ms)        │            × base_view_bonus
 Filters: [{segment: "OPEN"}]   │    ↓ pgvector search     │            × desc_sim_bonus
 Time:    null                   │    → 0.96 similarity     │            × filter_penalty
                                 │    → total_billed_       │
 ~300ms                          │      business_amt        │      Winner:
                                 └─────────────────────────┘      finance_cardmember_360
                                                                  Score: 0.544
                                 ~250ms                            Confidence: 54%

                                                                   ~50ms
 ─────────────────────────────────────────────────────────────────────

 STEP 4                                        STEP 5
 FILTER RESOLUTION                             SQL GENERATION
 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~         ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
 5-pass cascade resolves user filters          Builds augmented prompt with resolved
 to exact Looker values:                       fields → Looker MCP generates SQL:

 User said: "OPEN"                             SELECT
   Pass 1: Exact match ✓ (conf: 1.0)            segment,
   → segment = 'OPEN'                            SUM(billed_business)
                                                   AS total_billed_business
 Auto-injected (governance rule):              FROM custins_customer_insights
   → partition_date = last 90 days             WHERE segment = 'OPEN'
     (Finance Data Office policy)                AND partition_date
                                                   BETWEEN DATE_SUB(CURRENT_DATE(),
 Total: 1 resolved, 1 mandatory                   INTERVAL 90 DAY)
                                                   AND CURRENT_DATE()
 ~0ms (computed in Step 2)                     GROUP BY 1

                                               ~500ms (Looker MCP)
 ─────────────────────────────────────────────────────────────────────

 TOTAL PIPELINE: ~1.2 seconds  │  Streamed via SSE — user sees each step animate in real time
```

### The Decision Gates — When the AI Stops and Asks

```
                              ┌──────────────────┐
                              │  Entity Extraction │
                              │  (Step 1)          │
                              └────────┬───────────┘
                                       │
                              ┌────────▼───────────┐
                              │  All similarities   │──── YES ───→  CLARIFY
                              │  below 0.70?        │               "I can't find fields
                              └────────┬───────────┘                matching your question"
                                       │ NO
                              ┌────────▼───────────┐
                              │  No explores found? │──── YES ───→  NO MATCH
                              │                     │               "No data source covers
                              └────────┬───────────┘                this combination"
                                       │ NO
                              ┌────────▼───────────┐
                              │  Runner-up within   │──── YES ───→  DISAMBIGUATE
                              │  85% of winner?     │               "Did you mean X or Y?"
                              └────────┬───────────┘
                                       │ NO
                              ┌────────▼───────────┐
                              │     PROCEED         │
                              │  Generate SQL with  │
                              │  top-scoring explore│
                              └─────────────────────┘
```

---

## SLIDE 2: The Math — How the AI Picks the Right Data Source

### The Scoring Formula

```
 ┌────────────────────────────────────────────────────────────────────┐
 │                                                                    │
 │   SCORE  =  coverage³  ×  mean_sim  ×  base_view  ×  desc_sim    │
 │                                         bonus        bonus        │
 │                                                                    │
 │             ×  filter_penalty                                      │
 │                                                                    │
 └────────────────────────────────────────────────────────────────────┘

 Each factor serves a specific purpose:

 ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
 │ COVERAGE³            │  │ MEAN SIMILARITY      │  │ BASE VIEW BONUS     │
 │                      │  │                      │  │ (P1 Signal)         │
 │ How many of the      │  │ How close are the    │  │ Does the explore    │
 │ user's entities      │  │ vector matches?      │  │ OWN the fields?     │
 │ does this explore    │  │                      │  │                     │
 │ cover?               │  │ BGE embedding        │  │ Measures: 2× weight │
 │                      │  │ cosine similarity    │  │ Dimensions: 1×      │
 │ CUBIC = harsh:       │  │ per entity           │  │                     │
 │ 100% → 1.00          │  │                      │  │ Range: 1.0× – 2.0×  │
 │  80% → 0.51          │  │ Range: 0.0 – 1.0     │  │                     │
 │  50% → 0.13          │  │                      │  │ Only counts if      │
 │  33% → 0.04          │  │                      │  │ similarity ≥ 0.65   │
 └─────────────────────┘  └─────────────────────┘  └─────────────────────┘

 ┌─────────────────────┐  ┌─────────────────────┐
 │ DESC SIM BONUS       │  │ FILTER PENALTY       │
 │ (P2 Tiebreaker)     │  │ (P4 Signal)          │
 │                      │  │                      │
 │ How well does the    │  │ Does the explore     │
 │ explore's description│  │ support the user's   │
 │ match the query?     │  │ filter dimensions?   │
 │                      │  │                      │
 │ Formula:             │  │ matched / total      │
 │ 1.0 + 0.2 × sim     │  │ Floor: 0.1           │
 │                      │  │ (prevents zeroing)   │
 │ Range: 1.0× – 1.2×  │  │                      │
 │ Subtle but decisive  │  │ Range: 0.1 – 1.0     │
 │ for close races      │  │                      │
 └─────────────────────┘  └─────────────────────┘
```

### Worked Example: "Total billed business for OPEN segment"

```
 Entities extracted:
   E1: "total billed business"  (measure, weight 1.0)
   E2: "segment"                (dimension, weight 1.0)
   F1: "OPEN"                   (filter on segment)

 ┌─────────────────────────────┬──────────┬──────────┬──────────┬──────────┬──────────┬────────┐
 │ Explore                      │ Coverage³│ Mean Sim │ Base View│ Desc Sim │ Filter   │ SCORE  │
 ├─────────────────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┼────────┤
 │ finance_cardmember_360      │ 1.000    │ 0.91     │ 1.45     │ 1.08     │ 1.0      │ 0.544  │ ◄ WINNER
 │ finance_merchant_profit     │ 0.125    │ 0.72     │ 1.00     │ 1.04     │ 0.1      │ 0.009  │
 │ finance_travel_sales        │ 0.125    │ 0.68     │ 1.00     │ 1.02     │ 0.1      │ 0.009  │
 │ finance_card_issuance       │ 0.037    │ 0.44     │ 1.00     │ 1.01     │ 0.1      │ 0.002  │
 │ finance_customer_risk       │ 0.037    │ 0.38     │ 1.00     │ 1.00     │ 0.1      │ 0.001  │
 └─────────────────────────────┴──────────┴──────────┴──────────┴──────────┴──────────┴────────┘

 Winner: finance_cardmember_360 (0.544)
 Runner-up: 0.009 → ratio = 0.009/0.544 = 0.017 → NOT near-miss → PROCEED
```

### The 5-Pass Filter Resolution Cascade

```
 User says: "OPEN"  →  Which exact value in the database?

 ┌─────────────────────────────────────────────────────────────────┐
 │                                                                 │
 │  PASS 1: EXACT MATCH          conf: 1.00                       │
 │  "open" in value_map? ───────── YES ──→ "OPEN" ✓ DONE         │
 │                          │                                      │
 │                          NO                                     │
 │                          ↓                                      │
 │  PASS 2: SYNONYM EXPANSION    conf: 0.85                       │
 │  "open" in synonym_map? ────── YES ──→ resolved value ✓        │
 │                          │                                      │
 │                          NO                                     │
 │                          ↓                                      │
 │  PASS 3: FUZZY MATCH          conf: 0.50–0.85                  │
 │  Levenshtein ≤ 2? ──────────── YES ──→ closest match ✓        │
 │  (min input length: 3)  │                                      │
 │                          NO                                     │
 │                          ↓                                      │
 │  PASS 4: EMBEDDING SIMILARITY (planned — not yet implemented)  │
 │                          │                                      │
 │                          ↓                                      │
 │  PASS 5: PASSTHROUGH          conf: 0.30                       │
 │  Use value as-is ─────────────── → raw value sent to Looker    │
 │                                                                 │
 └─────────────────────────────────────────────────────────────────┘

 PLUS: Mandatory partition filter auto-injected
 ┌──────────────────────────────────────────────────┐
 │  partition_date = "last 90 days"                  │
 │  Source: Finance Data Office governance rule      │
 │  Confidence: 1.00 (policy, not guesswork)        │
 └──────────────────────────────────────────────────┘
```

### Why This Design Works at Scale

```
 TODAY                              JUNE 2026 TARGET
 ─────────────────────────         ─────────────────────────
 5 explores                        50+ explores
 1 BU (Finance)                    3 BUs
 ~80% routing accuracy             90%+ accuracy

 What scales:
 ┌──────────────────────────────────────────────────────────┐
 │ ✓ Multiplicative formula — adding explores doesn't       │
 │   degrade existing accuracy (no shared weights)          │
 │                                                          │
 │ ✓ Base-view signal — LookML structure does the routing,  │
 │   not hand-tuned rules                                   │
 │                                                          │
 │ ✓ Enrichment-driven — data stewards add synonyms,        │
 │   descriptions, filters → accuracy improves without      │
 │   code changes                                           │
 │                                                          │
 │ ✓ Near-miss detection — system asks instead of guessing  │
 │   when it's unsure (0.85 threshold)                      │
 │                                                          │
 │ ✓ Filter governance — partition rules are policy,         │
 │   injected automatically. No full-table scans.           │
 └──────────────────────────────────────────────────────────┘
```

---

*Generated for Kalyan demo — March 2026*
