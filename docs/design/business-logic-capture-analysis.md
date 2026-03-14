# The Business Logic Capture Problem: First-Principles Analysis

## Definitions

Before reasoning about this problem, I define every term precisely.

**Business Logic (for NL2SQL):** A mapping from a human-interpretable concept to an exact database predicate or transformation. Specifically, three subtypes:

1. **Value Mappings:** Human term to exact DB value. "small business" maps to `bus_seg = 'OPEN'`. The column value `'OPEN'` is arbitrary -- it could be `'SB'` or `'7'`. The mapping is pure institutional convention.

2. **Derivation Rules:** A computation that creates a new concept from raw columns. `generation = CASE WHEN birth_year >= 1997 THEN 'Gen Z' ...` The birth year cutoffs for generational cohorts are not stored in the database. They are external knowledge encoded in SQL.

3. **Semantic Predicates:** Conditions that define a business concept. "active customer" means `billed_business > $50` (standard) or `> $100` (premium). The threshold is a business decision, not a data property.

**Source of Truth:** A system from which business logic can be extracted with known reliability. I characterize each source by (a) coverage (what fraction of business logic it contains), (b) precision (what fraction of extracted logic is correct), and (c) freshness (how current the information is).

**Coverage:** The fraction of all business logic instances that a source can provide. If there are N total business logic mappings needed across the enterprise, and a source captures M of them, coverage = M/N.

**Correctness (Precision):** The fraction of extracted mappings that are actually right. If a source produces K mappings and J are correct, precision = J/K.

---

## Axioms (Measured / Verified)

From examining the codebase:

1. **The Finance BU has 7 curated LookML views with 41 fields (dimensions + measures) across 5 explores.** (Measured from `filter_catalog.json` and `.view.lkml` files.)

2. **Of these 7 views, 13 dimensions are filterable string/yesno types.** (Measured from ADR-007.)

3. **The filter value catalog currently contains ~70 distinct values across those 13 dimensions.** (Measured from ADR-007 scale analysis.)

4. **The manually curated `FILTER_VALUE_MAP` has ~40 synonym mappings.** These were hand-built by reading LookML descriptions and Ayush's data dictionary. (Measured from ADR-007.)

5. **Amex has 8,000+ datasets in BigQuery, with tables having 100-500+ columns.** The `cmdl_card_main` table alone has 500+ columns; the curated LookML view exposes ~20. (Stated in view header comments.)

6. **BQ `INFORMATION_SCHEMA.JOBS_BY_PROJECT` retains 180 days of query history.** `INFORMATION_SCHEMA.JOBS_BY_ORGANIZATION` also retains 180 days. (Confirmed from Google Cloud documentation.)

7. **Looker System Activity History retains 90 days of query data.** (Confirmed from Looker documentation.)

8. **BQ INFORMATION_SCHEMA queries are billed at $5/TB with a 10 MB minimum per query.** (Google Cloud pricing.)

---

## Assumptions (Needs Validation)

A1. **Amex analysts have been running queries against BQ for 2+ years, generating substantial query log volume.** At enterprise scale with thousands of analysts, this is near-certain but unverified.

A2. **The 8,000 datasets include significant redundancy -- many are staging tables, test tables, or derivatives.** A reasonable estimate is that 1,000-2,000 are "production" analytical tables that analysts actually query.

A3. **Renuka's Lumi enrichment store will capture dimension descriptions and synonyms, but NOT derivation rules (CASE statements) or threshold predicates (billed_business > $50).** This needs verification with Renuka.

A4. **The fraction of columns in any given table that carry business logic (as defined above) is small -- roughly 5-15% of columns are categorical dimensions with coded values.** The rest are numeric measures, dates, or IDs.

---

## Part 1: Source-by-Source Analysis

### Source 1: BigQuery INFORMATION_SCHEMA.JOBS (Query Logs)

**What it contains:** The `query` column stores the full SQL text of every query run in the project. The `user_email` identifies the analyst. The `total_bytes_processed` indicates query scale. The `referenced_tables` array identifies which tables were touched.

**What can be extracted:**

**(a) WHERE clause patterns -- Value Mappings**

From 180 days of query history, you can extract patterns like:
```sql
-- From query logs, extract:
WHERE bus_seg = 'OPEN'          -- "OPEN" is a valid bus_seg value
WHERE bus_seg IN ('OPEN','CPS') -- "OPEN" and "CPS" are both valid
WHERE generation = 'Gen Z'      -- "Gen Z" is a valid generation value
```

The extraction algorithm:
1. Parse each query SQL text (using `sqlglot` or similar SQL parser -- BigQuery SQL is well-structured)
2. Find all `WHERE` clause predicates of the form `column = 'literal'` or `column IN ('literal', ...)`
3. Group by (table, column, literal_value)
4. Count occurrences and distinct users

**Precision estimate for value extraction:** HIGH (~95%). If 50 different analysts have written `WHERE bus_seg = 'OPEN'` across 500 queries, there is near-zero probability that `'OPEN'` is not a valid `bus_seg` value. The SQL ran successfully and returned results.

**Coverage estimate for value extraction:** MEDIUM (~60-70%). Not every column/value combination will appear in query logs. Rarely-used filter values (e.g., an obscure merchant category) may have zero query log hits. Values that analysts always SELECT but never filter on will be missed.

