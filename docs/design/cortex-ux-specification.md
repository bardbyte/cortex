# Cortex UX Specification
## Enterprise NL2SQL Chat Experience

**Author:** UX Research (via Saheb)
**Date:** March 13, 2026
**Status:** Proposed
**Audience:** Saheb, Likhita (intent/response layer), Ayush (UI/CLI), demo review

---

## Design Mandate

> "When you interact with a piece of technology, you shouldn't understand the difficulty in tech that is implemented in the backend. You should leave with a magical experience." — Saheb, channeling Jobs

The entire UX specification flows from this. The user's job is to get an answer. Cortex's job is to run a 3-phase pipeline, resolve filters from a value catalog, call Looker via MCP, and format results. The user should experience none of that. They should experience: ask a question, get a trustworthy answer, ask another question.

The design principle that enables this: **the pipeline is visible only when the user needs it, never when they don't.**

---

## Section 1: Trust Signal Architecture

Trust in a financial enterprise tool is not built through personality or friendliness. It is built through three mechanisms: showing where the data came from, showing how the number was derived, and failing honestly when something is uncertain. Every trust signal in Cortex is designed around one of these three mechanisms.

### 1.1 Confidence Indicators

**Design Decision: Never show raw percentages to non-technical users.**

A "91% confidence" score displayed as a percentage creates more anxiety than trust. If it's right, the user wonders what the 9% risk was. If it's wrong, the number looks like a lie. Instead, confidence maps to one of three states, each with distinct visual and copy treatment.

```
Confidence Mapping:

  >= 0.85  →  [No indicator shown]
                The answer just appears. Silence is confidence.
                The absence of a warning IS the trust signal.

  0.70–0.84  →  [Source context shown inline]
                "Based on Finance Cardmember 360 dataset, last updated 4h ago."
                Subtle. Informational. Not alarming.

  < 0.70  →  [Explicit qualification shown]
                "I'm working with a partial match here — see details below."
                Never hidden, never alarming. Just honest.
```

**Why this works for Amex analysts:** A Daily Analyst running 20 queries a day learns quickly that "no indicator" means clean result. When a subtle note appears, they know to look closer. They don't need a number — they need a signal. This is how Bloomberg terminals work. The absence of a warning is the signal.

**What NOT to do:** Do not show confidence scores in the main response body. Do not use yellow warning triangles or red indicators on results you're still surfacing. Do not use hedging language like "I think" or "approximately" when retrieval confidence is above 0.85 — the system knows the answer.

### 1.2 Source Attribution

Three levels, matched to query type and user persona:

**Level A — Inline citation (default for all results):**
```
Source: Finance Cardmember 360  |  Explore: Card Member Spend  |  Last updated: 4h ago
```
This appears as a single line below the answer, before follow-up suggestions. Always shown. Anchors the result in a real dataset that the analyst can verify exists.

**Level B — Dataset context (shown when retrieval confidence is 0.70–0.84):**
```
This answer draws from the Card Member Spend explore in the Finance Cardmember 360
dataset. The "small business" filter matched to segment code OPEN, which covers
proprietorships and partnerships under $10M annual revenue.
```
This is the filter resolution story told in plain English. The Daily Analyst and Data Engineer will appreciate knowing the translation. The Executive doesn't read it — that's fine.

**Level C — On-demand (shown in Level 2 disclosure, covered in Section 3):**
Full field list, exact Looker model/explore path, filter resolution chain (what the user typed → what value was resolved → confidence of that resolution).

### 1.3 SQL Transparency

**Core principle: SQL is evidence, not interface.**

The user asked a data question. They want the answer. SQL is the receipt — they can check it if they want to, but it should not be the first thing they see.

SQL placement rules:
- Never in the main response body on first render
- Always available in Level 2 disclosure ("How I got this")
- Syntax-highlighted in a collapsible block
- Accompanied by plain-English translation: "This query filters to the last quarter (Q4 2025), restricts to small business segment (OPEN), and sums billed volume across all card products."

The SQL block should include the full query as generated, including the mandatory partition filter. This is both a transparency mechanism and a debugging affordance for the Data Engineer persona — they can copy it, run it manually, and verify. The partition filter being visible also demonstrates that Cortex is being fiscally responsible with BigQuery scan costs.

### 1.4 Pipeline Trace Exposure Policy

The PipelineTrace object contains per-step timing, confidence scores, retrieval decisions, filter resolution chains, and the full decision path. This is too much for most users, exactly the right amount for engineers and for debugging.

```
Trace Exposure by Persona:

  Executive          →  None. Not even the "How I got this" prompt.
                        Answer + number + source citation. Done.

  Business Analyst   →  Source citation (Level A) always.
                        Level 2 available on click, but not prompted.

  Daily Analyst      →  Source citation + follow-up suggestions.
                        Level 2 prompted subtly ("See query details").
                        Level 3 available via /trace command in CLI.

  Data Engineer      →  All three levels available.
                        Level 2 auto-expanded for validation.
                        Full trace JSON accessible via /trace.
```

**What the trace should NEVER show to any user:** Raw stack traces. Internal variable names. SafeChain gateway addresses. CIBIS auth tokens. BigQuery job IDs. These are operational details that erode trust when exposed.

---

## Section 2: Progressive Disclosure — 3-Level Pattern

The same response object (CortexResponse) is rendered at three levels of detail. The rendering level is controlled by user interaction, not by the query type.

