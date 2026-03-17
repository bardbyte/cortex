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

---

## Section 7: Thinking Visualization Research — Competitive Audit and Cortex Design Recommendations

**Author:** UX Research (ux-researcher agent)
**Date:** March 16, 2026
**Research basis:** Competitive audit of Claude, Gemini, ChatGPT/o-series, Perplexity, Cursor/Windsurf, v0; pattern synthesis from ShapeOfAI pattern library, Smashing Magazine agentic UX research, digestibleux.com reasoning display analysis, IntuitionLabs conversational AI comparison, and AI UX Design Guide.
**Applies to:** Both Analyst View and Engineering View for Cortex's 5-step pipeline (Intent Classification → Semantic Search → Explore Scoring → Filter Resolution → SQL Generation).

**How to read this section:** Part 1 is the raw competitive audit — what each product actually does, described precisely enough to implement from. Part 2 distills audit findings into named patterns with explicit Adopt/Adapt/Skip recommendations for Cortex. Part 3 is the opinionated design spec for Cortex's thinking UX. Part 4 covers conversational elements.

This section does not replace any prior UX decisions. It extends them with external competitive evidence and provides the specific implementation details that were missing from the original specs.

---

### 7.1 Part 1: Competitive Audit

#### Claude (Anthropic) — Extended Thinking

**Model:** Claude 3.7 Sonnet, Claude 4 series with extended thinking enabled.

**The thinking block pattern:**

When extended thinking is enabled, Claude renders a visually distinct block above the final response. This block is not a chat bubble — it is a separate container with a different visual treatment: a lighter background, a subdued text color (gray rather than the primary near-black used for responses), and a collapsible/expandable affordance.

The block header reads "Thinking" with an animated spinner icon while processing is active. The spinner is not a standard loading ring — it is an animated icon unique to Claude's brand, suggesting forward momentum rather than circular waiting. Next to the spinner, a time counter runs: "Thinking (4s)..." "Thinking (12s)..." up to whatever budget the model uses. This counter performs two functions: it communicates that the model is genuinely working rather than stalled, and it sets expectations for users about when the answer will appear.

The thinking content itself streams in as continuous prose. It is not formatted with headers or bullets during generation — it reads like a dense scratchpad rather than structured output. The text renders at a slightly smaller size than the final answer and in a muted color, visually de-emphasizing it relative to the upcoming response. Users can read the thinking in real time as it streams in, but the visual treatment signals "this is process, not product."

When thinking completes, the block transitions to a collapsed state automatically. The header changes from "Thinking (18s)..." to a clickable disclosure: "Thought for 18 seconds" with a chevron pointing down. The final answer then renders immediately below in normal chat format. The transition is not animated dramatically — the thinking block simply closes (with a height-collapse animation of roughly 200ms) and the answer begins streaming.

The collapsed state persists. Users can re-expand the thinking block after the answer is complete by clicking the disclosure row. The expanded state shows the full thinking trace, scrollable, with the same visual treatment as during generation.

**What this does well:**

The separation of thinking-as-process from answer-as-product is clean. The answer always comes after. The automatic collapse means the default state is clean even on long-running thoughts. The time counter prevents the uncanny silence problem — users know the system is computing, not stuck.

**What this gets wrong:**

The thinking content is largely unstructured for the user. It reads like raw chain-of-thought rather than a guided explanation. For a non-technical user, the thinking block is noise even when it's open. Claude has not solved the "thinking UX for non-engineers" problem — the block is transparency-for-engineers dressed as transparency-for-everyone.

The shimmer animation that plays inside the thinking block during generation has been criticized by power users as distracting. A GitHub issue specifically requests the ability to disable it. This is a signal that process animations can become friction for repeat users who have already internalized what the thinking block means.

**Relevance to Cortex:** Claude's collapsible thinking block is the direct conceptual ancestor of what the Engineering View panel does — it shows work, then collapses it, then shows the answer. The key difference is that Cortex's pipeline steps are structured (5 named stages with typed outputs) while Claude's thinking is unstructured prose. Cortex has better raw material for a thinking visualization than Claude does.

---

#### Gemini (Google) — Deep Research and Thinking Mode

**Model:** Gemini 2.0 Flash Thinking, Gemini 3 Deep Research.

**The research progress pattern:**

Gemini Deep Research uses a fundamentally different model than Claude's thinking block. Rather than a prose scratchpad, Gemini shows a structured progress sidebar that tracks distinct research phases. The research process runs in three visible stages:

Stage 1 (query interpretation, roughly 10-20 seconds): A plan panel appears, listing the sub-topics and research angles the model intends to investigate. These are rendered as a bulleted list of questions the model will answer. Users can read this plan before research executes. This is an "intent preview" — show what you're about to do before you do it.

Stage 2 (research execution, 1-2 minutes for deep research): The sidebar shows live search statistics — "Searched 14 sources," "Reading 3 pages" — as the model retrieves and processes web content. Sources appear as they are found, rendered with favicon, domain name, and title. This is a live accumulation view, not a progress bar.

Stage 3 (synthesis, 30-60 seconds): The model drafts the final report. A partial preview of the document appears as it is written. Users see section headers appear before the body text, providing structure before completeness.

The transition from research to final answer is a distinct mode change. The progress sidebar closes and the full structured report renders. The report includes proper headers, citations, and a source panel — a right-side drawer showing all referenced sources with links.

**The thinking mode pattern (Gemini 2.0 Flash Thinking):**

For shorter tasks, Gemini uses a lighter pattern. A "Thinking..." label with an animated throbber appears above the response area. The model generates its reasoning as continuously scrolling text with bullet points and numbered lists — more structured than Claude's prose scratchpad. The completion state is the problem: Gemini does not clearly signal when thinking ends and the answer begins. Users sometimes continue reading thinking output that has already transitioned to the final response, creating confusion about which content is authoritative.

**What this does well:**

The structured plan (Stage 1) is the strongest element. Showing "here are the five questions I'm going to answer" before beginning builds user confidence that the model understood the task. It also provides a natural recovery point — if one of the planned sub-topics is wrong, the user can see it early.

The live source accumulation during Stage 2 is excellent for the user's perception of thoroughness. Even if the final answer is identical to one that took 10 seconds, the experience of watching 14 sources be consulted creates more trust in the result than a fast answer would.

**What this gets wrong:**

