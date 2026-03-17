# LookML Explorer — UX Research & Concept Design
## "What Can I Ask?" Discoverability in a Conversational NL2SQL Interface

**Author:** UX Research (via Saheb)
**Date:** March 16, 2026
**Status:** Research complete — awaiting prioritization decision
**Audience:** Saheb (product decision), Ayush (if we build it), Likhita (downstream impact on intent classification)

---

## The Problem Being Solved

Right now, when a Finance analyst opens Cortex for the first time, they face a blank chat box. There are five starter query cards, but those represent five of the thousands of possible questions. The system has 5 explores, 50+ dimensions, and 30+ measures across the Finance BU alone. Users don't know:

- What topics the system covers (can I ask about delinquency? No. Can I ask about revolve rate? Yes.)
- What vocabulary to use ("spend" or "billed business"?)
- What time ranges are valid (the 365-day partition ceiling is invisible)
- How dimensions and measures combine (can I break down ROC by generation? Yes, but you have to know that explore joins those views)

The result: users either ask questions that Cortex can't answer and lose trust, or they stick to the five starter cards and never discover the system's full capability. Both outcomes are bad.

Saheb's idea is to expose the LookML structure visually — explores, dimensions, measures, relationships — so users understand the shape of what they can query before they ask.

This document researches how existing tools handle this, designs three concepts for Cortex, evaluates each, and assesses patentability.

---

## Section 1: Competitive Landscape — How Existing Tools Handle Discoverability

### 1.1 Looker Explore: The Field Picker (The Expert's Tool)

Looker's native interface for this is the field picker — a left-side panel that shows all available dimensions and measures organized by view, with search, grouping by label, and hover-to-see-description.

**What works:**
- Exhaustive — everything queryable is listed
- Descriptions on hover reduce the vocabulary guessing problem
- Search within the picker narrows the field set
- `group_label` lets developers create thematic clusters ("Demographics", "Activity", "Risk")

**What fails:**
- It's entirely a developer artifact. The field picker assumes you know the difference between a dimension and a measure. Finance VPs do not know this.
- The mental model is "browse a list and check boxes." This is not how people think about business questions.
- There is no concept of "here are the kinds of questions I was designed to answer." The picker shows everything, with no guidance on what matters.
- Relationships between explores are invisible. Nothing tells you "if you want generation + ROC, you need the Merchant Profitability explore, not Card Member 360."
- In Cortex's case, the field picker doesn't exist — users are in ChatGPT Enterprise, a chat shell with no sidebar.

**The lesson:** Exhaustive field listing is a power-user tool. It is not a discoverability tool. The vocabulary problem (dimension vs. measure, view names vs. business names) remains unsolved.

### 1.2 Tableau Ask Data: Lens-Based Scope + Dynamic Suggestions

Tableau's approach is two-layered. First, a Tableau author creates a "lens" — a curated, scoped subset of the data source with only the fields relevant to a specific question domain. Then within that lens, the query interface shows dynamic phrase suggestions that update as the user types.

**What works:**
- The lens model solves the overwhelm problem by hiding irrelevant fields before the user ever sees them. A "Marketing Analysis" lens shows marketing fields; a "Finance" lens shows finance fields.
- Dynamic suggestions as you type give real-time guidance. If you type "total," the system suggests "total spend by merchant category," "total new cards this month," and "total active cardmembers" — showing you what's possible without you having to imagine it.
- Recommended Visualizations (pre-authored examples) show the ceiling of what the lens can produce, setting user expectations correctly.
- Synonym support (adding "vehicle purchased" as a synonym for "New Vehicle Model") partially solves the vocabulary mismatch problem.

**What fails:**
- Lenses require significant author upfront work. This is LookML developer time, not free.
- Dynamic suggestions train users to query in Tableau's keyword syntax, not natural language. Users learn to say "total active cardmembers by generation last 90 days" rather than "how many active customers do we have by generation this quarter?"
- The UX is built for Tableau's query box, not a conversational thread. In a chat context, "type a query and see suggestions update" works differently because the conversation history changes the context.
- When Tableau deprecated Ask Data in 2024 and absorbed it into Tableau Pulse/Copilot, they explicitly acknowledged that the lens-and-suggestions model didn't scale to open-ended conversational queries.

**The lesson:** Scoping + dynamic suggestions work well for structured query composition. They break down in freeform conversation. The lens concept — "here is the curated slice of data for your domain" — is a better mental model than "here is everything in the database."

### 1.3 ThoughtSpot Sage: Starter Questions + Usage-Ranked Suggestions

ThoughtSpot's approach to discoverability has evolved through several generations. The current Sage experience combines two mechanisms:

**Starter questions:** When a user opens a new search, the system presents a set of pre-curated starter questions. These are not random — they are selected by the data team to represent high-value, commonly-asked questions. The goal is to get users past the blank-box paralysis immediately.

**Usage-ranked autocomplete:** As users type, ThoughtSpot's autocomplete is driven by a usage-based ranking ML model. The suggestions are not alphabetical — they rank by what users in your organization actually search for most. "Total spend by merchant" appears before "total spend by merchant hierarchy level 3 by quarter by card type" because the former is queried 10x more often.

