# ADR-008: Filter Value Resolution — Self-Improving Learning Loop

**Status:** Proposed
**Date:** March 11, 2026
**Decision Makers:** Saheb, Abhishek
**Reviewers:** Sulabh, Ashok, Lakshmi, Architecture Board
**Extends:** ADR-007 (Filter Value Resolution — Auto-Extracted Value Catalog)

---

## Context

ADR-007 established the auto-extracted value catalog and three-pass deterministic resolution (exact → fuzzy → synonym). This ADR addresses two open questions from ADR-007:

1. **Where do synonyms come from at scale?** ADR-007's `FILTER_VALUE_MAP` contains ~40 manually curated mappings. At 10 BUs with ~200 coded dimensions, manual curation doesn't scale.
2. **How does the system improve over time?** ADR-007's synonym list is static. There is no mechanism for the system to learn from failed resolutions.

### Industry Landscape — Nobody Has Fully Solved This

We researched every major NL2Data product and found no complete solution:

| Product | Filter Value Resolution | Learning Mechanism | Limitation |
|---------|----------------------|-------------------|------------|
| **Snowflake Cortex Analyst** | Sample values in YAML (manual). Cortex Search for high-cardinality. | Verified Query Repository — human Accept/Edit/Dismiss. Never auto-approved. | No value-level synonym learning. Operates at query level. |
| **ThoughtSpot SearchIQ** | Users "Teach" synonyms via click. Immediate persistence. | Single-user teaching. No confirmation gate. | One wrong teaching poisons the system. No multi-user validation. |
| **Power BI Q&A** | Admin-curated synonym lists via tooling UI. Copilot can suggest synonyms from column names. | Admin-only. No user-initiated learning. | Being retired Dec 2026. No organic learning. |
| **Tableau Ask Data** | Hardcoded synonyms for field names/values. Fuzzy matching (1 char diff). | None — admin-curated only. | Retired Feb 2024. Never persisted user selections. |
| **Databricks AI/BI Genie** | Unity Catalog comments + sample values. Verified answers. | Similar to Snowflake verified queries. | No value-level synonym learning. |
| **Google Conv. Analytics API** | RAG over Dataplex metadata. LLM-inferred. | None — "add filters during agent creation" (hardcoded). | Developers on Google forums report inability to reliably apply filters. |
| **Alation** | AI-powered glossary auto-suggests terms. Crowdsourcing with steward review. | Closest to our approach — ML suggests, steward reviews. | Operates at business term → column level, not value level. |
| **RubikSQL (Alibaba, 2025)** | LLM-generated synonyms via DAAC index. | LLM-bootstrapped, no user-initiated learning. Hierarchical merge for conflicts. | No multi-user confirmation. No feedback from failed resolutions. |

**Key finding:** Google's own Conversational Analytics API does not solve filter value resolution. Their guidance is "hardcode filters at agent creation." This validates that our approach addresses a genuinely unsolved problem at the platform level.

### Academic State-of-the-Art

| Paper | Venue | Relevance | Gap vs. Our Approach |
|-------|-------|-----------|---------------------|
| **Sphinteract** | VLDB 2025 | SRA paradigm for disambiguation via clarification questions | Schema-level ambiguity only, not value-level. No persistent learning. |
| **AmbiSQL** | arXiv Aug 2025 | Fine-grained ambiguity taxonomy including "unclear value reference" | Detection + per-session resolution. No accumulated synonym learning. |
| **Continual Learning from Human Feedback in Text-to-SQL** | arXiv Nov 2025 | Hybrid memory model (episodic/procedural/declarative) for learning from corrections | Feedback at SQL level (whole query), not value level. Closest architectural analog. |
| **RubikSQL** | arXiv 2025 | Lifelong learning NL2SQL with Unified Knowledge Format including synonyms | LLM-generated synonyms, not user-learned. No steward validation. DAAC index is interesting. |
| **Spider-Syn** | ACL 2021 | Proves NL2SQL models break on synonym substitution | The foundational "why" — motivates deterministic synonym matching. |
| **"NL2SQL is a solved problem... Not!"** | CIDR 2024, Microsoft + Waii.ai | Value grounding as core unsolved challenge. 14% of queries have inherent ambiguity. | Identifies the problem; does not propose a persistent learning solution. |
| **HILDA 2025 (SIGMOD Workshop)** | HILDA 2025 | Past user feedback improves text-to-SQL by up to 14.9% | Conversation-level feedback pairs, not value-level synonym mappings. |