**(b) CASE statement patterns -- Derivation Rules**

```sql
-- From query logs, extract CASE WHEN patterns:
CASE WHEN birth_year >= 1997 THEN 'Gen Z'
     WHEN birth_year BETWEEN 1981 AND 1996 THEN 'Millennial'
     ...
END
```

**Precision estimate for CASE extraction:** MEDIUM-HIGH (~80-85%). CASE statements in production analyst queries represent business logic that was deemed correct at time of writing. However:
- Different analysts may use different cutoffs (one uses `>= 1997` for Gen Z, another uses `>= 1996`)
- CASE statements may be outdated (definitions change over time)
- Ad-hoc exploratory queries may contain one-off CASE logic not suitable for production

**Coverage estimate for CASE extraction:** LOW-MEDIUM (~30-40%). Most derivation rules are embedded in views, dbt models, or BI tools -- not written repeatedly in ad-hoc queries. An analyst who uses a pre-built dashboard doesn't write the CASE statement themselves. The CASE only appears in logs if an analyst wrote it raw. Furthermore, many CASE statements are defined once in a view or ETL pipeline and then referenced by name -- the downstream queries just use the materialized column.

**(c) Conflict detection -- The critical failure mode**

When different analysts define the same concept differently, the query log will surface conflicting definitions:
```sql
-- Analyst A (Finance team):
WHERE billed_business > 50  -- "active" threshold

-- Analyst B (Marketing team):
WHERE billed_business > 100 -- "active" threshold
```

This is both a bug and a feature. The query log EXPOSES definitional conflicts rather than hiding them. But resolving them requires human judgment.

**Quantified conflict rate estimate:** Based on research showing that 14% of NL2SQL queries have inherent ambiguity (CIDR 2024, Microsoft + Waii.ai), and the Finance BU has 23 identified ambiguity pairs, I estimate 10-20% of extracted business logic will have conflicting definitions from different teams. These conflicts must be resolved by a domain expert; automation cannot resolve them.

**Cost analysis:**

At enterprise scale, the JOBS_BY_ORGANIZATION view could contain hundreds of millions of job records over 180 days. Querying it with filters:

```sql
SELECT query, user_email, creation_time, referenced_tables
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_ORGANIZATION
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
  AND statement_type = 'SELECT'
  AND state = 'DONE'
  AND error_result IS NULL
```

Estimated scan: At Amex scale (thousands of analysts, millions of queries), the JOBS table could be 50-200 GB for 180 days. At $5/TB, that's $0.25-$1.00 per full scan. With partition pruning on `creation_time`, you can reduce this further. This is negligible cost.

However, the SQL parsing step is compute-intensive. Parsing millions of SQL statements through `sqlglot` is an offline batch job, not a real-time operation. Estimated compute: A few hours on a single machine, or minutes on a Dataflow/Spark cluster.

**Summary for Source 1:**

| Business Logic Type | Coverage | Precision | Failure Mode |
|---------------------|----------|-----------|-------------|
| Value Mappings (WHERE clause values) | 60-70% | ~95% | Rarely-used values missing |
| Derivation Rules (CASE statements) | 30-40% | 80-85% | Conflicting definitions, outdated logic |
| Semantic Predicates (thresholds) | 20-30% | 70-80% | Multiple thresholds for same concept |
| Human-readable synonyms | ~0% | N/A | Query logs contain DB values, not human terms |

**Critical insight:** Query logs are excellent at telling you WHAT values exist and HOW they are used. They are terrible at telling you WHAT THEY MEAN in human language. The log shows `bus_seg = 'OPEN'` but does not tell you that `'OPEN'` means "Small Business." That semantic mapping is tribal knowledge.

---

### Source 2: BigQuery Column Statistics & Metadata

**What it contains:**

- `INFORMATION_SCHEMA.COLUMNS`: column names, data types, descriptions (if populated)
- `INFORMATION_SCHEMA.TABLE_OPTIONS`: table descriptions, partition/clustering info
- `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`: nested column metadata
- `SELECT DISTINCT column_name FROM table`: actual values
- `APPROX_TOP_COUNT(column, N)`: approximate top-N values with counts

**What can be extracted:**

**(a) Valid value enumeration -- Complete**

For any column, `SELECT DISTINCT` gives you every value that exists. `APPROX_TOP_COUNT` gives the most common values with frequencies, at much lower cost.

**Precision:** 100%. These are the actual values in the database. There are no false positives.

**Coverage of valid values:** 100%. Every value that exists is discoverable.

**Coverage of business logic:** ~15-20%. Knowing that `bus_seg` has values `{'OPEN', 'CPS', 'GCS', 'GMNS'}` is necessary but not sufficient. You still don't know:
- What "OPEN" means in human language
- Whether "OPEN" maps to "small business" or "open accounts"
- Which CASE statement derivations are correct
- What thresholds define business concepts

**(b) Column descriptions -- Sparse**

BQ column descriptions are populated if someone wrote them during table creation or via `ALTER TABLE ... SET OPTIONS`. At Amex, with 8,000 datasets, my estimate:
- ~5-10% of columns have useful descriptions
- ~20-30% have generic auto-generated descriptions
- ~60-70% have no description at all

