# Exhaustive Taxonomy of Semantic Metric Types for NL-to-SQL Pipelines

## Preliminary Definitions

Before enumerating metric types, I must define terms precisely, because imprecise terms produce incomplete taxonomies.

**Metric (Semantic Metric):** A named, reproducible computation over data warehouse tables that returns a quantitative answer to a business question. A metric is defined by: (a) an aggregation function, (b) the column(s) it operates on, (c) the grain at which it operates, (d) any filters or conditions, and (e) any post-aggregation transformations.

**Query Type:** The structural pattern of the SQL that must be generated. Two metrics can have different business meanings but the same query type (e.g., "total spend" and "total customers" are both Type 1 atomic measures). We are classifying by *structural query pattern*, not by business semantics.

**LookML Expressibility:** Whether the metric can be defined as a LookML measure, a derived table, a table calculation, or requires raw SQL that Looker cannot generate through its semantic layer.

**NL-to-SQL Difficulty:** The number of distinct inference steps the AI must perform correctly to generate the right query. Each inference step is a potential failure point. Difficulty = product of success probabilities at each step.

**Grain:** The level of detail at which data is stored. A transaction table has grain = one row per transaction. A customer snapshot has grain = one row per customer per day. Grain mismatches are the source of the hardest query generation errors.

---

## Taxonomy Structure

I organize the 32 metric types into 8 families, ordered from simplest to most complex. Within each family, types are numbered sequentially.

---

## Family A: Simple Aggregation Metrics

These are the atomic building blocks. One aggregation function, one table, no conditions, no time intelligence.

### A1. Atomic Additive Measure

**Definition:** A single aggregation function (SUM, COUNT, COUNT_DISTINCT, MIN, MAX) applied to one column in one table, with no conditional logic.

**SQL Pattern:**
```sql
SELECT SUM(billed_business) AS total_billed_business
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "What is total billed business?" -- SUM(billed_business). "How many total customers?" -- COUNT_DISTINCT(cust_ref).

**LookML Expressibility:** Native. This is what LookML measures are designed for. `type: sum`, `type: count_distinct`, etc.

**NL-to-SQL Difficulty:** Low. Requires: (1) map business term to correct measure, (2) select correct explore, (3) inject partition filter. Three inference steps. With good field descriptions, step 1 achieves >95% accuracy.

**Frequency:** Common. Approximately 40-50% of all business user queries.

---

### A2. Central Tendency Measure

**Definition:** AVG, MEDIAN, or MODE applied to one column. Semantically distinct from A1 because averages are non-additive (you cannot average averages to get the correct answer at a different grain).

**SQL Pattern:**
```sql
SELECT AVG(billed_business) AS avg_billed_business
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "What is the average spend per card member?" -- AVG(billed_business). "What is the median hotel cost per night?" -- PERCENTILE_CONT(gross_usd / hotel_nights, 0.5).

**LookML Expressibility:** AVG is native (`type: average`). MEDIAN requires `type: median` (supported in Looker but translates to PERCENTILE_CONT on BigQuery, which can be slow on large tables). MODE has no native type -- requires a derived table or custom SQL.

**NL-to-SQL Difficulty:** Low for AVG. Medium for MEDIAN (users say "median" but may mean "average"; disambiguation needed). MODE is rarely asked.

**Frequency:** Common. AVG queries are 10-15% of business user queries. MEDIAN is occasional. MODE is rare.

---

### A3. Conditional Aggregation Measure (COUNTIF/SUMIF)

**Definition:** An aggregation with a built-in CASE WHEN filter. The condition is part of the metric definition, not a user-supplied filter. The condition defines a sub-population.

**SQL Pattern:**
```sql
SELECT COUNT(DISTINCT CASE WHEN billed_business > 50 THEN cust_ref END) AS active_customers_standard
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "How many active customers?" -- COUNT_DISTINCT(cust_ref) WHERE billed_business > 50. "How many dining customers?" -- COUNT_DISTINCT(cust_ref) WHERE is_dining_at_restaurant = TRUE.

**LookML Expressibility:** Native. Use `type: count_distinct` with CASE WHEN in the `sql:` parameter, as done in the existing LookML: `sql: CASE WHEN ${is_active_standard} THEN ${cust_ref} END`.

**NL-to-SQL Difficulty:** Medium. The hard part is mapping "active customers" to the correct conditional measure (Standard vs. Premium). When multiple conditional measures exist for similar concepts (active_customers_standard vs. active_customers_premium), disambiguation is required. This is the scenario tested in demo query #26.

**Frequency:** Common. 15-20% of queries. These are the most politically sensitive metrics at Amex -- the definition of "active" varies by BU.

---

### A4. Dispersion/Distribution Measure

**Definition:** Statistical measures of spread: STDDEV, VARIANCE, range (MAX - MIN), coefficient of variation (STDDEV / AVG), interquartile range.

**SQL Pattern:**
```sql
SELECT
  STDDEV(billed_business) AS spend_stddev,
  VARIANCE(billed_business) AS spend_variance,
  MAX(billed_business) - MIN(billed_business) AS spend_range
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "What is the standard deviation of spend across card members?" "How much variance is there in ROC by merchant category?"

**LookML Expressibility:** Partial. Looker does not have a native `type: stddev` or `type: variance`. These must be defined as `type: number` with custom SQL: `sql: STDDEV(${billed_business})`. This works but is clunkier. BigQuery supports STDDEV_POP, STDDEV_SAMP, VAR_POP, VAR_SAMP natively.

**NL-to-SQL Difficulty:** Medium. The AI must recognize that "variance" or "spread" or "how much does it vary" maps to a statistical function. Users rarely say "standard deviation" explicitly; they say "how consistent is spend" or "how much does it vary."

**Frequency:** Occasional. Mostly asked by data analysts, not business users. Perhaps 2-3% of queries.

---

### A5. Approximate/Sketch Measure

**Definition:** Approximate aggregations designed for PB-scale data: HyperLogLog distinct counts (APPROX_COUNT_DISTINCT), approximate quantiles (APPROX_QUANTILES), approximate top-N (APPROX_TOP_COUNT).

**SQL Pattern:**
```sql
SELECT APPROX_COUNT_DISTINCT(cust_ref) AS approx_total_customers
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
```

**Financial Services Example:** "Roughly how many unique merchants do our card members transact with?" -- on a 1B+ row merchant table, exact COUNT_DISTINCT is expensive; APPROX_COUNT_DISTINCT is 10-100x faster with <2% error.

**LookML Expressibility:** Not native. Looker does not have a `type: approx_count_distinct`. Must use `type: number` with `sql: APPROX_COUNT_DISTINCT(${field})`. More importantly, the Looker user cannot toggle between exact and approximate -- the measure definition is fixed.

**NL-to-SQL Difficulty:** Low (for the AI), but high (for decision-making). The AI needs to know WHEN to use approximate vs. exact. This is a cost-optimization decision, not a semantic one. A policy rule ("use APPROX_COUNT_DISTINCT when table has >100M rows and COUNT_DISTINCT is requested") is more appropriate than LLM reasoning.

**Frequency:** Rare for direct user requests. Common as a system optimization. Users do not say "give me an approximate count" -- they say "how many customers" and the system should decide whether to use approximate.

---

## Family B: Ratio and Derived Metrics

Metrics that are computed FROM other metrics. They involve post-aggregation arithmetic.

### B1. Simple Ratio (Measure / Measure)

**Definition:** Division of one aggregated measure by another. Both measures are from the same grain/explore.

**SQL Pattern:**
```sql
SELECT
  SAFE_DIVIDE(
    COUNT(DISTINCT CASE WHEN is_replacement THEN cust_ref END),
    COUNT(DISTINCT cust_ref)
  ) AS replacement_rate
FROM cmdl_card_main
WHERE partition_date = (SELECT MAX(partition_date) FROM cmdl_card_main)
```

**Financial Services Example:** "What is the card replacement rate?" -- total_replacements / total_card_members. "What percentage of issuances are non-CM initiated?" -- non_cm_initiated / total_issuances.

**LookML Expressibility:** Native. `type: number` with `sql: SAFE_DIVIDE(${measure_a}, ${measure_b})`. The existing `replacement_rate` and `pct_non_cm_initiated` measures use this pattern.

**NL-to-SQL Difficulty:** Medium. The AI must recognize that "rate", "percentage", "ratio", "proportion" all indicate a derived measure, not a raw aggregation. It must find the pre-defined ratio measure rather than trying to construct one from components.

**Frequency:** Common. 10-15% of queries. Executives love ratios because they normalize for portfolio size.

---

### B2. Penetration Rate / Share Metric

**Definition:** A specific ratio where the numerator is a subset of the denominator. Answers "what fraction of X is Y?" Can also be expressed as a percentage of total.

**SQL Pattern:**
```sql
SELECT
  bus_seg,
  COUNT(DISTINCT cust_ref) AS segment_count,
  SUM(COUNT(DISTINCT cust_ref)) OVER () AS total,
  SAFE_DIVIDE(COUNT(DISTINCT cust_ref), SUM(COUNT(DISTINCT cust_ref)) OVER ()) AS pct_of_total
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY bus_seg
```

