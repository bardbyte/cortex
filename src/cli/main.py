#!/usr/bin/env python3
"""Cortex CLI -- interactive testing interface for the NL2SQL pipeline.

Usage:
    python -m src.cli.main

Commands:
    /trace    - Show full pipeline trace for last query
    /sql      - Show generated SQL for last query
    /tools    - List available MCP tools
    /health   - Check system health
    /debug    - Toggle debug mode (show trace with every response)
    /help     - Show help
    /quit     - Exit

This is the primary testing interface. Run it on the corp laptop to
verify the full pipeline: query → classify → retrieve → generate SQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

logger = logging.getLogger("cortex")


# ── Rich formatting (graceful fallback to plain text) ─────────────

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None


def print_panel(content: str, title: str = "", style: str = "blue"):
    """Print a Rich panel or plain text fallback."""
    if RICH_AVAILABLE and console:
        console.print(Panel(content, title=title, style=style, expand=False))
    else:
        print(f"\n{'─' * 60}")
        if title:
            print(f"  {title}")
            print(f"{'─' * 60}")
        print(content)
        print(f"{'─' * 60}")


def print_trace_table(trace: dict):
    """Print pipeline trace as a table."""
    steps = trace.get("steps", [])

    if RICH_AVAILABLE and console:
        table = Table(title="Pipeline Trace", show_lines=True)
        table.add_column("Step", style="cyan")
        table.add_column("Decision", style="green")
        table.add_column("Confidence", justify="right")
        table.add_column("Duration", justify="right", style="yellow")

        for step in steps:
            conf = step.get("confidence")
            conf_str = f"{conf:.0%}" if conf is not None else "—"
            table.add_row(
                step["name"],
                step["decision"],
                conf_str,
                f"{step['duration_ms']:.0f}ms",
            )

        # Summary row
        table.add_row(
            "[bold]TOTAL[/bold]",
            trace.get("action", ""),
            f"{trace.get('confidence', 0):.0%}",
            f"[bold]{trace.get('total_duration_ms', 0):.0f}ms[/bold]",
        )
        console.print(table)
        console.print(
            f"  LLM calls: {trace.get('llm_calls', 0)}  |  "
            f"MCP calls: {trace.get('mcp_calls', 0)}  |  "
            f"Trace ID: {trace.get('trace_id', '?')}"
        )
    else:
        print("\n  Pipeline Trace:")
        for step in steps:
            conf = step.get("confidence")
            conf_str = f" ({conf:.0%})" if conf is not None else ""
            print(
                f"    {step['name']:25s} "
                f"{step['decision']:15s}{conf_str:>8s}  "
                f"{step['duration_ms']:.0f}ms"
            )
        print(f"\n  Total: {trace.get('total_duration_ms', 0):.0f}ms")


def print_response(result: dict, debug: bool = False):
    """Print a CortexOrchestrator response."""
    answer = result.get("answer", "")
    sql = result.get("sql")
    follow_ups = result.get("follow_ups", [])
    error = result.get("error")
    metadata = result.get("metadata", {})
    trace = result.get("trace")

    # Confidence from trace
    confidence = None
    if trace:
        confidence = trace.get("confidence")
    elif metadata:
        confidence = metadata.get("confidence")

    # Answer
    if error:
        print_panel(
            f"Error: {error.get('message', str(error))}",
            title="Error",
            style="red",
        )
    elif answer:
        header = ""
        if confidence is not None:
            header = f"Confidence: {confidence:.0%}\n\n"
        print_panel(header + answer, title="Cortex", style="green")

    # SQL
    if sql:
        print_panel(sql, title="Generated SQL", style="cyan")

    # Follow-ups
    if follow_ups:
        follow_text = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(follow_ups))
        if RICH_AVAILABLE and console:
            console.print(f"\n[dim]Follow-up suggestions:[/dim]\n{follow_text}")
        else:
            print(f"\nFollow-up suggestions:\n{follow_text}")

    # Timing
    total_ms = metadata.get("total_duration_ms", 0) if metadata else 0
    if total_ms:
        if RICH_AVAILABLE and console:
            console.print(f"[dim]({total_ms:.0f}ms)[/dim]")
        else:
            print(f"({total_ms:.0f}ms)")

    # Debug trace
    if debug and trace:
        print()
        print_trace_table(trace)


# ── CLI Session ───────────────────────────────────────────────────

class CliSession:
    """Interactive CLI session wrapping CortexOrchestrator."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.history: list[dict] = []
        self.last_result: dict | None = None
        self.last_retrieval_context: dict | None = None
        self.debug = False

    async def query(self, user_input: str) -> dict:
        """Send a query through the pipeline."""
        result = await self.orchestrator.run(
            query=user_input,
            conversation_history=self.history,
            debug=True,  # always get trace for /trace command
            last_retrieval_context=self.last_retrieval_context,
        )

        # Update history
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": result.get("answer", "")})
        if len(self.history) > 20:
            self.history = self.history[-20:]

        # Store for follow-ups and /trace
        self.last_result = result
        self.last_retrieval_context = result.get("retrieval_context")

        return result

    def show_trace(self):
        """Show trace for last query."""
        if not self.last_result or not self.last_result.get("trace"):
            print("  No trace available. Run a query first.")
            return
        print_trace_table(self.last_result["trace"])

    def show_sql(self):
        """Show SQL for last query."""
        if not self.last_result:
            print("  No SQL available. Run a query first.")
            return
        sql = self.last_result.get("sql")
        if sql:
            print_panel(sql, title="Generated SQL", style="cyan")
        else:
            print("  No SQL was generated for the last query.")

    def show_tools(self):
        """Show available MCP tools."""
        if hasattr(self.orchestrator, 'agent') and hasattr(self.orchestrator.agent, 'tools'):
            tools = self.orchestrator.agent.tools
            print(f"\n  Available MCP tools ({len(tools)}):")
            for t in sorted(tools, key=lambda x: x.name):
                desc = t.description[:60] + "..." if len(t.description) > 60 else t.description
                print(f"    • {t.name:25s} {desc}")
        else:
            print("  Tool list not available.")

    def show_help(self):
        """Show help."""
        help_text = """
  Commands:
    /trace    Show full pipeline trace for last query
    /sql      Show generated SQL for last query
    /tools    List available MCP tools
    /debug    Toggle debug mode (show trace with every response)
    /health   Check system health
    /help     Show this help
    /quit     Exit

  Example queries:
    "What was total billed business for open card members?"
    "Show attrited customer count by generation"
    "Top 5 travel verticals by gross sales"
    "How many millennials use Apple Pay?"
"""
        print(help_text)