### Level 1 — The Answer (Default Render)

This is what 80% of users see 90% of the time. It contains:
1. A direct answer sentence in business language
2. A data table (or single number formatted large)
3. The source citation line
4. Two to three follow-up suggestion chips

Nothing else. No SQL. No pipeline steps. No confidence scores unless confidence is below 0.85.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Total billed business for Small Business customers last        │
│  quarter was $4.2B, up 8.3% from Q3 2025.                      │
│                                                                  │
│  ┌────────────────────────────────────────────────────┐         │
│  │ Quarter    Segment          Billed Volume           │         │
│  │ Q4 2025    Small Business   $4,213,847,200          │         │
│  └────────────────────────────────────────────────────┘         │
│                                                                  │
│  Source: Finance Cardmember 360  ·  Updated 4h ago              │
│                                                                  │
│  ──────────────────────────────────────────────────             │
│  You might also ask:                                             │
│  [Break down by card product]  [Compare to Q4 2024]             │
│  [Show monthly trend]                                            │
│                                                                  │
│                               [ How I got this ▼ ]              │
└─────────────────────────────────────────────────────────────────┘
```

**Copy standard for the answer sentence:**
- Lead with the number or finding, not a preamble
- Name the segment/filter as the user described it ("Small Business"), not as the internal code ("OPEN")
- Include a comparison if the data supports it (QoQ, YoY) — this adds value without the user asking
- Do not say "Based on your query" or "I found that" — start with the fact

### Level 2 — How I Got This (One Click to Expand)

Activated by clicking "How I got this." This is the analyst's receipt. It answers: what data did you use, what did you filter on, and what SQL did you run?

```
┌─────────────────────────────────────────────────────────────────┐
│  [ How I got this ▲ ]                                           │
│                                                                  │
│  DATA SOURCE                                                     │
│  Model:    cortex_finance                                        │
│  Explore:  card_member_spend                                     │
│  Fields:   total_billed_business (measure)                      │
│  Filter:   bus_seg = OPEN  (matched from "small businesses")     │
│            partition_date = last 1 quarters                      │
│                                                                  │
│  QUERY (click to copy)                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ SELECT                                                    │   │
│  │   SUM(total_billed_business) AS total_billed_business     │   │
│  │ FROM card_member_spend                                    │   │
│  │ WHERE bus_seg = 'OPEN'                                    │   │
│  │   AND partition_date >= DATE_TRUNC(                       │   │
│  │     DATE_SUB(CURRENT_DATE(), INTERVAL 1 QUARTER), QUARTER │   │
│  │   )                                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Plain English: Filtered to small business segment (OPEN code)  │
│  for Q4 2025 and summed all billed volume. Partition filter      │
│  applied automatically to control query cost.                    │
│                                                                  │
│  Retrieved in 1.8s  ·  2 LLM calls  ·  Confidence: High        │
└─────────────────────────────────────────────────────────────────┘
```

**Design notes:**
- Filter value translation is always shown: "bus_seg = OPEN (matched from 'small businesses')" — this is the most important trust signal in the entire UI. If the filter translation is wrong, the user catches it here and uses the correction flow.
- Confidence is shown as "High / Medium / Low" at this level, not as a percentage. The percentage lives only in Level 3.
- The SQL block has a copy-to-clipboard affordance. The Data Engineer will use this constantly.
- Response time and LLM call count are shown. This demonstrates the pipeline is efficient and signals that someone thought about cost.

### Level 3 — Full Pipeline Trace (Expert/Debug Mode)

Activated from Level 2 via "View full trace" link, or via `/trace` command in CLI. This is the PipelineTrace object rendered for humans. It maps directly to the `PipelineTrace.to_dict()` output.

```
┌─────────────────────────────────────────────────────────────────┐
│  PIPELINE TRACE  ·  trace_id: a3f9...  ·  Total: 1847ms        │
│                                                                  │
│  STEP 1  Intent Classification          203ms   confidence 0.97 │
│  ─────────────────────────────────────────────────────────────  │
│  Intent:    data_query                                           │
│  Entities:  metric=total_billed_business, filter=bus_seg:small  │
│             businesses, time=last quarter                        │
│  Decision:  proceed                                              │
│                                                                  │
│  STEP 2  Hybrid Retrieval               261ms   confidence 0.91 │
│  ─────────────────────────────────────────────────────────────  │
│  Vector search:   0.89 → card_member_spend.total_billed_business│
│  Graph validation: PASS (explore → view → field path valid)     │
│  Few-shot match:  GQ-fin-003 (similarity 0.94)                  │
│  Decision:  proceed                                              │
│                                                                  │
│  STEP 3  Filter Resolution               14ms                    │
│  ─────────────────────────────────────────────────────────────  │
│  "small businesses" → hash lookup → MISS                        │
│  "small businesses" → fuzzy match → "small business" → HIT      │
│  "small business" → synonym map → OPEN (confidence 1.0)         │
│  partition_date → mandatory inject → last 1 quarters            │
│                                                                  │
│  STEP 4  ReAct Execution                1369ms  1 LLM + 1 MCP  │
│  ─────────────────────────────────────────────────────────────  │
│  Iteration 1: LLM → query-sql → success (1 row returned)        │
│  Iteration 2: LLM → format answer → done                        │
│                                                                  │
│  [ Export trace JSON ]  [ Copy trace_id ]                       │
└─────────────────────────────────────────────────────────────────┘
```

**Who uses this:** Data Engineers validating the retrieval pipeline. Saheb debugging a regression. Likhita tuning intent classification. It is NOT a normal user experience — it is a power tool. The copy for each step should use field names that match the codebase (`bus_seg`, `card_member_spend`) because the person reading this level is cross-referencing with the code.

---

## Section 3: Interaction States

### 3.1 Proceed — Happy Path

This is the Level 1 render described in Section 2. The copy standard:

```
[Answer sentence leading with the number]

