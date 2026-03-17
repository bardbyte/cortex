"""End-to-end API test — acts as the UI, hits every endpoint, parses SSE.

Requires the backend running: uvicorn src.api.server:app --host 0.0.0.0 --port 8080

Run:
    python tests/test_api_e2e.py
"""

import json
import sys
import time
import requests

API = "http://localhost:8080"

# Test queries — easy, medium, hard
QUERIES = [
    ("easy",   "What is the total billed business for the OPEN segment?"),
    ("medium", "How many attrited customers do we have by generation?"),
    ("hard",   "What is our attrition rate for Q4 2025?"),
]


def sep(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def test_health():
    sep("1. GET /api/v1/health")
    try:
        r = requests.get(f"{API}/api/v1/health", timeout=10)
        print(f"  Status: {r.status_code}")
        data = r.json()
        print(f"  Response: {json.dumps(data, indent=2)}")
        if r.status_code != 200:
            print("  ✗ Health check failed")
            return False
        print("  ✓ Health OK")
        return True
    except requests.ConnectionError:
        print("  ✗ Cannot connect to backend. Is it running on port 8080?")
        return False


def test_capabilities():
    sep("2. GET /api/v1/capabilities")
    r = requests.get(f"{API}/api/v1/capabilities", timeout=10)
    print(f"  Status: {r.status_code}")
    data = r.json()
    explores = data.get("explores", [])
    starters = data.get("starter_questions", [])
    print(f"  Explores: {len(explores)}")
    for e in explores:
        print(f"    - {e['name']}: {len(e.get('sample_questions', []))} sample questions")
    print(f"  Starter questions: {len(starters)}")
    for q in starters:
        print(f"    [{q.get('difficulty', '?')}] {q.get('text', '?')}")
    print("  ✓ Capabilities OK")
    return data


def test_query_sse(difficulty: str, query: str):
    sep(f"3. POST /api/v1/query — [{difficulty}] \"{query}\"")
    t0 = time.time()

    events = []
    error_event = None
    done_event = None

    try:
        r = requests.post(
            f"{API}/api/v1/query",
            json={"query": query, "view_mode": "engineering"},
            stream=True,
            timeout=120,
        )
        print(f"  HTTP status: {r.status_code}")

        if r.status_code != 200:
            print(f"  ✗ Non-200 response: {r.text[:500]}")
            return False

        # Parse SSE stream
        current_event = "message"
        current_data = ""

        for line in r.iter_lines(decode_unicode=True):
            if line is None:
                continue
            line_str = line if isinstance(line, str) else line.decode("utf-8")

            if line_str.startswith("event:"):
                current_event = line_str[6:].strip()
            elif line_str.startswith("data:"):
                current_data = line_str[5:].strip()
            elif line_str == "":
                # Empty line = end of SSE block
                if current_data:
                    try:
                        payload = json.loads(current_data)
                    except json.JSONDecodeError:
                        print(f"  ⚠ Malformed JSON: {current_data[:100]}")
                        current_data = ""
                        current_event = "message"
                        continue

                    events.append({"event": current_event, "data": payload})
                    elapsed = time.time() - t0

                    # Print each event as it arrives
                    if current_event == "step_start":
                        step = payload.get("step", "?")
                        msg = payload.get("message", "")
                        print(f"  [{elapsed:5.1f}s] ▶ step_start: {step} — {msg}")

                    elif current_event == "step_complete":
                        step = payload.get("step", "?")
                        dur = payload.get("duration_ms", 0)
                        msg = payload.get("message", "")
                        print(f"  [{elapsed:5.1f}s] ✓ step_complete: {step} ({dur:.0f}ms) — {msg}")

                    elif current_event == "step_progress":
                        step = payload.get("step", "?")
                        msg = payload.get("message", "")
                        print(f"  [{elapsed:5.1f}s]   progress: {step} — {msg}")

                    elif current_event == "entities_extracted":
                        metrics = payload.get("metrics", [])
                        dims = payload.get("dimensions", [])
                        filters = payload.get("filters", [])
                        tr = payload.get("time_range")
                        print(f"  [{elapsed:5.1f}s] 🔍 entities: metrics={metrics} dims={dims} filters={filters} time_range={tr}")

                    elif current_event == "explore_scored":
                        winner = payload.get("winner")
                        conf = payload.get("confidence", 0)
                        near = payload.get("is_near_miss", False)
                        explores = payload.get("explores", [])
                        print(f"  [{elapsed:5.1f}s] 📊 explore_scored: winner={winner} confidence={conf:.2f} near_miss={near}")
                        for exp in explores[:3]:
                            print(f"           {exp.get('name')}: score={exp.get('score', 0):.3f} coverage={exp.get('coverage', 0):.2f}")

                    elif current_event == "disambiguate":
                        options = payload.get("options", [])
                        print(f"  [{elapsed:5.1f}s] ⚡ disambiguate: {len(options)} options")
                        for opt in options:
                            print(f"           {opt.get('explore')}: {opt.get('confidence', 0):.2f} — {opt.get('description', '')[:60]}")

                    elif current_event == "filter_resolved":
                        resolved = payload.get("resolved", [])
                        mandatory = payload.get("mandatory", [])
                        print(f"  [{elapsed:5.1f}s] 🔧 filters: {len(resolved)} resolved, {len(mandatory)} mandatory")
                        for f in resolved:
                            print(f"           \"{f.get('user_said')}\" → {f.get('resolved_to')} (pass={f.get('pass')}, conf={f.get('confidence', 0):.2f})")

                    elif current_event == "sql_generated":
                        sql = payload.get("sql", "")
                        explore = payload.get("explore", "?")
                        print(f"  [{elapsed:5.1f}s] 💾 sql_generated: explore={explore}")
                        # Print SQL indented
                        for sql_line in sql.strip().split("\n"):
                            print(f"           {sql_line}")

                    elif current_event == "results":
                        cols = payload.get("columns", [])
                        rows = payload.get("rows", [])
                        row_count = payload.get("row_count", len(rows))
                        truncated = payload.get("truncated", False)
                        col_names = [c.get("name", c) if isinstance(c, dict) else c for c in cols]
                        print(f"  [{elapsed:5.1f}s] 📋 results: {len(col_names)} columns, {row_count} rows, truncated={truncated}")
                        print(f"           columns: {col_names}")
                        for row in rows[:3]:
                            print(f"           {row}")
                        if len(rows) > 3:
                            print(f"           ... ({len(rows) - 3} more rows)")

                    elif current_event == "follow_ups":
                        suggestions = payload.get("suggestions", [])
                        print(f"  [{elapsed:5.1f}s] 💡 follow_ups: {suggestions}")

                    elif current_event == "done":
                        done_event = payload
                        trace = payload.get("trace_id", "?")
                        dur = payload.get("total_duration_ms", 0)
                        action = payload.get("action", "?")
                        conf = payload.get("overall_confidence", 0)
                        conv = payload.get("conversation_id", "?")
                        err = payload.get("error")
                        print(f"  [{elapsed:5.1f}s] 🏁 done: action={action} confidence={conf:.2f} duration={dur:.0f}ms")
                        print(f"           trace_id={trace}")
                        print(f"           conversation_id={conv}")
                        if err:
                            print(f"           ✗ ERROR: {err}")

                    elif current_event == "error":
                        error_event = payload
                        msg = payload.get("message", payload.get("error", "unknown"))
                        print(f"  [{elapsed:5.1f}s] ✗ ERROR: {msg}")

                    else:
                        print(f"  [{elapsed:5.1f}s] ? {current_event}: {json.dumps(payload)[:120]}")

                current_data = ""
                current_event = "message"

    except requests.ConnectionError as e:
        print(f"  ✗ Connection error: {e}")
        return False
    except requests.Timeout:
        print("  ✗ Request timed out after 120s")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

    total = time.time() - t0
    print(f"\n  Total: {len(events)} events in {total:.1f}s")

    if error_event:
        print(f"  ✗ FAILED — pipeline returned error")
        return False
    if done_event:
        action = done_event.get("action", "proceed")
        if done_event.get("error"):
            print(f"  ✗ FAILED — done event has error: {done_event['error']}")
            return False
        print(f"  ✓ PASSED — action={action}")
        return True

    print("  ✗ FAILED — no done event received")
    return False


def main():
    print("=" * 60)
    print("  Cortex API End-to-End Test")
    print("  Simulates exactly what the React UI does")
    print("=" * 60)

    # Health
    if not test_health():
        print("\n⛔ Backend not reachable. Aborting.")
        sys.exit(1)

    # Capabilities
    test_capabilities()

    # Queries
    results = {}
    for difficulty, query in QUERIES:
        ok = test_query_sse(difficulty, query)
        results[difficulty] = ok

    # Summary
    sep("SUMMARY")
    for difficulty, query in QUERIES:
        status = "✓ PASS" if results[difficulty] else "✗ FAIL"
        print(f"  [{difficulty:6s}] {status}  {query}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  {passed}/{total} queries passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
