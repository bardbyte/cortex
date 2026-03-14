# Cortex: Agentic Orchestration Layer Design

**Author:** Saheb | **Date:** March 11, 2026 | **Status:** Proposed
**Reviewers:** Sulabh, Ashok (Architecture Board), Abhishek
**ADRs:** [001-ADK](../../adr/001-adk-over-langgraph.md), [004-Retrieval](../../adr/004-semantic-layer-representation.md), [005-Intent](../../adr/005-intent-entity-classification.md), [007-Filters](../../adr/007-filter-value-resolution.md), [008-Learning Loop](../../adr/008-filter-value-learning-loop.md)

---

## 1. Overview

### What This Document Is

The engineering specification for Cortex's orchestration layer — how a user query enters the system, flows through intent classification, hybrid retrieval, Looker MCP SQL generation, and exits as a structured response with full per-step transparency.

### Problem

The existing PoC (`access_llm/chat.py`) works but is blind. The LLM must discover the right model, explore, dimensions, and measures from scratch on every query by chaining 4-6 Looker MCP tool calls (`get-models` → `get-explores` → `get-dimensions` → `get-measures` → `query-sql`). This is slow (~5s), expensive (5 SafeChain calls), and unreliable (~50% field accuracy on our schema).

### Solution

A three-phase orchestration layer that wraps the existing SafeChain `AgentOrchestrator`:

```
Phase 1: PRE-PROCESSING (deterministic, no LLM except intent classification)
  ├── Intent Classification + Entity Extraction (1 Gemini call, ~200ms)
  ├── Hybrid Retrieval (pgvector + AGE + FAISS, ~260ms)
  ├── Filter Value Resolution (deterministic 4-pass, ~15ms)
  └── Output: RetrievalResult + augmented system prompt

Phase 2: REACT EXECUTION (LLM + tools, 1-2 iterations)
  ├── MCPToolAgent with augmented prompt (LLM goes straight to query-sql)
  ├── Structural validation via partition filter injection
  └── Output: SQL results + raw data

Phase 3: POST-PROCESSING (deterministic)
  ├── Response formatting (progressive disclosure)
  ├── PipelineTrace assembly (per-step timing, scores, decisions)
  ├── Follow-up suggestion generation
  └── Output: Structured response + trace for frontend
```

### Key Design Principle

**Composition over inheritance.** `CortexOrchestrator` wraps the existing `AgentOrchestrator` — it does NOT subclass it. This keeps the PoC code untouched, makes the integration layer independently testable, and avoids coupling to SafeChain's internal API.

---

## 2. Architecture

### System Diagram

```
                              ┌─────────────────────┐
                              │    ChatGPT / UI      │
                              │    (Frontend)        │
                              └─────────┬───────────┘
                                        │ HTTP/SSE
                                        ▼
                              ┌─────────────────────┐
                              │    FastAPI Server     │
                              │   /query  /health    │
                              │   /trace  /feedback  │
                              └─────────┬───────────┘
                                        │
                                        ▼
┌────────────────────────────────────────────────────────────────────┐
│                     CortexOrchestrator                              │
│                                                                     │
│  ┌───────────── PHASE 1: PRE-PROCESSING ──────────────────────┐   │
│  │                                                               │   │
│  │   ┌─────────────┐    ┌───────────────┐    ┌──────────────┐  │   │
│  │   │   Intent     │    │   Retrieval    │    │   Filter     │  │   │
│  │   │   Classifier │───▶│   Orchestrator │───▶│   Resolver   │  │   │
│  │   │   (1 LLM)   │    │   (no LLM)    │    │   (no LLM)   │  │   │
│  │   └─────────────┘    └───────────────┘    └──────────────┘  │   │
│  │         │                     │                    │           │   │
│  │    intent +              model +              resolved        │   │
│  │    entities             explore +             filters         │   │
│  │                       dimensions +                            │   │
│  │                        measures                               │   │
│  └───────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│                              ▼ RetrievalResult                       │
│  ┌───────────── PHASE 2: REACT EXECUTION ─────────────────────┐   │
│  │                                                               │   │
│  │   ┌──────────────────────────────────────────────────────┐   │   │
│  │   │         AgentOrchestrator  (unchanged PoC)            │   │   │
│  │   │                                                        │   │   │
│  │   │   Augmented Prompt ──▶ MCPToolAgent ──▶ Looker MCP    │   │   │
│  │   │                        (SafeChain)     (query-sql)    │   │   │
│  │   │                                                        │   │   │
│  │   │   1-2 iterations (down from 5-6)                      │   │   │
│  │   └──────────────────────────────────────────────────────┘   │   │
│  └───────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│                              ▼ query results                         │
│  ┌───────────── PHASE 3: POST-PROCESSING ─────────────────────┐   │
│  │                                                               │   │
│  │   ┌─────────────┐    ┌───────────────┐    ┌──────────────┐  │   │
│  │   │   Response   │    │   Pipeline     │    │   Follow-up  │  │   │
│  │   │   Formatter  │    │   Trace        │    │   Generator  │  │   │
│  │   └─────────────┘    └───────────────┘    └──────────────┘  │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                ┌──────────────┐ ┌─────────────┐ ┌───────────┐
                │  PostgreSQL   │ │   FAISS     │ │  SafeChain │
                │  pgvector +   │ │   Index     │ │  Gateway   │
                │  Apache AGE   │ │  (golden)   │ │  (CIBIS)   │
                └──────────────┘ └─────────────┘ └───────────┘
```