The Finance BU LookML already captures some descriptions (marked `[CONFIRMED]` vs `[INFERRED]` in the view files), but these were reverse-engineered, not pulled from BQ metadata.

**(c) Partition and clustering metadata -- Complete and critical**

Partition columns and clustering columns are fully discoverable from `INFORMATION_SCHEMA.COLUMNS`. This is high-value, zero-ambiguity metadata. You MUST have it to avoid full table scans (the invariant in your pipeline design).

**Cost analysis:**

`SELECT DISTINCT` on a partitioned table scanning one partition: ~$0.01-0.05 per column depending on table size. `APPROX_TOP_COUNT` is cheaper (approximate, scans less data). At 13 filterable dimensions for the Finance BU: ~$0.13-$0.65. This matches the ADR-007 estimates.

At scale (1,000 production tables, ~50 filterable dimensions each = 50,000 columns): `APPROX_TOP_COUNT` at $0.01/column = $500 for a full scan. Running against only the latest partition reduces this further. Annual cost for daily refresh: $500 * 365 = $182,500 if you did every column every day. But you only need to refresh curated columns, which are a tiny fraction: realistically 500-2,500 dimensions across 10 BUs = $5-$25/day = $1,825-$9,125/year.

**Summary for Source 2:**

| Business Logic Type | Coverage | Precision | Failure Mode |
|---------------------|----------|-----------|-------------|
| Valid value enumeration | 100% | 100% | None -- these are the actual values |
| Human-readable meaning | 5-10% | ~80% (when descriptions exist) | Most columns have no description |
| Derivation Rules | 0% | N/A | Column stats don't contain CASE logic |
| Semantic Predicates | 0% | N/A | Thresholds are not metadata |
| Partition/clustering info | 100% | 100% | None |

---

### Source 3: Looker System Activity / Usage Analytics

**What it contains:** Looker's History explore tracks every query run through the Looker instance: which explore, which fields, which filters, which filter values, which user, when. Retained for 90 days.

**What can be extracted:**

**(a) Filter usage frequency**

Looker System Activity directly tells you:
- Which filters are applied most often (prioritization signal)
- Which filter values are used most often (validation signal)
- Which explores are queried most often (demand signal)

This is signal for prioritization, not for discovery. It tells you "analysts use `bus_seg = 'OPEN'` 300 times/month" but only for queries that go through Looker. Analysts writing raw SQL in BQ Console or Jupyter are invisible.

**(b) Explore-to-field mapping validation**

If Looker System Activity shows that analysts frequently query explore X with fields A, B, C, this validates that the explore-field mapping in your LookML is correct and covers real use cases.

**Coverage estimate:** LOW (~10-15% of all business logic). Looker System Activity only captures queries run through Looker. At many enterprises, a minority of analytical queries go through the BI tool -- the rest are ad-hoc SQL, notebooks, or programmatic queries. Furthermore, Looker at Amex may not have widespread adoption yet (you are building the LookML layer now, so historical Looker usage data is limited).

**Precision estimate:** HIGH (~95%). If Looker records that filter `bus_seg = 'OPEN'` was applied, that is ground truth for that Looker instance.

**Unique value:** The main value is PRIORITIZATION, not discovery. Use it to answer: "Of all the dimensions and values we've cataloged, which ones do people actually use?" This lets you focus synonym curation effort on the highest-traffic filters.

**Summary for Source 3:**

| Business Logic Type | Coverage | Precision | Failure Mode |
|---------------------|----------|-----------|-------------|
| Filter usage frequency | 10-15% (Looker-only queries) | ~95% | Only captures Looker queries, 90-day window |
| Value validation | Indirect | High | Same |
| Derivation Rules | 0% | N/A | Looker logs don't contain CASE logic |
| Prioritization signal | HIGH | HIGH | Only for Looker users |

---

### Source 4: Renuka's Semantic Enrichment Layer (Lumi)

**What it will contain (when built):** A UX where data stewards enter:
- Column descriptions and business context
- Synonyms and common names for fields
- Domain-specific metadata
- (Possibly) metric definitions and business term glossaries

**What it CAN capture -- and what it CANNOT:**

**(a) Synonym mappings -- YES, with caveats**

If a steward enters that `bus_seg` has values `OPEN = Small Business, CPS = Consumer Personal Services`, etc., this solves the value mapping problem for that column. But this is manual human effort, and the key question is: will stewards actually do this at scale?

Estimated steward throughput: Based on the ADR-008 analysis, ~15 minutes per BU for LLM-bootstrapped synonym review. For 10 BUs with ~200 coded dimensions total, that is approximately 10 * 15 = 150 minutes = 2.5 hours of total steward time for initial bootstrap. This is feasible.

But ongoing maintenance (new values, new columns) requires continuous steward attention. ADR-008 estimates 1-2 hours/week at Phase 2, declining to ~30 min/week at Phase 3 (with auto-approval).

**(b) Derivation rules (CASE statements) -- PROBABLY NOT**

Here is the gap. A steward entering metadata in a UX is unlikely to write:
```sql
CASE WHEN birth_year >= 1997 THEN 'Gen Z'
     WHEN birth_year BETWEEN 1981 AND 1996 THEN 'Millennial' ...
```

