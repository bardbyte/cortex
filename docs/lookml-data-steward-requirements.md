# Data Steward Input: What We Need to Make AI Understand Our Data

## Why This Matters

We're building an AI assistant that answers business questions in plain English — "How many Millennial customers are active?" — by querying our data automatically. For this to work, the AI needs to understand what our data *means*, not just what columns exist.

**The problem today:** We built initial models from screenshots and spreadsheets. Many column names, descriptions, and relationships are *guessed*. When we guess wrong, the AI returns wrong answers — or no answer at all.

**What we're asking:** For each table you own, tell us what the data means in business terms. This doc is your checklist.

**Time estimate:** ~30 minutes per table for someone who knows the data well.

---

## The Big Three — If You Fill Out Nothing Else, Do These

These three things have the highest impact on whether the AI can find the right data:

### 1. Business descriptions for every field

Not the column name repeated — what it *means*.

| Bad | Good |
|-----|------|
| "The billed business column" | "Total dollar amount charged to the card member across all transactions in the period" |
| "Customer NOA" | "Age-based generation cohort of the card member — Millennial, Gen X, Boomer, etc. Used for demographic segmentation" |
| "ROC test global" | "Return on Capital at the global level for a card member-merchant relationship. Key profitability indicator" |

### 2. Synonyms — what do people actually call this?

Users don't type column names. They say "spend" not `billed_business`, "generation" not `basic_cust_noa`. List 2-5 alternative names for each field.

| Field | Synonyms users might type |
|-------|--------------------------|
| `billed_business` | total spend, billing volume, card spend, charged amount |
| `basic_cust_noa` | generation, age group, demographic cohort |
| `oracle_mer_hier_lvl3` | merchant category, merchant type, MCC group |

### 3. Coded values — what do the codes mean?

This is where AI fails most. A user asks "show me small business customers" but the column stores `OPEN`. Without a translation table, the AI is stuck.

| Column | Code | What it means | What users say |
|--------|------|--------------|----------------|
| `bus_seg` | OPEN | Small Business / Open cards | "small businesses", "SMB", "open card" |
| `bus_seg` | GCS | Global Consumer Services | "consumer", "personal cards" |
| `card_tier` | PLAT | Platinum card product | "platinum", "plat", "premium" |

---

## Full Checklist

### A. About the Table

Tell us the basics so we set up the model correctly.

| What we need | Example | Why it matters |
|-------------|---------|----------------|
| **Full table name** in BigQuery | `axp-lumid.dw.cmdl_card_main` | We need the exact path to connect |
| **What does one row represent?** | "One row per card member per daily snapshot" | This determines how we count things — getting it wrong means double-counting |
| **Is it a fact table, dimension table, or snapshot?** | Snapshot (daily point-in-time) | Affects how we handle time and joins |
| **Which column(s) uniquely identify a row?** | `cust_ref` for latest snapshot, `cust_ref + partition_date` for historical | Without this, aggregations can be wrong |
| **Roughly how many rows?** | ~100 million | Tells us how aggressive to be on performance |
| **How often does it refresh?** | Daily ETL at 6am ET | Determines caching strategy |
| **Any gotchas?** | "Contains deleted accounts — filter on acct_status = 'A' for active only" | Prevents wrong answers |
| **Who's the go-to person for questions?** | "Finance Data Engineering — John S." | So we can follow up |

### B. About Each Column

For every column we should include (not all 500 — just the ones analysts care about):

**For attributes (things you filter or group by):**

| What we need | Example |
|-------------|---------|
| **Exact column name** in BigQuery | `basic_cust_noa` |
| **Data type** — text, number, date, yes/no | text |
| **Business name** — what humans call it | "Customer Generation" |
| **Description** — what it means, in plain English (see examples above) | "Age-based generation cohort of the card member" |
| **Synonyms** — 2-5 other names people use | generation, age group, demographic segment |
| **Category** — group it with related fields | "Demographics" |
| **Sample values** — 3-5 real values | Millennial, Gen X, Boomer, Gen Z |
| **Does it link to another table?** Which one? | "Joins to ace_organization on org_id" |
| **Contains personal info?** | No |

**For dates:**

| What we need | Example |
|-------------|---------|
| **Exact column name** | `issuance_date` |
| **What this date represents** | "Date the card was issued to the member" |
| **Type** — DATE, TIMESTAMP, or DATETIME | DATE |
| **Is this the table's partition column?** | Yes |
| **Synonyms** | issue date, card open date, acquisition date |

**For numbers you'd sum/average/count (metrics):**

| What we need | Example |
|-------------|---------|
| **Exact column name** | `billed_business` |
| **Business name** | "Total Billed Business" |
| **How to aggregate it** — SUM, COUNT, AVERAGE, COUNT DISTINCT, MAX, MIN | SUM |
| **Description** — what it measures | "Total dollar amount charged to the card member" |
| **Synonyms** | total spend, billing volume, card spend |
| **Unit** — dollars, count, percentage | dollars |
| **What does NULL mean?** Treat as zero? Exclude? | "NULL = no activity, treat as 0" |

### C. Calculated Metrics (Formulas)

For metrics that are calculated from other fields (ratios, rates, indexes):