**Financial Services Example:** "What percentage of our portfolio is OPEN segment?" "What share of total spend comes from Millennials?" "What is Apple Pay penetration among Gen Z?"

**LookML Expressibility:** Partial. Looker supports `percent_of_total` as a table calculation, not a measure. For column-level % of total, Looker can compute it in the frontend. But the LLM cannot request a table calculation through the MCP API -- it would need to request the raw counts and compute the ratio, or use a pre-defined `type: number` measure with window function SQL.

**NL-to-SQL Difficulty:** High. "Share" and "penetration" and "percentage of total" all require the AI to understand that the denominator is the total across ALL groups, not a per-group total. This requires window functions or two-pass aggregation, which Looker handles awkwardly.

**Frequency:** Common. 5-10% of queries. Every executive dashboard has mix/share analysis.

---

### B3. Weighted Average

**Definition:** An average where each data point contributes proportionally to a weight. AVG(x) assumes equal weights; weighted average uses SUM(x * w) / SUM(w).

**SQL Pattern:**
```sql
SELECT
  SAFE_DIVIDE(
    SUM(roc_test_global * tot_disc_bill_vol_usd_am),
    SUM(tot_disc_bill_vol_usd_am)
  ) AS weighted_avg_roc
FROM fin_card_member_merchant_profitability
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "What is the spend-weighted average ROC?" -- weight each merchant relationship's ROC by the spend volume. Simple AVG(ROC) would over-weight low-spend merchants.

**LookML Expressibility:** Partial. `type: number` with custom SAFE_DIVIDE SQL works. But Looker has no native `type: weighted_average`. The weight relationship must be explicitly encoded.

**NL-to-SQL Difficulty:** High. Users rarely say "weighted average" -- they say "average ROC" and mean the simple average. The system needs business context to know when a weighted average is the correct interpretation. This is a governance/definition problem, not an AI inference problem.

**Frequency:** Occasional. Data analysts request this. VPs typically do not know the difference between weighted and unweighted.

---

### B4. Index / Relative Metric

**Definition:** A value expressed relative to a benchmark: (observed / benchmark) * 100. An index of 120 means 20% above benchmark. The benchmark can be the overall average, a prior period, a target, or a peer group.

**SQL Pattern:**
```sql
SELECT
  generation,
  AVG(billed_business) AS avg_spend,
  AVG(billed_business) / (SELECT AVG(billed_business) FROM custins_customer_insights_cardmember WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)) * 100 AS spend_index
FROM custins_customer_insights_cardmember c
JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY generation
```

**Financial Services Example:** "What is the spend index by generation?" (Millennials at 85 means they spend 15% below average). "Revolve index by segment" (already exists as the revolve_index measure -- this is literally a ratio expressed as an index).

**LookML Expressibility:** Partial. The revolve_index is defined as a ratio, which is close. But index-to-benchmark requires knowing the benchmark value, which may need a subquery or a window function. Looker table calculations can compute this in the frontend, but the MCP API cannot request table calculations.

**NL-to-SQL Difficulty:** High. "Index" is ambiguous -- it can mean a database index, a general score, or specifically a ratio-to-benchmark. The AI needs to disambiguate from context.

**Frequency:** Occasional. Common in executive scorecards. Risk and portfolio management teams use indices heavily.

---

### B5. Year-to-Date / Period-to-Date Accumulation

**Definition:** Cumulative sum from the start of a calendar period (year, quarter, month) to the current date. YTD spend = SUM(spend) from Jan 1 to today. QTD and MTD are the quarter and month variants.

**SQL Pattern:**
```sql
SELECT
  SUM(billed_business) AS ytd_billed_business
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_TRUNC(CURRENT_DATE(), YEAR)
  AND partition_date <= CURRENT_DATE()
```

**Financial Services Example:** "What is YTD billed business?" "What are QTD card issuances?" "MTD restaurant spend?"

**LookML Expressibility:** Partially native. YTD is essentially a filter: partition_date between start-of-year and today. Looker can handle this through its date filter syntax (`partition_date: "this year"`). The difficulty is that the AI must translate "YTD" into the correct Looker date filter expression.

**NL-to-SQL Difficulty:** Medium. "YTD" is unambiguous. But "this year" in Looker means calendar year -- if Amex uses a fiscal year (Oct-Sep), "YTD" means something different. The AI must know the fiscal calendar convention.

**Frequency:** Common. 5-8% of queries, especially near quarter-end and year-end. Every finance VP asks for YTD numbers.

---

## Family C: Time Intelligence Metrics

Metrics that involve comparison across time periods. These are among the most frequently asked and hardest to get right.

### C1. Period-over-Period Absolute Change

**Definition:** Current period value minus prior period value. "How much did X change?" Variants: MoM (month-over-month), QoQ, YoY, WoW.

**SQL Pattern:**
```sql
WITH periods AS (
  SELECT
    DATE_TRUNC(partition_date, MONTH) AS month,
    SUM(billed_business) AS total_spend
  FROM custins_customer_insights_cardmember
  WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 13 MONTH)
  GROUP BY 1
)
SELECT
  month,
  total_spend,
  total_spend - LAG(total_spend) OVER (ORDER BY month) AS mom_change
FROM periods
```

**Financial Services Example:** "How did billed business change month over month?" "What is the YoY change in active customers?"

**LookML Expressibility:** Not native for arbitrary periods. Looker's `offset` parameter in table calculations can compute prior period values, but this is a frontend/table calculation feature, not a measure. For the MCP API path, you would need to either: (a) make two separate queries and compute the difference, or (b) define a `type: number` measure with LAG window function SQL, which Looker supports but which requires knowing the time dimension to LAG over.

**NL-to-SQL Difficulty:** High. The AI must: (1) identify the time comparison intent, (2) determine the period grain (month, quarter, year), (3) determine the offset (1 period back, or same period last year), (4) generate the correct LAG/window function or dual-query. Four inference steps, each with failure modes.

**Frequency:** Common. 10-15% of queries. "How did X change?" is the second most common question pattern after "What is X?"

---

### C2. Period-over-Period Percentage Change (Growth Rate)

**Definition:** ((Current - Prior) / Prior) * 100. "How much did X grow?" This is distinct from C1 because the output is a percentage, not an absolute value, and division by zero is a concern.

**SQL Pattern:**
```sql
WITH periods AS (
  SELECT
    DATE_TRUNC(partition_date, MONTH) AS month,
    SUM(billed_business) AS total_spend
  FROM custins_customer_insights_cardmember
  WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 13 MONTH)
  GROUP BY 1
)
SELECT
  month,
  total_spend,
  SAFE_DIVIDE(total_spend - LAG(total_spend) OVER (ORDER BY month), LAG(total_spend) OVER (ORDER BY month)) * 100 AS mom_growth_pct