**The gap in literature:** Every system either (a) learns at the query level, not the value level, (b) allows single-user teaching without confirmation, or (c) requires admin-only curation. No system combines user-initiated value-level synonym learning with multi-user confirmation and steward governance.

---

## Decision Drivers

- **The synonym bottleneck is the scalability constraint.** Data extraction scales automatically (`APPROX_TOP_COUNT`). Deterministic matching scales trivially. But synonym curation is the only component that requires human knowledge — "OPEN" means "small business" is Amex domain knowledge that exists nowhere in the data itself.
- **Manual curation must be a one-time cost, not an ongoing burden.** Each BU onboarding can tolerate 30 minutes of steward effort. Monthly synonym maintenance cannot exceed 1-2 hours total.
- **Wrong synonyms in financial data have high blast radius.** "SMB" resolving to "GCS" instead of "OPEN" means wrong financial reports. The confirmation gate is non-negotiable in a regulated enterprise.
- **The system must work on day one.** Cold-start bootstrapping must produce a functional synonym set before any user has interacted with the system.

---

## Options Considered

### Option A: Manual Curation Only (Current — ADR-007 Baseline)

**Description:** Stewards manually add synonyms to the `dimension_value_catalog.synonyms` array. No automated learning.

**Pros:**
- Simple, auditable, no surprises
- Full steward control over every mapping

**Cons:**
- Does not improve from failed resolutions
- Steward must anticipate every possible user phrasing upfront (impossible)
- New user terms require someone to notice the failure and manually add the synonym

**Effort:** Zero additional development. Ongoing steward burden: high (estimated 3-5 hours/week at 3 BUs).
**Reversibility:** N/A (this is the default state)

### Option B: Simple Count-Based Auto-Approval

**Description:** When a resolution fails, the user is shown candidate values and selects one. The system logs this as a synonym suggestion. After N distinct users select the same mapping (e.g., N=3), the synonym is auto-promoted to active status.

**Pros:**
- Dead simple — one `UPDATE SET status='approved' WHERE occurrence_count >= N`
- Easy to explain to architecture board and compliance
- Deterministic — no probabilistic reasoning

**Cons:**
- Ignores base rate. If 100 users see "SMB" and only 3 select "OPEN" (3% selection rate), that is weak evidence, not strong. But count-based auto-approval treats 3/3 the same as 3/100.
- Fixed threshold doesn't adapt. New BUs with fewer users need lower thresholds; popular queries need higher.
- No mechanism for conflicting mappings ("SMB" → "OPEN" by 3 users, "SMB" → "GCS" by 2 users).

**Effort:** Small (schema + simple UPDATE trigger)
**Reversibility:** Easy

### Option C: Bayesian Confidence with Steward Governance (Recommended)

**Description:** Three-phase lifecycle:

**Phase 1 — Cold-Start Bootstrap (BU onboarding):**
Auto-extract values from BQ → LLM generates synonym suggestions per coded value → steward reviews/corrects → load into value catalog. One-time cost per BU.

**Phase 2 — Steward-Gated Learning (v1, <100 users):**
Failed resolutions → user selects correct value → logged as synonym suggestion with `times_selected` and `times_shown` → all suggestions go to steward queue for approval. Simple and safe during pilot.

**Phase 3 — Bayesian Auto-Approval (scale, 100+ users):**
Track both positive signals (user selects this mapping) and negative signals (user was shown this mapping but chose something else). Compute Wilson score confidence interval. Auto-approve when lower bound exceeds threshold (0.8). Route ambiguous or conflicting mappings to steward queue.