### Data Flow (Concrete Types)

```
User Query: "What was total billed business for small businesses last quarter?"
    │
    ▼
Phase 1a — Intent Classification (1 LLM call, ~200ms)
    │  Input:  str
    │  Output: ClassificationResult {
    │    intent: "data_query",
    │    confidence: 0.97,
    │    entities: {
    │      metrics: ["total billed business"],
    │      dimensions: [],
    │      filters: {"bus_seg": "small businesses"},
    │      time_range: "last quarter"
    │    }
    │  }
    │
    ▼
Phase 1b — Hybrid Retrieval (~260ms, zero LLM calls)
    │  Input:  entities dict
    │  Output: RetrievalResult {
    │    action: "proceed",
    │    model: "cortex_finance",
    │    explore: "card_member_spend",
    │    dimensions: [],
    │    measures: ["total_billed_business"],
    │    filters: {},  ← filter VALUES resolved in next step
    │    confidence: 0.91,
    │    coverage: 1.0,
    │    fewshot_matches: ["GQ-fin-003"]
    │  }
    │
    ▼
Phase 1c — Filter Value Resolution (~15ms, zero LLM calls)
    │  Input:  entities.filters + RetrievalResult.explore
    │  Output: resolved_filters = {"bus_seg": "OPEN", "partition_date": "last 1 quarters"}
    │
    │  "small businesses" → FILTER_VALUE_MAP["bus_seg"]["small business"] → "OPEN"
    │  "last quarter" → Looker time syntax → "last 1 quarters"
    │  partition_date → mandatory filter injected from AGE graph
    │
    ▼
Phase 1d — Prompt Augmentation
    │  Input:  RetrievalResult + resolved_filters
    │  Output: augmented_system_prompt (str)
    │
    │  The LLM now sees:
    │    "Use query-sql with model=cortex_finance, explore=card_member_spend,
    │     measures=[total_billed_business], filters={bus_seg: OPEN, partition_date: last 1 quarters}.
    │     Do NOT explore. These fields are structurally validated."
    │
    ▼
Phase 2 — ReAct Execution (1 LLM call + 1 tool call, ~800ms)
    │  Iteration 1: LLM → query-sql (correct on first try)
    │  Iteration 2: LLM → formats answer (no more tool calls)
    │
    │  Output: {"content": "Total billed business for Small Business (OPEN)
    │           last quarter was $4.2B.", "tool_results": [...]}
    │
    ▼
Phase 3 — Post-Processing (~50ms)
    │  Output: CortexResponse {
    │    answer: "Total billed business...",
    │    data: {rows: [...], columns: [...], row_count: 1},
    │    trace: PipelineTrace { ... },  ← per-step transparency
    │    follow_ups: ["Break down by card product", "Compare to previous quarter"],
    │    sql: "SELECT ... FROM ... WHERE bus_seg = 'OPEN' ..."
    │  }
```