SpotIQ (their AI insight engine) separately scans datasets proactively and surfaces "here's something interesting" insights, which indirectly teaches users what the data contains.

**What works:**
- Starter questions are an extremely low-friction way to begin. They also implicitly teach vocabulary — users see "revolve index" in a starter question and learn that's the term to use.
- Usage-ranked suggestions improve over time and align with what matters to your specific organization, not what the vendor thought was important.
- The separation of "browse" (SpotIQ push) and "search" (query pull) covers two different user modes — exploratory and task-driven.

**What fails:**
- Starter questions go stale. If the top 5 questions don't include your question, you're back to guessing.
- Usage ranking helps repeat users, not new users. On day one, there's no usage data to rank. New user experience and experienced user experience are essentially different products.
- The schema — what dimensions and measures exist — is still opaque. ThoughtSpot doesn't expose a visual "here are all the things you can slice by" view. You discover fields through autocomplete, which means you have to already know roughly what you're looking for.

**The lesson:** Starter questions solve blank-box paralysis. Usage-ranked suggestions help repeat users. Neither solves the deep problem: a new user cannot know the shape of the data model without being told.

### 1.4 Power BI Copilot: "Add Items" + On-Demand Schema Summaries

Power BI's Copilot (as of 2025) takes a different approach: instead of exposing schema visually, it lets users attach reports and semantic models to the conversation as context, then asks Copilot to describe what's in them.

A user can say "Provide a detailed summary of this report's contents so I can ask questions" and Copilot generates a natural-language description of what topics and fields the data covers. This is a conversational data dictionary.

The "AI Data Schema" feature lets authors define a focused subset of the semantic model — similar to Tableau's lens — to constrain what Copilot uses when answering.

**What works:**
- "Summarize this report so I can ask questions about it" is a completely natural conversational interaction. It requires no UI innovation — it's just a prompt.
- The summary provides a vocabulary guide without showing raw field names ("the data covers customer acquisition from campaigns, card issuance rates by region, and organic vs. campaign-driven new accounts").
- Authors can scope what Copilot considers, reducing hallucination risk.

**What fails:**
- It places the discoverability burden on the user ("ask me what I can answer"). Users who don't know to do this still face blank-box paralysis.
- The summary is a wall of text. If the model has 50 fields across 5 topics, the summary is overwhelming. There's no visual structure.
- No drill-down: you can't click a topic in the summary and see the specific fields/metrics it covers.

**The lesson:** Conversational data dictionary is a good pattern for discovery, but text-only summaries need structure to be scannable. The "ask me what I cover" prompt is underused because users don't know to ask it.

### 1.5 What None of Them Do Well

After reviewing all four tools, one gap is consistent: **no tool shows the relationship between question topics and underlying data structure in a way that non-technical users can act on.**

Looker shows fields (technical). Tableau shows suggestions (narrow). ThoughtSpot shows starter questions (shallow). Power BI shows text summaries (unstructured).

Nobody shows: "Here are 5 question domains. Each domain has a set of ways to slice the data and a set of metrics to measure. You can mix and match within a domain, and here's what you get when you cross domains."

That is the gap Cortex can own.

---

## Section 2: The Cortex-Specific Discoverability Problem

Before designing solutions, let's be precise about what users need to know.

### 2.1 The Five Explores as Question Domains

The Finance model has five explores, each of which is a distinct question domain:

| Explore (Business Name) | What Questions It Answers | Key Metrics | Key Slices |
|------------------------|--------------------------|-------------|------------|
| Card Member 360 | Who are our customers? How active are they? What's their profile? | Total customers, Active customers (standard/premium), Avg billed business, Total billed business | Generation, Card type, Business segment, Customer tenure, Org hierarchy |
| Merchant Profitability | How profitable are merchant relationships? What drives ROC? | Avg ROC (global), Total merchant spend, Restaurant spend, Dining customer count | Merchant category, Generation (via join), Partition month |
| Travel & Lifestyle Sales | What is our travel revenue? How does it break down? | Total gross TLS sales, Total bookings, Avg hotel cost per night, Avg booking value | Travel vertical, Air trip type, Booking month |
| Card Issuance & Campaigns | How many cards were issued? Which campaigns work? | Total issuances, Pct non-CM initiated (organic vs. campaign) | Campaign code, Issuance month, Org hierarchy |
| Customer Risk Profile | What is the revolve behavior of the portfolio? | Revolve index, Revolving customer count, Total risk customers, Avg risk rank | Generation (via join), Relationship type, Partition month |

### 2.2 The Cross-Domain Combinations (The Join Layer)

This is the hard part. Because explores join multiple views, some questions require you to know which explore enables which cross-domain analysis:

- "ROC by generation" — needs Merchant Profitability (which joins cmdl_card_main for generation)
- "Attrited customers by generation" — needs Card Member 360 (which joins cmdl_card_main)
- "Risk profile by card type" — needs Customer Risk Profile (which joins cmdl_card_main)
- "Travel bookings by generation" — needs Travel Sales (which joins cmdl_card_main)

