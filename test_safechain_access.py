#!/usr/bin/env python3
"""
Cortex SafeChain Access Test Script
====================================
Copy this onto the corp laptop and run:

    cd cortex/
    python test_safechain_access.py

Tests access to:
  1. SafeChain config (CIBIS auth)
  2. Gemini 2.5 Pro (model idx "1") — reasoning LLM
  3. Gemini 2.5 Flash (model idx "3") — fast classifier LLM
  4. BGE-large-en embedding (model idx "2") — vector search
  5. MCP tool loading (Looker tools) — optional, needs MCP server

Prerequisites:
  - .env file with CIBIS_CONSUMER_INTEGRATION_ID, CIBIS_CONSUMER_SECRET
  - config/config.yml with model entries "1", "2", "3"
  - safechain, ee_config packages installed
  - (Optional) Looker MCP server running at localhost:5000/scp

NO execution — this only tests connectivity and model access.
"""

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

# Ensure we can import from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv, find_dotenv

# ============================================================================
# Test Infrastructure
# ============================================================================

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
SKIP = "\033[93m⊘ SKIP\033[0m"
INFO = "\033[94mℹ INFO\033[0m"

results = []


def report(test_name: str, passed: bool, detail: str = "", skipped: bool = False):
    """Record and print a test result."""
    if skipped:
        status = SKIP
        results.append(("SKIP", test_name, detail))
    elif passed:
        status = PASS
        results.append(("PASS", test_name, detail))
    else:
        status = FAIL
        results.append(("FAIL", test_name, detail))
    print(f"  {status}  {test_name}")
    if detail:
        print(f"         {detail}")


def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ============================================================================
# Test 1: Environment & Config
# ============================================================================

def test_env_and_config():
    """Test that .env and config.yml are loadable."""
    section("1. Environment & SafeChain Config")

    # .env file
    load_dotenv(find_dotenv())
    env_path = find_dotenv()
    report(".env file found", bool(env_path), env_path or "Not found")

    # CIBIS credentials
    cibis_id = os.getenv("CIBIS_CONSUMER_INTEGRATION_ID")
    cibis_secret = os.getenv("CIBIS_CONSUMER_SECRET")
    report(
        "CIBIS_CONSUMER_INTEGRATION_ID set",
        bool(cibis_id),
        f"{'[{len(cibis_id)} chars]' if cibis_id else 'Missing — set in .env'}",
    )
    report(
        "CIBIS_CONSUMER_SECRET set",
        bool(cibis_secret),
        f"{'[{len(cibis_secret)} chars]' if cibis_secret else 'Missing — set in .env'}",
    )

    # CONFIG_PATH
    config_path = os.getenv("CONFIG_PATH", "./config/config.yml")
    config_exists = Path(config_path).exists()
    report("config.yml exists", config_exists, config_path)

    # SafeChain Config.from_env()
    try:
        from ee_config.config import Config
        config = Config.from_env()
        report("Config.from_env()", True, f"type={type(config).__name__}")
        return config
    except ImportError as e:
        report("Config.from_env()", False, f"ImportError: {e}")
        return None
    except Exception as e:
        report("Config.from_env()", False, str(e))
        return None


# ============================================================================
# Test 2: Gemini 2.5 Pro (model idx "1")
# ============================================================================

def test_gemini_pro():
    """Test Gemini 2.5 Pro access via SafeChain."""
    section("2. Gemini 2.5 Pro (model idx '1')")

    try:
        from safechain.lcel import model
        report("safechain.lcel import", True)
    except ImportError as e:
        report("safechain.lcel import", False, str(e))
        return

    try:
        t0 = time.time()
        client = model("1")
        elapsed = time.time() - t0
        report(
            "model('1') instantiation",
            True,
            f"type={type(client).__name__}, {elapsed:.1f}s",
        )
    except Exception as e:
        report("model('1') instantiation", False, str(e))
        return

    # Test a simple invoke — LangChain-style
    try:
        from langchain_core.messages import HumanMessage

        t0 = time.time()
        response = client.invoke(
            [HumanMessage(content="Reply with exactly: CORTEX_PRO_OK")]
        )
        elapsed = time.time() - t0

        # Extract text from response
        if hasattr(response, "content"):
            text = response.content
        elif isinstance(response, dict):
            text = response.get("content", str(response))
        else:
            text = str(response)

        passed = len(text) > 0
        report(
            "Pro invoke (simple prompt)",
            passed,
            f"response={text[:80]!r}... ({elapsed:.1f}s)",
        )
    except Exception as e:
        report("Pro invoke (simple prompt)", False, f"{type(e).__name__}: {e}")


# ============================================================================
# Test 3: Gemini 2.5 Flash (model idx "3")
# ============================================================================