---

## 3. Core Components

### 3.1 PipelineTrace — First-Class Observability

Every query produces a `PipelineTrace` that captures per-step timing, inputs, outputs, scores, and decisions. This is NOT logging — it is a structured data object returned to the frontend for transparency.

```python
@dataclass
class StepTrace:
    """One step in the pipeline."""
    step_name: str                    # "intent_classification"
    started_at: float                 # time.monotonic()
    ended_at: float
    duration_ms: float                # computed
    input_summary: dict               # truncated inputs for display
    output_summary: dict              # truncated outputs for display
    decision: str                     # "proceed" | "disambiguate" | "clarify"
    confidence: float | None = None   # step-specific confidence
    error: str | None = None

@dataclass
class PipelineTrace:
    """Full pipeline trace for one query."""
    trace_id: str                     # UUID
    query: str                        # original user query
    steps: list[StepTrace]            # ordered list
    total_duration_ms: float
    llm_calls: int                    # total LLM round-trips
    mcp_calls: int                    # total MCP tool calls
    retrieval_confidence: float       # overall retrieval confidence
    action_taken: str                 # "proceed" | "disambiguate" | "clarify" | "fallback"

    def to_dict(self) -> dict:
        """Serialize for API response / SSE streaming."""
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "total_duration_ms": self.total_duration_ms,
            "llm_calls": self.llm_calls,
            "mcp_calls": self.mcp_calls,
            "confidence": self.retrieval_confidence,
            "action": self.action_taken,
            "steps": [
                {
                    "name": s.step_name,
                    "duration_ms": s.duration_ms,
                    "decision": s.decision,
                    "confidence": s.confidence,
                    "input": s.input_summary,
                    "output": s.output_summary,
                    "error": s.error,
                }
                for s in self.steps
            ],
        }
```

**Why this matters:** The frontend (ChatGPT Enterprise or custom UI) can display a live pipeline visualization showing which step is executing, what confidence the retrieval produced, and why the system chose a particular explore. This is the "show your work" that builds user trust.

### 3.2 CortexOrchestrator — The Integration Layer

```python
class CortexOrchestrator:
    """Wraps AgentOrchestrator with Cortex retrieval pipeline.

    Composition over inheritance:
      - Does NOT subclass AgentOrchestrator
      - Wraps it: prepares context (Phase 1), delegates to it (Phase 2),
        then post-processes (Phase 3)
      - If Phase 1 fails, falls through to raw AgentOrchestrator (PoC behavior)

    Why not subclass:
      - AgentOrchestrator's run() method couples LangChain message types,
        SafeChain auth, and tool execution. Subclassing means coupling to
        all of that internal API surface.
      - Composition means CortexOrchestrator owns its own run() contract
        and delegates cleanly.
    """

    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        retrieval: RetrievalOrchestrator,
        embed_fn: Callable[[str], list[float]],
        pg_conn: Any,
        taxonomy_terms: list[str] | None = None,
    ):
        self.orchestrator = orchestrator     # the PoC, unchanged
        self.retrieval = retrieval           # hybrid retrieval
        self.embed_fn = embed_fn             # SafeChain embedding endpoint
        self.pg_conn = pg_conn               # shared pgvector + AGE connection
        self.taxonomy_terms = taxonomy_terms or []
        self.last_retrieval_result: RetrievalResult | None = None
        self._trace: PipelineTrace | None = None

    async def run(self, query: str, conversation_history: list[dict] | None = None) -> CortexResponse:
        """Main entry point. Three-phase pipeline."""
        trace_builder = TraceBuilder(query)
        history = conversation_history or []

        try:
            # ── PHASE 1: PRE-PROCESSING ──────────────────────────
            classification = await self._classify(query, history, trace_builder)

            if classification.intent == "out_of_scope":
                return self._out_of_scope_response(query, trace_builder)

            if classification.intent in ("schema_browse", "saved_content"):
                return await self._passthrough(query, history, trace_builder)

            if classification.intent == "follow_up" and self.last_retrieval_result:
                retrieval_result = self._handle_follow_up(classification, trace_builder)
            else:
                retrieval_result = self._retrieve(classification.entities, trace_builder)

            resolved_filters = self._resolve_filters(
                classification.entities, retrieval_result, trace_builder
            )
            retrieval_result.filters = resolved_filters

            # ── PHASE 2: REACT EXECUTION ─────────────────────────
            augmented_prompt = self._build_augmented_prompt(retrieval_result)
            messages = [
                {"role": "system", "content": augmented_prompt},
                *history,
                {"role": "user", "content": query},
            ]

            react_result = await self._execute_react(messages, trace_builder)

            # ── PHASE 3: POST-PROCESSING ─────────────────────────
            self.last_retrieval_result = retrieval_result
            response = self._build_response(
                react_result, retrieval_result, trace_builder
            )
            return response

        except Exception as e:
            # Fallback: raw AgentOrchestrator (PoC behavior)
            trace_builder.add_step("fallback", {"reason": str(e)}, {}, "fallback")
            messages = [*history, {"role": "user", "content": query}]
            raw = await self.orchestrator.run(messages)
            return CortexResponse(
                answer=raw.get("content", ""),
                trace=trace_builder.build(),
            )
```