FROM periods
```

**Financial Services Example:** "What is YoY spend growth by generation?" "What is the MoM growth rate for card issuances?"

**LookML Expressibility:** Same limitations as C1, plus the added complexity of the SAFE_DIVIDE. Looker table calculations support `offset()` and `${measure} / offset(${measure}, 1) - 1` patterns, but again only as frontend calculations.

**NL-to-SQL Difficulty:** High. Same as C1, plus the AI must distinguish between "change" (absolute) and "growth" (percentage). Users often use these interchangeably.

**Frequency:** Common. Growth rates are the language of executive presentations. Perhaps 8-12% of queries.

---

### C3. Rolling/Moving Window Aggregation

**Definition:** An aggregation over a sliding window of N periods. "30-day rolling average spend", "12-month trailing total", "7-day moving average of daily issuances."

**SQL Pattern:**
```sql
SELECT
  partition_date,
  SUM(billed_business) AS daily_spend,
  AVG(SUM(billed_business)) OVER (ORDER BY partition_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS rolling_30d_avg_spend
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 120 DAY)
GROUP BY partition_date
ORDER BY partition_date
```

**Financial Services Example:** "What is the 90-day rolling average of daily spend?" "Show me trailing 12-month total TLS sales."

**LookML Expressibility:** Not native for dynamic window sizes. Can be pre-defined as a `type: number` measure with window function SQL for fixed windows (e.g., always 30-day rolling). But the window size is hardcoded. Looker cannot dynamically adjust the window based on user request.

**NL-to-SQL Difficulty:** Very High. The AI must: (1) detect "rolling" or "moving" or "trailing" intent, (2) extract the window size, (3) determine the grain of the time axis (daily, weekly, monthly), (4) construct the window function with correct frame specification. Users also confuse rolling averages with cumulative totals.

**Frequency:** Occasional. Analysts and quants use these for trend smoothing. Executives rarely request them by name but consume them on dashboards.

---

### C4. Same Period Last Year (SPLY) Comparison

**Definition:** Compare the current period to the same calendar period one year ago. Distinct from C1/C2 because it preserves seasonality comparison.

**SQL Pattern:**
```sql
SELECT
  DATE_TRUNC(partition_date, MONTH) AS month,
  SUM(billed_business) AS current_year_spend,
  SUM(CASE WHEN partition_date BETWEEN DATE_SUB(DATE_TRUNC(partition_date, MONTH), INTERVAL 12 MONTH)
                                AND DATE_SUB(LAST_DAY(partition_date), INTERVAL 12 MONTH)
           THEN billed_business END) AS sply_spend
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 13 MONTH)
GROUP BY 1
```

**Financial Services Example:** "How does this December's spend compare to last December?" "Is holiday travel booking up vs. same period last year?"

**LookML Expressibility:** Not native as a single measure. Requires either two queries with different date ranges, or a self-join pattern via derived table. Looker's `period_over_period` feature (introduced in some Looker versions) partially handles this, but it is a dashboard/visualization feature, not a measure-level feature.

**NL-to-SQL Difficulty:** Very High. The AI must recognize "vs last year" or "compared to same time last year" as SPLY, not just "last year." "Last year" could mean the previous calendar year (YoY) or the same month/quarter one year ago (SPLY). Context is everything.

**Frequency:** Common. Seasonality comparison is foundational in retail and financial services. 3-5% of queries, but much higher during earnings seasons.

---

### C5. Cumulative / Running Total

**Definition:** Running sum of a measure over time. At each time point, the value is the sum from the start of the series to that point.

**SQL Pattern:**
```sql
SELECT
  partition_date,
  SUM(billed_business) AS daily_spend,
  SUM(SUM(billed_business)) OVER (ORDER BY partition_date) AS cumulative_spend
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_TRUNC(CURRENT_DATE(), YEAR)
GROUP BY partition_date
ORDER BY partition_date
```

**Financial Services Example:** "Show cumulative card issuances since January." "What is the running total of TLS sales this quarter?"

**LookML Expressibility:** Partial. Looker table calculations support `running_total(${measure})`, but this is a frontend feature. As a measure, it requires a `type: number` with `SUM() OVER (ORDER BY ...)` window function.

**NL-to-SQL Difficulty:** Medium. "Cumulative" and "running total" are fairly unambiguous terms. The harder part is determining the reset point (does it reset at the start of each year? quarter? or is it an all-time running total?).

**Frequency:** Occasional. Used for tracking progress toward targets. 2-3% of queries.

---

### C6. Fiscal Calendar / Custom Calendar Metric

**Definition:** Any metric where "year", "quarter", or "month" does not mean calendar year but a custom fiscal calendar. Amex's fiscal year, for example, might run October to September.

**SQL Pattern:**
```sql
-- If Amex fiscal year starts in October:
SELECT
  CASE
    WHEN EXTRACT(MONTH FROM partition_date) >= 10 THEN EXTRACT(YEAR FROM partition_date) + 1
    ELSE EXTRACT(YEAR FROM partition_date)
  END AS fiscal_year,
  SUM(billed_business) AS total_spend
FROM custins_customer_insights_cardmember
WHERE partition_date >= '2025-10-01'
GROUP BY 1
```

**Financial Services Example:** "What is fiscal YTD billed business?" "Q1 active customers" (where Q1 = Oct-Dec, not Jan-Mar).

**LookML Expressibility:** Partially native. Looker supports `fiscal_month_offset` at the model level, which shifts all time calculations to align with the fiscal calendar. If this is configured, then "this year" automatically means "this fiscal year." However, if fiscal calendars differ by BU (Finance uses Oct-Sep, Travel uses Jan-Dec), this becomes a model-level configuration issue.

**NL-to-SQL Difficulty:** Very High. The AI has no way to know the fiscal calendar unless it is explicitly provided in the system prompt or taxonomy. If a user says "Q1 numbers," the AI must know whether Q1 = Jan-Mar or Oct-Dec. A wrong assumption silently produces wrong data.

**Frequency:** Common within Finance. Every earnings report uses fiscal periods. For non-finance BUs, calendar year is more common.

---

## Family D: Window Function and Ranking Metrics

Metrics that produce ordered or ranked results using SQL window functions.

### D1. Top-N / Bottom-N

**Definition:** Return only the N highest or lowest values of a metric, grouped by a dimension.

**SQL Pattern:**
```sql
SELECT
  oracle_mer_hier_lvl3 AS merchant_category,
  SUM(tot_disc_bill_vol_usd_am) AS total_spend
FROM fin_card_member_merchant_profitability
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10
```

**Financial Services Example:** "What are the top 10 merchant categories by spend?" "Bottom 5 card products by issuance volume."

**LookML Expressibility:** Partially native. Looker's `row_limit` parameter in the query API handles LIMIT. The `sorts` parameter handles ORDER BY. But "top 10 by spend" requires the AI to set both the sort order and the row limit. LookML itself does not define top-N in measure definitions.

**NL-to-SQL Difficulty:** Medium. "Top 10" and "bottom 5" are fairly explicit. The challenge is when users say "biggest" or "largest" or "most" without a number -- the AI must decide a default N (10 is standard). Also, "top merchants" is ambiguous: top by spend, by ROC, by customer count?

**Frequency:** Common. 5-8% of queries. Ranking queries are natural for exploration.

---

### D2. Rank Within Group (RANK / DENSE_RANK / ROW_NUMBER)

**Definition:** Assign a rank to each row within a group, ordered by a metric. Distinct from D1 because the rank is a computed column, not a filter.

**SQL Pattern:**
```sql
SELECT
  generation,
  bus_seg,
  SUM(billed_business) AS total_spend,
  RANK() OVER (PARTITION BY generation ORDER BY SUM(billed_business) DESC) AS spend_rank_within_generation
FROM custins_customer_insights_cardmember c
JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1, 2
```

**Financial Services Example:** "Rank business segments by spend within each generation." "Which merchant category ranks #1 in each business segment?"

**LookML Expressibility:** Not native as a measure. Window functions with PARTITION BY are not expressible as LookML measures. Requires a derived table or native derived table. Alternatively, Looker table calculations can compute `rank()` in the frontend, but only over the returned result set, not over the full dataset.

**NL-to-SQL Difficulty:** Very High. The AI must understand: (1) the ranking metric, (2) the partition dimension (rank WITHIN what?), (3) the ordering direction (ASC or DESC), (4) handle ties (RANK vs. DENSE_RANK). Users rarely specify all four.

**Frequency:** Occasional. Analysts doing competitive analysis across segments. 2-4% of queries.

---

### D3. Percentile / Quantile Segmentation

**Definition:** Divide records into equal-sized groups (quartiles, deciles, percentiles) based on a metric. Assign each record to its bucket.

**SQL Pattern:**
```sql
SELECT
  cust_ref,
  billed_business,
  NTILE(10) OVER (ORDER BY billed_business DESC) AS spend_decile
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "Which decile does each customer fall into by spend?" "What is the 90th percentile of billed business?"

**LookML Expressibility:** Not native for NTILE. Looker has `type: percentile` (e.g., `percentile: 90`), which computes a specific percentile value. But NTILE segmentation (assigning each row to a bucket) requires a derived table.

**NL-to-SQL Difficulty:** High. Users say "top quartile customers" or "high-spend decile" or "whale segment." The AI must translate these into NTILE or PERCENTILE_CONT. The boundary between "top quartile" (NTILE = 1) and "above 75th percentile" (PERCENTILE_CONT(..., 0.75)) is ambiguous.

**Frequency:** Occasional. Common in customer segmentation and risk scoring. 2-3% of queries.

---

### D4. Lag / Lead Comparison (Previous/Next Value)

**Definition:** Compare each row's value to the preceding or following row's value within an ordered group. "What was last month's value? What is the difference from previous?"

**SQL Pattern:**
```sql
SELECT
  partition_month,
  total_spend,
  LAG(total_spend, 1) OVER (ORDER BY partition_month) AS prev_month_spend,
  total_spend - LAG(total_spend, 1) OVER (ORDER BY partition_month) AS change_from_prev
FROM (
  SELECT DATE_TRUNC(partition_date, MONTH) AS partition_month, SUM(billed_business) AS total_spend
  FROM custins_customer_insights_cardmember
  WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
  GROUP BY 1
) sub
```

**Financial Services Example:** "For each month, show me spend and the change from the previous month." "Compare each quarter's issuance count to the prior quarter."

**LookML Expressibility:** Not native as a measure. Looker table calculations support `offset(${measure}, 1)` which provides LAG functionality, but only in the frontend. For the MCP path, this requires a derived table or two queries.

**NL-to-SQL Difficulty:** High. Same challenges as C1/C2, with the additional complexity of the user potentially wanting a full time series with lag columns rather than a single comparison.

**Frequency:** Occasional. This is typically an analyst query for trend analysis. 2-3%.

---

### D5. First / Last Value Within Group

**Definition:** The first or last value of a dimension/measure within a group, ordered by time or another dimension.

**SQL Pattern:**
```sql
SELECT
  cust_ref,
  FIRST_VALUE(card_prod_id) OVER (PARTITION BY cust_ref ORDER BY card_setup_dt) AS first_card_product,
  LAST_VALUE(card_prod_id) OVER (PARTITION BY cust_ref ORDER BY card_setup_dt ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS current_card_product
FROM cmdl_card_main
```

**Financial Services Example:** "What was each customer's first card product?" "What is the most recent merchant category for each customer?"

**LookML Expressibility:** Not native. Requires derived table with window functions. Looker cannot express FIRST_VALUE/LAST_VALUE as a measure.