[Table or single value]

Source: [Dataset name]  ·  Updated [X]h ago

You might also ask:
[Follow-up 1]  [Follow-up 2]  [Follow-up 3]
```

No filler. No "Great question!" No "I analyzed your query and found..." Start with the answer.

### 3.2 Disambiguate — Two Valid Interpretations Found

This state fires when retrieval returns `action: "disambiguate"` — two Looker explores have similarly high confidence scores for the query. The challenge is making this feel like a smart clarification, not a failure or a bug.

**Design principle for disambiguation:** Present both options as equally valid, with a one-sentence description of each that uses the user's language, not the field names. The user should immediately recognize which one they meant.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Your question could draw from two different datasets.          │
│  Which one are you looking for?                                 │
│                                                                  │
│  A  Small Business Billed Volume                                │
│     Spending by small business cardmembers at merchants.        │
│     Includes all card products. (Finance Cardmember 360)        │
│                                                                  │
│  B  Small Business Credit Portfolio                             │
│     Credit metrics for small business accounts —               │
│     receivables, utilization, credit line. (Credit Risk)        │
│                                                                  │
│  [ Choose A ]   [ Choose B ]                                    │
│                                                                  │
│  Or rephrase — "What was total billed volume..." or             │
│  "What was total credit exposure..."                            │
└─────────────────────────────────────────────────────────────────┘
```

**Copy rules:**
- Never name the Looker model/explore in the option title — name the business concept
- Include the dataset name in parentheses as a secondary label for analysts who know the landscape
- Provide a rephrase suggestion so the user can avoid this state in the future — this trains them
- The two options are presented equally. No default selection. No "I think you mean A." The system does not know which one the user meant — that is the whole point of this state.

**After user selects:** The pipeline continues as if the user had specified that explore from the start. A subtle note appears in Level 2: "You selected: Small Business Billed Volume from Finance Cardmember 360."

**Learning loop trigger:** Each selection is a signal for the retrieval system. If users consistently pick Option A when they type "small business revenue," that context gets fed back to improve disambiguation routing.

### 3.3 Clarify — Low Confidence on Intent or Entities

This state fires when intent classification confidence falls below 0.70, or when a key entity (metric, time range, filter value) is missing or ambiguous. The goal is to ask exactly one clarifying question — not a list of questions — and frame it as a thoughtful analyst making sure they get it right.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  I want to make sure I pull the right number here.              │
│                                                                  │
│  When you say "small businesses" — are you looking at:          │
│                                                                  │
│  - Spending by small business cardmembers at merchants?         │
│  - American Express small business card accounts?               │
│  - Small business clients in the corporate portfolio?           │
│                                                                  │
│  [ Cardmember spending ]   [ Card accounts ]   [ Corporate ]    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**When there are only two options:**
```
I want to make sure I pull the right number here.

"Last quarter" — do you mean Q4 2025 (Oct–Dec) or the trailing
90 days ending today?

[ Q4 2025 ]   [ Trailing 90 days ]
```

**When the clarification is about a missing entity:**
```
Which business unit are you asking about? I have data for
Consumer, Small Business, and Corporate segments.

[ Consumer ]   [ Small Business ]   [ Corporate ]   [ All segments ]
```

**Copy rules:**
- Start with "I want to make sure I get this right" — this signals intent, not failure
- Ask about one ambiguity at a time — the most consequential one
- Offer buttons for the most common options plus a free-text field for edge cases
- Never list more than four options in the buttons — beyond four, ask a free-text question

### 3.4 No Match — Nothing Found

This is the most dangerous state for user trust. If the system says "I don't have that," the user's confidence in the whole system drops. The UX must immediately redirect to what IS possible.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  I don't have data on merchant acquisition costs yet.           │
│                                                                  │
│  Cortex currently covers:                                       │
│  - Billed business and spend volume (Consumer + Small Business) │
│  - Customer segment metrics (by product, region, vintage)       │
│  - Delinquency and credit risk indicators                       │
│  - Card activation and usage trends                             │
│                                                                  │
│  Related questions I can answer:                                │
│  [What is customer acquisition cost for new card members?]      │
│  [What is the spend activation rate by acquisition channel?]    │
│                                                                  │
│  Is one of these close to what you need?                        │
└─────────────────────────────────────────────────────────────────┘
```

**Design rules:**
- First sentence names exactly what wasn't found — not "I couldn't understand your question"
- Immediately show what IS covered — this turns a dead end into a menu
- Offer two specific related questions that use the system's actual data
- End with an open question — leaves the conversation alive
- Never say "I'm just a beta" or "This feature is coming soon" — it undermines the whole interaction

### 3.5 Error / Fallback — System Error During Execution

When Phase 2 fails (SQL execution error, MCP timeout, SafeChain error), the system must handle this without showing any technical details. The fallback path in `CortexOrchestrator` drops to raw ReAct — the UX masks this transition completely.

**First attempt (before fallback triggers):**
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Let me try a different approach...                             │
│                                          [subtle spinner]        │
└─────────────────────────────────────────────────────────────────┘
```

