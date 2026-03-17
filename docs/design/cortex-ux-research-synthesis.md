# Cortex UX Research Synthesis
## Enterprise NL2SQL — Full Audit, Gap Analysis, and Design Recommendation

**Author:** UX Research (ux-researcher agent)
**Date:** March 16, 2026
**Status:** Complete — ready for product review
**Audience:** Saheb (product), Ayush (implementation), Likhita (intent layer), Kalyan (leadership demo)

---

## How to Read This Document

This is a living synthesis, not a requirements list. Section 1 is the inventory — what exists. Section 2 is the current-state user journey built from code, not assumptions. Section 3 is the gap analysis, organized by the moments that matter most. Section 4 is the recommended UX design. Section 5 is the competitive analysis. Use Section 4 when making implementation decisions; use Section 3 when prioritizing what to fix first.

A critical standing override applies throughout: confidence scores must always be shown as numerical values. This overrides the "hide percentages from non-technical users" recommendation in the earlier UX specification. The enterprise explainability requirement at Amex takes precedence.

---

## Section 1: UX Artifact Inventory

Everything in the repository that informs the user experience, with a one-line summary of its contribution.

### Primary UX Artifacts

| File | Type | Summary |
|------|------|---------|
| `docs/design/cortex-demo-ui-design.md` | Design spec | Full React component specification for the demo app — dual Analyst/Engineering view, tokens, layout, step animations, all components to pixel precision |
| `docs/design/cortex-ux-specification.md` | UX specification | Behavioral spec for the chat experience — trust signal architecture, 3-level progressive disclosure, all interaction states (proceed/disambiguate/clarify/error), streaming timeline, follow-up patterns, CLI design, error taxonomy |
| `docs/design/lookml-explorer-ux-research.md` | Research + concept | Three discoverability concepts (Explore Map, Inline Query Assistant, Conversational Data Dictionary) with competitive analysis of Looker, Tableau Ask Data, ThoughtSpot, and Power BI |
| `docs/api-contract-ayush.md` | API contract | Complete SSE event schema, TypeScript integration code, all 7 pipeline steps with copy for each, happy path and disambiguation sequences, error state table |
| `scripts/cortex_chat.py` | Working prototype | CLI implementation with color-coded event rendering — the current live UX for developers |
| `src/api/server.py` | API implementation | FastAPI with all 6 endpoints: query, followup, trace, capabilities, feedback, health |

### Technical Context Artifacts (UX-Relevant)