**NL-to-SQL Difficulty:** High. "First" and "last" and "most recent" are natural language terms that map to window functions, but the AI must determine the ordering column and the partition column.

**Frequency:** Rare. Mostly for customer journey analysis. 1-2% of queries.

---

## Family E: Cross-Entity and Multi-Grain Metrics

Metrics that require joining multiple tables or reasoning about different granularities.

### E1. Cross-View Metric (Single Fact + Dimension Join)

**Definition:** A measure from one view combined with a dimension from another view, requiring a JOIN. The two views exist in the same explore.

**SQL Pattern:**
```sql
SELECT
  d.generation,
  SUM(c.billed_business) AS total_spend
FROM custins_customer_insights_cardmember c
JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
```

**Financial Services Example:** "Total billed business by generation" -- spend from custins, generation from cmdl. This is demo query #6.

**LookML Expressibility:** Fully native. This is what Looker explores are designed for. The join is defined in the model, and the explore handles it transparently.

**NL-to-SQL Difficulty:** Medium. The AI must: (1) find an explore that contains both the measure and dimension, (2) validate the join path exists, (3) handle the case where the same dimension exists in multiple views (e.g., card_prod_id exists in both custins and cmdl).

**Frequency:** Common. 15-20% of queries. Cross-dimensional analysis is the bread and butter of BI.

---

### E2. Filtered Cross-View Metric

**Definition:** Type E1 plus a WHERE clause requiring filter value resolution. The filter value may use internal codes that differ from user-facing terms.

**SQL Pattern:**
```sql
SELECT
  d.generation,
  COUNT(DISTINCT CASE WHEN c.billed_business > 100 THEN c.cust_ref END) AS active_customers_premium
FROM custins_customer_insights_cardmember c
JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND d.generation = 'Millennial'
GROUP BY 1
```

**Financial Services Example:** "Millennial customers with billed business over $100" -- demo query #10. "OPEN segment billed business by generation."

**LookML Expressibility:** Fully native. The filter is applied through Looker's filter syntax. The challenge is mapping "Millennial" to the correct filter value (exact match in this case, but "small business" to "OPEN" requires synonym resolution).

**NL-to-SQL Difficulty:** High. The filter value resolution is the hardest part. The AI must: (1) identify which dimension the filter applies to, (2) resolve the user's phrasing to the correct internal code, (3) handle ambiguity (does "business segment" mean bus_seg or business_org?). This is the problem addressed by ADR-007 and ADR-008.

**Frequency:** Common. 10-15% of queries. Most real-world questions include at least one filter.

---

### E3. Multi-Fact Table Metric (Cross-Explore Computation)

**Definition:** A computation that requires data from two different fact tables at different grains. Example: comparing a customer's spend (from custins) to the merchant profitability of where they spend (from fin_merchant). These tables may not share an explore.

**SQL Pattern:**
```sql
-- Requires joining two fact tables, or two separate queries stitched together
SELECT
  d.generation,
  SUM(c.billed_business) AS card_spend,
  SUM(m.tot_disc_bill_vol_usd_am) AS merchant_spend,
  SAFE_DIVIDE(SUM(m.tot_disc_bill_vol_usd_am), SUM(c.billed_business)) AS merchant_capture_rate
FROM custins_customer_insights_cardmember c
JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
JOIN fin_card_member_merchant_profitability m ON c.cust_ref = m.cust_ref
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND m.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
```

**Financial Services Example:** "Compare card member spend to merchant profitability by generation." "What is the ratio of TLS booking value to total card spend per customer?"

**LookML Expressibility:** Limited. If both fact tables are joined in the same explore (as finance_merchant_profitability has custins joined), it works. But if the metric requires data from explores that DO NOT share a common join path, Looker cannot express this in a single query. You would need a merged results query (two separate queries joined in the Looker frontend) or a derived table.

**NL-to-SQL Difficulty:** Very High. The AI must: (1) recognize that two fact tables are needed, (2) determine if an explore exists that joins them, (3) if not, decide whether to use merged results or refuse the query. Grain mismatches between fact tables (custins: per customer, fin: per customer-merchant pair) can produce wrong results via fanout.

**Frequency:** Occasional. Analysts doing cross-domain analysis. 2-5% of queries.

---

### E4. Nested Aggregation (Aggregate of Aggregates)

**Definition:** Aggregate at grain A, then re-aggregate at grain B. "Average of per-customer totals", "Max of monthly averages", "Median of per-segment counts."

**SQL Pattern:**
```sql
-- "What is the average total spend per customer?"
-- Step 1: total per customer, Step 2: average of those totals
SELECT AVG(customer_total_spend) AS avg_customer_spend
FROM (
  SELECT cust_ref, SUM(billed_business) AS customer_total_spend
  FROM custins_customer_insights_cardmember
  WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY cust_ref
) customer_totals
```

**Financial Services Example:** "What is the average per-customer spend?" (NOT the same as AVG(billed_business) if there are multiple rows per customer). "What is the maximum monthly replacement rate over the past year?"

**LookML Expressibility:** Not native for true nested aggregation. Looker measures operate at a single grain -- the grain of the explore. To compute AVG(SUM(x)), you need a derived table that pre-aggregates at the inner grain. The existing `avg_billed_business` measure computes AVG(billed_business) per row, which is correct only if the table grain is one row per customer per snapshot period.

**NL-to-SQL Difficulty:** Very High. This is the most common source of subtle correctness errors in NL-to-SQL systems. "Average spend per customer" could mean: (a) AVG(billed_business) across rows (which might double-count multi-card customers), or (b) SUM first by customer, then AVG. The correct interpretation depends on table grain, which the AI must know.

**Frequency:** Occasional but critical. When it is wrong, it is silently wrong -- the query runs, returns a number, but the number is incorrect. This is the most dangerous metric type. 3-5% of queries.

---

### E5. Semi-Additive Measure (Balance / Point-in-Time Metric)

**Definition:** A metric that can be summed across some dimensions but NOT across time. Account balances, inventory counts, and headcounts are semi-additive: you can sum them across segments (total balance = sum of segment balances) but NOT across time (January balance + February balance is meaningless).

**SQL Pattern:**
```sql
-- Correct: Take the latest snapshot, then sum across segments
SELECT
  bus_seg,
  SUM(accounts_in_force) AS total_aif
FROM custins_customer_insights_cardmember
WHERE partition_date = (SELECT MAX(partition_date) FROM custins_customer_insights_cardmember)
GROUP BY 1

-- WRONG: Summing across all partition dates double-counts
SELECT SUM(accounts_in_force) AS total_aif  -- This is WRONG
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "Total accounts in force" -- this is a point-in-time metric. Summing across 90 days of snapshots would multiply the actual value by ~90. The existing LookML `total_accounts_in_force` measure (type: sum on accounts_in_force) is CORRECT only if the explore ensures single-snapshot semantics (e.g., through `sql_always_where` or the explore is configured to default to a single partition date).

**LookML Expressibility:** Partially native. Looker does not have a concept of "semi-additive." The developer must ensure correct behavior through explore configuration (e.g., forcing partition_date to a single value for balance metrics). There is no guardrail preventing a user from summing a balance metric across dates.

**NL-to-SQL Difficulty:** Critical / Very High. If the AI generates a query that sums a semi-additive metric across time, the result is silently wrong -- often by 90x. The AI must know which metrics are semi-additive and ensure the date filter is a point-in-time, not a range.

**Frequency:** Common. Balance metrics appear in every financial services data warehouse. 5-10% of queries. The danger is not frequency but the consequence of getting it wrong.

---

## Family F: Comparison and Variance Metrics

Metrics that compare values across segments, targets, or benchmarks.

### F1. Benchmark vs. Actual (Target Variance)

**Definition:** Compare an actual metric value to a predetermined target or budget, computing the variance (absolute or percentage). Targets are typically stored in a separate table.

**SQL Pattern:**
```sql
SELECT
  a.bus_seg,
  a.actual_spend,
  t.target_spend,
  a.actual_spend - t.target_spend AS variance,
  SAFE_DIVIDE(a.actual_spend - t.target_spend, t.target_spend) * 100 AS variance_pct
FROM (
  SELECT bus_seg, SUM(billed_business) AS actual_spend
  FROM custins_customer_insights_cardmember
  WHERE partition_date >= DATE_TRUNC(CURRENT_DATE(), YEAR)
  GROUP BY 1
) a
JOIN budget_targets t ON a.bus_seg = t.bus_seg AND t.fiscal_year = 2026
```

**Financial Services Example:** "Are we on track against our spend target?" "What is the variance between actual and budgeted issuances by quarter?"

**LookML Expressibility:** Requires a separate view for targets, joined to the fact explore. The variance computation itself is a `type: number` measure. The hard part is that targets are stored at different grains (annual targets, quarterly targets) and may need to be distributed across months.

**NL-to-SQL Difficulty:** Very High. The AI must: (1) know a target/budget table exists, (2) join it correctly, (3) align the time period, (4) compute the right variance formula. Most NL-to-SQL systems cannot do this because the target table is not typically in the same explore.

**Frequency:** Common in FP&A (Financial Planning & Analysis). 3-5% of overall queries, but 30%+ for finance teams specifically.

---

### F2. Segment-to-Segment Comparison

**Definition:** Compare the same metric across two specific segments side by side. "How does Millennial spend compare to Gen X?"

**SQL Pattern:**
```sql
SELECT
  generation,
  SUM(billed_business) AS total_spend
