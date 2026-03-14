# 80% Coverage Demo Queries
# These 6 queries represent the 8 scenario types that cover ~80% of real-world NL2SQL traffic.
# Each query maps to a scenario type (S1-S8) and shows which explore, dimensions, measures,
# and filters the Cortex pipeline should resolve to.

---

## Query 1: Simple Aggregation + Filtered by Dimension (S1 + S3)

**User says:** "What is the total billed business for the OPEN segment?"

**Pipeline resolves to:**
- Explore: `finance_cardmember_360`
- Measures: `custins_customer_insights_cardmember.total_billed_business`
- Dimensions: (none — aggregate only)
- Filters: `custins_customer_insights_cardmember.bus_seg` = `OPEN`
- Filter resolution: "OPEN segment" → FILTER_VALUE_MAP["bus_seg"]["open"] = "OPEN"

**Why this matters:** This is the bread-and-butter query — single measure, single filter. ~25% of all queries look like this. Tests that the pipeline can: (a) find the right measure via embedding, (b) resolve "OPEN segment" to the correct filter value, (c) select the right explore.

**Ambiguity risk:** "segment" could mean `bus_seg`, `basic_cust_noa`, or `business_org`. The word "OPEN" disambiguates to `bus_seg` because OPEN is a known value.

---

## Query 2: Conditional Aggregation + Group By Joined Dimension (S2 + S4)

**User says:** "How many attrited customers do we have by generation?"

**Pipeline resolves to:**
- Explore: `finance_cardmember_360`
- Measures: `custins_customer_insights_cardmember.attrited_customer_count`
- Dimensions: `cmdl_card_main.generation`
- Filters: (none)

**Why this matters:** Tests two things at once: (a) conditional aggregation — "attrited" maps to a CASE WHEN measure, not a simple COUNT, (b) cross-view join — "generation" lives in `cmdl_card_main`, not in `custins`. The pipeline must recognize that `finance_cardmember_360` joins both views.

**Ambiguity risk:** "customers" could mean `total_customers` (all) vs `attrited_customer_count` (filtered). The word "attrited" must trigger the conditional variant.

---

## Query 3: Ratio / Derived Metric + Time Filter (S5 + S8)

**User says:** "What is our attrition rate for Q4 2025?"

**Pipeline resolves to:**
- Explore: `finance_cardmember_360`
- Measures: `custins_customer_insights_cardmember.attrition_rate`
- Dimensions: (none)
- Filters: `custins_customer_insights_cardmember.partition_date` = `2025-10-01 to 2025-12-31` (or Looker syntax: `2025/Q4`)

**Why this matters:** Tests: (a) derived metric resolution — "attrition rate" is a `type: number` measure (ratio of two other measures), not a simple aggregation. The embedding must match "attrition rate" → `attrition_rate`, not `attrited_customer_count`. (b) Time filter parsing — "Q4 2025" must be converted to a Looker date filter expression.

**Ambiguity risk:** "attrition" could mean the count (how many churned) vs the rate (what percentage churned). "rate" is the disambiguator.

---

## Query 4: Min/Max Extremes + Dimension (S6 + S4)

**User says:** "What is the highest billed business by merchant category?"

**Pipeline resolves to:**
- Explore: `finance_merchant_profitability`
- Measures: `fin_card_member_merchant_profitability.max_merchant_spend`
- Dimensions: `fin_card_member_merchant_profitability.oracle_mer_hier_lvl3`
- Filters: (none)

**Why this matters:** Tests: (a) extremes — "highest" must map to a MAX measure, not SUM or AVG. Before this uplift, we had NO max measures. (b) Explore selection — "merchant category" signals `finance_merchant_profitability`, not `finance_cardmember_360`.

**Ambiguity risk:** "highest billed business" could mean (a) MAX of individual transactions, or (b) the merchant category with the largest total. The former is `max_merchant_spend`, the latter is `total_merchant_spend` with ORDER BY DESC LIMIT 1. The word "highest" combined with "by merchant category" suggests the GROUP BY + ORDER BY pattern (Top-N with N=1). This is where near-miss detection matters.

