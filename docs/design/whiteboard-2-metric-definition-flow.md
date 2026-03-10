# Whiteboard 2: How Data Stewards Define Metrics (And How AI Uses Them)

**Audience:** Data stewards, Abhishek, Kalyan, non-technical stakeholders
**Format:** Whiteboard walkthrough (draw the ASCII diagrams)
**Duration:** 12 minutes
**Key message:** A data steward fills out a simple form. That single definition powers the AI, the dashboards, and every analyst who asks a question. Define it once, use it everywhere.

---

## Start With the Pain (Draw This First)

```
  TODAY: THE SAME METRIC, DEFINED 5 DIFFERENT WAYS
  ────────────────────────────────────────────────

  ┌──────────┐   "Active Customers" = billed > $0 last 90 days
  │ Analyst A │──────────────────────────────────────────────────
  └──────────┘

  ┌──────────┐   "Active Customers" = billed > $50 last 90 days
  │ Analyst B │──────────────────────────────────────────────────
  └──────────┘

  ┌──────────┐   "Active Customers" = billed > $100 last 90 days
  │ Analyst C │──────────────────────────────────────────────────
  └──────────┘

  ┌──────────┐   "Active Customers" = had a transaction in 6 months
  │ Dashboard │──────────────────────────────────────────────────
  └──────────┘

  ┌──────────┐   "Active Customers" = ???
  │  The AI   │──────────────────────────────────────────────────
  └──────────┘

  RESULT: Same question, 5 different answers.
  Nobody knows which one is "right."
```

**Say:** "This is the problem Cortex solves. Not by guessing, but by having ONE official definition that everyone — humans and AI — reads from."

---

## The Fix: One Definition, Three Users

```
         DATA STEWARD
         (You define it ONCE)
              │
              ▼
  ┌───────────────────────┐
  │   METRIC DEFINITION    │
  │                        │
  │   Name: Active         │
  │         Customers      │
  │         (Standard)     │
  │                        │
  │   Definition:          │
  │   "Card members with   │
  │    billed business     │
  │    > $50 in the last   │
  │    90 days"            │
  │                        │
  │   Formula:             │
  │   COUNT_DISTINCT where │
  │   billed > 50          │
  │                        │
  │   Also known as:       │
  │   "active CMs",        │
  │   "active accounts",   │
  │   "active base"        │
  └───────────┬────────────┘
              │
     ┌────────┼────────┐
     │        │        │
     ▼        ▼        ▼
  ┌──────┐ ┌──────┐ ┌──────┐
  │  AI  │ │Dash- │ │Analyst│
  │Cortex│ │boards│ │ SQL  │
  │      │ │      │ │      │
  │Reads │ │Uses  │ │Sees  │
  │defn, │ │same  │ │same  │
  │finds │ │calc  │ │number│
  │field │ │      │ │      │
  └──────┘ └──────┘ └──────┘

  ALL THREE GET THE SAME ANSWER.
```

---

## What the Steward Actually Does (5-Minute Form)

```
  ┌───────────────────────────────────────────────────────────┐
  │                  METRIC DEFINITION FORM                    │
  │                                                            │
  │  ① WHAT IS IT?                                             │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ Metric Name:    Active Customers (Standard)          │   │
  │  │ Definition:     Card members with billed business    │   │
  │  │                 exceeding $50 in last 90 days        │   │
  │  │ Business Unit:  Finance                              │   │
  │  │ Owner:          Jane Smith, Finance Analytics        │   │
  │  └─────────────────────────────────────────────────────┘   │
  │                                                            │
  │  ② WHAT DO PEOPLE CALL IT?                                 │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ Synonyms:  active CMs, active accounts, active base, │  │
  │  │            active card members, standard active       │  │
  │  │                                                      │  │
  │  │  💡 This is how the AI finds it.                     │  │
  │  │     More synonyms = higher accuracy.                 │  │
  │  │     Think: "what would an analyst type?"             │  │
  │  └─────────────────────────────────────────────────────┘   │
  │                                                            │
  │  ③ HOW IS IT CALCULATED? (optional, for power users)       │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ Formula:  COUNT_DISTINCT(cust_ref)                   │  │
  │  │           WHERE billed_business > 50                 │  │
  │  │           AND partition_date within 90 days          │  │
  │  └─────────────────────────────────────────────────────┘   │
  │                                                            │
  │  ④ ANYTHING ELSE?                                          │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ Related terms:  Active Customers (Premium),          │  │
  │  │                 Total Billed Business                 │  │
  │  │ Required filter: partition_date                      │  │
  │  │ Status:         ☑ Approved                           │  │
  │  └─────────────────────────────────────────────────────┘   │
  │                                                            │
  │              [ Save Definition ]                            │
  └───────────────────────────────────────────────────────────┘
```