| What we need | Example |
|-------------|---------|
| **Metric name** | "Revolve Index" |
| **What it tells you** (plain English) | "What proportion of a customer's accounts carry a balance. Higher = more credit usage." |
| **Formula** | revolving accounts / total accounts |
| **What goes into it** — spell out numerator and denominator | Numerator: count of accounts where revolve_flag = 'Y'. Denominator: count of all accounts. |
| **Unit** | Percentage |
| **Synonyms** | revolve rate, revolving ratio |
| **Edge cases** | "Can be undefined for new customers with no accounts yet" |

### D. How Tables Connect

For every pair of tables that analysts query together:

| What we need | Example |
|-------------|---------|
| **Which two tables?** | customer_insights + card_demographics |
| **What column links them?** | Both have `cust_ref` |
| **What's the relationship?** Pick one: | |
| - One customer row matches one demographics row | one-to-one |
| - Many transactions match one customer | many-to-one |
| - One customer has many risk records | one-to-many |
| **Can the link be missing?** (some customers have no match) | "Yes — some customers have no risk record" |
| **Does joining create duplicate rows?** | "Yes — risk table has multiple rows per customer (one per relationship type). Must filter by rel_type or results multiply." |

### E. Coded Value Translations

For every column that stores codes instead of readable values — **this is the most commonly missed item and the #1 reason AI gives wrong answers:**

| What we need | Example |
|-------------|---------|
| **Which column** | `bus_seg` |
| **Every possible value in the column** | OPEN, GCS, GNS, ICS, PROP |
| **What each value means** | OPEN = Small Business, GCS = Global Consumer, GNS = Global Network, ICS = Intl Consumer, PROP = Proprietary |
| **What users would say instead** | "small business" = OPEN, "consumer" = GCS |
| **Do new values get added?** How often? | "Stable — hasn't changed in 2+ years" |

**Start with these columns first:**
- Anything users filter by often (customer segment, product type, region)
- Any status or flag column (active/inactive, premium/standard)
- Any hierarchy column (org level, merchant category, geography)

### F. Business Questions This Data Answers

For each group of tables that go together, tell us:

| What we need | Example |
|-------------|---------|
| **Name for this data view** | "Card Member 360" |
| **3-5 questions it answers** | "Who are our Millennial customers? What's their avg spend? How does tenure affect activity?" |
| **Which tables are involved?** | customer_insights (base) + card_demographics + risk_scores + org_hierarchy |
| **Who uses this?** | Portfolio managers, segment analysts |
| **What are the top 5 queries people run today?** | "Monthly active customers by generation", "Average billed business by card type" |

---

## What Happens With Your Input

```
Your input                  What we build                  What the AI can do
─────────────              ──────────────                 ──────────────────
Business descriptions  →   Rich LookML field metadata  →  Finds the right field when users ask questions
Synonyms               →   Search embeddings           →  "total spend" matches billed_business
Coded value maps       →   Filter resolution           →  "Millennials" resolves to basic_cust_noa = 'Millennial'
Table relationships    →   Correct joins               →  Queries across tables return accurate numbers
Example questions      →   Test cases                  →  We can measure and improve AI accuracy
```

---

## Current Status

We've built initial models for 7 Finance tables. Here's what's confirmed vs guessed:

| Table | What's confirmed | What we need verified |
|-------|-----------------|----------------------|
| `custins_customer_insights_cardmember` | Business terms from spreadsheet | Column names, partition column, join keys |
| `cmdl_card_main` | Some demographics fields from screenshots | Most column names, all coded values |
| `fin_card_member_merchant_profitability` | Merchant category, ROC fields | Column names, exact merchant hierarchy values |
| `tlsarpt_travel_sales` | Travel verticals, booking fields | Column names, trip type codes |
| `risk_indv_cust` | Revolve concept | Column names, rel_type values, relationship to other tables |
| `gihr_card_issuance` | Issuance concept, campaign fields | Column names, campaign code meanings |
| `ace_organization` | Org hierarchy concept | Actual hierarchy level columns |

**Bottom line:** The models work but are built on assumptions. Every assumption that's wrong becomes a wrong AI answer. Your 30 minutes per table saves weeks of debugging.

---

## Template

Copy and fill out for each table. If something is unknown, write "UNKNOWN" — don't leave it blank.

```yaml
table:
  full_path: ""
  what_one_row_represents: ""
  type: ""  # fact | dimension | snapshot
  primary_key: ""
  approx_rows: ""
  refresh_cadence: ""
  gotchas: ""
  owner: ""

columns:
  - name: ""
    type: ""  # text | number | date | yes/no
    business_name: ""
    description: ""
    synonyms: []
    category: ""
    how_to_aggregate: ""  # sum | count | count_distinct | average (metrics only)
    unit: ""  # usd | count | percentage (metrics only)
    null_means: ""
    sample_values: []
    links_to: ""  # other_table.column (if it joins)
    contains_pii: false

coded_values:
  - column: ""
    values:
      - code: ""
        meaning: ""
        users_say: []

formulas:
  - name: ""
    what_it_tells_you: ""
    formula: ""
    pieces: ""
    unit: ""
    synonyms: []
    edge_cases: ""

relationships:
  - tables: ""  # "table_a + table_b"
    link_column: ""
    type: ""  # one-to-one | many-to-one | one-to-many
    can_be_missing: ""  # yes/no
    creates_duplicates: ""  # yes/no — explain if yes

questions_this_answers:
  - ""
  - ""
  - ""
```
