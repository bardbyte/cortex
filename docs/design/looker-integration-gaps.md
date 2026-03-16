# Looker Integration Gaps & Questions for Looker Team

**Date:** 2026-03-16
**Context:** Cortex NL2SQL pipeline at 83% accuracy, scaling from 6 → 50+ explores across 3 BUs

---

## Looker MCP Limitations

1. **Field name aliasing hides view ownership.** MCP returns fields prefixed with explore alias, not original view name. `finance_cardmember_360.total_billed_business` not `custins_customer_insights_cardmember.total_billed_business`. We work around this with `EXPLORE_BASE_VIEWS` but it's manual. At 50 explores, auto-extract `from:` clauses during LookML ingest.

2. **No BigQuery cost metadata.** MCP doesn't return bytes_scanned or slot_ms. Can't build cost alerting per query. Workaround: query BQ `INFORMATION_SCHEMA.JOBS` after execution.

3. **Row limit (default 5000, max 50000).** We set 500 in augmented prompt. Need truncation detection + warning in SSE stream when `row_count == limit`.

4. **No pivots, table calculations, or custom fields.** "YoY growth rate" or "pivot by quarter" can't be expressed through MCP `query`. Need derived tables or Python post-processing.

5. **`get_explores` doesn't return joins, `always_filter`, `sql_always_where`, or `conditionally_filter`.** We hardcode these in constants.py — must be auto-synced from LookML.

6. **Filter syntax must be Looker-native, not SQL.** If the ReAct LLM overrides pre-resolved filters with SQL `WHERE` clauses, query fails.

7. **No dry-run / EXPLAIN.** Can't validate query before execution. Every call is live against BigQuery.

---

## LookML Gaps That Break Retrieval

1. **`from:` alias namespace mismatch.** pgvector embeddings use view_name, MCP returns explore alias. Verify `explore_name` in `field_embeddings` uses aliased name.

2. **Hidden fields invisible to search.** `hidden: yes` fields filtered out of pgvector. But queries like "show data for customer X" can't resolve `cust_ref`. May need second-tier search for join keys.

3. **Derived tables lose partition signals.** `cmdl_card_main` derived table pins to latest partition_date. Questions asking "what did demographics look like in Q3?" are unanswerable.

4. **Description quality varies across BUs.** Finance views have excellent descriptions. BU2/BU3 may not. Poor descriptions = poor recall. Need LookML lint rule: reject fields with < 20 word descriptions.

5. **Tier dimensions generate non-obvious filter values.** `customer_tenure_tier` produces `"1 to 2"`, `"5 to 9"`, `"20 or above"`. Not in our `FILTER_VALUE_MAP`. User saying "tenure over 10 years" needs custom tier mapping.

6. **Cross-join fanout in one_to_many joins.** `risk_indv_cust` joined with `relationship: one_to_many` inflates aggregates. `type: average` on many-side is incorrect without `average_distinct`.

7. **SQL CASE dimensions don't auto-generate filter suggestions.** Must manually maintain value maps or run `SELECT DISTINCT` from BigQuery.

---

## Filter Edge Cases Not Yet Handled

| Pattern | Expected Looker Syntax | Status |
|---------|----------------------|--------|
| `"before 2025-06-01"` | `before 2025-06-01` | NOT HANDLED |
| `"March 2025"` | `2025-03` | NOT HANDLED |
| `"this quarter to date"` | `this quarter to date` | NOT HANDLED |
| `"fiscal quarter"` | Amex fiscal year ends January | NOT HANDLED |
| `"today"` | `today` | NOT HANDLED |
| `"7 days ago"` (single day) | `7 days ago` | NOT HANDLED (confused with `last 7 days`) |
| Tier dimension values | `"10 to 19,20 or above"` | NOT HANDLED |
| Numeric filter on non-numeric dim | Should not trigger | RISK — no dim type check |

---

## Scale Concerns: 6 → 50+ Explores

1. **Embedding space pollution.** 50 explores x 20 fields = 1000 fields. "total spend" matches 15+ explores. More ties, more disambiguation prompts. **Fix:** Add `WHERE model_name = :model_name` pre-filter to pgvector search.

2. **Cross-BU namespace collisions.** Multiple BUs define `cust_ref`, `partition_date` with different semantics. **Fix:** Prefix embedding content with `[BU_name]` to cluster by business unit.

3. **Hardcoded constants don't scale.** `EXPLORE_BASE_VIEWS`, `EXPLORE_DESCRIPTIONS`, `EXPLORE_PARTITION_FIELDS` are manual. **Fix:** Auto-generate from LookML parse during pgvector ingest.

4. **Explore description similarity weakens.** At 50 explores in same BU, descriptions converge. The 0.2 desc_sim coefficient may need reduction.

5. **HNSW index tuning.** Current `m=16, ef_construction=64` tuned for small datasets. At 1000+ fields, bump to `m=32, ef_construction=128` or benchmark flat scan.

6. **Classifier prompt bloat.** 50 explore descriptions = ~2000 tokens just for context. Consider pre-filtering to top-10 by keyword match before sending to classifier.

---

## Questions for Looker Team

**Must-ask (blocks correctness):**

1. **Does the MCP `query` tool honor `sql_always_where` and `always_filter` when we construct queries programmatically?** If we send a query with no partition_date in filters, does Looker still inject the default? This is a $100/query cost exposure if wrong.

2. **When `get_dimensions` returns `suggestions` for a SQL CASE dimension, what does it return?** Empty `[]`? Or does it query the table and return CASE output values like `["Gen Z", "Millennial"]`? If it returns values, we can auto-populate filter maps from MCP.

3. **Is there an MCP endpoint that returns the `from:` clause and join graph for an explore?** The REST API has `/api/4.0/lookml_models/{model}/explores/{explore}` — does MCP expose equivalent?

4. **Does the MCP `query` tool support the `sorts` parameter?** "Top 5 merchants by spend" needs sort + limit.

**Should-ask (blocks scale):**

5. **Max fields per query call?** If we send 10 dimensions + 5 measures + 8 filters, does MCP truncate or error?

6. **Can we get SQL without executing?** The REST API supports `result_format=sql`. Does MCP?

7. **Does `conditionally_filter` work through MCP or only UI?** Our model uses `conditionally_filter` on cluster key columns. If API ignores it, no cluster pruning = higher BQ costs.

8. **Does aggregate awareness work through MCP queries?** We define aggregate tables in the model. If MCP always hits the raw table, aggregates are wasted.

---

## Top 3 Risks

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| 1 | Filter value resolution for SQL CASE dimensions | Accuracy ceiling — can't resolve "Gen Z", "Millennial" without hardcoded maps | Auto-generate value maps from LookML + BQ `SELECT DISTINCT` |
| 2 | `always_filter` / `conditionally_filter` not enforced through MCP | Cost exposure — unfiltered BQ scans on 5+ PB tables | Verify with Looker team. Our code injects partition filters as fallback. |
| 3 | Cross-BU embedding pollution at 50+ explores | Accuracy regression — more false positives, more disambiguation | Add `model_name` filter to pgvector search queries |