**Say:** "That's it. The steward fills this out in 5 minutes. No SQL, no code, no BigQuery. Just business knowledge. The system handles everything else."

---

## What Happens After the Steward Clicks Save

```
  Steward clicks "Save"
        │
        ▼
  ┌──────────────────────────┐
  │  TAXONOMY STORE           │     The single source of truth.
  │  (Structured database)    │     Every definition lives here.
  │                           │
  │  "Active Customers        │
  │   (Standard)"             │
  │   + definition            │
  │   + synonyms              │
  │   + formula               │
  │   + owner                 │
  └──────────┬────────────────┘
             │
             │ AUTOMATIC (no human needed)
             │
     ┌───────┼───────────────┐
     │       │               │
     ▼       ▼               ▼

  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │  LookML     │  │  AI Vector │  │  AI Graph  │
  │  Generation │  │  Index     │  │  Update    │
  │             │  │            │  │            │
  │ Updates the │  │ Embeds the │  │ Adds the   │
  │ field       │  │ description│  │ business   │
  │ description │  │ + synonyms │  │ term node  │
  │ with        │  │ into       │  │ and links  │
  │ synonyms    │  │ pgvector   │  │ to fields  │
  └─────────────┘  └────────────┘  └────────────┘

  ALL THREE UPDATE AUTOMATICALLY.
  Next time someone asks "how many active customers?",
  the AI already knows the answer.
```

**Say to Abhishek:** "The steward defines the business knowledge. The system propagates it everywhere. No engineer in the loop for routine updates."

---

## The Three Tiers: Not All Metrics Are Equal

```
  ┌───────────────────────────────────────────────────────────┐
  │                                                            │
  │  TIER 1: CANONICAL (Company-Wide)                          │
  │  ─────────────────────────────────                         │
  │  "Active Customers (Standard)" — billed > $50              │
  │                                                            │
  │  • Approved by Finance leadership                          │
  │  • AI uses this AS THE DEFAULT when someone asks            │
  │    "how many active customers?"                            │
  │  • One definition. No debate.                              │
  │                                                            │
  │  ════════════════════════════════════════════════════       │
  │                                                            │
  │  TIER 2: BU VARIANT (Team-Level Override)                  │
  │  ────────────────────────────────────────                   │
  │  "Active Customers (Premium)" — billed > $100              │
  │                                                            │
  │  • INHERITS from the canonical definition                  │
  │  • Changes ONE parameter ($50 → $100)                      │
  │  • AI knows it exists, offers it when relevant              │
  │  • When user says "active customers", AI asks:             │
  │    "Standard ($50) or Premium ($100)?"                     │
  │                                                            │
  │  ════════════════════════════════════════════════════       │
  │                                                            │
  │  TIER 3: TEAM DERIVED (Ephemeral, No Governance)           │
  │  ────────────────────────────────────────────────           │
  │  "Q4 Active Customers" — billed > $50, Oct-Dec only        │
  │                                                            │
  │  • Created by an analyst for a specific project            │
  │  • NOT in the official taxonomy                            │
  │  • AI won't surface this unless the analyst asks for it    │
  │  • Expires or gets promoted to Tier 2 if useful            │
  │                                                            │
  └───────────────────────────────────────────────────────────┘

  WHY THIS MATTERS:

  Without tiers → 47 definitions of "active customers"
  With tiers    → 1 canonical + 2-3 official variants
                  AI knows which to use and when to ask
```

---

## The Disambiguation Flow (When Metrics Collide)

```
  USER: "How many active customers do we have?"
                    │
                    ▼
  ┌─────────────────────────────┐
  │  AI finds TWO definitions:  │
  │                             │
  │  1. Active (Standard): $50  │  ← Tier 1 (canonical)
  │     Score: 0.92             │
  │                             │
  │  2. Active (Premium): $100  │  ← Tier 2 (variant)
  │     Score: 0.89             │
  │                             │
  │  Gap: 0.03 < 0.05 threshold │
  │  → NEAR MISS DETECTED       │
  └──────────────┬──────────────┘
                 │
                 ▼
  ┌──────────────────────────────────────────────┐
  │                                               │
  │  AI RESPONSE:                                 │
  │                                               │
  │  "I found two definitions of 'active          │
  │   customers' — which one do you mean?         │
  │                                               │
  │   1. Standard: billed > $50 (company default) │
  │   2. Premium:  billed > $100 (Finance team)   │
  │                                               │
  │   Or I can show you both side by side."        │
  │                                               │
  └──────────────────────────────────────────────┘

  THE AI NEVER GUESSES. It asks.
  This is the single most important quality signal.
```