This is SQL logic, not descriptive metadata. The enrichment UX would need a specialized interface for defining computed dimensions (business rules as formulas). Based on A3, I assume Lumi does NOT capture this.

**(c) Semantic predicates (thresholds) -- MAYBE**

A steward could document "active customer = billed_business > $50" as a description. But this is unstructured text, not a computable rule. The gap between "the steward wrote it in a description field" and "the pipeline can parse it into a CASE statement" is significant.

**The dependency problem:** Lumi's value depends entirely on steward participation. If stewards actually fill in the metadata, coverage could reach 70-80% for value mappings. If they don't (which is common at enterprises -- metadata initiatives often stall), coverage approaches 0%. This is a social/organizational problem, not a technical one.

**Summary for Source 4:**

| Business Logic Type | Coverage (optimistic) | Coverage (realistic) | Precision |
|---------------------|----------------------|---------------------|-----------|
| Value Mappings (synonyms) | 70-80% | 30-50% | ~95% (human-curated) |
| Column descriptions | 60-70% | 20-40% | ~90% |
| Derivation Rules (CASE) | 0-5% | ~0% | N/A |
| Semantic Predicates | 10-20% | 5-10% | ~80% (natural language, not parseable) |

---

### Source 5: LLM-Assisted Discovery

**What it does:** Given column name, table name, sample values, and any available context, ask an LLM to infer:
- What do these coded values mean?
- What CASE statements might apply to this column?
- What synonyms would a business user use?

**Precision analysis -- by type:**

**(a) Inferring value meanings from column names + sample values**

For some columns, the inference is trivial:
- Column: `apple_pay_wallet_flag`, values: `{Y, N}` --> LLM correctly infers: "Y = enrolled in Apple Pay, N = not enrolled." Precision: ~99%.
- Column: `generation`, values: `{Gen Z, Millennial, Gen X, Baby Boomer}` --> LLM correctly infers the meaning. Precision: ~99%.

For coded values, precision drops sharply:
- Column: `bus_seg`, values: `{OPEN, CPS, GCS, GMNS}` --> An LLM MIGHT guess "OPEN = Open accounts?" or it might know "OPEN is Amex's Small Business brand" from its training data (Amex uses "OPEN" publicly in marketing). Precision: ~50-70% for Amex-specific codes.
- Column: `basic_supp_in`, values: `{B, S}` --> With column description "basic or supplementary card," the LLM can infer "B = Basic, S = Supplementary." Without the description, it is a coin flip. Precision: 30-90% depending on context availability.

**(b) Inferring CASE statement derivation rules**

- Column: `birth_year` (numeric, range 1930-2010), nearby column `generation` --> LLM can plausibly generate a generational CASE statement. But will it use the correct cutoffs? The boundary between Millennial and Gen Z (1996 vs 1997) varies by source. Precision: ~60-70% for the correct structure, but boundary values may differ from institutional definitions.

**(c) The hallucination risk**

For NL2SQL in financial services, a wrong CASE mapping is worse than no mapping. If the LLM hallucinates that `GCS` means "General Card Services" when it actually means "Global Commercial Services," every query using that mapping returns wrong financial data. At $50K per bad query (your stated risk), the expected cost of an LLM hallucination is:

```
E[cost_of_hallucination] = P(hallucination) * P(not_caught) * cost_per_bad_query
```

If P(hallucination) = 15% for coded values, and P(not_caught) = 20% (steward misses the error during review), and cost_per_bad_query = $50K:
```
E[cost] = 0.15 * 0.20 * $50,000 = $1,500 per coded dimension
```

At 200 coded dimensions across 10 BUs: E[total_cost] = $300,000. This is why human review of LLM-suggested mappings is non-negotiable.

**However, with steward review (the ADR-008 approach), the risk drops to:**
```
P(hallucination) * P(steward_misses) = 0.15 * 0.05 = 0.75%
E[cost] = 0.0075 * $50,000 * 200 = $75,000
```

And with the additional guard of golden dataset regression testing catching errors before production:
```
P(hallucination) * P(steward_misses) * P(golden_dataset_misses)
= 0.15 * 0.05 * 0.10 = 0.075%
E[cost] = 0.00075 * $50,000 * 200 = $7,500
```

This is an acceptable risk level with the right guardrails.

**Summary for Source 5:**

| Business Logic Type | Coverage | Precision (without review) | Precision (with steward review) |
|---------------------|----------|---------------------------|-------------------------------|
| Value meanings (self-documenting codes) | ~90% | ~95% | ~99% |
| Value meanings (opaque codes) | ~70% | ~50-70% | ~90-95% |
| CASE derivation rules | ~50% | ~60-70% | ~85-90% |
| Synonym generation | ~80% | ~75-85% | ~95% |

---

## Part 2: The Coverage Model

### What fraction of business logic can each source capture?

I decompose "business logic" into four orthogonal components:

**Component 1: Valid values** (what values exist in each column)
**Component 2: Value meanings** (what those values mean in human language)
**Component 3: Derivation rules** (CASE statements that create new concepts)
**Component 4: Semantic predicates** (thresholds and conditions that define business concepts)