def test_gemini_flash():
    """Test Gemini 2.5 Flash access via SafeChain."""
    section("3. Gemini 2.5 Flash (model idx '3')")

    try:
        from safechain.lcel import model
    except ImportError:
        report("safechain.lcel import", False, "Already failed above")
        return

    try:
        t0 = time.time()
        client = model("3")
        elapsed = time.time() - t0
        report(
            "model('3') instantiation",
            True,
            f"type={type(client).__name__}, {elapsed:.1f}s",
        )
    except Exception as e:
        report(
            "model('3') instantiation",
            False,
            f"{e}\n         → If 'model not found', add Flash entry as model '3' in config.yml",
        )
        return

    # Test invoke
    try:
        from langchain_core.messages import HumanMessage

        t0 = time.time()
        response = client.invoke(
            [HumanMessage(content="Reply with exactly: CORTEX_FLASH_OK")]
        )
        elapsed = time.time() - t0

        if hasattr(response, "content"):
            text = response.content
        elif isinstance(response, dict):
            text = response.get("content", str(response))
        else:
            text = str(response)

        passed = len(text) > 0
        report(
            "Flash invoke (simple prompt)",
            passed,
            f"response={text[:80]!r}... ({elapsed:.1f}s)",
        )
    except Exception as e:
        report("Flash invoke (simple prompt)", False, f"{type(e).__name__}: {e}")


# ============================================================================
# Test 4: Embedding Model (model idx "2")
# ============================================================================

def test_embedding():
    """Test BGE embedding model access via SafeChain."""
    section("4. Embedding Model (model idx '2')")

    try:
        from safechain.lcel import model
    except ImportError:
        report("safechain.lcel import", False, "Already failed above")
        return

    try:
        t0 = time.time()
        client = model("2")
        elapsed = time.time() - t0
        report(
            "model('2') instantiation",
            True,
            f"type={type(client).__name__}, {elapsed:.1f}s",
        )
    except Exception as e:
        report("model('2') instantiation", False, str(e))
        return

    # Test embed_query
    try:
        test_text = "total billed business for open card members"
        t0 = time.time()
        vector = client.embed_query(test_text)
        elapsed = time.time() - t0

        is_list = isinstance(vector, list)
        dim = len(vector) if is_list else 0
        report(
            "embed_query()",
            is_list and dim > 0,
            f"dim={dim}, first_3={vector[:3] if is_list else 'N/A'}, {elapsed:.1f}s",
        )

        # Verify dimensionality (BGE-large-en = 1024)
        if dim > 0:
            report(
                f"Vector dimensionality ({dim})",
                dim == 1024,
                "Expected 1024 for BGE-large-en" if dim != 1024 else "Matches BGE-large-en",
            )
    except Exception as e:
        report("embed_query()", False, f"{type(e).__name__}: {e}")


# ============================================================================
# Test 5: MCP Tool Loading (Looker)
# ============================================================================

async def test_mcp_tools(config):
    """Test MCP tool loading — needs MCP server running."""
    section("5. MCP Tool Loading (Looker)")

    if config is None:
        report("MCP tools", False, skipped=True, detail="No config — skipped")
        return

    try:
        from safechain.tools.mcp import MCPToolLoader
        report("MCPToolLoader import", True)
    except ImportError as e:
        report("MCPToolLoader import", False, str(e))
        return

    try:
        t0 = time.time()
        tools = await MCPToolLoader.load_tools(config)
        elapsed = time.time() - t0
        report(
            "MCPToolLoader.load_tools()",
            len(tools) > 0,
            f"loaded {len(tools)} tools in {elapsed:.1f}s",
        )

        # List tool names
        if tools:
            tool_names = [t.name for t in tools]
            print(f"\n  {INFO}  Available Looker MCP tools:")
            for name in sorted(tool_names):
                print(f"         • {name}")

            # Check for critical tools we need
            critical = ["query_sql", "query", "get_explores", "get_dimensions", "get_measures"]
            for tool_name in critical:
                found = tool_name in tool_names
                report(f"Critical tool: {tool_name}", found)

    except ConnectionRefusedError:
        report(
            "MCPToolLoader.load_tools()",
            False,
            skipped=True,
            detail="MCP server not running at localhost:5000/scp — this is OK for now",
        )
    except Exception as e:
        report(
            "MCPToolLoader.load_tools()",
            False,
            f"{type(e).__name__}: {e}\n"
            "         → Is the Looker MCP server running? (npm start in looker-mcp/)",
        )


# ============================================================================
# Test 6: MCPToolAgent with Pro (end-to-end LLM + tools)
# ============================================================================