**Say:** "This is what separates us from every other NL2SQL tool. They guess and get it wrong 40% of the time. We detect the ambiguity and ask. That's how you get to 90%."

---

## Real Example: End to End

```
  BEFORE CORTEX                         WITH CORTEX
  ──────────────                         ───────────

  Analyst: "How many active              Analyst: "How many active
  customers in OPEN segment?"            customers in OPEN segment?"
       │                                      │
       ▼                                      ▼
  Opens BQ console                       AI reads taxonomy:
  Searches for table                     • "active customers" →
  Finds custins table                      Active Customers (Standard)
  Picks wrong column                     • "OPEN segment" →
  Forgets partition filter                 bus_seg = 'OPEN'
  Runs full table scan ($87)             • Adds partition_date filter
  Gets wrong number                      • Finds correct explore
  Takes 3 hours                          • Looker generates SQL
       │                                      │
       ▼                                      ▼
  Presents in meeting                    AI responds in 10 seconds:
  Gets challenged                        "There are 2.3M active
  "That's not right"                     customers in the OPEN segment
  Runs it again...                       (billed > $50, last 90 days)"
```

---

## Steward Impact: The Numbers

```
  ┌──────────────────────────────────────────────────────────┐
  │                                                           │
  │  TODAY (Finance BU):                                      │
  │    17 business terms defined                              │
  │    41 fields curated with synonyms                        │
  │    35 test queries passing                                │
  │                                                           │
  │  EACH NEW TERM ADDED BY A STEWARD:                        │
  │    → Instantly searchable by AI                           │
  │    → Automatically deduplicated                           │
  │    → Versioned (who changed what, when)                   │
  │    → Linked to related terms                              │
  │                                                           │
  │  STEWARD TIME PER TERM: ~5 minutes                        │
  │  ENGINEER TIME PER TERM: 0 minutes                        │
  │  (system propagates automatically)                        │
  │                                                           │
  │  VALUE: Every term defined saves analysts                 │
  │         2-4 hours PER QUESTION that uses it.              │
  │         17 terms × 50 analysts × 2 questions/week =       │
  │         ~3,400 hours/year saved. For ONE BU.              │
  └──────────────────────────────────────────────────────────┘
```

---

## The Whiteboard Summary (Final Diagram)

```
  ┌─────────┐         ┌──────────────┐         ┌──────────┐
  │  DATA    │  FORM   │   TAXONOMY   │  AUTO   │  AI +     │
  │  STEWARD │───────▶│   STORE      │────────▶│  LOOKER   │
  │          │ 5 min  │              │         │           │
  │ "What    │        │ • Name       │         │ • Vector  │
  │  does    │        │ • Definition │         │   index   │
  │  this    │        │ • Synonyms   │         │ • Graph   │
  │  metric  │        │ • Formula    │         │   node    │
  │  mean?"  │        │ • Owner      │         │ • LookML  │
  │          │        │ • Tier       │         │   desc    │
  └─────────┘         └──────────────┘         └──────────┘

  STEWARD DEFINES. SYSTEM PROPAGATES. AI USES.

  ┌─────────────────────────────────────────────────┐
  │  The steward is the expert.                      │
  │  The system is the memory.                       │
  │  The AI is the navigator.                        │
  │                                                  │
  │  No one needs to know SQL.                       │
  │  No one needs to know BigQuery.                  │
  │  Everyone gets the same answer.                  │
  └─────────────────────────────────────────────────┘
```

---

## Talking Points for Kalyan/Jeff

1. "Data stewards define metrics in plain English. No code, no SQL, no BigQuery access needed."

2. "One definition powers three systems: the AI, the dashboards, and analyst tools. Same number everywhere."

3. "The three-tier hierarchy prevents the 47-definitions-of-active-customers problem. One canonical truth, controlled variants, and ephemeral team metrics that don't pollute the system."

4. "When two metrics could match, the AI asks — it never guesses. That's how we hit 90% accuracy instead of the industry standard 36%."

5. "Adding a new business term takes a steward 5 minutes. Zero engineer time. The system auto-propagates to vector search, knowledge graph, and LookML descriptions."