A user who doesn't know this join structure will ask "show me risk by generation" and may not know which explore to point at. Cortex's pipeline handles this invisibly — but users who are curious about "can this system cross these two things?" don't have a way to find out without just trying.

### 2.3 The Vocabulary Gap

From the query patterns research, there are 23 documented ambiguity pairs where business language maps to multiple possible fields:

- "Total spend" could mean `total_billed_business` OR `total_merchant_spend`
- "Active customers" could mean standard threshold ($50) OR premium threshold ($100)
- "Segment" could mean `bus_seg`, `basic_cust_noa`, or `business_org`
- "Revenue" could mean discount revenue OR billed business

A discoverability surface needs to show users not just "here are the fields" but "here is the business concept, and here is what it means precisely."

### 2.4 The Constraint Layer (What Users Cannot Ask)

The model has hard limits that users bump into:
- Maximum 365-day lookback (enforced invisibly by `sql_always_where`)
- Default 90-day window on all explores (the `always_filter`)
- Certain metrics are not in the model (delinquency rate, net charge-off rate, CLV, market share)

A discoverability surface should set these expectations upfront, not let users discover them through query failures.

---

## Section 3: The Three Concepts

### Concept A: Explore Map — Visual Topic Browser

**Core idea:** A persistent or on-demand panel that shows the five explores as topic cards. Each card expands to show its dimensions and measures in plain-language groupings. Users click any metric or dimension to auto-populate it in the chat input as a query seed.

**Primary persona:** The Business Stakeholder (quarterly user, no SQL, needs to understand scope)
**Secondary persona:** The Daily Analyst (wants to verify "can I ask about X before I type it")

**Interaction flow:**

```
Step 1: User opens Cortex, sees blank chat
Step 2: Below starter cards, a small link: "Explore what I can answer →"
Step 3: Clicking opens the Explore Map panel (slides in from the right, 340px wide)
Step 4: Panel shows 5 topic cards in a vertical stack

┌─────────────────────────────────────────────────────────────┐
│  What can I ask about?                          [X Close]    │
│  Click any topic to explore. Click any metric to ask about it│
│─────────────────────────────────────────────────────────────│
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [person icon] Card Member 360                    [v]   │  │
│  │ Customer profiles, activity, and demographics         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [$  icon] Merchant Profitability                  [v]  │  │
│  │ Merchant ROC, spending patterns, dining analysis      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [plane icon] Travel & Lifestyle Sales             [v]  │  │
│  │ TLS revenue, booking trends, hotel and air metrics    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [card icon] Card Issuance & Campaigns             [v]  │  │
│  │ New card volumes, organic vs. campaign acquisition     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [chart icon] Customer Risk Profile                [v]  │  │
│  │ Revolve index, risk rankings, portfolio risk mix       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│  Data window: Last 90 days (max 365 days)                   │
│  Updated: Daily at 6 AM ET                                  │
└─────────────────────────────────────────────────────────────┘
```

Step 5: User clicks on "Merchant Profitability" to expand it:

```
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [$  icon] Merchant Profitability                  [^]  │  │
│  │ Merchant ROC, spending patterns, dining analysis      │  │
│  │ ─────────────────────────────────────────────────── │  │
│  │ METRICS (what to measure)                             │  │
│  │  [pill] Avg ROC         [pill] Total Merchant Spend   │  │
│  │  [pill] Restaurant Spend [pill] Dining Customers      │  │
│  │                                                       │  │
│  │ SLICE BY (how to break it down)                       │  │
│  │  [pill] Merchant Category                             │  │
│  │  [pill] Generation  [pill] Month                      │  │
│  │                                                       │  │
│  │ SAMPLE QUESTIONS                                      │  │
│  │  "What is avg ROC by merchant category?"              │  │
│  │  "Show restaurant spend by generation last quarter"   │  │
│  │                                                       │  │
│  │ [Ask a question about Merchant Profitability]         │  │
│  └───────────────────────────────────────────────────────┘  │
```

Step 6: User clicks the "Avg ROC" pill → the chat input fills with "What is the average ROC..." and focus moves to the input box, ready for the user to complete or just hit send.

Step 7: Alternatively, user clicks "Ask a question about Merchant Profitability" → sends a meta-query to Cortex: "What questions can I ask about merchant profitability?" → Cortex responds with 5-7 example questions drawn from real query patterns.

**Key design decisions:**

1. Pills, not lists — metrics and dimensions are displayed as clickable chips. This communicates "these are discrete, selectable items" and invites interaction.

2. Plain language labeling — "Avg ROC" not "fin_card_member_merchant_profitability.avg_roc_global". Business names from the LookML `label:` parameter surface here.

3. Two-level hierarchy only — Topic → (Metrics | Dimensions). We deliberately do not expose view names, table names, or LookML field names. The technical model is hidden.

4. Constraint surfacing at the bottom — "Data window: Last 90 days (max 365 days)" is shown once, at the panel footer. Not repeated per explore. Sets expectations without overwhelming.