async def test_mcp_agent(config):
    """Test MCPToolAgent with ReAct loop — mirrors chat.py's AgentOrchestrator."""
    section("6. MCPToolAgent End-to-End (ReAct loop)")

    if config is None:
        report("MCPToolAgent", False, skipped=True, detail="No config — skipped")
        return

    try:
        from safechain.tools.mcp import MCPToolLoader, MCPToolAgent
        from langchain_core.messages import (
            SystemMessage, HumanMessage, AIMessage, ToolMessage,
        )
    except ImportError as e:
        report("MCPToolAgent imports", False, str(e))
        return

    try:
        tools = await MCPToolLoader.load_tools(config)
    except Exception:
        report("MCPToolAgent", False, skipped=True, detail="No MCP tools — skipped")
        return

    if not tools:
        report("MCPToolAgent", False, skipped=True, detail="No MCP tools loaded — skipped")
        return

    # Get model_id from config (same pattern as chat.py line 547)
    model_id = (
        getattr(config, "model_id", None)
        or getattr(config, "model", None)
        or getattr(config, "llm_model", None)
        or "gemini-pro"
    )

    try:
        agent = MCPToolAgent(model_id, tools)
        report("MCPToolAgent creation", True, f"model_id={model_id!r}")
    except Exception as e:
        report("MCPToolAgent creation", False, str(e))
        return

    # ReAct loop — same pattern as AgentOrchestrator.run() in chat.py
    # MCPToolAgent does single-pass (LLM call → tool exec → return).
    # We loop: if the agent called tools, we feed results back and go again.
    messages = [
        {"role": "system", "content": "You are a test agent. Be brief. List Looker models using get_models."},
        {"role": "user", "content": "What Looker models are available? Just list the names."},
    ]

    def to_lc_messages(msgs):
        lc = []
        for m in msgs:
            role, content = m.get("role", ""), m.get("content", "")
            if role == "system":
                lc.append(SystemMessage(content=content))
            elif role == "user":
                lc.append(HumanMessage(content=content))
            elif role == "assistant":
                lc.append(AIMessage(content=content))
            elif role == "tool":
                lc.append(ToolMessage(
                    content=content,
                    tool_call_id=m.get("tool_call_id", ""),
                    name=m.get("name", ""),
                ))
        return lc

    max_iterations = 5
    final_content = ""
    total_tool_calls = 0

    try:
        t0 = time.time()
        for iteration in range(max_iterations):
            lc_input = to_lc_messages(messages)
            result = await agent.ainvoke(lc_input)

            # Parse result
            if isinstance(result, dict):
                content = result.get("content", "")
                tool_results = result.get("tool_results", [])
            else:
                content = getattr(result, "content", str(result))
                tool_results = []

            if tool_results:
                total_tool_calls += len(tool_results)
                # Add assistant message + tool results back to messages for next loop
                messages.append({"role": "assistant", "content": content or ""})
                for tr in tool_results:
                    messages.append({
                        "role": "tool",
                        "content": str(tr.get("result", tr.get("error", ""))),
                        "tool_call_id": tr.get("tool_call_id", ""),
                        "name": tr.get("tool", ""),
                    })
                print(f"         iteration {iteration + 1}: {len(tool_results)} tool call(s)")
            else:
                # No tool calls — this is the final answer
                final_content = content
                break

        elapsed = time.time() - t0
        passed = len(str(final_content)) > 0
        report(
            "MCPToolAgent ReAct loop",
            passed,
            f"iterations={iteration + 1}, tools_called={total_tool_calls}, "
            f"response={str(final_content)[:100]!r}... ({elapsed:.1f}s)",
        )
    except Exception as e:
        report("MCPToolAgent ReAct loop", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()


# ============================================================================
# Summary
# ============================================================================

def print_summary():
    section("SUMMARY")
    passed = sum(1 for s, _, _ in results if s == "PASS")
    failed = sum(1 for s, _, _ in results if s == "FAIL")
    skipped = sum(1 for s, _, _ in results if s == "SKIP")
    total = len(results)

    print(f"\n  Total: {total}  |  {PASS} {passed}  |  {FAIL} {failed}  |  {SKIP} {skipped}")

    if failed > 0:
        print(f"\n  Failed tests:")
        for status, name, detail in results:
            if status == "FAIL":
                print(f"    {FAIL}  {name}")
                if detail:
                    print(f"           {detail}")

    # Guidance for next steps
    print(f"\n{'─' * 60}")
    print("  NEXT STEPS")
    print(f"{'─' * 60}")

    if failed == 0 and passed > 0:
        print("  All critical tests passed! Tell Saheb to give the go-ahead")
        print("  to build the full Cortex agent pipeline.")
    else:
        if any(s == "FAIL" and "model('3')" in n for s, n, _ in results):
            print("  → Add Flash as model '3' in config/config.yml (see below)")
        if any(s == "FAIL" and "CIBIS" in n for s, n, _ in results):
            print("  → Set CIBIS_CONSUMER_INTEGRATION_ID and CIBIS_CONSUMER_SECRET in .env")
        if any(s == "FAIL" and "safechain" in n.lower() for s, n, _ in results):
            print("  → Ensure safechain and ee_config are installed: pip install safechain ee_config")

    print()


# ============================================================================
# Main
# ============================================================================

async def main():
    print("\n" + "=" * 60)
    print("  CORTEX — SafeChain Access Test")
    print("  Tests: Config, Pro, Flash, Embedding, MCP Tools")
    print("=" * 60)

    config = test_env_and_config()
    test_gemini_pro()
    test_gemini_flash()
    test_embedding()
    await test_mcp_tools(config)
    await test_mcp_agent(config)

    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
