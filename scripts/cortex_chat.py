#!/usr/bin/env python3
"""Cortex CLI Chat — interactive demo of the full NL2SQL pipeline.

Shows all 7 pipeline steps in real-time as SSE events stream back.
Supports multi-turn conversations, follow-ups, and full trace inspection.

Usage:
    python scripts/cortex_chat.py

Commands:
    /trace    - Show full trace of last query
    /clear    - Clear conversation history
    /help     - Show help
    /quit     - Exit
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ── Terminal colors (no dependencies) ─────────────────────────────

class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    WHITE = "\033[37m"
    RESET = "\033[0m"


def styled(text: str, *styles: str) -> str:
    return "".join(styles) + text + C.RESET


# ── Event renderer ────────────────────────────────────────────────

def render_event(event_type: str, data: dict) -> None:
    """Render a single SSE event to the terminal."""

    if event_type == "step_start":
        n = data.get("step_number", "?")
        total = data.get("total_steps", 7)
        msg = data.get("message", "")
        bar = "=" * n + "-" * (total - n)
        print(f"  {styled(f'[{n}/{total}]', C.BOLD, C.BLUE)} {msg}  {styled(f'[{bar}]', C.DIM)}")

    elif event_type == "step_progress":
        msg = data.get("message", "")
        print(f"         {styled(msg, C.DIM)}")

    elif event_type == "step_complete":
        n = data.get("step_number", "?")
        ms = data.get("duration_ms", 0)
        msg = data.get("message", "")
        print(f"         {styled('done', C.GREEN)} {msg} {styled(f'({ms}ms)', C.DIM)}")

    elif event_type == "explore_scored":
        winner = data.get("winner", "?")
        conf = data.get("confidence", 0)
        near = data.get("is_near_miss", False)
        label = styled(f"{conf:.0%}", C.BOLD, C.GREEN if conf >= 0.8 else C.YELLOW)
        print(f"         {styled('explore:', C.CYAN)} {winner} @ {label}")
        if near:
            print(f"         {styled('NEAR MISS — two explores are close', C.YELLOW)}")
        for exp in data.get("explores", [])[:3]:
            marker = styled(">>", C.GREEN) if exp.get("is_winner") else "  "
            print(f"           {marker} {exp['name']}: score={exp.get('score', 0):.4f} "
                  f"cov={exp.get('coverage', 0):.2f}")

    elif event_type == "sql_generated":
        sql = data.get("sql", "")
        explore = data.get("explore", "")
        print(f"         {styled('SQL for', C.CYAN)} {explore}:")
        for line in sql.strip().split("\n"):
            print(f"           {styled(line, C.DIM)}")

    elif event_type == "results":
        cols = data.get("columns", [])
        rows = data.get("rows", [])
        row_count = data.get("row_count", 0)
        truncated = data.get("truncated", False)

        print(f"         {styled(f'{row_count} rows', C.BOLD, C.GREEN)}"
              f"{' (truncated)' if truncated else ''}")

        if cols and rows:
            col_names = [c.get("label", c.get("name", "?")) for c in cols]
            # Simple table
            print(f"         {styled(' | '.join(col_names), C.BOLD)}")
            print(f"         {'-' * min(80, len(' | '.join(col_names)))}")
            for row in rows[:10]:
                vals = [str(row.get(c.get("name", ""), "")) for c in cols]
                print(f"         {' | '.join(vals)}")
            if row_count > 10:
                print(f"         {styled(f'... and {row_count - 10} more rows', C.DIM)}")

    elif event_type == "follow_ups":
        suggestions = data.get("suggestions", [])
        if suggestions:
            print(f"\n  {styled('Follow-ups:', C.BOLD, C.MAGENTA)}")
            for i, s in enumerate(suggestions, 1):
                print(f"    {styled(f'{i}.', C.MAGENTA)} {s}")

    elif event_type == "disambiguate":
        msg = data.get("message", "")
        options = data.get("options", [])
        print(f"\n  {styled('DISAMBIGUATION NEEDED', C.BOLD, C.YELLOW)}")
        print(f"  {msg}")
        for i, opt in enumerate(options, 1):
            print(f"    {styled(f'{i}.', C.YELLOW)} {opt['explore']} — {opt.get('description', '')[:60]}")
        print(f"\n  {styled('Pick one and rephrase, e.g.:', C.DIM)} "
              f"\"Use {options[0]['explore']} for my question\"")

    elif event_type == "clarify":
        msg = data.get("message", "")
        print(f"\n  {styled('CLARIFICATION NEEDED', C.BOLD, C.YELLOW)}")
        print(f"  {msg}")

    elif event_type == "error":
        msg = data.get("message", "")
        recoverable = data.get("recoverable", False)
        tag = "RECOVERABLE" if recoverable else "ERROR"
        print(f"\n  {styled(tag, C.BOLD, C.RED)}: {msg}")

    elif event_type == "done":
        total_ms = data.get("total_duration_ms", 0)
        llm_calls = data.get("llm_calls", 0)
        conf = data.get("overall_confidence", 0)
        error = data.get("error")
        if not error:
            print(f"\n  {styled('Pipeline complete', C.BOLD, C.GREEN)} "
                  f"in {styled(f'{total_ms}ms', C.BOLD)} "
                  f"| {llm_calls} LLM calls "
                  f"| confidence {conf:.0%}")


# ── Orchestrator initialization ───────────────────────────────────

async def init_orchestrator():
    """Initialize the CortexOrchestrator (same as server.py startup)."""
    from ee_config.config import Config
    from safechain.tools.mcp import MCPToolLoader
    from access_llm.chat import AgentOrchestrator
    from src.pipeline.orchestrator import CortexOrchestrator, ConversationStore

    print(f"  {styled('[1/4]', C.BOLD)} Loading SafeChain config...")
    config = Config.from_env()

    print(f"  {styled('[2/4]', C.BOLD)} Loading MCP tools...")
    tools = await MCPToolLoader.load_tools(config)
    print(f"         {len(tools)} tools loaded")

    print(f"  {styled('[3/4]', C.BOLD)} Creating orchestrator...")
    react_agent = AgentOrchestrator(
        model_id="3",  # Gemini 2.5 Flash
        tools=tools,
        max_iterations=5,
    )

    orchestrator = CortexOrchestrator(
        react_agent=react_agent,
        conversations=ConversationStore(max_turns=20),
        classifier_model_idx="3",
    )

    print(f"  {styled('[4/4]', C.BOLD)} Pre-warming caches...")
    await orchestrator.warm_up()

    return orchestrator


# ── Main chat loop ────────────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    print(f"""
{styled('=' * 62, C.BOLD)}
{styled('  Cortex CLI', C.BOLD, C.CYAN)} — NL2SQL Pipeline with Looker Semantic Layer
{styled('=' * 62, C.BOLD)}
""")

    try:
        orchestrator = await init_orchestrator()
    except Exception as e:
        print(f"\n  {styled('INIT FAILED', C.BOLD, C.RED)}: {e}")
        print(f"  Check: CONFIG_PATH, SafeChain creds, MCP servers, Docker (PostgreSQL)")
        return

    print(f"\n  {styled('Ready!', C.BOLD, C.GREEN)} Type a question or /help\n")

    conversation_id = None
    last_trace_id = None

    while True:
        try:
            prompt = styled("You: ", C.BOLD, C.WHITE)
            user_input = input(prompt).strip()

            if not user_input:
                continue

            # Commands
            if user_input.lower() == "/quit":
                print(f"\n{styled('Goodbye!', C.DIM)}")
                break

            elif user_input.lower() == "/help":
                print(f"""
  {styled('Commands:', C.BOLD)}
    /trace    Show full JSON trace of last query
    /clear    Clear conversation (start fresh)
    /help     This message
    /quit     Exit

  {styled('Example queries:', C.BOLD)}
    Total billed business by generation
    How many attrited customers by card product?
    Top 5 travel verticals by gross sales
    Break that down by quarter          {styled('(follow-up)', C.DIM)}