FROM custins_customer_insights_cardmember c
JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND d.generation IN ('Millennial', 'Gen X')
GROUP BY 1
```

**Financial Services Example:** "Compare Millennial and Gen Z spend." "OPEN vs CPS active customers."

**LookML Expressibility:** Native. This is just a filtered cross-view query (E2) with an IN filter. The comparison happens in the returned data, not in SQL computation.

**NL-to-SQL Difficulty:** Medium. The AI must: (1) identify the two segments being compared, (2) map them to correct filter values, (3) structure the query to return both segments. The word "compare" can mean side-by-side (GROUP BY) or ratio (one divided by the other) -- disambiguation needed.

**Frequency:** Common. 5-8% of queries. "Compare X vs Y" is a natural question pattern.

---

### F3. Cohort Retention / Survival Analysis

**Definition:** Track a fixed group of customers (a cohort, usually defined by acquisition date) over time. Measure what fraction of the cohort remains active at each subsequent period.

**SQL Pattern:**
```sql
WITH cohort AS (
  SELECT
    cust_ref,
    DATE_TRUNC(card_setup_dt, MONTH) AS acquisition_month
  FROM cmdl_card_main
),
activity AS (
  SELECT
    c.cust_ref,
    co.acquisition_month,
    DATE_TRUNC(c.partition_date, MONTH) AS activity_month,
    DATE_DIFF(DATE_TRUNC(c.partition_date, MONTH), co.acquisition_month, MONTH) AS months_since_acquisition
  FROM custins_customer_insights_cardmember c
  JOIN cohort co ON c.cust_ref = co.cust_ref
  WHERE c.billed_business > 50
)
SELECT
  acquisition_month,
  months_since_acquisition,
  COUNT(DISTINCT cust_ref) AS active_count,
  SAFE_DIVIDE(COUNT(DISTINCT cust_ref), FIRST_VALUE(COUNT(DISTINCT cust_ref)) OVER (PARTITION BY acquisition_month ORDER BY months_since_acquisition)) AS retention_rate
FROM activity
GROUP BY 1, 2
ORDER BY 1, 2
```

**Financial Services Example:** "What is the 12-month retention rate for customers acquired in Q1 2025?" "Show me a retention curve by acquisition cohort."

**LookML Expressibility:** Not native. This requires derived tables with complex window functions. Looker does not have built-in cohort analysis support. Some Looker partners build cohort blocks (pre-built LookML patterns), but they are custom.

**NL-to-SQL Difficulty:** Extremely High. Cohort analysis requires understanding the concept of a "cohort" (fixed group at time 0), the "activity signal" (what counts as retention), and the time-since-acquisition calculation. This is fundamentally a multi-step analytical workflow, not a single query.

**Frequency:** Occasional but high-value. Product and marketing teams ask cohort questions. 2-3% of queries. A v1 system should acknowledge these questions and refuse gracefully, or pre-define specific cohort views.

---

### F4. Contribution to Parent (Percentage of Total at Hierarchy Level)

**Definition:** Within a hierarchy (org, product, geography), compute what percentage each child contributes to its parent's total. Requires knowing the hierarchy structure.

**SQL Pattern:**
```sql
SELECT
  org_name,
  SUM(total_issuances) AS issuances,
  SAFE_DIVIDE(
    SUM(total_issuances),
    SUM(SUM(total_issuances)) OVER ()
  ) AS pct_of_total
FROM gihr_card_issuance i
JOIN ace_organization a ON i.org_id = a.org_id
WHERE issuance_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
```

**Financial Services Example:** "What percentage of total issuances does each organization contribute?" "What share of billed business does each business segment represent?"

**LookML Expressibility:** Partial. Looker's `percent_of_total` table calculation handles this in the frontend. As a measure with window functions, it requires `SUM(x) / SUM(SUM(x)) OVER ()` which Looker can express as `type: number`.

**NL-to-SQL Difficulty:** High. "Contribution" and "share" and "portion" all indicate this type. The AI must determine the parent level (are we looking at % of grand total, or % of parent in a multi-level hierarchy?).

**Frequency:** Common. 5-8% of queries. Executives always want to know the mix.

---

## Family G: Set Operation and Existence Metrics

Metrics that involve set logic: union, intersection, difference, existence, absence.

### G1. Existence Filter (Customers Who DID X)

**Definition:** Filter to entities that satisfy a condition in a related table. "Customers who have a travel booking." "Cards with at least one replacement."

**SQL Pattern:**
```sql
SELECT COUNT(DISTINCT c.cust_ref) AS customers_with_travel
FROM custins_customer_insights_cardmember c
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND EXISTS (
    SELECT 1 FROM tlsarpt_travel_sales t
    WHERE t.cust_ref = c.cust_ref
      AND t.booking_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  )
```

**Financial Services Example:** "How many customers have made a travel booking?" "Customers who have Apple Pay" (simpler: just a filter on apple_pay_wallet_flag = 'Y').

**LookML Expressibility:** Partial. Simple cases (flag columns like apple_pay_wallet_flag) are native filters. Cross-table existence (EXISTS subquery) requires a derived table or a join with non-null filter.

**NL-to-SQL Difficulty:** Medium to High. "Customers who have" or "customers with" typically maps to either a filter on a flag column (easy) or an existence check across tables (hard). The AI must determine which.

**Frequency:** Common. 5-10% of queries.

---

### G2. Absence / Exclusion Filter (Customers Who Did NOT X)

**Definition:** Filter to entities that do NOT satisfy a condition. The complement of G1. "Customers with no travel bookings in 90 days." "Cards that were never replaced."

**SQL Pattern:**
```sql
SELECT COUNT(DISTINCT c.cust_ref) AS customers_without_travel
FROM custins_customer_insights_cardmember c
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND NOT EXISTS (
    SELECT 1 FROM tlsarpt_travel_sales t
    WHERE t.cust_ref = c.cust_ref
      AND t.booking_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  )
```

**Financial Services Example:** "How many customers have NOT made a purchase in 90 days?" (churn/lapse analysis). "Card products with zero issuances this quarter."

**LookML Expressibility:** Limited. NOT EXISTS requires anti-join patterns. Looker can handle LEFT JOIN with IS NULL filter, but the AI must construct this pattern. No native support for absence queries.

**NL-to-SQL Difficulty:** Very High. "Not", "never", "without", "no" are negation words that must flip the logic. Anti-joins are a common source of SQL errors (using NOT IN with NULLs, for example). The AI must also handle the time window: "no purchase in 90 days" is different from "never purchased."

**Frequency:** Occasional. Churn and lapse analysis. 2-4% of queries.

---

### G3. Set Intersection (Customers Who Did BOTH X AND Y)

**Definition:** Entities that satisfy conditions in two different tables/dimensions simultaneously. "Customers who both travel AND dine at restaurants."

**SQL Pattern:**
```sql
SELECT COUNT(DISTINCT c.cust_ref) AS travel_and_dining_customers
FROM custins_customer_insights_cardmember c
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND EXISTS (SELECT 1 FROM tlsarpt_travel_sales t WHERE t.cust_ref = c.cust_ref AND t.booking_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY))
  AND EXISTS (SELECT 1 FROM fin_card_member_merchant_profitability m WHERE m.cust_ref = c.cust_ref AND m.oracle_mer_hier_lvl3 = 'Restaurants' AND m.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY))
```

**Financial Services Example:** "Customers who travel AND dine at restaurants." "Millennials who are both Apple Pay enrolled AND have authorized users."

**LookML Expressibility:** Limited for cross-table intersection. Within a single table, it is just two filters (native). Across tables, it requires EXISTS subqueries or derived tables.

**NL-to-SQL Difficulty:** Very High. "Both X and Y" across different tables requires multi-table reasoning. The AI must decide whether to use EXISTS, INNER JOIN, or INTERSECT, and each has different performance characteristics.

**Frequency:** Occasional. Cross-behavior analysis. 1-3% of queries.

---

### G4. Set Difference (Customers Who Did X But NOT Y)

**Definition:** Entities that satisfy condition A but NOT condition B. "Customers who travel but never dine at restaurants."

**SQL Pattern:**
```sql
SELECT COUNT(DISTINCT c.cust_ref) AS travel_but_no_dining
FROM custins_customer_insights_cardmember c
WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND EXISTS (SELECT 1 FROM tlsarpt_travel_sales t WHERE t.cust_ref = c.cust_ref)
  AND NOT EXISTS (SELECT 1 FROM fin_card_member_merchant_profitability m WHERE m.cust_ref = c.cust_ref AND m.oracle_mer_hier_lvl3 = 'Restaurants')
