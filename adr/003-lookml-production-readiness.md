# ADR-003: LookML Production Readiness Checklist

**Date:** March 6, 2026
**Status:** Accepted
**Decider:** Saheb
**Consulted:** Sulabh, Ayush

---

## Decision

Every LookML project (view, explore, model) MUST pass a mandatory production readiness checklist before deployment. The checklist enforces a 4-layer BigQuery cost optimization strategy, AI-retrieval readiness, and structural correctness.

## Context

At 5+ PB across 8,000+ datasets, an unfiltered BigQuery query can scan terabytes and cost $50-100+ per execution. When the Cortex AI agent generates queries via Looker MCP, it can trigger hundreds of queries per day. Without guardrails baked into the LookML itself, a single misconfigured explore can burn through cloud budget in hours.

The Finance BU LookML (7 views, 5 explores, 1 model) was our first production implementation. During development, we discovered that cost control cannot be delegated to the AI agent or to user discipline — it must be **structurally enforced in LookML**. Looker's `sql_always_where`, `always_filter`, and `conditionally_filter` provide this enforcement at the semantic layer, before any SQL reaches BigQuery.

This ADR codifies the strategy we developed for Finance BU into a reusable checklist for every subsequent BU onboarding.

## The 4-Layer Cost Optimization Strategy

### Layer 1: `sql_always_where` — Hard Ceiling (Invisible)

**What:** A hidden WHERE clause injected into every query on the explore. Users cannot see, modify, or remove it.

**Purpose:** Absolute last line of defense. Even if all other filters are misconfigured, this prevents full table scans.

**Standard:**
```lookml
sql_always_where:
  ${explore_alias.partition_raw} >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY) ;;
```

**Rules:**
- Every explore on a partitioned table MUST have a `sql_always_where` referencing the partition column
- Maximum window: 365 days (adjustable per BU if justified)
- Uses `_raw` timeframe for direct date comparison (avoids Looker date filter parsing)
- Reference tables (<10K rows) are exempt

### Layer 2: `always_filter` — Mandatory Visible Filter

**What:** A filter that appears in the UI. Users can change the value but cannot remove it.

**Purpose:** Guides users (and the AI agent) toward time-bounded queries. Default value covers typical analytical use cases.

**Standard:**
```lookml
always_filter: {
  filters: [explore_alias.partition_date: "last 90 days"]
}
```

**Rules:**
- Every explore with a `sql_always_where` MUST also have an `always_filter` on the same partition column
- Default value: "last 90 days" (covers most operational questions)
- The AI agent sees this filter and respects it; Looker injects it automatically into generated SQL

### Layer 3: `conditionally_filter` — Smart Cluster Key Defaults

**What:** A default filter that is automatically removed if the user provides an alternative filter on specified fields.

**Purpose:** Encourages filtering on BigQuery cluster key columns for maximum data pruning. Smart enough to not stack unnecessary filters.

**Standard:**
```lookml
conditionally_filter: {
  filters: [view_name.cluster_key_column: ""]
  unless: [view_name.cluster_key_column, view_name.primary_key]
}
```

**Rules:**
- Apply to columns tagged with `tags: ["cluster_key"]` in the view
- The `unless` list should include the cluster key itself AND common alternative filter columns (e.g., `cust_ref`)
- Empty string default (`""`) means "show the filter but don't pre-fill a value"

### Layer 4: `aggregate_table` — Pre-Computed Rollups

**What:** Materialized summary tables that Looker automatically routes matching queries to.

**Purpose:** Common query patterns (e.g., "monthly totals by category") read from a small pre-computed table instead of scanning the full fact table.

**Standard:**
```lookml
aggregate_table: descriptive_name {
  query: {
    dimensions: [commonly_used_dimension_1, commonly_used_dimension_2]
    measures: [primary_measure_1, primary_measure_2]
    filters: [explore_alias.partition_date: "last 2 years"]
  }
  materialization: {
    datagroup_trigger: daily_refresh
  }
}
```

**Rules:**
- Define for the top 2-3 most common query patterns per explore (identify from usage logs or anticipated dashboard queries)
- Always include a partition filter in the aggregate query to bound the materialized data
- Tie to a datagroup for automatic refresh
- Name descriptively: `monthly_members_by_generation`, not `agg_table_1`

**Cost Impact:**
| Scenario | Est. Cost per Query |
|----------|-------------------|
| No optimization (full scan) | $50-100+ |
| Layer 1+2 (partition filter) | $0.50-5.00 |
| Layer 3 (cluster pruning) | $0.10-1.00 |
| Layer 4 (aggregate table) | $0.01-0.10 |

---

## View-Level Checklist

Before any view file is merged to production:

| # | Check | How to Verify |
|---|-------|--------------|
| V1 | Partition column exists as `dimension_group` with `type: time` | View file has `tags: ["partition_key"]` |
| V2 | Partition description includes "MUST be filtered" warning | Read the `description` field |
| V3 | Primary key dimension is defined with `primary_key: yes` | View file inspection |
| V4 | Cluster key columns have `tags: ["cluster_key"]` | Grep for `cluster_key` tag |
| V5 | All dimensions/measures have enriched descriptions | Each field has `description:` with "Also known as:" synonyms |
| V6 | Financial dimensions used only by measures are `hidden: yes` | Raw amount columns hidden, exposed via measures |
| V7 | `group_label` is set for all non-hidden fields | Logical grouping for UI and AI retrieval |
| V8 | `value_format_name` is set for all numeric measures | `usd`, `decimal_0`, `percent_2`, etc. |
| V9 | `drill_fields` defined for key measures | At least top 2-3 measures have drill paths |
| V10 | BQ optimization header comment exists | Top of file documents partition, cluster, est. size |

## Explore-Level Checklist

Before any explore is merged to production:

| # | Check | How to Verify |
|---|-------|--------------|
| E1 | `sql_always_where` references partition column (Layer 1) | Explore definition |
| E2 | `always_filter` on partition date with 90-day default (Layer 2) | Explore definition |
| E3 | `conditionally_filter` on primary cluster key (Layer 3) | Explore definition |
| E4 | At least 1 `aggregate_table` for common query pattern (Layer 4) | Explore definition |
| E5 | `description` is rich enough for AI disambiguation | Explore has multi-sentence description |
| E6 | All joins specify `type`, `relationship`, and `sql_on` | No implicit inner joins or missing cardinality |
| E7 | Join relationships are correct (`one_to_one`, `many_to_one`, etc.) | Validated against actual data cardinality |
| E8 | `group_label` is set (e.g., "Finance") | Groups explores in the UI picker |
| E9 | Reference table joins use `many_to_one` from fact side | Small tables joined as dimensions, not duplicated |
| E10 | Explore-level header comment documents optimization layers | Comment block above explore |

## Model-Level Checklist

Before any model file is merged to production:

| # | Check | How to Verify |
|---|-------|--------------|
| M1 | `connection` points to correct BQ connection | Model file |
| M2 | Constants `PROJECT_ID` and `DATASET` are defined | Model file |
| M3 | `datagroup` defined for cache management | `sql_trigger` + `max_cache_age` |
| M4 | `persist_with` references the datagroup | Model file |
| M5 | All view includes use correct paths | `include: "/views/*.view.lkml"` |
| M6 | At least 1 `test` block validates partition filter enforcement | Model file has `test:` blocks |
| M7 | Model name follows ADR-002 convention: `{bu_name}_model` | Naming check |
| M8 | BQ optimization strategy header comment exists | Top of model documents 4-layer strategy |

## AI-Retrieval Readiness Checklist

These checks ensure LookML is optimized for the Cortex retrieval pipeline:

| # | Check | Why |
|---|-------|-----|
| A1 | Every field has "Also known as:" synonyms in description | Vector search matches business terms to field names |
| A2 | `tags: ["partition_key"]` and `tags: ["cluster_key"]` are set | Agent programmatically identifies optimization-relevant fields |
| A3 | Derived dimensions include CASE logic explanation in description | Agent understands what "Active Customer (Standard)" means vs "Active Customer (Premium)" |
| A4 | Explore descriptions mention which questions the explore answers | Graph search can route "portfolio health" to `finance_cardmember_360` |
| A5 | `hidden: yes` is set on implementation-detail fields | Reduces noise in retrieval results — agent only sees user-facing fields |
| A6 | Business terms map 1:1 or 1:many to fields (not ambiguous) | If ambiguous, description must explain the distinction |

## Data Tests

Every model must include `test:` blocks that validate cost control:

```lookml
test: partition_filter_enforced_{explore_name} {
  explore_source: {explore_name} {
    column: {measure_alias} { field: {view}.{measure} }
    filters: [{view}.partition_date: "last 7 days"]
  }
  assert: returns_data {
    expression: ${measure_alias} >= 0 ;;
  }
}
```

Run via Spectacles CI or Looker's test runner before deploy. If any test fails, the LookML should NOT be deployed.

## Consequences

- Every new BU onboarding adds ~1-2 hours for checklist verification
- Consistent cost guardrails across all BUs — no "one bad explore" can blow the budget
- AI agent can trust that partition and cluster key metadata is present in every view
- Aggregate tables require storage cost (materialized tables) — offset by query cost savings
- Checklist enforcement can be partially automated via a CI script that parses LookML for required patterns

## Appendix: Finance BU Reference Implementation

The Finance BU (`cortex/lookml/`) serves as the reference implementation:

| Component | Count | Status |
|-----------|-------|--------|
| Views | 7 | All pass V1-V10 |
| Explores | 5 | All pass E1-E10 |
| Model | 1 | Passes M1-M8 |
| Aggregate tables | 5 | Covering top query patterns |
| Data tests | 3 | Partition enforcement validated |
| Business terms | 17+ | All mapped with synonyms |
