# ADR-005: Intent & Entity Classification Pipeline Integration

**Date:** March 6, 2026
**Status:** Proposed
**Decider:** Saheb
**Consulted:** Likhita (intent classification lead), Sulabh

---

## Decision

We will integrate intent classification and entity extraction as a **pre-processing pipeline stage** into the existing SafeChain CLI agent (`chat.py`), not as LLM-invoked tools. The classification layer sits between the user query and the existing ReAct orchestration loop, augmenting the system prompt with retrieval results before the LLM ever sees the query.

## Context

### Current State: chat.py (PoC)

The existing CLI agent at `/Desktop/safechain/chat.py` implements a ReAct-style orchestration loop around SafeChain's `MCPToolAgent`:

```
User Query → System Prompt → LLM (Gemini via SafeChain)
                                ↓
                         Tool Calls (Looker MCP)
                                ↓
                         Tool Results → LLM → Loop or Final Answer
```

**What works:** Multi-turn reasoning, tool execution, conversation history, thinking visualization.

**What's missing:** The LLM must discover the right model, explore, dimensions, and measures from scratch on every query by calling `get-models` → `get-explores` → `get-dimensions` → `get-measures` → `query-sql`. This is:
- **Slow:** 4-6 LLM calls before the first data query (each ~500ms through SafeChain)
- **Unreliable:** The LLM often picks wrong fields, misses partition filters, or explores the wrong model
- **Expensive:** Every exploration step is a Gemini call through SafeChain — adds up at 100+ queries/day
- **No structural validation:** The LLM has no way to verify that selected fields can be queried together

### Target State: Cortex Pipeline

```
User Query
    ↓
┌──────────────────────────────┐
│  INTENT CLASSIFIER            │  ← NEW: Single LLM call
│  (data_query | schema_browse  │
│   | saved_content | chitchat) │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  ENTITY EXTRACTOR             │  ← NEW: Single LLM call (or same call)
│  metrics[], dimensions[],     │
│  filters[], time_range        │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  RETRIEVAL PIPELINE           │  ← NEW: No LLM calls (~260ms)
│  pgvector + AGE + FAISS       │
│  → RRF fusion                 │
│  → Structural validation      │
│  → RetrievalResult            │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  AUGMENTED SYSTEM PROMPT      │  ← MODIFIED: Inject retrieval context
│  + RetrievalResult context    │
│  + Specific field instructions│
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│  MCPToolAgent (existing)      │  ← UNCHANGED: Same ReAct loop
│  Now starts with correct      │
│  fields, skips exploration    │
└──────────────────────────────┘
```

**Key principle:** The existing `AgentOrchestrator` / `SafeChainOrchestrator` stays intact. We add a pre-processing layer that makes the LLM smarter before it enters the ReAct loop.

---

## Design

### Intent Classification

**Purpose:** Route queries to the right handler. Not every user message needs the full retrieval pipeline.

**Taxonomy:**

| Intent | Example | Handler |
|--------|---------|---------|
| `data_query` | "What was total billed business for Millennials?" | Full retrieval pipeline → augmented MCP query |
| `schema_browse` | "What explores are available?" / "What does billed_business mean?" | Direct MCP tool call (`get-explores`, `get-dimensions`) |
| `saved_content` | "Show me the executive dashboard" | Direct MCP tool call (`get-dashboards`, `run-dashboard`) |
| `follow_up` | "Now break that down by card type" | Reuse previous RetrievalResult, modify dimensions/filters |
| `clarification` | "I meant the premium definition" | Update previous filter, re-execute |
| `out_of_scope` | "What's the weather?" | Polite refusal |

**Implementation:** Single Gemini Flash call with structured output:

```python
INTENT_PROMPT = """Classify the user's intent. Return JSON.

Intents:
- data_query: User wants data or metrics from the warehouse
- schema_browse: User wants to explore what data is available
- saved_content: User wants existing looks or dashboards
- follow_up: User is refining a previous query (e.g., "break that down by...")
- clarification: User is disambiguating a previous ambiguous result
- out_of_scope: Not a data question

Previous context (if any): {previous_retrieval_result}

User: {query}

Return:
{
  "intent": "<intent>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>"
}"""
```

**Decision:** Use a single LLM call for both intent AND entity extraction (combined prompt) to minimize SafeChain round-trips. At our scale, one call is materially better than two.

### Entity Extraction

**Purpose:** Extract structured entities from natural language for retrieval.

**Output schema:**

```python
@dataclass
class ExtractedEntities:
    metrics: list[str]        # ["total billed business"]
    dimensions: list[str]     # ["generation"]
    filters: list[Filter]     # [Filter(field="generation", op="=", value="Millennial")]
    time_range: str | None    # "last quarter"
    sort: str | None          # "descending" / "ascending"
    limit: int | None         # 10
```

**Combined intent + entity prompt** (single LLM call):