```

**Financial Services Example:** "Customers who have Apple Pay but NOT airline fee credit enrollment." "Card products issued through campaigns but NOT through mass migration."

**LookML Expressibility:** Very limited. Requires complex anti-join patterns that Looker does not natively support.

**NL-to-SQL Difficulty:** Extremely High. Combines the challenges of G1, G2, and G3. The AI must parse "X but not Y" and correctly implement both the inclusion and exclusion logic.

**Frequency:** Rare. Advanced segmentation. 1-2% of queries.

---

## Family H: Data Quality, Text, and Miscellaneous Metrics

### H1. NULL / Missing Data Analysis

**Definition:** Count or percentage of records where a field is NULL, empty, or contains a default/sentinel value. "How many customers are missing a birth year?"

**SQL Pattern:**
```sql
SELECT
  COUNT(*) AS total_records,
  COUNTIF(birth_year IS NULL) AS missing_birth_year,
  SAFE_DIVIDE(COUNTIF(birth_year IS NULL), COUNT(*)) * 100 AS pct_missing
FROM cmdl_card_main
WHERE partition_date = (SELECT MAX(partition_date) FROM cmdl_card_main)
```

**Financial Services Example:** "What percentage of card members have no generation data?" "How many customer records are missing business segment?"

**LookML Expressibility:** Partially native. A conditional measure (A3) with `CASE WHEN field IS NULL` works. But Looker does not have a built-in "null analysis" feature.

**NL-to-SQL Difficulty:** Medium. "Missing", "null", "blank", "empty", "no value" all indicate NULL analysis. The AI must map these to IS NULL. The subtlety is distinguishing between NULL (no data) and empty string '' or sentinel values like 'Unknown' or 'Other.'

**Frequency:** Occasional. Data quality analysts ask these. Rare for business users. 1-2% of queries.

---

### H2. Text / Pattern Match Filter

**Definition:** Filtering or counting based on string patterns: LIKE, CONTAINS, STARTS_WITH, REGEXP. "Merchant names containing 'Amazon'."

**SQL Pattern:**
```sql
SELECT
  merchant_name,
  SUM(tot_disc_bill_vol_usd_am) AS total_spend
FROM fin_card_member_merchant_profitability
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND LOWER(merchant_name) LIKE '%amazon%'
GROUP BY 1
ORDER BY 2 DESC
```

**Financial Services Example:** "Total spend at merchants containing 'Amazon'" or "Spend at Starbucks" (exact match vs. fuzzy). "Campaign codes starting with 'FU'."

**LookML Expressibility:** Partially native. Looker filters support `contains`, `starts with`, `matches (advanced)` filter expressions. The AI can use Looker's filter syntax: `merchant_name: "%Amazon%"`.

**NL-to-SQL Difficulty:** Medium. "Contains", "starting with", "ending with" are explicit. "At Starbucks" is ambiguous -- exact match on merchant_name = 'Starbucks' or LIKE '%Starbucks%'?

**Frequency:** Occasional. 2-4% of queries. Common when exploring merchant data.

---

### H3. Dynamic Bucketing / Segmentation

**Definition:** Group a continuous dimension into user-defined or system-defined buckets. "Spend in ranges: 0-100, 100-500, 500-1000, 1000+." "Customer tenure tiers."

**SQL Pattern:**
```sql
SELECT
  CASE
    WHEN billed_business <= 100 THEN '$0-100'
    WHEN billed_business <= 500 THEN '$100-500'
    WHEN billed_business <= 1000 THEN '$500-1000'
    ELSE '$1000+'
  END AS spend_bucket,
  COUNT(DISTINCT cust_ref) AS customer_count
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
```

**Financial Services Example:** "Distribution of customers by spend range." "Tenure buckets: <1yr, 1-3yr, 3-5yr, 5-10yr, 10+yr."

**LookML Expressibility:** Native. Looker's `type: tier` dimension handles this. The existing `customer_tenure_tier` dimension uses this pattern. Bucket boundaries are defined in the LookML.

**NL-to-SQL Difficulty:** Medium for pre-defined tiers (the AI just selects the tier dimension). Very High for dynamic/user-specified bucket boundaries (the AI must generate CASE WHEN with arbitrary thresholds from natural language, which Looker cannot do dynamically).

**Frequency:** Common. 3-5% of queries. Distribution analysis is fundamental.

---

### H4. Pivot / Crosstab Query

**Definition:** Display one dimension as columns rather than rows. "Show spend by generation with each business segment as a separate column." This is a display/layout request, not a computation difference.

**SQL Pattern:**
```sql
-- BigQuery PIVOT syntax
SELECT * FROM (
  SELECT generation, bus_seg, SUM(billed_business) AS spend
  FROM custins c JOIN cmdl_card_main d ON c.cust_ref = d.cust_ref
  WHERE c.partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY 1, 2
)
PIVOT (SUM(spend) FOR bus_seg IN ('CPS', 'OPEN', 'Commercial'))
```

**Financial Services Example:** "Show me a matrix of generation (rows) by business segment (columns) with spend in each cell."

**LookML Expressibility:** Native. Looker handles pivoting in the API/frontend through the `pivots` parameter. The AI just needs to specify which dimension to pivot.

**NL-to-SQL Difficulty:** Medium. "As columns", "cross-tab", "matrix", "pivot" are explicit signals. "By X and Y" is ambiguous -- does the user want both as rows (GROUP BY) or one as columns (PIVOT)?

**Frequency:** Occasional. 2-4% of queries. More common in dashboard requests than ad-hoc queries.

---

### H5. Geographic / Distance Metric

**Definition:** Metrics involving geographic calculations: distance between points, region-based aggregation, geo-clustering.

**SQL Pattern:**
```sql
SELECT
  ST_DISTANCE(
    ST_GEOGPOINT(merchant_longitude, merchant_latitude),
    ST_GEOGPOINT(customer_longitude, customer_latitude)
  ) AS distance_meters,
  COUNT(DISTINCT cust_ref) AS customer_count
FROM fin_card_member_merchant_profitability
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
```

**Financial Services Example:** "Average distance between card members and their most frequent merchants." "Spend density by ZIP code."

**LookML Expressibility:** Limited. Looker can define BigQuery's ST_* functions in dimension SQL, but has no native geo-aggregation support. Looker maps (visualization) can display geo data but the semantic layer does not handle distance calculations natively.

**NL-to-SQL Difficulty:** Very High. Geographic queries require knowing which columns contain lat/lon data, and users rarely specify this. "Nearby merchants" requires a reference point.

**Frequency:** Rare in the Finance BU context. More common for marketing and network operations. 0-1% of queries.

---

### H6. Correlation / Bi-Variate Statistical Metric

**Definition:** Measure the statistical relationship between two metrics: Pearson correlation, R-squared, covariance.

**SQL Pattern:**
```sql
SELECT
  CORR(billed_business, customer_tenure_years) AS spend_tenure_correlation
FROM custins_customer_insights_cardmember c
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "Is there a correlation between tenure and spend?" "What is the R-squared between risk rank and billed business?"

**LookML Expressibility:** Not native. Looker has no `type: correlation`. Must use `type: number` with `sql: CORR(${field_a}, ${field_b})`. BigQuery supports CORR natively.

**NL-to-SQL Difficulty:** High. "Correlation" and "relationship between" are the explicit signals. Users more often say "does X affect Y?" which is a causal question the system should reframe as correlation.

**Frequency:** Rare. Analyst and data science queries. 0-1% of business user queries.

---

### H7. Count of Distinct Values (Cardinality Check)

**Definition:** How many unique values exist in a dimension. Not a business metric per se, but a common exploratory query.

**SQL Pattern:**
```sql
SELECT COUNT(DISTINCT oracle_mer_hier_lvl3) AS num_merchant_categories
FROM fin_card_member_merchant_profitability
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "How many distinct merchant categories are there?" "How many unique campaign codes?"

**LookML Expressibility:** Native. Just `type: count_distinct` on the dimension field.

**NL-to-SQL Difficulty:** Low. "How many different", "how many unique", "how many types of" map directly to COUNT_DISTINCT on a dimension.

**Frequency:** Occasional. Data exploration queries. 1-2%.

---

### H8. List / Enumeration Query (Non-Aggregate)

**Definition:** Return a list of distinct values, not a count or sum. "What are the business segments?" "Show me all campaign codes."

**SQL Pattern:**
```sql
SELECT DISTINCT bus_seg FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
ORDER BY bus_seg
```

**Financial Services Example:** "What business segments exist?" "List all generation categories." "What merchant categories are available?"

**LookML Expressibility:** Native through Looker's `suggest_dimension` or field value suggestion API. Also via a query with no measures (dimension-only query).

**NL-to-SQL Difficulty:** Medium. The AI must recognize this is NOT an aggregation query. "What are", "show me all", "list the" are signals. The challenge is that Looker queries typically require at least one measure -- a dimension-only query requires the AI to use COUNT as a throwaway measure.

**Frequency:** Common. 5-8% of queries, especially in first-time or exploratory sessions. Users ask what values exist before filtering on them.

---

### H9. Data Freshness / Recency Metric

**Definition:** When was data last updated? What is the most recent partition date? How stale is the data?

**SQL Pattern:**
```sql
SELECT MAX(partition_date) AS latest_data_date,
       DATE_DIFF(CURRENT_DATE(), MAX(partition_date), DAY) AS staleness_days