### 3.3 SafeChain Integration

All LLM calls go through SafeChain (`CIBIS` auth). The integration pattern from `chat.py` is preserved exactly:

```python
# ── SafeChain config loading (proven in PoC) ──────────────────
from ee_config.config import Config
from safechain.tools.mcp import MCPToolLoader, MCPToolAgent

config = Config.from_env()                        # loads CIBIS creds from .env
tools = await MCPToolLoader.load_tools(config)    # connects to MCP servers
model_id = config.model_id                        # e.g. "gemini-2.0-flash"

# ── For intent classification (separate from ReAct) ──────────
# Use MCPToolAgent directly (no tools needed for classification)
classifier_agent = MCPToolAgent(model_id, tools=[])

# ── For ReAct loop (unchanged from PoC) ──────────────────────
orchestrator = AgentOrchestrator(
    model_id=model_id,
    tools=tools,
    system_prompt=AUGMENTED_PROMPT,  # ← only change: prompt is augmented
    max_iterations=5,                # reduced from 15 (retrieval handles discovery)
    thinking_callback=callback,
)
```

**Embedding endpoint:** The SafeChain gateway must support `text-embedding-005` for pgvector. If the embedding endpoint is not available through SafeChain, we fall back to Vertex AI's embedding API directly (requires separate auth — verify with Ravi J).

### 3.4 API Layer — FastAPI

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="Cortex API", version="0.1.0")

@app.post("/query")
async def query(request: QueryRequest) -> CortexResponse:
    """Synchronous query endpoint. Returns full response + trace."""
    response = await cortex.run(
        query=request.query,
        conversation_history=request.history,
    )
    return response

@app.post("/query/stream")
async def query_stream(request: QueryRequest) -> StreamingResponse:
    """SSE streaming endpoint. Streams trace events as they happen."""
    async def event_generator():
        async for event in cortex.run_streaming(
            query=request.query,
            conversation_history=request.history,
        ):
            yield f"data: {event.to_json()}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/health")
async def health():
    """Health check — verifies SafeChain, PostgreSQL, and FAISS."""
    return {
        "status": "ok",
        "safechain": await check_safechain(),
        "postgresql": await check_pg(),
        "faiss": check_faiss(),
    }

@app.post("/feedback")
async def feedback(request: FeedbackRequest):
    """User feedback on query results. Feeds learning loop (ADR-008)."""
    # If user corrects a filter value, log as synonym suggestion
    if request.filter_correction:
        await log_synonym_suggestion(
            user_term=request.filter_correction.user_term,
            correct_value=request.filter_correction.correct_value,
            dimension=request.filter_correction.dimension,
        )
    return {"status": "logged"}