| Source | Valid Values | Value Meanings | Derivation Rules | Semantic Predicates |
|--------|------------|---------------|-----------------|-------------------|
| BQ Query Logs | 60-70% | ~0% | 30-40% | 20-30% |
| BQ Column Stats | 100% | 5-10% | 0% | 0% |
| Looker Usage | 10-15% | ~0% | 0% | 0% |
| Lumi (optimistic) | 0% (not its role) | 70-80% | ~0% | 10-20% |
| Lumi (realistic) | 0% | 30-50% | ~0% | 5-10% |
| LLM Inference | 0% (needs input) | 70-90% (with review) | 50% | 40-50% |

### Combined coverage (using all sources):

**Valid Values: ~100%.** BQ Column Stats gives you this completely. This is a solved problem.

**Value Meanings: ~85-95%.** The combination of Lumi (where stewards participate) + LLM inference (for everything else) + BQ Query Logs (for validation/prioritization) covers the vast majority. The remaining 5-15% are obscure codes used by <1% of queries -- the learning loop (ADR-008) handles these organically over time.

**Derivation Rules: ~50-65%.** This is the hardest problem. Query logs provide some CASE patterns (~30-40%). LLM inference can generate plausible CASE statements (~50%). But conflicting definitions, institutional-specific cutoffs, and evolving rules mean that ~35-50% of derivation rules will require manual authorship by domain experts.

**Semantic Predicates: ~40-60%.** Thresholds like "active = billed_business > $50" are partially discoverable from query logs and partially inferable by LLMs, but require human validation. This is the second-hardest problem.

### The compound coverage formula:

If a query requires all four components to be correct, the overall business logic coverage is bounded by the WEAKEST component (proof by analogy to series system reliability):

```
P(query_correct) <= min(P(valid_values), P(value_meanings), P(derivation_rules), P(semantic_predicates))
```

But not all queries require all four components. The distribution from your query patterns research:

- ~30-35% of queries: Simple aggregation with filters (needs Components 1+2 only)
- ~25-30% of queries: Aggregation with joins and filters (needs Components 1+2+3 for joined dimensions)
- ~15-20% of queries: Time intelligence (needs Components 1+2+4)
- ~10-15% of queries: Complex analytics (needs all four)

**Weighted coverage estimate:**

```
P(correct) = 0.325 * min(1.0, 0.90) + 0.275 * min(1.0, 0.90, 0.575)
           + 0.175 * min(1.0, 0.90, 0.50) + 0.125 * min(1.0, 0.90, 0.575, 0.50) + 0.10 * 0
         = 0.325 * 0.90 + 0.275 * 0.575 + 0.175 * 0.50 + 0.125 * 0.50 + 0
         = 0.293 + 0.158 + 0.088 + 0.063
         = 0.601
```

**The combined automated sources, without human curation, achieve approximately 60% business logic coverage.** This is a ceiling, not a guarantee.

With strong steward participation in Lumi pushing value meanings to 90% and targeted manual CASE authorship pushing derivation rules to 75%:

```
P(correct) = 0.325 * 0.90 + 0.275 * 0.75 + 0.175 * 0.70 + 0.125 * 0.70 + 0
         = 0.293 + 0.206 + 0.123 + 0.088
         = 0.709
```

**With human curation, coverage reaches approximately 70%.** The remaining 30% is the Tier 3-5 complexity that your query patterns research already identified as "graceful refusal" territory.

---

## Part 3: The 8,000 Dataset Reality

### The three tiers of data maturity

At 8,000 datasets, the distribution will be heavily skewed:

**Tier A: Well-Curated (Curated LookML exists):** The Finance BU and eventual 2 additional BUs. ~50-100 tables.
- Business logic: ~80-90% captured in LookML CASE statements, value catalogs, synonyms
- Your pipeline accuracy target: 90%+
- Percentage of all datasets: ~1%

**Tier B: Partially Curated (Some documentation exists):** Tables with BQ descriptions, data dictionaries, or informal Confluence documentation. Perhaps 500-1,000 tables.
- Business logic: ~30-50% capturable via automated extraction + LLM inference
- Pipeline accuracy achievable: ~60-70%
- Percentage of all datasets: ~8-12%

**Tier C: Raw/Undocumented (No semantic layer):** The vast majority. Tables with cryptic column names (`col_a_123_dt`), no descriptions, no data dictionary.
- Business logic: ~10-20% capturable (column stats only)
- Pipeline accuracy achievable: ~20-40% (basically guessing)
- Percentage of all datasets: ~85-90%

**The meta-theorem:** At enterprise scale, the Cortex pipeline will NEVER cover 8,000 datasets with 90% accuracy. It will cover 50-100 curated datasets with 90%+ accuracy, 500-1,000 partially curated datasets with 60-70% accuracy, and the rest will require "I don't have enough context to answer this reliably" responses.

**Therefore:** The strategy is not "capture all business logic across 8,000 datasets." The strategy is "curate the 50-100 highest-value datasets to 90%+ coverage, and have the pipeline honestly refuse queries against uncurated datasets."

This is not a limitation. This is the correct design. A system that gives wrong answers to 85% of the data estate is worse than one that refuses and explains why.

---

## Part 4: The Hierarchy of Business Logic Sources

Ranked by reliability (precision * coverage):

### Rank 1: Human-Authored LookML (your current approach)
- **Reliability:** ~95% precision, ~90% coverage for curated tables
- **Scalability:** ~20 human-hours per BU to write LookML views
- **Role in pipeline:** THE source of truth for CASE statements, value semantics, and predicate definitions
- **Limitation:** Does not scale to 8,000 datasets. Does scale to 10-20 BUs with dedicated effort.