**If fallback succeeds:**
Result renders normally at Level 1. No mention of the error.

**If fallback also fails:**
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  I hit an issue pulling that data right now.                    │
│                                                                  │
│  A few things that might help:                                  │
│  - Try rephrasing with a specific time range ("Q4 2025")        │
│  - Break it into a simpler question first                       │
│  - Try again in a moment — it may be a temporary issue          │
│                                                                  │
│  If this keeps happening, reference trace ID: a3f9...           │
│  and reach out to the Cortex team.                              │
└─────────────────────────────────────────────────────────────────┘
```

**Hard rules for error states:**
- Never show stack traces. Never show internal error codes. Never show "500 Internal Server Error."
- Always give the user an action they can take
- The trace ID is surfaced here so engineers can look up the failure without the user needing to describe it
- "Reach out to the Cortex team" — use team name, not "support" — this is an internal enterprise tool

### 3.6 Out of Scope — Not a Data Question

When intent classification returns `out_of_scope`, the system should redirect clearly and immediately, with no attempt to answer.

```
That's outside what I can help with. I'm a data query tool —
I work best with questions about spending patterns, customer
segments, card metrics, and financial performance.

Try asking something like:
[What was billed volume for Consumer cards last quarter?]
[Show me delinquency rates by vintage for Q4 2025]
```

**Copy rule:** The first sentence is direct. It does not apologize. It names what the system IS, not what it isn't. The examples are specific enough to be immediately actionable.

---

## Section 4: Streaming UX — The 2.4 Second Experience

The pipeline takes ~2400ms P50. The question is: what does the user experience during that time?

**Rejected options:**

"Thinking..." with a spinner — generic, gives the user no information, feels like a loading screen from 2008.

Full step-by-step verbose progress — "Step 1: Classifying intent... Step 2: Running vector search... Step 3: Validating against graph..." — this is the pipeline documentation, not a user experience. It trains users to watch the plumbing, not the answer.

**The right answer:** Staged contextual feedback with a single lightweight progress indicator.

### The Timeline

```
t=0ms    User hits send.

t=0–200ms   Response area appears with the query echoed back
             in a subtle "working on" frame. Nothing more.

             ┌────────────────────────────────────────────────┐
             │  Analyzing: "Total billed business for small   │
             │  businesses last quarter"                       │
             │                                    [   ···   ] │
             └────────────────────────────────────────────────┘

t=200ms  Intent classification completes.
         If the system is proceeding confidently (action=proceed),
         nothing changes. The frame updates only if the system
         needs to communicate something to the user.

         If action=disambiguate → IMMEDIATELY show disambiguation
         state. Do not wait for retrieval to complete.
         If action=clarify → IMMEDIATELY show clarification state.

t=200–460ms  Retrieval running. User sees:

             ┌────────────────────────────────────────────────┐
             │  Analyzing: "Total billed business for small   │
             │  businesses last quarter"                       │
             │                        [Finding relevant data] │
             └────────────────────────────────────────────────┘

             "Finding relevant data" is the only text that updates.
             One phrase. Not a progress bar. Not step names.

t=460–475ms  Filter resolution. Imperceptibly fast. No update.

t=475–1275ms  SQL generation via Looker MCP. User sees:

             ┌────────────────────────────────────────────────┐
             │  Analyzing: "Total billed business for small   │
             │  businesses last quarter"                       │
             │                              [Querying data...] │
             └────────────────────────────────────────────────┘

t=1275–1875ms  LLM formats final answer. The result begins
               streaming in — the answer sentence appears word
               by word, then the table renders all at once.

t=1875ms     Full Level 1 response is visible.
             Follow-up suggestions fade in 300ms after the
             table appears — not simultaneous.