```python
CLASSIFY_AND_EXTRACT_PROMPT = """You are an intent classifier and entity extractor for a data analytics system.

Given the user's question, return:
1. The intent type
2. Extracted entities (metrics, dimensions, filters, time range)

Available business terms (from taxonomy):
{business_terms_context}

Previous query context (if follow-up):
{previous_context}

User: {query}

Return JSON:
{
  "intent": "data_query|schema_browse|saved_content|follow_up|clarification|out_of_scope",
  "confidence": 0.95,
  "entities": {
    "metrics": ["total billed business"],
    "dimensions": ["generation"],
    "filters": [{"field": "generation", "operator": "=", "value": "Millennial"}],
    "time_range": "last quarter",
    "sort": null,
    "limit": null
  }
}"""
```

### Integration Point: Modified AgentOrchestrator

The integration happens in the `run()` method of the existing orchestrator. We add a pre-processing step before the ReAct loop:

```python
class CortexOrchestrator(AgentOrchestrator):
    """Extended orchestrator with intent classification and retrieval."""

    def __init__(self, retrieval_pipeline, taxonomy, **kwargs):
        super().__init__(**kwargs)
        self.retrieval = retrieval_pipeline  # pgvector + AGE + FAISS
        self.taxonomy = taxonomy
        self.last_retrieval_result = None    # for follow-ups

    async def run(self, messages: list[dict]) -> dict:
        user_query = messages[-1]["content"]

        # Step 1: Classify intent + extract entities (1 LLM call)
        classification = await self._classify_and_extract(user_query)

        # Step 2: Route based on intent
        if classification.intent == "data_query":
            return await self._handle_data_query(classification, messages)
        elif classification.intent == "follow_up":
            return await self._handle_follow_up(classification, messages)
        elif classification.intent == "schema_browse":
            # Pass through to existing ReAct loop — LLM will use get-explores etc.
            return await super().run(messages)
        elif classification.intent == "out_of_scope":
            return {"content": "I can help with data questions about the Amex warehouse. "
                              "Could you rephrase as a data question?"}
        else:
            return await super().run(messages)

    async def _handle_data_query(self, classification, messages):
        # Step 3: Run retrieval pipeline (no LLM — ~260ms)
        retrieval_result = await self.retrieval.retrieve(
            entities=classification.entities,
            taxonomy=self.taxonomy,
        )
        self.last_retrieval_result = retrieval_result

        # Step 4: Augment the system prompt with retrieval context
        augmented_prompt = self._build_augmented_prompt(retrieval_result)

        # Step 5: Run existing ReAct loop with augmented context
        # Now the LLM starts with the RIGHT model/explore/fields
        # and goes straight to query_sql instead of exploring
        messages[0] = {"role": "system", "content": augmented_prompt}
        return await super().run(messages)

    def _build_augmented_prompt(self, result: RetrievalResult) -> str:
        return f"""{SYSTEM_PROMPT}

## Retrieved Context (from Cortex retrieval pipeline)

I have already identified the correct Looker fields for this query:

- **Model:** {result.model}
- **Explore:** {result.explore}
- **Dimensions:** {', '.join(result.dimensions)}
- **Measures:** {', '.join(result.measures)}
- **Required filters:** {json.dumps(result.filters)}
- **Confidence:** {result.confidence}

**Action:** Use `query-sql` directly with these exact fields. Do NOT explore or
discover — the retrieval pipeline has already validated that these fields exist
in this explore and can be queried together.

If the query returns an error, you may fall back to manual exploration (Path B)
but report the error to the user."""
```

### What Changes in chat.py

**Minimal changes to existing code:**

1. `AgentOrchestrator` → `CortexOrchestrator` (subclass, ~100 lines)
2. Add `RetrievalPipeline` import (pgvector + AGE + FAISS client)
3. Add `Taxonomy` import (business term registry)
4. `main()` initialization adds retrieval pipeline setup

**What stays identical:**
- `MCPToolAgent` — unchanged
- `MCPToolLoader` — unchanged
- `ThinkingCallback` — unchanged (extended with new event types)
- `ChatSession` — unchanged
- `ConsoleThinkingCallback` — unchanged
- SafeChain authentication flow — unchanged
- All MCP tool bindings — unchanged

### Follow-up Handling

For multi-turn conversations ("now break that down by card type"):

```python
async def _handle_follow_up(self, classification, messages):
    if not self.last_retrieval_result:
        # No previous context — treat as new data query
        return await self._handle_data_query(classification, messages)

    # Modify the previous retrieval result with new entities
    updated_result = self.last_retrieval_result.copy()

    # Add new dimensions
    if classification.entities.dimensions:
        new_dims = await self.retrieval.resolve_dimensions(
            classification.entities.dimensions,
            explore=updated_result.explore,
        )
        updated_result.dimensions.extend(new_dims)

    # Add/update filters
    if classification.entities.filters:
        for f in classification.entities.filters:
            updated_result.filters[f.field] = f.value

    # Re-validate structurally (are new fields in the same explore?)
    is_valid = await self.retrieval.validate_fields(
        updated_result.dimensions + updated_result.measures,
        explore=updated_result.explore,
    )

    if not is_valid:
        return {"content": "The additional fields you requested aren't available "
                          "in the same data source. Let me search for alternatives."}

    self.last_retrieval_result = updated_result
    return await self._handle_data_query_with_result(updated_result, messages)
```

