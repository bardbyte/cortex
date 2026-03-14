Now I have all the research needed. Let me produce the definitive reference document.

---

# The Definitive Reference: "Metrics" in Modern Semantic Layers and the Query Pattern Universe

## Preliminary Definitions

Before any analysis, I define every term precisely.

**Metric:** A named, reproducible computation over data warehouse tables that returns a quantitative answer to a business question. Defined by: (a) an aggregation function, (b) the column(s) it operates on, (c) the grain at which it operates, (d) any filters or conditions, and (e) any post-aggregation transformations.

**Measure:** The implementation-level representation of a metric within a specific semantic layer tool. In Looker, measures ARE the metric primitives. In dbt, measures are the building blocks FROM WHICH metrics are composed. The terminology is inconsistent across the industry -- this is a source of real confusion.

**Semantic Layer:** A logical abstraction that maps business concepts (dimensions, metrics, relationships) to physical database structures (tables, columns, joins), enabling tools to generate correct SQL without requiring users to understand the physical schema.

**Additivity:** Whether a metric can be correctly aggregated by summation across all dimensions (additive), some dimensions (semi-additive), or no dimensions (non-additive). This is the single most important property of a metric for correctness -- get it wrong and you silently produce wrong answers.

**Query Pattern:** The structural SQL template required to answer a class of business questions. Two questions with different business meanings may share the same query pattern (e.g., "total spend" and "total customers" both use simple aggregation).

---

## Part 1: How Each System Defines "Metric"

### 1.1 dbt Semantic Layer / MetricFlow

**Architecture:** Two-layer model. You define **semantic models** (which map to physical tables and define dimensions + measures) and then define **metrics** on top of measures. Metrics are first-class objects, separate from the physical layer.

**Metric Types (5 types):**

| Type | Definition | Composition Rule | SQL Pattern Generated |
|------|-----------|-----------------|----------------------|
| **Simple** | Direct aggregation on a measure. The atomic building block. | References exactly one measure. Cannot reference other metrics. | `SELECT SUM(column) FROM table WHERE ...` |
| **Derived** | Expression combining multiple metrics via arithmetic. | References 1+ other metrics via `input_metrics`. Requires `expr` (e.g., `revenue - cost`). | Generates subqueries for each input metric, then applies the arithmetic expression. |
| **Ratio** | Division of one metric by another. | Requires `numerator` and `denominator`, each referencing a metric. Optional `filter` applied separately to numerator/denominator. | Two aggregation subqueries joined, then division. |
| **Cumulative** | Running total or window accumulation over time. | References one `input_metric`. Optional `window` (e.g., 7 days) or `grain_to_date` (MTD/QTD/YTD). If no window, accumulates over all time. | Window function with `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` or date-range filtering. |
| **Conversion** | Funnel metric tracking base event to conversion event for an entity within a time window. | Requires `base_metric`, `conversion_metric`, `entity`, `calculation` (conversion_rate or conversions), optional `window`. | Self-join on entity with time window constraint, then aggregation. |

**Measure types within semantic models:** `sum`, `count`, `count_distinct`, `avg`, `min`, `max`, `median`, `percentile`, `sum_boolean`. Each maps directly to SQL aggregation functions.

**Composition rules:** Metrics can reference other metrics (derived references simple, ratio references two metrics). Circular references are prohibited. MetricFlow handles the SQL join planning -- given a metric request with dimension filters, MetricFlow determines the optimal join path between semantic models.

**Key constraint:** MetricFlow enforces that metrics are **time-grained** -- every metric must have an associated time dimension. This is architecturally significant: it means MetricFlow is designed for time-series analytics, not arbitrary ad-hoc queries.

**SQL generation:** MetricFlow generates SQL optimized for Snowflake, BigQuery, Databricks, and Redshift. It handles join fanout deduplication, time spine joins for cumulative metrics, and multi-metric queries requiring different join paths.