```

### Copy for Each Streaming Phase

| Phase | Indicator text |
|-------|---------------|
| 0–200ms | (no indicator text, just the query echo + dots) |
| 200–460ms | Finding relevant data |
| 460–1275ms | Querying data... |
| 1275ms+ | (answer begins streaming in) |

**Why this approach beats step-by-step progress:**
The analyst's mental model is "ask a question, get an answer" — not "watch the pipeline run." The three phases ("finding," "querying") map to things the user understands: looking up the right data, then getting it. They do not need to know about pgvector, AGE, FAISS, or intent classification. Perplexity does this well — it shows "Searching..." and then "Analyzing..." and then the answer arrives. Cortex should do the same at a financial enterprise quality bar.

**The disambiguation/clarification exception:** If the pipeline determines early (at t=200ms) that it needs user input, it interrupts the streaming flow immediately with the appropriate state. Do not complete retrieval before asking the question. Time-to-user-input matters as much as time-to-answer.

---

## Section 5: Follow-up Suggestions

Follow-up suggestions are generated in Phase 3 post-processing. They are not decorative — for a Daily Analyst running variations of the same analysis, they reduce the query-to-insight cycle from "type the next question" to "click the chip."

### What Makes a Good Follow-up

Three categories, always in this order:

1. **Drill-down** — Same metric, more granular breakdown
   "Total billed business for Small Business" → "Break down by card product"

2. **Comparison** — Same metric, different time or segment
   "Total billed business for Small Business" → "Compare to Q4 2024"

3. **Adjacent angle** — Different metric on the same subject
   "Total billed business for Small Business" → "Show charge-off rate for Small Business"

**What makes a bad follow-up:**
- Repeating the current query with minor variation ("Show billed business for small businesses")
- Questions that require data Cortex doesn't have
- Questions that are less specific than the current one ("Show all billed business")
- Generic questions that could follow any query ("What other data is available?")

### Follow-up Presentation

```
You might also ask:
[Break down by card product]  [Compare to Q4 2024]  [Show monthly trend]
```

Three chips, horizontally arranged. Chips are buttons — clicking one fills the input and submits. They do not just fill the input — they submit, because the analyst wants the answer, not to review their query.

**Why chips over a list:** In ChatGPT Enterprise, the conversation is narrow. Chips stay on one or two lines. A bulleted list would dominate the response visually and push the data table up. Chips are scannable, clickable, and unobtrusive.

**Chip placement:** Below the source citation line, above the "How I got this" disclosure. They must be the last thing the user sees before the interaction ends — positioned to invite continuation.

### Follow-up Examples by Query Type

| Original Query | Drill-down | Comparison | Adjacent |
|----------------|------------|------------|----------|
| Total billed business, Small Business, last quarter | Break down by card product | Compare to Q4 2024 | Show delinquency rate for Small Business |
| Delinquency rate by vintage, Consumer, Q4 2025 | Break down by product type | Compare to Q4 2024 | Show charge-off rate by vintage |
| Spend activation rate by acquisition channel | Break down by card type | Compare to last year | Show new account volumes by channel |
| Credit line utilization, Corporate, last month | Break down by industry segment | Compare to Q3 2025 | Show delinquency rate for Corporate |

---

## Section 6: CLI Experience

The CLI (`access_llm/chat.py`) is the first implementation surface and the primary tool for Saheb, Likhita, and Animesh during development. It must implement the same UX principles as the chat interface, adapted for a terminal. The current PoC uses Rich panels — this design extends that pattern systematically.

### CLI Startup Sequence

Current startup shows progress steps with checkmarks. Keep this pattern but tighten the copy:

```
╔═══════════════════════════════════════════════════════════════╗
║  Cortex  ·  Financial Data Assistant  ·  American Express     ║
╚═══════════════════════════════════════════════════════════════╝

Connecting to data pipeline...
  [1/3] Configuration loaded
  [2/3] Looker tools ready (12 tools)
  [3/3] Retrieval index loaded (Finance BU · 847 fields)

Ready. Ask a question, or type /help for commands.

You: _
```

Changes from current PoC: Remove the ASCII art that shows every tool categorized. That belongs in `/tools`. Startup should be clean and fast-feeling. The "847 fields" number gives users a sense of the system's scope.

### CLI Streaming — Rich Panel Approach

The PoC uses `rich.Panel` for ThinkingEvents. The Cortex CLI should repurpose this for the streaming UX pattern from Section 4.

```
You: Total billed business for small businesses last quarter

  Analyzing your question...
```

During retrieval:
```
  Finding relevant data...
```

During SQL generation (subtle, not a new panel):
```
  Querying data...
```

Answer renders in a panel:
```
╭─── Answer ─────────────────────────────────────────────────────╮
│                                                                  │
│  Total billed business for Small Business customers last        │
│  quarter was $4.2B, up 8.3% from Q3 2025.                      │
│                                                                  │
│  Quarter     Segment           Billed Volume                    │
│  ─────────   ──────────────    ──────────────────               │
│  Q4 2025     Small Business    $4,213,847,200                   │
│                                                                  │
│  Source: Finance Cardmember 360  ·  Updated 4h ago              │
╰──────────────────────────────────────────────────────────────────╯

  You might also ask:
  [1] Break down by card product
  [2] Compare to Q4 2024
  [3] Show monthly trend

  Enter a number to continue, or ask a new question:
You: _
```

**CLI adaptation of follow-ups:** Numbered options instead of chips, because CLI users can type "1" faster than they can copy a question. Pressing Enter on an empty input after seeing numbered options should be treated as "I'll type my own question."

### CLI Disclosure — Level 2 and Level 3

The PoC currently shows ThinkingEvents in panels during execution. In Cortex CLI, these become on-demand:

```
You: /trace

╭─── Pipeline Trace ─────────────────────────────────────────────╮
│  trace_id: a3f9...  ·  1847ms total                            │
│                                                                  │
│  Intent Classification    203ms   confidence 0.97              │
│  intent=data_query  entities: metric=total_billed_business,    │
│  filter=bus_seg:small businesses, time=last quarter             │
│                                                                  │
│  Hybrid Retrieval         261ms   confidence 0.91              │
│  model=cortex_finance  explore=card_member_spend               │
│  few-shot match: GQ-fin-003 (0.94)                             │
│                                                                  │
│  Filter Resolution         14ms                                 │
│  "small businesses" → fuzzy → "small business" → OPEN          │
│  partition_date → injected → last 1 quarters                   │
│                                                                  │
│  ReAct Execution         1369ms   2 LLM calls, 1 MCP           │
╰──────────────────────────────────────────────────────────────────╯
```

```
You: /sql