```

**Why FastAPI over Vertex AI Agent Engine:**
- Agent Engine deploys ADK agents as managed services — but Cortex is NOT a pure ADK agent. It's a wrapper around SafeChain's `MCPToolAgent`.
- Agent Engine does not support SafeChain's CIBIS auth flow.
- FastAPI gives us full control over SSE streaming, health checks, and the feedback endpoint.
- Deploy on GKE (where the Looker MCP Toolbox sidecar already runs).

---

## 4. Data Models

### Request / Response Contract

```python
@dataclass
class QueryRequest:
    query: str
    history: list[dict] = field(default_factory=list)  # [{role, content}]
    session_id: str | None = None
    user_id: str | None = None

@dataclass
class CortexResponse:
    answer: str                                         # formatted text response
    data: dict | None = None                            # {rows, columns, row_count}
    sql: str | None = None                              # generated SQL for transparency
    trace: PipelineTrace | None = None                  # full pipeline trace
    follow_ups: list[str] = field(default_factory=list) # suggested next questions
    retrieval_result: dict | None = None                # raw RetrievalResult for debugging

@dataclass
class FeedbackRequest:
    query: str
    session_id: str
    rating: int | None = None                           # 1-5
    filter_correction: FilterCorrection | None = None   # for learning loop
    comment: str | None = None

@dataclass
class FilterCorrection:
    user_term: str          # what the user typed: "small businesses"
    correct_value: str      # what the user corrected to: "OPEN"
    dimension: str          # "bus_seg"
```

### ClassificationResult

```python
@dataclass
class ClassificationResult:
    intent: str               # data_query | schema_browse | saved_content | follow_up | out_of_scope
    confidence: float         # 0.0 - 1.0
    entities: ExtractedEntities
    reasoning: str            # one-sentence explanation

@dataclass
class ExtractedEntities:
    metrics: list[str]
    dimensions: list[str]
    filters: dict[str, str]   # {dimension_name: user_value}
    time_range: str | None
    sort: str | None
    limit: int | None
```

---

## 5. File Map

### Files to Implement

```
cortex/src/
├── pipeline/
│   ├── orchestrator.py      # CortexOrchestrator (composition wrapper)       ~250 lines
│   ├── trace.py             # PipelineTrace, StepTrace, TraceBuilder         ~150 lines
│   ├── prompts.py           # SYSTEM_PROMPT, CLASSIFY_PROMPT, AUGMENT tmpl   ~100 lines
│   ├── errors.py            # CortexError, RetryableError, FallbackError      ~50 lines
│   ├── state.py             # CortexState (EXISTS — extend with trace)
│   └── agent.py             # ADK agent definition (EXISTS — becomes thin)
│
├── connectors/
│   ├── safechain_client.py  # get_config, create_classifier, create_agent    ~120 lines
│   └── mcp_tools.py         # get_looker_toolset, tool_filter (EXISTS)
│
├── retrieval/
│   ├── orchestrator.py      # RetrievalOrchestrator (EXISTS — mostly done)
│   ├── vector.py            # pgvector search (STUB — implement)             ~80 lines
│   ├── graph_search.py      # AGE Cypher validation (STUB — implement)       ~120 lines
│   ├── fewshot.py           # FAISS golden query matching (STUB — implement)  ~80 lines
│   ├── fusion.py            # RRF merge (STUB — implement)                    ~60 lines
│   ├── filter_resolver.py   # 4-pass deterministic resolution (NEW)          ~150 lines
│   └── models.py            # FieldCandidate, RetrievalResult (EXISTS)
│
├── api/
│   ├── server.py            # FastAPI app, /query, /health, /feedback         ~150 lines
│   ├── models.py            # QueryRequest, CortexResponse, etc.              ~80 lines
│   └── middleware.py        # Auth, logging, error handling                    ~60 lines
│
└── evaluation/
    └── golden.py            # Golden dataset runner (EXISTS)
