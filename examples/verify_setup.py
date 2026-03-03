#!/usr/bin/env python3
"""Verify your Cortex development environment.

Run this once after setup. If all checks pass, you're ready to build.

Usage:
    python examples/verify_setup.py

Prerequisites:
    1. cp .env.example .env && fill in credentials
    2. pip install -e ".[dev]"
"""

import os
import sys

from dotenv import load_dotenv, find_dotenv

REQUIRED_ENV_VARS = [
    "LOOKER_INSTANCE_URL",
    "LOOKER_CLIENT_ID",
    "LOOKER_CLIENT_SECRET",
]


def check_env() -> bool:
    """Check 1: Required environment variables present."""
    load_dotenv(find_dotenv())
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        print(f"  FAIL  Missing: {', '.join(missing)}")
        print("        Copy .env.example -> .env and fill in values.")
        return False
    print(f"  OK    All {len(REQUIRED_ENV_VARS)} env vars set")
    return True


def check_deps() -> bool:
    """Check 2: Core dependencies installed."""
    checks = {
        "google.adk": "google-adk",
        "pydantic": "pydantic",
        "neo4j": "neo4j",
        "yaml": "pyyaml",
        "httpx": "httpx",
    }
    missing = []
    for module, package in checks.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print(f"  FAIL  Missing packages: {', '.join(missing)}")
        print('        Fix: pip install -e ".[dev]"')
        return False
    print(f"  OK    All {len(checks)} core packages installed")
    return True


def check_neo4j() -> bool:
    """Check 3: Neo4j reachable (if configured)."""
    uri = os.getenv("NEO4J_URI")
    if not uri:
        print("  SKIP  NEO4J_URI not set (optional for initial setup)")
        return True
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            uri,
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "")),
        )
        driver.verify_connectivity()
        driver.close()
        print(f"  OK    Neo4j reachable at {uri}")
        return True
    except Exception as e:
        print(f"  FAIL  Neo4j: {e}")
        print("        Run: docker compose up neo4j")
        return False


def main():
    print()
    print("Cortex Setup Verification")
    print("=" * 50)
    passed = 0
    total = 3

    print("\n[1/3] Environment variables")
    if check_env():
        passed += 1

    print("\n[2/3] Core dependencies")
    if check_deps():
        passed += 1

    print("\n[3/3] Neo4j connectivity")
    if check_neo4j():
        passed += 1

    print()
    print("=" * 50)
    if passed == total:
        print(f"PASSED  {passed}/{total} — You're ready to build.")
    else:
        print(f"FAILED  {passed}/{total} — Fix the issues above and re-run.")
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
