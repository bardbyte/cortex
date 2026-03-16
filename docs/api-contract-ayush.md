# Cortex API Contract — Frontend Integration Guide

**For:** Ayush | **From:** Saheb | **Date:** March 16, 2026
**Status:** Stable — build against this. Backend is implemented.

---

## Quick Start

```
Base URL: http://localhost:8080
Main endpoint: POST /api/v1/query (SSE stream)
```

The API returns Server-Sent Events (SSE). Your React frontend opens a streaming connection, receives events as pipeline steps complete, and renders them in real time.

---

## Endpoints

### 1. POST /api/v1/query — Main pipeline (SSE)

**Request:**
```json
{
  "query": "Total billed business by generation last quarter",
  "conversation_id": null,
  "session_id": "sess_abc123",
  "view_mode": "engineering"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `query` | string | yes | Natural language question |
| `conversation_id` | string\|null | no | null = new conversation. Set to value from previous `done` event for follow-ups |
| `session_id` | string | no | Browser session ID for grouping |
| `view_mode` | `"engineering"` \| `"analyst"` | no | Default: `"engineering"`. Controls event verbosity |

**Response:** `Content-Type: text/event-stream`

### 2. POST /api/v1/followup — Follow-up question (SSE)

```json
{
  "query": "Break that down by card product",
  "conversation_id": "conv_abc123"
}
```

Same SSE stream as `/query`. `conversation_id` is required.

### 3. GET /api/v1/trace/{trace_id} — Get pipeline trace (JSON)

Returns the full decision trace for a completed query. Use in the Engineering View's "inspect" panel.

### 4. GET /api/v1/capabilities — Explore catalog (JSON)

```json
{
  "version": "1.0.0",
  "explores": [
    {"name": "finance_cardmember_360", "description": "Card member activity..."}
  ],
  "features": {"streaming": true, "follow_ups": true, "disambiguation": true},
  "limits": {"max_result_rows": 500, "max_conversation_turns": 20}
}
```

Use this to populate starter query cards on first load.

### 5. POST /api/v1/feedback — User feedback (JSON)

```json
{"trace_id": "uuid", "rating": 4, "comment": "optional"}
```

### 6. GET /api/v1/health — System health (JSON)

---

## SSE Event Types — The Complete List

Every event has this wire format:
```
event: <event_type>
data: <single-line JSON>

```

### Pipeline Step Events (always emitted)

| Event | When | Key Fields |
|-------|------|------------|
| `step_start` | Step begins | `step`, `step_number`, `total_steps`, `message` |
| `step_progress` | Mid-step update | `step`, `message`, `detail` |
| `step_complete` | Step finished | `step`, `step_number`, `duration_ms`, `message`, `detail` |

### Special Events

| Event | When | Key Fields |
|-------|------|------------|
| `explore_scored` | After scoring | `explores[]`, `winner`, `confidence`, `is_near_miss` |
| `sql_generated` | SQL ready | `sql`, `explore`, `model` |
| `results` | Data ready | `columns[]`, `rows[]`, `row_count`, `truncated` |
| `follow_ups` | Suggestions ready | `suggestions[]` |
| `done` | Pipeline complete | `trace_id`, `total_duration_ms`, `conversation_id`, `overall_confidence` |

### Branching Events (pipeline pauses or terminates)

| Event | When | What to Do |
|-------|------|------------|
| `disambiguate` | Two explores too close | Show modal with `options[]`. User picks one. Send as follow-up. |
| `clarify` | Can't understand query | Show message + input for rephrasing |
| `error` | Something broke | Show error message. Check `recoverable` field. |

---

## The 7 Pipeline Steps

```
[1] Intent Classification  →  "Analyzing your question..."
[2] Retrieval               →  "Searching for matching data fields..."
[3] Explore Scoring         →  "Scoring candidate data sources..."
[4] Filter Resolution       →  "Resolving filter values..."
[5] SQL Generation          →  "Generating SQL query..."
[6] Results Processing      →  "Processing query results..."
[7] Response Formatting     →  "Formatting response..."
```

Each step emits `step_start` → (optional `step_progress`) → `step_complete`.

---

## TypeScript Integration Code

```typescript
// ── Types ──

interface SSEEventData {
  step?: string;
  step_number?: number;
  total_steps?: number;
  duration_ms?: number;
  message?: string;
  detail?: Record<string, unknown>;

  // explore_scored
  explores?: Array<{
    name: string;
    score: number;
    confidence: number;
    coverage: number;
    matched_entities: string[];
    is_winner: boolean;
  }>;
  winner?: string;
  confidence?: number;
  is_near_miss?: boolean;

  // sql_generated
  sql?: string;
  explore?: string;
  model?: string;

  // results
  columns?: Array<{ name: string; type: string; label: string }>;
  rows?: Record<string, unknown>[];
  row_count?: number;
  truncated?: boolean;

  // follow_ups
  suggestions?: string[];

  // disambiguate
  options?: Array<{
    explore: string;
    description: string;
    confidence: number;
  }>;

  // done
  trace_id?: string;
  total_duration_ms?: number;
  overall_confidence?: number;
  conversation_id?: string;

  // error
  recoverable?: boolean;
  error?: string;
}

// ── SSE Consumer ──
// NOTE: Can't use native EventSource because it only supports GET.
// Use fetch + ReadableStream for POST requests.