# ── Main ──────────────────────────────────────────────────────────

async def main():
    """Run the interactive CLI."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy loggers during interactive use
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║     Cortex — NL2SQL Pipeline (v1: SQL Generation)        ║
║                                                           ║
║     Natural Language → SQL via Looker Semantic Layer      ║
║     Type /help for commands, /quit to exit                ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
    print(banner)

    # Bootstrap
    print("  Initializing pipeline...\n")
    try:
        from access_llm.chat import ConsoleThinkingCallback
        thinking_cb = ConsoleThinkingCallback(use_rich=RICH_AVAILABLE)
    except ImportError:
        thinking_cb = None

    try:
        from src.pipeline.bootstrap import create_cortex_orchestrator
        orchestrator = await create_cortex_orchestrator(
            sql_gen_only=True,
            thinking_callback=thinking_cb,
        )
    except Exception as e:
        print(f"\n  Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        print("\n  Check your .env file and SafeChain connectivity.")
        return

    session = CliSession(orchestrator)
    session.show_help()
    print("  Ready. Type your question.\n")

    # Chat loop
    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Commands
            cmd = user_input.lower()
            if cmd == "/quit":
                print("\n  Goodbye!")
                break
            elif cmd == "/trace":
                session.show_trace()
                continue
            elif cmd == "/sql":
                session.show_sql()
                continue
            elif cmd == "/tools":
                session.show_tools()
                continue
            elif cmd == "/debug":
                session.debug = not session.debug
                print(f"  Debug mode: {'ON' if session.debug else 'OFF'}")
                continue
            elif cmd == "/help":
                session.show_help()
                continue
            elif cmd == "/health":
                print("  Checking health...")
                # Quick health check
                try:
                    from ee_config.config import Config
                    Config.from_env()
                    print("  SafeChain: OK")
                except Exception as e:
                    print(f"  SafeChain: FAIL ({e})")
                try:
                    from src.connectors.postgres_age_client import get_engine
                    from sqlalchemy import text
                    with get_engine().connect() as conn:
                        conn.execute(text("SELECT 1"))
                    print("  PostgreSQL: OK")
                except Exception as e:
                    print(f"  PostgreSQL: FAIL ({e})")
                continue

            # Query
            try:
                t0 = time.monotonic()
                result = await session.query(user_input)
                elapsed = (time.monotonic() - t0) * 1000

                print()
                print_response(result, debug=session.debug)
                print()

            except KeyboardInterrupt:
                print("\n  Query cancelled.")
            except Exception as e:
                print(f"\n  Error: {e}")
                import traceback
                traceback.print_exc()

        except KeyboardInterrupt:
            print("\n\n  Goodbye!")
            break
        except EOFError:
            print("\n\n  Goodbye!")
            break


def run():
    """Entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