---

## Why Pre-Processing, Not Tool-Based

| Approach | Pre-processing (chosen) | Tool-based (rejected) |
|----------|------------------------|----------------------|
| LLM calls for classification | 1 (combined intent + entity) | 2-4 (LLM decides which tools to call) |
| Reliability | Deterministic pipeline after classification | LLM may skip validation, call tools in wrong order |
| Latency | ~460ms (200ms classify + 260ms retrieve) | ~2-3s (multiple LLM round-trips through SafeChain) |
| Debuggability | Each stage has clear input/output | Tool calls interleaved with LLM reasoning |
| Cost | 1 SafeChain call + local compute | 3-5 SafeChain calls |
| Testing | Each stage independently testable | Must test full agent loop |

**The fundamental insight:** Classification and retrieval are deterministic operations. They don't benefit from LLM reasoning. Making them tools means the LLM might skip them, call them in the wrong order, or ignore their results. Making them a pipeline stage before the LLM guarantees they always run.

---

## Evaluation

### Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Intent accuracy | >95% | Golden dataset of 200 queries with labeled intents |
| Entity extraction recall | >90% | Correct metrics/dimensions extracted vs. expected |
| End-to-end accuracy | >90% | Query returns correct answer (field precision + SQL correctness) |
| Time to first data | <4s P95 | From user input to data response |
| SafeChain calls saved | 3-5 per query | Compare pre/post classification (was 5-6, now 1-2) |

### Testing Strategy

1. **Unit tests:** Intent classifier and entity extractor tested independently with 200 labeled queries
2. **Integration tests:** Full pipeline (classify → retrieve → augment → MCP query) tested with golden dataset
3. **A/B comparison:** Run same 50 queries through old (no classification) and new (with classification) pipeline, compare accuracy and latency

---

## Implementation Plan

| Phase | Task | Owner | Dependency |
|-------|------|-------|-----------|
| 1 | Intent classification prompt + structured output | Likhita | None |
| 2 | Entity extraction (combined with intent) | Likhita | Phase 1 |
| 3 | pgvector + AGE setup and schema creation | Rajesh | ADR-004 approved |
| 4 | LookML → pgvector/AGE sync pipeline | Rajesh | Phase 3 + LookML views ready |
| 5 | Retrieval pipeline (vector + graph + FAISS + RRF) | Saheb | Phase 3, 4 |
| 6 | `CortexOrchestrator` integration with chat.py | Saheb | Phase 1, 2, 5 |
| 7 | Golden dataset for intent + entity evaluation | Animesh | Phase 1, 2 |
| 8 | End-to-end testing | All | Phase 6, 7 |

### Likhita's Scope (Intent Classification Lead)

Likhita owns the intent classification and entity extraction components:
1. Design the classification taxonomy (expand beyond 6 intents if needed)
2. Build the combined intent + entity extraction prompt
3. Create evaluation dataset (200 queries, labeled)
4. Achieve >95% intent accuracy, >90% entity recall on eval set
5. Handle edge cases: ambiguous intents, multi-intent queries, follow-up detection

She should NOT be responsible for the retrieval pipeline (pgvector/AGE/FAISS) or the orchestrator integration — those are Saheb's.

---

## Consequences

### Positive
- Existing chat.py architecture is preserved — subclass, don't rewrite
- 3-5 fewer SafeChain calls per query (significant cost and latency savings)
- Retrieval pipeline ensures structural correctness before LLM sees the query
- Follow-up handling becomes deterministic (modify previous result, not re-explore)
- Each pipeline stage is independently testable and debuggable

### Negative
- Adds ~460ms latency for the classification + retrieval stage (but saves ~2-3s in exploration calls — net positive)
- Classification errors propagate downstream (mitigated by confidence threshold — low-confidence classifications fall through to the existing ReAct loop)
- Requires taxonomy/business term registry to be maintained alongside LookML

### Risks
- Combined intent + entity prompt may degrade accuracy vs. separate calls — benchmark before committing
- Follow-up detection is fragile for conversational context — start with simple heuristics, improve with data
- SafeChain latency is the bottleneck — if classification call takes >500ms, the pipeline advantage shrinks

### Fallback
If classification confidence < 0.7, skip the retrieval pipeline entirely and fall through to the existing ReAct loop. The system degrades to the current PoC behavior — slower but functional. This ensures the classification layer is additive, not a gate.