**Pros:**
- Mathematically principled — Wilson score handles small samples correctly
- Naturally handles conflicting feedback — 7/10 approval rate produces lower confidence than 7/7
- Adapts to volume — requires more evidence before high-confidence decisions
- Reduces steward burden at scale (only edge cases need review)
- Full audit trail (every suggestion, every approval, every rejection logged)

**Cons:**
- More complex than simple counting (but only ~20 lines of additional Python)
- Requires tracking "shown but not selected" events (the denominator)
- Phase 3 may feel like a black box to non-technical stewards

**Effort:** Medium
**Reversibility:** Easy — disable Phase 3 auto-approval, revert to Phase 2 steward-only

---

## Decision

**Chosen option: Option C — Bayesian Confidence with Steward Governance**

**Rationale:**

Option A doesn't scale beyond 1 BU — stewards cannot anticipate every user phrasing. Option B's fixed threshold ignores base rate and cannot handle conflicting mappings. Option C starts simple (Phase 2 = steward-gated, identical to Option A) and adds intelligence only when volume justifies it (Phase 3). The phased approach means zero risk at launch with a clear upgrade path.

The Wilson score confidence interval is the standard approach for small-sample proportion estimation — it is used by Reddit for comment ranking, Amazon for review scoring, and Stack Overflow for answer quality. It is well-understood, well-tested, and appropriate for our sample sizes (5-50 confirmations per synonym).

---

## Design

### Enhanced Schema (Instrumenting for Phase 3 from Day 1)

```sql
-- Replaces synonym_suggestions from ADR-007
CREATE TABLE synonym_suggestions (
    id              SERIAL PRIMARY KEY,
    user_term       TEXT NOT NULL,           -- "small businesses" (raw user phrase)
    matched_value   TEXT NOT NULL,           -- "OPEN" (BQ value user selected)
    dimension_name  TEXT NOT NULL,           -- "bus_seg"
    view_name       TEXT NOT NULL,           -- "custins_customer_insights_cardmember"
    times_selected  INT DEFAULT 1,           -- users who selected this mapping
    times_shown     INT DEFAULT 1,           -- users who were shown this as candidate
    distinct_users  INT DEFAULT 1,           -- unique users who selected this
    confidence      FLOAT DEFAULT 0.0,       -- Wilson lower bound (computed on update)
    status          TEXT DEFAULT 'pending',   -- pending | approved | rejected | conflict
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    reviewed_by     TEXT,
    UNIQUE (user_term, matched_value, dimension_name)
);

CREATE INDEX idx_ss_status ON synonym_suggestions (status);
CREATE INDEX idx_ss_term ON synonym_suggestions (user_term);
```

**Key addition vs. ADR-007:** `times_shown` column. Without it, you cannot compute meaningful confidence because you don't know the denominator. 3 selections out of 3 showings is different from 3 selections out of 100 showings.

### Value-Level Embedding (Pass 4 — New)

ADR-007 defined three resolution passes: exact → fuzzy → synonym. This ADR adds a fourth:

```sql
-- Extend dimension_value_catalog with embeddings
ALTER TABLE dimension_value_catalog ADD COLUMN
    value_embedding vector(768);  -- embedding of enriched value description

-- Example: for bus_seg = "OPEN"
-- Embedding text: "OPEN small business SMB open card business segment"
-- This text is auto-generated from:
--   1. The raw value itself ("OPEN")
--   2. The dimension description mentioning this value
--   3. Any existing synonyms
--   4. LLM-generated context from cold-start bootstrap
```

**Pass 4 — Embedding Match:** When passes 1-3 fail, compute cosine similarity between the embedded user term and all `value_embedding` vectors for the candidate dimensions. This handles creative phrasings that are semantically related but don't match any exact/fuzzy/synonym pattern.

```python
# Pass 4: Semantic match (only if passes 1-3 miss)
EMBED_MATCH_QUERY = """
SELECT dimension_name, raw_value, display_label,
       1 - (value_embedding <=> %s::vector) AS similarity
FROM dimension_value_catalog
WHERE dimension_name = ANY(%s)
  AND value_embedding IS NOT NULL
ORDER BY value_embedding <=> %s::vector
LIMIT 5;
"""
```

