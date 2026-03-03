# ADR-001: ADK over LangGraph for Agent Orchestration

**Date:** February 25, 2026  
**Status:** Accepted  
**Decider:** Saheb  
**Consulted:** Sulabh, Abhishek

---

## Decision

We will use Google's Agent Development Kit (ADK) as our agent orchestration framework instead of LangGraph.

## Context

We need an agent framework to orchestrate the Cortex pipeline: intent classification → entity resolution → SQL generation via Looker → validation → execution. Our PoC was built on LangGraph with a system prompt connecting to a local Looker MCP server.

Two options were evaluated:

| Criteria | LangGraph | ADK |
|----------|-----------|-----|
| GCP ecosystem alignment | Partial (works on GCP but not native) | Native (Vertex AI, Cloud Run, Agent Engine) |
| Looker MCP Toolbox integration | Works (MCP is protocol-level) | Works + Google's own blog shows this exact pattern |
| Team learning curve | Steep (graph theory, state machines) | Moderate (simpler agent + tools model) |
| Framework complexity | Heavy — designed for complex multi-agent state machines | Lighter — designed for tool-calling agents |
| Maturity | More mature, larger community | Newer, but backed by Google |
| Our use case fit | Overkill — our orchestrator is a thin sequential pipeline | Right-sized — agent with tools and sessions |
| Vendor story for leadership | "We used an open-source framework" | "We built on Google's AI agent stack on Google's cloud with Google's semantic layer" |
| Reversibility | Can swap in ~1 week | Can swap in ~1 week |

## Rationale

1. **Strategic alignment:** We're on GCP, using Looker (Google's product), with BigQuery (Google's product). ADK completes the Google stack. This is the story Jeff tells upward: "We built the blessed path."

2. **Right-sized complexity:** Our orchestrator is thin — classify intent, resolve entities, call MCP tools, validate, return. We don't need LangGraph's state machines, parallel execution, or complex branching. ADK's agent + tools model matches our pattern.

3. **Team capability:** Mixed skill levels. LangGraph requires understanding graph theory and state machines. ADK's model (agent has tools, agent calls tools) is more intuitive for the team.

4. **MCP Toolbox is framework-agnostic:** The heavy lifting — Looker integration, SQL generation, model introspection — happens via MCP protocol. The orchestrator is just glue code. If ADK doesn't work out, we swap the glue in a week without touching the MCP tools.

5. **Google's December 2025 blog post** literally shows ADK + MCP Toolbox + Looker for exactly this use case (NL → semantic layer → SQL). We're following a proven pattern.

## Consequences

- PoC needs rewrite from LangGraph to ADK (~1-2 days, intelligence is in prompts not framework)
- Team needs ADK onboarding (simpler than LangGraph onboarding would have been)
- Smaller community for troubleshooting vs LangGraph
- Risk: ADK is newer and may have gaps; mitigated by thin orchestrator layer

## Risk Hedge

If ADK has blocking issues, we can swap to LangGraph in under a week because:
- MCP Toolbox tools don't change (protocol-level, framework-agnostic)
- Business term registry doesn't change (YAML config)
- Intent classifier doesn't change (standalone LLM call)
- Entity resolver doesn't change (standalone logic)
- Only the orchestrator glue code changes