### Rank 2: BQ Column Statistics (SELECT DISTINCT / APPROX_TOP_COUNT)
- **Reliability:** 100% precision for valid values, 0% for meanings
- **Scalability:** Fully automated, pennies per column
- **Role in pipeline:** Populate the value catalog with every valid value. This is the foundation on which everything else builds.
- **Limitation:** Values without meaning are useless for NL2SQL. "The column has 4 values" without "what they mean" is necessary but insufficient.

### Rank 3: BQ Query Logs (INFORMATION_SCHEMA.JOBS)
- **Reliability:** ~95% precision for value usage patterns, ~80% for CASE patterns, ~70% for predicate thresholds
- **Scalability:** Fully automated, pennies per query
- **Role in pipeline:** (a) VALIDATE value mappings by frequency of use, (b) DISCOVER CASE patterns that analysts have written, (c) DETECT conflicting definitions for steward resolution, (d) PRIORITIZE which columns/values matter most (by query frequency)
- **Limitation:** Cannot provide human-meaningful labels. Exposes conflicts without resolving them.

### Rank 4: LLM Inference (Gemini/GPT over column metadata + sample values)
- **Reliability:** 50-95% precision depending on code opacity, ~80% coverage
- **Scalability:** ~$0.05 per BU, fully automated
- **Role in pipeline:** BOOTSTRAP synonym suggestions for steward review. Generate candidate CASE statements for human validation. NEVER use directly without review.
- **Limitation:** Hallucination risk for opaque codes. Must be gated by human review.

### Rank 5: Lumi Enrichment (Steward-Curated Metadata)
- **Reliability:** ~95% precision (human-authored), 30-80% coverage (depends on steward participation)
- **Scalability:** Limited by human availability. 15 min per BU for bootstrap, 1-2 hrs/week ongoing.
- **Role in pipeline:** Ongoing synonym and description enrichment. The long-term steady-state source.
- **Limitation:** Social/organizational dependency. Cannot be commanded; must be enabled and incentivized.

### Rank 6: Looker System Activity
- **Reliability:** ~95% precision, ~10-15% coverage
- **Scalability:** Fully automated
- **Role in pipeline:** PRIORITIZE filter value catalog curation. Validate that LookML coverage matches actual usage.
- **Limitation:** Only captures Looker-routed queries. 90-day window.

---

## Part 5: What Can Be Automated vs. What Requires Human Judgment

### Fully Automatable (Zero Human Effort):
1. **Valid value enumeration** -- `SELECT DISTINCT` / `APPROX_TOP_COUNT` from BQ
2. **Partition/clustering metadata** -- `INFORMATION_SCHEMA.COLUMNS`
3. **Column data type and nullability** -- `INFORMATION_SCHEMA.COLUMNS`
4. **Query frequency by table/column** -- `INFORMATION_SCHEMA.JOBS`
5. **WHERE clause value extraction** -- SQL parsing of query logs
6. **Filter usage prioritization** -- Looker System Activity
7. **Value catalog refresh** -- Daily scheduled pipeline
8. **Exact/fuzzy match resolution** -- Deterministic string matching

### Semi-Automatable (LLM Bootstrap + Human Review):
1. **Value meaning inference** for self-documenting codes (apple_pay_wallet_flag = Y/N)
2. **Synonym generation** -- LLM suggests, steward reviews
3. **CASE statement generation** for common patterns (generational cohorts, age bands)
4. **Column description generation** from column names + sample data

### Requires Human Judgment (Not Automatable):
1. **Opaque code meaning** -- `bus_seg = 'OPEN'` means "Small Business" is institutional knowledge
2. **Threshold definitions** -- `billed_business > $50` as "active" is a business decision
3. **Conflict resolution** -- When two teams define "active customer" differently, a human must choose
4. **Domain-specific CASE logic** -- `basic_cust_noa` = 'New' means "tenure <= 13 months WITH active account" -- the "with active account" qualifier is business logic no LLM can infer
5. **Measure formula definitions** -- `attrition_rate = attrited / total` is a business decision (should denominator include attrited? depend on time period?)

---

## Part 6: The Correctness Assumption -- Quantified

You raised: "we are assuming that it will be run correctly."

### If historical queries are the source of truth for CASE logic:

**Axiom:** BQ query logs contain SQL that successfully executed and returned results. Successful execution does NOT guarantee correct business logic. A query can successfully return wrong results.

**Error rate estimate:**

Based on enterprise data quality research and the CIDR 2024 finding that 14% of NL2SQL queries have inherent ambiguity:

- ~5% of historical analyst queries contain incorrect WHERE clauses (wrong value, wrong column, stale definition)
- ~10-15% contain CASE logic that differs from the "institutional standard" (if one exists)
- ~3% contain outright bugs (wrong join, missing filter, wrong aggregation)

**Propagation analysis:**

If we extract CASE patterns from query logs:
1. **Step 1:** Extract all CASE patterns mentioning `birth_year` and `generation`
2. **Step 2:** Find 50 queries with this pattern
3. **Step 3:** 45 use `>= 1997` for Gen Z, 3 use `>= 1996`, 2 use `>= 1998`