**Scale:** ~250 rows × 768 dims × 4 bytes = ~768 KB at 3 BUs. Trivial.

### The Learning Loop — Complete Flow

```
USER: "show me spend for SMBs"
       │
       ▼
ENTITY EXTRACTION (LLM):
  filter_terms: ["SMBs"]
       │
       ▼
VECTOR SEARCH (pgvector):
  "SMBs" → candidate_dimensions: [bus_seg, business_org]
       │
       ▼
VALUE CATALOG RESOLUTION:
  Pass 1 (exact):   SELECT WHERE LOWER(raw_value) = 'smbs'     → MISS
  Pass 2 (fuzzy):   SELECT WHERE levenshtein(val, 'smbs') ≤ 2  → MISS
  Pass 3 (synonym): SELECT WHERE 'smbs' = ANY(synonyms)        → MISS
  Pass 4 (embed):   SELECT ... ORDER BY embedding <=> embed('smbs')
                     → bus_seg.OPEN (0.82), bus_seg.CPS (0.71)  → MISS (below threshold)
       │
       ▼ ALL PASSES FAILED
       │
DISAMBIGUATION UI:
  "I found these values for business segment. Which did you mean?"
  ┌──────────────────────────────────────────┐
  │  ○ OPEN  — Small Business                │
  │  ○ CPS   — Consumer Personal Services    │
  │  ○ GCS   — Global Commercial Services    │
  │  ○ GMNS  — Global Merchant Network       │
  │  ○ None of these                         │
  └──────────────────────────────────────────┘
       │
       ▼ USER SELECTS "OPEN"
       │
LOG SUGGESTION:
  INSERT INTO synonym_suggestions
    (user_term, matched_value, dimension_name, view_name, times_selected, times_shown)
  VALUES ('smbs', 'OPEN', 'bus_seg', 'custins...', 1, 1)
  ON CONFLICT (user_term, matched_value, dimension_name)
  DO UPDATE SET
    times_selected = times_selected + 1,
    times_shown = times_shown + 1,
    distinct_users = distinct_users + 1,
    confidence = wilson_lower(times_selected + 1, times_shown + 1),
    updated_at = NOW();
       │
       ▼ MEANWHILE, QUERY PROCEEDS WITH bus_seg = "OPEN"
       │
       ▼ OVER TIME...

USER 2: "SMBs" → same flow → selects "OPEN" → times_selected=2, times_shown=2
USER 3: "SMBs" → same flow → selects "OPEN" → times_selected=3, times_shown=3
       │
       ▼ PHASE 2 (v1): Steward reviews weekly queue
       │  Steward sees: "SMBs" → OPEN (bus_seg), 3 users, 100% selection rate
       │  Steward clicks APPROVE
       │
       ▼ PHASE 3 (scale): Wilson lower bound at 3/3 = 0.44
       │  Not enough for auto-approve (threshold 0.8).
       │  After 10/10: Wilson lower = 0.74. Still goes to steward.
       │  After 15/15: Wilson lower = 0.82. AUTO-APPROVED.
       │
       ▼ SYNONYM PROMOTED TO VALUE CATALOG
       │
UPDATE dimension_value_catalog
SET synonyms = array_append(synonyms, 'smbs')
WHERE dimension_name = 'bus_seg' AND raw_value = 'OPEN';

NEXT USER: "SMBs" → Pass 3 (synonym) → INSTANT MATCH → bus_seg = "OPEN"
```

### Cold-Start Bootstrap Process

