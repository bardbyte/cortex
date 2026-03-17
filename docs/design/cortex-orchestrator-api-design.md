# Cortex Orchestrator + API Design

**Author:** Saheb | **Date:** March 16, 2026 | **Status:** Ready for Implementation
**Audience:** Ayush (frontend), Saheb (orchestrator), Sulabh/Ashok (architecture review)
**Depends on:** [Agentic Orchestration Design](agentic-orchestration-design.md), [Demo UI Design](cortex-demo-ui-design.md), [ADR-001 ADK](../../adr/001-adk-over-langgraph.md)

---

## 1. Overview

This document specifies the CortexOrchestrator class and its SSE-streaming API -- the contract between the Python backend and Ayush's React frontend. It defines every event the frontend consumes, every endpoint it calls, the conversation management model, the PipelineTrace schema for eval, and the error handling strategy.

The system takes a natural language question, streams pipeline progress to the UI in real time (like Gemini's "thinking" display), executes SQL via Looker MCP, and returns structured results with follow-up suggestions. Every decision the system makes is captured in a trace that is stored, displayable, and replayable.

**What exists today:**
- Retrieval pipeline (`src/retrieval/pipeline.py`) -- working, 83% accuracy, synchronous
- Filter resolution (`src/retrieval/filters.py`) -- working, deterministic 5-pass
- API server (`src/api/server.py`) -- working, stops after retrieval (no SQL generation)
- PoC orchestrator (`access_llm/chat.py`) -- working, AgentOrchestrator wrapping MCPToolAgent
- SafeChain model adapter (`src/adapters/model_adapter.py`) -- working

**What this document adds:**
- CortexOrchestrator class that composes all of the above into a streaming pipeline
- SSE API contract for real-time pipeline visualization
- Conversation management for multi-turn follow-ups
- PipelineTrace schema for evaluation and debugging
- Production error handling with graceful degradation

---

## 2. Architecture Overview

### System Diagram

```
                          +-------------------------+
                          |   React Frontend (Ayush) |
                          |   Analyst + Eng Views    |
                          +------------+------------+
                                       | EventSource (SSE)
                                       | POST /api/v1/query
                                       v
                          +-------------------------+
                          |     FastAPI Server       |
                          |  /query  /followup       |
                          |  /trace  /capabilities   |
                          |  /health /feedback       |
                          +------------+------------+
                                       |
                                       v
+----------------------------------------------------------------------+
|                       CortexOrchestrator                              |
|                                                                       |
|  +--- PHASE 1: PRE-PROCESSING (deterministic, 1 LLM call) --------+ |
|  |                                                                   | |
|  |  [Intent + Entity]  -->  [Retrieval]  -->  [Explore Scoring]     | |
|  |  Classification          Vector+Graph      Coverage x SimScore   | |
|  |  (1 Gemini call)         (pgvector+AGE)    (deterministic)       | |
|  |        |                      |                   |              | |
|  |        v                      v                   v              | |
|  |  [Filter Resolution]  <-- top explore selected                   | |
|  |  5-pass deterministic                                            | |
|  +------------------------------|-----------------------------------+ |
|                                 | RetrievalResult + resolved filters |
|                                 v                                     |
|  +--- PHASE 2: REACT EXECUTION (LLM + Looker MCP) ----------------+ |
|  |                                                                   | |
|  |  Augmented Prompt -----> AgentOrchestrator (unchanged PoC)       | |
|  |  (fields pre-selected)   MCPToolAgent --> Looker MCP --> BQ      | |
|  |                          1-2 iterations (down from 5-6)          | |
|  +------------------------------|-----------------------------------+ |
|                                 | SQL results + raw data             |
|                                 v                                     |
|  +--- PHASE 3: POST-PROCESSING (1 LLM call) ----------------------+ |
|  |                                                                   | |
|  |  [Response Formatting]  [Follow-up Generation]  [Trace Assembly] | |
|  |  Answer + data table     2-3 suggestions         Per-step timing | |
|  +-------------------------------------------------------------------+ |
+----------------------------------------------------------------------+
         |                    |                    |
         v                    v                    v
  +-------------+     +-----------+     +------------+
  | PostgreSQL  |     |  FAISS    |     | SafeChain  |
  | pgvector +  |     |  (golden  |     | Gateway    |
  | Apache AGE  |     |   queries)|     | (CIBIS)    |
  +-------------+     +-----------+     +------------+
```

### Data Flow -- Happy Path

```
User: "What was total billed business for small businesses last quarter?"
  |
  v
[1] Intent Classification (Gemini Flash, ~300ms)
    SSE: step_start -> step_progress -> step_complete
    Output: intent=data_query, entities={metrics: ["total billed business"],
            filters: {bus_seg: "small businesses"}, time: "last quarter"}
  |
  v
[2] Entity Extraction + Vector Search (pgvector, ~80ms)
    SSE: step_start -> step_progress -> step_complete
    Output: 15 candidate fields across 5 explores, top similarities
  |
  v
[3] Explore Scoring (deterministic, ~5ms)
    SSE: step_start -> explore_scored -> step_complete
    Output: finance_cardmember_360 (confidence=0.94), 2 runner-ups
  |
  v
[4] Filter Resolution (deterministic, ~15ms)
    SSE: step_start -> step_progress -> step_complete
    Output: bus_seg=OPEN, partition_date="last 1 quarters"
  |
  v
[5] SQL Generation via Looker MCP (Gemini + MCP tool call, ~1200ms)
    SSE: step_start -> sql_generated -> step_complete
    Output: SELECT ... FROM ... WHERE bus_seg='OPEN' AND partition_date ...
  |
  v
[6] Query Execution (BigQuery via Looker, ~500ms)
    SSE: step_start -> step_complete
    Output: {columns: [...], rows: [...], row_count: 1}
  |
  v
[7] Response Formatting + Follow-ups (Gemini, ~400ms)
    SSE: step_start -> results -> follow_ups -> step_complete -> done
    Output: "Total billed business for Small Business (OPEN) last quarter
             was $4.2B." + follow-up suggestions
```

### How SafeChain / MCPToolAgent Fits In

SafeChain is not optional and has no fallback. It provides two things:

1. **LLM access via CIBIS auth** -- `model(model_idx)` returns a LangChain-compatible chat model or embedding model. Model indices are defined in `config.yml` managed by ee_config.
2. **MCP tool binding** -- `MCPToolLoader.load_tools(config)` connects to MCP servers (Looker MCP Toolbox running as sidecar) and returns tool objects that MCPToolAgent can invoke.

The CortexOrchestrator uses SafeChain at three points:
- **Intent classification:** Direct `model("3").invoke()` call (Gemini Flash, no tools needed)
- **ReAct execution:** `AgentOrchestrator` wrapping `MCPToolAgent` with augmented system prompt
- **Follow-up generation:** Direct `model("3").invoke()` call (generates suggestions from context)

```python
from ee_config.config import Config
from safechain.lcel import model
from safechain.tools.mcp import MCPToolLoader, MCPToolAgent

# Initialization (once at server startup)
config = Config.from_env()
tools = await MCPToolLoader.load_tools(config)
classifier_model = model("3")           # Gemini 2.5 Flash
react_agent = MCPToolAgent("3", tools)   # Flash + Looker MCP tools
```

---

## 3. Pipeline Steps -- SSE Event Specification

Every step in the pipeline emits a sequence of SSE events. The frontend renders these in the Engineering View panel as sequential steps (per the UI design doc Section 9).

### 3.1 SSE Event Types

| Event Type | Purpose | Emitted By |
|------------|---------|------------|
| `step_start` | A pipeline step has begun | Every step |
| `step_progress` | Intermediate progress within a step | Long-running steps |
| `step_complete` | A pipeline step finished | Every step |
| `explore_scored` | Explore scoring results (special detail event) | Explore Scoring step |
| `sql_generated` | The SQL has been generated | SQL Generation step |
| `results` | Final query results (data) | Response Formatting step |
| `follow_ups` | Follow-up question suggestions | Response Formatting step |
| `done` | Pipeline complete, stream ends | Orchestrator |
| `error` | An error occurred | Any step |
| `disambiguate` | System needs user to choose between options | Retrieval / Scoring |
| `clarify` | System needs user to rephrase | Classification / Retrieval |

### 3.2 SSE Wire Format

All events follow the [SSE specification](https://html.spec.whatwg.org/multipage/server-sent-events.html). Each event has a named `event:` field and a JSON `data:` payload.

```
event: step_start
data: {"step": "intent_classification", "step_number": 1, "total_steps": 7, "message": "Analyzing your question...", "timestamp": 1710547200.123}

event: step_complete
data: {"step": "intent_classification", "step_number": 1, "duration_ms": 287, "message": "Intent classified as data query", "detail": {...}, "timestamp": 1710547200.410}

```

The `data` field is always a single-line JSON object (newlines within data are not used). The frontend parses each event with `JSON.parse(event.data)`.

### 3.3 Step-by-Step Event Specification

#### Step 1: Intent Classification + Entity Extraction

**What it does:** Single LLM call to Gemini Flash. Classifies the query intent (data_query, schema_browse, follow_up, out_of_scope) and extracts structured entities (metrics, dimensions, filters, time range).

**Timing budget:** 400ms

**Events emitted:**

```
event: step_start
data: {
  "step": "intent_classification",
  "step_number": 1,
  "total_steps": 7,
  "message": "Analyzing your question..."
}

event: step_complete
data: {
  "step": "intent_classification",
  "step_number": 1,
  "duration_ms": 287,
  "message": "Identified as a data query",
  "detail": {
    "intent": "data_query",
    "confidence": 0.97,
    "entities": {
      "metrics": ["total billed business"],
      "dimensions": [],
      "filters": {"bus_seg": "small businesses"},
      "time_range": "last quarter"
    },
    "reasoning": "User is asking for a specific metric with segment and time filters."
  }
}
```

**Error handling:** If the LLM call fails or returns unparseable JSON, emit `step_complete` with `"status": "fallback"` and skip to Phase 2 with no augmentation (PoC behavior). The pipeline continues -- this step is additive, not blocking.

**Short-circuit paths:**
- `intent == "out_of_scope"` -- emit `done` with a polite refusal. No further steps.
- `intent == "schema_browse"` -- skip retrieval, go straight to Phase 2 (let the LLM use Looker tools to browse schema).

---

#### Step 2: Retrieval -- Vector Search + Graph Validation

**What it does:** Takes extracted entities, embeds them via SafeChain BGE model, searches pgvector for candidate LookML fields, validates against the AGE explore-field graph. Zero LLM calls.

**Timing budget:** 150ms

**Events emitted:**

```
event: step_start
data: {
  "step": "retrieval",
  "step_number": 2,
  "total_steps": 7,
  "message": "Searching for matching data fields..."
}

event: step_progress
data: {
  "step": "retrieval",
  "message": "Found 15 candidate fields across 5 explores",
  "detail": {
    "candidate_count": 15,
    "explore_count": 5,
    "top_similarity": 0.94
  }
}

event: step_complete
data: {
  "step": "retrieval",
  "step_number": 2,
  "duration_ms": 142,
  "message": "Retrieved 15 candidate fields",
  "detail": {
    "candidate_count": 15,
    "explore_count": 5,
    "entity_coverage": 1.0
  }
}
```

**Error handling:** If pgvector or AGE is unreachable, emit `step_complete` with `"status": "error"` and fall through to Phase 2 (PoC behavior). Log the error for ops.

---

#### Step 3: Explore Scoring

**What it does:** Scores each candidate explore using the multiplicative formula: `coverage^3 x mean_sim x base_view_bonus x desc_sim_bonus x filter_penalty`. Selects the top explore. Detects near-misses for disambiguation. Deterministic -- zero LLM calls.

**Timing budget:** 10ms

**Events emitted:**

```
event: step_start
data: {
  "step": "explore_scoring",
  "step_number": 3,
  "total_steps": 7,
  "message": "Scoring candidate data sources..."
}

event: explore_scored
data: {
  "step": "explore_scoring",
  "explores": [
    {
      "name": "finance_cardmember_360",
      "score": 1.87,
      "confidence": 0.94,
      "coverage": 1.0,
      "matched_entities": ["total_billed_business", "bus_seg"],
      "is_winner": true
    },
    {
      "name": "finance_merchant_profitability",
      "score": 0.62,
      "confidence": 0.33,
      "coverage": 0.5,
      "matched_entities": ["total_billed_business"],
      "is_winner": false
    }
  ],
  "winner": "finance_cardmember_360",
  "confidence": 0.94,
  "is_near_miss": false
}

event: step_complete
data: {
  "step": "explore_scoring",
  "step_number": 3,
  "duration_ms": 4,
  "message": "Selected finance_cardmember_360 (94% confidence)",
  "detail": {
    "selected_explore": "finance_cardmember_360",
    "confidence": 0.94,
    "runner_up": "finance_merchant_profitability",
    "runner_up_confidence": 0.33,
    "is_near_miss": false
  }
}
```

**Near-miss handling:** If `is_near_miss == true` (runner-up within 85% of top score), emit a `disambiguate` event instead of proceeding:

```
event: disambiguate
data: {
  "step": "explore_scoring",
  "message": "I found two equally relevant data sources. Which one matches your question?",
  "options": [
    {
      "explore": "finance_cardmember_360",
      "description": "Card member activity, demographics, portfolio health",
      "confidence": 0.89
    },
    {
      "explore": "finance_merchant_profitability",
      "description": "Merchant spending, ROC metrics, dining behavior",
      "confidence": 0.86
    }
  ]
}
```

The stream pauses here. The frontend shows a disambiguation modal (per UI design doc). The user's selection is sent as a follow-up request with the chosen explore ID.

---

#### Step 4: Filter Resolution

**What it does:** Resolves user-typed filter values to LookML-compatible values using the deterministic 5-pass cascade (exact match, synonym, fuzzy, embedding, passthrough). Auto-injects mandatory partition filters. Zero LLM calls.

**Timing budget:** 20ms

**Events emitted:**

```
event: step_start
data: {
  "step": "filter_resolution",
  "step_number": 4,
  "total_steps": 7,
  "message": "Resolving filter values..."
}

event: step_complete
data: {
  "step": "filter_resolution",
  "step_number": 4,
  "duration_ms": 12,
  "message": "Resolved 2 filters (1 user, 1 mandatory)",
  "detail": {
    "resolved": [
      {
        "field": "bus_seg",
        "user_said": "small businesses",
        "resolved_to": "OPEN",
        "resolution_pass": 1,
        "confidence": 1.0,
        "method": "exact_match"
      }
    ],
    "mandatory": [
      {
        "field": "partition_date",
        "value": "last 1 quarters",
        "reason": "auto_injected_partition"
      }
    ],
    "unresolved": []
  }
}
```

**Error handling:** If any filter cannot be resolved (pass 5 passthrough), include it in `unresolved` with a low confidence flag. The pipeline proceeds -- unresolved filters are passed through as-is to Looker, which may or may not accept them.

---

#### Step 5: SQL Generation (Looker MCP)

**What it does:** Constructs an augmented system prompt with the selected explore, fields, and resolved filters, then delegates to AgentOrchestrator. The LLM makes 1 MCP tool call (`query-sql`) with the pre-selected fields. This is where the PoC code runs -- the only change is the augmented prompt.

**Timing budget:** 1500ms (LLM call + MCP tool call + BigQuery execution)

**Events emitted:**

```
event: step_start
data: {
  "step": "sql_generation",
  "step_number": 5,
  "total_steps": 7,
  "message": "Generating SQL query..."
}

event: step_progress
data: {
  "step": "sql_generation",
  "message": "Calling Looker MCP with pre-selected fields...",
  "detail": {
    "model": "proj-d-lumi-gpt",
    "explore": "finance_cardmember_360",
    "measures": ["total_billed_business"],
    "dimensions": [],
    "filters": {"bus_seg": "OPEN", "partition_date": "last 1 quarters"}
  }
}

event: sql_generated
data: {
  "step": "sql_generation",
  "sql": "SELECT SUM(billed_business) AS total_billed_business FROM `amex-finance.cardmember.cm_360` WHERE bus_seg = 'OPEN' AND partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 QUARTER)",
  "explore": "finance_cardmember_360",
  "model": "proj-d-lumi-gpt"
}

event: step_complete
data: {
  "step": "sql_generation",
  "step_number": 5,
  "duration_ms": 1340,
  "message": "SQL generated and executed",
  "detail": {
    "llm_iterations": 1,
    "mcp_tool_calls": 1,
    "tool_used": "query-sql"
  }
}
```

**Error handling:** If the MCP tool call fails (Looker API error, BQ timeout), emit an `error` event with the error message and `recoverable: true`. The frontend shows the error inline with a "Retry" button. The orchestrator does NOT retry automatically -- retries burn LLM calls and BQ cost.

---

#### Step 6: Query Execution (Results Processing)

**What it does:** Parses the raw data returned by Looker MCP's `query-sql` tool. Extracts columns, rows, and row count. Formats the data for the frontend table component.

**Timing budget:** 10ms (deterministic parsing, no LLM)

**Events emitted:**

```
event: step_start
data: {
  "step": "results_processing",
  "step_number": 6,
  "total_steps": 7,
  "message": "Processing query results..."
}

event: results
data: {
  "step": "results_processing",
  "columns": [
    {"name": "total_billed_business", "type": "number", "label": "Total Billed Business"}
  ],
  "rows": [
    {"total_billed_business": 4200000000}
  ],
  "row_count": 1,
  "truncated": false,
  "bytes_scanned": null
}

event: step_complete
data: {
  "step": "results_processing",
  "step_number": 6,
  "duration_ms": 3,
  "message": "Processed 1 row",
  "detail": {
    "row_count": 1,
    "column_count": 1,
    "truncated": false
  }
}
```

**Row limit:** The API returns a maximum of 500 rows. If the result exceeds 500 rows, `truncated` is set to `true` and the frontend shows a "Showing first 500 of N rows" notice.

---

#### Step 7: Response Formatting + Follow-ups

**What it does:** Generates a natural language answer summarizing the data and 2-3 follow-up question suggestions. Uses Gemini Flash (1 LLM call) with the query, results, and conversation context.

**Timing budget:** 500ms

**Events emitted:**

```
event: step_start
data: {
  "step": "response_formatting",
  "step_number": 7,
  "total_steps": 7,
  "message": "Formatting response..."
}

event: step_complete
data: {
  "step": "response_formatting",
  "step_number": 7,
  "duration_ms": 380,
  "message": "Response ready",
  "detail": {
    "answer": "Total billed business for Small Business (OPEN) last quarter was $4.2B.",
    "follow_ups": [
      "Break down by card product",
      "Compare to previous quarter",
      "Show trend over last 4 quarters"
    ]
  }
}

event: follow_ups
data: {
  "suggestions": [
    "Break down by card product",
    "Compare to previous quarter",
    "Show trend over last 4 quarters"
  ]
}

event: done
data: {
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "total_duration_ms": 2178,
  "llm_calls": 3,
  "mcp_calls": 1,
  "overall_confidence": 0.94,
  "conversation_id": "conv_abc123"
}
```

---

## 4. REST + SSE Endpoints

### Base URL

```
https://{host}:8080/api/v1
```

### Endpoint Specification

#### POST /api/v1/query

Primary endpoint. Accepts a natural language query, returns an SSE stream of pipeline events.

**Request:**

```json
{
  "query": "What was total billed business for small businesses last quarter?",
  "conversation_id": null,
  "session_id": "sess_abc123",
  "view_mode": "engineering"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Natural language question |
| `conversation_id` | string or null | no | Existing conversation ID for follow-ups. Null for new conversations. |
| `session_id` | string | no | Browser session ID for grouping conversations |
| `view_mode` | string | no | `"analyst"` or `"engineering"` (default `"engineering"`). Controls verbosity of SSE events. |

**Response:** `Content-Type: text/event-stream`

The response is a stream of SSE events as specified in Section 3. The stream terminates with a `done` event.

In `analyst` view mode, `step_start` and `step_progress` events for deterministic steps (retrieval, scoring, filter resolution, results processing) are suppressed -- only LLM-involving steps emit progress. This keeps the Analyst View clean while the Engineering View gets the full trace.

**Error response (non-streaming):**

```json
HTTP 400: {"error": "query_empty", "message": "Query cannot be empty"}
HTTP 503: {"error": "service_unavailable", "message": "SafeChain gateway not reachable"}
```

---

#### POST /api/v1/followup

Follow-up question within an existing conversation. Same SSE streaming behavior as `/query`.

**Request:**

```json
{
  "query": "Break that down by card product",
  "conversation_id": "conv_abc123",
  "session_id": "sess_abc123"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Follow-up question |
| `conversation_id` | string | yes | Existing conversation ID (from `done` event of previous query) |
| `session_id` | string | no | Browser session ID |

**Behavior:** The orchestrator loads the conversation context (previous RetrievalResult, conversation history) and uses it to resolve the follow-up. If the follow-up modifies an existing query ("add a filter", "break down by", "compare to"), the orchestrator reuses the previous explore and adjusts fields/filters. If it is a new question, it runs the full pipeline.

**Response:** Same SSE stream as `/query`.

---

#### GET /api/v1/trace/{trace_id}

Retrieve the full PipelineTrace for a completed query. Used for debugging, eval, and the Engineering View's "replay" mode.

**Response:**

```json
{
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "query": "What was total billed business for small businesses last quarter?",
  "conversation_id": "conv_abc123",
  "timestamp": "2026-03-16T14:30:00Z",
  "total_duration_ms": 2178,
  "llm_calls": 3,
  "mcp_calls": 1,
  "overall_confidence": 0.94,
  "action": "proceed",
  "steps": [
    {
      "step_name": "intent_classification",
      "step_number": 1,
      "started_at": 1710600600.123,
      "ended_at": 1710600600.410,
      "duration_ms": 287,
      "status": "complete",
      "input_summary": {"query": "What was total billed business..."},
      "output_summary": {
        "intent": "data_query",
        "confidence": 0.97,
        "entities": {"metrics": ["total billed business"], "filters": {"bus_seg": "small businesses"}}
      },
      "decision": "proceed",
      "confidence": 0.97,
      "error": null
    },
    {
      "step_name": "retrieval",
      "step_number": 2,
      "started_at": 1710600600.411,
      "ended_at": 1710600600.553,
      "duration_ms": 142,
      "status": "complete",
      "input_summary": {"entities_count": 3, "entity_types": ["measure", "filter", "time_range"]},
      "output_summary": {"candidate_count": 15, "explore_count": 5, "top_similarity": 0.94},
      "decision": "proceed",
      "confidence": null,
      "error": null
    }
  ],
  "result": {
    "answer": "Total billed business for Small Business...",
    "sql": "SELECT ...",
    "row_count": 1,
    "columns": ["total_billed_business"],
    "follow_ups": ["Break down by card product", "Compare to previous quarter"]
  }
}
```

---

#### GET /api/v1/capabilities

Returns available explores, their descriptions, and system capabilities. The frontend uses this to populate starter query cards and validate what the system can answer.

**Response:**

```json
{
  "version": "1.0.0",
  "explores": [
    {
      "name": "finance_cardmember_360",
      "description": "Card member activity, demographics, portfolio health, segmentation",
      "sample_questions": [
        "How many active cardmembers by generation?",
        "What is total billed business for the OPEN segment?"
      ],
      "measure_count": 12,
      "dimension_count": 28
    }
  ],
  "features": {
    "streaming": true,
    "follow_ups": true,
    "disambiguation": true,
    "filter_resolution": true,
    "confidence_scores": true,
    "sql_transparency": true
  },
  "limits": {
    "max_result_rows": 500,
    "max_conversation_turns": 20,
    "max_query_length": 2000
  }
}
```

---

#### GET /api/v1/health

System health check. Returns component-level status.

**Response:**

```json
{
  "status": "ok",
  "components": {
    "safechain": {"status": "ok", "latency_ms": 45},
    "postgresql": {"status": "ok", "latency_ms": 12},
    "faiss": {"status": "ok", "vectors_loaded": 187},
    "looker_mcp": {"status": "ok", "tools_loaded": 12}
  },
  "version": "1.0.0",
  "uptime_seconds": 3600
}
```

---

#### POST /api/v1/feedback

User feedback on query results. Feeds the learning loop (ADR-008).

**Request:**

```json
{
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "rating": 4,
  "filter_correction": {
    "user_term": "small businesses",
    "correct_value": "OPEN",
    "dimension": "bus_seg"
  },
  "comment": "Correct answer but I expected it broken down by quarter"
}
```

**Response:**

```json
{"status": "logged", "trace_id": "a1b2c3d4-..."}
```

---

## 5. CortexOrchestrator Class Design

### Module: `src/pipeline/orchestrator.py`

```python
"""CortexOrchestrator -- full NL2SQL pipeline with streaming SSE events.

Composition over inheritance: wraps the PoC's AgentOrchestrator,
does NOT subclass it. Phase 1 (pre-processing) and Phase 3 (post-processing)
are owned by CortexOrchestrator. Phase 2 (ReAct execution) delegates
to the PoC's AgentOrchestrator with an augmented prompt.

Key design decisions:
  - AsyncGenerator[SSEEvent] as the primary output contract
  - Every step emits events regardless of success/failure
  - PipelineTrace is assembled incrementally as steps complete
  - Conversation state is per-instance (not global) -- one orchestrator per request
    for stateless horizontal scaling; conversation context passed in via request
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, AsyncGenerator

from safechain.lcel import model
from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore, PipelineResult
from src.retrieval.filters import FilterResolutionResult

logger = logging.getLogger(__name__)


# ── SSE Event ────────────────────────────────────────────────────────

@dataclass
class SSEEvent:
    """A single Server-Sent Event."""
    event: str              # event type: step_start, step_complete, etc.
    data: dict[str, Any]    # JSON-serializable payload

    def to_sse(self) -> str:
        """Serialize to SSE wire format."""
        json_data = json.dumps(self.data, default=str)
        return f"event: {self.event}\ndata: {json_data}\n\n"


# ── Pipeline Trace ───────────────────────────────────────────────────

@dataclass
class StepTrace:
    """Trace of a single pipeline step."""
    step_name: str
    step_number: int
    started_at: float
    ended_at: float = 0.0
    duration_ms: float = 0.0
    status: str = "pending"          # pending | active | complete | error | skipped
    input_summary: dict = field(default_factory=dict)
    output_summary: dict = field(default_factory=dict)
    decision: str = "pending"        # proceed | disambiguate | clarify | fallback | skip
    confidence: float | None = None
    error: str | None = None


@dataclass
class PipelineTrace:
    """Full pipeline trace for one query -- stored for eval and debugging."""
    trace_id: str
    query: str
    conversation_id: str
    timestamp: str                    # ISO 8601
    total_duration_ms: float = 0.0
    llm_calls: int = 0
    mcp_calls: int = 0
    overall_confidence: float = 0.0
    action: str = "pending"           # proceed | disambiguate | clarify | fallback
    steps: list[StepTrace] = field(default_factory=list)
    result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Conversation Store ───────────────────────────────────────────────

@dataclass
class ConversationContext:
    """Context carried across turns in a conversation."""
    conversation_id: str
    history: list[dict]                             # [{role, content}]
    last_retrieval_result: PipelineResult | None = None
    last_explore: str = ""
    last_filters: dict = field(default_factory=dict)
    turn_count: int = 0


class ConversationStore:
    """In-memory conversation store. Replace with Redis for multi-pod."""

    def __init__(self, max_turns: int = 20):
        self._store: dict[str, ConversationContext] = {}
        self._max_turns = max_turns

    def get_or_create(self, conversation_id: str | None) -> ConversationContext:
        if conversation_id and conversation_id in self._store:
            return self._store[conversation_id]
        new_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
        ctx = ConversationContext(conversation_id=new_id, history=[])
        self._store[new_id] = ctx
        return ctx

    def update(self, ctx: ConversationContext, query: str, answer: str) -> None:
        ctx.history.append({"role": "user", "content": query})
        ctx.history.append({"role": "assistant", "content": answer})
        ctx.turn_count += 1
        # Trim to max turns (keep system message + last N*2 messages)
        if len(ctx.history) > self._max_turns * 2:
            ctx.history = ctx.history[-(self._max_turns * 2):]


# ── Orchestrator ─────────────────────────────────────────────────────

class CortexOrchestrator:
    """Full NL2SQL pipeline with SSE streaming.

    Usage:
        orchestrator = CortexOrchestrator(react_agent, conversations)
        async for event in orchestrator.process_query("total spend?", "conv_123"):
            yield event.to_sse()
    """

    TOTAL_STEPS = 7

    def __init__(
        self,
        react_agent,                              # AgentOrchestrator from chat.py
        conversations: ConversationStore,
        classifier_model_idx: str = "3",          # Gemini Flash
        taxonomy_terms: list[str] | None = None,
    ):
        self.react_agent = react_agent
        self.conversations = conversations
        self.classifier_model_idx = classifier_model_idx
        self.taxonomy_terms = taxonomy_terms or []
        self._trace_store: dict[str, PipelineTrace] = {}  # trace_id -> trace

    async def process_query(
        self,
        query: str,
        conversation_id: str | None = None,
        view_mode: str = "engineering",
    ) -> AsyncGenerator[SSEEvent, None]:
        """Main entry point. Streams SSE events as the pipeline executes.

        Yields SSEEvent objects. The caller (FastAPI endpoint) serializes
        them to SSE wire format.
        """
        trace_id = str(uuid.uuid4())
        ctx = self.conversations.get_or_create(conversation_id)
        trace = PipelineTrace(
            trace_id=trace_id,
            query=query,
            conversation_id=ctx.conversation_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        pipeline_start = time.monotonic()
        llm_calls = 0
        mcp_calls = 0

        try:
            # ── PHASE 1: PRE-PROCESSING ──────────────────────────

            # Step 1: Intent Classification + Entity Extraction
            step1_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "intent_classification",
                "step_number": 1,
                "total_steps": self.TOTAL_STEPS,
                "message": "Analyzing your question...",
            })

            classification = await self._classify_intent(query, ctx)
            llm_calls += 1
            step1_duration = (time.monotonic() - step1_start) * 1000

            step1_trace = StepTrace(
                step_name="intent_classification", step_number=1,
                started_at=step1_start, ended_at=time.monotonic(),
                duration_ms=step1_duration, status="complete",
                input_summary={"query": query[:200]},
                output_summary=classification,
                decision="proceed", confidence=classification.get("confidence", 0),
            )
            trace.steps.append(step1_trace)

            yield SSEEvent("step_complete", {
                "step": "intent_classification",
                "step_number": 1,
                "duration_ms": round(step1_duration),
                "message": f"Identified as {classification.get('intent', 'unknown')}",
                "detail": classification,
            })

            # Short-circuit: out of scope
            if classification.get("intent") == "out_of_scope":
                yield SSEEvent("done", {
                    "trace_id": trace_id,
                    "message": "This question is outside what I can answer with your Finance data.",
                    "total_duration_ms": round((time.monotonic() - pipeline_start) * 1000),
                    "conversation_id": ctx.conversation_id,
                })
                return

            # Step 2: Retrieval (vector + graph)
            step2_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "retrieval",
                "step_number": 2,
                "total_steps": self.TOTAL_STEPS,
                "message": "Searching for matching data fields...",
            })

            pipeline_result = retrieve_with_graph_validation(query, top_k=5)
            step2_duration = (time.monotonic() - step2_start) * 1000

            step2_trace = StepTrace(
                step_name="retrieval", step_number=2,
                started_at=step2_start, ended_at=time.monotonic(),
                duration_ms=step2_duration, status="complete",
                input_summary={"entity_count": len(classification.get("entities", {}).get("metrics", []))},
                output_summary={
                    "explore_count": len(pipeline_result.explores),
                    "action": pipeline_result.action,
                    "confidence": pipeline_result.confidence,
                },
                decision=pipeline_result.action,
                confidence=pipeline_result.confidence,
            )
            trace.steps.append(step2_trace)

            yield SSEEvent("step_complete", {
                "step": "retrieval",
                "step_number": 2,
                "duration_ms": round(step2_duration),
                "message": f"Found {len(pipeline_result.explores)} candidate explores",
                "detail": {
                    "candidate_count": len(pipeline_result.explores),
                    "action": pipeline_result.action,
                },
            })

            # Handle clarify / no_match
            if pipeline_result.action in ("clarify", "no_match"):
                yield SSEEvent("clarify", {
                    "step": "retrieval",
                    "message": "I could not find matching data fields. Could you rephrase your question?",
                    "reason": pipeline_result.clarify_reason,
                })
                yield SSEEvent("done", {
                    "trace_id": trace_id,
                    "total_duration_ms": round((time.monotonic() - pipeline_start) * 1000),
                    "conversation_id": ctx.conversation_id,
                })
                return

            # Step 3: Explore Scoring
            step3_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "explore_scoring",
                "step_number": 3,
                "total_steps": self.TOTAL_STEPS,
                "message": "Scoring candidate data sources...",
            })

            top_explore_data = get_top_explore(pipeline_result)
            step3_duration = (time.monotonic() - step3_start) * 1000

            explore_list = []
            for i, exp in enumerate(pipeline_result.explores[:5]):
                explore_list.append({
                    "name": exp.name,
                    "score": exp.score,
                    "confidence": exp.confidence,
                    "coverage": exp.coverage,
                    "matched_entities": exp.supported_entities,
                    "is_winner": i == 0,
                })

            yield SSEEvent("explore_scored", {
                "step": "explore_scoring",
                "explores": explore_list,
                "winner": pipeline_result.explores[0].name if pipeline_result.explores else None,
                "confidence": pipeline_result.confidence,
                "is_near_miss": pipeline_result.explores[0].is_near_miss if pipeline_result.explores else False,
            })

            # Handle disambiguation
            if pipeline_result.action == "disambiguate":
                yield SSEEvent("disambiguate", {
                    "step": "explore_scoring",
                    "message": "I found two equally relevant data sources. Which one matches your question?",
                    "options": explore_list[:2],
                })
                # Stream pauses -- frontend sends selection as follow-up
                return

            step3_trace = StepTrace(
                step_name="explore_scoring", step_number=3,
                started_at=step3_start, ended_at=time.monotonic(),
                duration_ms=step3_duration, status="complete",
                output_summary={
                    "selected_explore": top_explore_data.get("top_explore_name"),
                    "confidence": pipeline_result.confidence,
                },
                decision="proceed",
                confidence=pipeline_result.confidence,
            )
            trace.steps.append(step3_trace)

            yield SSEEvent("step_complete", {
                "step": "explore_scoring",
                "step_number": 3,
                "duration_ms": round(step3_duration),
                "message": f"Selected {top_explore_data.get('top_explore_name')} ({pipeline_result.confidence:.0%} confidence)",
                "detail": top_explore_data,
            })

            # Step 4: Filter Resolution
            step4_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "filter_resolution",
                "step_number": 4,
                "total_steps": self.TOTAL_STEPS,
                "message": "Resolving filter values...",
            })

            filters_data = top_explore_data.get("filters", {})
            unresolved = top_explore_data.get("unresolved_filters", [])
            step4_duration = (time.monotonic() - step4_start) * 1000

            filter_detail = {
                "resolved": filters_data,
                "unresolved": unresolved,
                "filter_count": len(filters_data),
            }
            if pipeline_result.filters:
                filter_detail["resolved_detail"] = [
                    {
                        "field": f.field_name,
                        "user_said": f.original_value,
                        "resolved_to": f.value,
                        "confidence": f.confidence,
                        "pass": f.resolution_pass,
                    }
                    for f in pipeline_result.filters.resolved_filters
                ]
                filter_detail["mandatory_detail"] = [
                    {
                        "field": f.field_name,
                        "value": f.value,
                        "reason": "auto_injected_partition" if f.resolution_pass == 0 else "user",
                    }
                    for f in pipeline_result.filters.mandatory_filters
                ]

            step4_trace = StepTrace(
                step_name="filter_resolution", step_number=4,
                started_at=step4_start, ended_at=time.monotonic(),
                duration_ms=step4_duration, status="complete",
                output_summary=filter_detail,
                decision="proceed",
            )
            trace.steps.append(step4_trace)

            yield SSEEvent("step_complete", {
                "step": "filter_resolution",
                "step_number": 4,
                "duration_ms": round(step4_duration),
                "message": f"Resolved {len(filters_data)} filters",
                "detail": filter_detail,
            })

            # ── PHASE 2: REACT EXECUTION ─────────────────────────

            # Step 5: SQL Generation via Looker MCP
            step5_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "sql_generation",
                "step_number": 5,
                "total_steps": self.TOTAL_STEPS,
                "message": "Generating SQL query...",
            })

            augmented_prompt = self._build_augmented_prompt(
                top_explore_data, filters_data, pipeline_result
            )

            yield SSEEvent("step_progress", {
                "step": "sql_generation",
                "message": "Calling Looker MCP with pre-selected fields...",
                "detail": {
                    "explore": top_explore_data.get("top_explore_name"),
                    "filters": filters_data,
                },
            })

            messages = [
                {"role": "system", "content": augmented_prompt},
                *ctx.history[-10:],  # last 5 turns
                {"role": "user", "content": query},
            ]

            react_result = await self.react_agent.run(messages)
            llm_calls += 1  # at minimum 1 LLM call
            mcp_calls += 1  # at minimum 1 query-sql call
            step5_duration = (time.monotonic() - step5_start) * 1000

            raw_content = react_result.get("content", "")
            sql = self._extract_sql(raw_content)

            if sql:
                yield SSEEvent("sql_generated", {
                    "step": "sql_generation",
                    "sql": sql,
                    "explore": top_explore_data.get("top_explore_name"),
                })

            step5_trace = StepTrace(
                step_name="sql_generation", step_number=5,
                started_at=step5_start, ended_at=time.monotonic(),
                duration_ms=step5_duration, status="complete",
                output_summary={"sql_length": len(sql) if sql else 0},
                decision="proceed",
            )
            trace.steps.append(step5_trace)

            yield SSEEvent("step_complete", {
                "step": "sql_generation",
                "step_number": 5,
                "duration_ms": round(step5_duration),
                "message": "SQL generated and executed",
            })

            # ── PHASE 3: POST-PROCESSING ─────────────────────────

            # Step 6: Results Processing
            step6_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "results_processing",
                "step_number": 6,
                "total_steps": self.TOTAL_STEPS,
                "message": "Processing query results...",
            })

            parsed_results = self._parse_results(raw_content)
            step6_duration = (time.monotonic() - step6_start) * 1000

            yield SSEEvent("results", {
                "step": "results_processing",
                "columns": parsed_results.get("columns", []),
                "rows": parsed_results.get("rows", []),
                "row_count": parsed_results.get("row_count", 0),
                "truncated": parsed_results.get("row_count", 0) > 500,
            })

            step6_trace = StepTrace(
                step_name="results_processing", step_number=6,
                started_at=step6_start, ended_at=time.monotonic(),
                duration_ms=step6_duration, status="complete",
                output_summary={"row_count": parsed_results.get("row_count", 0)},
                decision="proceed",
            )
            trace.steps.append(step6_trace)

            yield SSEEvent("step_complete", {
                "step": "results_processing",
                "step_number": 6,
                "duration_ms": round(step6_duration),
                "message": f"Processed {parsed_results.get('row_count', 0)} rows",
            })

            # Step 7: Response Formatting + Follow-ups
            step7_start = time.monotonic()
            yield SSEEvent("step_start", {
                "step": "response_formatting",
                "step_number": 7,
                "total_steps": self.TOTAL_STEPS,
                "message": "Formatting response...",
            })

            answer = self._extract_answer(raw_content)
            follow_ups = await self._generate_follow_ups(
                query, answer, top_explore_data, ctx
            )
            llm_calls += 1
            step7_duration = (time.monotonic() - step7_start) * 1000

            step7_trace = StepTrace(
                step_name="response_formatting", step_number=7,
                started_at=step7_start, ended_at=time.monotonic(),
                duration_ms=step7_duration, status="complete",
                output_summary={"answer_length": len(answer), "follow_up_count": len(follow_ups)},
                decision="proceed",
            )
            trace.steps.append(step7_trace)

            yield SSEEvent("step_complete", {
                "step": "response_formatting",
                "step_number": 7,
                "duration_ms": round(step7_duration),
                "message": "Response ready",
                "detail": {
                    "answer": answer,
                    "follow_ups": follow_ups,
                },
            })

            yield SSEEvent("follow_ups", {
                "suggestions": follow_ups,
            })

            # ── FINALIZE ─────────────────────────────────────────

            total_duration = (time.monotonic() - pipeline_start) * 1000
            trace.total_duration_ms = total_duration
            trace.llm_calls = llm_calls
            trace.mcp_calls = mcp_calls
            trace.overall_confidence = pipeline_result.confidence
            trace.action = "proceed"
            trace.result = {
                "answer": answer,
                "sql": sql,
                "row_count": parsed_results.get("row_count", 0),
                "follow_ups": follow_ups,
            }

            # Store trace for GET /trace/{id}
            self._trace_store[trace_id] = trace

            # Update conversation context
            ctx.last_retrieval_result = pipeline_result
            ctx.last_explore = top_explore_data.get("top_explore_name", "")
            ctx.last_filters = filters_data
            self.conversations.update(ctx, query, answer)

            yield SSEEvent("done", {
                "trace_id": trace_id,
                "total_duration_ms": round(total_duration),
                "llm_calls": llm_calls,
                "mcp_calls": mcp_calls,
                "overall_confidence": pipeline_result.confidence,
                "conversation_id": ctx.conversation_id,
            })

        except Exception as e:
            logger.exception("Pipeline error for query: %s", query)
            yield SSEEvent("error", {
                "step": "pipeline",
                "message": str(e),
                "recoverable": False,
                "trace_id": trace_id,
            })
            yield SSEEvent("done", {
                "trace_id": trace_id,
                "total_duration_ms": round((time.monotonic() - pipeline_start) * 1000),
                "conversation_id": ctx.conversation_id,
                "error": str(e),
            })

    def get_trace(self, trace_id: str) -> PipelineTrace | None:
        """Retrieve a stored trace by ID."""
        return self._trace_store.get(trace_id)

    # ── Private Methods ──────────────────────────────────────────

    async def _classify_intent(
        self, query: str, ctx: ConversationContext
    ) -> dict:
        """Classify intent and extract entities using Gemini Flash."""
        # Implementation calls model(self.classifier_model_idx).invoke()
        # with CLASSIFY_AND_EXTRACT_PROMPT from prompts.py
        # Returns parsed JSON dict
        ...

    def _build_augmented_prompt(
        self, top_explore: dict, filters: dict, pipeline_result: PipelineResult
    ) -> str:
        """Build the augmented system prompt for the ReAct agent."""
        # Uses AUGMENTED_PROMPT_TEMPLATE from prompts.py
        # Injects model, explore, measures, dimensions, filters, fewshot match
        ...

    def _extract_sql(self, raw_content: str) -> str:
        """Extract SQL from the raw LLM response."""
        # Parses SQL from markdown code blocks or raw text
        ...

    def _parse_results(self, raw_content: str) -> dict:
        """Parse query results from LLM response into structured data."""
        # Extracts columns, rows, row_count from the LLM's formatted response
        ...

    def _extract_answer(self, raw_content: str) -> str:
        """Extract the natural language answer from LLM response."""
        ...

    async def _generate_follow_ups(
        self, query: str, answer: str, explore_data: dict,
        ctx: ConversationContext
    ) -> list[str]:
        """Generate 2-3 follow-up suggestions using Gemini Flash."""
        # 1 LLM call with context about available dimensions/measures
        ...
```

### Key Design Decisions

**1. AsyncGenerator, not callback.** The `process_query` method is an async generator that yields SSEEvent objects. This is the natural fit for SSE streaming -- FastAPI's `StreamingResponse` consumes the generator directly. No callback registration, no event bus, no pubsub. The control flow IS the event stream.

**2. One orchestrator instance per server, not per request.** The CortexOrchestrator holds the ConversationStore and trace store. It is created once at server startup. Individual queries are isolated by `conversation_id`. This avoids re-initializing SafeChain connections per request.

**3. Conversation context passed by reference.** The ConversationStore is in-memory for the demo. For multi-pod production, replace with Redis or PostgreSQL-backed sessions. The interface stays the same.

**4. Trace stored in-memory, flushed to PostgreSQL.** For the demo, traces live in a dict. Post-demo, add a background task that flushes traces to `query_logs` table in PostgreSQL for eval.

---

## 6. Conversation Management

### How Conversations Work

Every query either starts a new conversation or continues an existing one.

```
First query:     POST /api/v1/query { query: "...", conversation_id: null }
                 Response includes: conversation_id: "conv_abc123"

Follow-up:       POST /api/v1/followup { query: "break down by...", conversation_id: "conv_abc123" }
                 Orchestrator loads ConversationContext for conv_abc123
```

### ConversationContext Schema

| Field | Type | Purpose |
|-------|------|---------|
| `conversation_id` | string | Unique ID for the conversation |
| `history` | list[dict] | Message history: `[{role: "user"/"assistant", content: "..."}]` |
| `last_retrieval_result` | PipelineResult | Full retrieval output from the last query |
| `last_explore` | string | Name of the last selected explore |
| `last_filters` | dict | Last resolved filters (for follow-up modifications) |
| `turn_count` | int | Number of completed turns |

### Follow-up Resolution Logic

When the intent classifier detects `intent == "follow_up"`:

1. **Additive modification** ("break down by card product"): Reuse `last_retrieval_result`, add the new dimension to the field list, keep existing filters, re-run Phase 2.

2. **Filter modification** ("show only Platinum"): Reuse `last_retrieval_result`, add/replace the filter, re-run Phase 2.

3. **New question** ("how about travel sales?"): Run the full pipeline from Phase 1. The conversation history provides context but the retrieval is fresh.

The orchestrator determines which case applies by checking:
- Does the follow-up reference a dimension/measure not in the previous explore? -> New question
- Does the follow-up add a filter, sort, or limit? -> Additive modification
- Does the follow-up change the metric? -> New question

### Session Management

| Concern | Implementation |
|---------|---------------|
| Session creation | New `conversation_id` generated on first query if none provided |
| Session TTL | 30 minutes of inactivity (demo). Configurable. |
| History limit | Last 20 messages (10 turns). Older messages dropped. |
| Multi-pod | In-memory for demo. Redis/Postgres for production. |
| Concurrent sessions | Supported -- each conversation_id is independent |

---

## 7. PipelineTrace Schema

### Purpose

The PipelineTrace is the single source of truth for what happened during a query. It serves three audiences:

1. **Frontend Engineering View** -- displays the trace as the step-by-step pipeline visualization
2. **Evaluation** -- offline analysis of accuracy, latency, and failure modes across queries
3. **Debugging** -- when a query returns wrong results, the trace shows exactly where the pipeline went wrong

### Storage

| Phase | Storage | Retention |
|-------|---------|-----------|
| Demo | In-memory dict (CortexOrchestrator._trace_store) | Until server restart |
| Post-demo | PostgreSQL `query_logs` table | 90 days |
| Eval | Exported to JSON Lines for offline analysis | Permanent |

### Full Schema

```python
@dataclass
class StepTrace:
    step_name: str          # Enum: intent_classification | retrieval | explore_scoring |
                            #        filter_resolution | sql_generation |
                            #        results_processing | response_formatting
    step_number: int        # 1-7
    started_at: float       # time.monotonic() -- for duration calculation
    ended_at: float         # time.monotonic()
    duration_ms: float      # (ended_at - started_at) * 1000
    status: str             # pending | active | complete | error | skipped
    input_summary: dict     # Truncated inputs (no full embeddings, no raw SQL results)
    output_summary: dict    # Truncated outputs (key decisions, scores, counts)
    decision: str           # proceed | disambiguate | clarify | fallback | skip
    confidence: float | None  # Step-specific confidence (not all steps produce one)
    error: str | None       # Error message if status == "error"


@dataclass
class PipelineTrace:
    trace_id: str               # UUIDv4
    query: str                  # Original user query
    conversation_id: str        # Which conversation this belongs to
    timestamp: str              # ISO 8601 UTC
    total_duration_ms: float
    llm_calls: int              # Total Gemini calls (classification + ReAct + follow-ups)
    mcp_calls: int              # Total MCP tool calls (query-sql, get-dimensions, etc.)
    overall_confidence: float   # From explore scoring (0.0 - 1.0)
    action: str                 # proceed | disambiguate | clarify | fallback
    steps: list[StepTrace]      # Ordered list of 7 steps
    result: dict                # {answer, sql, row_count, columns, follow_ups}
```

### Trace Replay

To replay a trace for debugging:

1. Fetch the trace via `GET /api/v1/trace/{trace_id}`
2. Each step's `input_summary` contains enough information to re-run that step in isolation
3. The `output_summary` is the expected output -- compare against actual re-run output
4. This enables targeted debugging: "Step 3 scored the wrong explore. Here's what it saw, here's what it chose."

### PostgreSQL Schema (Post-Demo)

```sql
CREATE TABLE query_logs (
    trace_id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_duration_ms FLOAT,
    llm_calls INT,
    mcp_calls INT,
    overall_confidence FLOAT,
    action TEXT,
    steps JSONB NOT NULL,
    result JSONB,
    session_id TEXT,
    user_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_query_logs_conversation ON query_logs(conversation_id);
CREATE INDEX idx_query_logs_timestamp ON query_logs(timestamp);
CREATE INDEX idx_query_logs_confidence ON query_logs(overall_confidence);
```

---

## 8. Error States

### Error Handling Philosophy

Every error is classified on two axes:
- **Recoverable vs. Fatal** -- Can the pipeline continue?
- **User-facing vs. Internal** -- Should the user see the raw error?

The pipeline never crashes silently. Every failure emits an SSE `error` event with enough information for the frontend to render a meaningful message and for the trace to capture the failure point.

### Error Table

| Step | Failure Mode | Recoverable? | Pipeline Behavior | User Message |
|------|-------------|-------------|-------------------|-------------|
| Intent Classification | LLM timeout | Yes | Skip to Phase 2 (raw ReAct, no augmentation) | "Analyzing your question (fallback mode)..." |
| Intent Classification | Unparseable JSON | Yes | Skip to Phase 2 | Same as above |
| Intent Classification | Low confidence (<0.7) | Yes | Skip to Phase 2 | Same as above |
| Retrieval | pgvector unreachable | Yes | Skip to Phase 2 | "Searching data fields (fallback mode)..." |
| Retrieval | AGE unreachable | Partial | Vector-only scoring (degraded accuracy) | "Using reduced search..." |
| Retrieval | No matches found | Terminal | Return clarify event | "I could not find relevant data fields. Could you rephrase?" |
| Explore Scoring | Near-miss (ambiguous) | Pause | Return disambiguate event | "Which data source did you mean?" |
| Filter Resolution | Value not found | Yes | Pass through as-is (low confidence) | Filter shown with warning badge in UI |
| SQL Generation | LLM timeout | No | Return error | "Query generation timed out. Please try again." |
| SQL Generation | MCP tool error | No | Return error with raw message | "Looker returned an error: {message}" |
| SQL Generation | BigQuery error | No | Return error | "Query execution failed: {message}" |
| Results Processing | Parse failure | Yes | Return raw LLM text as answer | Answer shown without structured table |
| Response Formatting | LLM timeout | Yes | Use raw answer, skip follow-ups | Answer shown, no follow-up chips |
| SafeChain | CIBIS auth failure | Fatal | Return 503 | "System authentication error. Contact support." |
| SafeChain | Model endpoint down | Fatal | Return 503 | "AI service temporarily unavailable." |

### Error SSE Event

```
event: error
data: {
  "step": "sql_generation",
  "error_code": "mcp_tool_error",
  "message": "Looker returned: Invalid dimension 'foo_bar' for explore 'finance_cardmember_360'",
  "recoverable": false,
  "suggestion": "Try rephrasing your question or ask about available fields.",
  "trace_id": "a1b2c3d4-..."
}
```

### Fallback Cascade

The system degrades gracefully through three levels:

```
Level 0: Full pipeline (Phase 1 + 2 + 3)
  |  If Phase 1 fails:
  v
Level 1: Augmented ReAct (classification succeeded, retrieval failed)
  |  Use extracted entities in prompt, but let LLM discover explore/fields
  |  If classification also failed:
  v
Level 2: Raw ReAct (PoC behavior)
  |  No augmentation. LLM chains get-models -> get-explores -> query-sql
  |  Slower (~4s) and less accurate (~50%), but functional
  |  If SafeChain is down:
  v
Level 3: Service unavailable (503)
  |  Nothing works. Return error.
```

Each fallback level is reflected in the trace (`action: "fallback"`) and in the SSE events (`step_complete` with `status: "fallback"`).

---

## 9. What to Showcase in the Demo

### Audience-Specific "Wow" Moments

#### For Jeff / Kalyan (Leadership)

**The "magic" moment:** User types a plain English question, the system streams progress in real time (like watching Gemini think), and within 2-3 seconds shows a correct answer with data. No SQL knowledge required.

What to highlight:
- "Ask anything about your Finance data" -- broad capability, not a narrow tool
- Follow-up questions: "Break down by card product" -- conversational, not transactional
- Confidence scores visible: "94% confidence" -- the system tells you when it is uncertain
- The system explains itself: "I selected finance_cardmember_360 because it best matches your question about billed business by segment"
- Demo script should start with a simple question, then use follow-ups to go deeper, showing the conversational flow

**What Jeff needs to see:** This works. It is fast. It is trustworthy. It scales to more BUs.

**What Kalyan needs to see:** The engineering depth is real. This is not a wrapper around ChatGPT. The pipeline is explainable, evaluatable, and production-grade.

#### For Sulabh / Ashok (Architecture Board)

**The engineering depth:**
- Toggle to Engineering View -- show every pipeline step with timing, scores, and decisions
- Show the trace for a query -- per-step input/output, latency breakdown
- Show disambiguation: ask an ambiguous question, watch the system detect the near-miss and ask the user to choose
- Show filter resolution: "small businesses" -> "OPEN" (deterministic, not LLM-dependent)
- Show partition filter injection: mandatory `partition_date` auto-injected for cost control

What to highlight:
- 3 LLM calls total (down from 5-6 in the PoC), with the rest being deterministic
- Hybrid retrieval (vector + graph) providing structural validation, not just vibes
- Filter resolution that is deterministic and auditable, not LLM-hallucinated
- Cost control: partition filters always injected, preventing full-table scans
- Graceful degradation: if retrieval fails, falls back to PoC behavior

#### For the Demo Script

**Query sequence:**

1. **Simple metric:** "What is the total billed business for the OPEN segment?"
   - Shows full pipeline, clean result, high confidence
   - Engineering View: all steps green, 94% confidence

2. **Follow-up with breakdown:** "Break down by card product"
   - Shows conversation memory, field addition
   - Result table with multiple rows

3. **Time filter:** "Show me the trend for the last 4 quarters"
   - Shows time normalization ("last 4 quarters" -> Looker syntax)
   - Ideally shows a chart (if Ayush implements it)

4. **Ambiguous query:** "How many customers do we have?"
   - Might trigger disambiguation between cardmember_360 and card_issuance
   - Shows the system asking for clarification, not guessing

5. **Filter with synonym:** "How many Millennial customers are Gold cardholders?"
   - "Millennial" -> generation: "Millennial"
   - "Gold" -> card_prod_id: "GOLD"
   - Shows multi-filter resolution

6. **Out of scope:** "What's the weather in New York?"
   - Shows graceful refusal, not hallucination

### UX Polish Differentiators

These are the details that make this feel different from every other NL2SQL demo:

1. **Streaming steps, not a spinner.** The user sees the system working -- "Analyzing...", "Searching 15 fields...", "Selected finance_cardmember_360...", "Generating SQL...". This builds trust and reduces perceived latency.

2. **Confidence is always visible.** Not hidden behind a developer toggle. The user sees "94% confidence" and knows when to double-check the answer.

3. **SQL is always accessible.** Collapsed by default (analysts don't need it), but one click reveals the exact SQL that was run. Full transparency.

4. **Follow-up suggestions are contextual.** Not generic ("tell me more") but specific to the data ("Break down by card product", "Compare to last quarter"). Generated from the explore's available dimensions.

5. **Disambiguation is clean.** Not "ERROR: ambiguous query". Instead: "I found two data sources that match. Which one did you mean?" with clear descriptions of each option.

---

## 10. Implementation File Map

### New Files to Create

```
cortex/src/
├── pipeline/
│   ├── orchestrator.py      # CortexOrchestrator (this design)      ~400 lines
│   ├── trace.py             # SSEEvent, StepTrace, PipelineTrace    ~120 lines
│   ├── prompts.py           # CLASSIFY_PROMPT, AUGMENTED_PROMPT     ~100 lines
│   ├── conversations.py     # ConversationStore, ConversationContext ~80 lines
│   └── errors.py            # CortexError hierarchy                  ~50 lines
│
├── api/
│   ├── server.py            # Rewrite: add SSE endpoints, v1 routes ~200 lines
│   └── models.py            # Pydantic models for request/response   ~80 lines
```

### Files to Modify

```
cortex/src/api/server.py     # Add /api/v1/query (SSE), /followup, /trace, /capabilities
cortex/access_llm/chat.py    # No changes (PoC stays untouched, composed into)
cortex/src/retrieval/*       # No changes (used as-is by orchestrator)
```

### Total New Code

| File | Lines | Priority | Owner |
|------|-------|----------|-------|
| `pipeline/orchestrator.py` | ~400 | P0 | Saheb |
| `pipeline/trace.py` | ~120 | P0 | Saheb |
| `pipeline/prompts.py` | ~100 | P0 | Saheb |
| `pipeline/conversations.py` | ~80 | P0 | Saheb |
| `api/server.py` (rewrite) | ~200 | P0 | Saheb + Ayush |
| `api/models.py` | ~80 | P1 | Saheb |
| `pipeline/errors.py` | ~50 | P1 | Saheb |

**Total: ~1,030 lines of new code.**

### Implementation Order

1. `trace.py` -- data structures first, no dependencies
2. `conversations.py` -- conversation management, no dependencies
3. `prompts.py` -- prompt templates, no dependencies
4. `orchestrator.py` -- the main class, depends on 1-3 + existing retrieval pipeline
5. `api/server.py` -- SSE endpoints, depends on 4
6. `api/models.py` -- Pydantic request/response models
7. `errors.py` -- error hierarchy

Ayush can start on the frontend SSE consumer immediately using the event specification in Section 3. The API contract is stable -- the backend and frontend can be developed in parallel.

---

## 11. Frontend Integration Guide (For Ayush)

### SSE Connection

```typescript
// Connect to SSE stream
const eventSource = new EventSource('/api/v1/query', {
  method: 'POST',  // Note: native EventSource is GET-only.
  // Use fetch + ReadableStream instead:
});

// Recommended: use fetch with ReadableStream for POST support
async function streamQuery(query: string, conversationId?: string) {
  const response = await fetch('/api/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, conversation_id: conversationId }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop()!; // Keep incomplete event in buffer

    for (const block of lines) {
      if (!block.trim()) continue;
      const eventMatch = block.match(/^event: (.+)$/m);
      const dataMatch = block.match(/^data: (.+)$/m);
      if (eventMatch && dataMatch) {
        const eventType = eventMatch[1];
        const data = JSON.parse(dataMatch[1]);
        handleEvent(eventType, data);
      }
    }
  }
}
```

### Event Handling Map

```typescript
function handleEvent(type: string, data: any) {
  switch (type) {
    case 'step_start':
      // Set step to "active" state (blue spinner)
      // data.step_number tells you which step (1-7)
      // data.message is the user-facing text
      break;

    case 'step_progress':
      // Update the active step's sub-text
      break;

    case 'step_complete':
      // Set step to "complete" state (green check)
      // data.duration_ms for the timing badge
      // data.detail for the expandable content
      break;

    case 'explore_scored':
      // Special: render the explore comparison in Step 3
      // data.explores is the ranked list
      // data.winner is the selected explore
      break;

    case 'sql_generated':
      // Store the SQL for the code block
      break;

    case 'results':
      // Render the data table
      // data.columns and data.rows
      break;

    case 'follow_ups':
      // Render the follow-up suggestion chips
      break;

    case 'disambiguate':
      // Show the disambiguation modal
      // data.options is the list of explores to choose from
      break;

    case 'clarify':
      // Show clarification request inline
      break;

    case 'error':
      // Show error state on the current step
      // data.recoverable determines if we show a retry button
      break;

    case 'done':
      // Pipeline complete. Store trace_id and conversation_id.
      // data.conversation_id is needed for follow-up queries.
      break;
  }
}
```

### State Machine (Frontend)

The Engineering View pipeline panel has a state machine per step:

```
pending -> active -> complete
                  -> error
                  -> warning (near-miss)
                  -> skipped (fallback)
```

The chat panel has a separate state:
```
idle -> processing -> complete
                   -> error
                   -> disambiguating (waiting for user choice)
```

---

## 12. Latency Budget (Revised)

```
+-------------------------------+----------+------------------------+
| Phase                         | Budget   | Notes                  |
+-------------------------------+----------+------------------------+
| Intent + Entity (1 LLM)      | 400ms    | Gemini Flash via SC    |
| Vector Search (pgvector)      | 80ms     | HNSW index, 1024-dim   |
| Graph Validation (AGE)        | 50ms     | 2 Cypher queries       |
| Explore Scoring               | 5ms      | Deterministic math     |
| Filter Resolution             | 15ms     | Hash + fuzzy + synonym |
| Prompt Assembly               | 5ms      | String formatting      |
| ReAct: LLM -> query-sql      | 1200ms   | 1 Gemini + 1 MCP      |
| Results Processing            | 5ms      | JSON parsing           |
| Follow-up Generation (1 LLM) | 400ms    | Gemini Flash           |
| SSE serialization overhead    | 20ms     | Per-event JSON encode  |
+-------------------------------+----------+------------------------+
| TOTAL P50                     | ~2200ms  | Well within 4s budget  |
| TOTAL P95 (retries/network)   | ~3200ms  | 800ms headroom         |
+-------------------------------+----------+------------------------+

Comparison:
  PoC (no retrieval):  5-6 LLM calls = ~3500ms + lower accuracy
  Cortex (this):       3 LLM calls   = ~2200ms + 90%+ accuracy
  Savings: ~1300ms (37% faster) + dramatically higher accuracy
```

---

## 13. Open Questions

| # | Question | Impact | Decision Needed By |
|---|----------|--------|-------------------|
| 1 | Should follow-up generation be a separate LLM call or part of the ReAct response? | Latency: separate adds ~400ms but gives better control | Before implementation |
| 2 | How do we handle the `query-sql` MCP tool returning Markdown-formatted tables vs. raw JSON? | Parsing strategy in `_parse_results` | During implementation |
| 3 | Should the disambiguation modal auto-select if the user does not respond within 5s? | UX decision | Before demo |
| 4 | Redis vs. PostgreSQL for conversation store in production? | Infrastructure | Post-demo |
| 5 | Should traces be stored for every query or only for queries with feedback? | Storage cost vs. eval coverage | Post-demo |
| 6 | Is there a SafeChain API for streaming LLM responses (token-by-token)? | Would enable typewriter effect for the answer | Verify with Ravi J |
| 7 | Should the `/query` endpoint return the full SSE stream even in `analyst` mode, with the frontend filtering, or should the backend suppress events? | Bandwidth vs. frontend complexity | Before implementation (recommendation: backend suppresses) |

---

## 14. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| SQL injection via user query | Looker MCP generates SQL; user input never touches SQL directly |
| PII in query results | Looker model-level access controls; Cortex does not bypass Looker permissions |
| Prompt injection | Classification prompt uses structured output (JSON); augmented prompt constrains LLM to pre-selected fields |
| Credential exposure | SafeChain CIBIS handles auth; no credentials in code or env vars exposed to frontend |
| Unbounded BQ cost | Mandatory partition filter injection; row limit (500); Looker query limits apply |
| Conversation history exfiltration | In-memory store with 30-min TTL; no persistence of raw conversation data beyond session |

---

## 15. Deployment (Demo)

```
Development machine (corp laptop):
  - uvicorn src.api.server:app --host 0.0.0.0 --port 8080
  - MCP Toolbox sidecar: ./toolbox --tools-file config/tools.yaml --port 5000
  - PostgreSQL: existing instance (pgvector + AGE)
  - Frontend: npm run dev (Vite, port 3000, proxies to :8080)

Demo day:
  - Same setup, shared screen
  - Pre-warm: run 2-3 queries before demo to warm SafeChain connection and HNSW index
  - Fallback: pre-recorded video of the pipeline in action (insurance)
```

Post-demo GKE deployment is specified in the [agentic orchestration design doc](agentic-orchestration-design.md) Section 10.