╭─── Generated SQL ──────────────────────────────────────────────╮
│  SELECT                                                         │
│    SUM(total_billed_business) AS total_billed_business          │
│  FROM card_member_spend                                         │
│  WHERE bus_seg = 'OPEN'                                         │
│    AND partition_date >= DATE_TRUNC(                            │
│      DATE_SUB(CURRENT_DATE(), INTERVAL 1 QUARTER), QUARTER      │
│    )                                                            │
╰──────────────────────────────────────────────────────────────────╯
```

### CLI Commands — Full Set

```
/help      Show commands and example queries
/tools     List available Looker tools (from MCP)
/trace     Show full pipeline trace for last query
/sql       Show generated SQL for last query
/clear     Clear conversation history
/feedback  Submit feedback on last result (opens rating prompt)
/quit      Exit
```

The `/feedback` command opens an inline flow:
```
You: /feedback

How accurate was the last result?
[1] Correct    [2] Partially correct    [3] Wrong    [4] Skip

Your rating: 2

What was wrong? (optional, press Enter to skip):
The "small businesses" filter returned OPEN, but I wanted CORP-SME.

Feedback logged. Thank you — this trains the filter resolution.
```

This is the `/feedback` endpoint from `api/server.py` implemented in CLI. The `filter_correction` field in `FeedbackRequest` gets populated when the user describes a filter mismatch.

### CLI Disambiguation Flow

```
Your question matches two datasets. Which are you looking for?

  [1] Small Business Billed Volume
      Spending by small business cardmembers at merchants.
      (Finance Cardmember 360)

  [2] Small Business Credit Portfolio
      Credit metrics — receivables, utilization, credit line.
      (Credit Risk)

  [3] Rephrase my question

Enter a number: _
```

Numbered options in CLI. No buttons. User enters 1, 2, or 3. If they enter 3, the prompt returns to `You: _` with the previous query pre-filled so they can edit it.

---

## Section 7: Error States That Build Trust

Every error state has one job: maintain the user's belief that the system is honest, competent, and working in their interest. The errors that most damage trust are those that feel evasive, generic, or that expose internal details the user can't act on.

### 7.1 SQL Validation Fails

The system generated SQL but validation caught a problem before execution.

```
I generated a query but something in the structure doesn't look
right before I run it.

Here's what I was trying to do:
  Sum billed volume for small business segment,
  filtered to Q4 2025.

This is usually caused by ambiguity in the question. Could you:
  - Confirm which time period? ("Q4 2025" or "last quarter ending Dec 31")
  - Confirm which segment? ("Small Business cardmembers" or
    "small business merchants accepting Amex")

Or rephrase and I'll try again.
```

**What NOT to say:** "SQL validation error." "Invalid query syntax." "The generated SQL contains an error." These all feel like the system made a mistake and is confessing — not helpful.

**Key move:** Translate the SQL error back into business terms. The user asked about "small businesses" — the error is in the SQL, but describe the ambiguity in their language.

### 7.2 Partition Filter Missing (Cost Protection)

This should never be visible to the user as an error. The architecture injects partition filters automatically. But if the filter resolver fails to inject a required partition filter, the query should be blocked and the user should see:

```
I want to run this query safely before I execute it. The time
range you specified spans multiple years — this could be a large
query. Can you narrow it to a specific quarter or year?

  [ Q4 2025 ]  [ Full year 2025 ]  [ Custom range ]
```

**Never:** "Partition filter is required." "This query exceeds cost limits." "BigQuery scan limit exceeded."
**Always:** Translate the constraint into a user decision about time range. They get to choose. The system protects them, but they stay in control.

### 7.3 Filter Value Not Found

When the filter resolver's 4-pass matching fails to find a match for a user-provided filter value.

**Pass 1–4 exhausted, no match found:**
```
I couldn't match "luxury travel" to a category in my data.

The closest categories I have are:
  - Travel & Entertainment (T&E spending across all travel categories)
  - Airlines (air travel specifically)
  - Hotel & Lodging
  - Restaurants & Dining

Did you mean one of these? Or rephrase to use one of these
terms and I'll run the query.

[ Travel & Entertainment ]  [ Airlines ]  [ Hotel & Lodging ]
```

**When there is exactly one close match (high fuzzy confidence):**
```
I matched "luxury travel" to "Travel & Entertainment" — is that
what you meant?

[ Yes, proceed ]  [ No, let me rephrase ]
```

**Design principle:** Never silently substitute a filter value. If the resolver maps "small businesses" to "OPEN" with confidence > 0.95, proceed silently and show the translation in Level 2. If confidence is below 0.95, confirm explicitly. A wrong filter on a financial metric is worse than a delayed answer.

### 7.4 Timeout

When BigQuery or the Looker MCP call takes longer than the expected budget.

**At 4 seconds (approaching limit):**
```
The database is taking longer than usual — still working on it.
```

**At 8 seconds (soft timeout):**
```
This query is taking longer than expected. It may be running
against a large dataset.

You can:
  - Wait a bit longer — I'll keep trying                [Wait]
  - Narrow the time range to speed it up               [Narrow]
  - Try a simpler version of the question              [Simplify]
```

**At 15 seconds (hard timeout):**
```
The query timed out. This can happen with large date ranges
or complex aggregations.

To get a faster result:
  - Try a single quarter instead of multiple years
  - Filter to a specific segment or region