The majority vote (45/50 = 90%) is probably correct. But "probably correct" is not a proof. The 90% could all be copying from the same wrong dbt model.

**Propagation rate into LookML:** If we use majority vote from query logs to generate CASE statements:
- P(error propagation) = P(majority is wrong) * P(reviewer misses)
- P(majority is wrong) estimated at ~5% (based on the observation that most analysts copy from shared templates)
- P(reviewer misses) estimated at ~10% (steward reviewing LLM-generated CASE)
- P(error in production LookML) = 0.05 * 0.10 = 0.5%

At 50 CASE statement dimensions across 3 BUs: expected errors = 0.005 * 50 = 0.25. Roughly one error in four BU onboardings. This is caught by golden dataset regression testing if the golden dataset includes those dimensions.

---

## Part 7: The Recommended Pipeline

### The five-stage business logic capture pipeline:

```
Stage 1: EXTRACT (Automated, Zero Human Effort)
+-- BQ INFORMATION_SCHEMA.COLUMNS -> column names, types, descriptions, partition keys
+-- BQ SELECT DISTINCT / APPROX_TOP_COUNT -> valid values for every string column
+-- BQ INFORMATION_SCHEMA.JOBS -> WHERE clause patterns, CASE patterns, frequency
+-- Output: Raw Skeleton (every table, every column, every value, every pattern)

Stage 2: INFER (LLM-Assisted, No Human Effort)
+-- For each coded column: LLM infers value meanings from name + values + context
+-- For each derived column: LLM generates candidate CASE statements
+-- For each column: LLM generates synonym suggestions
+-- Output: Candidate Business Logic (unvalidated)

Stage 3: VALIDATE (Human-in-the-Loop, ~15 min per BU)
+-- Steward reviews LLM-inferred value meanings (approve/reject/edit)
+-- Steward reviews candidate CASE statements (approve/reject/edit)
+-- Steward resolves conflicting definitions surfaced by query log analysis
+-- Output: Validated Business Logic (production-ready)

Stage 4: ENCODE (Automated)
+-- Validated logic -> LookML CASE statements
+-- Validated value meanings -> dimension_value_catalog synonyms
+-- Validated thresholds -> LookML yesno dimensions
+-- Output: Production LookML + Value Catalog

Stage 5: LEARN (Ongoing, Automated + Steward-Gated)
+-- Failed filter resolutions -> user selection -> synonym suggestions
+-- ADR-008 learning loop: Wilson score auto-approval at scale
+-- New values appearing in BQ -> auto-added to catalog
+-- Query log analysis detects new patterns -> queued for review
+-- Output: Continuously improving business logic coverage
```

### Where the chain of trust breaks:

**Break Point 1: LLM hallucination of opaque codes.**
Mitigation: Steward review gate (Stage 3). Never auto-deploy LLM inferences.

**Break Point 2: Conflicting definitions from different teams.**
Mitigation: Query log analysis surfaces conflicts explicitly. Steward resolves with domain context. Document the resolution in LookML description so it is auditable.

**Break Point 3: Stale business logic.**
Mitigation: Daily value catalog refresh catches new values. Quarterly CASE statement review against query log patterns catches definition drift.

**Break Point 4: Steward non-participation.**
Mitigation: Phase the approach. Start with Finance BU (where you have steward engagement). Prove value. Use success to justify steward time for subsequent BUs. If stewards don't engage, coverage for that BU stays at the automated floor (~60%).

**Break Point 5: The golden dataset doesn't cover the error.**
Mitigation: Golden dataset must include queries that exercise every CASE statement and every coded value mapping. If there are 50 CASE dimensions, there must be at least 50 golden dataset queries testing them. The golden dataset spec (assigned to Animesh) must be designed with this coverage requirement.

---

## Part 8: Red Team

### The counterexample that comes closest to breaking this:

A column called `rel_type` with values `{AA, AB, AC, AD, AE}`. No BQ description. No Looker description. No query log CASE statements mentioning it. The LLM guesses: "AA = Active Account, AB = Active Balance, ..." All wrong. The actual meanings are institution-specific relationship codes that exist only in a mainframe data dictionary from 1998 that nobody has digitized.

**Impact:** The value catalog has the raw values (`AA`, `AB`, ...) but no human-meaningful synonyms. A user asking "show me revolving accounts" cannot be matched to `rel_type = 'AA'`. The pipeline correctly refuses (returns no match) rather than guessing wrong. But the user gets no answer.

**How often does this happen?** At 200 coded dimensions across 10 BUs, I estimate 10-30 dimensions (5-15%) will have truly undiscoverable meanings. These are the "dark matter" of enterprise data -- they exist, they are used by experts who know the codes by heart, and they will require targeted SME interviews to unlock.

**Mitigation:** Prioritize these dimensions by query frequency from BQ logs. If `rel_type` appears in 500 queries/month, it is worth a 30-minute SME interview. If it appears in 2 queries/month, leave it as "graceful refusal" until someone asks.

### Which assumption, if wrong, collapses the chain:

**A4 (5-15% of columns carry coded business logic).** If the actual rate is 30-40%, the manual curation burden triples. At 200 coded dimensions per BU instead of 50, steward bootstrap time goes from 15 minutes to 1-2 hours per BU, and ongoing synonym curation becomes a part-time job. This doesn't collapse the architecture -- it collapses the timeline. Validate by running `SELECT COUNT(DISTINCT column) FROM INFORMATION_SCHEMA.COLUMNS WHERE data_type = 'STRING'` against representative tables.

### The strongest argument for the alternative I rejected:

**"Just let the LLM figure it out in the prompt."** The argument: "You are over-engineering. Gemini 2.0 with a sufficiently large context window can handle 250 values in a few-shot prompt. You don't need a value catalog, a PostgreSQL table, a learning loop, and a steward review queue. You need a good prompt."

**Why this argument is wrong but seductive:**

It works for demos. A well-crafted prompt with all 70 Finance BU values fits in context and resolves correctly ~85% of the time. But:

1. At 3 BUs (250 values), the prompt grows to ~5,000 tokens of value mappings. At 10 BUs (2,500 values), it is 50,000 tokens. Gemini Flash 2.0 can handle this in context, but latency increases linearly and cost increases linearly. The deterministic catalog lookup is O(1).

2. Non-determinism. The same prompt produces different outputs on different calls. For financial data, "it works 93% of the time" means 7% of queries return wrong financial numbers. The value catalog is deterministic -- same input, same output, every time.

3. No learning. When the LLM fails, nothing improves. You need a developer to add a few-shot example. The learning loop captures failures automatically.

4. Proof by contradiction: If the LLM could reliably resolve `'OPEN' = Small Business` from context alone, it would need to have learned this from Amex-specific training data. But Amex internal codes are not in public training data. The LLM is guessing. Sometimes it guesses right (because "OPEN" is used in Amex marketing), sometimes it doesn't. Guessing is not a system architecture.

---

## Recommendation

**The five-source pipeline (BQ stats + Query logs + LLM inference + Lumi enrichment + Learning loop) is the correct architecture. ADRs 007 and 008 already describe the right system.** The analysis in this document provides the mathematical backing for why.

**What this analysis adds to the existing ADRs:**

1. **Query log mining is an underutilized source.** The ADRs focus on `SELECT DISTINCT` for value extraction and learning loops for synonym growth. They do not include query log analysis as a source of CASE patterns, conflict detection, and prioritization. This should be added as a Stage 0 bootstrap step.

2. **The 60% automation floor is realistic.** Without human curation, automated sources cover ~60% of business logic. With steward participation, this rises to ~70-75%. The remaining 25-30% is Tier 3-5 query complexity that should be graceful refusal, not guessing.

3. **Derivation rules (CASE statements) are the hardest gap.** Value mappings are solvable via catalog + synonyms + learning. But CASE statements require either (a) extraction from query logs, (b) LLM inference with human review, or (c) manual authorship. The pipeline should include a dedicated CASE statement discovery module.

4. **The 8,000-dataset scaling question has a clear answer: do not try.** Curate the 50-100 highest-value datasets to 90%+. Let the rest be graceful refusal. A system that is 90% accurate on 1% of datasets and honest about the other 99% is infinitely more valuable than a system that is 40% accurate on everything.

**What would invalidate this analysis:**

- If Amex's BQ query logs are purged or inaccessible (regulatory restriction). This removes Source 1 and its prioritization/CASE discovery value.
- If steward participation in Lumi drops to near-zero for sustained periods. This caps value meaning coverage at the LLM-inferred floor (~70% with high hallucination risk).
- If the actual number of coded dimensions per BU is 3-5x higher than estimated. This doesn't break the architecture but extends the timeline.

**Reversibility:** HIGH. Every component in this pipeline can be turned off or replaced independently. The value catalog is a PostgreSQL table (deletable). The learning loop is a feature flag (disableable). The LLM bootstrap is a one-time script (re-runnable). The query log analysis is an offline batch job (optional). No one-way doors.

---

## Sources

- [BigQuery INFORMATION_SCHEMA JOBS View](https://cloud.google.com/bigquery/docs/information-schema-jobs)
- [BigQuery JOBS_BY_ORGANIZATION View](https://cloud.google.com/bigquery/docs/information-schema-jobs-by-organization)
- [BigQuery Approximate Aggregate Functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/approximate_aggregate_functions)
- [Monitoring Looker Usage with System Activity Explores](https://cloud.google.com/looker/docs/usage-reports-with-system-activity-explores)
- [TailorSQL: An NL2SQL System Tailored to Your Query Workload (VLDB 2025)](https://www.vldb.org/2025/Workshops/VLDB-Workshops-2025/AIDB/AIDB25_2.pdf)
- [BigQuery Query History and INFORMATION_SCHEMA](https://datawise.dev/exploring-the-bigquery-query-history)
- [Using the Query History Log in BigQuery (OWOX)](https://www.owox.com/blog/articles/bigquery-query-history-log/)

---

Key files referenced in this analysis:
- `adr/007-filter-value-resolution.md`
- `adr/008-filter-value-learning-loop.md`
- `config/filter_catalog.json`
- `lookml/views/custins_customer_insights_cardmember.view.lkml`
- `lookml/views/cmdl_card_main.view.lkml`
- `lookml/views/fin_card_member_merchant_profitability.view.lkml`
- `docs/design/financial-query-patterns-research.md`