```python
def bootstrap_synonyms_for_bu(
    bq_client,
    pg_conn,
    llm_client,    # SafeChain Gemini Flash
    view_configs: list[dict],
    steward_email: str,
):
    """One-time BU onboarding. ~30 min total (mostly steward review time).

    1. Auto-extract distinct values from BQ (APPROX_TOP_COUNT)
    2. Identify coded dimensions (where values are opaque: "OPEN", "CPS", etc.)
    3. For coded dimensions, call LLM to generate synonym suggestions:
       Prompt: "Given dimension '{dim_name}' with description '{desc}'
                and values {values}, suggest 3-5 business-friendly synonyms
                for each value. Output as JSON."
    4. Load suggestions into synonym_suggestions with status='llm_suggested'
    5. Email steward with review link
    6. Steward approves/rejects/edits each suggestion (10-15 min)
    7. Approved synonyms loaded into dimension_value_catalog.synonyms array

    Cost estimate:
      - BQ extraction: ~$0.15 per BU
      - LLM calls: ~$0.05 per BU (small prompts)
      - Steward time: ~15 min per BU
      - Total: $0.20 + 15 min human time
    """
    ...
```

### Handling Conflicting Mappings

When the same user term maps to different values across different users:

```python
def handle_conflict(pg_conn, user_term: str, dimension_name: str):
    """Detect and handle conflicting synonym suggestions.

    Conflict: "active" → card_status="A" (5 users) AND
              "active" → acct_status="ACTIVE" (3 users)

    Resolution:
    1. If different dimensions: BOTH are valid (context-dependent).
       Store both. At resolution time, candidate_dimensions from
       vector search disambiguates.
    2. If same dimension, different values: CONFLICT.
       Route to steward with frequency context.
       Never auto-approve conflicting mappings.
    """
    suggestions = query("""
        SELECT matched_value, times_selected, times_shown, confidence
        FROM synonym_suggestions
        WHERE user_term = %s AND dimension_name = %s AND status != 'rejected'
        ORDER BY times_selected DESC
    """, (user_term, dimension_name))

    if len(suggestions) > 1:
        # Same dimension, different values = true conflict
        update_status(user_term, dimension_name, status='conflict')
        notify_steward(user_term, dimension_name, suggestions)
        return

    # Different dimensions = context-dependent, both valid
    # Vector search candidate_dimensions will disambiguate at runtime
```

### Wilson Score Confidence Function

```python
import math

def wilson_lower_bound(positive: int, total: int, z: float = 1.96) -> float:
    """Compute lower bound of Wilson score 95% confidence interval.

    Used by Reddit, Amazon, Stack Overflow for small-sample ranking.

    Args:
        positive: Number of positive signals (times_selected).
        total: Total trials (times_shown).
        z: Z-score for confidence level (1.96 = 95%).

    Returns:
        Lower bound of confidence interval [0.0, 1.0].
        Higher = more confident that the true proportion is high.

    Examples:
        wilson_lower(3, 3)   = 0.44  (too few samples, low confidence)
        wilson_lower(10, 10) = 0.74  (more data, approaching threshold)
        wilson_lower(15, 15) = 0.82  (exceeds 0.8 threshold → auto-approve)
        wilson_lower(7, 10)  = 0.42  (3 disagreements → low confidence)
    """
    if total == 0:
        return 0.0

    p_hat = positive / total
    denominator = 1 + z * z / total
    center = p_hat + z * z / (2 * total)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * total)) / total)

    return (center - spread) / denominator
```

### Phase Transition Rules

| Phase | Condition | Approval Mechanism | Steward Burden |
|-------|-----------|-------------------|----------------|
| Phase 1 | BU onboarding | LLM-bootstrapped, steward validates all | ~15 min per BU (one-time) |
| Phase 2 | <100 active users | All suggestions go to steward queue | ~1-2 hrs/week |
| Phase 3 | ≥100 active users AND synonym queue > 20/week | Wilson lower > 0.8 AND distinct_users ≥ 5 → auto-approve. Conflicts always to steward. | ~30 min/week (edge cases only) |

**Phase transition is manual** — Saheb or Abhishek explicitly enables Phase 3 when volume justifies it. There is no automatic escalation.

---

## Scale Analysis

### Synonym Growth Projection