async function queryPipeline(
  query: string,
  conversationId: string | null,
  onEvent: (eventType: string, data: SSEEventData) => void,
): Promise<void> {
  const response = await fetch('/api/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      conversation_id: conversationId,
      view_mode: 'engineering',
    }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    while (buffer.includes('\n\n')) {
      const [eventBlock, rest] = buffer.split('\n\n', 2) as [string, string];
      buffer = rest;

      if (!eventBlock.trim()) continue;

      let eventType = '';
      let eventData: SSEEventData = {};

      for (const line of eventBlock.split('\n')) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7);
        } else if (line.startsWith('data: ')) {
          eventData = JSON.parse(line.slice(6));
        }
      }

      if (eventType) {
        onEvent(eventType, eventData);
      }
    }
  }
}

// ── Usage Example ──

async function handleQuery(query: string) {
  let conversationId: string | null = null;

  await queryPipeline(query, null, (eventType, data) => {
    switch (eventType) {
      case 'step_start':
        // Show step indicator: "Step 1/7: Analyzing your question..."
        updateStepIndicator(data.step_number!, data.total_steps!, data.message!);
        break;

      case 'step_complete':
        // Mark step as done, show duration
        completeStep(data.step_number!, data.duration_ms!);
        break;

      case 'explore_scored':
        // Engineering View: show scored explores table
        renderExploreScores(data.explores!);
        break;

      case 'sql_generated':
        // Engineering View: show SQL with syntax highlighting
        renderSQL(data.sql!);
        break;

      case 'results':
        // Render data table
        renderDataTable(data.columns!, data.rows!, data.truncated);
        break;

      case 'follow_ups':
        // Show follow-up suggestion chips
        renderFollowUpChips(data.suggestions!);
        break;

      case 'disambiguate':
        // Show modal: "Which data source?"
        showDisambiguationModal(data.message!, data.options!);
        break;

      case 'clarify':
        // Show: "Could you rephrase?"
        showClarification(data.message!);
        break;

      case 'done':
        conversationId = data.conversation_id!;
        showConfidenceBadge(data.overall_confidence!);
        break;

      case 'error':
        showError(data.message!, data.recoverable);
        break;
    }
  });
}
```

---

## Happy Path Event Sequence

Query: "Total billed business for small businesses last quarter"

```
event: step_start       → {step: "intent_classification", step_number: 1, message: "Analyzing..."}
event: step_complete    → {step: "intent_classification", duration_ms: 287, detail: {intent: "data_query"}}
event: step_start       → {step: "retrieval", step_number: 2}
event: step_progress    → {step: "retrieval", message: "Found 5 candidate explores"}
event: step_complete    → {step: "retrieval", duration_ms: 350}
event: step_start       → {step: "explore_scoring", step_number: 3}
event: explore_scored   → {winner: "finance_cardmember_360", confidence: 0.94, explores: [...]}
event: step_complete    → {step: "explore_scoring", duration_ms: 3}
event: step_start       → {step: "filter_resolution", step_number: 4}
event: step_complete    → {step: "filter_resolution", detail: {resolved: {bus_seg: "OPEN", ...}}}
event: step_start       → {step: "sql_generation", step_number: 5}
event: step_progress    → {step: "sql_generation", message: "Calling Looker MCP..."}
event: sql_generated    → {sql: "SELECT ...", explore: "finance_cardmember_360"}
event: step_complete    → {step: "sql_generation", duration_ms: 1340}
event: step_start       → {step: "results_processing", step_number: 6}
event: results          → {columns: [...], rows: [...], row_count: 1}
event: step_complete    → {step: "results_processing", duration_ms: 3}
event: step_start       → {step: "response_formatting", step_number: 7}
event: step_complete    → {detail: {answer: "Total billed business...", follow_ups: [...]}}
event: follow_ups       → {suggestions: ["Break down by card product", ...]}
event: done             → {trace_id: "uuid", total_duration_ms: 2178, conversation_id: "conv_abc123"}
```

---

## Disambiguation Flow

When two explores score too close:
```
event: step_start       → {step: "explore_scoring"}
event: explore_scored   → {is_near_miss: true, ...}
event: disambiguate     → {
  message: "I found two equally relevant data sources...",
  options: [
    {explore: "finance_cardmember_360", description: "...", confidence: 0.89},
    {explore: "finance_merchant_profitability", description: "...", confidence: 0.86}
  ]
}
event: done             → {action: "disambiguate"}
```

**Frontend action:** Show a modal with the two options. When user picks one, send:
```json
POST /api/v1/followup
{
  "query": "Use finance_cardmember_360 for: <original query>",
  "conversation_id": "<from done event>"
}
```

---

## Error States

| Error | Frontend Action |
|-------|----------------|
| `{recoverable: true}` | Show error inline with "Retry" button |
| `{recoverable: false}` | Show error, hide step indicators |
| HTTP 400 | Show validation error |
| HTTP 503 | Show "System unavailable, try again later" |

---

## Key Numbers for UI

| Metric | Value |
|--------|-------|
| Max rows returned | 500 |
| Max conversation turns | 20 |
| Max query length | 2,000 chars |
| Typical E2E latency (Phase 1 only) | ~500ms |
| Typical E2E latency (full pipeline) | ~2-3 seconds |
| Confidence threshold for "proceed" | ≥ 0.6 |
| Pipeline steps | 7 |
