# ADR-006: Metric Governance Architecture

**Date:** March 10, 2026
**Status:** Proposed
**Decider:** Saheb
**Consulted:** Sulabh, Likhita, Renuka (enrichment workflow), Abhishek

---

## Decision

We will implement a **three-tier metric hierarchy** (Canonical, BU Variant, Team Derived) with the **taxonomy store as the canonical authority** that generates governed LookML. This is "Option C: Hybrid" -- the taxonomy store owns truth, LookML is a generated artifact for governed metrics, and manual LookML coexists for ungoverned fields.

This ADR documents:
1. The three-tier metric hierarchy and why it matters for retrieval accuracy
2. The extended `TaxonomyEntry` schema (from 10 fields to 17+)
3. Three sources of metric definitions and their ingestion workflows
4. The data flow between taxonomy store, LookML, AGE graph, and the AI pipeline
5. Deduplication, versioning, and the data steward workflow

---

## Context

### The Problem: Metric Chaos at Scale

Amex has 5+ PB of data across 8,000+ datasets. Business metrics -- "Active Customers," "Billed Business," "Attrition Rate" -- exist today as:

- SQL snippets in individuals' heads ("I know how to calculate that")
- Scattered across 100+ Looker dashboards with no single source of truth
- Duplicated across BUs with subtle definitional differences (Finance "Active" = $50 threshold; Premium Card Services "Active" = $100 threshold)
- Documented in Confluence pages that are stale within weeks of creation

**Why this blocks Cortex:** When a user asks "How many active customers do we have?", the AI agent must decide which `active_customers` to use. Today, `custins_customer_insights_cardmember.view.lkml` has BOTH `active_customers_standard` (billed_business > $50) and `active_customers_premium` (billed_business > $100). These are hardcoded in LookML with no metadata indicating which is the "default" or how they relate to each other.

At 3 BUs the problem is manageable. At 100+ tables across the enterprise, unstructured metric definitions are the single biggest threat to the 90%+ accuracy target.

### What Exists Today

The current `TaxonomyEntry` in `src/taxonomy/schema.py` covers 10 fields:

```
canonical_name, definition, formula, synonyms, domain, owner,
column_mappings, lookml_target, related_terms, status, filters
```

This was designed for Ayush's LookML mapping work -- mapping business terms to physical columns. It does NOT capture:

- Metric type (dimension vs. measure vs. derived ratio)
- Hierarchy (which metric is the "parent" canonical definition)
- Grain (customer-level vs. account-level vs. transaction-level)
- Time window defaults ("last 12 months" vs. "quarter-to-date")
- Versioning (what changed, when, who approved)
- Governance state beyond draft/review/approved

### Industry Precedent

This is a solved problem at companies that have invested:

| Company | System | Key Idea |
|---------|--------|----------|
| Airbnb | Minerva | Canonical metrics with dimensions, single source of truth, consumed by all tools |
| Uber | uMetric | Metric definitions with lineage, automated consistency checks |
| dbt Labs | MetricFlow | Metrics defined in YAML, semantic layer generates SQL |
| Netflix | DataJunction | Metric store as API, consumers query the store not raw tables |

All four converge on the same pattern: **a structured metric store that is the authority, with downstream tools (BI, AI, dashboards) consuming from it rather than defining their own copies.**

---

## Architecture: Three-Tier Metric Hierarchy

```
TIER 1: CANONICAL                    TIER 2: BU VARIANT                TIER 3: TEAM DERIVED
(Company-wide truth)                 (Scoped override)                 (Ephemeral, computed)

┌─────────────────────────┐          ┌─────────────────────────┐       ┌─────────────────────────┐
│ Active Customers        │          │ Active Customers        │       │ Millennial Active       │
│                         │◄─────────│ (Premium)               │       │ Premium %               │
│ canonical_name:         │ INHERITS │                         │       │                         │
│   "Active Customers"    │          │ parent: MTR-001         │       │ No governance needed.   │
│ id: MTR-001             │          │ id: MTR-002             │       │ AI constructs on-the-   │
│ tier: canonical         │          │ tier: bu_variant        │       │ fly from Tier 1+2.      │
│ formula:                │          │ formula:                │       │                         │
│   count_distinct(       │          │   count_distinct(       │       │ = Active(Premium)       │
│     cust_ref            │          │     cust_ref            │       │   WHERE gen=Millennial  │
│   ) WHERE               │          │   ) WHERE               │       │   / Total               │
│   billed_business > $50 │          │   billed_business > $100│       │   WHERE gen=Millennial  │
│ grain: customer         │          │ grain: customer         │       │                         │
│ owner: Finance          │          │ owner: Premium Card Svcs│       │ Not stored. Not         │
│ change: RFC + committee │          │ change: BU lead + review│       │ versioned. Transient.   │
│ version: 2.1.0          │          │ version: 1.0.0          │       │                         │
└─────────────────────────┘          └─────────────────────────┘       └─────────────────────────┘
         │                                      │
         │  HAS_VARIANT (AGE edge)              │
         ├──────────────────────────────────────►│
         │
         │  MAPS_TO (AGE edge)
         ├──────────────────►  (:Measure {name: "active_customers_standard"})
         │
         └──────────────────►  (:Dimension {name: "is_active_standard"})
```

### Tier 1: Canonical Metrics

**Definition:** One true definition per business concept, applicable company-wide. This is the answer when a user asks without qualifiers.