| Timeline | Seed Synonyms | Learned Synonyms | Total | Resolution Coverage |
|----------|--------------|------------------|-------|-------------------|
| Day 0 (onboarding) | ~60 (3 BUs × ~20 coded mappings) | 0 | ~60 | ~80% of filter terms |
| Month 1 | 60 | ~150 (from user selections) | ~210 | ~92% |
| Month 3 | 60 | ~500 | ~560 | ~97% |
| Month 6 | 60 | ~1,200 | ~1,260 | ~99% |
| Month 12 | 60 | ~2,000 (plateau — most terms seen) | ~2,060 | ~99.5% |

**Plateau reasoning:** Natural language has finite ways to express the same concept. After 2,000 learned synonyms across ~250 dimension values, nearly every user phrasing has been seen. The growth rate drops exponentially as coverage approaches 100%.

### Steward Burden Projection

| Phase | Monthly Synonym Suggestions | Steward Time/Week | Auto-Approved |
|-------|---------------------------|-------------------|---------------|
| Month 1 (Phase 2) | ~150 new suggestions | ~2 hrs | 0% (all manual) |
| Month 3 (Phase 2) | ~100 (declining — more terms resolved) | ~1.5 hrs | 0% |
| Month 6 (Phase 3 enabled) | ~50 (mostly edge cases) | ~30 min | ~70% |
| Month 12 (Phase 3 mature) | ~10 (plateau) | ~10 min | ~90% |

### Storage

All negligible:

| Component | Rows (3 BUs) | Rows (10 BUs) | Size |
|-----------|-------------|---------------|------|
| dimension_value_catalog | ~250 | ~1,000 | <5 MB |
| value_embeddings (768d) | ~250 | ~1,000 | <3 MB |
| synonym_suggestions (all-time) | ~2,000 | ~8,000 | <1 MB |

---

## Consequences

### Positive
- System improves from every failed resolution — flywheel effect
- Steward burden decreases over time as coverage approaches 100%
- Cold-start bootstrap produces functional synonyms before any user interaction
- Bayesian confidence prevents premature auto-approval from small samples
- Full audit trail for compliance (every suggestion, approval, rejection logged)
- Conflicting mappings surface automatically for human review