| File | UX Relevance |
|------|-------------|
| `docs/design/pipeline-first-principles-breakdown.md` | Per-step latency budgets used to design the streaming UX timeline |
| `docs/design/financial-query-patterns-research.md` | 23 documented ambiguity pairs that drive the clarification/disambiguation flow design; LookML coverage gaps inform the "no match" state |
| `docs/design/80-percent-coverage-queries.md` | The 6 golden queries that define the starter card content and follow-up generation |
| `docs/design/agentic-orchestration-design.md` | Three-phase pipeline architecture — the operational reality the UX must map to |
| `docs/design/cortex-orchestrator-api-design.md` | SSE event contract origin document — defines what information is available for UI rendering |
| `docs/design/whiteboard-3-technical-pipeline.md` | Technical whiteboard for engineering view — informs what the pipeline explainability panel must explain |
| `docs/design/metric-taxonomy.md` | Metric vocabulary used in follow-up suggestion generation and "no match" redirects |
| `docs/patents/patent-landscape-analysis.md` | Near-miss detection (Patent #2) has direct UX implications for the disambiguation modal design |

### Missing UX Artifacts (Gaps to Address)

- No ADRs directory exists — architecture decisions about UX patterns are embedded in design docs but not formally committed
- No user research notes or interview transcripts from actual Finance analysts
- No usability testing plan
- No A/B test design for any UX decisions
- No accessibility audit or WCAG checklist
- No mobile experience design (desktop-primary assumption is stated but never validated)
- No onboarding flow design beyond starter cards
- No session timeout or idle state design
- No notification/alert design for when Cortex capabilities expand

---

## Section 2: Current UX State — The User Journey Today

This is not what is designed. This is what a user experiences right now if they access the system.

### Entry Point: CLI Only

There is no React frontend deployed. The only interactive surface is `scripts/cortex_chat.py`. The API server is running and the contract is specified for Ayush, but the demo app described in `cortex-demo-ui-design.md` does not yet exist as a built application.

The production path through ChatGPT Enterprise is a design intention, not an implemented reality.

### What the CLI Actually Does

**Startup (not user-controllable, happens automatically):**
```
[1/4] Loading SafeChain config
[2/4] Loading MCP tools
[3/4] Creating orchestrator
[4/4] Pre-warming caches
```

**Query input:** A plain `You: ` prompt. No examples, no suggestions, no starter queries. Users must already know what to ask.

**Progress display during pipeline:**
- Step start: `[1/7] Analyzing your question...  [=------]` with a text-based progress bar
- Step complete: `done (287ms)` — timing visible to all users, not just engineers
- Explore scored: explore name + percentage confidence, plus a table of top 3 candidates with raw scores and coverage values
- SQL generated: full SQL printed to terminal, syntax visible to all users
- Results: raw column/row table, max 10 rows shown inline

**Follow-ups:** Numbered list (1, 2, 3) with question text. User must type the full question themselves — clicking is not available.

**Disambiguation:** Text display with numbered options. User must type the exact explore name as a follow-up query. The instruction "Use finance_cardmember_360 for my question" is shown as an example, but users must construct this manually.

**Error states:** Raw tag display: `ERROR: <message>` or `RECOVERABLE: <message>`. No suggestions, no actions.

**Commands:** `/trace` (shows full JSON trace), `/clear`, `/help`, `/quit`.

### Current User Journey Map

```
FINANCE ANALYST TRYING TO GET DATA TODAY

1. DISCOVERY
   How does user find Cortex?  →  [GAP: No formal onboarding path. Word of mouth only.]

2. FIRST LAUNCH
   Runs: python scripts/cortex_chat.py
   Waits ~5-10 seconds for SafeChain + MCP initialization
   Sees: 4-step startup sequence with timing
   Then: "Ready! Type a question or /help"

   PAIN: User has no idea what questions to ask. Blank prompt with no examples.

3. FIRST QUERY (Happy Path)
   User types: "Total billed business by generation"
   Pipeline runs, user watches 7 steps stream in real time

   What user sees:
   - All 7 step_start/step_complete events with ms timings
   - Raw confidence scores (0.94, etc.) for explores
   - Raw SQL query
   - A table of results (up to 10 rows)
   - Numbered follow-up suggestions
   - "Wall clock: 2450ms"

   PAIN: Engineering data (ms timings, raw scores, SQL) is front-loaded.
         User must scroll through this to reach the actual answer.
         Answer text is at the BOTTOM, not the top.

4. FIRST QUERY (Disambiguation Path)
   explore_scored fires with is_near_miss=true
   disambiguate event fires
   User sees: "DISAMBIGUATION NEEDED" + numbered options

   User must type: "Use finance_cardmember_360 for my question"
   Or rephrase: system says 'Pick one and rephrase, e.g.: "Use finance_cardmember_360 for my question"'

   PAIN: "Use finance_cardmember_360 for my question" is an unnatural construct.
         Users who don't know explore names are stuck.
         The instruction to manually type this is asking too much.

5. FOLLOW-UP
   User sees numbered suggestions: "1. Break down by card product"
   Must type full question text. Numbers don't trigger the follow-up.
   conversation_id is maintained automatically. This works.

   PAIN: Follow-up friction is high. Typing the full question again defeats
         the point of the suggestion.

6. ERROR STATE
   SQL execution fails. User sees:
   "RECOVERABLE: <error message>"
   No guidance on what to do next.

   PAIN: Error message is technical. No actions offered.

7. TRACE INSPECTION
   User types /trace
   Full JSON trace object rendered to terminal

   STRENGTH: This is genuinely useful for engineers.
             Detailed per-step info is accessible.

8. SESSION END
   /quit or Ctrl+C
   No session persistence. Next session starts fresh.

   PAIN: No session history. User must remember previous queries.
```

### What Is Designed But Not Yet Built

The demo UI spec in `cortex-demo-ui-design.md` and the UX spec in `cortex-ux-specification.md` describe a substantially better experience — dual view modes, streaming with staged contextual feedback, progressive disclosure, follow-up chips, proper disambiguation modal, full accessibility design. These are design documents waiting for implementation.

The gap between the current CLI state and the designed state is significant. The designed state is the right target. This synthesis identifies what matters most in bridging that gap.

---

## Section 3: Gap Analysis

Organized by the UX moments that have the highest impact on trust and adoption. Each gap is rated by severity: P0 (breaks core use case), P1 (degrades daily use significantly), P2 (quality of life).

### Gap 1: The Blank Page Problem — No First-Time Guidance
**Severity: P0**

Current state: A bare `You: ` prompt. Users who have not been trained do not know what to ask. This is not a minor UX problem — it is a trust cliff. A user who asks an out-of-scope question on their first interaction and gets a failure or a confusing response will not come back.

What the design spec says: Five starter query cards on the welcome screen, derived from the `/api/v1/capabilities` endpoint. This endpoint exists and is implemented in the API server. The capabilities response includes explore names and descriptions. Sample questions are stubbed as empty arrays (`"sample_questions": []` — explicitly noted as a TODO in `server.py`).

**Gap:** The `/api/v1/capabilities` endpoint exists but `sample_questions` is not populated. Starter cards have no content to pull from. The API endpoint is ready; the data population is missing.

**What is additionally missing from the design:**
- The three discoverability concepts in `lookml-explorer-ux-research.md` provide excellent options, but none is chosen. A decision needs to be made before Ayush builds anything. Concept C (Conversational Data Dictionary) is the only option that works in ChatGPT Enterprise production — this should be the baseline. Concepts A and B are demo app enhancements.
- The onboarding path for a brand-new Finance analyst with no prior context is not specified — what they see before they ever ask a question, who tells them Cortex exists, what the "value proposition" message is.

**Recommended resolution:** Populate `sample_questions` from the 80% coverage queries in `docs/design/80-percent-coverage-queries.md`. Six queries, mapped to five explores, covering the scenarios that represent 80% of real-world traffic. This is a one-hour content task, not an engineering task.

---

### Gap 2: The Streaming UX — Answer Position and Information Priority
**Severity: P0**

Current state: The CLI renders pipeline events as they stream. The order is: step progress, step progress, step progress, step progress, step progress, step progress, step progress, then the answer at the very end. Engineering data (ms timings, raw scores, SQL) is interleaved throughout.

What the design spec says: The answer appears first. Pipeline steps are in the Engineering panel (separate, right-side). In Analyst View, the user sees only staged contextual feedback: "Analyzing..." then "Finding relevant data..." then "Querying data..." then the answer streams in.

**Gap:** The CLI has no concept of "Analyst View" vs "Engineering View." Everything is one stream. The answer is buried at the bottom of engineering output.

For the React demo app, the view_mode toggle exists in the API (`view_mode: "engineering" | "analyst"`) but the current `scripts/cortex_chat.py` always uses `view_mode="engineering"`. There is no analyst mode render path in the CLI.

**A specific interaction gap that creates friction:** The CLI currently puts the answer after the pipeline output but before the "Wall clock" line. This means the answer is not the first thing the user's eyes go to — it competes with the SQL block and explore scoring table that precede it. In a web interface, this translates to a response that starts with a table of scored explores instead of the actual finding.

**Recommended resolution:**
- CLI: Add an analyst mode where step events are collapsed to three lines maximum ("Analyzing... Finding data... Done.") and the answer panel appears prominently at the top.
- React app: The Analyst View / Engineering View toggle is correctly designed and must be the default-to-Analyst implementation. The Engineering View exists for Saheb and Likhita during development and for the Kalyan demo.

---

### Gap 3: Disambiguation UX — The Manual Rephrase Instruction Fails Non-Technical Users
**Severity: P0**

Current state: When `disambiguate` fires, the CLI shows the two options with explore technical names and tells the user to type `"Use finance_cardmember_360 for my question"`. This instruction requires the user to know the explore name and construct a synthetic follow-up query.

What the design spec says: A modal with two option cards, each describing the option in business language. User clicks a button. The pipeline handles the routing. The user never types an explore name.

**Gap:** The CLI and the API contract are misaligned. The API contract correctly specifies that after a disambiguation, the frontend sends `POST /api/v1/followup` with `"query": "Use finance_cardmember_360 for: <original query>"`. But the CLI exposes the explore name directly to the user and asks them to construct this themselves. The pipeline correctly supports disambiguation routing — the UX failure is in how the choice is presented and handled.

**A deeper gap in the specification:** The disambiguation modal design in the UX spec uses business names ("Small Business Billed Volume") not explore names. But the `disambiguate` SSE event currently surfaces `explore` names (technical identifiers) in the `options[]` array. The business-language descriptions are `description` fields — these exist in the payload but are not guaranteed to use business language. The `EXPLORE_DESCRIPTIONS` in `config/constants.py` determines what text appears. If those descriptions use technical field names, the modal will expose technical language regardless of the CSS.

**Recommended resolution:**
- Audit `config/constants.py` `EXPLORE_DESCRIPTIONS` to ensure all explore descriptions are in plain business language, not LookML identifiers.
- In the React app, map explore technical names to business names in a lookup table before rendering the modal. Never surface the explore name as the primary label.
- In the CLI, replace the "rephrase with explore name" instruction with numbered selection: the user presses 1 or 2, the CLI constructs the follow-up query internally.

---

### Gap 4: Confidence Score Display — An Active Contradiction in the Docs
**Severity: P1**

The UX specification (Section 1.1) says: "Never show raw percentages to non-technical users." It maps confidence to High/Medium/No indicator states.

The memory file (`feedback_confidence_scores.md`) says: "Always show numerical confidence scores in UI. Saheb overruled the 'hide percentages' UX recommendation. Enterprise explainability requirement."

The demo UI spec (Section 8, Engineering View Panel Footer) shows: "94%" as the large primary display in the footer.

**Current implementation:** The CLI shows `confidence 0.91` (raw float) for explore scoring and `confidence {conf:.0%}` (percentage) in the done event.

**Gap:** There is a documented decision (always show) but no consistent implementation of it, and the two main spec documents contradict each other. This creates implementation ambiguity for Ayush.

**Resolved direction (applying the memory override):** Numerical confidence percentages are always shown. The question is where and how.

Recommended display rules:
- Analyst View: Show confidence percentage in the metadata footer of every response, always. Format: "94% match" — not "94% confidence" (the word "confidence" implies the system might be wrong; "match" implies the system found the right thing). Green for >=80%, amber for 60-79%, red for <60%.
- Engineering View panel footer: Show the large percentage with the three-component breakdown (semantic: X, graph: X, few-shot: X) as currently designed.
- CLI: Show confidence on the `done` line in the format already implemented (`confidence 94%`).
- Do not show confidence mid-stream during pipeline execution for non-engineers. Show it once, on the completed result.

**What this means for the UX spec:** Section 1.1 of `cortex-ux-specification.md` is superseded. Confidence thresholds still control behavior (whether to proceed, disambiguate, clarify, etc.) but the percentage is always displayed rather than mapped to a label. High/Medium/Low labels can be secondary labels alongside the number, not replacements for it.

---

### Gap 5: Follow-Up Flow — Chips vs Numbers, and the Submission Problem
**Severity: P1**

Current state (CLI): Follow-ups are numbered. User must type the question text manually. The `conversation_id` is maintained correctly — the pipeline supports multi-turn. The UX does not.

What the design spec says: Clickable chips that submit immediately on click. No retyping. The suggestion is a complete question, not a starting point.

**Gap:** The follow-up intent — reducing the cost of the next question to near zero — is correct. The implementation in the CLI achieves zero of this. In the React app, this is straightforward chip rendering. The gap is that numbered CLI follow-ups also fail to use the number as a shortcut — typing "1" does not trigger the follow-up. Users must type the full suggestion text.

**An additional gap not mentioned in the spec:** The follow-up suggestions are generated by the pipeline (Phase 3 post-processing) and surfaced as a `follow_ups` SSE event. But there is no specification for what happens when the pipeline fails to generate follow-up suggestions — no fallback, no fallback content, no minimum guarantee. If the model skips follow-up generation on a low-confidence result, the user is left with no continuation path. This is most likely to happen exactly when the user needs guidance most (after a confusing or partial answer).

**Recommended resolution:**
- CLI: Pressing "1", "2", or "3" at the follow-up prompt should submit the corresponding suggestion, not require the user to type it.
- React: Chips submit on click, not on Enter. No intermediate fill-and-review step — analysts want the answer, not to review their rephrased query.
- Fallback follow-ups: If the pipeline does not generate follow-ups, the UI should show two generic continuation prompts based on the explore that was used. These can be pre-generated templates: "Break this down by [common dimension]" and "Compare to the previous quarter." Not ideal, but better than silence.

---

### Gap 6: Error States — The Technical Bleed
**Severity: P1**

Current state: Error rendering in the CLI is `styled('RECOVERABLE', C.BOLD, C.RED): {msg}`. The message comes directly from the error event, which comes from the orchestrator. If the orchestrator generates a technical error message ("MCP connection timeout" or "BigQuery scan limit exceeded"), that technical message reaches the user.

What the design spec says: Seven fully designed error states, each with business-language copy, specific user actions, and no technical detail exposure. The spec is thorough. The implementation does not enforce it.

**Gap:** The error message copy is defined in the UX spec but not enforced in the pipeline. The `error` event's `message` field is populated by the orchestrator, and nothing in the pipeline guarantees that error messages are user-safe. An MCP timeout could surface "aiohttp.ClientConnectionError: Connect call failed" as the error message.

**A second gap:** The `recoverable` boolean in the error event is used to show a Retry button in the API contract, but the CLI does not implement retry. Users must retype their query. This compounds the frustration of an error.

**Recommended resolution:**
- Add an error message mapping layer in the orchestrator or in the API server that maps internal exception types to the user-safe messages defined in the UX spec. The technical error should be logged internally (and captured in the trace) but the message field in the SSE event should always be user-safe copy.
- CLI: Implement retry on recoverable errors by pressing "r" rather than retyping the query.
- React: The Retry button on recoverable errors should be a first-class element, not just shown optionally.

---

### Gap 7: Filter Value Translation — Trust Signal or Trust Risk
**Severity: P1**

The UX specification correctly identifies filter translation as the single most important trust signal in the entire interface. The Level 2 disclosure shows: "bus_seg = OPEN (matched from 'small businesses')" — this translation chain is what allows an analyst to verify the system didn't silently misinterpret their query.

Current state: Filter resolution happens correctly in the pipeline. The translation is captured in the trace. But the CLI does not surface it except in the full `/trace` output. A user who got the wrong answer because `"small businesses"` resolved to the wrong segment value has no way to know this without specifically running `/trace`.

The `FeedbackRequest` model in `server.py` includes a `filter_correction` field — the data model for this feedback exists. But there is no UI surface in the CLI or in the spec'd React app that proactively shows the filter translation and invites correction.

**Gap:** The filter translation is available in the pipeline trace but is not surfaced as a default part of the response. The UX spec says it appears in Level 2 ("How I got this"). But Level 2 requires a click. For new users, most will never click Level 2. The filter resolution information will only be discovered after something goes wrong.

**Recommended resolution:**
- Show filter translations inline in the main response, always. Not in Level 2. Use format: "Filters applied: Small Business (OPEN) — Q4 2025" below the answer sentence and above the table. This is a one-line addition that surfaces the most important trust signal without requiring a click.
- Add a "Wrong filter?" link inline next to the filter translation. Clicking it opens an inline correction flow: "What did you mean by 'small businesses'?" with a free-text field. This feeds directly to `filter_correction` in the feedback endpoint.
- In the CLI, add the filter translation to the standard result output, not just to `/trace`. It should appear as: `  filters: "small businesses" → OPEN` in the same section as the answer.

---

### Gap 8: Feedback Mechanism — Endpoint Exists, UX Does Not
**Severity: P1**

The `POST /api/v1/feedback` endpoint exists in `server.py`. It accepts `trace_id`, `rating`, `filter_correction`, and `comment`. The learning loop design (ADR-008, referenced in agentic orchestration design) specifies that feedback drives filter resolution improvement.

Current state: The CLI implements `/feedback` as a command (defined in the UX spec, Section 6) but it is not in the actual `cortex_chat.py` implementation. The CLI only has `/trace`, `/clear`, `/help`, `/quit`. The feedback command is in the spec but not in the code.

The React app design includes a metadata footer with what appears to be the intent for rating, but the actual thumbs up/down or rating UI is not specified in the demo UI design document.

**Gaps:**
- The feedback command is missing from the CLI implementation
- The React app has no specified feedback UI (the metadata footer is described but no rating mechanism is included in the component hierarchy)
- The `filter_correction` feedback path (the highest-value signal for the learning loop) has no UX surface at all in either interface
- There is no design for what happens after feedback is submitted — no confirmation, no "thank you," no indication that the feedback will change anything

**Recommended resolution:**
- CLI: Implement `/feedback` as specified in the UX spec. The inline rating flow is fully designed — it just needs to be coded.
- React: Add a thumbs up/thumbs down to the metadata footer of every response. This is the minimum feedback surface. One click, no modal.
- React: The "Wrong filter?" inline link (from Gap 7) feeds the `filter_correction` path.
- React: Show a "Feedback submitted" toast on submit. One-line copy: "Thanks — this helps improve filter matching." This closes the loop for the user and signals that feedback has a purpose.

---

### Gap 9: Data Presentation — Chart Recommendations and Large Result Sets
**Severity: P2**

The UX spec (Section 8) specifies handling for single values, tables, time series charts, large result sets, and empty results. The API already returns `columns`, `rows`, `row_count`, and `truncated`. The data is available to drive these display decisions.

Current state: CLI shows a fixed-width text table, maximum 10 rows, with a "... and N more rows" line. No chart recommendation. No large-result guidance.

**Gaps:**
- Time series detection (query returns a time dimension with 3+ data points) is not implemented in either the CLI or the spec'd React app. The spec says to recommend a chart; the API contract does not include a `result_type` or `chart_recommended` field in the `results` event. The frontend would need to infer this from column types.
- The "Download CSV" action for large results is specified in the UX spec but there is no endpoint for CSV export in the API. This is a missing API endpoint, not just a UI gap.
- The "empty result" state (valid query, zero rows) is fully specified in the UX spec but not implemented in the CLI. Currently, zero rows just prints "0 rows" with no guidance.

**Recommended resolution:**
- Add `result_type: "single_value" | "table" | "time_series" | "empty"` to the `results` SSE event. The backend can detect this — it knows the column types.
- Add `POST /api/v1/export/{trace_id}` as a CSV download endpoint. The raw data already exists in the trace.
- CLI: Implement the empty result state with the filter removal suggestions as designed in the UX spec.

---

### Gap 10: The ChatGPT Enterprise Production Path — The Critical Unsolved Problem
**Severity: P0 (for production, P2 for demo)**

The entire React demo app is a demonstration surface. The actual production deployment is through ChatGPT Enterprise. The UX spec acknowledges this in passing: "In ChatGPT Enterprise, you don't control the chrome. Your UX is the response format."

But the design work — all of it — is aimed at the React demo app. The Analyst View, the Engineering View, the pipeline step animations, the disambiguation modal, the starter query cards: none of these are available in ChatGPT Enterprise.

**What Cortex's UX looks like in ChatGPT Enterprise today:**
- User types a question in the ChatGPT chat box
- The ChatGPT GPT action calls `POST /api/v1/query`
- The full SSE stream is not rendered as a streaming pipeline animation — ChatGPT renders the response as a single block when the stream completes (or partial markdown if streaming is configured)
- The response format is whatever the `response_formatting` step returns as a plain text / markdown string
- There is no disambiguation modal — the `disambiguate` event would need to surface as a text question in the response
- There is no Engineering View
- Follow-up suggestions appear as markdown chips (some ChatGPT versions render `[suggestion text]()` as clickable)

**Gap:** There is no specification for the ChatGPT Enterprise response format. The response formatting prompt in the orchestrator (Phase 3) determines what the final answer looks like, and the UX spec does not include a specific section for "what does a ChatGPT Enterprise response look like in markdown?" This means the Level 1 experience for 100% of production users is unspecified.

**Recommended resolution:** Write a separate "ChatGPT Enterprise Response Format" specification. At minimum it must cover:
- The markdown template for a standard result (answer sentence + table + source citation + follow-ups as suggested actions)
- How disambiguation is handled as a conversational turn rather than a modal
- How filter translations are surfaced in plain text
- How confidence is shown in the response body (percentage, since the memory override applies here too)
- What the system prompt includes to set context for new users (the Concept C "Conversational Data Dictionary" from the lookml-explorer-ux-research)

---

## Section 4: Recommended UX Design

### 4.1 Design Philosophy for Cortex

The UX specifications already document several strong principles. This section adds the synthesis layer — the decision framework that resolves contradictions and fills the gaps identified in Section 3.

**Principle 1: Numerical honesty.** Confidence percentages are shown. Always. In every view. The user's right to understand how certain the system is supersedes the concern that they will over-interpret the number. Financial analysts at Amex are comfortable with numbers; they are not comfortable with vague signals. "94% match" is more trustworthy to a daily analyst than "High" or a colored dot with no value.

**Principle 2: Filter transparency is mandatory, not optional.** Filter translations are shown inline in the response body, not hidden in Level 2. The rule is: any filter the pipeline resolved from natural language to a code value must be surfaced before the result is read, not after. A user reading "$4.2B" without knowing whether the "small businesses" filter resolved correctly is reading an unverified number. We cannot ask them to click first.

**Principle 3: The pipeline serves the analyst, not the demo.** The Engineering View is a credibility and debugging tool. It should be excellent. But the Analyst View is the product. Every default, every initial state, every flow should be optimized for the Daily Analyst running 20 queries a day — not for the executive watching a Thursday demo.

**Principle 4: Disambiguation is a feature, not a failure.** When the system asks which data source to use, it is demonstrating that it recognized ambiguity rather than silently guessing. This is a competitive strength. The UX for disambiguation must make this feel like a smart question, not an error. Presentation: two clear option cards with business language, side by side, each with a one-sentence description and a click target. Not a dropdown. Not a text prompt. Not a bullet list with instructions to rephrase.

**Principle 5: Conversation continuity is the retention driver.** A user who discovers they can type "compare to last year" after getting a result and immediately get a comparison — without re-specifying the explore or the segment — will use Cortex every day. A user who must retype the full context each time will use it occasionally. Multi-turn conversation handling is correct in the pipeline. The UX must make it effortless.

---

### 4.2 User Journey Map — From Landing to Insight to Action

The following is the recommended end-to-end experience for the Daily Analyst persona — the user who will determine whether this product succeeds.

**PRE-SESSION: First Contact**

User hears about Cortex from a colleague or receives a Slack message from the Cortex team. No cold-start email blast — this is wrong for enterprise. The first contact should be a Slack DM or team post with: one example query, one output screenshot, and a single link. "Ask about your Finance data in plain English. Try: 'What was billed business for Small Business last quarter?'"

**STEP 1: Opening the Interface**

Opens the React app (demo / internal deployment) or opens the ChatGPT GPT in their enterprise environment.

If React app: sees the welcome state with greeting, five starter query cards, and a small "What can I ask?" link below the cards.
If ChatGPT Enterprise: first message from the system is the Concept C capability summary — five topics, example questions, constraints. This happens once per session via the system prompt, not as a visible chat message.

The five starter cards are sourced from the `/api/v1/capabilities` endpoint, populated with the six 80% coverage queries. Cards are not decorative — each card has a title and a specific example question. Clicking a card submits the query.

**STEP 2: Query Input**

User clicks a starter card or types their own question.

If typing: after 3 characters, the Inline Query Assistant (Concept B) shows suggestions from the LookML model and golden dataset. Each suggestion has an explore badge. Escape dismisses. If the user's partial input matches a known ambiguity pair (from the 23 documented pairs), a disambiguation hint appears inline before submission.

Input field: "Ask anything about your Finance data..." placeholder. No character counter shown (it feels constraining). 2,000 character limit enforced silently — if the query is near the limit, a subtle indicator appears.

**STEP 3: Pipeline Processing — Analyst View**

The query submits. The response area appears immediately with the query echoed back in a "working" state.

Phase 1 (0-460ms): "Analyzing your question..."
Phase 2 (460-1275ms): "Finding relevant data..."
Phase 3 (1275-2000ms): Answer streams in word by word.

Three text states only, in the same position. No step numbers visible to the analyst. No progress bar. The query echo fades when the answer begins to appear.

**Exception — disambiguation at 200ms:** If `disambiguate` fires, the working state immediately transitions to the disambiguation modal. No waiting for retrieval to complete. The modal is the UX response to the early signal.

**STEP 4: Reading the Result**

The full Level 1 response:

```
Total billed business for Small Business customers last
quarter was $4.2B, up 8.3% from Q3 2025.

Quarter      Segment           Billed Volume
──────────   ──────────────    ──────────────
Q4 2025      Small Business    $4,213,847,200

Filters: Small Business (OPEN) — Q4 2025 [Wrong filter?]
Source: Finance Cardmember 360  ·  Updated 4h ago  ·  94% match

You might also ask:
[Break down by card product]   [Compare to Q4 2024]   [Show monthly trend]

                                      [ How I got this ▼ ]
```

The answer sentence leads with the number. The table follows immediately. The filter translation line is always shown and includes an inline "Wrong filter?" affordance. The source citation includes the confidence percentage. Follow-up chips are clickable and submit immediately. The "How I got this" disclosure is available but not promoted.

**STEP 5: Follow-Up**

User clicks "Break down by card product." The pipeline runs with the conversation context intact. The new query inherits the explore, time range, and segment filters from the previous turn. The result adds card product as a dimension without the user having to re-specify anything.

If the new query requires a different explore (rare but possible), the system detects this and either routes silently (if high confidence) or asks: "This breakdown requires a different data source — proceed with Finance Cardmember 360?"

**STEP 6: Level 2 Disclosure (Power User Path)**

User clicks "How I got this." Level 2 expands inline below the response. Shows: data source (model + explore), filter resolution chain, full SQL with copy button, plain-English SQL translation, response time, LLM call count, and confidence breakdown (semantic: 0.91, graph: 0.97, few-shot: 0.89).

The SQL copy button is always present. The Data Engineer persona will use this constantly. The copy action works silently — no modal, no confirmation — just a clipboard write with a subtle checkmark on the button for 1 second.

**STEP 7: Engineering View (Optional Toggle)**

For Saheb, Likhita, engineers, and the demo. Toggle in the top nav activates a right-side panel showing the full pipeline trace. Seven steps with timing, scores, and expandable detail for each. Overall confidence in the footer. This view does not change what the analyst sees in the left panel — it adds a layer on top.

**STEP 8: Session Continuity**

Each conversation is stored in the sidebar by first query (truncated). User can return to previous sessions. Within a session, conversation history is sent with each request so follow-ups work correctly across any time gap within the session.

Session limit is 20 turns (a hard limit in the ConversationStore). When approaching this limit (at turn 18), a subtle indicator appears: "You're approaching the conversation limit (18/20). Start a new conversation to continue fresh." At turn 20, the conversation is automatically closed and a "Start new" prompt appears.

---

### 4.3 How to Handle the 7-Step Pipeline Visually

This is the defining UX challenge of Cortex and the opportunity that differentiates it from every competitor.

**The tension:** The pipeline is genuinely impressive — 7 deterministic steps, hybrid retrieval, graph validation, filter resolution, confidence scoring, Looker MCP execution. Showing it creates trust and credibility. Hiding it creates magic.

**The resolution: show it to the right audience at the right time.**

For the Analyst (always): Show only three phases, described in business terms, that map to what the pipeline is actually doing:
- "Analyzing your question" = intent classification + retrieval (steps 1-3)
- "Finding your data" = filter resolution + SQL generation (steps 4-5)
- "Getting results" = execution + formatting (steps 6-7)

This is not dumbing down. It is translating the pipeline into the user's mental model. The analyst understands "finding data" as a real thing that takes time. They do not need to understand pgvector.

For the Engineer (on toggle): Show all 7 steps in real time in the Engineering View panel. Step indicator circles transition: gray (pending) → pulsing blue (active) → solid green (complete) → amber (warning/near-miss) → red (error). Per-step timing badges. Expandable step detail shows exactly what the step computed. This is the pipeline documentation made interactive.

For the Executive (special handling): The typing indicator in Analyst View is the only thing they see. "Cortex is thinking..." with three animated dots. No phases, no progress, just movement. The result must appear in under 3 seconds for this persona — if it takes longer, the executive has already minimized the window.

**The 7-step animation in the Engineering View panel** is the key visual differentiator for the demo. The sequential execution — each step completing with a green check before the next activates — communicates that this is a deterministic, auditable system, not an LLM making things up. Each step is a decision, not a guess. This visual narrative is worth more than any slide deck for getting architecture board approval.

**Animation spec (already designed, confirmed correct):**
- Connector line between steps fills from gray to green as the step completes
- Step circle transitions with a 200ms ease-out
- Step content area expands from 0 height with a spring animation when the step becomes active
- Timing badge fades in on step_complete
- Explore scoring step (step 3) shows a mini bar chart of top 3 candidates with the winner highlighted — this is the near-miss visualization that makes the disambiguation logic tangible

---

### 4.4 Confidence Score Display — The Final Word

Applying the memory override and the analysis from Gap 4:

**Where confidence appears:**
| Location | Format | Audience |
|----------|--------|----------|
| Response metadata footer (Analyst View) | "94% match" in green/amber/red | All users |
| Engineering View panel footer | "94%" large, with sem/graph/fewshot breakdown | Engineers |
| Level 2 ("How I got this") | "Confidence: 94% (High)" — both number and label | Analysts who click |
| CLI done event | `confidence 94%` | CLI users |

**Color thresholds:**
- >=80%: Green (#008767) — proceed, answer is reliable
- 60-79%: Amber (#B37700) — proceed with qualification
- <60%: Red (#C40000) — clarify or no_match state

**What the number means to the user:** "94% match" means the system found a data source that covers 94% of what was asked. It does not mean the answer is 94% accurate (this would be confusing and inaccurate). The label "match" is critical — it describes the retrieval quality, not the answer quality. A 94% match that returns the right SQL is a 94% match. An 80% match that also returns the right SQL is still 80%. The percentage describes the retrieval signal, which is verifiable; the answer accuracy is what the SQL and data validate.

**What not to do:** Do not show confidence as a loading indicator that updates during processing. Confidence is a property of the completed result, not a real-time metric. Showing "confidence: 0%... 45%... 78%... 94%" during pipeline execution would be misleading — those intermediate values are not the same thing as the final routing confidence.

---

### 4.5 Disambiguation — The Full Interaction Design

When the pipeline emits `disambiguate` (two explores within 85% of each other's score):

**In the React app:**
A modal card appears in the response area. Not a dialog overlay — it appears inline in the conversation thread, like a response. This is important: it keeps the conversation metaphor intact. A modal dialog breaks the flow; an inline card continues it.

```
Your question could draw from two different datasets.
Which one are you looking for?

┌─────────────────────────────────────────────────────┐   ┌─────────────────────────────────────────────────────┐
│  Small Business Billed Volume            89% match  │   │  Small Business Credit Portfolio         86% match  │
│                                                     │   │                                                     │
│  Spending by small business cardmembers             │   │  Credit metrics for small business                  │
│  at merchants. Includes all card products.          │   │  accounts — receivables, utilization,               │
│  Finance Cardmember 360                             │   │  and credit lines. Credit Risk                      │
│                                                     │   │                                                     │
│                              [ Use this one ]       │   │                              [ Use this one ]       │
└─────────────────────────────────────────────────────┘   └─────────────────────────────────────────────────────┘

Or rephrase: "What was total billed volume..." or "What was total credit exposure..."
```

The confidence scores (89% vs 86%) are shown here. This is the near-miss situation — the two options are genuinely close — and showing the scores gives the analyst context for why the system is asking. This is the one place where showing two confidence scores simultaneously is appropriate and builds trust rather than creating anxiety.

After selection, the pipeline continues. A subtle note appears in Level 2: "You selected: Small Business Billed Volume. The alternative was Small Business Credit Portfolio (86% match)."

**In ChatGPT Enterprise:**
```
Your question matches two datasets. Which are you looking for?

A: Small Business Billed Volume (89% match)
   Spending by small business cardmembers at merchants.
   Finance Cardmember 360

B: Small Business Credit Portfolio (86% match)
   Credit metrics — receivables, utilization, credit lines.
   Credit Risk

Reply with A or B, or rephrase your question.
```

The follow-up `POST /api/v1/followup` is constructed by the ChatGPT GPT action based on the user's reply.

**Learning signal:** Every disambiguation choice is a training example. If 80% of users pick A when they type "small business revenue," the next version of the routing model should handle this without asking. The feedback endpoint captures this. The learning loop design (ADR-008) handles the update mechanism.

---

### 4.6 Follow-Up Flow — Conversational, Not Transactional

The follow-up experience should feel like talking to a colleague who remembers the last thing you asked, not like submitting a new form.

**Three rules:**
1. Chips submit immediately on click. No fill-then-send. The analyst wants the next answer, not to proofread their query.
2. The conversation context is invisible. The user never needs to re-state the explore, the time range, or the segment from the previous turn. Cortex carries it.
3. Pronoun resolution works. "Show that by card product" is a valid follow-up after a billed business query. The intent classifier handles pronoun-to-entity resolution with the conversation history. If it can't resolve, it asks: "What would you like to break down by card product — the billed volume from the last question?"

**What three good follow-ups look like:**
- Drill-down: "Break down by card product" — same metric, more granular
- Comparison: "Compare to Q4 2024" — same metric, different time
- Adjacent: "Show delinquency rate for Small Business" — different metric, same segment

**What a bad follow-up looks like:**
- "Show billed business for small businesses" — this is the previous query
- "What other data is available?" — too generic, doesn't use the conversation context
- "Show that" — too vague, requires clarification before it can execute

The follow-up generation prompt (Phase 3) must be constrained to avoid these patterns. If it cannot generate three valid follow-ups for the current result, show two or one. Never show a bad suggestion.

---

### 4.7 ChatGPT Enterprise Response Format — The Production Spec

Since the production deployment is ChatGPT Enterprise and zero of the React app UX applies there, this response format is the highest-impact UX artifact that does not yet exist.

**Standard result format (markdown, rendered by ChatGPT):**

```markdown
**Total billed business for Small Business customers last quarter was $4.2B,
up 8.3% from Q3 2025.**

| Quarter   | Segment        | Billed Volume       |
|-----------|----------------|---------------------|
| Q4 2025   | Small Business | $4,213,847,200      |

> Filters applied: Small Business (OPEN) — Q4 2025
> Source: Finance Cardmember 360 | Updated 4h ago | 94% match

**Want to go deeper?**
- Break down by card product
- Compare to Q4 2024
- Show monthly trend

*To see how I got this answer, ask: "Show me the query for the last result"*
```

**Key decisions in this format:**
- Bold answer sentence first. Always.
- Table is standard markdown — renders cleanly in ChatGPT.
- Blockquote for filter translation and metadata — visually distinct from data, less prominent but always visible.
- Confidence as "94% match" in the metadata line.
- Follow-up suggestions as a bulleted list (ChatGPT cannot render clickable chips, but suggested actions in the ChatGPT interface may be available through the actions config).
- Italic footnote for Level 2 access via a conversational prompt rather than a button.

**Disambiguation format in ChatGPT Enterprise:**

```markdown
Your question matches two data sources. Which are you looking for?

**A: Small Business Billed Volume** (89% match)
Spending by small business cardmembers at merchants.
*Finance Cardmember 360*

**B: Small Business Credit Portfolio** (86% match)
Credit metrics — receivables, utilization, credit lines.
*Credit Risk*

Reply with **A** or **B** to continue.
```

**Out-of-scope format in ChatGPT Enterprise:**

```markdown
That's outside what I can help with. I answer questions about Finance data —
spending patterns, customer segments, card metrics, and financial performance.

Things I can answer:
- What was billed business for Small Business last quarter?
- How many active cardmembers by generation?
- What is our revolve index by relationship type?
```

---

### 4.8 Mobile Considerations

The Amex desktop-primary assumption is stated in existing documentation and is correct based on what is known about Finance analyst workflows. Designing for mobile is not a priority for the current phase.

However, there are two mobile scenarios that should not be left undesigned:

**Scenario 1: Executive reading a Cortex result on mobile.** An executive might receive a Cortex result forwarded in Slack or email. The table format must be readable on a narrow screen. Tables wider than 3 columns on mobile become unreadable. The response formatting should detect narrow result sets (<=3 columns) and use full table rendering, and for wider result sets, use a prose summary with a "View full table" link.

**Scenario 2: Someone accessing the demo app on an iPad in a meeting room.** The 800px max-width constraint on the chat panel means the demo app degrades reasonably on tablet viewports without specific work. The Engineering View should be hidden on screens below 1024px — a split panel is unusable at tablet width.

The inline query assistant (Concept B, dropdown suggestions) should be disabled on viewports below 768px as already specified in `lookml-explorer-ux-research.md`. This is the right call.

---

### 4.9 Accessibility and Enterprise Requirements

The demo UI design spec (Section 17) mentions accessibility but does not specify what standard applies. At Amex, the applicable standard is WCAG 2.1 AA at minimum.

Critical accessibility requirements not yet designed:

**Keyboard navigation:** All interactive elements must be keyboard-accessible. The pipeline step animation in the Engineering View must not require mouse hover to reveal step details. Tab order: query input → send → follow-up chips → "How I got this" → navigation.

**Screen reader support:** The live region pattern is essential for streaming responses. The answer text must be announced by screen readers as it streams in — using `aria-live="polite"` on the response container. Pipeline step progress updates should use `aria-live="off"` to avoid overloading screen readers with step updates.

**Color contrast:** The design tokens are mostly compliant. Specific concerns: `--color-text-secondary (#6B7280)` on `--color-surface-primary (#FFFFFF)` is 4.6:1 contrast — passes AA (4.5:1 required) but barely. Any use of secondary text on colored backgrounds (e.g., amber warning on warning-light background) needs audit.

**Focus management:** When a disambiguation modal appears, focus must move to it. When it closes (after selection), focus must return to the query input.

**Reduced motion:** The step animation, streaming text, and transition effects should respect `prefers-reduced-motion`. For users with this set, animations should be instant transitions, not timed transitions.

---

## Section 5: Competitive Analysis

### 5.1 ThoughtSpot (Spotter, formerly Sage)

**What they do well:**

ThoughtSpot evolved from Sage to Spotter, which now provides agentic analytics with multi-step reasoning. The experience goes beyond single-query Q&A to connected analysis: "What's our ROC?" → "Why did it change?" → "Which merchants drive that?" in a connected thread with a shared state.

ThoughtSpot's SpotIQ push intelligence ("here's something interesting we noticed") solves a different problem than query answering — it teaches users what the data contains without them having to ask. This is a discoverability approach that Cortex does not have.

Usage-ranked autocomplete (ranking suggestions by what your organization actually queries most) is superior to alphabetical or recency-based suggestions. It trains the interface to the organization's actual vocabulary.

**What they get wrong:**

The field picker model — even in a conversational interface — still requires users to understand the data structure. ThoughtSpot autocomplete helps users who partially know what they want. Users who don't know what to ask are still lost.

Spotter's agentic reasoning adds latency. Moving from instant answers (sub-3 seconds) to multi-step reasoning (30+ seconds for complex analyses) breaks the "ask a question, get an answer" mental model that Finance analysts expect.

The schema is still opaque. ThoughtSpot does not expose a "here are all the ways you can break down this metric" view in natural language.

**What Cortex does better:**

The semantic layer routing via LookML structural signals is more architecturally sound than ThoughtSpot's column-matching approach. When Cortex picks an explore, it knows why — the coverage score, the base-view declaration, the join topology. ThoughtSpot's routing is a scoring model that is opaque even to ThoughtSpot.

Near-miss detection and explicit disambiguation is a stronger trust mechanism than silent selection. Cortex tells you when it is uncertain and asks; ThoughtSpot generally picks and proceeds.

Filter value resolution (mapping "small businesses" to "OPEN") with a learnable catalog is a moat. This domain-specific vocabulary problem is underestimated by competitors.

---

### 5.2 Looker Explore Assistant / Looker Conversational Analytics

**What they do well:**

Looker's native advantage is trust through structural integrity. When Looker generates SQL, it goes through the semantic layer — joins are correct, filters are validated against the model, partition safety is enforced by Looker's runtime. The SQL correctness bar is higher than any LLM-only approach.

Multi-turn conversation with "Show that by region" or "Change this to a stacked area chart" (as of Looker 25.x Conversational Analytics) is a significant UX improvement over earlier versions.

The integration with Looker Studio means results can be pinned to dashboards and shared — an action layer that Cortex currently lacks.

**What they get wrong:**

Looker Conversational Analytics still requires users to be in the Looker environment. ChatGPT Enterprise integration (Cortex's deployment target) requires the Looker MCP pattern, which is architecturally correct but means latency is added by the MCP round-trip.

Looker's field picker metaphor bleeds into the conversational interface. Users sometimes see LookML field names (e.g., `custins_customer_insights_cardmember.total_billed_business`) in responses because the model uses them internally and the response formatting doesn't always strip them.

The Explore Assistant (the earlier Gemini-powered version) had a known failure mode: it would hallucinate dimensions that don't exist in the model because the LLM was generating LookML queries from general knowledge rather than from retrieved model context. Cortex's hybrid retrieval approach (vector + graph validation) directly solves this failure mode.

No confidence scoring. Looker Conversational Analytics gives you an answer or an error — there is no signal for "I found a partial match" or "I'm uncertain about this field."

**What Cortex does better:**

The confidence-gated action system (proceed at >=0.85, qualify at 0.70-0.84, disambiguate at near-miss, clarify at <0.70) is more nuanced than Looker's binary success/failure. Users of Cortex get meaningful signal about result reliability.

The hybrid retrieval pipeline (vector + graph validation + few-shot) is more accurate on the schema routing problem than Looker's pure LLM approach. The 83% retrieval accuracy (current state) targets 90%+ — already competitive with Looker Explore Assistant's known performance on complex cross-join queries.

The PipelineTrace and Engineering View are transparency tools that Looker does not offer. A data engineer can audit exactly why Cortex picked a particular explore and what SQL it generated. Looker Conversational Analytics is a black box to engineers.

---

### 5.3 Snowflake Cortex Analyst

**What they do well:**

Snowflake Cortex Analyst's semantic model YAML approach is the most developer-friendly schema definition format for NL2SQL. Authors define metrics, synonyms, and validated queries in a YAML file that can be version-controlled, reviewed in PRs, and deployed through standard CI/CD. This is a better developer experience than LookML for the specific purpose of NL2SQL.

The "custom instructions" feature (January 2025 preview) allows telling Cortex Analyst exactly what "performance" or "financial year" means in your organization. This is a direct solution to the vocabulary gap problem. Cortex's filter catalog serves a similar purpose but is less flexible — filter catalogs are for filter values, not for metric definitions.

The Streamlit integration gives a quick chat interface without custom frontend work. For organizations without Ayush, this would be the fastest path to a working demo.

**What they get wrong:**

Snowflake Cortex Analyst is Snowflake-native. It cannot route to Looker. For Amex's architecture (BigQuery + Looker semantic layer + SafeChain gateway), Snowflake Cortex Analyst is not a viable deployment target regardless of UX quality.

The YAML semantic model is developer-authored, not data-steward-authored. Renuka's semantic enrichment work (the metadata enrichment that feeds Looker) has no path to a Snowflake YAML. The semantic layer split (Cortex on Looker, Cortex Analyst on Snowflake) would create two maintenance surfaces.

No streaming pipeline visualization. Snowflake Cortex Analyst returns a completed response — there is no transparency into how the routing decision was made. For an architecture approval at Amex, the absence of an auditable decision trace is a vulnerability.

**What Cortex does better:**

Looker as the semantic layer is architecturally superior to a YAML file for a 5 PB, 8,000 dataset environment. Looker's model validation, explore management, and deployment tooling are enterprise-grade. Cortex inherits that enterprise posture; Snowflake Cortex Analyst starts from a YAML file.

The Amex-specific filter catalog (the hash/synonym/fuzzy/LLM 5-pass resolution) handles the kind of domain-specific vocabulary ("OPEN", "GCS", "GMNS") that a generic semantic model YAML cannot. This is a moat for the Amex internal use case.

---

### 5.4 Power BI Copilot / Q&A

**What they do well:**

Power BI Q&A's training interface is the best in class for vocabulary teaching. Authors can define synonyms, mark queries as "featured questions," and review Q&A errors to teach the system correct phrasing. The maintenance loop is designed for non-engineers.

Power BI Copilot's "summarize this report so I can ask questions" prompt is a genuinely useful onboarding pattern. It generates a natural-language description of what the data covers. This is Concept C from the lookml-explorer-ux-research, implemented as a prompt, not a feature.

The integration with the broader Microsoft 365 ecosystem (Teams, Outlook, SharePoint) means Power BI answers can be surfaced in the tools Finance analysts already use — without requiring them to open a separate interface. This is a distribution advantage Cortex does not have.

**What they get wrong:**

Power BI Copilot's filter accuracy is a known weakness. Verified Answers with filter mismatches (filters not applied consistently) reduce trust rapidly. The symptom: user asks "Show me Q4 2025 data" and gets Q4 2024 because a date filter was applied inconsistently. This is the same class of problem Cortex's filter catalog and partition filter injection solves.

Semantic model clarity issues ("Without clear naming, comprehensive synonyms, and thoughtfully written metadata, Copilot might interpret the same question asked by two departments as entirely separate queries") is a content governance problem that compounds over time. Cortex's filter catalog provides a single source of truth for vocabulary resolution.

The Power BI chat interface is embedded in the Report viewer context — users need to be looking at a specific report to ask questions about it. Open-ended cross-report queries are limited. Cortex's cross-explore routing is more flexible.

**What Cortex does better:**

The confidence-gated action system catches filter ambiguity before it produces a wrong answer. Power BI Copilot's silent filter mismatch is worse UX than Cortex's explicit disambiguation — even though the disambiguation adds friction, it prevents the wrong answer.

Cortex's filter resolution catalog (with the learning loop from user corrections) is more maintainable than Power BI's manual synonym training at scale. As the dataset grows from 5 to 50 to 500 filter values, the 5-pass resolution scales; Power BI's manual training does not.

---

### 5.5 What No Competitor Does Well — Cortex's Whitespace

After reviewing all five competitors, one gap is consistent across all of them:

**None of them show the user why they got the answer they got, in a way that non-engineers can verify and act on.**

ThoughtSpot picks an answer and shows it. Looker generates SQL and shows it (sometimes). Snowflake shows SQL but no routing rationale. Power BI shows a result or an error.

Cortex's combination of:
- Filter translation inline in the response ("small businesses" → OPEN)
- Confidence percentage on every result
- Near-miss disambiguation with two scored options
- Level 2 disclosure showing the exact field mapping and SQL with plain-English translation
- Full pipeline trace accessible for engineers

...is the deepest transparency stack of any NL2SQL tool in production. This is a competitive differentiator. It should be the primary message when presenting to Kalyan and Jeff: "We built the first NL2SQL tool that Finance analysts can trust because they can verify every answer."

---

## Section 6: Summary — What to Do First

### Immediate Actions (Before Next Demo)

1. **Populate `sample_questions` in the `/api/v1/capabilities` endpoint.** Fill it from `80-percent-coverage-queries.md`. Six queries, five explores. One hour of content work. The starter cards in the demo app are blocked on this data.

2. **Implement the CLI `/feedback` command.** The spec is written in `cortex-ux-specification.md` Section 6. The API endpoint exists. This is the learning loop's primary signal source and it has been designed but not coded.

3. **Audit `EXPLORE_DESCRIPTIONS` in `config/constants.py`.** Ensure every description is in plain business language. The disambiguation modal depends on these strings. If they contain LookML identifiers, the modal will look technical.

4. **Add filter translation to the standard CLI response output.** Not only in `/trace`. Format: `filters: "small businesses" → OPEN  |  time: Q4 2025`. One line. Maximum trust signal per character.

5. **Write the ChatGPT Enterprise response format spec** (Section 4.7 of this document is the start). This is the production surface that 100% of non-demo users will experience.

### High Priority (Before BU Rollout)

6. **Implement an error message mapping layer** that translates internal exceptions to user-safe copy before they reach the SSE `message` field. The UX spec error taxonomy is the source of truth.

7. **Build the CLI analyst mode** that collapses 7 pipeline steps to 3 human-readable phases and surfaces the answer prominently at the top, not after the SQL block.

8. **Decide on discoverability approach** (Concepts A, B, or C from lookml-explorer-ux-research) and assign to Ayush with a specific scope. Concept C is the only one that works in production — implement it as a system prompt capability. Concepts A and B are demo enhancements.

9. **Add `result_type` field to the `results` SSE event** to enable chart recommendations and empty-result handling in the frontend.

### Medium Priority (Before 3-BU Expansion)

10. **WCAG 2.1 AA accessibility audit** of the React demo app once built. Focus on keyboard navigation, screen reader live regions, and color contrast on semantic colors.

11. **Design session timeout and idle state** — what happens when a conversation is left open for 30 minutes and BigQuery connections have aged.

12. **CSV export endpoint** (`GET /api/v1/export/{trace_id}`) for large result sets. The UX spec promises this; the API does not implement it.

13. **A/B test design for follow-up chip placement** — below source citation vs. below table. The hypothesis is that chips below the source citation (current spec) are seen before the user has evaluated the result, which may cause premature continuation. Test with the Daily Analyst persona.

---

*End of UX Research Synthesis. File path: `/Users/bardbyte/Desktop/amex-leadership-project/cortex/docs/design/cortex-ux-research-synthesis.md`*