5. The "out of scope" path — if a user searches within the panel for "delinquency rate" and finds nothing, the panel shows: "Delinquency rate is not currently available. Topics I can answer: [list]." This is better than the user typing it into chat, getting a failure, and losing trust.

**Edge cases:**

| Situation | Handling |
|-----------|----------|
| User clicks a metric from one explore and a dimension from another | The pill stays selected, but when user submits, Cortex resolves to the correct explore. If the combination is impossible (no explore joins them), Cortex says so explicitly. |
| User is in the middle of a conversation | Explore Map shows as a slide-in that doesn't interrupt the chat thread. It's context — not a navigation change. |
| ChatGPT Enterprise shell (production) | Concept A cannot be built in ChatGPT Enterprise. This is a demo/React app only feature. Flag for Saheb: if this gets built, it lives in the Cortex demo app, not in production ChatGPT. |
| Panel becomes stale | Derived from LookML at build time. Needs a CI step that regenerates the panel content when LookML changes. |

**Evaluation:**

Helps or overwhelms? For Business Stakeholders: helps significantly. The card metaphor is scannable. Expanding one card at a time is progressive disclosure. For Daily Analysts: mild help on first use, largely ignored after. For Executives: won't use it — they want the answer in 30 seconds, not a browsing experience.

**Build effort:** Medium. The LookML model can be parsed to generate the panel content statically. The pill-to-chat-input interaction is a few dozen lines of React. The hard part is writing the plain-language descriptions and sample questions — that's content work, not engineering work.

---

### Concept B: Inline Query Assistant — Contextual Suggestions as You Type

**Core idea:** As a user types in the chat input box, the system shows a lightweight dropdown of auto-complete suggestions drawn from the LookML model — but framed as complete business questions, not field names. This brings the discoverability surface directly into the query moment rather than requiring a separate browsing session.

**Primary persona:** The Daily Analyst (types partial queries 20+ times per day, wants speed)
**Secondary persona:** The Business Stakeholder (gets vocabulary assistance without leaving the input)

**Interaction flow:**

```
Step 1: User types "How many" in the input box

┌────────────────────────────────────────────────────────────────────────┐
│ How many|                                                         [>]  │
│────────────────────────────────────────────────────────────────────────│
│ Suggestions:                                                           │
│   How many active cardmembers do we have this month?   [Card Member]  │
│   How many cards were issued last quarter?             [Issuance]     │
│   How many customers have revolving accounts?          [Risk]         │
│   How many dining customers by merchant category?      [Merchant]     │
└────────────────────────────────────────────────────────────────────────┘

Step 2: User types "How many active"

┌────────────────────────────────────────────────────────────────────────┐
│ How many active|                                                  [>]  │
│────────────────────────────────────────────────────────────────────────│
│ Suggestions (narrowed):                                                │
│   How many active cardmembers (standard) do we have?  [Card Member]  │
│   How many active cardmembers (premium) do we have?   [Card Member]  │
│   — — — — — — — — — — — — — — — — — — — — — — — — — — — — — — — — │
│   "active" resolves to: customers with $50+ or $100+ spend.           │
│   Both options available — which do you mean?                         │
└────────────────────────────────────────────────────────────────────────┘
```

The disambiguation hint ("'active' resolves to...") is the critical element. It surfaces the vocabulary problem at the moment the user is typing, before they submit a query that might get the wrong answer.

```
Step 3: User selects "How many active cardmembers (standard)..."
         → Input fills with selected text
         → User can refine ("...by generation last quarter?")
         → User hits send

Step 4: For a query like "show me revenue", where ambiguity is high:

┌────────────────────────────────────────────────────────────────────────┐
│ show me revenue|                                                  [>]  │
│────────────────────────────────────────────────────────────────────────│
│ "Revenue" is ambiguous. Which do you mean?                             │
│   Billed Business — total customer spend charged to cards             │
│   Discount Revenue — merchant fees earned by Amex                     │
│   Travel Revenue (TLS) — T&LS booking revenue                         │
│   [None of these — let me type it differently]                        │
└────────────────────────────────────────────────────────────────────────┘
```

This is a pre-submission disambiguation — the user resolves the ambiguity before the query is sent, which is faster than the current flow (submit ambiguous query → Cortex detects ambiguity → asks clarification → user answers → Cortex re-runs).

**Key design decisions:**

1. Trigger threshold — suggestions appear after 3+ characters. Below that, the signal-to-noise ratio is too low (typing "ho" produces useless suggestions).

2. Suggestion source — suggestions are seeded from two sources: (a) the LookML model's labels and descriptions, filtered to match the partial input, and (b) a pre-indexed library of the 80% coverage queries from the golden dataset. The golden dataset queries are weighted higher because they represent real, validated questions.

3. Explore badge — each suggestion shows which explore it routes to (small pill: "Card Member", "Merchant", etc.). This implicitly teaches users which domain their question belongs to.

4. Max 5 suggestions — no infinite scroll. If the input matches more than 5 suggestions, show the top 5 ranked by: (a) how closely the partial input matches, (b) how often the query type appears in the golden dataset. More than 5 suggestions collapses into "or ask me anything and I'll figure it out."