---

## Query 5: Top-N Ranking + Multiple Measures (S7 + S1)

**User says:** "Show me the top 5 travel verticals by gross sales and booking count"

**Pipeline resolves to:**
- Explore: `finance_travel_sales`
- Measures: `tlsarpt_travel_sales.total_gross_tls_sales`, `tlsarpt_travel_sales.total_bookings`
- Dimensions: `tlsarpt_travel_sales.travel_vertical`
- Filters: (none)
- Sort: `total_gross_tls_sales` DESC
- Limit: 5

**Why this matters:** Tests: (a) multi-measure retrieval — the pipeline must find TWO measures, not just one, (b) ranking — "top 5" translates to ORDER BY + LIMIT at query time, not a special measure, (c) "travel verticals" must map to the `travel_vertical` dimension, not `air_trip_type`.

**Ambiguity risk:** "gross sales" must map to `total_gross_tls_sales`, not `avg_booking_value`. "booking count" must map to `total_bookings`. These are unambiguous given the travel context.

---

## Query 6: Multi-Filter + Conditional + Joined (S2 + S3 + S4)

**User says:** "How many Millennial customers have Apple Pay enrolled and are active?"

**Pipeline resolves to:**
- Explore: `finance_cardmember_360`
- Measures: `custins_customer_insights_cardmember.active_customers_standard`
- Dimensions: (none)
- Filters:
  - `cmdl_card_main.generation` = `Millennial` (resolved via FILTER_VALUE_MAP)
  - `cmdl_card_main.apple_pay_wallet_flag` = `Y` (resolved via FILTER_VALUE_MAP)

**Why this matters:** This is the most complex 80%-tier query. Tests: (a) multi-filter resolution — TWO filters from a joined table, (b) filter value mapping — "Millennial" → "Millennial", "Apple Pay enrolled" → "Y", (c) conditional aggregation — "active" triggers `active_customers_standard`, not `total_customers`, (d) cross-view — filters come from `cmdl_card_main` but the measure comes from `custins`.

**Ambiguity risk:** "active" → standard ($50) or premium ($100)? Default to standard unless user says "premium" or "strict." "Have Apple Pay" could be a filter (show active customers WHERE apple_pay = Y) or a measure (count of apple pay users). "How many... are active" strongly suggests counting active members with the apple_pay filter.

---

## Scenario Coverage Summary

| Query | S1 Simple Agg | S2 Conditional | S3 Filter | S4 Join Dim | S5 Ratio | S6 Min/Max | S7 Top-N | S8 Time |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Q1: Total billed business for OPEN | x | | x | | | | | |
| Q2: Attrited customers by generation | | x | | x | | | | |
| Q3: Attrition rate Q4 2025 | | | | | x | | | x |
| Q4: Highest spend by merchant category | | | | x | | x | | |
| Q5: Top 5 travel verticals | x | | | | | | x | |
| Q6: Millennial + Apple Pay + active | | x | x | x | | | | |

All 8 scenario types covered across 6 queries.

---

## Remaining 20%: What We Explicitly Don't Cover Yet

These are the Tier 3-5 patterns we acknowledge but defer:

| Pattern | Example | Why Deferred |
|---------|---------|-------------|
| **Period-over-period** | "Spend vs last quarter" | Requires Looker `period_over_period` measure type or agent dual-query logic |
| **Cohort analysis** | "Retention curve for Q1 2025 vintage" | Requires self-join on same table at different dates |
| **Nested aggregation** | "Average spend of top-decile customers" | Requires subquery → outer query |
| **Set difference** | "Customers who bought travel but NOT dining" | Requires NOT EXISTS / anti-join |
| **Statistical** | "Standard deviation of spend by segment" | Looker doesn't expose STDDEV natively |
| **Multi-step** | "Why did Millennial spend drop?" | Requires causal reasoning, not SQL |
| **Window function** | "Running total of issuances by month" | Requires OVER() clause |