Sources: [dbt MetricFlow documentation](https://docs.getdbt.com/docs/build/metrics-overview), [Cumulative metrics](https://docs.getdbt.com/docs/build/cumulative), [Derived metrics](https://docs.getdbt.com/docs/build/derived), [Semantic Layer 2025 comparison](https://www.typedef.ai/resources/semantic-layer-metricflow-vs-snowflake-vs-databricks)

---

### 1.2 Looker / LookML

**Architecture:** Single-layer model. Measures (Looker's term for metrics) are defined directly within **views** (which map to tables) and exposed through **explores** (which define join relationships). There is no separate "metric" abstraction above measures.

**Measure Types (21 types in 3 categories):**

**Aggregate Measures (14 types)** -- perform SQL aggregations, can only reference dimensions:

| Type | SQL Generated | Notes |
|------|--------------|-------|
| `count` | `COUNT(primary_key)` | Counts based on explore's primary key |
| `count_distinct` | `COUNT(DISTINCT column)` | Unique value counts |
| `sum` | `SUM(column)` | Handles fanout from joins |
| `sum_distinct` | Deduplicates via `sql_distinct_key` | For denormalized data with fanout |
| `average` | `AVG(column)` | Handles fanout |
| `average_distinct` | Deduplicated AVG via `sql_distinct_key` | For denormalized data |
| `min` | `MIN(column)` | |
| `max` | `MAX(column)` | |
| `median` | `PERCENTILE_CONT(0.5)` | 50th percentile |
| `median_distinct` | Deduplicated median | For fanout scenarios |
| `percentile` | `PERCENTILE_CONT(n)` | Configurable percentile value |
| `percentile_distinct` | Deduplicated percentile | For fanout scenarios |
| `list` | `GROUP_CONCAT` / `STRING_AGG` | Concatenates distinct values |
| `period_over_period` | Time-shifted aggregation | New type; requires `based_on`, `based_on_time`, `period`, `kind` (previous, relative_change, difference) |

**Non-Aggregate Measures (4 types)** -- no SQL aggregation, reference other measures:

| Type | Purpose | Notes |
|------|---------|-------|
| `number` | Arithmetic on measures | `SAFE_DIVIDE(${measure_a}, ${measure_b})` |
| `string` | Text output | Rarely used |
| `date` | Date output | Can wrap MIN/MAX |
| `yesno` | Boolean condition | TRUE/FALSE display |

**Post-SQL Measures (3 types)** -- calculated after query execution:

| Type | Computation | Constraint |
|------|------------|-----------|
| `percent_of_previous` | (current - previous) / previous | Depends on sort order; references only numeric measures |
| `percent_of_total` | value / column_sum | Only over returned rows |
| `running_total` | Cumulative sum down column | Depends on sort order |

**Composition rules:** Non-aggregate measures (`type: number`) can reference aggregate measures but NOT other non-aggregate measures (no nesting). Post-SQL measures reference aggregate or non-aggregate measures but NOT other post-SQL measures. Aggregate measures reference ONLY dimensions.

**Key constraint:** Looker's semantic layer operates at ONE grain -- the grain of the explore. Nested aggregations (AVG of SUM) require derived tables. Window functions in measure SQL are supported but cannot have dynamic PARTITION BY -- the partition must be hardcoded.

**The `period_over_period` type** is architecturally significant for Cortex. It handles YoY/QoQ/MoM natively with three `kind` values: `previous` (raw prior value), `relative_change` (percentage change), `difference` (absolute change). This eliminates the need for LAG/window function SQL for the most common time intelligence pattern, and it works through the Looker MCP API.

Sources: [Looker measure types](https://docs.cloud.google.com/looker/docs/reference/param-measure-types), [Period-over-period measures](https://cloud.google.com/looker/docs/period-over-period), [Looker measure parameter](https://cloud.google.com/looker/docs/reference/param-field-measure)

---

### 1.3 Cube.js / Cube

**Architecture:** YAML/JavaScript data model with **cubes** (analogous to views) containing **dimensions** and **measures**. Pre-aggregation layer for caching. Next-gen engine "Tesseract" adds advanced features.

**Measure Types (12 types):**

| Type | SQL Generated | Constraint |
|------|--------------|-----------|
| `count` | `COUNT(*)` | No `sql` parameter needed; handles join deduplication |
| `count_distinct` | `COUNT(DISTINCT expr)` | Non-additive; incompatible with rollup pre-aggregations |
| `count_distinct_approx` | HyperLogLog (backend-dependent) | Additive; works with pre-aggregations |
| `sum` | `SUM(expr)` | Handles join-induced duplication |
| `avg` | `AVG(expr)` | Handles join multiplication |
| `min` | `MIN(expr)` | |
| `max` | `MAX(expr)` | |
| `number` | Custom aggregate expression | Must contain aggregate function; for arithmetic: `SUM(x)/COUNT(*)` |
| `number_agg` | Custom aggregate (Tesseract only) | For functions not covered by standard types |
| `string` | Aggregate returning string | e.g., `STRING_AGG` |
| `time` | Aggregate returning timestamp | e.g., `MAX(created_at)` |
| `boolean` | Aggregate returning boolean | e.g., `BOOL_AND(condition)` |

**Advanced features (Tesseract engine):**
- **Rolling windows:** `trailing`/`leading` parameters define moving window size (e.g., "1 month", "unbounded"). Requires time dimension with date range.
- **Multi-stage measures:** `multi_stage: true` enables time shifts, nested aggregates, conditional logic via `case` parameters.
- **Time shift:** `interval` parameter (e.g., "1 year") enables prior-period comparison.
- **Group by controls:** `group_by`, `reduce_by`, `add_group_by` control inner aggregation granularity for fixed-dimension and ranking calculations.

**Composition rules:** `number` type measures reference other measures via arithmetic expressions. Pre-aggregation layer caches results for additive measures but cannot cache non-additive measures (count_distinct, avg).

**Key constraint:** The pre-aggregation system is Cube's architectural differentiator but creates a hard boundary: any measure that is non-additive cannot be served from pre-aggregated caches and must hit the raw data source. This is the "additivity constraint" that Kimball identified decades ago, now baked into a software system.

Sources: [Cube measures documentation](https://cube.dev/docs/product/data-modeling/reference/measures), [Cube types and formats](https://cube.dev/docs/product/data-modeling/reference/types-and-formats), [Cube non-additivity guide](https://cube.dev/docs/guides/recipes/query-acceleration/non-additivity)

---

### 1.4 Snowflake Semantic Views / Cortex Analyst

**Architecture:** Schema-level database objects (DDL, not YAML) that define **logical tables**, **dimensions**, **facts**, **metrics**, and **relationships**. Cortex Analyst uses semantic views to generate SQL from natural language.

**Key distinction -- Facts vs. Metrics:**
- **Facts:** Row-level quantitative attributes (individual sale amounts, quantities). Always at the row grain. These are the "helper" building blocks.
- **Metrics:** Aggregated computations across rows (total revenue, average order value). Built FROM facts using aggregation functions.

**Metric Types (2 types):**

| Type | Definition | Constraint |
|------|-----------|-----------|
| **Regular** | Aggregation over a fact column using SUM, AVG, COUNT, etc. | Must reference a fact in the same logical table |
| **Derived** | Arithmetic on existing metrics, or aggregation of dimensions/facts | Can reference other metrics; enables (Total Revenue / Order Count) patterns |

**Additional features:**
- **Private metrics:** Defined in the semantic model but hidden from end users. Used as intermediate building blocks for derived metrics.
- **Relationships:** Define join paths between logical tables, enabling cross-table queries.
- **Semantic metadata:** Descriptions, synonyms, and examples that guide Cortex Analyst's NL2SQL.

**Key constraint:** Semantic views are Snowflake-native DDL objects, meaning they are tightly coupled to Snowflake. No cross-platform portability. The metric type system is deliberately simple (2 types) because Cortex Analyst handles the SQL complexity.

Sources: [Snowflake semantic views overview](https://docs.snowflake.com/en/user-guide/views-semantic/overview), [Cortex Analyst semantic model spec](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec), [Snowflake summit 2025 insights](https://www.atscale.com/blog/snowflake-summit-2025-ai-semantic-layer-takeaways/)

---

### 1.5 Databricks Metric Views

**Architecture:** Unity Catalog objects that define a semantic layer over lakehouse tables. Composable metric views reference other metric views.

**Measure Types (2 categories):**

| Category | Definition | Example |
|----------|-----------|---------|
| **Atomic measures** | Direct aggregation on a source column. Building blocks. | `SUM(o_totalprice)` |
| **Composed measures** | Expression combining other measures via `MEASURE()` function. | `MEASURE(Total Revenue) / MEASURE(Order Count)` |

**Advanced features:**
- **Window measures:** Enable windowed, cumulative, or semi-additive aggregations (moving averages, period-over-period, running totals).
- **Composability:** Metric views can reference other metric views, creating layered, reusable logic without SQL duplication.
- **Semantic metadata:** Display names, format specs, synonyms for AI/BI dashboard integration and Genie natural language interface.

**Composition rules:** Define atomic measures first, then composed measures. Use `MEASURE()` function consistently when referencing other measures. Composed expressions read like mathematical formulas for KPIs.

Sources: [Databricks metric views](https://docs.databricks.com/aws/en/metric-views/), [Composability in metric views](https://docs.databricks.com/aws/en/metric-views/data-modeling/composability), [Semantic metadata](https://docs.databricks.com/aws/en/metric-views/data-modeling/semantic-metadata)

---

### 1.6 AtScale

**Architecture:** OLAP-style semantic layer with MDX and SQL dual interface. Supports star/snowflake schemas, hierarchical drilldowns, time intelligence, many-to-many relationships.

**Measure Types (4 types):**

| Type | Definition | Aggregation Behavior |
|------|-----------|---------------------|
| **Additive** | Can be summed across ALL dimensions. | Standard SUM, COUNT |
| **Semi-additive** | Can be summed across SOME dimensions but not all (typically not time). | Returns First Non-empty, Last Non-empty, First Child, or Last Child for excluded dimensions |
| **Non-additive** | Cannot be summed across ANY dimension. Ratios, averages. | Requires re-computation from additive components |
| **Calculated** | Derived via formulas referencing other measures or using MDX/DAX-like expressions. | Supports LAG, CURRENTMEMBER, range operators |

**Key differentiator:** AtScale is the only semantic layer that natively supports semi-additive measures as a first-class concept with configurable behavior (first/last child, first/last non-empty). This matters enormously for financial services: account balances, portfolio counts, AIF (accounts in force) are all semi-additive.

Sources: [AtScale semi-additive measures](https://documentation.atscale.com/installer/creating-and-sharing-cubes/creating-cubes/modeling-cube-measures/types-of-cube-measures/semi-additive-measures), [AtScale multidimensional calculation engine](https://www.atscale.com/blog/multidimensional-calculation-engine/)

---

### 1.7 Lightdash (dbt-native BI)

**Architecture:** Open-source BI built on dbt models. Metrics defined in YAML alongside dbt models.

**Metric Types (16 types in 3 categories):**

**Aggregate (10):** `count`, `count_distinct`, `sum`, `average`, `median`, `percentile`, `min`, `max`, `sum_distinct` (beta), `average_distinct` (beta)

**Non-aggregate (4):** `number` (calculations on metrics), `boolean` (TRUE/FALSE), `date`, `string`

**Post-calculation (3, experimental):** `percent_of_previous`, `percent_of_total`, `running_total`

**Composition rules:** Aggregate metrics reference dimensions only. Non-aggregate reference other metrics only. Post-calculation reference aggregate/non-aggregate metrics only. No circular references within a tier.

Sources: [Lightdash metrics reference](https://docs.lightdash.com/references/metrics)

---

### 1.8 Tableau

**Architecture:** No standalone "semantic layer" -- calculation logic lives in workbooks. Three calculation categories.

**Calculation Types (3 categories):**

| Category | Evaluation Level | Key Feature |
|----------|-----------------|-------------|
| **Row-level / Aggregate** | Data source grain or viz grain | Standard: SUM, AVG, COUNT, COUNTD, MIN, MAX, MEDIAN, ATTR, STDEV, VAR, PERCENTILE |
| **LOD Expressions** | Custom grain independent of viz | `{FIXED [dim]: AGG(expr)}`, `{INCLUDE [dim]: AGG(expr)}`, `{EXCLUDE [dim]: AGG(expr)}` |
| **Table Calculations** | Visualization grain only | RUNNING_SUM, RUNNING_AVG, WINDOW_SUM, WINDOW_AVG, RANK, INDEX, LOOKUP, OFFSET, SIZE, TOTAL, PERCENTILE, etc. |

**LOD expressions are Tableau's architectural innovation.** They allow computing aggregations at a grain DIFFERENT from the visualization grain. FIXED ignores all viz-level filters except context filters. INCLUDE adds dimensions (finer grain). EXCLUDE removes dimensions (coarser grain). This is the equivalent of nested aggregation / subquery patterns.

Sources: [Tableau calculation types](https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_understand_types.htm), [Tableau LOD expressions](https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_lod.htm)

---

### 1.9 Power BI (DAX)

**Architecture:** Tabular data model with DAX formula language. Two measure paradigms.

**Measure Types:**
- **Implicit measures:** Auto-generated when dragging numeric fields. Limited to basic aggregations (SUM, AVERAGE, COUNT, DISTINCTCOUNT, MIN, MAX).
- **Explicit measures:** User-defined DAX formulas. Full expressiveness: CALCULATE, filter manipulation, time intelligence functions (TOTALYTD, SAMEPERIODLASTYEAR, DATEADD), iterator functions (SUMX, AVERAGEX, COUNTX), and CALCULATE with context modification.

**Time Intelligence functions (built-in):** TOTALYTD, TOTALQTD, TOTALMTD, SAMEPERIODLASTYEAR, DATEADD, DATESBETWEEN, DATESYTD, DATESQTD, DATESMTD, PARALLELPERIOD, PREVIOUSYEAR/QUARTER/MONTH/DAY, NEXTYEAR/QUARTER/MONTH/DAY, STARTOFYEAR/QUARTER/MONTH, ENDOFYEAR/QUARTER/MONTH, OPENINGBALANCEYEAR/QUARTER/MONTH, CLOSINGBALANCEYEAR/QUARTER/MONTH.

**Calculation Groups:** Reusable calculation patterns (e.g., "YTD", "PY", "YoY%") that can be applied to ANY measure without redefining it. This is Power BI's answer to metric composability -- define the time intelligence pattern once, apply it to any measure.

**Key differentiator:** DAX's CALCULATE function modifies filter context, which is conceptually equivalent to changing WHERE clauses dynamically. This enables patterns like "total sales for the same product category but in the previous year" in a single expression. No other semantic layer has an equivalent.

Sources: [DAX Time Intelligence guide](https://powerbiconsulting.com/blog/power-bi-time-intelligence-dax-complete-guide-2026), [Standard time-related calculations](https://www.daxpatterns.com/standard-time-related-calculations/), [DAX basics in semantic model](https://tabulareditor.com/blog/dax-basics-in-a-semantic-model)

---

### 1.10 Apache Superset

**Architecture:** Thin semantic layer with virtual metrics and calculated columns stored per dataset.

**Metric types:**
- **Virtual metrics:** SQL expressions with aggregate functions (e.g., `SUM(recovered) / SUM(confirmed)`). Can be saved, certified, and reused.
- **Virtual calculated columns:** SQL expressions WITHOUT aggregate functions (row-level transforms like CAST, CASE WHEN). Cannot reference aggregate functions.
- **Custom SQL (ad-hoc):** One-time SQL expressions entered in the explore UI.

**Key constraint:** Calculated columns cannot be referenced inside custom metric SQL -- the generated query uses the column name literally rather than expanding its definition. This is a known limitation ([GitHub Issue #15060](https://github.com/apache/superset/issues/15060)).

Sources: [Preset/Superset metrics docs](https://docs.preset.io/docs/using-metrics-and-calculated-columns), [Superset aggregate functions guide](https://www.restack.io/docs/superset-knowledge-apache-superset-aggregate-functions)

---

### 1.11 Looker Modeler (new, headless Looker)

**Architecture:** Decouples LookML semantic layer from Looker's UI. Exposes metrics via SQL/JDBC interface so Tableau, Power BI, Looker Studio, and other tools can consume them.

**Metric definitions:** Same LookML measure types as classic Looker (the 21 types above). The innovation is the consumption pattern, not the definition pattern. LookML metrics become accessible to any SQL-speaking tool via JDBC.

**Key differentiator for Cortex:** This means our LookML-defined measures could potentially be consumed not only through Looker MCP but also through direct JDBC connections. If Looker Modeler matures, it may offer an alternative query path.

Sources: [Opening up the Looker semantic layer](https://cloud.google.com/blog/products/business-intelligence/opening-up-the-looker-semantic-layer), [Introducing Looker Modeler](https://cloud.google.com/blog/products/data-analytics/introducing-looker-modeler)

---

### Cross-System Comparison Matrix

| Feature | dbt MetricFlow | Looker | Cube.js | Snowflake | Databricks | AtScale |
|---------|---------------|--------|---------|-----------|------------|---------|
| **Metric types** | 5 | 21 | 12 | 2 | 2 | 4 |
| **Composition** | Metrics reference metrics | Measures reference measures (1 level) | number references measures | Derived references metrics | MEASURE() function | MDX expressions |
| **Semi-additive support** | `non_additive_dimension` param | No native concept | No native concept | No native concept | Window measures | First-class (4 behaviors) |
| **Time intelligence** | Cumulative type + grain_to_date | `period_over_period` type | Rolling windows (Tesseract) | Derived metrics | Window measures | MDX LAG/CURRENTMEMBER |
| **Pre-aggregation** | Via dbt materializations | PDTs/Aggregate awareness | Built-in pre-agg engine | Materialized views | Delta caching | Aggregate tables |
| **NL2SQL integration** | dbt Semantic Layer API | Looker MCP | Cube AI API | Cortex Analyst | Genie | AI Link |
| **Cross-platform** | Yes (4 warehouses) | BigQuery-native | Yes (all major DBs) | Snowflake-only | Databricks-only | Yes (all major DBs) |

---

## Part 2: NL2SQL Benchmark Query Pattern Distributions

### 2.1 Spider Benchmark (Yu et al., 2018)

**Dataset:** 10,181 questions, 5,693 unique SQL queries, 200 databases, 138 domains.

**Difficulty distribution (dev set, 1,034 queries):**

| Difficulty | Count | Percentage |
|-----------|-------|-----------|
| Easy | ~248 | ~24% |
| Medium | ~446 | ~43% |
| Hard | ~174 | ~17% |
| Extra Hard | ~166 | ~16% |

**SQL component frequency (across 10,181 questions):**

| SQL Component | Approximate Count | Percentage |
|--------------|------------------|-----------|
| GROUP BY | ~1,491 | ~14.6% |
| ORDER BY / LIMIT | ~1,335 | ~13.1% |
| Nested subqueries | ~844 | ~8.3% |
| HAVING | ~388 | ~3.8% |
| INTERSECT / EXCEPT / UNION | Present but rare | <5% |
| Window functions | Essentially absent | ~0% |
| CTEs | Essentially absent | ~0% |

**Critical finding:** Spider contains ZERO window functions and essentially zero CTEs. This means that ANY system benchmarked only on Spider has never been tested on window functions, which are required for 15-25% of real enterprise queries (ranking, running totals, period-over-period, percent of total).

Sources: [Spider benchmark paper](https://arxiv.org/abs/1809.08887), [Spider Yale challenge](https://yale-lily.github.io/spider), [Spider SQL component analysis](https://arxiv.org/html/2407.19517v1)

---

### 2.2 BIRD Benchmark (Li et al., 2023)

**Dataset:** 12,751 text-SQL pairs, 95 databases, 33.4 GB total, 37 professional domains. Dev set: 1,534 pairs.

**Difficulty distribution (3 levels):**

| Difficulty | Approximate Distribution |
|-----------|------------------------|
| Simple | ~40% |
| Moderate | ~40% |
| Challenging | ~20% |

**Key differences from Spider:**
- BIRD includes "evidence" -- external knowledge hints that the model may need (e.g., "small business means bus_seg = 'OPEN'"). This is the filter value resolution problem.
- BIRD databases are larger and more realistic (33.4 GB vs. Spider's small schemas).
- BIRD uses execution accuracy as primary metric (does the SQL return the correct result?), not exact match.

**SQL feature usage (approximate, from comparative analysis):**
- JOINs requiring 4+ tables: <1% (74 out of ~9,500 training queries)
- Subquery usage: Minimal (comparable to Spider)
- Window functions: Not systematically present
- CTEs: Not systematically present

Sources: [BIRD benchmark](https://bird-bench.github.io/), [BIRD original paper](https://arxiv.org/abs/2305.03111), [Understanding noise in BIRD](https://arxiv.org/html/2402.12243v4)

---

### 2.3 TPC-DS (Decision Support Benchmark)

**Not an NL2SQL benchmark** but represents real enterprise analytical query complexity. 99 query templates.

**Complexity comparison to Spider/BIRD:**

| Feature | Spider/BIRD | TPC-DS |
|---------|------------|--------|
| WHERE predicates per query | 1-3 | 5-15+ |
| JOINs per query | 0-3 | 5-15+ |
| Subqueries | Minimal (<8%) | Regular, heavy use |
| CTEs | Absent | Heavy use |
| Function calls | 0-3, never >5 | 5-10+, some >10 |
| Column references | Few | Order of magnitude more |
| Window functions | Absent | Present |

**LLM performance on TPC-DS (from 2024 evaluation):**
- GPT-4: 0.32 average similarity to gold SQL
- Gemini-1.5: 0.33 average similarity
- Mistral-Large: 0.28 average similarity
- "None of the LLMs are able to generate queries that match the WHERE predicates and JOIN pairs."

**Implication for Cortex:** TPC-DS represents what enterprise analysts ACTUALLY need. The gap between Spider/BIRD performance (~85% accuracy) and TPC-DS performance (~30% similarity) is the real measure of how far NL2SQL has to go for enterprise use cases.

Sources: [Evaluating LLMs for Text-to-SQL with complex SQL workload](https://arxiv.org/html/2407.19517v1)

---

### 2.4 Other Notable Benchmarks

| Benchmark | Size | Key Feature | Limitation |
|-----------|------|-------------|-----------|
| **WikiSQL** | 80,654 pairs | Large but simple (single-table, no JOINs) | Too simple for enterprise use |
| **SParC** | 4,298 pairs | Multi-turn conversational | Small, limited SQL complexity |
| **CoSQL** | 3,007 pairs | Conversational with clarification | Small, limited SQL complexity |
| **KaggleDBQA** | 272 pairs | Real Kaggle databases | Very small |
| **Spider 2.0** | Enterprise workflows | Multi-step, real enterprise tools | Just released (ICLR 2025), limited adoption |
| **BIRD-INTERACT** | Interactive | Multi-turn with dynamic interactions | New, limited results available |

Sources: [Spider 2.0](https://spider2-sql.github.io/), [NL2SQL survey](https://arxiv.org/abs/2408.05109), [Analysis of Text-to-SQL benchmarks](https://openproceedings.org/2025/conf/edbt/paper-41.pdf)

---

## Part 3: Exhaustive Query Pattern Taxonomy

Drawing from all sources (benchmarks, industry tools, research papers, financial services domain knowledge), I identify **34 distinct query pattern types** organized in 8 families. The existing metric taxonomy document at `/Users/bardbyte/Desktop/amex-leadership-project/cortex/docs/design/metric-taxonomy.md` covers 32 of these as types A1-H10. I add two additional patterns identified through this research.

### Family A: Simple Aggregation (5 types)
- **A1. Atomic Additive** -- SUM, COUNT, COUNT_DISTINCT, MIN, MAX on one column. ~40-50% of queries.
- **A2. Central Tendency** -- AVG, MEDIAN, MODE. ~10-15%.
- **A3. Conditional Aggregation** -- COUNTIF/SUMIF via CASE WHEN. ~15-20%.
- **A4. Dispersion/Distribution** -- STDDEV, VARIANCE, range. ~2-3%.
- **A5. Approximate/Sketch** -- APPROX_COUNT_DISTINCT, HyperLogLog. Rare for users, common as system optimization.

### Family B: Ratio and Derived (5 types)
- **B1. Simple Ratio** -- measure / measure. ~10-15%.
- **B2. Penetration/Share** -- subset / total via window function. ~5-10%.
- **B3. Weighted Average** -- SUM(x*w) / SUM(w). Occasional.
- **B4. Index/Relative** -- (observed / benchmark) * 100. Occasional.
- **B5. Period-to-Date** -- YTD/QTD/MTD accumulation. ~5-8%.

### Family C: Time Intelligence (6 types)
- **C1. Period-over-Period Absolute** -- MoM/QoQ/YoY change. ~10-15%.
- **C2. Period-over-Period Percentage** -- growth rate. ~8-12%.
- **C3. Rolling/Moving Window** -- 30-day rolling avg, trailing 12-month. Occasional.
- **C4. Same Period Last Year (SPLY)** -- seasonal comparison. ~3-5%.
- **C5. Cumulative/Running Total** -- running sum over time. ~2-3%.
- **C6. Fiscal Calendar** -- custom fiscal year mapping. Common in Finance.

### Family D: Window Function and Ranking (5 types)
- **D1. Top-N / Bottom-N** -- ORDER BY + LIMIT. ~5-8%.
- **D2. Rank Within Group** -- RANK/DENSE_RANK/ROW_NUMBER with PARTITION BY. ~2-4%.
- **D3. Percentile/Quantile Segmentation** -- NTILE, PERCENTILE_CONT. ~2-3%.
- **D4. Lag/Lead Comparison** -- compare to previous/next row. ~2-3%.
- **D5. First/Last Value** -- FIRST_VALUE/LAST_VALUE within group. ~1-2%.

### Family E: Cross-Entity and Multi-Grain (5 types)
- **E1. Cross-View (Single Fact + Dimension Join)** -- GROUP BY dimension from another table. ~15-20%.
- **E2. Filtered Cross-View** -- E1 + filter value resolution. ~10-15%.
- **E3. Multi-Fact Table** -- cross-explore computation. ~2-5%.
- **E4. Nested Aggregation** -- AVG of per-customer SUM. ~3-5%. MOST DANGEROUS for silent errors.
- **E5. Semi-Additive** -- balance/point-in-time metrics. ~5-10%. Second most dangerous.

### Family F: Comparison and Variance (4 types)
- **F1. Benchmark vs. Actual** -- target variance. ~3-5% overall, ~30% for FP&A teams.
- **F2. Segment-to-Segment Comparison** -- "compare X vs Y". ~5-8%.
- **F3. Cohort Retention/Survival** -- track acquisition cohort over time. ~2-3%.
- **F4. Contribution to Parent** -- % of hierarchy total. ~5-8%.

### Family G: Set Operations and Existence (4 types)
- **G1. Existence Filter** -- customers who DID X. ~5-10%.
- **G2. Absence/Exclusion** -- customers who did NOT X. ~2-4%.
- **G3. Set Intersection** -- did BOTH X AND Y. ~1-3%.
- **G4. Set Difference** -- did X but NOT Y. ~1-2%.

### Family H: Data Quality, Text, and Misc (10+ types)
- **H1. NULL/Missing Analysis** -- COUNTIF IS NULL. ~1-2%.
- **H2. Text/Pattern Match** -- LIKE, CONTAINS, REGEXP. ~2-4%.
- **H3. Dynamic Bucketing** -- CASE WHEN for custom tiers. ~3-5%.
- **H4. Pivot/Crosstab** -- dimension as columns. ~2-4%.
- **H5. Geographic/Distance** -- ST_DISTANCE, geo-aggregation. ~0-1%.
- **H6. Correlation/Bivariate** -- CORR, R-squared. ~0-1%.
- **H7. Cardinality Check** -- COUNT(DISTINCT dimension). ~1-2%.
- **H8. List/Enumeration** -- SELECT DISTINCT (no aggregation). ~5-8%.
- **H9. Data Freshness** -- MAX(partition_date). ~1-2%.
- **H10. Union/Append** -- UNION ALL across tables. ~0-1%.

### NEW -- H11. CAGR / Compound Growth Rate

**Definition:** Compound Annual Growth Rate computed as `(end_value / start_value)^(1/years) - 1`. Requires exactly two time points and an exponentiation function.

**SQL Pattern:**
```sql
SELECT
  POWER(
    SAFE_DIVIDE(
      (SELECT SUM(billed_business) FROM custins WHERE partition_date >= '2025-01-01' AND partition_date < '2026-01-01'),
      (SELECT SUM(billed_business) FROM custins WHERE partition_date >= '2022-01-01' AND partition_date < '2023-01-01')
    ),
    1.0 / 3
  ) - 1 AS cagr_3yr
```

**Frequency:** Rare for ad-hoc queries. Common in executive presentations and investor reports.

**LookML Expressibility:** Not native. Requires derived table or custom SQL with POWER function.

### NEW -- H12. Conditional Ranking / "Which segment is best by X?"

**Definition:** Identify which dimension value maximizes or minimizes a metric. Not "give me the top 10" (D1) but "which ONE is the best/worst?"

**SQL Pattern:**
```sql
SELECT bus_seg, SUM(billed_business) AS total_spend
FROM custins_customer_insights_cardmember
WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1
ORDER BY 2 DESC
LIMIT 1
```

**NL examples:** "Which business segment has the highest spend?" "What generation has the lowest attrition?" "Which card product is most popular?"

**Frequency:** Common (~3-5%). This is a degenerate case of D1 with N=1, but the natural language pattern is different ("which" vs "top N").

---

## Part 4: The "Long Tail" -- Uncommon but Real Query Patterns

These are patterns that most NL2SQL systems miss entirely.

### 4.1 Failure Modes from Research (CIDR 2024, NL2SQL Surveys)

The paper "NL2SQL is a solved problem... Not!" (Floratou et al., CIDR 2024) identifies these enterprise-specific failure categories:

**Schema Complexity Failures:**
- Hundreds of tables with ambiguous naming (enterprise schemas have `tbl_cust_acct_dtl_stg_v2`)
- Multiple valid join paths between the same two tables
- Schema evolution -- table/column names change but business meaning stays the same
- Star vs. snowflake vs. denormalized schemas requiring different query strategies

**Ambiguity Categories (three levels):**
1. **Lexical ambiguity** -- single word has multiple meanings ("balance" = account balance, balance due, trial balance)
2. **Syntactic ambiguity** -- sentence can be parsed multiple ways ("customers with cards expiring in March" -- March of which year?)
3. **Under-specification** -- insufficient detail for clear intent ("show me the numbers" -- which numbers? for what time period?)

**The "Unanswerable Query" Problem:**
- The database genuinely cannot answer the question (no data available)
- NL2SQL systems almost never say "I can't answer this" -- they generate plausible-looking but wrong SQL instead
- No benchmark penalizes systems for answering unanswerable questions

**Benchmark vs. Reality Gap:**
- 85.98% of enterprise SQL queries use advanced dialect-specific functions not present in benchmarks
- Academic benchmarks have ~2-3 tables per schema; enterprise schemas have 100-1,000+ tables
- Benchmarks assume clean data; enterprise data has NULLs, sentinel values, duplicates, and inconsistencies

Sources: [NL2SQL is a solved problem... Not!](https://www.cidrdb.org/cidr2024/papers/p74-floratou.pdf), [VLDB 2025 NL2SQL survey](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/VLDB25-NL2SQL.pdf), [NL2SQL-BUGs benchmark](https://arxiv.org/pdf/2503.11984)

### 4.2 Multi-Step Analytical Queries

These require the answer to query 1 as input to query 2.

| Pattern | Example | SQL Complexity |
|---------|---------|---------------|
| **Threshold from subquery** | "Customers spending above the 90th percentile" | Subquery to compute percentile, outer query to filter |
| **Dynamic cohort definition** | "Customers who joined in the month with highest acquisitions" | Subquery to find the max month, outer query to filter |
| **Conditional aggregation on derived set** | "Average spend of customers in the top decile" | Subquery to assign deciles, outer query to filter and average |
| **Iterative drill-down** | "What's total spend? Now break it by segment. Now show me just OPEN." | Three sequential queries, each refining the previous |

### 4.3 Comparative Queries

| Pattern | Example | Why It's Hard |
|---------|---------|--------------|
| **A vs B side-by-side** | "Compare Millennial vs Gen X spend" | Simple GROUP BY, but "compare" is ambiguous (ratio? difference? side-by-side?) |
| **Before/After** | "Spend before and after the rewards program launch" | Requires knowing the event date and constructing two time windows |
| **Outperformers/Underperformers** | "Which regions underperformed vs target?" | Requires target data + join + variance computation |
| **Relative to peer group** | "How does this segment compare to the overall average?" | Requires window function for overall average + per-group calculation |

### 4.4 Negation and Absence Queries

These are systematically harder because SQL expresses presence (EXISTS, IN) more naturally than absence (NOT EXISTS, NOT IN, LEFT JOIN WHERE IS NULL).

| Pattern | Example | SQL Pattern | Trap |
|---------|---------|------------|------|
| **Never did** | "Customers who never made a purchase" | NOT EXISTS or LEFT JOIN WHERE NULL | NOT IN with NULLs returns empty set (classic SQL bug) |
| **Stopped doing** | "Customers who were active last year but not this year" | EXISTS for last year AND NOT EXISTS for this year | Requires two correlated subqueries |
| **Missing from set** | "Products with no sales in Q4" | LEFT JOIN WHERE NULL | Grain mismatch if product table has different grain |

### 4.5 Temporal Queries Beyond Simple Filtering

| Pattern | Example | SQL Feature Required |
|---------|---------|---------------------|
| **First occurrence** | "When was each customer's first purchase?" | MIN(date) with GROUP BY |
| **Days since last activity** | "How many days since each customer's last transaction?" | DATE_DIFF(CURRENT_DATE(), MAX(date)) |
| **Consecutive periods** | "Customers active for 3 consecutive months" | Window function with conditional logic (gaps-and-islands) |
| **Seasonality detection** | "Is there a seasonal pattern in spend?" | Statistical analysis beyond SQL |
| **Time to event** | "Average time from card issuance to first $1000 spend" | Two dates from different tables, DATE_DIFF |
| **Recurring pattern** | "Customers who spend every month" | COUNT(DISTINCT month) = total months in range |

### 4.6 Statistical Queries

| Pattern | Example | SQL Function |
|---------|---------|-------------|
| **Standard deviation** | "What's the spread of spend across customers?" | STDDEV_POP / STDDEV_SAMP |
| **Correlation** | "Is spend correlated with tenure?" | CORR(x, y) |
| **Regression** | "What's the trend line for monthly spend?" | No native SQL; requires ML functions or external computation |
| **Distribution shape** | "Is spend normally distributed?" | APPROX_QUANTILES + manual histogram |
| **Outlier detection** | "Flag customers with spend > 3 standard deviations" | STDDEV + threshold filtering |

### 4.7 Data Quality Queries

| Pattern | Example | Notes |
|---------|---------|-------|
| **Null analysis** | "What percentage of records are missing generation?" | COUNTIF(IS NULL) / COUNT(*) |
| **Duplicate detection** | "Are there duplicate customer records?" | GROUP BY + HAVING COUNT(*) > 1 |
| **Consistency check** | "Do card counts in custins match card counts in cmdl?" | Cross-table comparison |
| **Freshness** | "When was this data last updated?" | MAX(partition_date) |
| **Completeness** | "Which months have no data?" | Calendar table LEFT JOIN |

### 4.8 Financial Services Specific Patterns (Long Tail for Amex)

| Pattern | Example | SQL Complexity |
|---------|---------|---------------|
| **Vintage analysis** | "Delinquency rate by issuance vintage" | Cohort definition by issuance date + time-series delinquency tracking |
| **Roll rate** | "What % of 30-day delinquent accounts rolled to 60-day?" | Two snapshots, state transition matrix |
| **Net flow** | "Net new accounts = new issuances - closures - attritions" | Multiple aggregations subtracted |
| **Wallet share** | "What % of a customer's total spend is on our card?" | Requires competitor data (usually unavailable) |
| **Portfolio concentration** | "Herfindahl index of spend by merchant category" | SUM(share^2) -- requires squared share computation |
| **Charge-off rate** | "What % of receivables were written off?" | Point-in-time balance / cumulative write-offs |
| **Yield curve** | "Revenue yield by risk tier over time" | Multi-dimensional time-series with computed ratio |

---

## Part 5: Query Complexity Distribution

### 5.1 Academic Benchmark Distribution

From measured data across Spider and BIRD:

```
Simple queries (1 table, 1 aggregation, 0-1 filter):     ~25%
Medium queries (1-2 tables, 1-2 aggregations, filters):  ~43%
Hard queries (2-3 tables, GROUP BY + HAVING, or nested):  ~17%
Extra Hard (3+ tables, nested subqueries, set ops):       ~15%
```

### 5.2 Real Enterprise Query Distribution (Synthesized from Multiple Sources)

Based on the TPC-DS analysis, CIDR 2024 paper, enterprise BI survey data, and financial services domain knowledge, the realistic distribution for an Amex-like environment is:

```
TIER 1: Simple Aggregation (no joins)                     ~30-35%
  "What is total billed business?"
  "How many active customers?"
  SQL: SELECT AGG(col) FROM table WHERE partition_filter

TIER 2: Aggregation with Joins + Filters                  ~25-30%
  "Total spend by generation for Millennials"
  "Active customers in OPEN segment"
  SQL: SELECT AGG(col) FROM t1 JOIN t2 WHERE filters GROUP BY dim

TIER 3: Time Intelligence + Comparison                    ~15-20%
  "YoY spend growth by segment"
  "Compare this quarter vs last quarter"
  SQL: Window functions, LAG/LEAD, self-joins, dual queries

TIER 4: Complex Analytics                                 ~10-15%
  "Top 5 segments by YoY growth rate"
  "Retention curve for Q1 2025 cohort"
  SQL: CTEs, nested subqueries, multiple window functions

TIER 5: Multi-Step / Unsolvable                           ~5-10%
  "Why did Millennial spend drop?"
  "What should we do about attrition?"
  SQL: Requires human judgment, causal analysis, or data not in warehouse
```

### 5.3 SQL Feature Frequency in Real Enterprise Queries

| SQL Feature | Spider/BIRD | TPC-DS | Real Enterprise (estimated) |
|------------|------------|--------|---------------------------|
| Simple WHERE | ~70% | ~100% | ~90% |
| JOIN (any) | ~40% | ~95% | ~60% |
| GROUP BY | ~15% | ~80% | ~50% |
| ORDER BY | ~13% | ~60% | ~40% |
| HAVING | ~4% | ~30% | ~10% |
| Subquery | ~8% | ~70% | ~15% |
| Window Function | ~0% | ~40% | ~20% |
| CTE | ~0% | ~60% | ~15% |
| CASE WHEN | ~5% | ~50% | ~25% |
| UNION/INTERSECT/EXCEPT | ~3% | ~20% | ~3% |
| Self-Join | ~1% | ~15% | ~5% |

### 5.4 Current NL2SQL System Accuracy by Tier

| Tier | Best System Accuracy (2025) | Notes |
|------|---------------------------|-------|
| Tier 1 | ~90-95% | Well-handled by all modern systems |
| Tier 2 | ~75-85% | Schema linking and filter value resolution are the bottleneck |
| Tier 3 | ~40-60% | Time intelligence requires explicit semantic layer support |
| Tier 4 | ~20-40% | Complex SQL generation is unreliable |
| Tier 5 | ~0-5% | Requires refusal detection, not SQL generation |

**The 85% plateau:** Research consistently shows NL2SQL accuracy plateaus at ~85% on academic benchmarks. This number is misleading for enterprise deployment because (a) benchmarks over-represent Tier 1-2, (b) benchmarks under-represent window functions, CTEs, and semi-additive measures, and (c) benchmarks use execution accuracy which can be gamed by returning the right answer via wrong SQL.

Sources: [NL2SQL survey](https://arxiv.org/abs/2408.05109), [Evaluating LLMs on complex SQL](https://arxiv.org/html/2407.19517v1), [NL2SQL is a solved problem... Not!](https://www.cidrdb.org/cidr2024/papers/p74-floratou.pdf)

---

## Implications for Cortex

### What This Proves

1. **Looker's `period_over_period` measure type covers the single most common "hard" query pattern (C1/C2 at ~20% of queries).** This is why Looker as semantic layer is the right architectural choice -- it natively handles the pattern that would otherwise require window function SQL generation, which LLMs fail at.

2. **Semi-additive measures (E5) are the most dangerous blind spot.** No semantic layer except AtScale treats them as first-class. In Looker, you must manually ensure single-snapshot semantics via explore configuration. A single missing partition filter on accounts_in_force produces a result that is ~90x wrong. This must be an invariant in Cortex.

3. **Tier 1+2 queries account for ~60% of real traffic and are achievable at 90%+ accuracy.** This is the May 2026 target. Do not chase Tier 3-4 until Tier 1-2 is rock solid.

4. **The filter value resolution problem (E2) is the highest-leverage unsolved problem for Cortex.** It appears in ~10-15% of ALL queries, and it is the difference between "Millennial" (exact match, easy) and "small business" -> "OPEN" (synonym resolution, hard). This is what ADR-007/ADR-008 address.

5. **Benchmarks systematically under-test the patterns that matter most for Amex.** Window functions (0% in Spider), CTEs (0% in Spider), semi-additive measures (0% in all benchmarks), and fiscal calendars (0% in all benchmarks) are all absent. Our golden dataset MUST include these patterns.

### What the Existing Taxonomy Already Covers

The document at `/Users/bardbyte/Desktop/amex-leadership-project/cortex/docs/design/metric-taxonomy.md` is already comprehensive. It covers all 8 families (A through H) with 32 types, includes Amex-specific SQL examples, LookML expressibility assessments, NL-to-SQL difficulty ratings, and frequency estimates. The two additions from this research (H11: CAGR, H12: Conditional Ranking) are minor. The existing taxonomy is production-ready as a reference document.

### The Coverage Gap

The critical gap is not in the taxonomy but in the **golden dataset coverage**. For the May 2026 demo, the golden dataset should include at minimum:

| Family | Priority Patterns | Minimum Test Cases |
|--------|------------------|-------------------|
| A (Simple Agg) | A1, A2, A3 | 15 |
| B (Ratio/Derived) | B1, B2, B5 | 10 |
| C (Time Intel) | C1, C2, C4 | 10 |
| D (Ranking) | D1 | 5 |
| E (Cross-Entity) | E1, E2, E5 | 15 |
| F (Comparison) | F2 | 5 |
| G (Set Ops) | G1 | 3 |
| H (Misc) | H8 | 3 |
| **Total** | | **~66 cases** |

This covers ~85% of real query traffic with ~66 test cases. The remaining 15% (Tiers 4-5) should be deferred to post-May.

---

## Sources

- [dbt MetricFlow documentation](https://docs.getdbt.com/docs/build/metrics-overview)
- [dbt Cumulative metrics](https://docs.getdbt.com/docs/build/cumulative)
- [dbt Derived metrics](https://docs.getdbt.com/docs/build/derived)
- [Looker measure types](https://docs.cloud.google.com/looker/docs/reference/param-measure-types)
- [Period-over-period measures in Looker](https://cloud.google.com/looker/docs/period-over-period)
- [Cube measures documentation](https://cube.dev/docs/product/data-modeling/reference/measures)
- [Cube types and formats](https://cube.dev/docs/product/data-modeling/reference/types-and-formats)
- [Snowflake semantic views overview](https://docs.snowflake.com/en/user-guide/views-semantic/overview)
- [Cortex Analyst semantic model spec](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec)
- [Databricks metric views](https://docs.databricks.com/aws/en/metric-views/)
- [Databricks metric view composability](https://docs.databricks.com/aws/en/metric-views/data-modeling/composability)
- [AtScale semi-additive measures](https://documentation.atscale.com/installer/creating-and-sharing-cubes/creating-cubes/modeling-cube-measures/types-of-cube-measures/semi-additive-measures)
- [Lightdash metrics reference](https://docs.lightdash.com/references/metrics)
- [Tableau calculation types](https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_understand_types.htm)
- [Tableau LOD expressions](https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_lod.htm)
- [Power BI Time Intelligence DAX guide](https://powerbiconsulting.com/blog/power-bi-time-intelligence-dax-complete-guide-2026)
- [DAX time patterns](https://www.daxpatterns.com/standard-time-related-calculations/)
- [Preset/Superset metrics docs](https://docs.preset.io/docs/using-metrics-and-calculated-columns)
- [Opening up the Looker semantic layer](https://cloud.google.com/blog/products/business-intelligence/opening-up-the-looker-semantic-layer)
- [Introducing Looker Modeler](https://cloud.google.com/blog/products/data-analytics/introducing-looker-modeler)
- [Semantic Layer 2025 comparison](https://www.typedef.ai/resources/semantic-layer-metricflow-vs-snowflake-vs-databricks)
- [Spider benchmark paper (EMNLP 2018)](https://arxiv.org/abs/1809.08887)
- [Spider Yale challenge](https://yale-lily.github.io/spider)
- [BIRD benchmark](https://bird-bench.github.io/)
- [BIRD original paper](https://arxiv.org/abs/2305.03111)
- [Understanding noise in BIRD](https://arxiv.org/html/2402.12243v4)
- [Evaluating LLMs on complex SQL workload](https://arxiv.org/html/2407.19517v1)
- [NL2SQL survey (2024)](https://arxiv.org/abs/2408.05109)
- [NL2SQL is a solved problem... Not! (CIDR 2024)](https://www.cidrdb.org/cidr2024/papers/p74-floratou.pdf)
- [NL2SQL-BUGs benchmark](https://arxiv.org/pdf/2503.11984)
- [VLDB 2025 NL2SQL survey](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/VLDB25-NL2SQL.pdf)
- [Spider 2.0](https://spider2-sql.github.io/)
- [Kimball Group on additivity](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/additive-semi-additive-non-additive-fact/)
- [Semi-additive measures in DAX (SQLBI)](https://www.sqlbi.com/articles/semi-additive-measures-in-dax/)
- [Credit card KPIs executive guide](https://execviva.com/executive-hub/credit-card-kpis)
- [Astrafy Looker PoP analysis](https://medium.astrafy.io/new-pop-measure-in-looker-220d6d842d93)
- [Analysis of Text-to-SQL benchmarks (EDBT 2025)](https://openproceedings.org/2025/conf/edbt/paper-41.pdf)