```

### Estimated Effort

| Component | Lines | Owner | Dependency | Priority |
|-----------|-------|-------|-----------|----------|
| `pipeline/orchestrator.py` | ~250 | Saheb | safechain_client + retrieval | P0 — demo |
| `pipeline/trace.py` | ~150 | Saheb | None | P0 — demo |
| `pipeline/prompts.py` | ~100 | Saheb + Likhita | Intent taxonomy finalized | P0 — demo |
| `connectors/safechain_client.py` | ~120 | Saheb | SafeChain access + CIBIS creds | P0 — blocker |
| `retrieval/vector.py` | ~80 | Rajesh | pgvector schema + embeddings loaded | P0 — demo |
| `retrieval/graph_search.py` | ~120 | Rajesh | AGE schema + LookML graph loaded | P0 — demo |
| `retrieval/fewshot.py` | ~80 | Animesh | FAISS index + golden queries | P1 — post-demo |
| `retrieval/fusion.py` | ~60 | Saheb | vector + graph + fewshot | P1 — post-demo |
| `retrieval/filter_resolver.py` | ~150 | Saheb | Value catalog populated | P1 — post-demo |
| `api/server.py` | ~150 | Saheb | orchestrator working | P1 — post-demo |
| `api/models.py` | ~80 | Saheb | None | P1 — post-demo |
| `pipeline/errors.py` | ~50 | Saheb | None | P2 |
| `api/middleware.py` | ~60 | Saheb | FastAPI server | P2 |

**Total:** ~1,450 lines of production code.

### Demo-Critical Path (P0)

For a working demo, the minimum viable slice is:

```
safechain_client.py   → can call Gemini via SafeChain ✓
prompts.py            → intent classification + augmented prompt ✓
orchestrator.py       → Phase 1 + Phase 2 + Phase 3 ✓
trace.py              → per-step trace object ✓
vector.py             → pgvector cosine search ✓
graph_search.py       → AGE structural validation ✓
```

Six files. Fewshot, fusion, filter resolver, and API layer are post-demo enhancements.

---

## 6. Latency Budget

Target: **<4 seconds** from user input to data response (P95).

```
┌───────────────────────────────────────────────────────────────────────┐
│                        LATENCY BUDGET                                 │
├────────────────────────────┬───────────┬──────────────────────────────┤
│ Phase                      │ Budget    │ Notes                        │
├────────────────────────────┼───────────┼──────────────────────────────┤
│ Intent + Entity (1 LLM)   │ 400ms     │ Gemini Flash via SafeChain   │
│ Vector Search (pgvector)   │ 50ms      │ Indexed, 768-dim, <500 rows  │
│ Graph Validation (AGE)     │ 100ms     │ 2-3 Cypher queries           │
│ Few-Shot Search (FAISS)    │ 20ms      │ In-memory, <200 vectors      │
│ Filter Resolution          │ 15ms      │ Hash + fuzzy + synonym       │
│ Prompt Assembly            │ 5ms       │ String formatting            │
│ ReAct: LLM → query-sql    │ 1200ms    │ 1 Gemini call + 1 MCP call   │
│ ReAct: LLM → format       │ 600ms     │ 1 Gemini call (final answer) │
│ Post-processing            │ 10ms      │ Trace assembly               │
├────────────────────────────┼───────────┼──────────────────────────────┤
│ TOTAL                      │ ~2400ms   │ P50, well within 4s budget   │
│ P95 (with retries/network) │ ~3500ms   │ Leaves 500ms headroom        │
└────────────────────────────┴───────────┴──────────────────────────────┘

Comparison vs. PoC (no retrieval):
  PoC:    5-6 LLM calls × 500ms = 2500-3000ms LLM + 500-1000ms tools = ~4000ms
  Cortex: 2-3 LLM calls × 500ms = 1000-1500ms LLM + 200ms retrieval  = ~2400ms
  Savings: ~1600ms (40% faster) + higher accuracy
