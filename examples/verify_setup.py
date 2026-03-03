#!/usr/bin/env python3
"""Verify your Cortex development environment.

Run this once after setup. If all 5 checks pass, you're ready to build.

Usage:
    python examples/verify_setup.py

Prerequisites:
    1. cp .env.example .env && fill in credentials
    2. pip install -e ".[dev]"
    3. pip install langchain-core==0.3.83 --force-reinstall
    4. Start MCP Toolbox in a separate terminal:
       source .env && export LOOKER_INSTANCE_URL LOOKER_CLIENT_ID LOOKER_CLIENT_SECRET
       ./toolbox --tools-file config/tools.yaml
"""

import asyncio
import os
import sys

from dotenv import load_dotenv, find_dotenv

REQUIRED_LANGCHAIN_CORE = "0.3.83"

REQUIRED_ENV_VARS = [
    "CIBIS_CONSUMER_KEY",
    "CIBIS_CONSUMER_SECRET",
    "CIBIS_CONFIGURATION_ID",
    "CONFIG_PATH",
    "LOOKER_INSTANCE_URL",
    "LOOKER_CLIENT_ID",
    "LOOKER_CLIENT_SECRET",
]


def check_env() -> bool:
    """Check 1: All environment variables present."""
    load_dotenv(find_dotenv())
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        print(f"  FAIL  Missing: {', '.join(missing)}")
        print(f"        Copy .env.example → .env and fill in values.")
        return False
    print(f"  OK    All {len(REQUIRED_ENV_VARS)} env vars set")
    return True


def check_langchain_core() -> bool:
    """Check 2: langchain-core pinned to exact version SafeChain needs."""
    try:
        import langchain_core
        version = langchain_core.__version__
        if version != REQUIRED_LANGCHAIN_CORE:
            print(f"  FAIL  langchain-core=={version} (need {REQUIRED_LANGCHAIN_CORE})")
            print(f"        Fix: pip install langchain-core=={REQUIRED_LANGCHAIN_CORE} --force-reinstall")
            return False
        print(f"  OK    langchain-core=={version}")
        return True
    except ImportError:
        print("  FAIL  langchain-core not installed")
        return False


def check_safechain_config():
    """Check 3: SafeChain loads CIBIS credentials."""
    try:
        from ee_config.config import Config
        config = Config.from_env()
        print("  OK    SafeChain config loaded (CIBIS auth resolved)")
        return config
    except ImportError:
        print("  FAIL  ee_config not installed (install from internal PyPI)")
        return None
    except Exception as e:
        print(f"  FAIL  Config.from_env(): {e}")
        return None


async def check_mcp_tools(config) -> list | None:
    """Check 4: MCP Toolbox server reachable, Looker tools load."""
    try:
        from safechain.tools.mcp import MCPToolLoader
        tools = await MCPToolLoader.load_tools(config)
        names = [t.name for t in tools]
        print(f"  OK    {len(tools)} tools: {', '.join(names)}")
        return tools
    except Exception as e:
        print(f"  FAIL  MCPToolLoader: {e}")
        print("        Is MCP Toolbox running? In another terminal:")
        print("          source .env && export LOOKER_INSTANCE_URL LOOKER_CLIENT_ID LOOKER_CLIENT_SECRET")
        print("          ./toolbox --tools-file config/tools.yaml")
        return None


async def check_llm_call(config, tools) -> bool:
    """Check 5: Gemini responds through SafeChain with tool access."""
    try:
        from safechain.tools.mcp import MCPToolAgent
        from langchain_core.messages import SystemMessage, HumanMessage

        # model_id comes from config.yml, not .env
        model_id = (
            getattr(config, "model_id", None)
            or getattr(config, "model", None)
            or getattr(config, "llm_model", None)
            or "gemini-pro"
        )

        agent = MCPToolAgent(model_id, tools)
        result = await agent.ainvoke([
            SystemMessage(content="You are a helpful assistant. Be concise."),
            HumanMessage(content="Say 'Cortex ready' and nothing else."),
        ])

        response = result.get("content", str(result)) if isinstance(result, dict) else getattr(result, "content", str(result))
        print(f"  OK    model={model_id} → \"{response.strip()[:80]}\"")
        return True
    except Exception as e:
        print(f"  FAIL  LLM call: {e}")
        print("        Check: VPN connected? CIBIS creds valid? model_id in config.yml?")
        return False


async def main():
    print()
    print("Cortex Setup Verification")
    print("=" * 50)
    passed = 0

    # Check 1
    print("\n[1/5] Environment variables")
    if check_env():
        passed += 1

    # Check 2
    print("\n[2/5] langchain-core version")
    if check_langchain_core():
        passed += 1

    # Check 3
    print("\n[3/5] SafeChain configuration")
    config = check_safechain_config()
    if config:
        passed += 1

    # Check 4 (needs config)
    print("\n[4/5] MCP Toolbox + Looker tools")
    tools = None
    if config:
        tools = await check_mcp_tools(config)
        if tools:
            passed += 1
    else:
        print("  SKIP  (config failed)")

    # Check 5 (needs config + tools)
    print("\n[5/5] Gemini LLM call")
    if config and tools:
        if await check_llm_call(config, tools):
            passed += 1
    else:
        print("  SKIP  (earlier checks failed)")

    # Summary
    print()
    print("=" * 50)
    if passed == 5:
        print(f"PASSED  {passed}/5 — You're ready to build Cortex.")
    else:
        print(f"FAILED  {passed}/5 — Fix the issues above and re-run.")
    print()

    sys.exit(0 if passed == 5 else 1)


if __name__ == "__main__":
    asyncio.run(main())