Reference: trace ID a3f9... if you need to escalate.
```

**Never expose BigQuery job IDs, timeout thresholds, or raw HTTP timeout errors.**

### 7.5 Low Retrieval Confidence (0.70–0.84 range)

This is NOT an error — it's a proceed with a subtle qualifier. But the UX must handle it differently from a high-confidence result.

The answer renders normally at Level 1, but the source citation includes a note:

```
Source: Finance Cardmember 360  ·  Updated 4h ago
Note: I used the closest matching dataset. Verify the data
source in the details below if this doesn't look right.
                                        [ How I got this ▼ ]
```

Level 2 auto-expands the source and filter section (not the SQL) so the user can verify the translation without having to click. The "How I got this" is still collapsible, but it opens to the source section by default.

---

## Section 8: Data Presentation Patterns

### 8.1 Single Value Result

When the query returns one number, format it large and in business language.

```
Total billed business for Small Business customers last quarter
was $4.2B, up 8.3% from Q3 2025.
```

Rules:
- Dollar amounts: format as $X.XB (billions), $X.XM (millions), $X,XXX (under a million)
- Percentages: one decimal place
- Include QoQ or YoY change when the previous period is available in the same dataset — this requires a second row in the query result, which the post-processing layer can detect
- Format the segment name as the user wrote it ("Small Business"), not the internal code ("OPEN")
- No table for single values — inline prose is sufficient

### 8.2 Table Result

When the query returns multiple rows.

```
Quarter     Segment           Billed Volume
──────────  ──────────────    ──────────────
Q4 2025     Small Business    $4,213,847,200
Q3 2025     Small Business    $3,891,234,100
Q2 2025     Small Business    $3,612,008,500
```

Rules:
- Column headers use business names, not field names ("Billed Volume" not "total_billed_business")
- Numbers formatted consistently within a column
- Sort order respects the user's intent (if they asked "by quarter" → chronological; if they asked "top 10" → descending)
- Maximum 10 rows shown by default in chat interface
- If more than 10 rows: "Showing 10 of 847 results. [ Show all ] [ Download CSV ]" — these are functional, not decorative

### 8.3 Time Series — Chart Recommendation

When the query result has a time dimension AND more than 3 data points, surface a chart recommendation.

```
[Table with monthly data...]

This data has a time dimension across 12 months. Would you
like to see it as a chart?

[ Show as line chart ]   [ Keep as table ]
```

**Implementation note:** In ChatGPT Enterprise, charts may not be natively renderable in the conversation. The prompt should be conditional on whether the interface supports visualization. In the CLI, the chart recommendation becomes: "This looks like trend data. Export as CSV to visualize in Tableau or Excel?" — because terminal chart rendering is not worth the implementation cost for the data team.

### 8.4 Large Result Sets

When the query returns more than 100 rows:

```
I found 847 results. Here are the top 10 by billed volume:

[Table, 10 rows]

[ Show top 25 ]   [ Download full dataset as CSV ]   [ Refine the filter ]
```

"Refine the filter" opens a prompt: "Add a filter — for example, limit to a specific region, card product, or time period." This is a better UX than showing 847 rows — it guides the analyst toward a focused query.

### 8.5 No Rows Returned — Valid Query, Empty Result

This is different from a no_match (which means no dataset). This means the query ran successfully but returned zero rows — the data exists but doesn't match the filters.

```
The query ran successfully but returned no results.

This typically means no data matches all your filters together.
Your filters were:
  - Segment: Small Business (OPEN)
  - Quarter: Q1 2019
  - Region: Alaska

Try removing one filter to see if data exists:
[ Remove region filter ]   [ Try a different quarter ]
```

This is high-value UX. Without it, the user assumes the system is broken. With it, they understand what happened and can take action.

---

## Section 9: Wireframe Reference — Full Interaction States

### Main Chat Interface

```
╔═════════════════════════════════════════════════════════════════╗
║  Cortex  ·  American Express Financial Data                     ║
╚═════════════════════════════════════════════════════════════════╝

[Previous conversation messages...]

──────────────────────────────────────────────────────────────────

You: Total billed business for small businesses last quarter

Cortex:
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Total billed business for Small Business customers last        │
│  quarter was $4.2B, up 8.3% from Q3 2025.                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Quarter     Segment           Billed Volume              │   │
│  │ Q4 2025     Small Business    $4,213,847,200             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Source: Finance Cardmember 360  ·  Updated 4h ago             │
│                                                                 │
│  You might also ask:                                            │
│  [Break down by card product]  [Compare to Q4 2024]            │
│  [Show monthly trend]                                           │
│                                                                 │
│                              [ How I got this ▼ ]              │
└─────────────────────────────────────────────────────────────────┘

──────────────────────────────────────────────────────────────────