### Negative
- Phase 3 (Bayesian auto-approval) adds mathematical complexity that non-technical stewards may not understand
- Requires UI for disambiguation ("which value did you mean?") — Ayush must build this
- `times_shown` tracking requires client-side instrumentation (must fire event when user sees but doesn't select a candidate)

### Neutral
- Phase 2 is identical to manual curation but with user-initiated suggestions — zero behavior change for stewards
- Phase 3 is optional and manually enabled — can stay in Phase 2 indefinitely if volume is low

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Adversarial synonym injection (user deliberately maps "revenue" → wrong value) | Low | High | Multi-user confirmation + steward gate. Single user cannot create a synonym alone. |
| Conflicting mappings overwhelm steward queue | Medium | Medium | Conflict detection auto-groups related suggestions. Context-dependent mappings (different dimensions) are not conflicts. |
| Wilson score threshold too high (synonyms never auto-approved) | Medium | Low | Monitor approval rates. If Phase 3 auto-approves <30% of suggestions, lower threshold from 0.8 to 0.7. |
| Users don't engage with disambiguation UI (just retype query differently) | Medium | Medium | Track disambiguation_shown vs disambiguation_selected rates. If <30% engagement, consider inline suggestions instead of modal. |
| LLM-bootstrapped synonyms are wrong and steward misses errors | Low | High | Bootstrap generates suggestions with status='llm_suggested' (distinct from 'pending'). Steward sees the source. Flag coded dimensions for extra scrutiny. |

---

## Validation Plan

**Success criteria:**
- Filter resolution coverage ≥ 95% by month 3 (measured: resolved / total filter terms)
- Synonym suggestion accuracy ≥ 90% (measured: approved / (approved + rejected) from steward queue)
- Steward review time ≤ 2 hours/week at Phase 2
- False positive synonyms (approved but wrong) < 1% (measured via golden dataset regression)
- Zero auto-approved synonyms that are later rejected by steward (Phase 3 safety check)

**Timeline:**
- Sprint 1 (March): Phase 1 cold-start bootstrap for Finance BU. Seed ~20 synonyms.
- Sprint 2 (April): Phase 2 learning enabled. Measure suggestion volume and accuracy.
- Sprint 3 (May): Evaluate Phase 3 readiness. Enable if >100 users and >20 suggestions/week.

**What would trigger reconsidering:**
- If steward queue exceeds 50 suggestions/week before Phase 3 is ready → fast-track Phase 3
- If Wilson score auto-approval produces >2% false positives → disable Phase 3, revert to Phase 2
- If user engagement with disambiguation UI is <20% → redesign UI or switch to implicit feedback (track which queries succeed after retry)

---

## Novelty Assessment

### What Exists (Prior Art)

| Component | Prior Art |
|-----------|-----------|
| Auto-extracting dimension values from DB | Snowflake sample_values; Dataplex profiling |
| Three-pass resolution (exact/fuzzy/synonym) | Tableau Ask Data fuzzy matching; Power BI linguistic schema |
| Learned synonyms from user corrections | ThoughtSpot "Teach" (single-user, no confirmation) |
| LLM-bootstrapped synonym generation | RubikSQL (Alibaba) DAAC index |
| Steward-reviewed synonym queue | Alation business glossary |
| Wilson score for ranking | Reddit, Amazon, Stack Overflow |

### What Is Novel (No Direct Prior Art Found)

The specific combination does not exist in any system, academic or commercial:

1. **Value-level synonym learning from failed resolution with multi-user confirmation.** Every existing system learns at the query level (Snowflake) or from single users (ThoughtSpot).
2. **Auto-extracted value catalog + deterministic four-pass resolution + learning feedback loop.** Individual components exist. The full pipeline does not.
3. **LLM-bootstrapped cold start with steward validation → user-driven organic growth → Bayesian auto-approval.** A three-phase synonym lifecycle. No existing system implements this.
4. **Graph-structural candidate narrowing for filter disambiguation.** Using vector search results to constrain which dimensions are searched in the value catalog, validated by graph structural checks. Architecturally unique.

**Patent disclosure drafted separately — see `cortex/patents/001-self-improving-filter-resolution.md`.**

---

## Related Decisions

- **ADR-007** (Filter Value Resolution): This ADR extends ADR-007 with the learning loop mechanism. ADR-007 remains the base architecture; this ADR adds the self-improvement layer.
- **ADR-005** (Intent & Entity Classification): Entity extraction outputs `filter_terms` (raw phrases). The learning loop logs failed `filter_terms` → user selections.
- **ADR-004** (Semantic Layer Representation): Value embeddings (Pass 4) use the same pgvector instance and embedding model as field embeddings.
- **ADR-006** (Metric Governance): Steward workflow for synonym review integrates with the existing enrichment approval process.

---

## References

### Academic
- Sphinteract, VLDB 2025 — Disambiguation via clarification questions
- AmbiSQL, arXiv Aug 2025 — Ambiguity taxonomy for NL2SQL
- Continual Learning from Human Feedback, arXiv Nov 2025 — Hybrid memory model
- RubikSQL, arXiv 2025 (Alibaba) — Lifelong learning NL2SQL with synonym templates
- Spider-Syn, ACL 2021 — Synonym substitution breaks NL2SQL
- "NL2SQL is a solved problem... Not!", CIDR 2024 — Value grounding as unsolved challenge
- HILDA 2025, SIGMOD Workshop — User feedback improves text-to-SQL by 14.9%
- Interactive Text-to-SQL via Expected Information Gain, arXiv Jul 2025

### Industry
- Snowflake Cortex Analyst: Verified Query Repository & Cortex Search
- ThoughtSpot SearchIQ: "Teach" feature
- Power BI Q&A: Linguistic schema & synonym management
- Alation: AI-powered business glossary with crowdsourcing
- Coveo: Automatic Relevance Tuning (behavioral synonym detection)
- Google Conversational Analytics API (filter limitations confirmed via developer forums)

### Statistical Methods
- Wilson Score Confidence Interval — standard for small-sample proportion estimation