5. "Escape hatch" always visible — users who are not finding what they want in suggestions see "[Ignore suggestions — send as typed]" at the bottom. This prevents the suggestion panel from feeling like a mandatory step.

6. Mobile consideration — this pattern is desktop-primary, which matches the Amex constraint (minimal mobile usage). On a virtual keyboard, the suggestion panel is unworkable. The system should detect viewport width and disable the dropdown below 768px.

**Edge cases:**

| Situation | Handling |
|-----------|----------|
| User types something out of scope (e.g., "delinquency rate") | No matching suggestions appear. After a 1-second pause with no suggestions, show: "I don't see 'delinquency rate' in my current Finance model. I can answer questions about [5 topic links]." |
| User types something ambiguous with no direct suggestion | Suggestions section shows: "Your question is complex. Try starting with a metric: [Avg ROC] [Total Spend] [Active Customers]..." — metric pills below the empty suggestion list. |
| Suggestions conflict with what user is actually trying to ask | The escape hatch is always there. Also, user feedback ("this wasn't what I meant") feeds back to deprioritize false-positive suggestions. |
| Golden dataset is small initially | Fall back to LookML-only suggestions. As the golden dataset grows, the suggestion quality improves. This is the compound learning loop. |

**Evaluation:**

Helps or overwhelms? For Daily Analysts: high value. This is the ThoughtSpot model applied to chat — vocabulary disambiguation before submission, faster than post-submission disambiguation. For Business Stakeholders: good for discovery ("I didn't know I could ask about dining customers"). For Executives: likely to find the dropdown distracting. Needs to be dismissible quickly.

The risk is that users start treating Cortex as a search typeahead and stop using natural language — they select from suggestions instead of formulating questions. This actually reduces the NL2SQL challenge but may make the product feel less conversational and more like a fancy autocomplete. That is probably fine for the Daily Analyst persona. It is not fine for the Executive persona.