```

---

## 7. Prompt Engineering

### Intent + Entity Classification Prompt

```python
CLASSIFY_AND_EXTRACT_PROMPT = """You are an intent classifier and entity extractor for a financial data analytics system at American Express.

Given the user's question, determine the intent and extract structured entities.

## Intents
- data_query: User wants data, metrics, or analysis from the data warehouse
- schema_browse: User wants to explore what data is available ("what fields exist?")
- saved_content: User wants existing dashboards or saved queries
- follow_up: User is refining a previous query ("break that down by...", "add a filter for...")
- out_of_scope: Not a data-related question

## Available Business Terms
{taxonomy_terms}

## Previous Context
{previous_context}

## User Query
{query}

Return valid JSON:
{{
  "intent": "<intent>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>",
  "entities": {{
    "metrics": ["<business metric names>"],
    "dimensions": ["<grouping/breakdown fields>"],
    "filters": {{"<field>": "<value>"}},
    "time_range": "<time expression or null>",
    "sort": "<ascending|descending or null>",
    "limit": <integer or null>
  }}
}}"""
```

### Augmented System Prompt (injected into ReAct)

```python
AUGMENTED_PROMPT_TEMPLATE = """You are a data analyst assistant that queries Looker on behalf of American Express analysts.

## Retrieved Context (from Cortex retrieval pipeline)
The retrieval pipeline has already identified the correct Looker fields for this query.
Confidence: {confidence:.0%}

- Model: {model}
- Explore: {explore}
- Dimensions: {dimensions}
- Measures: {measures}
- Filters: {filters}
- Matched golden query: {fewshot_match}

## Instructions
1. Use `query-sql` with EXACTLY these fields. Do NOT explore or discover.
2. The filters include mandatory partition filters. Do NOT remove them.
3. If query-sql returns an error, report the error. Do NOT attempt to fix it by changing fields.
4. Present results clearly with:
   - A direct answer to the question
   - The data in a readable table
   - The SQL used (for transparency)
5. Suggest 2-3 follow-up questions the user might ask.

## Boundaries
- Never make predictions or forecasts
- Never expose PII or raw card numbers
- Never modify data — read-only access
- If unsure, ask the user to clarify rather than guessing"""
```

---

## 8. Error Handling & Fallback

### Fallback Strategy

The system degrades gracefully. If any Phase 1 component fails, the query falls through to the raw PoC behavior:

```
Classification fails (LLM error)    → skip to Phase 2 (raw ReAct, no augmentation)
Classification low confidence (<0.7) → skip to Phase 2 (raw ReAct, no augmentation)
Retrieval returns "no_match"         → skip to Phase 2 (raw ReAct, no augmentation)
Retrieval returns "clarify"          → ask user to rephrase (don't hit LLM)
Retrieval returns "disambiguate"     → present options to user (1 LLM call)
Phase 2 fails (tool error)          → return error with trace showing where it broke
```

**Principle:** Phase 1 is additive. If it works, queries are faster and more accurate. If it fails, the system still functions — just slower and less reliable, exactly like the PoC.

### Error Types

```python
class CortexError(Exception):
    """Base exception for Cortex pipeline errors."""
    def __init__(self, message: str, step: str, recoverable: bool = True):
        self.step = step
        self.recoverable = recoverable
        super().__init__(message)

class ClassificationError(CortexError):
    """Intent classification failed."""
    def __init__(self, message: str):
        super().__init__(message, step="intent_classification", recoverable=True)

class RetrievalError(CortexError):
    """Hybrid retrieval failed."""
    def __init__(self, message: str):
        super().__init__(message, step="retrieval", recoverable=True)

class SafeChainError(CortexError):
    """SafeChain/CIBIS authentication or LLM call failed."""
    def __init__(self, message: str):
        super().__init__(message, step="safechain", recoverable=False)
```

---

## 9. Session & Memory

### Session State (Within Conversation)

The `CortexOrchestrator` maintains session state for multi-turn conversations:

```python
# Managed by CortexOrchestrator instance:
last_retrieval_result: RetrievalResult | None  # for follow-up queries
conversation_history: list[dict]               # managed by ChatSession
```

ADK Session is NOT used. The PoC's `ChatSession` already manages conversation history (last 20 messages). `CortexOrchestrator` adds `last_retrieval_result` for follow-up detection.

### Long-Term Memory (PostgreSQL)

All persistent state lives in PostgreSQL (single instance, pgvector + AGE extensions):

| Table | Purpose | Read/Write |
|-------|---------|-----------|
| `field_embeddings` | pgvector embeddings of LookML field descriptions | Read at query time |
| `lookml_graph` | AGE graph of explore → view → field relationships | Read at query time |
| `golden_queries` | Verified query patterns for FAISS + evaluation | Read at query time |
| `dimension_value_catalog` | Auto-extracted dimension values + synonyms (ADR-007) | Read + write (learning loop) |
| `synonym_suggestions` | User-initiated synonym proposals (ADR-008) | Write at feedback time |
| `query_logs` | Full PipelineTrace per query (for evaluation + debugging) | Write after each query |

---

## 10. Deployment

```
┌─────────────────────────────────────────────────────┐
│                  GKE Cluster                         │
│                                                      │
│   ┌─────────────┐    ┌────────────────────────────┐ │
│   │  Cortex API  │    │  MCP Toolbox (sidecar)     │ │
│   │  (FastAPI)   │───▶│  ./toolbox --tools-file    │ │
│   │  Port 8080   │    │  config/tools.yaml         │ │
│   └──────┬──────┘    │  Port 5000                  │ │
│          │            └────────────┬───────────────┘ │
│          │                         │                  │
│          │    ┌────────────────────┘                  │
│          │    │                                       │
│          ▼    ▼                                       │
│   ┌──────────────┐    ┌──────────────┐              │
│   │  PostgreSQL   │    │  Looker API   │              │
│   │  (pgvector    │    │  (via MCP)    │              │
│   │   + AGE)      │    │              │              │
│   │  Port 5432    │    └──────────────┘              │
│   └──────────────┘                                   │
│                                                      │
└──────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
  ┌──────────────┐       ┌──────────────┐
  │  SafeChain    │       │  BigQuery    │
  │  Gateway      │       │  (via Looker)│
  │  (CIBIS auth) │       │              │
  └──────────────┘       └──────────────┘
```

**Container image:** Single Python container running FastAPI + CortexOrchestrator. MCP Toolbox runs as a sidecar in the same pod.

**Scaling:** Stateless — horizontal scaling via GKE replicas. Session state (`last_retrieval_result`) is per-request; for multi-turn, the frontend sends conversation history with each request.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| SafeChain embedding endpoint not available | Medium | High — blocks pgvector | Verify with Ravi J. Fallback: Vertex AI embedding API with separate auth |
| SafeChain latency >500ms for classification | Medium | Medium — reduces speed advantage | Classification cache for repeated patterns. Gemini Flash is fastest. |
| AgentOrchestrator internal API changes | Low | Medium — breaks composition wrapper | Pin safechain version. Wrapper has thin interface (`.run()` only) |
| pgvector + AGE on same PostgreSQL instance causes contention | Low | Medium — latency spike | Separate read replicas if needed. Current scale (<500 fields) is fine. |
| Intent classification accuracy <90% | Medium | High — wrong pipeline path | Fallback to raw ReAct on low confidence. Likhita targets >95%. |
| MCP Toolbox sidecar fails | Low | High — no Looker access | Health check + restart policy. Already proven in PoC. |

---

## 12. Validation Plan

### Demo Criteria (Thursday Target)

1. User types query → system returns correct answer with trace showing all pipeline steps
2. Trace shows: intent classified, entities extracted, retrieval found model/explore/fields, filter values resolved, SQL executed
3. Total latency <4 seconds
4. At least 5 out of 5 golden queries produce correct results

### Post-Demo Evaluation

| Metric | Target | How Measured |
|--------|--------|-------------|
| End-to-end accuracy | >90% | 25 golden queries (from `lookml/demo_queries.md`) |
| Intent accuracy | >95% | 200 labeled queries |
| Retrieval precision | >90% | Correct model + explore + fields |
| Filter resolution accuracy | >95% | Correct filter values (deterministic) |
| Time to first data | <4s P95 | Measured from API request to response |
| LLM calls per query | 2-3 (down from 5-6) | Counted in PipelineTrace |

---

## 13. Related Decisions

- **ADR-001:** ADK over LangGraph — ADK's `McpToolset` for Looker MCP tool binding
- **ADR-004:** Semantic layer representation — pgvector + AGE on single PostgreSQL
- **ADR-005:** Intent as pre-processing — classification happens before ReAct loop, not as a tool
- **ADR-007:** Filter value resolution — auto-extracted value catalog, 4-pass matching
- **ADR-008:** Learning loop — Wilson score confidence, multi-user synonym approval
- **Hybrid Retrieval Design:** Full retrieval architecture specification