**Properties:**
- Owned by a designated team (e.g., Finance Analytics owns "Active Customers")
- Changing the formula or grain requires an RFC reviewed by the metric governance committee
- The AI agent defaults to Tier 1 when the user provides no qualifier: "How many active customers?" -> MTR-001, not MTR-002
- Each canonical metric maps to exactly one LookML measure or dimension (or generates one if it doesn't exist)

**Finance BU Examples:**

| Canonical Metric | Formula | Grain | LookML Field |
|-----------------|---------|-------|-------------|
| Active Customers | `count_distinct(cust_ref) WHERE billed_business > 50` | customer | `custins.active_customers_standard` |
| Billed Business | `sum(billed_business)` | customer | `custins.total_billed_business` |
| Accounts in Force | `sum(accounts_in_force)` | customer | `custins.total_accounts_in_force` |
| Customer Tenure | `avg(date_diff(current_date, card_setup_dt, YEAR))` | customer | `custins.avg_customer_tenure` |
| Attrition Rate | `count(cust WHERE noa='Attrited') / count(cust)` | customer | *(derived -- needs LookML)* |

### Tier 2: BU Variant Metrics

**Definition:** A scoped override of a canonical metric. Changes one or more parameters (threshold, filter, grain) while preserving the structural intent.

**Properties:**
- MUST reference a parent canonical metric via `parent_metric_id`
- Naming convention: `canonical_name + (qualifier)` -- e.g., "Active Customers (Premium)"
- The AI agent only selects a variant when the user's query contains the qualifier or context makes it unambiguous
- Change controlled by BU lead + peer review (lighter than RFC)

**Rules for what constitutes a "variant" vs. a "new canonical":**

| Change | Classification | Example |
|--------|---------------|---------|
| Different threshold, same formula | Variant | Active Customers ($100 vs. $50) |
| Different time window, same formula | Variant | Billed Business (YTD vs. trailing 12 months) |
| Different grain, same concept | Variant | Active Customers (household-level vs. customer-level) |
| Different formula entirely | New Canonical | Customer Lifetime Value (not a variant of Active Customers) |
| Same formula, different domain filter | Variant | Active Customers (International only) |

### Tier 3: Team Derived Metrics

**Definition:** Computed on-the-fly from Tier 1 and Tier 2 components. These are ratios, percentages, filtered aggregations, and cross-metric calculations.

**Properties:**
- Not stored in the taxonomy store
- Not versioned or governed
- The AI agent constructs them from the user's query using available Tier 1+2 metrics
- If a Tier 3 metric is asked for frequently (>N times/quarter), it should be promoted to Tier 1 or Tier 2

**Examples:**

| Derived Metric | Composition | How the AI Constructs It |
|---------------|-------------|------------------------|
| Millennial Active Premium % | Active Customers(Premium) WHERE gen=Millennial / Total Customers WHERE gen=Millennial | Dimension filter on `cmdl.generation` + ratio of two measures |
| Active Rate by Segment | Active Customers / Total Customers grouped by bus_seg | Two measures from custins, grouped by a dimension |
| Spend per Active Customer | Total Billed Business / Active Customers | Two canonical measures divided |
| YoY Active Customer Growth | Active Customers(current year) - Active Customers(prior year) / Active Customers(prior year) | Time-offset calculation, same canonical metric |

---

## Extended TaxonomyEntry Schema

### Current Schema (10 fields)

```python
class TaxonomyEntry(BaseModel):
    canonical_name: str          # "Active Customers"
    definition: str              # Human-readable definition
    formula: str                 # SQL-like formula
    synonyms: list[str]          # ["active CMs", "active members"]
    domain: list[str]            # ["finance", "risk"]
    owner: str                   # "Finance Analytics"
    column_mappings: list[...]   # Physical BQ columns
    lookml_target: ...           # Model/explore/field
    related_terms: list[str]     # Other canonical names
    status: str                  # draft | review | approved
    filters: list[str]           # Required filters
```

### Proposed Schema (17+ fields)

```python
class MetricType(str, Enum):
    """What kind of metric this is -- drives LookML generation."""
    DIMENSION = "dimension"          # Categorical/raw value
    MEASURE = "measure"              # Aggregation (sum, count, avg)
    DERIVED_METRIC = "derived_metric"  # Computed from other metrics
    RATIO = "ratio"                  # Metric A / Metric B
    CUMULATIVE = "cumulative"        # Running total over time


class MetricTier(str, Enum):
    """Governance tier -- determines change control process."""
    CANONICAL = "canonical"          # Company-wide, RFC required
    BU_VARIANT = "bu_variant"        # Scoped override, BU lead approval
    TEAM_DERIVED = "team_derived"    # Ephemeral, no governance


class MetricGrain(str, Enum):
    """The entity level at which this metric is computed."""
    CUSTOMER = "customer"            # cust_ref grain
    ACCOUNT = "account"              # account_id grain
    HOUSEHOLD = "household"          # household_id grain
    PORTFOLIO = "portfolio"          # business segment or product level
    TRANSACTION = "transaction"      # individual transaction


class ChangeLogEntry(BaseModel):
    """Immutable record of a change to a metric definition."""
    version: str                     # SemVer at time of change
    date: str                        # ISO 8601
    author: str
    change_type: str                 # "formula" | "description" | "threshold" | "deprecation"
    description: str                 # What changed and why


class RecommendedFilter(BaseModel):
    """A filter the AI agent should suggest but not enforce."""
    field: str                       # LookML field reference
    reason: str                      # Why this filter helps
    default_value: str = ""          # Suggested default


class TaxonomyEntry(BaseModel):
    """A governed business metric definition.

    This is the core data structure for metric governance. Every business
    metric at Amex that matters for AI-assisted analytics should have one.

    Fields marked [NEW] are additions to the current schema.
    Fields marked [CHANGED] have modified semantics.
    """

    # ---- Identity ----
    id: str                          # [NEW] Immutable. "MTR-001". Never reused.
    canonical_name: str              # "Active Customers"
    type: MetricType                 # [NEW] dimension | measure | derived_metric | ratio | cumulative
    tier: MetricTier                 # [NEW] canonical | bu_variant | team_derived

    # ---- Hierarchy ----
    parent_metric_id: str = ""       # [NEW] For BU variants: points to canonical. "" for canonicals.
    variants: list[str] = []         # [NEW] For canonicals: list of child metric IDs. [] for variants.

    # ---- Definition ----
    definition: str                  # Human-readable definition
    formula: str                     # SQL-like formula
    grain: MetricGrain               # [NEW] customer | account | household | portfolio | transaction
    default_time_window: str = ""    # [NEW] "trailing_12_months" | "ytd" | "qtd" | ""

    # ---- Discovery ----
    synonyms: list[str] = []         # ["active CMs", "active members"]
    domain: list[str] = []           # ["finance", "risk"]
    related_terms: list[str] = []    # Other canonical names

    # ---- Physical Mapping ----
    column_mappings: list[ColumnMapping] = []
    lookml_target: LookMLTarget | None = None

    # ---- Governance ----
    owner: str = ""                  # Team that owns the definition
    status: str = "draft"            # [CHANGED] draft | review | approved | deprecated
    version: str = "0.1.0"          # [NEW] SemVer. See versioning section.
    approved_by: str = ""            # [NEW] Who approved current version
    approved_date: str = ""          # [NEW] ISO 8601 date of approval
    change_log: list[ChangeLogEntry] = []  # [NEW] Immutable history

    # ---- Filters ----
    filters: list[str] = []          # Required filters (e.g., partition filters)
    recommended_filters: list[RecommendedFilter] = []  # [NEW] Suggested but not enforced
```

### Field-by-Field Comparison

| Field | Current schema.py | Proposed | Change Type |
|-------|-------------------|----------|-------------|
| `id` | -- | `str` (immutable ID) | NEW |
| `canonical_name` | `str` | `str` (unchanged) | SAME |
| `type` | -- | `MetricType` enum | NEW |
| `tier` | -- | `MetricTier` enum | NEW |
| `parent_metric_id` | -- | `str` (FK to canonical) | NEW |
| `variants` | -- | `list[str]` (child IDs) | NEW |
| `definition` | `str` | `str` (unchanged) | SAME |
| `formula` | `str` | `str` (unchanged) | SAME |
| `grain` | -- | `MetricGrain` enum | NEW |
| `default_time_window` | -- | `str` | NEW |
| `synonyms` | `list[str]` | `list[str]` (unchanged) | SAME |
| `domain` | `list[str]` | `list[str]` (unchanged) | SAME |
| `related_terms` | `list[str]` | `list[str]` (unchanged) | SAME |
| `owner` | `str` | `str` (unchanged) | SAME |
| `column_mappings` | `list[ColumnMapping]` | `list[ColumnMapping]` (unchanged) | SAME |
| `lookml_target` | `LookMLTarget` | `LookMLTarget` (unchanged) | SAME |
| `status` | `str` (draft/review/approved) | `str` (+deprecated) | CHANGED |
| `version` | -- | `str` (SemVer) | NEW |
| `approved_by` | -- | `str` | NEW |
| `approved_date` | -- | `str` (ISO 8601) | NEW |
| `change_log` | -- | `list[ChangeLogEntry]` | NEW |
| `filters` | `list[str]` | `list[str]` (unchanged) | SAME |
| `recommended_filters` | -- | `list[RecommendedFilter]` | NEW |

**Migration:** All existing `TaxonomyEntry` YAML files remain valid. New fields have defaults. The schema evolution is fully backward-compatible. A migration script adds `id`, `type`, `tier`, and `grain` based on the existing `lookml_target` and `formula` content.

---

## Three Sources of Metric Definitions

Metrics don't appear from nowhere. There are exactly three pathways by which a metric enters the taxonomy store, each with a different workflow and different actors.

### Source 1: SQL Query Log Mining

**What:** Extracting metric definitions from the patterns in existing SQL queries against BigQuery.

**Workflow:**

```
BigQuery Audit Logs (90-day window)
    │
    ├──► Extract SELECT/GROUP BY/WHERE patterns
    │       (Batch job, Animesh)
    │
    ├──► Cluster similar queries (embedding similarity)
    │       (Automated, weekly)
    │
    ├──► Surface top-N clusters without canonical definitions
    │       (Report to governance committee)
    │
    ├──► SME review: "Is this a real metric or ad-hoc exploration?"
    │       (Domain expert, manual)
    │
    └──► If real metric:
            ├──► Draft TaxonomyEntry (LLM-assisted from SQL pattern)
            ├──► Steward review + enrichment
            └──► Approval chain (see Data Steward Workflow)
```

**Who does what:**
| Actor | Responsibility |
|-------|---------------|
| Animesh | Build and run the SQL pattern extraction batch job |
| LLM (Gemini) | Cluster similar queries, propose draft definitions from SQL |
| Domain SME | Validate: "Yes, this is 'Active Customers' calculated this way" |
| Data Steward | Formalize into TaxonomyEntry, add synonyms, set grain |
| Governance Committee | Approve as Canonical or classify as BU Variant |

**Example:** Query log mining finds 47 queries in Finance BU that all compute `COUNT(DISTINCT cust_ref) WHERE billed_business > 50`. LLM proposes: "This appears to be 'Active Customers' with a $50 threshold." Domain SME confirms. Steward creates MTR-001.

### Source 2: Tribal Knowledge (SME Interviews)

**What:** Business metrics that exist only in people's heads, PowerPoints, and verbal agreements.

**Workflow:**

```
SME Interview / Business Requirements Doc
    │
    ├──► Structured intake form (web form via Renuka's UX)
    │       Fields: name, what it measures, how it's calculated,
    │       who uses it, how often, known variants
    │
    ├──► LLM-assisted structuring
    │       (Convert free-text description → formula + grain + synonyms)
    │
    ├──► Deduplication check (see Deduplication Strategy)
    │       "This looks 89% similar to existing MTR-001"
    │
    ├──► If duplicate: link as synonym or variant
    │    If new: create draft TaxonomyEntry
    │
    └──► Approval chain
```

**Who does what:**
| Actor | Responsibility |
|-------|---------------|
| SME (Business user) | Fill out intake form with metric knowledge |
| Data Steward | Review form, validate formula, assign grain and domain |
| LLM (Gemini) | Auto-suggest formula from description, flag potential duplicates |
| Governance Committee | Approve if Canonical; BU lead approves if Variant |

**Example:** A VP mentions in a strategy meeting: "We track 'card activation rate' -- percentage of issued cards with a transaction in first 90 days." Steward captures this, LLM structures it as `count_distinct(cust_ref WHERE first_txn_date <= card_setup_dt + 90) / count_distinct(cust_ref)`, steward assigns `grain: customer`, `type: ratio`, `domain: [risk, acquisition]`.

### Source 3: Enrichment (Bare LookML --> Governed Metric)

**What:** LookML fields that exist in views but lack structured governance. This is the most common source -- we already have 52 fields in 7 Finance BU views.

**Workflow:**

```
Existing LookML View (e.g., custins_customer_insights_cardmember.view.lkml)
    │
    ├──► Parse LookML (lkml parser, automated)
    │       Extract: field name, type, label, description, sql
    │
    ├──► LLM-assisted enrichment
    │       "This measure total_billed_business appears to calculate
    │        sum of billed_business. Suggested definition:
    │        'Total spend charged to all card members...'"
    │
    ├──► Steward review via Renuka's enrichment UX
    │       Accept/edit LLM suggestion, add synonyms, set tier/grain
    │
    ├──► Deduplication check against existing TaxonomyEntries
    │
    ├──► Create TaxonomyEntry linking back to LookML field
    │       lookml_target: {model: "finance",
    │                       explore: "finance_cardmember_360",
    │                       field: "custins.total_billed_business"}
    │
    └──► Once governed, future LookML for this field is GENERATED
         from the TaxonomyEntry (not hand-edited)
```

**Who does what:**
| Actor | Responsibility |
|-------|---------------|
| Ayush | Creates initial LookML views (current workstream) |
| LLM (Gemini) | Proposes enriched descriptions, synonyms, grain from SQL/label |
| Data Steward | Reviews via Renuka's UX, approves enrichments |
| Automation | Generates updated LookML description from `to_lookml_description()` |

**This is the intersection with Renuka's workstream.** Her enrichment UX is the primary interface for Source 3. The contract: her UX writes structured data, our pipeline consumes it.

---

## Where Truth Lives: Option C (Hybrid)

We evaluated three options for where metric truth resides:

| Option | Description | Drawback |
|--------|-------------|----------|
| **A: LookML is truth** | All metadata lives in LookML files, AI reads LookML | No structured governance, no hierarchy, limited to what LookML can express |
| **B: Store is truth** | Taxonomy store owns everything, LookML is 100% generated | Too aggressive -- breaks existing ungoverned LookML, blocks Ayush's current work |
| **C: Hybrid** | Store is truth for governed metrics, manual LookML coexists | Complexity of two sources -- mitigated by clear separation |

**We choose Option C.**

### Data Flow

```
                           ┌─────────────────────────────────────────┐
                           │         TAXONOMY STORE                   │
                           │         (Source of Truth)                 │
                           │                                          │
                           │  Phase 1: YAML files in Git              │
                           │  Phase 2: PostgreSQL metrics table       │
                           │  Phase 3: DataHub/Collibra API           │
                           │                                          │
                           │  ┌────────────────────────────────────┐  │
                           │  │  MTR-001: Active Customers         │  │
                           │  │  MTR-002: Active Customers (Prem)  │  │
                           │  │  MTR-003: Billed Business          │  │
                           │  │  ...                               │  │
                           │  └────────────────────────────────────┘  │
                           └──────┬──────────────┬───────────────┬────┘
                                  │              │               │
                    ┌─────────────┘              │               └────────────┐
                    │                            │                            │
                    ▼                            ▼                            ▼
        ┌───────────────────┐      ┌──────────────────────┐     ┌─────────────────────┐
        │ LOOKML GENERATION │      │ RETRIEVAL STORES      │     │ GOLDEN QUERIES       │
        │                   │      │                       │     │                      │
        │ Governed fields:  │      │ pgvector:             │     │ FAISS:               │
        │  description,     │      │  embed(definition +   │     │  generate test       │
        │  label, synonyms  │      │  synonyms + formula)  │     │  queries from        │
        │  are GENERATED    │      │                       │     │  canonical metrics   │
        │  from store       │      │ AGE graph:            │     │                      │
        │                   │      │  :CanonicalMetric     │     │  "What is total      │
        │ Ungoverned fields:│      │  :BUVariant           │     │   billed business    │
        │  manual LookML    │      │  -[:HAS_VARIANT]->    │     │   for Gen X?"        │
        │  stays as-is      │      │  -[:MAPS_TO]->        │     │                      │
        └───────┬───────────┘      └──────────┬───────────┘     └──────────┬──────────┘
                │                              │                            │
                ▼                              ▼                            ▼
        ┌───────────────────┐      ┌──────────────────────┐     ┌─────────────────────┐
        │ LOOKER            │      │ CORTEX RETRIEVAL      │     │ CORTEX EVALUATION    │
        │ (SQL generation)  │      │ (Field discovery)     │     │ (Accuracy testing)   │
        │                   │      │                       │     │                      │
        │ Reads LookML,     │      │ Vector + Graph +      │     │ Golden dataset       │
        │ generates SQL     │      │ Few-shot fusion       │     │ runner               │
        │ deterministically │      │                       │     │                      │
        └───────────────────┘      └──────────────────────┘     └─────────────────────┘
                │                              │                            │
                └──────────────┬───────────────┘                            │
                               ▼                                            │
                    ┌──────────────────────┐                                │
                    │ AI AGENT (ADK)        │◄───────────────────────────────┘
                    │                       │
                    │ Retrieval tells agent │
                    │ WHICH fields.         │
                    │ Looker MCP generates  │
                    │ SQL.                  │
                    │ Golden queries        │
                    │ validate accuracy.    │
                    └──────────────────────┘
```

### How Governed vs. Ungoverned Fields Coexist

```
custins_customer_insights_cardmember.view.lkml

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  # ---- GOVERNED (generated from taxonomy store) ----              │
│  # DO NOT EDIT BELOW THIS LINE -- managed by cortex/scripts/       │
│  #        generate_lookml.py from taxonomy YAML                    │
│                                                                     │
│  measure: active_customers_standard {                              │
│    description: "Count of card members with billed business        │
│      greater than $50, the standard active customer threshold.     │
│      Also known as: active count, active CMs, active member count. │
│      Calculation: count_distinct(cust_ref) WHERE billed_business   │
│      > 50. Note: Requires filter on partition_date."               │
│    ...                                                             │
│  }                                                                 │
│                                                                     │
│  # ---- UNGOVERNED (manual, Ayush-maintained) ----                 │
│                                                                     │
│  dimension: age35andover {                                         │
│    description: "Y or N flag indicating if the card member is      │
│      age 35 or older."                                             │
│    ...                                                             │
│  }                                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Rules:**
1. A field is "governed" once a TaxonomyEntry with status=approved exists and has a `lookml_target` pointing to it
2. Governed fields have their `description`, `label`, and `group_label` regenerated from the TaxonomyEntry on every sync
3. Ungoverned fields are left untouched -- manual edits are preserved
4. The generation script (`generate_lookml.py`) uses section markers to separate governed from ungoverned blocks
5. A field can transition from ungoverned to governed when a steward creates and approves a TaxonomyEntry for it

---

## Deduplication Strategy

Metric duplication is the entropy that governance fights. Without active deduplication, the taxonomy store will accumulate variants that are actually the same metric with different names.

### At Entry Time: Semantic Similarity Gate

Before a steward can create a new TaxonomyEntry, the system checks for duplicates:

```
New Entry Draft
    │
    ├──► Embed (canonical_name + definition + formula + synonyms)
    │
    ├──► Search existing TaxonomyEntries via pgvector
    │       similarity threshold: 0.80
    │
    ├──► If similarity > 0.80:
    │       "This looks similar to MTR-001: Active Customers (92% match).
    │        Is this a variant? Or the same metric with different phrasing?"
    │       Options: [Create as Variant of MTR-001] [Create as New Canonical] [Cancel]
    │
    └──► If similarity < 0.80:
            Proceed with new entry creation
```

### Mandatory Parent for BU Variants

A BU Variant (`tier: bu_variant`) cannot be saved without a valid `parent_metric_id`. The system enforces:

- Parent must exist and have `tier: canonical`
- Parent must have `status: approved`
- The variant's `formula` must be structurally related to the parent's (warning if completely different)

### Expiration Policy for Unused Metrics

Metrics that are never queried accumulate like dead code:

| Metric Status | No Usage For | Action |
|--------------|-------------|--------|
| `approved` | 6 months | Flag for review: "This metric has no queries. Still needed?" |
| `approved` | 12 months | Auto-transition to `deprecated` with notification to owner |
| `deprecated` | 6 months | Archive: remove from retrieval indexes, retain in store for audit |

"Usage" means: the metric's LookML field appears in a Looker query, OR the AI agent selected it in response to a user query.

### Quarterly Governance Audit

The governance committee (domain leads + data stewards) reviews:

1. **New canonicals** created since last audit -- validate they aren't duplicates
2. **Orphan variants** -- BU variants whose parent was deprecated
3. **High-usage Tier 3** -- derived metrics that should be promoted to Tier 1/2
4. **Cross-BU inconsistencies** -- same metric name, different formulas across BUs
5. **Synonym collisions** -- different metrics claiming the same synonym

---

## How This Feeds the AI Pipeline

The extended TaxonomyEntry is not just a governance artifact -- it directly improves retrieval accuracy. Here is how each new field feeds the AI pipeline.

### Priority Ranking: Which Fields Matter Most for Accuracy

| Field | Impact on Retrieval | How It's Used |
|-------|-------------------|---------------|
| `tier` | **Critical** | Determines default when user is ambiguous. Canonical > BU Variant > Derived. |
| `grain` | **Critical** | Prevents joining incompatible grains (customer-level metric with transaction-level dimension). |
| `synonyms` | **High** | Each synonym becomes a separate embedding row in pgvector for broader coverage. |
| `parent_metric_id` | **High** | When user says "active customers" and context suggests Premium card, agent can traverse to MTR-002. |
| `type` | **High** | Drives whether the agent selects a dimension, measure, or computes a ratio. |
| `formula` | **Medium** | Embedded alongside definition for semantic matching on calculation patterns. |
| `default_time_window` | **Medium** | Injects sensible time filters when user doesn't specify ("trailing 12 months" as default). |
| `recommended_filters` | **Medium** | Agent suggests these after initial results: "Would you like to filter by business segment?" |
| `version` | **Low** | Surfaced to user only when relevant: "Note: Active Customers definition changed in v2.0 (Jan 2026)." |

### Synonyms as Separate Embedding Rows

Current approach: synonyms are concatenated into the `content` string that gets embedded.

```
"active_customers_standard is a measure (count_distinct)...
 Also known as: active count, active CMs, active member count."
```

**Proposed enhancement:** In addition to the concatenated description, create separate embedding rows for each synonym:

```sql
-- Row 1: Primary description (existing)
INSERT INTO field_embeddings (field_key, content, ...)
VALUES ('finance...active_customers_standard',
        'active_customers_standard is a measure (count_distinct)...',
        ...);

-- Row 2: Synonym embedding (NEW)
INSERT INTO field_embeddings (field_key, content, ...)
VALUES ('finance...active_customers_standard.syn.active_count',
        'active count: Count of card members with billed business > $50...',
        ...);

-- Row 3: Another synonym (NEW)
INSERT INTO field_embeddings (field_key, content, ...)
VALUES ('finance...active_customers_standard.syn.active_cms',
        'active CMs: Count of active card members...',
        ...);
```

**Why:** A user searching for "active CMs" gets a direct embedding match rather than depending on the synonym being close enough to the full description in embedding space. At 17 business terms with ~5 synonyms each, this adds ~85 rows to pgvector -- negligible cost, meaningful recall improvement.

### HAS_VARIANT Edges in AGE Graph

New edge type in the graph schema:

```sql
-- New node types
(:CanonicalMetric {id, canonical_name, tier, grain, formula, version})
(:BUVariant {id, canonical_name, tier, grain, formula, qualifier})

-- New edges
(:CanonicalMetric)-[:HAS_VARIANT {qualifier, override_field, override_value}]->(:BUVariant)
(:CanonicalMetric)-[:MAPS_TO]->(:Measure|:Dimension)
(:BUVariant)-[:MAPS_TO]->(:Measure|:Dimension)

-- Existing edges still apply
(:BusinessTerm)-[:MAPS_TO]->(:Dimension|:Measure)
```

**Query: Disambiguate "active customers"**

```sql
SELECT * FROM cypher('lookml_schema', $$
  MATCH (cm:CanonicalMetric)-[:HAS_VARIANT]->(v:BUVariant)
  WHERE cm.canonical_name =~ '(?i).*active customer.*'
  RETURN cm.canonical_name AS canonical,
         cm.formula AS canonical_formula,
         v.canonical_name AS variant_name,
         v.formula AS variant_formula,
         v.id AS variant_id
$$) AS (canonical agtype, canonical_formula agtype,
        variant_name agtype, variant_formula agtype, variant_id agtype);
```

**Result:**
```
canonical: "Active Customers"
canonical_formula: "count_distinct(cust_ref) WHERE billed_business > 50"
variant_name: "Active Customers (Premium)"
variant_formula: "count_distinct(cust_ref) WHERE billed_business > 100"
variant_id: "MTR-002"
```

The agent can now present: "I found two definitions of 'Active Customers.' The standard definition uses a $50 threshold; the Premium definition uses $100. Which would you like?"

### Golden Queries Generated from Canonical Metrics

Each canonical metric auto-generates a set of golden queries for the evaluation corpus:

```
Canonical Metric: MTR-001 (Active Customers)
    │
    ├──► "How many active customers do we have?"
    │       explore: finance_cardmember_360
    │       measures: [custins.active_customers_standard]
    │       filters: {partition_date: "last 12 months"}
    │
    ├──► "What is the active customer count by generation?"
    │       dimensions: [cmdl.generation]
    │       measures: [custins.active_customers_standard]
    │
    ├──► "Show me active customers by business segment for Q4"
    │       dimensions: [custins.bus_seg]
    │       measures: [custins.active_customers_standard]
    │       filters: {partition_date: "Q4 2025"}
    │
    └──► "How has the active customer count trended over the last year?"
            dimensions: [custins.partition_date]
            measures: [custins.active_customers_standard]
            filters: {partition_date: "last 12 months"}
```

For N canonical metrics with M template patterns, this generates N x M golden queries automatically. With 20 canonical metrics and 4 templates, that is 80 golden queries -- a significant contribution to Animesh's golden dataset.

---

## Versioning

### SemVer for Metric Definitions

Every TaxonomyEntry carries a `version` field following [Semantic Versioning](https://semver.org):

```
MAJOR.MINOR.PATCH
  │      │     │
  │      │     └──► Metadata fix (typo in description, tag change)
  │      │          No impact on query results. Silent update.
  │      │
  │      └──────► Additive change (new synonym, description enrichment,
  │               new recommended_filter). No impact on existing queries.
  │               AI agent does NOT surface to user.
  │
  └─────────────► Breaking change (formula change, grain change, threshold
                  change, deprecation). May change query results.
                  AI agent SURFACES to user when relevant.
```

**Examples:**

| Version Change | Trigger | What Changed | Agent Behavior |
|---------------|---------|-------------|----------------|
| 1.0.0 -> 1.0.1 | Patch | Fixed typo: "custoemrs" -> "customers" | Silent |
| 1.0.1 -> 1.1.0 | Minor | Added synonyms: "active CMs", "active cardmembers" | Silent |
| 1.1.0 -> 2.0.0 | Major | Threshold changed from $50 to $25 | "Note: The Active Customers definition was updated on 2026-02-15. The threshold changed from $50 to $25." |
| 2.0.0 -> 2.0.0-deprecated | Deprecation | Replaced by MTR-005 | "Note: 'Active Customers (Legacy)' is deprecated. The current definition is MTR-005." |

### Version Conflict Resolution

When a BU Variant's parent canonical is updated:

```
MTR-001 (Active Customers) v1.0 -> v2.0 (threshold $50 -> $25)
    │
    ├──► MTR-002 (Active Customers Premium) still says "billed_business > $100"
    │    No conflict -- variant overrides threshold, parent change irrelevant.
    │
    ├──► MTR-003 (Active Customers International) inherits threshold from parent
    │    CONFLICT -- variant was tracking parent's threshold.
    │    Notification sent to MTR-003 owner: "Parent changed. Review variant."
    │
    └──► All golden queries referencing MTR-001 are flagged for re-validation
```

---

## Data Steward Workflow

### Five Core Activities

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  DEFINE  │───►│  REVIEW  │───►│  ENRICH  │───►│DEPRECATE │    │ARBITRATE │
│          │    │          │    │          │    │          │    │          │
│ Create   │    │ Peer     │    │ Add      │    │ Phase    │    │ Resolve  │
│ draft    │    │ review   │    │ synonyms,│    │ out old  │    │ conflict │
│ metric   │    │ formula  │    │ context, │    │ metrics  │    │ between  │
│ entry    │    │ accuracy │    │ examples │    │ safely   │    │ competing│
│          │    │          │    │          │    │          │    │ defs     │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

**1. Define:** Create a new TaxonomyEntry from any of the three sources. LLM assists by pre-filling fields from SQL patterns, descriptions, or existing LookML. Steward validates and corrects.

**2. Review:** Peer review of the definition, formula, grain, and tier classification. For canonicals, this includes the governance committee. For variants, BU lead + one peer.

**3. Enrich:** Post-approval enrichment -- adding synonyms discovered from user queries, refining descriptions based on how users actually describe the metric, adding recommended filters based on common query patterns.

**4. Deprecate:** Mark a metric as deprecated with a replacement pointer. The AI agent stops recommending it but can still explain it if asked. Golden queries referencing it are flagged. After 6 months, archived.

**5. Arbitrate:** When two BUs have conflicting definitions for the same metric name, the governance committee arbitrates: one becomes the canonical, the other becomes a BU variant, or both are renamed to be unambiguous.

### Approval Chain

```
  DRAFT                    REVIEW                   APPROVED
    │                        │                         │
    │  Steward creates       │  Peer reviews           │  Ready for
    │  or LLM drafts         │  formula + grain        │  AI consumption
    │                        │                         │
    ├────────────────────────►├─────────────────────────►│
    │                        │                         │
    │  Tier 1 (canonical):   │  Tier 1: Domain lead    │  Tier 1: Committee
    │  Any steward           │  + 1 peer steward       │  sign-off
    │                        │                         │
    │  Tier 2 (variant):     │  Tier 2: BU lead        │  Tier 2: BU lead
    │  Any steward           │                         │  approval
    │                        │                         │
    │  Metadata-only change: │  Self-approve           │  Auto-approved
    │  (synonym, description)│  (logged)               │  (patch version)
```

### Non-Technical UX Requirements

Data stewards are domain experts, not engineers. The UX (Renuka's enrichment tool) must support:

| Requirement | Implementation |
|-------------|---------------|
| Form-based entry | No YAML editing. Structured form with dropdowns for `type`, `tier`, `grain`. |
| LLM-assisted drafting | "Describe this metric in plain English" -> LLM generates `formula`, suggests `grain`, proposes `synonyms`. |
| Preview before commit | Show the generated LookML description, the graph edges that will be created, and the embedding that will be stored. |
| Diff view for changes | When editing an approved metric, show what changed and what version bump this implies. |
| Duplicate warning | Real-time similarity check as the steward types the canonical name and definition. |
| Bulk import | Upload a spreadsheet of metrics (for initial migration from existing docs). |

---

## Consequences

### Positive

- **Retrieval accuracy improves:** Structured tier + grain metadata prevents the AI agent from selecting the wrong "active customers" or joining incompatible grains. This directly impacts the 90%+ accuracy target.
- **Disambiguation becomes systematic:** Instead of relying on LLM judgment to pick between `active_customers_standard` and `active_customers_premium`, the hierarchy provides deterministic rules (default to canonical, use variant when qualifier present).
- **Golden queries scale automatically:** Each canonical metric generates evaluation test cases, reducing Animesh's manual workload and keeping the golden dataset in sync with the metric catalog.
- **LookML quality improves:** Generated descriptions are richer, more consistent, and always include synonyms -- boosting vector search recall without manual effort.
- **Audit trail:** `change_log` and `version` provide full history for compliance. When a metric's numbers change, you can trace why.

### Negative

- **Schema complexity increases:** From 10 fields to 17+. More fields means more validation, more migration, more things to get wrong. Mitigated by backward-compatible defaults on all new fields.
- **Dual-source LookML:** Governed and ungoverned fields coexisting in the same file creates confusion about which fields can be hand-edited. Mitigated by clear section markers and the generation script refusing to touch ungoverned blocks.
- **Governance overhead:** Quarterly audits, approval chains, and deduplication checks take time. At 3 BUs this is lightweight. At enterprise scale, the committee becomes a bottleneck without tooling support.
- **Dependency on Renuka's UX:** Source 3 (enrichment) requires Renuka's steward interface. If her timeline slips, stewards fall back to YAML editing in Git -- functional but not user-friendly.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Stewards don't adopt: too much friction to create entries | Medium | High | LLM-assisted drafting reduces effort to 2-3 minutes per metric. Start with high-value canonical metrics only. |
| Governance committee becomes bottleneck | Low (at 3 BUs) | High (at scale) | Phase 2 introduces API-driven approval with async review. Committee meets monthly, not per-metric. |
| Taxonomy store and LookML drift apart | Medium | High | CI check: every LookML deploy validates that governed fields match their TaxonomyEntry. Drift = build failure. |
| Over-governance: teams create Tier 3 metrics to avoid the process | Medium | Medium | Monitor Tier 3 usage. If >30% of queries use unstructured derived metrics, the governance bar is too high. |
| Renuka's UX diverges from the TaxonomyEntry schema | Low | Medium | The Pydantic schema IS the contract. Her UX must produce valid TaxonomyEntry JSON. Validate at the API boundary. |

---

## Implementation Plan

### Phase 1: Now through May 2026 (3 BUs, 100+ tables)

**Storage:** YAML files in `cortex/taxonomy/` directory, validated by extended `TaxonomyEntry` Pydantic schema.

**Governance:** Manual -- stewards edit YAML, PRs reviewed by Saheb or domain lead. No committee yet (too few metrics to warrant one).

**Scope:**
- Extend `src/taxonomy/schema.py` with all new fields (backward-compatible)
- Write migration script to add `id`, `type`, `tier`, `grain` to existing YAML entries
- Create 15-25 canonical metrics for Finance BU (from existing 17 business terms + measures)
- Create 5-10 BU variants for known split definitions
- Build `generate_lookml.py` to regenerate governed LookML descriptions from YAML
- Add `:CanonicalMetric` and `:BUVariant` node types + `:HAS_VARIANT` edges to AGE graph loader
- Implement synonym-per-row embedding enhancement in pgvector loader

**Deliverables:**
| What | Owner | Timeline |
|------|-------|----------|
| Extended schema.py | Saheb | Week 1 |
| Migration script | Ravikanth | Week 1-2 |
| Finance BU canonical metrics (YAML) | Ayush + domain SME | Week 2-4 |
| generate_lookml.py | Ravikanth | Week 2-3 |
| AGE graph loader update (HAS_VARIANT) | Likhita / Rajesh | Week 3-4 |
| Synonym embedding rows | Likhita / Rajesh | Week 3-4 |
| Golden query auto-generation | Animesh | Week 4-5 |

### Phase 2: June-September 2026 (10+ BUs)

**Storage:** PostgreSQL `metrics` table alongside pgvector. YAML files become the import/export format, not the runtime store.

```sql
CREATE TABLE metrics (
    id              TEXT PRIMARY KEY,       -- "MTR-001"
    canonical_name  TEXT NOT NULL,
    type            TEXT NOT NULL,          -- enum: dimension, measure, ...
    tier            TEXT NOT NULL,          -- enum: canonical, bu_variant
    parent_id       TEXT REFERENCES metrics(id),
    definition      TEXT NOT NULL,
    formula         TEXT,
    grain           TEXT NOT NULL,
    domain          TEXT[],
    owner           TEXT,
    status          TEXT DEFAULT 'draft',
    version         TEXT DEFAULT '0.1.0',
    synonyms        TEXT[],
    approved_by     TEXT,
    approved_date   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_metrics_parent ON metrics(parent_id);
CREATE INDEX idx_metrics_status ON metrics(status);
CREATE INDEX idx_metrics_tier ON metrics(tier);
```

**Governance:** Renuka's UX writes to the metrics API. Approval workflow moves from PR-based to form-based. Quarterly audits begin.

**Scope:**
- Metrics REST API (FastAPI, deployed alongside Cortex)
- Renuka's UX integration (API contract defined by `TaxonomyEntry` schema)
- Automated deduplication check at create time
- Usage tracking (which metrics are queried, how often)
- CI validation: governed LookML fields must match metrics table

### Phase 3: October 2026+ (Enterprise)

**Storage:** Evaluate integration with enterprise data governance tools (Collibra, DataHub, Atlan).

**Scope:**
- If Amex adopts Collibra/DataHub, the metrics table becomes a sync target
- Cortex reads from the enterprise tool's API instead of its own PostgreSQL table
- The TaxonomyEntry schema remains the internal contract -- the integration layer maps between external format and our schema
- Taxonomy store becomes a cache/index of the enterprise source of truth

---

## Appendix A: Complete TaxonomyEntry YAML Example

Full "Active Customers" canonical metric with all 17 fields populated:

```yaml
# taxonomy/mtr-001-active-customers.yaml
id: "MTR-001"
canonical_name: "Active Customers"
type: "measure"
tier: "canonical"

parent_metric_id: ""
variants:
  - "MTR-002"   # Active Customers (Premium)

definition: >
  Count of unique card members whose billed business exceeds $50
  in the reporting period. This is the standard company-wide definition
  of an active customer. Used across Finance, Risk, and Marketing BUs
  for portfolio health assessment.

formula: "count_distinct(cust_ref) WHERE billed_business > 50"

grain: "customer"
default_time_window: "trailing_12_months"

synonyms:
  - "active count"
  - "active CMs"
  - "active card members"
  - "active member count"
  - "active cardmembers"
  - "customers who spend"

domain:
  - "finance"
  - "risk"
  - "marketing"

related_terms:
  - "Billed Business"
  - "Customer Tenure"
  - "Accounts in Force"

column_mappings:
  - table: "custins_customer_insights_cardmember"
    column: "billed_business"
    dataset: "dw"

lookml_target:
  model: "finance"
  explore: "finance_cardmember_360"
  field: "custins_customer_insights_cardmember.active_customers_standard"

owner: "Finance Analytics"
status: "approved"
version: "2.1.0"
approved_by: "Finance Domain Lead"
approved_date: "2026-02-15"

change_log:
  - version: "1.0.0"
    date: "2025-10-01"
    author: "Finance Analytics"
    change_type: "formula"
    description: "Initial canonical definition. Threshold set at $50 based on historical portfolio analysis."
  - version: "2.0.0"
    date: "2026-01-15"
    author: "Finance Analytics"
    change_type: "formula"
    description: "Updated threshold from $50 to $25 for broader inclusion. Reverted after VP pushback."
  - version: "2.1.0"
    date: "2026-02-15"
    author: "Finance Analytics"
    change_type: "description"
    description: "Restored $50 threshold. Added clarifying note about reporting period. Added 3 new synonyms."

filters:
  - "partition_date"

recommended_filters:
  - field: "custins_customer_insights_cardmember.bus_seg"
    reason: "Active customer counts vary significantly by business segment (CPS vs. OPEN vs. Commercial)"
    default_value: ""
  - field: "custins_customer_insights_cardmember.partition_date"
    reason: "Always scope to a time period to avoid full-table scan"
    default_value: "last 12 months"
```

**Corresponding BU Variant:**

```yaml
# taxonomy/mtr-002-active-customers-premium.yaml
id: "MTR-002"
canonical_name: "Active Customers (Premium)"
type: "measure"
tier: "bu_variant"

parent_metric_id: "MTR-001"
variants: []

definition: >
  Count of unique card members whose billed business exceeds $100
  in the reporting period. This is the stricter/premium threshold used
  by Premium Card Services for high-value customer segmentation.

formula: "count_distinct(cust_ref) WHERE billed_business > 100"

grain: "customer"
default_time_window: "trailing_12_months"

synonyms:
  - "premium active customers"
  - "high-activity customers"
  - "active customers 2"
  - "premium active count"

domain:
  - "finance"
  - "premium_card_services"

related_terms:
  - "Active Customers"
  - "Billed Business"

column_mappings:
  - table: "custins_customer_insights_cardmember"
    column: "billed_business"
    dataset: "dw"

lookml_target:
  model: "finance"
  explore: "finance_cardmember_360"
  field: "custins_customer_insights_cardmember.active_customers_premium"

owner: "Premium Card Services"
status: "approved"
version: "1.0.0"
approved_by: "PCS Domain Lead"
approved_date: "2026-03-01"

change_log:
  - version: "1.0.0"
    date: "2026-03-01"
    author: "Premium Card Services"
    change_type: "formula"
    description: "Initial definition. $100 threshold established for premium customer segmentation."

filters:
  - "partition_date"

recommended_filters:
  - field: "custins_customer_insights_cardmember.card_prod_id"
    reason: "Premium metrics are most meaningful when scoped to premium card products"
    default_value: ""
```

---

## Appendix B: Industry References

### Airbnb Minerva (2021)

Minerva is Airbnb's metric computation and serving platform. Key design choices that informed this ADR:

- **Single source of truth:** Every metric has one canonical definition in Minerva. Dashboards, experiments, and ML models all consume from it.
- **Dimensions are first-class:** A metric isn't just a formula -- it includes the dimensions it can be sliced by, the grain it operates at, and the time window it defaults to.
- **Certification levels:** Metrics are "certified" (equivalent to our "canonical") or "uncertified" (equivalent to "team derived").

**What we took:** The tier system, the concept of grain as a first-class field, the idea that the AI agent should default to certified metrics.

### Uber uMetric (2022)

Uber's metric platform for consistent metric definitions across 4,000+ microservices.

- **Metric ownership:** Every metric has a team owner. Changes require owner approval.
- **Lineage tracking:** uMetric tracks which upstream tables and transformations feed each metric.
- **Consistency checks:** Automated validation that two metrics claiming to measure the same thing produce the same results.

**What we took:** The ownership and approval model, the change_log as an immutable record.

### dbt MetricFlow (2023)

dbt Labs' semantic layer for defining metrics in YAML:

- **Metrics as code:** Defined in YAML alongside dbt models, version-controlled.
- **Semantic types:** simple (single measure), derived (ratio/calculation of other metrics), cumulative (running total).
- **Joins are implicit:** MetricFlow resolves join paths automatically from entity relationships.

**What we took:** The MetricType enum (our `type` field mirrors their semantic types), YAML-first definition approach for Phase 1.

### Netflix DataJunction (2024)

Netflix's metric store that serves as an API layer between metric definitions and downstream consumers.

- **Metric store as API:** Consumers query the metric store, not raw tables. The store resolves to SQL.
- **Multiple downstream engines:** Same metric definition serves dashboards, ML pipelines, ad-hoc analysis.
- **Versioned definitions:** Each metric has a version, with breaking changes requiring consumer acknowledgment.

**What we took:** The API-driven Phase 2 design, the versioning strategy (SemVer for metrics), the concept that the store is consumed by multiple downstream systems (retrieval, LookML generation, golden queries).

---

## Open Questions

| Question | Owner | Deadline | Impact |
|----------|-------|----------|--------|
| Should `grain` be enforced at query time (reject incompatible grain combinations) or advisory (warn but allow)? | Saheb | Sprint 3 | Determines structural validation gate behavior |
| How does `default_time_window` interact with Looker's `always_filter`? Does the agent inject it, or does LookML handle it? | Saheb + Ayush | Sprint 3 | Determines if time window is AI logic or LookML logic |
| What is the ID format? Sequential (`MTR-001`) vs. content-addressable (hash of canonical_name + domain)? | Saheb | Sprint 2 | Sequential is simpler; content-addressable prevents accidental duplicates |
| Should Renuka's UX validate against our Pydantic schema directly, or define its own schema with a mapping layer? | Saheb + Renuka | Sprint 3 | Direct validation = tighter coupling but guaranteed compatibility |
| At what usage threshold should a Tier 3 metric be auto-promoted to Tier 2? | Governance Committee | Phase 2 | Too low = governance overhead; too high = missed standardization opportunities |