**Build effort:** Medium-high. The suggestion index needs to be built from LookML metadata + golden dataset queries. The real-time matching (partial string → ranked suggestions) is a lightweight local search problem (FAISS or just trie-based string matching on a small corpus). The pre-submission disambiguation panel is novel and requires careful state management (don't show it when the user is mid-sentence, only when they pause for 500ms+).

**ChatGPT Enterprise compatibility:** This concept also cannot be implemented in ChatGPT Enterprise — it requires control over the input box. Lives in the demo app only.

---

### Concept C: Conversational Data Dictionary — "What Can You Tell Me About?"

**Core idea:** Instead of a visual component, the discoverability surface is a built-in conversational capability. Users ask Cortex what it can answer, and it responds with a structured, interactive summary of its own capabilities. No additional UI components required — works inside ChatGPT Enterprise and the demo app equally.

**Primary persona:** The Business Stakeholder (doesn't know what to ask, needs guidance in plain language)
**Secondary persona:** The Executive (wants the fast answer path, but needs orientation once)

**This is the only concept that works in production ChatGPT Enterprise.**

**Interaction flow:**

```
User: "What can you help me with?"

Cortex:
I cover five Finance topics. Here's what I can answer:

CARD MEMBER 360 — Customer Portfolio
  Metrics: Total customers, Active cardmembers (standard or premium),
           Average billed business, Total billed business, Attrition rate,
           Customers with authorized users
  Slice by: Generation, Card type, Business segment, Customer tenure,
            Org hierarchy
  Example: "How many active premium cardmembers by generation in Q4 2025?"

MERCHANT PROFITABILITY — Revenue & Spending
  Metrics: Avg ROC, Total merchant spend, Restaurant spend, Dining customers
  Slice by: Merchant category, Generation, Month
  Example: "What is our average ROC by merchant category last 90 days?"

TRAVEL & LIFESTYLE SALES — TLS Revenue
  Metrics: Total TLS sales, Total bookings, Avg hotel cost per night, Avg booking value
  Slice by: Travel vertical, Air trip type, Month
  Example: "Show me TLS revenue by travel vertical this quarter vs last quarter"

CARD ISSUANCE — Acquisition & Campaigns
  Metrics: Total new cards issued, % organic (non-campaign) acquisitions
  Slice by: Campaign code, Issuance month, Org hierarchy
  Example: "What percentage of new cards last month were organic vs campaign-driven?"

CUSTOMER RISK — Revolve & Risk
  Metrics: Revolve index, Revolving customer count, Avg risk rank
  Slice by: Relationship type, Generation, Month
  Example: "What is the revolve index by generation for the last 90 days?"

DATA WINDOW: I can answer questions about the last 365 days.
Default time range is last 90 days unless you specify otherwise.

NOT AVAILABLE: Delinquency rates, net charge-off rates, CLV, competitor data,
and real-time data (data refreshes daily at 6 AM ET).

What would you like to know?
```

**The progressive version — for users who know roughly what they want:**

```
User: "Can I ask about merchant data?"

Cortex:
Yes. Here's what I can tell you about merchants:

  I have Return on Capital (ROC) by merchant category.
  I have total spend across all merchant categories.
  I have restaurant-specific spend and the count of dining customers.
  I can break any of these down by merchant category, generation, or month.
  Data window: last 90 days (you can ask for up to 365 days).

  NOTE: "Revenue" from merchants means discount revenue (fees Amex earns from
  merchants). "Spend" means what cardmembers charge at those merchants.
  These are different metrics — let me know which you want.

  Try asking: "What is our average ROC for restaurant merchants last quarter?"
```

**The "I can't do this" version — graceful boundary:**

```
User: "Can I ask about delinquency rates?"

Cortex:
Delinquency rates are not in my current Finance model. I can't answer that.

What I can tell you about risk is limited to revolve behavior:
  - Revolve index (proportion of revolving accounts in the portfolio)
  - Revolving customer count
  - Risk rank (avg across segments)

Would any of those help? Or I can point you to the team that owns delinquency data.
```

**The vocabulary clarification flow:**

```
User: "What does 'active' mean in your system?"

Cortex:
Good question — "active" is ambiguous in the Finance model. It can mean two things:

  Active (Standard): A cardmember with $50 or more in billed business
  Active (Premium): A cardmember with $100 or more in billed business

When you ask about active cardmembers, I'll ask which threshold you mean
unless you specify it. You can say "active (standard)" or "active ($50+)"
and I'll use that definition.

Most dashboard queries use the Standard threshold. Let me know your preference.
```

**Key design decisions:**

1. Response format is table-free — the capability summary uses plain text with clear section headers. It is scannable without being a table. Tables inside chat responses are hard to read and don't print/export well.

2. "NOT AVAILABLE" section is explicit — this is critical for trust. A system that proactively tells you what it can't do is more trustworthy than one that waits for you to discover gaps through query failures.

3. The vocabulary clarification is a first-class interaction — Cortex answers "what does X mean?" questions about its own model. These are meta-queries about the system, not about the data. The intent classifier needs to route these correctly.

4. Persistent context — in a multi-turn conversation, if the user has already asked "what can you help me with?", Cortex should not repeat the full capability dump when they ask a follow-up. The system tracks whether capabilities have been explained in the session.

5. Works in ChatGPT Enterprise — this is a pure text interaction pattern. No sidebar, no pills, no panels. It operates entirely within the chat thread. This is the only concept that works in the production environment.

**Edge cases:**

| Situation | Handling |
|-----------|----------|
| User asks "what can you do?" at the start of every session | This is expected behavior for new users. Over time, usage data shows this question frequency decreasing as users internalize the model. If it doesn't decrease, the starter cards are not doing enough. |
| User asks about a metric that partially exists ("what about attrition?") | "I have attrited customer counts. I do not have an attrition rate (a percentage would require total customers as denominator, which I can compute, but this is not a pre-built metric). Want the count or should I calculate the rate from available fields?" |
| User asks about something adjacent to what's available | Show what's close: "I don't have CLV directly. The closest metric I have is avg billed business per active cardmember, which is a spend proxy. Want that?" |
| Intent classifier misroutes a capability question as a data query | The classifier needs a dedicated "capability_question" intent class. If someone asks "can you tell me about revolve index?", the system should answer with a definition, not run a query. |

**Evaluation:**

Helps or overwhelms? For Business Stakeholders: highest value of the three concepts. Plain language, no new UI to learn, works in their natural environment. For Daily Analysts: one-time utility. After the first session, they've internalized the model and never ask "what can you do?" again. For Executives: if this is one of the starter cards ("Ask me what I can answer"), they might use it once. The response needs to be very short for executives — the full capability dump above is too long.

The constraint: this works only if the intent classifier is trained to handle capability questions. Right now, Likhita's intent classification work is focused on routing data queries. Capability questions are a distinct intent class that needs to be added.

**Build effort:** Low (for the conversational pattern). The response content can be hardcoded initially from the LookML model metadata, then made dynamic as the model grows. The hard work is training the intent classifier to recognize "what can you do?" variants as a distinct intent. That is a golden dataset addition (10-15 example capability questions with expected responses) and a new intent class in Likhita's classifier.

---

## Section 4: Comparative Evaluation

### 4.1 Effectiveness by Persona

| Concept | Daily Analyst | Business Stakeholder | Executive | Data Engineer |
|---------|--------------|---------------------|-----------|---------------|
| A: Explore Map | Medium | High | Low | Medium |
| B: Inline Suggestions | High | High | Low | Low |
| C: Conversational Dict | Low (repeat use) | High | Medium | Low |

**Reading:** Concept B wins for Daily Analysts. Concepts A and C tie for Business Stakeholders (different modes: browsing vs. asking). None of them serve Executives — the Executive persona doesn't want discovery, they want the answer.

### 4.2 Implementation Feasibility

| Concept | ChatGPT Enterprise | Demo App | Build Effort | LookML Dependency |
|---------|-------------------|----------|--------------|-------------------|
| A: Explore Map | No | Yes | Medium | Static parse at build time |
| B: Inline Suggestions | No | Yes | Medium-High | Static index + golden dataset |
| C: Conversational Dict | Yes | Yes | Low | Hardcoded → dynamic |

The production reality is stark: Concepts A and B can only live in the demo app. If Cortex is ever running natively (not in ChatGPT Enterprise), those concepts become viable for production. But today, Concept C is the only one that ships to real users.

### 4.3 Risk Assessment

**Concept A risk:** The Explore Map panel becomes stale when LookML changes. If a new explore is added or a field is renamed and the panel isn't regenerated, users see wrong information. This is a trust-breaking failure. Mitigation: the LookML parse must be part of the CI pipeline, not a manual step.

**Concept B risk:** Auto-suggest trains users to query in a specific vocabulary, reducing the NL flexibility that makes Cortex valuable. Also, suggestions that don't match what the user actually wants create friction. The escape hatch ("ignore suggestions") must be prominent, not buried.

**Concept C risk:** If the intent classifier doesn't correctly route capability questions, users asking "what can you do?" get a SQL query run against nothing, which is a confusing failure. Also, the capability response hardcoded in the system prompt goes stale unless there's a process to update it.

### 4.4 Recommendation

Build all three, in this order:

**Phase 1 (now, zero new UI):** Implement Concept C as a new intent class in Likhita's classifier. Add 15 capability-question examples to the golden dataset. Write the capability response template and bake it into the system prompt as a conditional response. This ships to ChatGPT Enterprise. Estimated effort: 2-3 days for Likhita + content writing by Saheb.

**Phase 2 (demo app, next sprint):** Implement Concept A as the Explore Map panel in the demo React app. This is for the demo and for new users. Parse LookML at build time to generate the panel content. Wire pill clicks to the chat input. Estimated effort: 3-4 days for Ayush.

**Phase 3 (demo app, after golden dataset grows):** Implement Concept B inline suggestions once the golden dataset reaches 100+ examples. The suggestion quality depends on having real validated queries to surface. Building it before the golden dataset exists produces low-quality suggestions that erode trust.

---

## Section 5: Patent Evaluation

### 5.1 What's Novel

Three specific patterns in this research may have patent-defensible novelty:

**Pattern 1: Pre-submission semantic disambiguation UI**

The element in Concept B where, as the user types an ambiguous term (e.g., "active"), the input area shows a real-time disambiguation prompt ("'active' resolves to standard ($50+) or premium ($100+) — which do you mean?") before query submission is novel in combination.

Individual parts exist elsewhere:
- ThoughtSpot has autocomplete (but not semantic disambiguation)
- Cortex already has post-submission disambiguation
- No tool combines partial-input detection + semantic conflict detection + pre-submission disambiguation prompt in one UX

The novel combination: detecting semantic ambiguity from a partial natural language input (not a complete query), resolving it to specific field-level conflicts in a semantic layer, and presenting resolution options inline in the input box before query submission.

Prior art concern: Medium. ThoughtSpot's autocomplete is close. The combination with semantic-layer-aware conflict detection is the differentiator. This needs Lakshmi's review to assess what ThoughtSpot has filed.

**Pattern 2: Capability-bounded conversational data dictionary with explicit "not available" disclosure**

The pattern in Concept C where a conversational AI proactively discloses its own capability boundaries in structured natural language — including explicit enumeration of unavailable metrics — is not well-documented in existing BI tooling.

This is distinct from schema documentation (which is technical and developer-facing) and from FAQ systems (which are manually authored). The specific novelty is: a system that (a) knows its own query capability scope from the semantic layer, (b) expresses that scope in business language, (c) explicitly includes a "NOT AVAILABLE" section generated from the gap between schema coverage and the full domain of expected questions, and (d) updates this disclosure dynamically as the schema changes.

Prior art concern: Low-Medium. Power BI Copilot has semantic model summaries but they are human-authored, not generated from schema gap analysis. The "explicit not-available disclosure" pattern is the most novel element.

**Pattern 3: LookML-derived explore-to-question-domain mapping with join-aware discoverability**

The concept underlying Concept A — that an explore is not just a table but a "question domain" defined by the set of questions its join graph enables, and that this question domain can be surfaced as a user-facing browsable topic — is novel as a formalized pattern.

The specific claim would be: automatically deriving a user-facing "topic card" from a LookML explore definition, where the topic's available slices and metrics are determined by traversing the explore's join graph, not just the base view's fields.

Prior art concern: Medium. Looker's field picker traverses joins implicitly, but it doesn't expose this as a "topic with a set of answerable question types." The framing of join graph → question domain → user-facing topic card may be patentable as a UX/system architecture combination claim.

### 5.2 Patent Recommendation

```
POTENTIAL PATENT — Priority 1
Idea: Pre-submission semantic disambiguation for NL2SQL input
Novel aspect: Real-time detection of semantic field conflicts from partial
              natural language input, resolved through inline UI prompt
              before query submission, using a semantic layer as the
              disambiguation authority
Prior art concern: Medium (ThoughtSpot autocomplete is adjacent)
Next step: Discuss with Lakshmi. Draft a disclosure for the
           pre-submission disambiguation loop. Check ThoughtSpot's
           filed patents on search autocomplete.

POTENTIAL PATENT — Priority 2
Idea: Semantic-layer-derived capability disclosure with explicit
      gap enumeration ("not available" section)
Novel aspect: Automated generation of a conversational capability
              summary that includes both available metrics (from schema)
              and unavailable metrics (from domain-expected questions
              minus schema coverage), expressed in business language,
              updated dynamically as the schema changes
Prior art concern: Low-Medium
Next step: Discuss with Lakshmi. This may pair well with the
           filter value resolution patent already in progress.
```

---

## Section 6: What We Learn About Cortex's Core Problem

This research surfaces something important beyond the discoverability feature itself.

The discoverability problem exists because the system is capable but opaque. Users don't know what's possible. The traditional solution is documentation. Cortex's opportunity is different: the capability is already encoded in the LookML model. The question is whether Cortex can read its own schema and express it as user-facing guidance.

This means the LookML model is not just the data access layer — it is the system's self-knowledge. The descriptions, labels, and group labels in the LookML are not just metadata for the retrieval pipeline. They are the raw material for every discoverability surface.

This has a practical implication: every time Renuka's semantic enrichment pipeline adds a description to a dimension or measure, that description should automatically propagate to:
- The retrieval pipeline (already planned)
- The capability response in Concept C (new)
- The Explore Map panel in Concept A (new)
- The inline suggestions in Concept B (new)

The enrichment pipeline and the discoverability layer are the same pipeline, reading the same source. That's an architecture point worth capturing: semantic enrichment → LookML → three surfaces simultaneously. The discoverability features are not a separate system. They are the output of the enrichment pipeline made user-visible.

---

## Section 7: Open Questions for Saheb

1. **ChatGPT Enterprise constraint:** Concepts A and B can only live in the demo app today. If the plan is always to deliver Cortex inside ChatGPT Enterprise, then Concept C is the only long-term viable path and the others are demo-only features. Is that acceptable, or is there a plan to build a standalone Cortex UI over time?

2. **Content ownership:** The capability response in Concept C requires written descriptions of each explore in business language. The LookML `description` fields are a starting point but are written for engineers. Someone needs to translate "Analyze card member spending by merchant category, Return on Capital (ROC) metrics..." into what an analyst actually needs to hear. Is this Saheb's content, or does it come from the business stakeholders who own each domain?

3. **"Not available" list:** The explicit "NOT AVAILABLE" section requires knowing what questions Finance analysts want to ask that Cortex can't answer. The query patterns research gives a starting list (delinquency, charge-off, CLV, market share). But this list goes stale. Who maintains it? Does it get derived automatically from failed queries? That's a feedback loop worth designing explicitly.

4. **Scope creep risk:** The Explore Map (Concept A) is a permanent UI feature, not a one-time investment. As new business units are added (Travel BU, Consumer BU after Finance), the panel needs to show those explores too. Is the panel designed to scale to 30+ explores, or does it stay Finance-only?

5. **Relationship to Renuka's enrichment layer:** The discoverability surfaces are only as good as the LookML descriptions. If Renuka's enrichment pipeline is the canonical source of those descriptions, there is a dependency here. Cortex's discoverability quality is bounded by Renuka's enrichment quality. This is worth surfacing explicitly to avoid a situation where Cortex promises a capability and the underlying description is wrong.

---

## Appendix: The 23 Vocabulary Ambiguities — Discoverability Surface Coverage

| Ambiguous Term | Business Meaning 1 | Business Meaning 2 | Concept A | Concept B | Concept C |
|---------------|-------------------|-------------------|-----------|-----------|-----------|
| Total spend | Billed business (cardmember charges) | Merchant spend (fees) | Pill labels clarify | Pre-submit disambiguation | Definition in capability response |
| Revenue | Discount revenue (merchant fees) | Billed business | Two separate metrics shown | Dropdown before submit | Explicit note in merchant section |
| Active customers | Standard ($50+ threshold) | Premium ($100+ threshold) | Two separate pills | Pre-submit disambiguation | Vocabulary clarification response |
| Segment | Bus seg | Basic cust NOA | Group labels separate them | Suggestions use full names | "Segment means..." clarification |
| Profitability | Avg ROC | Total account margin | ROC labeled explicitly | — | "Profitability means ROC here" |
| Attrition | Count of attrited customers | Attrition rate | Both listed under Card Member 360 | Two suggestions shown | Explicit in Card Member section |
| New customers | Total issuances | basic_cust_noa = 'New' count | — | Two suggestions | Note in Issuance section |
| Travel revenue | TLS gross sales | Merchant spend in travel MCC | Separate explores shown | Explore badge clarifies | Two separate sections |
| Risk | Revolve index | Avg risk rank | Both metrics shown | Both suggestions | Both in Risk section |

Coverage is reasonable across all three concepts. The key gaps are: "new customers" (ambiguous between issuance and status) and cross-explore combinations where the join is non-obvious. Both of these require Concept C (the conversational clarification path) more than a static visual.

---

*End of research document. Decision needed: prioritize or shelve? Recommendation is to implement Concept C immediately (low effort, ships to production) and evaluate demand before investing in Concepts A and B.*
