#!/usr/bin/env python3
"""Local test script for the Cortex orchestrator + SSE API.

Tests three layers:
  1. Unit: SSEEvent serialization, ConversationStore, PipelineTrace
  2. Integration: Full pipeline via retrieve_with_graph_validation (existing)
  3. API: SSE streaming endpoint via httpx (requires server running)

Usage:
  # Unit + Integration tests (no server needed):
  python scripts/test_orchestrator_local.py

  # Full test including API endpoints (start server first):
  uvicorn src.api.server:app --host 0.0.0.0 --port 8080 &
  python scripts/test_orchestrator_local.py --with-api

  # Just API tests:
  python scripts/test_orchestrator_local.py --api-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ── Add project root to path ──
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ════════════════════════════════════════════════════════════════════════
# LAYER 1: Unit Tests (no external deps)
# ════════════════════════════════════════════════════════════════════════

def test_sse_event_serialization():
    """SSEEvent.to_sse() must produce valid SSE wire format."""
    from src.pipeline.orchestrator import SSEEvent

    event = SSEEvent("step_start", {
        "step": "intent_classification",
        "step_number": 1,
        "message": "Analyzing...",
    })
    wire = event.to_sse()

    assert wire.startswith("event: step_start\n"), f"Bad event line: {wire!r}"
    assert "data: " in wire, f"Missing data line: {wire!r}"
    assert wire.endswith("\n\n"), f"Must end with double newline: {wire!r}"

    # Data must be valid single-line JSON
    data_line = wire.split("data: ")[1].split("\n")[0]
    parsed = json.loads(data_line)
    assert parsed["step"] == "intent_classification"
    assert parsed["step_number"] == 1

    print("  [PASS] SSEEvent serialization")


def test_sse_event_special_chars():
    """SSEEvent handles special characters (newlines, unicode) in data."""
    from src.pipeline.orchestrator import SSEEvent

    event = SSEEvent("step_complete", {
        "message": "Found 'Millennial' → resolved",
        "detail": {"sql": "SELECT\n  SUM(x)\nFROM t"},
    })
    wire = event.to_sse()
    data_line = wire.split("data: ")[1].split("\n\n")[0]
    # Must be single line — SSE spec requires no newlines in data
    assert "\n" not in data_line.rstrip(), f"Data has newlines: {data_line!r}"
    parsed = json.loads(data_line)
    assert "→" in parsed["message"]
    assert "\n" in parsed["detail"]["sql"]  # Newlines preserved inside JSON

    print("  [PASS] SSEEvent special characters")


def test_conversation_store():
    """ConversationStore creates, retrieves, and trims conversations."""
    from src.pipeline.orchestrator import ConversationStore

    store = ConversationStore(max_turns=3)

    # Create new conversation
    ctx = store.get_or_create(None)
    assert ctx.conversation_id.startswith("conv_")
    assert ctx.history == []
    assert ctx.turn_count == 0

    # Retrieve existing
    ctx2 = store.get_or_create(ctx.conversation_id)
    assert ctx2 is ctx

    # Update with messages
    store.update(ctx, "query 1", "answer 1")
    assert ctx.turn_count == 1
    assert len(ctx.history) == 2

    # Fill to max
    store.update(ctx, "query 2", "answer 2")
    store.update(ctx, "query 3", "answer 3")
    store.update(ctx, "query 4", "answer 4")
    assert ctx.turn_count == 4
    # max_turns=3 → keeps last 6 messages (3 turns × 2)
    assert len(ctx.history) == 6
    assert ctx.history[0]["content"] == "query 2"  # query 1 trimmed

    print("  [PASS] ConversationStore")


def test_pipeline_trace():
    """PipelineTrace serializes to dict correctly."""
    from src.pipeline.orchestrator import PipelineTrace, StepTrace

    trace = PipelineTrace(
        trace_id="test-123",
        query="total spend",
        conversation_id="conv_abc",
        timestamp="2026-03-16T00:00:00Z",
    )
    trace.steps.append(StepTrace(
        step_name="intent_classification",
        step_number=1,
        started_at=100.0,
        ended_at=100.3,
        duration_ms=300,
        status="complete",
    ))
    trace.total_duration_ms = 2000
    trace.llm_calls = 3

    d = trace.to_dict()
    assert d["trace_id"] == "test-123"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["step_name"] == "intent_classification"
    assert d["llm_calls"] == 3

    # Must be JSON-serializable
    json_str = json.dumps(d)
    assert "test-123" in json_str

    print("  [PASS] PipelineTrace serialization")


def test_extract_json_block():
    """_extract_json_block handles markdown fences and raw JSON."""
    from src.pipeline.orchestrator import CortexOrchestrator

    # Markdown fenced JSON
    assert json.loads(CortexOrchestrator._extract_json_block(
        '```json\n{"intent": "data_query"}\n```'
    )) == {"intent": "data_query"}

    # Raw JSON with preamble
    assert json.loads(CortexOrchestrator._extract_json_block(
        'Here is the result:\n{"intent": "follow_up", "confidence": 0.9}'
    )) == {"intent": "follow_up", "confidence": 0.9}

    # JSON array
    assert json.loads(CortexOrchestrator._extract_json_block(
        '```json\n["Question 1?", "Question 2?"]\n```'
    )) == ["Question 1?", "Question 2?"]

    # Plain JSON
    result = json.loads(CortexOrchestrator._extract_json_block(
        '{"a": 1}'
    ))
    assert result == {"a": 1}

    print("  [PASS] _extract_json_block")


def test_extract_sql():
    """_extract_sql finds SQL in various LLM response formats."""
    from src.pipeline.orchestrator import CortexOrchestrator
    orch = CortexOrchestrator.__new__(CortexOrchestrator)

    # Markdown fenced SQL
    sql = orch._extract_sql("Here's the query:\n```sql\nSELECT SUM(x) FROM t\n```\nDone.")
    assert sql == "SELECT SUM(x) FROM t"

    # Raw SELECT
    sql = orch._extract_sql("The total is found by: SELECT COUNT(*) FROM users;")
    assert "SELECT COUNT(*) FROM users" in sql

    # No SQL
    sql = orch._extract_sql("I don't know how to answer that.")
    assert sql == ""

    print("  [PASS] _extract_sql")


def test_extract_fields_from_entities():
    """_extract_fields_from_entities does exact explore matching (not substring)."""
    from src.pipeline.orchestrator import CortexOrchestrator
    orch = CortexOrchestrator.__new__(CortexOrchestrator)

    entities = [
        {
            "type": "measure",
            "candidates": [
                {"explore": "finance_cardmember_360,finance_merchant_profitability", "field_key": "total_billed_biz"},
                {"explore": "finance_card_issuance", "field_key": "new_cards"},
            ],
        },
        {
            "type": "dimension",
            "candidates": [
                {"explore": "finance_cardmember_360", "field_key": "generation"},
            ],
        },
        {
            "type": "filter",  # Should be skipped
            "candidates": [],
        },
    ]

    # Exact match
    measures, dimensions = orch._extract_fields_from_entities(entities, "finance_cardmember_360")
    assert measures == ["total_billed_biz"]
    assert dimensions == ["generation"]

    # Substring should NOT match — "finance_card" is NOT "finance_cardmember_360"
    measures2, dimensions2 = orch._extract_fields_from_entities(entities, "finance_card")
    assert measures2 == [], f"Substring matched! Got {measures2}"
    assert dimensions2 == []

    # Exact match for issuance
    measures3, _ = orch._extract_fields_from_entities(entities, "finance_card_issuance")
    assert measures3 == ["new_cards"]

    print("  [PASS] _extract_fields_from_entities (exact match, no substring)")


def run_unit_tests():
    print("\n═══ LAYER 1: Unit Tests ═══")
    test_sse_event_serialization()
    test_sse_event_special_chars()
    test_conversation_store()
    test_pipeline_trace()
    test_extract_json_block()
    test_extract_sql()
    test_extract_fields_from_entities()
    print("  All unit tests passed.\n")


# ════════════════════════════════════════════════════════════════════════
# LAYER 2: Integration Tests (requires SafeChain + PostgreSQL)
# ════════════════════════════════════════════════════════════════════════

def test_retrieval_pipeline():
    """Full retrieval pipeline — verifies the core engine works."""
    from src.retrieval.pipeline import retrieve_with_graph_validation, get_top_explore

    queries = [
        ("Total billed business by generation", "finance_cardmember_360"),
        ("How many attrited customers by card product", "finance_cardmember_360"),
        ("Top 5 travel verticals by gross sales", "finance_travel_sales"),
    ]

    for query, expected_explore in queries:
        print(f"  Testing: {query!r}")
        t0 = time.monotonic()
        result = retrieve_with_graph_validation(query, top_k=5)
        duration = (time.monotonic() - t0) * 1000

        top = get_top_explore(result)
        actual_explore = top.get("top_explore_name", "")
        confidence = top.get("confidence", 0)
        action = top.get("action", "unknown")

        status = "PASS" if actual_explore == expected_explore else "FAIL"
        print(f"    [{status}] explore={actual_explore}, confidence={confidence:.3f}, "
              f"action={action}, {duration:.0f}ms")

        if actual_explore != expected_explore:
            print(f"    ⚠ Expected {expected_explore}")


def test_retrieval_edge_cases():
    """Edge cases: near-miss, clarify, low confidence."""
    from src.retrieval.pipeline import retrieve_with_graph_validation

    # This should trigger near-miss (billed business is ambiguous)
    print("  Testing near-miss: 'What is total billed business?'")
    result = retrieve_with_graph_validation("What is total billed business?", top_k=5)
    if result.action == "disambiguate":
        print(f"    [PASS] action=disambiguate (near-miss detected)")
    elif result.action == "proceed" and result.explores and result.explores[0].is_near_miss:
        print(f"    [WARN] is_near_miss=True but action=proceed — check threshold")
    else:
        print(f"    [INFO] action={result.action}, confidence={result.confidence:.3f}")

    # This should trigger clarify (gibberish query)
    print("  Testing clarify: 'asdfghjkl random noise'")
    result = retrieve_with_graph_validation("asdfghjkl random noise", top_k=5)
    if result.action == "clarify":
        print(f"    [PASS] action=clarify (garbage rejected)")
    else:
        print(f"    [WARN] action={result.action} — expected clarify")


def run_integration_tests():
    print("═══ LAYER 2: Integration Tests (requires SafeChain + PostgreSQL) ═══")
    try:
        test_retrieval_pipeline()
        test_retrieval_edge_cases()
        print("  Integration tests complete.\n")
    except Exception as e:
        print(f"  ⚠ Integration tests failed: {e}")
        print("  (This is expected if SafeChain/PostgreSQL are not available)\n")


# ════════════════════════════════════════════════════════════════════════
# LAYER 3: API Tests (requires running server)
# ════════════════════════════════════════════════════════════════════════

def test_api_health(base_url: str):
    """Health endpoint returns component statuses."""
    import httpx

    # V1 health
    r = httpx.get(f"{base_url}/api/v1/health")
    assert r.status_code == 200, f"Health returned {r.status_code}"
    data = r.json()
    print(f"    Status: {data['status']}")
    for comp, info in data.get("components", {}).items():
        print(f"    {comp}: {info['status']}")
    assert "orchestrator" in data["components"]
    print("  [PASS] /api/v1/health")


def test_api_capabilities(base_url: str):
    """Capabilities endpoint returns explore catalog."""
    import httpx

    r = httpx.get(f"{base_url}/api/v1/capabilities")
    assert r.status_code == 200
    data = r.json()
    assert "explores" in data
    assert len(data["explores"]) >= 1
    assert data["features"]["streaming"] is True
    print(f"  [PASS] /api/v1/capabilities ({len(data['explores'])} explores)")


def test_api_sse_streaming(base_url: str):
    """Full SSE streaming pipeline test — the money shot."""
    import httpx

    query = "Total billed business by generation"
    print(f"  Testing SSE: {query!r}")

    events_received = []
    trace_id = None
    conversation_id = None

    with httpx.stream(
        "POST",
        f"{base_url}/api/v1/query",
        json={"query": query, "view_mode": "engineering"},
        timeout=60.0,
    ) as response:
        assert response.status_code == 200, f"Got {response.status_code}"
        assert "text/event-stream" in response.headers.get("content-type", "")

        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                if not event_block.strip():
                    continue

                lines = event_block.strip().split("\n")
                event_type = None
                event_data = None

                for line in lines:
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        event_data = json.loads(line[6:])

                if event_type and event_data:
                    events_received.append((event_type, event_data))
                    step = event_data.get("step", "")
                    msg = event_data.get("message", "")

                    if event_type == "step_start":
                        n = event_data.get("step_number", "?")
                        print(f"    [{n}/7] {msg}")
                    elif event_type == "step_complete":
                        ms = event_data.get("duration_ms", 0)
                        print(f"          ✓ {msg} ({ms}ms)")
                    elif event_type == "explore_scored":
                        winner = event_data.get("winner", "?")
                        conf = event_data.get("confidence", 0)
                        print(f"          → Winner: {winner} ({conf:.0%})")
                    elif event_type == "sql_generated":
                        sql = event_data.get("sql", "")[:80]
                        print(f"          → SQL: {sql}...")
                    elif event_type == "results":
                        rows = event_data.get("row_count", 0)
                        print(f"          → {rows} rows")
                    elif event_type == "follow_ups":
                        for s in event_data.get("suggestions", []):
                            print(f"          → Follow-up: {s}")
                    elif event_type == "disambiguate":
                        print(f"          → DISAMBIGUATE: {msg}")
                        for opt in event_data.get("options", []):
                            print(f"            Option: {opt['explore']}")
                    elif event_type == "clarify":
                        print(f"          → CLARIFY: {msg}")
                    elif event_type == "done":
                        trace_id = event_data.get("trace_id")
                        conversation_id = event_data.get("conversation_id")
                        total_ms = event_data.get("total_duration_ms", 0)
                        llm = event_data.get("llm_calls", 0)
                        print(f"    Done: {total_ms}ms, {llm} LLM calls")
                    elif event_type == "error":
                        print(f"          ✗ ERROR: {msg}")

    # Validate event sequence
    event_types = [e[0] for e in events_received]
    assert "step_start" in event_types, "No step_start events"
    assert "done" in event_types, "No done event"
    print(f"  [PASS] SSE streaming ({len(events_received)} events)")

    return trace_id, conversation_id


def test_api_trace(base_url: str, trace_id: str):
    """Trace retrieval for eval/debugging."""
    import httpx

    if not trace_id:
        print("  [SKIP] No trace_id from SSE test")
        return

    r = httpx.get(f"{base_url}/api/v1/trace/{trace_id}")
    assert r.status_code == 200, f"Trace returned {r.status_code}"
    data = r.json()
    assert data["trace_id"] == trace_id
    assert len(data["steps"]) >= 1
    print(f"  [PASS] /api/v1/trace ({len(data['steps'])} steps, "
          f"{data.get('total_duration_ms', 0):.0f}ms)")


def test_api_followup(base_url: str, conversation_id: str):
    """Follow-up query within a conversation."""
    import httpx

    if not conversation_id:
        print("  [SKIP] No conversation_id from SSE test")
        return

    print("  Testing follow-up: 'Break that down by card product'")
    events = []

    with httpx.stream(
        "POST",
        f"{base_url}/api/v1/followup",
        json={
            "query": "Break that down by card product",
            "conversation_id": conversation_id,
        },
        timeout=60.0,
    ) as response:
        assert response.status_code == 200
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                if not event_block.strip():
                    continue
                lines = event_block.strip().split("\n")
                for line in lines:
                    if line.startswith("event: "):
                        events.append(line[7:])

    assert "done" in events, "Follow-up didn't complete"
    print(f"  [PASS] Follow-up ({len(events)} events)")


def test_api_feedback(base_url: str, trace_id: str):
    """Feedback endpoint."""
    import httpx

    if not trace_id:
        print("  [SKIP] No trace_id")
        return

    r = httpx.post(f"{base_url}/api/v1/feedback", json={
        "trace_id": trace_id,
        "rating": 5,
        "comment": "Test feedback from test script",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "logged"
    print("  [PASS] /api/v1/feedback")


def test_api_v0_compat(base_url: str):
    """V0 endpoints still work (backward compat)."""
    import httpx

    r = httpx.post(f"{base_url}/query", json={"query": "total billed business", "top_k": 3})
    assert r.status_code == 200
    data = r.json()
    assert "action" in data
    print(f"  [PASS] V0 /query (action={data['action']})")

    r = httpx.get(f"{base_url}/health")
    assert r.status_code == 200
    print(f"  [PASS] V0 /health")


def run_api_tests(base_url: str = "http://localhost:8080"):
    print(f"═══ LAYER 3: API Tests (server at {base_url}) ═══")
    try:
        import httpx
    except ImportError:
        print("  ⚠ httpx not installed. Run: pip install httpx")
        return

    try:
        test_api_health(base_url)
        test_api_capabilities(base_url)
        trace_id, conversation_id = test_api_sse_streaming(base_url)
        test_api_trace(base_url, trace_id)
        test_api_followup(base_url, conversation_id)
        test_api_feedback(base_url, trace_id)
        test_api_v0_compat(base_url)
        print("  All API tests passed.\n")
    except Exception as e:
        print(f"\n  ✗ API test failed: {e}")
        import traceback
        traceback.print_exc()
        print()


# ════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Test Cortex orchestrator + API")
    parser.add_argument("--with-api", action="store_true", help="Include API tests (server must be running)")
    parser.add_argument("--api-only", action="store_true", help="Run only API tests")
    parser.add_argument("--url", default="http://localhost:8080", help="API base URL")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  Cortex Orchestrator Test Suite")
    print("=" * 70)

    if not args.api_only:
        run_unit_tests()
        run_integration_tests()

    if args.with_api or args.api_only:
        run_api_tests(args.url)

    if not args.with_api and not args.api_only:
        print("Tip: Run with --with-api to also test the SSE streaming endpoint.")
        print(f"     Start server first: uvicorn src.api.server:app --port 8080\n")


if __name__ == "__main__":
    main()