The deep research UX is designed for a 2-minute task. For a sub-3-second query (Cortex's target), staging research into three phases would feel slow and patronizing. The pattern is correct for depth; it is wrong for speed.

The structured plan in Stage 1 creates an implicit contract: the user expects all five planned sub-topics to appear in the final report. If the model drops one, the user notices. Cortex's pipeline does not have this problem because the steps are mechanical, not thematic.

**Relevance to Cortex:** The Stage 1 "intent preview" maps directly to Cortex's Intent Classification step. Showing "I understood your question as: metric=billed business, segment=Small Business, time=Q4 2025" before executing the retrieval is exactly what Cortex should do. This is the single highest-value pattern from the Gemini audit. The full Deep Research staging model is not applicable due to latency constraints.

---

#### ChatGPT / o-series (OpenAI) — Reasoning Models

**Models:** GPT-4o (non-reasoning), o3, o4-mini, GPT-5 Thinking.

**The non-reasoning model pattern (GPT-4o):**

Standard ChatGPT shows a minimal processing indicator: three animated dots in the response position, or a "shimmer" effect on the composer as the response streams in. There is no thinking visualization. The response streams word-by-word starting immediately. This is the "magic" end of the spectrum — the system hides all process and presents only product.

**The o-series reasoning pattern (o3, o4-mini):**

The reasoning models introduced a new visual pattern. Before the response text begins, a collapsible reasoning trace appears. The header reads "Thought for [N] seconds" where N is the actual compute time — commonly 5-45 seconds for complex tasks, up to several minutes for o3-pro.

The critical interaction design: the reasoning trace is collapsed by default. Users see "Thought for 12 seconds" with a chevron, and then the answer below. They can expand to read the reasoning, but the default state is collapsed. This is the opposite of Claude's approach: Claude streams thinking in real time and auto-collapses at completion; ChatGPT collapses by default and the user opts into expanding.

The GPT-5 Thinking implementation adds a duration control in the composer: a small toggle labeled "Light," "Standard," "Extended," or "Heavy" that lets users choose how much compute to spend on a given question. This is "Autonomy Dial" pattern — users calibrate the depth of thinking to their tolerance for latency.

**The Searching pattern (web tools):**

When ChatGPT uses web search, a different visual pattern appears: a horizontally scrolling list of source tiles appearing above the response. Each tile shows a favicon, domain, and title. The tiles appear in sequence as sources are found, animating in from the right. When the response begins streaming, the source tiles remain visible above the response text in a compact panel.

**What this does well:**

The default-collapsed reasoning trace is the most respectful of the repeat user. On the 50th query, the analyst does not want to watch thinking stream by — they want the answer. The opt-in disclosure is the right default.

The duration control (Light/Standard/Extended/Heavy) is the most honest representation of the speed/accuracy trade-off in any AI interface. For Cortex, this translates to: should the user be able to control retrieval depth? The answer is probably no for Finance analysts (they want the best answer, not a speed choice), but the pattern is worth knowing.

**What this gets wrong:**

The horizontal source tile animation is visually heavy. It occupies significant vertical space and the animation itself draws attention to the research phase rather than the answer. On sub-5-second queries, it feels like unnecessary ceremony.

The "Thought for N seconds" label is accurate but not informative. Users do not know what the system was thinking about. "Thought for 18 seconds" is less useful than "Analyzed your question and searched 3 sources" — the latter tells you what happened, not just how long it took.

**Relevance to Cortex:** The default-collapsed pattern for engineering detail is a direct recommendation for Cortex's Analyst View. The Engineering View is the opt-in expansion — exactly what o-series does with its reasoning trace. The duration control is not applicable to Cortex, but the principle (let the user choose depth) surfaces an open question: should Cortex offer a "quick answer" mode that skips filter resolution for lower-stakes queries? Not for V1, but worth noting.

---

#### Perplexity — Multi-Source Research Progress

**Product:** Perplexity Pro Search, Perplexity Deep Research.

**The Pro Search pattern:**

Perplexity's Pro Search shows a sequential progress flow above the response. The stages are rendered as text labels with status indicators that transition through three states: pending (gray, subdued), active (blue, with a spinner), and complete (green checkmark). The labels read something like:

- "Analyzing your question" (completes in ~0.5s)
- "Searching for relevant sources" (1-3s, shows "Searched 6 sources" when done)
- "Reading pages" (1-2s, shows "Read 3 pages")
- "Generating answer" (transitions to streaming response)

The transition from the last step to the answer is the defining moment of Perplexity's UX. The progress steps do not disappear — they collapse into a compact "Pro Search" badge above the response. The badge is clickable and expands to show the full step log. This creates a clean default state (answer prominent) with a one-click path to process transparency.

Citations in the response are inline superscript numbers: [1], [2], [3]. On hover, a small tooltip card appears showing the source title, domain, and a 1-2 sentence excerpt from the source that supports the claim in the adjacent text. On click, the source opens in a new tab. On the right side of the response, a persistent Sources panel lists all cited sources with icons and titles.

**The Deep Research pattern:**

Perplexity Deep Research is the highest-fidelity multi-step research UX of any consumer AI product. The key design innovation is the expandable step panel — a side panel that shows the model's research plan as it executes, with each step expandable to show the actual content retrieved. Users can click on any step to see what the model read, which sources it evaluated, and what it decided to include.

The research progress shows "live search stats" — a counter that increments as sources are scanned: "32 sources analyzed," "8 pages read in full." This live count creates the perception of thoroughness even before the answer appears.

**What this does well:**

The collapse-to-badge pattern is the single most elegant solution to the "show process without burying the answer" problem. The step log is prominent during processing (user knows what's happening) and non-intrusive at rest (user reads the answer unobstructed). The badge is a permanent link to the process.

Inline citations with hover-card previews are the best citation UX in the industry. The preview tooltip answers the user's next question ("what does this source say?") before they have to leave the page.

**What this gets wrong:**

The progress step labels ("Analyzing your question," "Searching for relevant sources") are generic. They communicate category, not content. "Searching for relevant sources" is true for every query — it does not tell the user what was found. Perplexity partially solves this with the "Searched 6 sources" count appended on completion, but the label itself is not adaptive.

**Relevance to Cortex:** The collapse-to-badge pattern directly addresses the Analyst View design challenge. Cortex's three-phase progress indicator (Analyzing → Finding Data → Building Query) should collapse to a metadata badge on completion, not disappear. The badge is the anchor for Level 2 disclosure. The hover-card citation pattern maps to what Cortex should do with explore attribution — hovering over "Finance Cardmember 360" should show a tooltip with the explore description and coverage fields, not just the name.

---

#### Cursor / Windsurf — Agentic Tool Call Visualization

**Products:** Cursor (Claude-backed), Windsurf (Codeium).

**The agentic tool call pattern:**

Code AI agents execute multi-step sequences: read files, search codebases, write code, run tests, apply edits. Cursor and Windsurf both render these steps as a sequential execution trace in the response area — not in a sidebar, but inline in the chat thread.

Each tool call is rendered as a distinct card:

```
[ Tool: Read file ]    src/api/server.py    ✓ 247ms
[ Tool: Search ]       "SSE event schema"   ✓ 3 results
[ Tool: Edit file ]    server.py            ✓ 3 changes applied
```

The card includes: tool name, argument (truncated), status icon, and timing badge. Cards appear sequentially as the agent completes each step. The final code edit or answer renders at the bottom after all tool cards.

Windsurf's "Cascade" agent adds a richer visualization: file tree indicators that highlight which files were touched, a diff view embedded inline showing exactly what changed, and a "revert" button on each edit card. This is the "Action Audit" pattern — every agentic action is visible and reversible.

Cursor's approach is leaner: tool cards are compact (single line each), collapsible with one click to show full detail, and the default state is expanded to show the sequence. The reasoning here is that Cursor's primary users are engineers — they want to see the tool calls.

**What this does well:**

The sequential tool card pattern directly maps to a pipeline execution — each card is one step, each card has a status, the sequence tells the story. This is the closest analog to what Cortex's Engineering View pipeline trace does.

The inline placement (same thread as the conversation, not a side panel) is interesting. It means the user reads: question → tool calls → answer, in one continuous scroll. There is no toggling or panel management.

**What this gets wrong:**

Inline tool cards work when users are technical and want every step visible. For Cortex's Daily Analyst persona, inline tool cards would interrupt the answer flow — the user would have to scroll past pipeline steps to reach the answer. The side panel (Engineering View) is the correct choice for Cortex's mixed-audience context.

The revert/undo pattern (Windsurf Cascade) is critical for code agents where actions are permanent. It is less relevant for Cortex, which generates SQL but does not execute it. But the principle — that every agentic step should be auditable and ideally reversible — applies to filter resolution: if a filter was resolved incorrectly, the "Wrong filter?" link is Cortex's equivalent of the revert button.

**Relevance to Cortex:** The sequential card pattern is what the Engineering View pipeline trace should look like — not as a sidebar with a list, but as a sequence of expandable cards, each representing one pipeline step. The timing badge on each card (e.g., "287ms") is already in the spec; this research validates it as a broadly used pattern. The step-by-step narrative communicates "deterministic pipeline," which is the opposite of "LLM making things up."

---

#### v0 (Vercel) — Code Generation with Live Preview

**Product:** v0 (v0.app), powered by Vercel's composite model family.

**The generation pattern:**

v0 generates React components from natural language prompts. The UX is structured around three simultaneous surfaces: the chat thread, a code editor panel, and a live preview panel. All three update in real time as generation proceeds.

The chat response streams in with step-level narration: "I'll create a dashboard component with..." followed by the generated code. The code appears in the code panel as it is written — syntax-highlighted, auto-formatted, with a progress indicator on the file tab (a pulsing dot while writing, a static dot when complete).

The live preview panel updates as code completes — not as individual tokens stream in, but as complete logical units (component, function, JSX block) are written. This prevents showing broken partial renders. The render timing is heuristic — v0 detects syntax completeness and triggers a preview compile.

The "inline logic" pattern: while generating, v0 renders the remaining planned steps as subdued text below the current generation point. If the model plans to generate a header, a data table, and a chart, the outline ("Header — Table — Chart") appears before the code is written. Steps that complete are rendered fully; steps not yet started remain in outline form. This creates a "skeleton → content" reveal that users find reassuring.

**What this does well:**

The skeleton-to-content reveal is distinct from every other product in this audit. It answers the question "what is the system going to produce?" before it produces it. Users can abort early if the planned output is wrong.

The multi-panel layout (chat + code + preview) is the clearest separation of layers in any AI product. Each panel is purpose-specific. The chat is conversation; the code is the artifact; the preview is the validation.

**What this gets wrong:**

The multi-panel layout requires significant screen real estate. v0 works on wide desktop displays; it degrades severely on narrow screens. This is a reasonable trade-off for a code tool but would not work for Cortex's mixed audience (including executives on laptops).

The live preview approach is only possible because v0 generates a self-contained web component that can be rendered in an iframe. Cortex generates SQL, which has no equivalent "live preview" — the SQL cannot be executed in the browser. The pattern is not directly portable.

**Relevance to Cortex:** The skeleton-to-content reveal has a Cortex analog: the Intent Summary that appears before retrieval executes. "I'm going to look for: metric=billed business, segment=Small Business, time=Q4 2025" is the skeleton. The retrieved result is the content. Showing the skeleton allows early correction without waiting for the full pipeline to run. This pattern is recommended for adoption in modified form.

---

### 7.2 Part 2: Pattern Library

The following are named patterns distilled from the competitive audit. Each has an Adopt/Adapt/Skip recommendation with rationale specific to Cortex.

---

#### Pattern 1: Collapsed-by-Default Reasoning Trace

**Used by:** ChatGPT o-series (primary), Claude (inverted — streams then collapses), Perplexity (collapse-to-badge variant).

**How it works:** Process detail is hidden by default after completion. The user sees the answer first. Process is accessible via a single-click disclosure. The disclosure label summarizes the process ("Thought for 18 seconds," "Pro Search," "How I got this").

**Cortex recommendation: ADOPT (already specified, now validated).**

This is the pattern that the existing spec already calls "Level 2 disclosure" and "How I got this." The competitive research validates this as the correct default. The key implementation note: the collapsed state must show a meaningful summary, not just "View details." "Found in Finance Cardmember 360 — 94% match — 1.2s" is a better collapsed label than "View details" because it gives the analyst the key signal without requiring the click.

**Implementation delta:** The current spec's MetadataFooter collapsed state shows three small pill badges (explore, confidence, freshness). This is correct. Add the total pipeline time as a fourth badge for the Engineering View. In Analyst View, collapse to a single summary line: "Finance Cardmember 360 · 94% match · Updated 4h ago · [How I got this]".

---

#### Pattern 2: Intent Preview (Pre-Retrieval Echo)

**Used by:** Gemini Deep Research (Stage 1 plan), v0 (skeleton reveal), Smashing Magazine agentic design spec (Intent Preview pattern).

**How it works:** Before the system begins executing, it shows the user what it understood from their query and what it plans to do. The user can correct misunderstandings at the lowest-cost moment — before any retrieval or generation has happened.

**Cortex recommendation: ADOPT with modification.**

The raw form — "Here are the five research questions I'm going to answer" — is designed for multi-minute deep research tasks. Cortex's pipeline completes in under 2 seconds total. An intent preview that adds 1 second before retrieval starts would double perceived latency for fast queries.

The correct implementation for Cortex is a zero-latency echo, not a separate stage. When intent classification completes (the first 200-460ms), the system renders a small entity extraction summary before retrieval begins. This does not add time — it surfaces information that was already computed.

The echo format:
```
You asked about: billed business  ·  Small Business  ·  Q4 2025
```

This appears as a subdued line between the user's message and the pipeline progress indicator. It is not a question — it is a statement. It confirms what was understood. If something is wrong, the user can type a correction immediately. The pipeline can continue running in parallel — the echo is display-only.

The echo becomes especially valuable for filter values: if the user typed "small biz" and the intent classifier extracted "Small Business," seeing "Small Business" in the echo before retrieval confirms the synonym resolved correctly without requiring Level 2 expansion.

---

#### Pattern 3: Sequential Step Cards with Status Indicators

**Used by:** Cursor (inline), Windsurf Cascade (inline with diff), Cortex Engineering View (side panel — already designed).

**How it works:** Each pipeline step is rendered as a discrete card with a name, status indicator (pending/active/complete/error), timing badge, and expandable detail. Steps activate sequentially as the pipeline progresses. The visual sequence communicates that this is a deterministic, ordered system.

**Cortex recommendation: ADOPT for Engineering View (already specified), DO NOT adopt for Analyst View.**

The existing Engineering View spec correctly implements this pattern. The research validates the specific details: status circle transitions (gray → pulsing blue → solid green → amber for near-miss → red for error), timing badges that appear on step completion, and expandable step detail.

The recommendation to not adopt this for Analyst View is equally important. Cursor uses inline step cards because its primary users are engineers who want to see every tool call. Cortex's Daily Analyst is not this user. Inline step cards in the chat thread would interrupt the answer reading experience. The side panel segregation is the correct architectural choice.

**Implementation note for Engineering View:** The step card expand/collapse behavior needs a specific trigger decision. Two options: auto-expand the active step (current spec implies this), or let users manually expand any step at any time. The recommendation is auto-expand-then-auto-collapse: when a step becomes active, its detail section expands automatically; when the step completes, it collapses to the completed summary card, and the next step expands. This maintains the sense of live progress without requiring user interaction to follow the pipeline.

---

#### Pattern 4: Collapse-to-Badge (Perplexity's process persistence)

**Used by:** Perplexity Pro Search (the collapsed "Pro Search" badge above the response).

**How it works:** When processing completes, the step-by-step progress indicator does not disappear — it collapses into a compact badge or summary row that persists above the response. The badge is clickable to re-expand the full step log. This means the process is always accessible but never intrusive.

**Cortex recommendation: ADOPT as modification to current spec.**

The current spec has the processing indicator replaced by the response when complete. This means the process disappears. The Analyst never has a one-click path back to "what happened during processing" without scrolling to the metadata footer and clicking "How I got this."

The Perplexity badge pattern solves this elegantly. After the three-phase Analyst View progress completes, it should collapse to a single-line badge above the answer:

```
[ ✓ Analyzed · Found in Finance Cardmember 360 · Built query · 1.2s ]  [Details ▾]
```

This badge is permanently visible above every response. Clicking "Details" expands to the Level 2 disclosure. This creates a single consistent disclosure affordance rather than requiring users to find the metadata footer.

---

#### Pattern 5: Inline Citation with Hover Preview

**Used by:** Perplexity (inline [n] with hover tooltip card), Claude web search (footnotes with inline links), ShapeOfAI Citations pattern.

**How it works:** Source attributions are embedded inline at the sentence level — not just listed at the bottom. On hover, a tooltip shows the source title, origin, and a brief excerpt. On click, the source opens or expands.

**Cortex recommendation: ADAPT.**

Cortex's "source" is not a web page — it is a Looker explore and model. The citation pattern needs adaptation: instead of web source citations, the inline attribution shows data source metadata.

The adapted pattern: the source line at the bottom of every response ("Finance Cardmember 360 · Updated 4h ago · 94% match") becomes an inline, hoverable element. Hovering over "Finance Cardmember 360" shows a tooltip:

```
Finance Cardmember 360
Finance Analytics > Cardmember Model
Covers: Billed business, active accounts, spend patterns
Last refreshed: 6 hours ago
Fields matched: 4 of 4 requested
```

This is the hover-card citation applied to data sources rather than web pages. It answers the question "where did this come from and does it cover what I asked?" at hover cost rather than at click cost. This is directly buildable from the explore metadata already in the pipeline response.

---

#### Pattern 6: Live Entity Extraction Display (Streaming Filter Translation)

**Not used by any competitor in this exact form.** Derived from the combination of Perplexity's live stats, Gemini's Stage 1 plan, and Cortex's unique filter resolution capability.

**How it works:** As the intent classification step executes, the extracted entities appear in real time beside or below the user's query. The user watches their natural language query get parsed: "small businesses" becomes "Small Business (OPEN)" as the filter resolves, "last quarter" becomes "Q4 2025" as the time parser fires. This is the filter translation made visual during processing, not just in the final result.

**Cortex recommendation: ADOPT as the defining differentiated pattern for Cortex's processing UX.**

No competitor shows filter resolution in real time. ThoughtSpot matches field names. Looker resolves filters silently. ChatGPT shows no filter reasoning at all. Cortex is the only product in this space that resolves natural language filter values through a 5-pass cascade (exact → fuzzy → synonym → semantic → LLM) and has the confidence signal to back it up.

Showing this resolution as it happens — "small businesses" → "OPEN" appearing as a real-time translation — is the UX equivalent of showing work in a math exam. It proves the system is doing what it says it's doing. For Finance analysts who have been burned by silent filter mismatches in Power BI and Looker, this is a revelation.

The implementation: during the Filter Resolution step (Step 4, which runs in the 1,275-1,800ms window), the processing indicator area shows:

```
Translating filters:
  "small businesses"  →  OPEN  (exact match in business segment catalog)
  "last quarter"      →  Q4 2025  (resolved from current date)
```

These lines appear as the filter resolution executes. They are visible for the remaining duration of the pipeline, then collapse into the "Filters applied:" line in the final response. The collapsed result carries forward the translation — nothing is lost, it just compacts.

This pattern is a potential patent candidate. See Section 7.5 for the flag.

---

#### Pattern 7: Structured Step Labels (Adaptive, Not Generic)

**Used by:** Gemini Stage 1 plan (partially), Perplexity step labels (generically).

**How it works:** Pipeline step labels adapt to the content of the query rather than being generic strings. Instead of "Searching for relevant sources" (always the same), the label says "Searching for spending metrics in Finance datasets" — parameterized with the extracted entities.

**Cortex recommendation: ADOPT.**

The current UX spec uses fixed labels: "Analyzing your question" / "Finding relevant data" / "Getting results." These are correct as fallbacks but miss an opportunity.

Once intent classification completes (Step 1), Cortex knows what it's looking for. The retrieval step label can be parameterized:

```
Searching for billed business data across Finance explores...
```

Once Explore Scoring completes (Step 3), the SQL generation label can be parameterized:

```
Building query against Finance Cardmember 360...
```

This requires SSE event content to be threaded into the label template, but the information is already in the events — it just needs to be surfaced in the status text rather than only in the Engineering View.

The impact is significant: a parameterized label is a signal that the system understood the query before it answers. "Searching for billed business data" is an implicit confirmation of intent that requires no extra user action to verify.

---

#### Pattern 8: Stream-of-Thought Side Panel (ShapeOfAI classification)

**Used by:** Perplexity (tab), Lovable (sidebar), Accio (full-width process view).

**How it works:** The AI's process is rendered in a synchronized but visually separate surface from the answer. The surfaces can be: a side panel (Engineering View), a tab strip above the response, or an expandable section below the response. The process and answer are maintained as distinct information layers that never mix.

**Cortex recommendation: ADOPT (already implemented as Engineering View, confirmed as correct architecture).**

The split-panel Engineering View is exactly this pattern. The competitive research validates it as the standard approach for AI tools where the audience is technical and wants to see work. The existing design is correct.

The one gap the ShapeOfAI analysis surfaces: the three sub-forms of stream-of-thought (human-readable plans, execution logs, compact summaries) should be treated differently. The Engineering View currently shows execution logs (per-step timing, raw scores, SQL). It should also show a compact summary header at the top of the panel: "5 steps · 1.2s total · 94% match" — this gives the engineer the quick-read before they drill into step detail.

---

#### Pattern 9: Disambiguation as Inline Conversation Card

**Used by:** No exact competitor. Derived from standard conversational AI disambiguation patterns.

**How it works:** When the system identifies ambiguity, it presents the disambiguation options as a card within the conversation thread — not as a dialog overlay, not as a modal interruption. The card is the system's "turn" in the conversation. The user's response (clicking a card option) is their next "turn."

**Cortex recommendation: ADOPT (already specified, now reinforced).**

The Section 4.5 design already specifies this correctly: the disambiguation appears inline in the conversation thread, not as a modal overlay. This research validates that choice — modal overlays break the conversation metaphor and create an "error state" feeling even when disambiguation is not an error.

The addition recommended by this research: the disambiguation card should include a brief, honest framing: "Your question closely matches two datasets. I need one more piece of context before I can continue." This positions disambiguation as precision-seeking behavior (positive) rather than system uncertainty (negative).

---

#### Pattern 10: Fallback Follow-Up Templates

**Used by:** v0 (skeleton reveal for unmapped content), ChatGPT (regenerate button).

**How it works:** When the system cannot generate contextually appropriate follow-up suggestions (low confidence result, no-match state, partial result), it falls back to templated suggestions based on the explore that was used rather than showing nothing.

**Cortex recommendation: ADOPT.**

Gap 5 in Section 3 identified that follow-up generation may fail exactly when the user needs guidance most — after a low-confidence result. The template library approach: for each explore in the system, pre-generate three fallback follow-ups that are always valid for that explore's content domain. For Finance Cardmember 360, the fallbacks might be: "Break down by card product," "Compare to the same period last year," "Show top 5 segments by volume." These are always safe and contextually relevant to the explore, even if not specific to the last query.

---

#### Pattern 11: Confidence Calibration Display

**Used by:** Smashing Magazine Agentic UX (Confidence Signal pattern), agentic-design.ai CVP pattern.

**How it works:** Confidence is shown as a combination of: a numerical percentage, a color indicator (green/amber/red), and a label that describes what the confidence measures — not just "confidence" as an abstract quality score.

**Cortex recommendation: ADOPT with label precision (already partially specified).**

The Section 4.4 decision (always show numerical confidence as "X% match") is confirmed as correct by multiple competitive patterns. The label precision is the key addition: "94% match" is better than "94% confidence" because it describes the retrieval quality, not the answer accuracy. The existing spec has this right.

The one delta: the color transitions should be visible during the pipeline processing, but only in the Engineering View. In the Analyst View, the confidence percentage appears only on the completed result, never during processing. Showing a changing confidence score during processing (0%... 45%... 94%) would imply the answer is getting more confident in real time, which misrepresents what the pipeline is doing — the confidence score is a property of the explore match, not a real-time computation.

---

#### Patterns to Skip

**Skip: Duration Control for Users (ChatGPT "Light/Standard/Extended/Heavy").**

Finance analysts should not be choosing how hard the system works. The system should always work at full capacity. Adding a depth toggle would create two problems: (1) users would choose "Light" to go faster and then complain about accuracy, and (2) it suggests that the default is not the system's best effort. The value of Cortex is that it always does the right level of work. Do not offer a speed/accuracy dial.

**Skip: Streamed Prose Thinking (Claude's unstructured thinking block style).**

Cortex's pipeline is structured — five typed steps with defined inputs, outputs, and latency windows. Rendering process as unstructured prose would obscure rather than reveal the pipeline's deterministic nature. The step card pattern is always preferable for a structured pipeline. Prose thinking is the right pattern for an LLM reasoning freely; it is the wrong pattern for a typed orchestration system.

**Skip: Side-by-Side Multi-Model Comparison (Poe Group Chats).**

Cortex is a single-pipeline tool. There is no user value in comparing Cortex's output to another model's output within the same interface. This pattern solves a different problem (model selection) that does not exist in Cortex's context.

**Skip: The Heavy-Animation Source Tile Reveal (ChatGPT web search tiles).**

Horizontal scrolling source tiles that animate in from the right consume significant attention during a sub-3-second pipeline execution. The tile animation is designed to fill a multi-second waiting period with perceived progress. Cortex's answer should be available before the animation would even complete. If the animation exists and the answer arrives, the user is waiting for animation to finish, not waiting for content.

---

### 7.3 Part 3: Recommended Thinking UX for Cortex's 5-Step Pipeline

This section provides the specific, opinionated design for how Cortex should show its pipeline processing. It is written to the level of specificity that Ayush can implement from directly.

---

#### The Core Architecture: Three Surfaces, One Pipeline

Cortex's processing UX operates across three surfaces simultaneously. They are not three modes — they run in parallel and the user sees whichever is appropriate for their role.

**Surface A — Analyst View inline feedback (default, all users):** Three adaptive text phases that collapse to the collapse-to-badge pattern on completion. No step numbers. No technical identifiers. No timing. Just what the system is doing in plain language.

**Surface B — Intent Echo (default, all users):** A zero-latency extracted entity display that appears as soon as Intent Classification completes, visible between the user's message and the progress indicator. This surfaces the "I understood X, Y, Z" confirmation before the answer arrives.

**Surface C — Engineering View Panel (on toggle, technical users):** The full sequential step card display in the right panel. All 5 pipeline steps with real-time status, timing, expandable detail, and the overall confidence + latency footer.

These three surfaces share the same SSE event stream. Surface A reads step_start and step_complete events to transition between phases. Surface B reads the intent_classified event to render the entity extraction. Surface C reads all events to render the full step trace.

---

#### Surface A: Analyst View Inline Progress

**Phase 1 — "Understanding your question" (Intent Classification, 0-460ms target)**

Timing: Appears immediately when the query is submitted (before the first SSE event — optimistic UI). Transitions to Phase 2 when step_complete fires for intent_classification.

Visual treatment:
```
[ Cortex icon, 32px, pulsing ]  Understanding your question...
```

The Cortex icon pulses with a slow, low-amplitude opacity animation (0.7 → 1.0 → 0.7, 800ms loop). This is not a spinner — it is a "breathing" pulse that communicates active work without the urgency of a spinning indicator. The pulsing is the only animation in Phase 1. The text does not animate.

After Intent Classification completes, if the entity extraction includes filter values, the text adapts:
```
[ Cortex icon, pulsing ]  Understanding your question...  billed business · Small Business · Q4 2025
```

The extracted entities appear inline with the progress text, separated by centered dots. This is the Intent Echo (Surface B) integrated into the Phase 1 label. The entities fade in from opacity 0 over 150ms as they appear.

**Phase 2 — "Searching for [entity] data" (Semantic Search + Explore Scoring, 460-1275ms target)**

Timing: Transitions from Phase 1 when step_complete fires for intent_classification. The Phase 1 text fades out (opacity 0, 100ms) and Phase 2 text fades in (opacity 1, 150ms).

Visual treatment:
```
[ Cortex icon, pulsing ]  Searching for billed business data in Finance datasets...
```

The label is parameterized with the primary metric extracted from intent classification. If the metric entity is not extractable, fall back to "Searching for relevant data in Finance datasets."

When Explore Scoring completes and a winner is found, the label updates inline:
```
[ Cortex icon, pulsing ]  Found relevant data in Finance Cardmember 360
```

This update appears before Phase 3 starts — it is a mid-phase label update, not a phase transition. The explore name that appears here uses the business-language description from EXPLORE_DESCRIPTIONS, not the technical LookML identifier. If the explore is "finance_cardmember_360", the displayed name is "Finance Cardmember 360."

**Filter Resolution sub-display (within Phase 2, only when filters are present):**

When step_start fires for filter_resolution, an indented sub-line appears below the Phase 2 label:
```
[ Cortex icon, pulsing ]  Building query against Finance Cardmember 360...

  Translating filters:
    "small businesses"  →  OPEN
    "last quarter"      →  Q4 2025
```

The filter translation lines appear one at a time as each filter resolves (exact match fires → line appears; time parser fires → second line appears). The lines fade in from opacity 0 and translate up from y+4px simultaneously, over 200ms. The arrow (→) and the resolved value appear as a unit, not character by character.

Color treatment: the original filter term ("small businesses") is in --color-text-secondary. The resolved value (OPEN) is in --color-success (#008767) for an exact match, in --color-warning (#B37700) for a fuzzy/synonym/semantic match, in --color-error (#C40000) if resolution failed.

This sub-display is the live entity extraction display pattern. It is the most important trust signal in the entire processing experience and should never be suppressed in Analyst View. These two lines are worth more to analyst trust than any amount of pipeline step animation.

**Phase 3 — "Building the query" (SQL Generation, 1275-2000ms target)**

Timing: Transitions from Phase 2 when step_complete fires for explore_scoring. SQL Generation (via Looker MCP) is the final step.

Visual treatment:
```
[ Cortex icon, pulsing ]  Building the query against Finance Cardmember 360...
```

When step_complete fires for sql_generation, Phase 3 ends. The inline progress collapses. The completion transition is:

1. Phase 3 text and icon fade out (opacity 0, 150ms).
2. The answer begins streaming in (first tokens appear 50ms after fade completes).
3. After 300ms of streaming, the collapse-to-badge appears above the streaming answer:

```
[ ✓ ]  Finance Cardmember 360  ·  Q4 2025  ·  94% match  ·  1.2s   [ How I got this ▾ ]
```

The badge appears with an opacity fade (0 → 1, 200ms). It is not animated dramatically — it materializes. The checkmark is solid green (#008767). The metadata items are in --color-text-secondary at --text-xs (11px). The "How I got this" link is in --color-text-link with a chevron.

**Disambiguation interruption:**

If `disambiguate` fires at any point during processing, the current phase immediately stops. The pulsing icon stops. The progress text fades out. The disambiguation card fades in (see Section 4.5 for the card design). The user's interaction with the disambiguation card resumes the pipeline. This interruption should feel like the system asking a precise question, not failing.

**Error interruption:**

If an error event fires, the current phase stops and the error state renders in the progress area. The pulsing icon changes to a static red exclamation icon. The error message uses the user-safe copy from the error mapping layer (Gap 6 recommendation). A "Try again" link appears if recoverable is true.

---

#### Surface B: Intent Echo

The Intent Echo is a dedicated display zone between the user's message and the progress indicator. It appears as soon as intent_classified fires — which should be within the first 250ms of the pipeline.

**Format:**

```
You asked about:  billed business  ·  Small Business  ·  Q4 2025
```

The label "You asked about:" is in --color-text-secondary, --text-sm. The extracted entities are in --color-text-primary, --font-medium, --text-sm. They appear inline, separated by centered dots.

The entities are colored by type: metric entities in --color-info (#006FCF), dimension entities in --color-text-primary, time entities in --color-text-secondary. This is subtle but gives power users a quick read of how their query was classified.

**If entities are incomplete or low-confidence:**

If the intent classifier extracted fewer than 2 entities or the overall intent confidence is below 0.60, the echo shows:
```
Analyzing: "total billed business by small business segment last quarter"
```

In this state, the original query text is shown verbatim rather than the extracted entities. This signals that the system is working from the raw query, not from a high-confidence parse — without explicitly communicating uncertainty in a way that worries the user.

**After the response completes:**

The Intent Echo becomes persistent text above the response, in --color-text-tertiary at --text-xs, reduced to a single line. It remains as a lightweight record of what was asked:
```
Query interpreted as: billed business · Small Business · Q4 2025
```

---

#### Surface C: Engineering View Panel — Full Pipeline Trace

This section extends the existing Engineering View spec with the specific interaction behaviors derived from competitive research. The layout specification in Section 8 of the demo UI design is correct and unchanged. What follows is the interaction behavior layer.

**Step card expansion behavior:**

Auto-expand-then-auto-collapse. When a pipeline step becomes active (step_start fires), its detail section expands with a spring animation (350ms, cubic-bezier spring). When the step completes (step_complete fires), its detail section collapses to the compact completed card (200ms ease-out), and the next pending step begins to activate. Only one step is expanded at a time during active processing.

After the pipeline completes, all steps are in the collapsed completed state. Any step can be manually expanded at any time — this is the forensic review mode for engineers. Clicking any completed step card expands it. Clicking it again collapses it.

**Step 1: Intent Classification — "Understanding your question"**

Expanded detail shows:
- Extracted entities table: entity type | extracted value | confidence
- Example: metric = "total billed business" (0.94), dimension = "Small Business segment" (0.89), time = "Q4 2025" (0.99)
- Ambiguity flag: "CLEAR" (green) or "AMBIGUOUS" (amber) with the ambiguity reason
- Query category: "METRIC_QUERY" (or whichever category applies)
- Latency: e.g., "Intent classified in 287ms"

**Step 2: Semantic Search — "Searching for relevant data"**

Expanded detail shows:
- Retrieval method: "pgvector + Neo4j" (or whichever was used)
- Top 5 retrieved candidates: explore name | cosine similarity score | coverage score
- Example: finance_cardmember_360 (cos: 0.89, cov: 0.94), finance_credit_portfolio (cos: 0.84, cov: 0.79), ...
- Retrieval latency: "Semantic search: 412ms"

**Step 3: Explore Scoring — "Finding the best data source"**

This is the near-miss visualization step — the most critical Engineering View element. Expanded detail shows:
- A horizontal bar chart of the top 3 scored explores, with bars proportional to their final multiplicative score
- The winning explore is highlighted with the full score breakdown: semantic_similarity × graph_coverage × few_shot_boost = final_score
- The near-miss indicator: if the second-place explore is within 85% of the winner's score, an amber "NEAR MISS" badge appears
- If near-miss: "Disambiguation triggered — user will be asked to confirm"
- Latency: "Explore scoring: 189ms"

**Step 4: Filter Resolution — "Translating your filters"**

Expanded detail shows:
- For each filter:
  - Original term: "small businesses"
  - Resolution path: "Exact match in business_segment catalog → OPEN"
  - Or: "Fuzzy match (0.87 similarity) against business_segment catalog → OPEN"
  - Or: "LLM-resolved (no catalog match) → OPEN — verify this interpretation"
  - Color-coded by resolution quality: green for exact, blue for fuzzy/synonym, amber for LLM-resolved
- Time filter resolution: "Q4 2025 → 2025-10-01 to 2025-12-31 (partition range)"
- Partition injection: "Partition filter injected: transaction_date BETWEEN '2025-10-01' AND '2025-12-31'"
- Latency: "Filter resolution: 234ms"

The LLM-resolved filter is shown in amber with an explicit "verify this interpretation" note. This is the highest-risk filter state — the system could not find a catalog match and made a judgment call. Engineers reviewing a wrong-answer trace can immediately see if this was the source of the error.

**Step 5: SQL Generation — "Building the query"**

Expanded detail shows:
- The Looker MCP call parameters (explore name, fields, filters, time range)
- The generated SQL in a syntax-highlighted code block with a Copy button
- The plain-English SQL translation: "This query selects total billed business from the Finance Cardmember 360 model, filtered to Small Business segment and Q4 2025, with no limit."
- SQL metadata: estimated bytes scanned, partition coverage ("Partition filter applied — no full table scan"), field count
- Latency: "SQL generation via Looker MCP: 312ms"

**Engineering View footer (persistent below all steps):**

```
[ Overall Confidence: 94% ]   [ sem: 0.89 · graph: 0.97 · few-shot: 0.92 ]   [ Total: 1,234ms ]
```

The confidence percentage is the large primary element (--text-2xl, --font-bold) in the color for its threshold (green at 94%). The component scores are secondary, in --text-sm, --color-text-secondary. The total time is right-aligned.

---

#### The Transition from Thinking to Answer

The single most important micro-animation in the entire interface.

The transition should communicate: "the work is done, here is the result." Not "loading complete." The visual language should shift from "active process" to "here is the answer."

The recommended transition sequence (total duration: 450ms):

1. Phase 3 progress text fades out simultaneously with the Cortex icon stopping its pulse (150ms, ease-out).
2. A brief pause (50ms) — no content on screen except the user's message and the filter echo above.
3. The collapse-to-badge materializes above the response area (200ms, fade-in from opacity 0).
4. The first word of the answer appears and begins streaming immediately (50ms after badge appears).
5. The answer streams at roughly 40-60 tokens per second — fast enough to feel immediate, slow enough to read as it arrives.

The answer text does not "type in" character by character (that's slow and feels like typewriter theater). It streams in full tokens at a comfortable reading pace. The streaming pace should allow a reader to track the sentence structure as it arrives: subject, verb, number, context.

**The answer sentence leads with the number.** Not "In Q4 2025, total billed business for Small Business..." but "Total billed business for Small Business in Q4 2025 was $4.2B, up 8.3% from Q3." The key metric is the second-to-last or third-to-last word before the full stop, not buried mid-sentence. This is not just style — it is the single highest-impact readability change that can be made to NL2SQL responses.

---

#### Timing Posture: Analyst View vs Engineering View During Processing

| Moment | Analyst View | Engineering View |
|--------|-------------|-----------------|
| Query submitted | Phase 1 text + pulsing icon | Phase 1 text + Step 1 activates in panel |
| Intent classified (287ms) | Intent echo appears | Step 1 completes (green), Step 2 activates |
| Entities shown | Filter terms appear in echo if present | Step 1 expands to show entity table |
| Semantic search complete (699ms) | Phase 2 text updates to "Searching..." | Step 2 completes, Step 3 activates |
| Explore scored (888ms) | Phase 2 text updates to "Found in Finance Cardmember 360" | Step 3 completes, near-miss bar chart visible |
| Filter resolved (1,122ms) | Filter translation lines appear (OPEN, Q4 2025) | Step 4 completes, resolution path visible |
| SQL generated (1,434ms) | Phase 3 text appears | Step 5 completes, SQL visible |
| Response streams (1,434ms+) | Collapse-to-badge + answer streaming | Panel footer shows final confidence + total time |

---

### 7.4 Part 4: Conversational Element Recommendations

#### 4.1 Disambiguation — Full Interaction Design Addendum

The Section 4.5 disambiguation design is confirmed correct by this research. The following addenda are derived from competitive analysis.

**The framing sentence matters.** Current spec does not specify the lead-in text. Recommended:

```
Your question closely matches two data sources. Which one applies?
```

Do not say "I'm not sure" or "I need clarification" — these frame disambiguation as system uncertainty. "Closely matches two data sources" frames it as precision — the system found two good answers and wants to give you the right one. This distinction is significant for Finance analysts who have low tolerance for systems that express doubt.

**The confidence scores on the disambiguation card are justified context, not anxiety-inducing.** Showing 89% vs 86% in the near-miss disambiguation is correct. These numbers are almost equal — that is exactly why the system is asking. The visual parity of the scores (a 3-point difference, both in green territory) communicates "either of these would be a reasonable answer" rather than "one is clearly right and I missed it."

**What happens after disambiguation if the user chooses wrong:** The follow-up pipeline should handle the correction. If a user selects option A, gets a result, and then types "that's not right, try the other one," the intent classifier should recognize this as a correction and route to option B. The pipeline does not need special handling — the conversation history contains the disambiguation context. What needs to be designed is the response: if Cortex detects a mid-conversation explore switch, it should acknowledge it: "Switching to Small Business Credit Portfolio now. Here's what that shows: [result]."

**Disambiguation in ChatGPT Enterprise:** The format specified in Section 4.7 is correct. The additional guidance: in ChatGPT Enterprise, the "Reply with A or B" instruction should always appear on its own line, bold, after the two options. Users have been trained by SMS voting and WhatsApp polls to expect this format. It is familiar.

---

#### 4.2 Follow-Up Suggestions — Chip Design and Generation Rules

**Chip placement:** Below the source citation line, above the disclosure toggle. This order matters: the user reads the answer, reads the table, sees the filters applied, sees the source, then sees where they can go next. The follow-up chips appear at the natural end of the response, not interrupting the data reading.

**Chip count:** Three chips maximum. Two is acceptable. One is a failure state (show the one plus a generic "Explore further" chip rather than showing only one). Zero chips should never be shown — use the fallback template library (Pattern 10).

**Chip generation rules (constraint the follow-up prompt with these):**

A valid follow-up chip must:
1. Be answerable by the same explore OR a clearly adjacent explore in the same business unit
2. Use a different dimension, time range, or metric than the current result — it cannot be a restatement
3. Be specific — "Break down by card product" is valid, "Show more data" is not
4. Be completable by clicking — no chips that require the user to fill in a value

**Chip generation anti-patterns to explicitly exclude from the prompt:**
- Restating the current query ("Show total billed business for Small Business")
- Generic exploration prompts ("What other data is available?")
- Out-of-scope queries ("Show marketing spend by segment" if Cortex does not cover marketing)
- Vague refinements ("Show that differently")

**Chip interaction states:**
- Default: white background, gray border, primary text color
- Hover: Amex blue border (#006FCF), blue text (#006FCF), light blue background (#E6F0FA)
- Active (click): scale transform to 0.96, background #006FCF, white text — this shows the chip was clicked before the new query submits
- After click: chip that was clicked disappears, remaining chips remain visible as the new query processes

**The fallback library (per Pattern 10):**

For Finance Cardmember 360: "Break down by card product" / "Compare to the same period last year" / "Show top 5 segments by volume"
For Finance Credit Portfolio: "Show delinquency rate trend" / "Break down by relationship type" / "Compare current quarter to prior quarter"
For Finance Acquisition: "Compare to prior quarter acquisition" / "Show by channel" / "Break down by generation"

These are hardcoded strings, not generated. They should live in the EXPLORE_DESCRIPTIONS config alongside the business description — a `fallback_follow_ups[]` array per explore.

---

#### 4.3 Error States — Complete Taxonomy

The existing UX spec error taxonomy is correct and complete. This section adds the specific processing-UX behavior for each error state — what happens to the progress indicators when each error type fires.

**Error Type 1: Intent Not Classifiable (no_match)**

Trigger: Intent confidence < 0.45, or no entities extractable.

Processing behavior: Phase 1 ("Understanding your question") continues for up to 460ms, then the intent echo shows the original query verbatim. If classification fails entirely, the pipeline stops at Phase 1 and the error renders.

Response format:
```
I wasn't able to understand that question as a Finance data query.

Try rephrasing with a specific metric or topic:
  · "What was billed business last quarter?"
  · "How many active cardmembers in Q4?"

Or ask "What can you help with?" for the full list.
```

The error response includes three example queries seeded from the capabilities endpoint. The user is never left with just an apology.

**Error Type 2: No Matching Explore (coverage gap)**

Trigger: All scored explores below 0.55 confidence threshold after retrieval.

Processing behavior: The Phase 2 label transitions to "Looking for relevant data..." then the error renders when no explore clears the threshold. The collapse-to-badge does not appear — the badge only appears on successful results.

Response format:
```
That metric isn't covered in the current Finance data sources.

Available topics include billed business, active accounts, credit metrics,
and acquisition data.

Is one of these close to what you need?
  · "Show me billed business by segment"
  · "What are the active account counts?"
```

This uses the metric taxonomy vocabulary. The "available topics" sentence is parameterized from the capabilities endpoint — it always reflects current coverage, not a hardcoded list.

**Error Type 3: Near-Miss Disambiguation Timeout**

Trigger: User does not respond to a disambiguation card within a session (not a timer — just if the session ends before they choose).

Response: Not applicable to the React app (users navigate away without timeouts). In ChatGPT Enterprise, if the user asks a new question without responding to the A/B choice: treat the new question as starting fresh. Do not persist the unresolved disambiguation. The pipeline re-runs on the new question.

**Error Type 4: Filter Resolution Failure**

Trigger: A filter value cannot be resolved through all 5 passes of the resolution cascade.

Processing behavior: The filter translation line in the analyst view shows the failed filter in red: "Q5 2025" → unresolved (in --color-error). The pipeline stops.

Response format:
```
I couldn't match "Q5 2025" to a valid time period in Finance data.

Finance data is organized by quarters Q1–Q4. Did you mean Q4 2025?
  · [Yes, use Q4 2025]   · [No, use a different period]
```

The response includes inline action chips for the most likely correct interpretation (identified by the LLM resolver) and a free-choice option. This is the only error state that offers a specific suggested correction rather than a generic rephrasing prompt.

**Error Type 5: SQL Generation Failure (Looker MCP error)**

Trigger: Looker MCP returns an error after receiving the explore + filters + fields.

Processing behavior: Steps 1-4 are already complete and their results are visible (or collapsed-to-badge). Step 5 fails. The Engineering View shows Step 5 card in red. The Analyst View shows a specific error at the Phase 3 position.

Response format:
```
The data source returned an error when I tried to build that query.

This sometimes happens when a specific field combination isn't supported.
Try simplifying:
  · Remove one of the filters
  · Ask for fewer dimensions at once
```

Do not expose the Looker MCP error text. Map it to user-safe copy. The technical details are in the Engineering View Step 5 card for engineers.

**Error Type 6: Pipeline Timeout (>8 seconds total)**

Trigger: The pipeline has not completed within the SLA budget.

Processing behavior: The progress indicator shifts from pulsing to a static "working" state at the 5-second mark. At 8 seconds, the pipeline is cancelled and the error renders.

Response format:
```
That query is taking longer than expected to process.

This can happen with very complex questions. Try:
  · Narrowing to a specific quarter instead of a full year
  · Focusing on one segment rather than all segments
  · Breaking it into two simpler questions
```

The suggestions are generic because the timeout can be caused by retrieval, scoring, or MCP latency — there is no single cause to address. The suggestions are validated against the known timeout triggers from the pipeline-first-principles-breakdown.

---

#### 4.4 Multi-Turn Context — Visual Treatment

**The context persistence indicator:**

When a follow-up query is submitted and the pipeline inherits context from the previous turn, a subtle context indicator should appear in the Phase 2 label:

```
Searching for card product breakdown using your previous context...
```

"Using your previous context" is the signal. It confirms that the system carried forward the explore, segment, and time range without requiring re-specification. This is the turn where the value of conversation becomes visible — the user asked "Break down by card product" without specifying Small Business or Q4 2025, and the system knew to apply them.

**Context shown in the Intent Echo on follow-up turns:**

The Intent Echo on follow-up turns should show inherited context differently from freshly-specified context:

```
You asked about:  card product breakdown  ·  [Small Business]  ·  [Q4 2025]
```

Bracketed, muted-color entities are inherited from context. Non-bracketed entities were extracted from the current query. This visual distinction tells the user at a glance which parts of the query they specified and which parts carried over. Engineers who test Cortex regularly will find this invaluable for debugging context-carryover failures.

**Context limit warning:**

The existing spec (Section 4.2 Step 8) calls for a warning at turn 18/20. The specific copy:

```
[ i ]  Approaching conversation limit (18 of 20 turns used). Start a new conversation
       to continue exploring — previous results stay in your history.
```

The message is rendered as an info banner above the chat input area, not as a system message in the thread. Banner background: --color-info-light (#E6F0FA), border-left 3px solid #006FCF, icon and text in --color-text-primary. This treatment matches standard enterprise notification patterns.

---

#### 4.5 The "Show Me the Query" Conversational Shortcut

This is a new recommendation not in the existing spec, derived from the competitive observation that Snowflake Cortex Analyst and Power BI Copilot both lack a natural-language way to expose the underlying query.

The ChatGPT Enterprise response format spec (Section 4.7) already includes: `*To see how I got this answer, ask: "Show me the query for the last result"*`. This footnote is correct but undersells the value.

The full conversational shortcut library that Cortex should handle as recognized intents:

| User says | Cortex does |
|-----------|-------------|
| "Show me the query" | Displays the SQL from the last result, formatted |
| "What data source was that?" | Identifies the explore and model used |
| "Why did you filter for OPEN?" | Explains the filter resolution step for that filter |
| "What does OPEN mean?" | Looks up the filter value in the business vocabulary catalog |
| "Is this data fresh?" | Shows the data freshness timestamp from the explore metadata |
| "Show the same thing for last year" | Adjusts the time range, preserves all other context |
| "That filter is wrong" | Initiates the filter correction flow, feeds feedback endpoint |

These should be handled by the intent classifier as a special `METADATA_QUERY` category that routes to the trace endpoint rather than the query endpoint. The trace for the conversation is always available — these shortcuts just make it accessible conversationally rather than requiring the user to click into Level 2.

---

### 7.5 Patent Flag

```
POTENTIAL PATENT
Idea: Real-time filter resolution visualization during AI pipeline execution
Novel aspect: Displaying natural language → structured value translation
(e.g., "small businesses" → OPEN) as a live streaming trust signal during
query processing, with color-coded resolution quality indicators
(exact/fuzzy/LLM-resolved) that persist into the final response as a
verifiable audit trail. No competitor (ThoughtSpot, Looker Conversational
Analytics, Snowflake Cortex Analyst, Power BI Copilot) surfaces filter
resolution transparency at this level of specificity to the end user.
Prior art concern: Medium — general "chain of thought" visualization
patents exist but are not specific to filter value resolution in NL2SQL.
Next step: Discuss with Lakshmi. Draft disclosure focusing on the
combination of: (1) live streaming display of resolution cascade step,
(2) persistence of resolution path in final response, (3) inline correction
affordance tied to feedback endpoint for learning loop update.
```

---

*Section 7 appended March 16, 2026. Research base: Claude, Gemini, ChatGPT/o-series, Perplexity, Cursor/Windsurf, v0 audit; ShapeOfAI pattern library; Smashing Magazine agentic UX (2026); digestibleux.com reasoning display analysis; IntuitionLabs conversational AI comparison (2025); AI UX Design Guide progressive disclosure pattern; agentic-design.ai confidence visualization pattern.*