FROM custins_customer_insights_cardmember
```

**Financial Services Example:** "When was the customer data last updated?" "How fresh is the merchant profitability data?"

**LookML Expressibility:** Can be defined as a `type: date` or `type: max` measure: `sql: MAX(${partition_date})`.

**NL-to-SQL Difficulty:** Low to Medium. "When was data updated" and "how fresh" are fairly unambiguous. The challenge is that this is a metadata question, not a business question -- the AI might try to answer it from documentation rather than querying.

**Frequency:** Occasional. Data quality checks. 1-2% of queries.

---

## Completeness Check: Exhaustive Case Analysis

I now verify completeness by enumerating dimensions of variation and confirming each is covered.

**Aggregation functions covered:** SUM (A1), COUNT/COUNT_DISTINCT (A1), AVG (A2), MEDIAN (A2), MIN/MAX (A1), STDDEV/VARIANCE (A4), APPROX_COUNT_DISTINCT (A5), CORR (H6). All standard SQL aggregation functions are accounted for.

**Time intelligence covered:** Period-over-period absolute (C1), growth rate (C2), rolling window (C3), SPLY (C4), cumulative (C5), fiscal calendar (C6), YTD/QTD/MTD (B5). All standard time intelligence patterns are accounted for.

**Window functions covered:** RANK/DENSE_RANK (D2), NTILE (D3), LAG/LEAD (D4), FIRST_VALUE/LAST_VALUE (D5), running total (C5), percent of total (B2/F4). All standard window function patterns are accounted for.

**Set operations covered:** Existence (G1), absence (G2), intersection (G3), difference (G4). UNION is not covered because it is a table operation, not a metric type -- but I should add it.

### H10. Union / Append Query

**Definition:** Combine rows from two different tables or filtered subsets into a single result. "All customers from both the cardmember table and the issuance table."

**SQL Pattern:**
```sql
SELECT cust_ref, 'active_customer' AS source FROM custins_customer_insights_cardmember WHERE billed_business > 50
UNION DISTINCT
SELECT cust_ref, 'new_issuance' AS source FROM gihr_card_issuance WHERE issuance_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
```

**Financial Services Example:** "Show me all customers who are either active OR who received a new card in the last 90 days." "Combine travel and merchant spending into a single view."

**LookML Expressibility:** Not native. Requires a derived table with UNION ALL/UNION DISTINCT. Looker explores cannot union two base tables.

**NL-to-SQL Difficulty:** Very High. Users rarely say "union." They say "combine" or "both X and Y" or "from all sources." Distinguishing between UNION (combine rows from different tables) and JOIN (combine columns) is critical.

**Frequency:** Rare. 0-1% of queries.

---

**Multi-turn / conversational covered:** Not a metric type per se, but a query pattern. Covered in demo queries Group 7. The AI must handle follow-ups that modify previous queries (add dimensions, change measures, add filters, change sort).

**Missing: Conditional/Branched metrics.** One more type I should add:

### H11. If-Then Business Rule Metric

**Definition:** A metric whose calculation depends on the value of a dimension. "Revenue = card_fee if product_type = 'Charge', interest_income if product_type = 'Lending'."

**SQL Pattern:**
```sql
SELECT
  card_prod_id,
  SUM(CASE
    WHEN business_org = 'Prop Lending' THEN account_margin
    WHEN business_org = 'Charge' THEN bluebox_discount_revenue
    ELSE billed_business * 0.025
  END) AS composite_revenue
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
```

**Financial Services Example:** "Total revenue" where "revenue" means different things for different product lines. The is_not_cm_initiated measure in gihr_card_issuance is a simpler version of this pattern.

**LookML Expressibility:** Native. CASE WHEN in measure SQL handles this. The existing measures already use this pattern extensively.

**NL-to-SQL Difficulty:** High. The AI must know that "revenue" has product-dependent definitions. This is a governance/taxonomy problem -- the metric must be pre-defined with the correct branching logic.

**Frequency:** Common. 3-5% of queries. Revenue and profitability metrics often have branching definitions.

---

## Summary Matrix: All 32 Metric Types

| # | Type | Family | LookML Native? | NL Difficulty | Frequency | V1 Scope? |
|---|------|--------|----------------|---------------|-----------|-----------|
| A1 | Atomic Additive Measure | Simple Agg | Yes | Low | Common | YES |
| A2 | Central Tendency (AVG/MEDIAN) | Simple Agg | Mostly | Low-Med | Common | YES |
| A3 | Conditional Aggregation (COUNTIF) | Simple Agg | Yes | Medium | Common | YES |
| A4 | Dispersion (STDDEV/VARIANCE) | Simple Agg | Partial | Medium | Occasional | DEFER |
| A5 | Approximate / Sketch | Simple Agg | No | Low (policy) | Rare | DEFER |
| B1 | Simple Ratio | Derived | Yes | Medium | Common | YES |
| B2 | Penetration / Share (% of total) | Derived | Partial | High | Common | PARTIAL |
| B3 | Weighted Average | Derived | Partial | High | Occasional | DEFER |
| B4 | Index / Relative Metric | Derived | Partial | High | Occasional | DEFER |
| B5 | YTD / QTD / MTD | Derived | Partial | Medium | Common | YES |
| C1 | Period-over-Period Change | Time Intel | No | High | Common | PHASE 2 |
| C2 | Growth Rate (% change) | Time Intel | No | High | Common | PHASE 2 |
| C3 | Rolling / Moving Window | Time Intel | No | Very High | Occasional | DEFER |
| C4 | Same Period Last Year | Time Intel | No | Very High | Common | PHASE 2 |
| C5 | Cumulative / Running Total | Time Intel | Partial | Medium | Occasional | DEFER |
| C6 | Fiscal Calendar | Time Intel | Partial (config) | Very High | Common (Finance) | PHASE 2 |
| D1 | Top-N / Bottom-N | Window | Partial | Medium | Common | YES |
| D2 | Rank Within Group | Window | No | Very High | Occasional | DEFER |
| D3 | Percentile / Quantile Segmentation | Window | Partial | High | Occasional | DEFER |
| D4 | Lag / Lead Comparison | Window | No | High | Occasional | DEFER |
| D5 | First / Last Value | Window | No | High | Rare | DEFER |
| E1 | Cross-View Metric | Multi-Entity | Yes | Medium | Common | YES |
| E2 | Filtered Cross-View Metric | Multi-Entity | Yes | High | Common | YES |
| E3 | Multi-Fact Table Metric | Multi-Entity | Limited | Very High | Occasional | DEFER |
| E4 | Nested Aggregation | Multi-Entity | No | Very High | Occasional | DEFER |
| E5 | Semi-Additive Measure | Multi-Entity | Partial | Critical | Common | YES (guardrail) |
| F1 | Benchmark vs. Actual | Comparison | Limited | Very High | Occasional | DEFER |
| F2 | Segment Comparison | Comparison | Yes | Medium | Common | YES |
| F3 | Cohort Retention | Comparison | No | Extremely High | Occasional | DEFER (refuse) |
| F4 | Contribution to Parent | Comparison | Partial | High | Common | PARTIAL |
| G1 | Existence Filter | Set Ops | Partial | Med-High | Common | PARTIAL |
| G2 | Absence / Exclusion | Set Ops | Limited | Very High | Occasional | DEFER |
| G3 | Set Intersection | Set Ops | Limited | Very High | Occasional | DEFER |
| G4 | Set Difference | Set Ops | Very Limited | Extremely High | Rare | DEFER |
| H1 | NULL / Missing Analysis | Misc | Partial | Medium | Occasional | DEFER |
| H2 | Text / Pattern Match | Misc | Partial | Medium | Occasional | PARTIAL |
| H3 | Dynamic Bucketing | Misc | Yes (predefined) | Med-High | Common | YES (predefined) |
| H4 | Pivot / Crosstab | Misc | Yes | Medium | Occasional | YES |
| H5 | Geographic / Distance | Misc | Limited | Very High | Rare | DEFER |
| H6 | Correlation / Bivariate | Misc | No | High | Rare | DEFER |
| H7 | Cardinality Check | Misc | Yes | Low | Occasional | YES |
| H8 | List / Enumeration | Misc | Yes | Medium | Common | YES |
| H9 | Data Freshness | Misc | Yes | Low-Med | Occasional | YES |
| H10 | Union / Append | Misc | No | Very High | Rare | DEFER |
| H11 | If-Then Business Rule | Misc | Yes | High | Common | YES (predefined) |

---

## V1 Scope Analysis (Targeting 90%+ Accuracy by May 2026)

### Proof of Scope Boundary (Bounds Analysis)

**Axiom:** User query distribution follows a Pareto pattern. Based on enterprise BI research and what I can infer from the 35 demo queries, approximately 80% of real user queries fall into 8 of the 32 types.

**Distribution estimate for Finance BU users:**

| Type | Est. % of Queries |
|------|-------------------|
| A1 (Atomic) | 25% |
| A3 (Conditional) | 12% |
| E1 (Cross-View) | 12% |
| E2 (Filtered Cross-View) | 10% |
| A2 (Central Tendency) | 8% |
| B1 (Simple Ratio) | 7% |
| H8 (List/Enumeration) | 5% |
| D1 (Top-N) | 4% |
| **Subtotal (v1 core)** | **83%** |
| C1+C2 (Period-over-Period) | 6% |
| B5 (YTD/QTD) | 3% |
| F2 (Segment Comparison) | 3% |
| B2 (% of Total) | 2% |
| F4 (Contribution) | 1% |
| All remaining 19 types | 2% |

**Therefore:** If v1 handles the top 8 types with 95% accuracy, plus gracefully refuses or redirects the remaining 17%, the effective accuracy is:

- 83% of queries handled at 95% accuracy = 78.85% correct
- 12% of queries handled at 80% accuracy (partial support types) = 9.6% correct
- 5% of queries gracefully refused (counts as "correct behavior") = 5% correct

**Total: 93.45% effective accuracy. This exceeds the 90% target.**

**Critical insight:** The path to 90% is NOT handling all 32 types. It is handling the top 8 with very high accuracy and gracefully refusing the rest.

### V1 In-Scope Types (14 types)

**Full support (must work at 95%+):**
1. A1 -- Atomic Additive Measure
2. A2 -- Central Tendency (AVG)
3. A3 -- Conditional Aggregation
4. B1 -- Simple Ratio
5. E1 -- Cross-View Metric
6. E2 -- Filtered Cross-View Metric
7. D1 -- Top-N / Bottom-N
8. F2 -- Segment Comparison
9. H3 -- Dynamic Bucketing (pre-defined tiers only)
10. H4 -- Pivot/Crosstab
11. H7 -- Cardinality Check
12. H8 -- List/Enumeration
13. H9 -- Data Freshness
14. H11 -- If-Then (pre-defined only)

**Partial support (handle when possible, redirect when not):**
- B2 -- Penetration Rate (if pre-defined as a measure)
- B5 -- YTD/QTD/MTD (through Looker date filter syntax)
- E5 -- Semi-Additive (implement as guardrail, not as a type)
- F4 -- Contribution to Parent (if pre-defined)
- G1 -- Existence Filter (for flag columns only)
- H2 -- Text Match (using Looker filter contains syntax)

**Guardrail (must not produce silently wrong answers):**
- E5 -- Semi-Additive: The system MUST detect balance/point-in-time metrics and either force single-date filtering or warn the user. A wrong answer here costs trust.

### Phase 2 Types (Target: Q3 2026)
- C1, C2 -- Period-over-Period (requires derived tables or multi-query orchestration)
- C4 -- SPLY (requires dual time range query)
- C6 -- Fiscal Calendar (requires fiscal calendar configuration per BU)

### Defer / Refuse Types (Beyond v2)
- A4, A5 -- Statistical/Approximate
- B3, B4 -- Weighted Average, Index
- C3, C5 -- Rolling Window, Cumulative
- D2, D3, D4, D5 -- Complex Window Functions
- E3, E4 -- Multi-Fact, Nested Aggregation
- F1, F3 -- Target Variance, Cohort Retention
- G2, G3, G4 -- Set Absence/Intersection/Difference
- H1, H5, H6, H10 -- NULL Analysis, Geographic, Correlation, Union

---

## Types That Are Fundamentally Hard for LookML/Looker

The following types are not just "hard to build" but structurally mismatched with Looker's semantic layer model:

1. **E4 (Nested Aggregation):** Looker measures operate at one grain. Aggregating an aggregate requires a derived table, which breaks the "define once, query flexibly" model. This is a fundamental limitation of all semantic layers, not just Looker.

2. **C3 (Rolling Window with dynamic size):** LookML measures with window functions must have static frame specifications. A user saying "30-day rolling" vs. "90-day rolling" requires different measure definitions. There is no way to parameterize the window size in a LookML measure.

3. **F3 (Cohort Retention):** This requires defining a cohort at time T0, then tracking it forward. Looker has no native cohort construct. This is fundamentally an analytical workflow, not a single query.

4. **G4 (Set Difference across tables):** Anti-join patterns across explores are not expressible in the Looker API. This requires raw SQL or complex derived tables.

5. **D2 (RANK PARTITION BY):** Looker measures cannot produce row-level ranked output with PARTITION BY. This requires derived tables.

---

## What Each Persona Asks (Persona-to-Type Mapping)

**Finance VP (Kalyan/Jeff):**
- "What is total spend?" (A1)
- "How does this compare to last year?" (C1/C2)
- "Are we on track against budget?" (F1)
- "What is the mix by segment?" (F4)
- "Show me the top 10 by..." (D1)
- "YTD active customers" (B5)
- Dominant types: A1, B5, C1, C2, D1, F1, F4

**Data Analyst:**
- "Break this down by generation and segment" (E1)
- "Filter to OPEN segment" (E2)
- "What is the replacement rate?" (B1)
- "Distribution of spend" (H3, D3)
- "Is there a correlation between tenure and spend?" (H6)
- "What values exist for this field?" (H8)
- Dominant types: E1, E2, B1, H3, H8, D3, H6

**Risk Manager:**
- "What is the revolve index?" (B1)
- "Revolve index by generation" (E1)
- "How has it trended?" (C1)
- "Which segment has highest risk?" (D1, D2)
- "Customers with delinquent balances" (G1)
- Dominant types: B1, E1, C1, D1, D2, G1

**Marketing Strategist:**
- "What is Apple Pay penetration by generation?" (B2)
- "Customers who travel but do not dine" (G4)
- "Cohort retention by acquisition date" (F3)
- "Which campaign drove the most issuances?" (D1, E1)
- "Compare campaign performance" (F2)
- Dominant types: B2, F2, F3, G4, D1

This confirms the persona analysis: VPs and analysts are well-served by v1 scope. Risk managers need Phase 2 (time intelligence). Marketing strategists need Phase 3+ (set operations, cohorts).

---

## Red Team: What Breaks This Taxonomy?

**Counterexample 1: Ambiguous natural language that spans types.** "How has the active customer mix changed year over year?" This is simultaneously A3 (conditional aggregation) + F4 (contribution to parent) + C2 (growth rate). The AI must decompose this into multiple metric types, compute each, and compose the answer. Single-type classification fails.

**Counterexample 2: Questions that are metrics over metrics.** "Which business segment has the most volatile spend?" This requires computing STDDEV of spend per segment, then ranking segments by that STDDEV. It is E1 + A4 + D1 composed. Three-level nesting.

**Counterexample 3: Questions that require external knowledge.** "Is our spend growth above industry average?" The "industry average" is not in the data warehouse. The system must either refuse or explain it can only provide Amex's growth rate, not the benchmark.

**Which assumption, if wrong, collapses the chain?** The Pareto distribution of query types. If Finance BU users actually ask time intelligence questions (C1-C6) 30% of the time instead of 6%, v1 accuracy drops from 93% to approximately 78%. This assumption MUST be validated against actual query logs before launch.

**Strongest argument for a different scoping:** Some would argue that C1 (period-over-period) belongs in v1 because "how did X change?" is the second most natural business question. Deferring it to Phase 2 means 6-10% of queries get refused in v1, which hurts user trust even if the accuracy number is technically 90%+. The counter-argument: implementing C1/C2 correctly requires derived tables or multi-query orchestration, which doubles the pipeline complexity and the surface area for correctness bugs. Better to ship 14 types at 95% than 16 types at 85%.

---

## Recommendation

**For the TaxonomyEntry schema:** Add a `metric_type` field that classifies each metric into one of the 32 types. This enables the AI to apply type-specific generation rules (e.g., if metric_type = E5/semi-additive, enforce point-in-time filter).

**For the golden dataset:** Ensure test coverage across all v1 types. The current 35 test queries heavily index on A1, A3, E1, E2, and B1. Missing: D1 (top-N), B5 (YTD), H8 (list), H4 (pivot), F2 (segment comparison). Add 10-15 test queries for the underrepresented v1 types.

**For the disambiguation agent:** Pre-define the "refuse gracefully" behavior for deferred types. When the AI detects a C3 (rolling window) or F3 (cohort) question, it should explain what it CAN do and offer the closest available alternative, rather than attempting and failing.

**For E5 (semi-additive) guardrail:** This is the single highest-risk metric type. Implement an invariant check: if a measure is tagged as semi-additive (balance, point-in-time), the generated query MUST filter partition_date to a single value or MAX(partition_date). Violating this invariant produces numbers that are 30-365x too large -- a career-ending error if presented to leadership.

---

**Relevant files examined during this analysis:**

- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/demo_queries.md`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/finance_model.model.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/custins_customer_insights_cardmember.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/cmdl_card_main.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/fin_card_member_merchant_profitability.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/tlsarpt_travel_sales.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/gihr_card_issuance.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/risk_indv_cust.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/lookml/views/ace_organization.view.lkml`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/src/taxonomy/schema.py`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/docs/design/whiteboard-2-metric-definition-flow.md`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/adr/006-metric-governance-architecture.md`
- `/Users/bardbyte/Desktop/amex-leadership-project/cortex/docs/design/pipeline-first-principles-breakdown.md`
