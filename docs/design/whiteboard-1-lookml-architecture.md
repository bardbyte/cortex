# Whiteboard 1: How LookML Powers Every Business Unit

**Audience:** Abhishek, Kalyan, non-technical leadership
**Format:** Whiteboard walkthrough (draw the ASCII diagrams)
**Duration:** 10 minutes
**Key message:** We built a semantic layer that turns 500-column BigQuery tables into clean, queryable business concepts — and it scales to every BU with the same pattern.

---

## The Problem (Draw This First)

```
  ANALYST TODAY                           WHAT THEY ACTUALLY NEED
  ─────────────                           ──────────────────────

  "What's our billed business              "billed business by generation"
   by generation?"                                    │
         │                                            ▼
         ▼                                    ┌──────────────┐
  Opens BigQuery                              │   Cortex AI   │
  Searches 8,000 datasets                     │  "I know the  │
  Finds 500-column table                      │   right table, │
  Guesses which column                        │   right column,│
  Writes SQL manually                         │   right filter" │
  Gets wrong answer 40% of time               └──────┬───────┘
                                                      │
  ⏱️ 2-4 hours                                   ⏱️ 10 seconds
```

**Say to Abhishek:** "The gap between what analysts need and what they have to do today is the entire value prop. LookML is how we bridge it."

---

## The Three Building Blocks (Draw This)

```
  ┌─────────────────────────────────────────────────────────────┐
  │                        MODEL FILE                            │
  │           (The roof — one per Business Unit)                 │
  │                                                              │
  │   "This is the Finance BU. It connects to BigQuery.          │
  │    Here are the 5 questions you can ask."                    │
  │                                                              │
  │   ┌─────────────┐ ┌──────────────┐ ┌───────────────────┐    │
  │   │  EXPLORE 1   │ │  EXPLORE 2    │ │    EXPLORE 3       │   │
  │   │  Card Member │ │  Merchant     │ │    Travel Sales    │   │
  │   │  360         │ │  Profitability│ │                    │   │
  │   │              │ │               │ │                    │   │
  │   │  "Who are    │ │ "How much do  │ │ "What's our       │   │
  │   │   our card   │ │  merchants    │ │  travel revenue?" │   │
  │   │   members?"  │ │  earn us?"    │ │                    │   │
  │   └──────┬───────┘ └──────┬────────┘ └────────┬──────────┘   │
  │          │                │                    │              │
  └──────────┼────────────────┼────────────────────┼──────────────┘
             │                │                    │
             ▼                ▼                    ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                        VIEW FILES                             │
  │              (The rooms — one per data source)                │
  │                                                               │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
  │  │ Customer │ │  Card    │ │ Merchant │ │ Travel           │ │
  │  │ Activity │ │  Demo-   │ │ Profit-  │ │ Sales            │ │
  │  │          │ │  graphics│ │  ability │ │                  │ │
  │  │ 14 fields│ │ 17 fields│ │ 10 fields│ │ 12 fields        │ │
  │  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘ │
  │                                                               │
  │  Each VIEW = one BigQuery table, CURATED to ~15 fields        │
  │  (The raw tables have 500+ columns. We pick the ones          │
  │   that matter for business questions.)                        │
  └───────────────────────────────────────────────────────────────┘
```

---

## What's Inside a View (Draw One Box, Expand It)

```
  ┌─────────────────────────────────────────────────────────┐
  │  VIEW: Customer Activity (custins)                       │
  │                                                          │
  │  DIMENSIONS (the "by what")          MEASURES (the "what")│
  │  ─────────────────────────           ────────────────────│
  │  • Business Segment                  • Total Customers    │
  │  • Customer Type (NOA)               • Active Customers   │
  │  • Business Organization             • Total Billed Biz   │
  │  • Partition Date ⚡                  • Avg Tenure          │
  │                                      • Accounts in Force  │
  │                                                          │
  │  ⚡ = Partition key. MUST be filtered.                    │
  │      Without it, one query costs $50-100.                │
  │      With it, $0.50.                                     │
  │                                                          │
  │  EVERY field has:                                        │
  │    • Business-friendly label ("Billed Business")         │
  │    • Description + synonyms ("Also known as: spend,      │
  │      total charges, billed amount")                      │
  │    • The AI reads these to find the right field.         │
  └─────────────────────────────────────────────────────────┘
```

**Say to Abhishek:** "The synonym pattern is our secret weapon. When a user says 'spend', the AI knows that means 'billed business'. This is what gets us from 36% to 90% accuracy."

---

## How Explores Connect Views (The Join Story)