[Message input                                         ] [Send]
```

### Disambiguation State

```
Cortex:
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Your question could draw from two different datasets.         │
│  Which are you looking for?                                     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ A  Small Business Billed Volume                        │     │
│  │    Spending by small business cardmembers at merchants │     │
│  │    Finance Cardmember 360                              │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ B  Small Business Credit Portfolio                     │     │
│  │    Credit metrics — receivables, utilization, lines    │     │
│  │    Credit Risk                                         │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                 │
│  [ Choose A ]    [ Choose B ]                                   │
│                                                                 │
│  Or rephrase: "What was total billed volume..." or             │
│  "What was total credit exposure..."                            │
└─────────────────────────────────────────────────────────────────┘
```

### Level 2 Expanded

```
Cortex:
┌─────────────────────────────────────────────────────────────────┐
│  [Answer and table as above...]                                 │
│                                                                 │
│                              [ How I got this ▲ ]              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  DATA SOURCE                                                    │
│  Model:    cortex_finance                                       │
│  Explore:  card_member_spend                                    │
│  Fields:   total_billed_business                                │
│  Filter:   bus_seg = OPEN  (matched from "small businesses")    │
│            partition_date = last 1 quarters                     │
│                                                                 │
│  QUERY                                          [Copy]          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SELECT SUM(total_billed_business)...                     │   │
│  │ FROM card_member_spend                                   │   │
│  │ WHERE bus_seg = 'OPEN'                                   │   │
│  │   AND partition_date >= DATE_TRUNC(...)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  The "small businesses" filter was resolved to segment code     │
│  OPEN. The partition filter was applied automatically to        │
│  optimize query cost.                                           │
│                                                                 │
│  Retrieved in 1.8s  ·  2 LLM calls  ·  Confidence: High       │
│                                            [ View full trace ] │
└─────────────────────────────────────────────────────────────────┘
```

---

## Section 10: Implementation Guidance for Cortex Team

### What the Backend Must Return (CortexResponse Contract)

For the UX to work as specified, the `CortexResponse` object must include:

```python
@dataclass
class CortexResponse:
    answer: str           # The narrative answer sentence(s)
    data: dict | None     # {rows, columns, row_count, display_limit}
    sql: str | None       # Generated SQL (for Level 2 disclosure)
    trace: PipelineTrace  # Full trace (for Level 3 and /trace command)
    follow_ups: list[str] # Exactly 3, in [drill-down, compare, adjacent] order
    source_citation: str  # "Finance Cardmember 360 · Updated Xh ago"
    confidence_tier: str  # "high" | "medium" | "low" (not a float)
    filter_translations: list[dict]  # [{"user_term": "small businesses",
                                     #   "resolved_value": "OPEN",
                                     #   "dimension": "bus_seg"}]
    action: str           # "proceed" | "disambiguate" | "clarify" | "no_match"
    disambiguation_options: list[dict] | None  # for disambiguate state
    clarification_question: str | None         # for clarify state
    row_count_total: int  # total rows available (not just displayed)
```

The `confidence_tier` field is important: the frontend never converts a float to a tier. The backend decides "high / medium / low" using the same thresholds defined in this spec (>=0.85, 0.70–0.84, <0.70). This keeps display logic consistent regardless of which frontend renders the response.

The `filter_translations` array is what enables the "matched from 'small businesses'" copy in Level 2. Without it, the frontend cannot produce this without re-doing the logic.

### CLI Implementation Priority

The CLI is the first surface. The following Rich patterns implement this spec:

- Use `rich.Panel` for the main answer (cyan border, "Answer" title)
- Use `rich.Table` for data results (no border, header row in bold)
- Use `rich.Text` with dim style for the source citation
- Use `rich.Panel` with yellow border for disambiguation ("Choose a dataset")
- Use `rich.Panel` with blue border for clarification ("Let me make sure...")
- Use `rich.Panel` with red border for errors
- Use `rich.Spinner` with text "Finding relevant data..." during retrieval phase
- The `/trace` command renders a Panel with step-by-step using `rich.Tree`

### Response Generation Responsibility Split

The backend (Cortex API) is responsible for:
- The `answer` string — narrative sentence(s) in business language
- Filter value translations (what was typed vs. what was resolved)
- Follow-up generation (3 suggestions, in drill/compare/adjacent order)
- Confidence tier classification
- Source citation string (dataset name + freshness)

The frontend is responsible for:
- Progressive disclosure rendering (which level to show)
- Streaming animation (updating indicator text)
- Follow-up chip/button rendering
- Level 2/3 expand/collapse behavior
- Disambiguation and clarification button rendering

This split keeps the response contract stable across CLI and ChatGPT Enterprise surfaces.

---

## Open Questions for Validation

1. **Confidence tier thresholds** — The 0.85/0.70 thresholds are assumptions from first principles. Validate against the golden dataset: at what retrieval confidence score do users start questioning results?

2. **Follow-up suggestion quality** — The drill/compare/adjacent framework is a hypothesis. Run a 2-week experiment: track which follow-ups get clicked vs. ignored. Remove or reorder based on actual behavior.

3. **Disambiguation frequency** — If disambiguation appears more than 10% of queries for a given user, the retrieval system is under-fitted to their domain vocabulary. Use disambiguation choices as a signal to weight retrieval for that user's context.

4. **Executive persona access** — Do executives actually use ChatGPT Enterprise directly, or do they see results forwarded by analysts? If the latter, Level 1 UX is irrelevant for them and we should focus entirely on the analyst experience.

5. **CLI vs. ChatGPT fidelity** — How much should the CLI experience diverge from the chat interface? The current spec tries to keep them close. If the CLI is only for engineers, it can become a power-user tool with more verbose output by default.

6. **Filter correction flow as onboarding** — Every time a filter value fails to resolve, that's a gap in the filter value catalog. Should the "I couldn't match X" state offer the user the ability to tell us the right value? This is the learning loop (ADR-008) surfaced to the user. Consider making this explicit: "Did you mean [X]? If so, I'll remember this for next time."