""")
                continue

            elif user_input.lower() == "/clear":
                conversation_id = None
                last_trace_id = None
                print(f"  {styled('Conversation cleared.', C.DIM)}\n")
                continue

            elif user_input.lower() == "/trace":
                if not last_trace_id:
                    print(f"  {styled('No trace yet — ask a question first.', C.DIM)}\n")
                    continue
                trace = orchestrator.get_trace(last_trace_id)
                if trace:
                    print(json.dumps(trace.to_dict(), indent=2, default=str))
                else:
                    print(f"  {styled('Trace not found.', C.RED)}")
                print()
                continue

            # ── Run pipeline ──────────────────────────────────
            print()
            t0 = time.monotonic()

            answer_text = ""
            async for event in orchestrator.process_query(
                query=user_input,
                conversation_id=conversation_id,
                view_mode="engineering",
            ):
                data = event.data
                render_event(event.event, data)

                # Capture state for follow-ups
                if event.event == "done":
                    conversation_id = data.get("conversation_id", conversation_id)
                    last_trace_id = data.get("trace_id")

                # Capture answer for display
                if event.event == "step_complete" and data.get("step") == "response_formatting":
                    detail = data.get("detail", {})
                    answer_text = detail.get("answer", "")

            # Show the answer
            if answer_text:
                print(f"\n  {styled('Answer:', C.BOLD, C.CYAN)}")
                for line in answer_text.strip().split("\n"):
                    print(f"  {line}")

            wall_ms = (time.monotonic() - t0) * 1000
            print(f"\n  {styled(f'Wall clock: {wall_ms:.0f}ms', C.DIM)}")
            print()

        except KeyboardInterrupt:
            print(f"\n\n{styled('Goodbye!', C.DIM)}")
            break
        except EOFError:
            print(f"\n\n{styled('Goodbye!', C.DIM)}")
            break
        except Exception as e:
            print(f"\n  {styled('ERROR', C.BOLD, C.RED)}: {e}")
            import traceback
            traceback.print_exc()
            print()


if __name__ == "__main__":
    asyncio.run(main())