```
  EXPLORE: Card Member 360
  "Show me billed business by generation"

         ┌─────────────────────┐
         │  Customer Activity   │  ◄── BASE VIEW (the star of the show)
         │  (custins)           │      Has: billed business, active status
         │                      │
         │  cust_ref ───────────┼──┐
         └─────────────────────┘   │
                                    │   JOIN ON cust_ref
         ┌─────────────────────┐   │
         │  Card Demographics   │ ◄─┘
         │  (cmdl)              │      Has: generation, card product
         │                      │
         │  cust_ref ───────────┤
         └─────────────────────┘

  The EXPLORE says: "You can ask questions that combine
  customer activity + demographics. I know how to join them."

  The AI doesn't write the JOIN — Looker does.
  The AI just picks the right fields.
```

---

## The Per-BU Pattern (How This Scales)

```
  TODAY (Finance BU)                    NEXT (3 BUs by May)
  ──────────────────                    ────────────────────

  finance_model.model.lkml              marketing_model.model.lkml
  ├── 5 Explores                        ├── Card Member 360 (shared)
  ├── 7 Views                           ├── Campaign Performance
  ├── 17 Business Terms                 ├── Digital Engagement
  └── 41 Curated Fields                 └── ~30 new fields

                                        risk_model.model.lkml
                                        ├── Card Member 360 (shared)
                                        ├── Credit Risk Analysis
                                        ├── Fraud Detection
                                        └── ~25 new fields

  ┌──────────────────────────────────────────────────────────┐
  │                    THE KEY INSIGHT                         │
  │                                                           │
  │  Views are REUSABLE.                                      │
  │  Card Demographics (cmdl) appears in ALL BU models.       │
  │  We write it once, every BU gets generation, card type.   │
  │                                                           │
  │  Adding a new BU = write new views for BU-specific data   │
  │                   + compose into explores                  │
  │                   + reuse shared views                     │
  │                                                           │
  │  Estimated effort per new BU: 2-3 weeks (not months)      │
  └──────────────────────────────────────────────────────────┘
```

---

## Cost Protection (Draw the 4 Layers)

```
  QUERY: "Total billed business"
  Table: 5+ PB, 100M+ rows

  Layer 4: Aggregate Table     ← Pre-computed answer. $0.01. Done.
           (if query matches)     "Monthly members by generation" = instant.
                │
                │ miss
                ▼
  Layer 3: Conditional Filter   ← Smart default. Adds card_prod_id filter.
           (cluster key)          BQ prunes 80% of data via clustering.
                │
                ▼
  Layer 2: Always Filter        ← Mandatory. User sees it, can change value.
           (partition_date)       "Last 90 days" = scans 90 partitions, not 365.
                │
                ▼
  Layer 1: sql_always_where     ← Hard ceiling. User can't see or remove.
           (365 day max)          Even if everything else fails, max 1 year scan.

  ┌──────────────────────────────────────┐
  │  Without optimization:  $50-100/query │
  │  With Layer 2 alone:    $0.50-5       │
  │  With aggregate table:  $0.01-0.10    │
  │                                       │
  │  That's 1000x cost reduction.         │
  └──────────────────────────────────────┘
```

**Say to Abhishek:** "Every query our AI generates goes through these 4 layers automatically. We can't accidentally burn $10K on a bad query. Looker enforces this at the infrastructure level."

---

## The Whiteboard Summary (Final Diagram)

```
  ┌──────────────────────────────────────────────────────────┐
  │                                                           │
  │   MODEL  = one per BU (Finance, Marketing, Risk)          │
  │      │                                                    │
  │      ├── EXPLORE = one queryable business question         │
  │      │      │                                             │
  │      │      ├── VIEW = one data source, curated fields     │
  │      │      │      │                                      │
  │      │      │      ├── DIMENSION = "by what" (generation)  │
  │      │      │      └── MEASURE   = "what" (total spend)    │
  │      │      │                                             │
  │      │      └── JOIN = how views connect (cust_ref)        │
  │      │                                                    │
  │      └── COST PROTECTION = 4 layers, automatic             │
  │                                                           │
  │   Each field has synonyms → AI finds the right one         │
  │   Each explore has joins → Looker writes the SQL           │
  │   Each model has cost protection → can't overspend         │
  │                                                           │
  │   WE CURATE. LOOKER EXECUTES. AI NAVIGATES.                │
  └──────────────────────────────────────────────────────────┘
```

---

## Talking Points for Abhishek

1. "We've built the Finance BU with 7 views, 5 explores, 41 curated fields. That covers 17 business terms and 35 test queries."

2. "The synonym-enriched descriptions are what make the AI work. Without them, accuracy is 36%. With them, we're targeting 90%+."

3. "Adding Marketing or Risk as the next BU is 2-3 weeks because we reuse shared views (demographics, org hierarchy)."

4. "The 4-layer cost protection means we can hand this to 100 analysts and not worry about a $50K BigQuery bill."

5. "Looker generates the SQL, not our AI. Our AI picks the right fields. This is fundamentally more reliable than having an LLM write SQL from scratch."
