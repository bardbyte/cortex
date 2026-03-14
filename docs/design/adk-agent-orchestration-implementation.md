# ADK Agent Orchestration: Implementation Architecture

**Author:** Saheb | **Date:** March 13, 2026 | **Status:** Implementation-Ready
**Audience:** Likhita (intent classification), Rajesh/Ravikanth (tools + integration), Saheb (orchestrator + SafeChain)
**Pre-reads:** [Agentic Orchestration Design](./agentic-orchestration-design.md), [ADR-001](../../adr/001-adk-over-langgraph.md)

---

## 0. Critical Finding: SafeChain x ADK Integration

**THE ANSWER: ADK supports custom model backends via `BaseLlm`.** ADK's `Agent` (alias for `LlmAgent`) accepts either a model name string (e.g., `"gemini-2.0-flash"`) or a `BaseLlm` instance. ADK ships with `LiteLlm`, `Gemma`, etc. as concrete implementations. We build `SafeChainLlm(BaseLlm)` that routes all LLM calls through SafeChain's CIBIS-authenticated gateway.

This is the adapter pattern, not the composition pattern. ADK IS the orchestrator. SafeChain IS the model backend. They compose cleanly.

```
ADK Agent orchestrates tool calls and flow
         |
         v
  SafeChainLlm (BaseLlm adapter)
         |
         v
  MCPToolAgent.ainvoke() under the hood
         |
         v
  SafeChain Gateway (CIBIS auth) --> Gemini
```

**Fallback plan:** If `BaseLlm.generate_content_async()` signature is incompatible with SafeChain's response format (risk: medium), we fall back to LiteLLM wrapping a local proxy that calls SafeChain. This is the 1-week escape hatch from ADR-001.

---

## 1. SafeChain x ADK Adapter (THE HARDEST PART)

### 1.1 SafeChainLlm: The Bridge

```python
# src/connectors/safechain_llm.py
"""ADK BaseLlm adapter that routes all LLM calls through SafeChain.

This is the critical integration point. ADK's LlmAgent calls
generate_content_async() on whatever BaseLlm you give it. We give it
this class, which translates ADK's content format to LangChain messages,
calls SafeChain's MCPToolAgent, and translates back.

Why not use LiteLLM?
  LiteLLM needs an OpenAI-compatible endpoint. SafeChain is NOT
  OpenAI-compatible -- it uses CIBIS auth + custom response format.
  Building a proxy to make SafeChain look like OpenAI is more code
  and more failure modes than building this adapter.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai.types import Content, Part, FunctionCall, FunctionResponse
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage,
)
from safechain.tools.mcp import MCPToolAgent
from ee_config.config import Config

logger = logging.getLogger(__name__)


class SafeChainLlm(BaseLlm):
    """ADK-compatible LLM that routes through SafeChain's CIBIS gateway.

    Translation layers:
      ADK Content/Part  -->  LangChain Messages  -->  SafeChain MCPToolAgent
      SafeChain result  -->  LangChain Messages  -->  ADK LlmResponse

    The MCPToolAgent handles:
      - CIBIS authentication (token refresh, cert pinning)
      - Model routing (model_id -> SafeChain endpoint)
      - Response streaming (if supported by the SafeChain endpoint)

    We handle:
      - Format translation (ADK <-> LangChain)
      - Tool call extraction from SafeChain responses
      - Error wrapping (SafeChain errors -> ADK-expected format)
    """

    def __init__(
        self,
        model_id: str,
        config: Config | None = None,
        mcp_tools: list | None = None,
    ):
        """Initialize the SafeChain LLM adapter.

        Args:
            model_id: SafeChain model identifier (e.g., "gemini-2.5-flash").
                Maps to a SafeChain endpoint via CIBIS config.
            config: Pre-loaded SafeChain config. If None, loads from env.
            mcp_tools: MCP tools to bind. For intent classification,
                pass empty list (no tools needed). For ReAct execution,
                pass Looker MCP tools.
        """
        self._model_id = model_id
        self._config = config
        self._mcp_tools = mcp_tools or []
        self._agent: MCPToolAgent | None = None

    @property
    def model(self) -> str:
        return self._model_id

    @classmethod
    def supported_models(cls) -> list[str]:
        """Models available through SafeChain at Amex."""
        return [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ]

    async def connect(self) -> None:
        """Initialize SafeChain connection and MCPToolAgent."""
        if self._agent is not None:
            return

        if self._config is None:
            self._config = Config.from_env()

        self._agent = MCPToolAgent(self._model_id, self._mcp_tools)
        logger.info(
            "SafeChainLlm connected: model=%s, tools=%d",
            self._model_id, len(self._mcp_tools),
        )

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
    ) -> AsyncGenerator[LlmResponse, None]:
        """Translate ADK request -> SafeChain call -> ADK response.

        ADK calls this method in its internal LLM flow. We:
          1. Convert ADK Content objects to LangChain messages
          2. Call SafeChain's MCPToolAgent.ainvoke()
          3. Convert the response back to ADK LlmResponse format
          4. Yield as an async generator (ADK expects streaming interface)

        Args:
            llm_request: ADK's request object containing:
                - contents: list[Content] (conversation history)
                - config: GenerateContentConfig (temperature, tools, etc.)

        Yields:
            LlmResponse with either text content or tool calls.
        """
        await self.connect()

        # Step 1: Convert ADK contents to LangChain messages
        lc_messages = self._adk_to_langchain(llm_request.contents)

        # Step 2: Inject system instruction if present
        if llm_request.config and llm_request.config.system_instruction:
            sys_text = _extract_text(llm_request.config.system_instruction)
            if sys_text:
                lc_messages.insert(0, SystemMessage(content=sys_text))

        # Step 3: Call SafeChain
        try:
            result = await self._agent.ainvoke(lc_messages)
        except Exception as e:
            logger.error("SafeChain call failed: %s", e)
            # Return error as text response -- ADK will handle
            yield LlmResponse(
                content=Content(
                    role="model",
                    parts=[Part(text=f"LLM error: {e}")],
                ),
            )
            return

        # Step 4: Translate SafeChain response to ADK format
        llm_response = self._safechain_to_adk(result)
        yield llm_response

    # -- Format Translation Methods --

    @staticmethod
    def _adk_to_langchain(contents: list[Content]) -> list:
        """Convert ADK Content objects to LangChain message objects.

        ADK Content structure:
          Content(role="user"|"model", parts=[Part(text=...), Part(function_call=...)])

        LangChain expects:
          HumanMessage, AIMessage, ToolMessage, SystemMessage
        """
        messages = []
        for content in contents:
            text_parts = [p.text for p in content.parts if p.text]
            combined_text = "\n".join(text_parts) if text_parts else ""

            if content.role == "user":
                messages.append(HumanMessage(content=combined_text))
            elif content.role == "model":
                # Check for function calls
                fn_calls = [p.function_call for p in content.parts if p.function_call]
                if fn_calls:
                    # AIMessage with tool_calls
                    messages.append(AIMessage(
                        content=combined_text,
                        additional_kwargs={
                            "tool_calls": [
                                {
                                    "id": f"call_{fc.name}",
                                    "function": {
                                        "name": fc.name,
                                        "arguments": str(fc.args),
                                    },
                                    "type": "function",
                                }
                                for fc in fn_calls
                            ]
                        },
                    ))
                else:
                    messages.append(AIMessage(content=combined_text))

            # Handle function responses (tool results)
            fn_responses = [
                p.function_response for p in content.parts
                if p.function_response
            ]
            for fr in fn_responses:
                messages.append(ToolMessage(
                    content=str(fr.response),
                    tool_call_id=f"call_{fr.name}",
                    name=fr.name,
                ))

        return messages

    @staticmethod
    def _safechain_to_adk(result) -> LlmResponse:
        """Convert SafeChain MCPToolAgent result to ADK LlmResponse.

        SafeChain returns one of:
          - dict with "content" (str) and optional "tool_results" (list)
          - AIMessage with content and optional tool_calls
          - str (rare, fallback)

        ADK expects:
          LlmResponse with Content(role="model", parts=[...])
        """
        parts = []

        if isinstance(result, dict):
            content_text = result.get("content", "")
            tool_results = result.get("tool_results", [])

            if content_text:
                parts.append(Part(text=content_text))

            for tr in tool_results:
                tool_name = tr.get("tool", "")
                if "error" in tr:
                    parts.append(Part(function_response=FunctionResponse(
                        name=tool_name,
                        response={"error": tr["error"]},
                    )))
                else:
                    parts.append(Part(function_response=FunctionResponse(
                        name=tool_name,
                        response={"result": tr.get("result", "")},
                    )))
        elif hasattr(result, "content"):
            parts.append(Part(text=str(result.content)))
            # Check for tool_calls on AIMessage
            if hasattr(result, "tool_calls"):
                for tc in result.tool_calls:
                    parts.append(Part(function_call=FunctionCall(
                        name=tc.get("name", ""),
                        args=tc.get("args", {}),
                    )))
        else:
            parts.append(Part(text=str(result)))

        return LlmResponse(
            content=Content(role="model", parts=parts),
        )


def _extract_text(content) -> str:
    """Extract text from a Content or string."""
    if isinstance(content, str):
        return content
    if hasattr(content, "parts"):
        return "\n".join(p.text for p in content.parts if p.text)
    return str(content)
```

### 1.2 Model Factory

```python
# src/connectors/safechain_client.py (REPLACES the stub)
"""SafeChain LLM client -- authenticates Cortex to call Gemini.

All LLM access at Amex goes through SafeChain (CIBIS authentication).
This module provides factory functions for the three LLM configurations
Cortex needs:

  1. classifier_llm: Gemini Flash, no tools (intent classification)
  2. react_llm: Gemini Flash, with Looker MCP tools (SQL generation)
  3. reasoning_llm: Gemini Pro, no tools (complex disambiguation)

Each returns a SafeChainLlm instance ready for ADK Agent(model=...).
"""

from __future__ import annotations

import os
import logging
from typing import Any

from ee_config.config import Config
from safechain.tools.mcp import MCPToolLoader

from src.connectors.safechain_llm import SafeChainLlm

logger = logging.getLogger(__name__)

# Model IDs -- these map to SafeChain endpoints via CIBIS config
MODEL_FLASH = os.getenv("CORTEX_MODEL_FLASH", "gemini-2.5-flash")
MODEL_PRO = os.getenv("CORTEX_MODEL_PRO", "gemini-2.5-pro")


async def get_config() -> Config:
    """Load SafeChain config with CIBIS authentication.

    Reads from .env:
      CIBIS_CLIENT_ID, CIBIS_CLIENT_SECRET, CIBIS_TOKEN_URL,
      SAFECHAIN_ENDPOINT, MCP_TOOLBOX_URL
    """
    config = Config.from_env()
    logger.info("SafeChain config loaded (model: %s)", getattr(config, 'model_id', 'unknown'))
    return config


async def create_classifier_llm(config: Config | None = None) -> SafeChainLlm:
    """LLM for intent classification -- fast, no tools.

    Uses Gemini Flash for speed (~200ms). No MCP tools bound because
    classification is a single prompt-in, JSON-out call.
    """
    if config is None:
        config = await get_config()
    llm = SafeChainLlm(model_id=MODEL_FLASH, config=config, mcp_tools=[])
    await llm.connect()
    return llm


async def create_react_llm(config: Config | None = None) -> SafeChainLlm:
    """LLM for ReAct execution -- has Looker MCP tools.

    Uses Gemini Flash with Looker MCP tools bound. The augmented prompt
    tells the agent exactly which fields to query, so it goes straight
    to query_sql (1 tool call instead of 5-6 discovery calls).
    """
    if config is None:
        config = await get_config()
    tools = await MCPToolLoader.load_tools(config)
    llm = SafeChainLlm(model_id=MODEL_FLASH, config=config, mcp_tools=tools)
    await llm.connect()
    return llm


async def create_reasoning_llm(config: Config | None = None) -> SafeChainLlm:
    """LLM for complex reasoning -- higher accuracy, slower.

    Uses Gemini Pro for tasks where accuracy matters more than speed:
      - Ambiguous disambiguation (top-2 explores within threshold)
      - Multi-entity queries with conflicting signals
      - Response formatting for complex results

    No tools -- reasoning LLM only processes text.
    """
    if config is None:
        config = await get_config()
    llm = SafeChainLlm(model_id=MODEL_PRO, config=config, mcp_tools=[])
    await llm.connect()
    return llm
```

---

## 2. ADK Agent Architecture

### 2.1 Agent Hierarchy

```
cortex_agent (root -- BaseAgent, custom orchestration)
    |
    +-- Phase 1: Pre-processing (deterministic, custom _run_async_impl)
    |   |-- classify_intent tool (1 LLM call via classifier sub-agent)
    |   |-- retrieve_fields tool (0 LLM calls, deterministic)
    |   |-- resolve_filters tool (0 LLM calls, deterministic)
    |   |-- validate_query tool (0 LLM calls, deterministic)
    |
    +-- Phase 2: Execution (LlmAgent, 1-2 LLM calls)
    |   |-- query_agent (LlmAgent with Looker MCP tools)
    |
    +-- Phase 3: Response (LlmAgent, 1 LLM call)
    |   |-- response_agent (LlmAgent, formats results)
    |
    +-- Special flows (delegated from Phase 1 based on retrieval action)
        |-- disambiguation_agent (LlmAgent, presents options)
        |-- clarification_agent (LlmAgent, asks for rephrasing)
        |-- boundary_agent (LlmAgent, graceful out-of-scope)
```

### 2.2 Root Agent: CortexAgent (Custom BaseAgent)

```python
# src/pipeline/agent.py (REPLACES the stub)
"""Cortex root agent -- custom BaseAgent that orchestrates the NL2SQL pipeline.

WHY custom BaseAgent instead of LlmAgent:
  LlmAgent gives the LLM control over which tools to call and in what order.
  But our pipeline is NOT LLM-driven -- it is a deterministic sequence with
  LLM calls at specific points. The LLM doesn't decide to "retrieve fields" --
  the pipeline always retrieves fields after classification.

  Custom BaseAgent gives us:
    1. Deterministic pipeline sequencing (classify -> retrieve -> filter -> validate)
    2. Conditional routing (disambiguate | clarify | proceed | out_of_scope)
    3. Streaming events at each step (ThinkingEvents for frontend)
    4. Per-step latency tracking (PipelineTrace)
    5. Graceful fallback (any step fails -> fall through to PoC behavior)

  The LLM-driven parts (query execution, response formatting) are delegated
  to LlmAgent sub-agents that ADK orchestrates normally.

Architecture:
  CortexAgent._run_async_impl():
    1. classify_intent() -> ClassificationResult
    2. Route based on intent:
       - out_of_scope -> yield to boundary_agent
       - schema_browse/saved_content -> yield to query_agent (passthrough)
       - data_query:
         a. retrieve_fields() -> RetrievalResult
         b. Route based on action:
            - disambiguate -> yield to disambiguation_agent
            - clarify -> yield to clarification_agent
            - proceed:
              i.   resolve_filters() -> resolved filters
              ii.  validate_query() -> ValidationResult
              iii. yield to query_agent (augmented prompt)
              iv.  yield to response_agent (format results)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.tools import FunctionTool

from src.pipeline.tools import (
    classify_intent,
    retrieve_fields,
    resolve_filters,
    validate_query,
)
from src.pipeline.sub_agents import (
    create_query_agent,
    create_response_agent,
    create_disambiguation_agent,
    create_clarification_agent,
    create_boundary_agent,
)
from src.pipeline.trace import PipelineTrace, StepTrace, TraceBuilder
from src.pipeline.state import CortexState
from src.pipeline.events import (
    PipelineStepEvent,
    StepStatus,
)

logger = logging.getLogger(__name__)


class CortexAgent(BaseAgent):
    """Root agent for the Cortex NL2SQL pipeline.

    Orchestrates the deterministic pipeline, delegates to LlmAgent
    sub-agents for LLM-driven steps.
    """

    def __init__(
        self,
        *,
        query_agent: LlmAgent,
        response_agent: LlmAgent,
        disambiguation_agent: LlmAgent,
        clarification_agent: LlmAgent,
        boundary_agent: LlmAgent,
        retrieval_orchestrator,  # RetrievalOrchestrator instance
        embed_fn,                # Callable[[str], list[float]]
        pg_conn,                 # psycopg connection
        taxonomy_terms: list[str] | None = None,
    ):
        super().__init__(
            name="cortex",
            description="Cortex NL2SQL pipeline -- translates natural language to SQL via Looker.",
            sub_agents=[
                query_agent,
                response_agent,
                disambiguation_agent,
                clarification_agent,
                boundary_agent,
            ],
        )
        self._query_agent = query_agent
        self._response_agent = response_agent
        self._disambiguation_agent = disambiguation_agent
        self._clarification_agent = clarification_agent
        self._boundary_agent = boundary_agent
        self._retrieval = retrieval_orchestrator
        self._embed_fn = embed_fn
        self._pg_conn = pg_conn
        self._taxonomy_terms = taxonomy_terms or []

    async def _run_async_impl(
        self, ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        """Execute the Cortex pipeline.

        This is the core orchestration loop. Every step emits events
        that the ADK runner surfaces to the frontend via SSE.
        """
        trace = TraceBuilder(query=_get_user_query(ctx))
        state = ctx.session.state

        # ============================================================
        # PHASE 1: PRE-PROCESSING (deterministic, 1 LLM call max)
        # ============================================================

        # -- Step 1: Intent Classification --
        yield PipelineStepEvent(step="classify_intent", status=StepStatus.STARTED)
        step_start = time.monotonic()

        try:
            classification = await classify_intent(
                query=_get_user_query(ctx),
                history=_get_history(ctx),
                taxonomy_terms=self._taxonomy_terms,
                ctx=ctx,
            )
        except Exception as e:
            logger.warning("Classification failed: %s -- falling through to raw query", e)
            yield PipelineStepEvent(
                step="classify_intent",
                status=StepStatus.FAILED,
                detail=str(e),
            )
            # Fallback: treat as data_query, skip retrieval
            async for event in self._query_agent.run_async(ctx):
                yield event
            return

        trace.add_step(
            "classify_intent",
            {"query": _get_user_query(ctx)},
            {
                "intent": classification.intent,
                "confidence": classification.confidence,
                "entities": classification.entities.__dict__,
            },
            decision=classification.intent,
            confidence=classification.confidence,
        )
        yield PipelineStepEvent(
            step="classify_intent",
            status=StepStatus.COMPLETED,
            detail=f"intent={classification.intent} ({classification.confidence:.0%})",
            duration_ms=(time.monotonic() - step_start) * 1000,
        )

        # -- Route based on intent --
        if classification.intent == "out_of_scope":
            state["classification"] = classification
            async for event in self._boundary_agent.run_async(ctx):
                yield event
            return

        if classification.intent in ("schema_browse", "saved_content"):
            # Passthrough to query agent -- let LLM discover via MCP tools
            async for event in self._query_agent.run_async(ctx):
                yield event
            return

        # -- Step 2: Hybrid Retrieval --
        yield PipelineStepEvent(step="retrieve_fields", status=StepStatus.STARTED)
        step_start = time.monotonic()

        entities_dict = {
            "metrics": classification.entities.metrics,
            "dimensions": classification.entities.dimensions,
            "filters": classification.entities.filters,
            "time_range": classification.entities.time_range,
        }

        retrieval_result = retrieve_fields(
            entities=entities_dict,
            retrieval_orchestrator=self._retrieval,
        )

        trace.add_step(
            "retrieve_fields",
            {"entities": entities_dict},
            {
                "action": retrieval_result.action,
                "model": retrieval_result.model,
                "explore": retrieval_result.explore,
                "dimensions": retrieval_result.dimensions,
                "measures": retrieval_result.measures,
                "confidence": retrieval_result.confidence,
            },
            decision=retrieval_result.action,
            confidence=retrieval_result.confidence,
        )
        yield PipelineStepEvent(
            step="retrieve_fields",
            status=StepStatus.COMPLETED,
            detail=(
                f"action={retrieval_result.action} "
                f"explore={retrieval_result.explore} "
                f"confidence={retrieval_result.confidence:.0%}"
            ),
            duration_ms=(time.monotonic() - step_start) * 1000,
        )

        # -- Route based on retrieval action --
        if retrieval_result.action == "disambiguate":
            state["retrieval_result"] = retrieval_result
            state["alternatives"] = retrieval_result.alternatives
            async for event in self._disambiguation_agent.run_async(ctx):
                yield event
            return

        if retrieval_result.action == "clarify":
            state["retrieval_result"] = retrieval_result
            async for event in self._clarification_agent.run_async(ctx):
                yield event
            return

        if retrieval_result.action == "no_match":
            state["retrieval_result"] = retrieval_result
            async for event in self._clarification_agent.run_async(ctx):
                yield event
            return

        # -- Step 3: Filter Resolution --
        yield PipelineStepEvent(step="resolve_filters", status=StepStatus.STARTED)
        step_start = time.monotonic()

        resolved_filters = resolve_filters(
            entities=classification.entities,
            explore_name=retrieval_result.explore,
        )
        retrieval_result.filters = resolved_filters

        trace.add_step(
            "resolve_filters",
            {"raw_filters": classification.entities.filters},
            {"resolved_filters": resolved_filters},
            decision="proceed",
        )
        yield PipelineStepEvent(
            step="resolve_filters",
            status=StepStatus.COMPLETED,
            detail=f"filters={resolved_filters}",
            duration_ms=(time.monotonic() - step_start) * 1000,
        )

        # -- Step 4: Pre-execution Validation --
        yield PipelineStepEvent(step="validate_query", status=StepStatus.STARTED)
        step_start = time.monotonic()

        validation = validate_query(retrieval_result)

        trace.add_step(
            "validate_query",
            {"retrieval_result": retrieval_result.__dict__},
            {"valid": validation.valid, "issues": validation.issues},
            decision="proceed" if validation.valid else "blocked",
        )
        yield PipelineStepEvent(
            step="validate_query",
            status=StepStatus.COMPLETED if validation.valid else StepStatus.FAILED,
            detail=f"valid={validation.valid} issues={validation.issues}",
            duration_ms=(time.monotonic() - step_start) * 1000,
        )

        if not validation.valid and validation.blocking:
            # Hard stop -- usually missing partition filter
            state["validation"] = validation
            yield PipelineStepEvent(
                step="pipeline",
                status=StepStatus.BLOCKED,
                detail=f"Query blocked: {validation.issues}",
            )
            return

        # ============================================================
        # PHASE 2: EXECUTION (LLM-driven, 1-2 calls)
        # ============================================================

        # Inject retrieval context into session state for query_agent
        state["retrieval_result"] = retrieval_result.__dict__
        state["augmented_prompt"] = _build_augmented_prompt(retrieval_result)
        state["trace"] = trace

        yield PipelineStepEvent(step="query_execution", status=StepStatus.STARTED)

        async for event in self._query_agent.run_async(ctx):
            yield event

        yield PipelineStepEvent(step="query_execution", status=StepStatus.COMPLETED)

        # ============================================================
        # PHASE 3: RESPONSE (LLM-driven, 1 call)
        # ============================================================

        yield PipelineStepEvent(step="format_response", status=StepStatus.STARTED)

        async for event in self._response_agent.run_async(ctx):
            yield event

        # Emit final trace
        pipeline_trace = trace.build()
        state["pipeline_trace"] = pipeline_trace.to_dict()

        yield PipelineStepEvent(
            step="pipeline",
            status=StepStatus.COMPLETED,
            detail=f"total={pipeline_trace.total_duration_ms:.0f}ms",
        )


# -- Helpers --

def _get_user_query(ctx: InvocationContext) -> str:
    """Extract the user's query from the invocation context."""
    if ctx.user_content and ctx.user_content.parts:
        return ctx.user_content.parts[0].text or ""
    return ""


def _get_history(ctx: InvocationContext) -> list[dict]:
    """Extract conversation history from session state."""
    return ctx.session.state.get("conversation_history", [])


def _build_augmented_prompt(retrieval_result) -> str:
    """Build the augmented system prompt for the query agent.

    This is the magic -- we tell the LLM exactly which model, explore,
    dimensions, measures, and filters to use. No discovery needed.
    """
    from src.pipeline.prompts import AUGMENTED_PROMPT_TEMPLATE

    fewshot_match = (
        retrieval_result.fewshot_matches[0]
        if retrieval_result.fewshot_matches
        else "none"
    )

    return AUGMENTED_PROMPT_TEMPLATE.format(
        confidence=retrieval_result.confidence,
        model=retrieval_result.model,
        explore=retrieval_result.explore,
        dimensions=", ".join(retrieval_result.dimensions) or "(none)",
        measures=", ".join(retrieval_result.measures) or "(none)",
        filters=retrieval_result.filters,
        fewshot_match=fewshot_match,
    )
```

---

## 3. Tool Definitions (ADK FunctionTools)

### 3.1 classify_intent

```python
# src/pipeline/tools.py
"""Pipeline stage tools -- each wraps a pipeline step as an ADK-callable function.

These are NOT LlmAgent tools (the LLM doesn't choose when to call them).
They are called directly by CortexAgent._run_async_impl() at deterministic
points in the pipeline. They are defined as functions (not FunctionTools)
because CortexAgent calls them directly, not through the ADK tool-calling
mechanism.

Exception: For the query_agent sub-agent, we wrap validate_sql as a
FunctionTool so the LLM can call it after receiving SQL from Looker MCP.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.retrieval.orchestrator import RetrievalOrchestrator
from src.retrieval.models import RetrievalResult
from src.retrieval import filters as filter_module

logger = logging.getLogger(__name__)


# ---- Data Models for Tool I/O ----

@dataclass
class ExtractedEntities:
    """Structured entities extracted from user query."""
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    time_range: str | None = None
    sort: str | None = None
    limit: int | None = None


@dataclass
class ClassificationResult:
    """Output of intent classification."""
    intent: str       # data_query | schema_browse | saved_content | follow_up | out_of_scope
    confidence: float
    entities: ExtractedEntities
    reasoning: str


@dataclass
class ValidationResult:
    """Output of pre-execution query validation."""
    valid: bool
    issues: list[str] = field(default_factory=list)
    blocking: bool = False   # True = hard stop (missing partition filter)
    warnings: list[str] = field(default_factory=list)  # Non-blocking issues
    estimated_scan_gb: float | None = None


# ---- Tool: classify_intent ----

async def classify_intent(
    query: str,
    history: list[dict],
    taxonomy_terms: list[str],
    ctx: Any = None,
) -> ClassificationResult:
    """Classify user intent and extract structured entities.

    This is the ONE LLM call in Phase 1. Uses Gemini Flash for speed.

    The prompt includes:
      - Intent taxonomy (data_query, schema_browse, etc.)
      - Available business terms (from LookML descriptions + taxonomy)
      - Conversation history (for follow-up detection)
      - Few-shot examples (hardcoded, version-controlled)

    Returns structured ClassificationResult parsed from JSON response.

    Latency budget: 400ms (P95)
    """
    from src.pipeline.prompts import CLASSIFY_AND_EXTRACT_PROMPT
    import json

    # Build the classification prompt
    previous_context = ""
    if history:
        last_exchange = history[-2:]  # last user + assistant
        previous_context = "\n".join(
            f"{m['role']}: {m['content']}" for m in last_exchange
        )

    prompt = CLASSIFY_AND_EXTRACT_PROMPT.format(
        taxonomy_terms="\n".join(f"- {t}" for t in taxonomy_terms[:50]),
        previous_context=previous_context or "(first message in conversation)",
        query=query,
    )

    # Call LLM via the classifier sub-agent in session state
    # The actual LLM call is made by a lightweight LlmAgent
    # configured with SafeChainLlm (Flash, no tools)
    from google.adk.agents import LlmAgent
    from google.genai.types import Content, Part

    classifier = ctx.session.state.get("_classifier_agent")
    if classifier is None:
        raise RuntimeError("Classifier agent not in session state -- check initialization")

    # Single LLM call: prompt in, JSON out
    response_text = ""
    async for event in classifier.run_async(ctx):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text

    # Parse JSON response
    try:
        # Strip markdown code fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Classification JSON parse failed: %s", response_text[:200])
        # Fallback: treat as data_query with raw query as metric
        return ClassificationResult(
            intent="data_query",
            confidence=0.5,
            entities=ExtractedEntities(metrics=[query]),
            reasoning="JSON parse failed -- falling through as data_query",
        )

    entities = ExtractedEntities(
        metrics=data.get("entities", {}).get("metrics", []),
        dimensions=data.get("entities", {}).get("dimensions", []),
        filters=data.get("entities", {}).get("filters", {}),
        time_range=data.get("entities", {}).get("time_range"),
        sort=data.get("entities", {}).get("sort"),
        limit=data.get("entities", {}).get("limit"),
    )

    return ClassificationResult(
        intent=data.get("intent", "data_query"),
        confidence=data.get("confidence", 0.5),
        entities=entities,
        reasoning=data.get("reasoning", ""),
    )


# ---- Tool: retrieve_fields ----

def retrieve_fields(
    entities: dict,
    retrieval_orchestrator: RetrievalOrchestrator,
) -> RetrievalResult:
    """Run hybrid retrieval pipeline. ZERO LLM calls.

    Calls the 10-step RetrievalOrchestrator:
      1. Per-entity vector search (pgvector)
      2. Confidence gate
      3. Near-miss detection
      4. Candidate collection for graph
      5. Structural validation (Apache AGE)
      6. Few-shot search (FAISS)
      7. Few-shot signal application
      8. Explore scoring + ranking
      9. Disambiguation check
     10. Field splitting + filter resolution

    Input: ExtractedEntities as dict
    Output: RetrievalResult with action, model, explore, dimensions, measures

    Latency budget: 260ms (P95)
    """
    return retrieval_orchestrator.retrieve(entities)


# ---- Tool: resolve_filters ----

def resolve_filters(
    entities: ExtractedEntities,
    explore_name: str,
) -> dict[str, str]:
    """Resolve raw user filter values to LookML-compatible expressions.

    ZERO LLM calls -- deterministic 5-pass resolution:
      Pass 1: Exact match (namespaced value map)
      Pass 2: Synonym expansion
      Pass 3: Fuzzy match (Levenshtein <= 2)
      Pass 4: Embedding similarity (TODO)
      Pass 5: Passthrough with low confidence

    Also handles:
      - Yesno dimensions ("enrolled" -> "Yes")
      - Negation ("not Gold" -> "-GOLD")
      - Numeric ranges ("between 1000 and 5000" -> "[1000,5000]")
      - Time normalization ("Q4 2025" -> "2025-10-01 to 2025-12-31")
      - Mandatory partition filter injection

    Input: ExtractedEntities + explore name
    Output: dict of {field_name: looker_filter_value}

    Latency budget: 15ms
    """
    # Build entities list in the format resolve_filters expects
    entity_list = []

    for dim_name, value in entities.filters.items():
        entity_list.append({
            "type": "filter",
            "name": dim_name,
            "values": [value],
            "operator": "=",
        })

    if entities.time_range:
        entity_list.append({
            "type": "time_range",
            "name": "time_range",
            "values": [entities.time_range],
        })

    result = filter_module.resolve_filters(entity_list, explore_name)
    return result.to_looker_filters()


# ---- Tool: validate_query ----

def validate_query(retrieval_result: RetrievalResult) -> ValidationResult:
    """Pre-execution validation. ZERO LLM calls.

    Five checks before we let Looker MCP execute:

    Check 1: Partition filter present (BLOCKING)
      Every explore in the finance model has ALWAYS_FILTER_ON pointing
      to a partition date dimension. Without it, BigQuery scans the
      full table -- $50K+ for our 5PB tables.

    Check 2: Dimensions + measures not empty
      An explore query with no fields is nonsensical. Usually means
      retrieval failed silently.

    Check 3: Model + explore resolved
      Must have non-empty model and explore names.

    Check 4: Field count sanity
      More than 20 dimensions or 10 measures is almost certainly wrong.
      Usually means retrieval returned noise.

    Check 5: Known-dangerous patterns (defense in depth)
      Check if any filter values contain SQL injection patterns.
      Should never happen via MCP (which parameterizes queries),
      but defense in depth.

    Returns ValidationResult with issues list and blocking flag.
    """
    issues = []
    warnings = []
    blocking = False

    # Check 1: Partition filter
    from src.retrieval.filters import EXPLORE_PARTITION_FIELDS
    partition_field = EXPLORE_PARTITION_FIELDS.get(
        retrieval_result.explore, "partition_date"
    )
    has_partition = partition_field in retrieval_result.filters
    if not has_partition:
        issues.append(
            f"MISSING PARTITION FILTER: {partition_field} not in filters. "
            f"This will cause a full table scan on {retrieval_result.explore}."
        )
        blocking = True

    # Check 2: Fields not empty
    if not retrieval_result.dimensions and not retrieval_result.measures:
        issues.append("No dimensions or measures resolved. Cannot generate query.")
        blocking = True

    # Check 3: Model + explore present
    if not retrieval_result.model:
        issues.append("Model name not resolved.")
        blocking = True
    if not retrieval_result.explore:
        issues.append("Explore name not resolved.")
        blocking = True

    # Check 4: Field count sanity
    if len(retrieval_result.dimensions) > 20:
        warnings.append(
            f"Unusually high dimension count ({len(retrieval_result.dimensions)}). "
            f"Check retrieval quality."
        )
    if len(retrieval_result.measures) > 10:
        warnings.append(
            f"Unusually high measure count ({len(retrieval_result.measures)}). "
            f"Check retrieval quality."
        )

    # Check 5: SQL injection patterns in filter values
    dangerous_patterns = [
        "DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ",
        "TRUNCATE ", "--", ";--", "/*", "*/", "xp_",
    ]
    for field_name, value in retrieval_result.filters.items():
        value_upper = str(value).upper()
        for pattern in dangerous_patterns:
            if pattern in value_upper:
                issues.append(
                    f"Dangerous pattern '{pattern.strip()}' detected in "
                    f"filter {field_name}='{value}'. Blocking execution."
                )
                blocking = True

    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
        blocking=blocking,
        warnings=warnings,
    )


# ---- Tool: validate_sql (FunctionTool for query_agent) ----

def validate_sql_post_execution(
    sql: str,
    retrieval_result_dict: dict,
) -> dict:
    """Post-execution SQL validation for the query_agent.

    This is exposed as an ADK FunctionTool because the query_agent
    (LlmAgent) calls Looker MCP's query_sql to GET the SQL, then
    calls this tool to validate it BEFORE calling query to execute.

    CRITICAL FINDING: Looker MCP has TWO separate tools:
      - query_sql: generates SQL only (returns SQL string, no execution)
      - query: executes and returns data

    Pipeline sequence in query_agent:
      1. LLM calls query_sql (Looker MCP) -> gets SQL
      2. LLM calls validate_sql_post_execution -> gets validation
      3. If valid: LLM calls query (Looker MCP) -> gets data
      4. If invalid: LLM reports issue (no execution)

    Checks:
      1. Partition filter in WHERE clause
      2. Expected fields appear in SELECT/GROUP BY
      3. No suspicious patterns
      4. Query is SELECT only (not DML)

    Returns dict for LLM consumption (not a dataclass -- ADK tools
    must return JSON-serializable types).
    """
    issues = []

    sql_upper = sql.upper().strip()

    # Must be a SELECT
    if not sql_upper.startswith("SELECT"):
        issues.append("Query is not a SELECT statement.")

    # Partition filter in WHERE
    if "WHERE" not in sql_upper:
        issues.append("No WHERE clause -- will scan entire table.")
    else:
        # Check for partition field reference
        partition_field = retrieval_result_dict.get("explore", "")
        from src.retrieval.filters import EXPLORE_PARTITION_FIELDS
        expected_partition = EXPLORE_PARTITION_FIELDS.get(partition_field, "partition_date")
        if expected_partition.upper() not in sql_upper:
            issues.append(
                f"Partition field '{expected_partition}' not found in WHERE clause."
            )

    # Check expected fields appear
    expected_dims = retrieval_result_dict.get("dimensions", [])
    expected_measures = retrieval_result_dict.get("measures", [])
    for field_name in expected_dims + expected_measures:
        if field_name.upper() not in sql_upper:
            issues.append(f"Expected field '{field_name}' not found in SQL.")

    # DML guard
    for dangerous in ["DROP ", "DELETE ", "UPDATE ", "INSERT ", "ALTER ", "TRUNCATE "]:
        if dangerous in sql_upper:
            issues.append(f"Dangerous SQL operation detected: {dangerous.strip()}")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "sql_length": len(sql),
        "recommendation": "proceed" if not issues else "do_not_execute",
    }
```

---

## 4. Sub-Agent Definitions

```python
# src/pipeline/sub_agents.py
"""ADK sub-agents for specialized flows.

Each sub-agent is a LlmAgent with a specific instruction and tool set.
CortexAgent delegates to these based on pipeline routing decisions.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from src.pipeline.tools import validate_sql_post_execution


# ---- Query Agent ----

QUERY_AGENT_INSTRUCTION = """You are a Looker query executor. Your job is to generate and validate SQL, then execute it.

## Retrieved Context
{augmented_prompt}

## Workflow
1. Call `query_sql` with the EXACT fields provided in the Retrieved Context above.
   - model_name: {model}
   - explore_name: {explore}
   - fields: {fields}
   - filters: {filters}
2. Take the SQL returned by query_sql and call `validate_sql_post_execution` to check it.
3. If validation passes: call `query` with the SAME parameters to execute.
4. If validation fails: STOP. Report the validation issues. Do NOT execute.

## Rules
- NEVER change the fields, model, or explore from what is provided.
- NEVER remove partition filters.
- If query returns an error, report it. Do NOT retry with different fields.
- Store the SQL in your response for transparency.
"""


def create_query_agent(react_llm, looker_mcp_tools: list) -> LlmAgent:
    """Query execution sub-agent.

    Has access to:
      - Looker MCP tools (query_sql, query, get_dimensions, get_measures, get_explores)
      - validate_sql_post_execution (custom FunctionTool)

    Uses Gemini Flash (speed-critical) via SafeChainLlm.
    """
    validate_tool = FunctionTool(func=validate_sql_post_execution)

    return LlmAgent(
        name="query_agent",
        model=react_llm,
        description="Executes validated SQL queries against Looker.",
        instruction=QUERY_AGENT_INSTRUCTION,
        tools=[validate_tool, *looker_mcp_tools],
    )


# ---- Response Agent ----

RESPONSE_AGENT_INSTRUCTION = """You are a data analyst at American Express. Format query results for business users.

## Rules
1. Start with a DIRECT answer to the question in 1-2 sentences.
2. Present data in a clean table if there are multiple rows.
3. Highlight notable patterns (highest/lowest values, trends).
4. Show the SQL used (for transparency -- wrap in a code block).
5. Suggest 2-3 follow-up questions the user might want to ask.

## Boundaries
- Never make predictions or forecasts.
- Never expose PII or raw card numbers.
- Never claim data accuracy beyond what the query returned.
- If results are empty, say so clearly and suggest why.

## Follow-up Suggestions
Generate follow-ups that:
- Add a dimension ("break this down by card product")
- Change the time range ("compare to previous quarter")
- Add or change a filter ("filter for Platinum only")
- Drill into a specific value ("show details for Gen Z")
"""


def create_response_agent(response_llm) -> LlmAgent:
    """Response formatting sub-agent.

    No tools -- pure text generation. Takes query results from session
    state and formats them for the user.

    Uses Gemini Flash (speed-critical) via SafeChainLlm.
    """
    return LlmAgent(
        name="response_agent",
        model=response_llm,
        description="Formats query results into clear business-friendly responses.",
        instruction=RESPONSE_AGENT_INSTRUCTION,
        tools=[],
    )


# ---- Disambiguation Agent ----

DISAMBIGUATION_INSTRUCTION = """You are helping a user clarify which dataset they want to query.

The retrieval system found multiple matching datasets. Present the options clearly.

## Available Options
{alternatives}

## How to Present
- Frame as: "I found {n} datasets that match your question. Which perspective are you looking for?"
- For each option, explain IN BUSINESS TERMS what it covers (not technical names).
- Give a concrete example of what each dataset would answer.
- Number the options so the user can just reply "1" or "2".

## Example
"I found 2 datasets that match 'total spend':
1. **Card Member Spend** -- Total billed business across all card transactions. Use this for spending volume analysis.
2. **Merchant Profitability** -- Revenue from merchant fees on transactions. Use this for merchant economics analysis.

Which one are you looking for?"

## Rules
- Never guess. Always ask.
- Keep it under 5 sentences per option.
- If there are more than 3 options, show top 3 by relevance.
"""


def create_disambiguation_agent(reasoning_llm) -> LlmAgent:
    """Disambiguation sub-agent.

    Uses Gemini Pro (accuracy-critical) because choosing the wrong
    explore means wrong data.
    """
    return LlmAgent(
        name="disambiguation_agent",
        model=reasoning_llm,
        description="Presents dataset options when the query is ambiguous.",
        instruction=DISAMBIGUATION_INSTRUCTION,
        tools=[],
    )


# ---- Clarification Agent ----

CLARIFICATION_INSTRUCTION = """You are helping a user rephrase their question so the system can find matching data.

The retrieval system could not confidently match the user's question to any dataset.

## What Went Wrong
Confidence: {confidence:.0%}
Reason: {reason}

## How to Respond
- Frame as: "I want to make sure I get this right."
- Suggest 2-3 SPECIFIC rephrased versions of their question.
- Each suggestion should use terms the system is likely to recognize.
- If possible, show what data IS available that is close to their question.

## Example
"I want to make sure I get this right. When you say 'customer value', do you mean:
1. **Total billed business** per card member (spending volume)
2. **Customer lifetime value** score (predictive metric)
3. **Net revenue** per card member (profitability)

You can also ask me 'what metrics are available?' to see the full list."

## Rules
- Never say "I don't understand."
- Never expose technical details (similarity scores, explore names).
- Always offer a way forward (rephrase suggestions or discovery).
"""


def create_clarification_agent(reasoning_llm) -> LlmAgent:
    """Clarification sub-agent.

    Uses Gemini Pro (accuracy-critical) because rephrasing suggestions
    need to be precise.
    """
    return LlmAgent(
        name="clarification_agent",
        model=reasoning_llm,
        description="Helps users rephrase questions when retrieval confidence is low.",
        instruction=CLARIFICATION_INSTRUCTION,
        tools=[],
    )


# ---- Boundary Agent ----

BOUNDARY_INSTRUCTION = """You are politely declining a request that is outside the system's capabilities.

The user asked something that is not a data query. This system can ONLY:
- Query financial data from BigQuery via Looker
- Explore available metrics, dimensions, and datasets
- Show existing dashboards and saved queries

## How to Respond
- Acknowledge what they asked.
- Explain what you CAN do.
- Suggest a related data question they COULD ask.
- Keep it to 3-4 sentences.

## Example
"I'm designed to help you query American Express financial data -- things like spending trends, card member metrics, and merchant analytics. I can't make predictions about future performance, but I can show you historical trends. For example, would you like to see total billed business by quarter for the last year?"

## Rules
- Never say "I can't do that" as the first sentence.
- Never be apologetic -- be helpful and redirect.
- Always end with a concrete suggestion.
"""


def create_boundary_agent(classifier_llm) -> LlmAgent:
    """Boundary sub-agent for out-of-scope queries.

    Uses Gemini Flash (simple task, speed matters).
    """
    return LlmAgent(
        name="boundary_agent",
        model=classifier_llm,
        description="Gracefully handles out-of-scope queries with helpful alternatives.",
        instruction=BOUNDARY_INSTRUCTION,
        tools=[],
    )
```

---

## 5. Pipeline Events (Streaming Protocol)

```python
# src/pipeline/events.py
"""Pipeline events for SSE streaming to frontend.

Each pipeline step emits events that the ADK runner surfaces.
The FastAPI SSE endpoint serializes these as JSON for the frontend.

Event flow:
  classify_intent:STARTED -> classify_intent:COMPLETED -> ...
  retrieve_fields:STARTED -> retrieve_fields:COMPLETED -> ...
  query_execution:STARTED -> query_execution:COMPLETED -> ...
  pipeline:COMPLETED (with total timing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from google.adk.events import Event


class StepStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class PipelineStepEvent(Event):
    """Event emitted at each pipeline step boundary.

    The frontend uses these to render a live pipeline visualization:

      [v] Classifying intent... (200ms)
      [v] Retrieving fields... (260ms)
      [v] Resolving filters... (15ms)
      [v] Validating query... (5ms)
      [ ] Executing query...
    """
    step: str = ""
    status: StepStatus = StepStatus.STARTED
    detail: str = ""
    duration_ms: float = 0.0

    def to_sse_dict(self) -> dict:
        """Serialize for Server-Sent Events."""
        return {
            "type": "pipeline_step",
            "step": self.step,
            "status": self.status.value,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 1),
        }
```

---

## 6. Data Flow Diagram

```
User: "What was total billed business for small businesses last quarter?"
  |
  v
+================================================================+
|                    CortexAgent (BaseAgent)                       |
|                                                                  |
|  PHASE 1: PRE-PROCESSING                                        |
|  +---------------------------------------------------------+    |
|  |                                                           |    |
|  |  1. classify_intent()           [1 LLM call, ~200ms]     |    |
|  |     SafeChainLlm (Flash)                                 |    |
|  |     Input:  "What was total billed business..."           |    |
|  |     Output: ClassificationResult {                        |    |
|  |       intent: "data_query",                               |    |
|  |       entities: {                                         |    |
|  |         metrics: ["total billed business"],               |    |
|  |         filters: {"bus_seg": "small businesses"},         |    |
|  |         time_range: "last quarter"                        |    |
|  |       }                                                   |    |
|  |     }                                                     |    |
|  |                          |                                |    |
|  |                          v                                |    |
|  |  2. retrieve_fields()   [0 LLM calls, ~260ms]            |    |
|  |     pgvector + AGE + FAISS                                |    |
|  |     Output: RetrievalResult {                             |    |
|  |       action: "proceed",                                  |    |
|  |       model: "cortex_finance",                            |    |
|  |       explore: "card_member_spend",                       |    |
|  |       measures: ["total_billed_business"],                |    |
|  |       confidence: 0.91                                    |    |
|  |     }                                                     |    |
|  |                          |                                |    |
|  |                          v                                |    |
|  |  3. resolve_filters()   [0 LLM calls, ~15ms]             |    |
|  |     5-pass deterministic resolution                       |    |
|  |     "small businesses" --> "OPEN"                         |    |
|  |     "last quarter" --> "last 1 quarters"                  |    |
|  |     + auto-inject partition_date: "last 90 days"          |    |
|  |                          |                                |    |
|  |                          v                                |    |
|  |  4. validate_query()    [0 LLM calls, ~5ms]              |    |
|  |     - Partition filter? YES                               |    |
|  |     - Fields present? YES                                 |    |
|  |     - Model/explore? YES                                  |    |
|  |     - Field count sane? YES                               |    |
|  |     - No injection? YES                                   |    |
|  |     --> VALID                                             |    |
|  |                                                           |    |
|  +---------------------------------------------------------+    |
|                             |                                    |
|                             v  RetrievalResult                   |
|  PHASE 2: EXECUTION                                              |
|  +---------------------------------------------------------+    |
|  |                                                           |    |
|  |  query_agent (LlmAgent + SafeChainLlm Flash)             |    |
|  |  Tools: [query_sql, query, validate_sql, ...]            |    |
|  |                                                           |    |
|  |  Iteration 1:                                             |    |
|  |    LLM --> query_sql(                                     |    |
|  |      model=cortex_finance,                                |    |
|  |      explore=card_member_spend,                           |    |
|  |      fields=[total_billed_business],                      |    |
|  |      filters={bus_seg: "OPEN",                            |    |
|  |               partition_date: "last 1 quarters"}          |    |
|  |    ) --> SQL string                                       |    |
|  |                                                           |    |
|  |  Iteration 2:                                             |    |
|  |    LLM --> validate_sql_post_execution(sql, result)       |    |
|  |    --> {valid: true}                                      |    |
|  |                                                           |    |
|  |  Iteration 3:                                             |    |
|  |    LLM --> query(same params) --> data rows               |    |
|  |                                                           |    |
|  +---------------------------------------------------------+    |
|                             |                                    |
|                             v  raw data                          |
|  PHASE 3: RESPONSE                                               |
|  +---------------------------------------------------------+    |
|  |                                                           |    |
|  |  response_agent (LlmAgent + SafeChainLlm Flash)          |    |
|  |  No tools. Pure text generation.                          |    |
|  |                                                           |    |
|  |  Output: "Total billed business for Small Business (OPEN) |    |
|  |   last quarter was $4.2B.                                 |    |
|  |                                                           |    |
|  |   | Metric                 | Value     |                  |    |
|  |   |------------------------|-----------|                  |    |
|  |   | Total Billed Business  | $4.2B     |                  |    |
|  |                                                           |    |
|  |   SQL: SELECT SUM(total_billed_business) FROM ...         |    |
|  |                                                           |    |
|  |   Follow-ups:                                             |    |
|  |   - Break down by card product                            |    |
|  |   - Compare to previous quarter                           |    |
|  |   - Filter for Platinum cards only"                       |    |
|  |                                                           |    |
|  +---------------------------------------------------------+    |
|                                                                  |
+================================================================+
  |
  v
SSE Events streamed to frontend:
  {"type":"pipeline_step","step":"classify_intent","status":"started"}
  {"type":"pipeline_step","step":"classify_intent","status":"completed","duration_ms":195}
  {"type":"pipeline_step","step":"retrieve_fields","status":"started"}
  {"type":"pipeline_step","step":"retrieve_fields","status":"completed","duration_ms":248}
  {"type":"pipeline_step","step":"resolve_filters","status":"completed","duration_ms":12}
  {"type":"pipeline_step","step":"validate_query","status":"completed","duration_ms":3}
  {"type":"pipeline_step","step":"query_execution","status":"started"}
  {"type":"tool_call","tool":"query_sql","args":{...}}
  {"type":"tool_result","tool":"query_sql","result":"SELECT ..."}
  {"type":"tool_call","tool":"validate_sql_post_execution","args":{...}}
  {"type":"tool_result","tool":"validate_sql_post_execution","result":{"valid":true}}
  {"type":"tool_call","tool":"query","args":{...}}
  {"type":"tool_result","tool":"query","result":{...data...}}
  {"type":"pipeline_step","step":"query_execution","status":"completed","duration_ms":1850}
  {"type":"pipeline_step","step":"format_response","status":"started"}
  {"type":"text","content":"Total billed business for Small Business..."}
  {"type":"pipeline_step","step":"pipeline","status":"completed","duration_ms":2450}
```

---

## 7. Model Selection Strategy

| Task | Model | Why | Latency Budget | Tool Access |
|------|-------|-----|----------------|-------------|
| Intent classification | Gemini 2.5 Flash | Speed. Classification is well-constrained; Flash handles it fine. | 400ms | None |
| Entity extraction | Gemini 2.5 Flash | Same call as classification (combined prompt). | (included above) | None |
| Query execution (ReAct) | Gemini 2.5 Flash | Speed. The augmented prompt makes this trivial -- just format the MCP call. | 1200ms | Looker MCP + validate_sql |
| Response formatting | Gemini 2.5 Flash | Speed. Formatting is simple text generation. | 600ms | None |
| Disambiguation | Gemini 2.5 Pro | Accuracy. Wrong explore = wrong data. Pro reasons better about which dataset matches. | 800ms | None |
| Clarification | Gemini 2.5 Pro | Accuracy. Generating useful rephrase suggestions requires understanding the domain. | 800ms | None |
| Boundary (out-of-scope) | Gemini 2.5 Flash | Speed. Simple redirect, no complex reasoning. | 300ms | None |

**SafeChain model routing:** Each SafeChainLlm instance is constructed with a specific model_id. The factory functions in `safechain_client.py` handle this. The model_id maps to a SafeChain endpoint via CIBIS config -- Ravi J controls this mapping. We need both Flash and Pro endpoints registered.

**Cost control:** Flash costs ~$0.15/1M tokens, Pro costs ~$1.25/1M tokens. At estimated 100 queries/day during pilot:
- Classification: 100 x ~500 tokens = 50K tokens/day (Flash) = ~$0.008/day
- ReAct: 100 x ~2000 tokens = 200K tokens/day (Flash) = ~$0.030/day
- Response: 100 x ~1000 tokens = 100K tokens/day (Flash) = ~$0.015/day
- Disambiguation: ~10 x ~1000 tokens = 10K tokens/day (Pro) = ~$0.013/day
- **Total: ~$0.07/day = ~$2/month during pilot**

---

## 8. SQL Validation Architecture

### 8.1 Two-Stage Validation

```
Stage 1: PRE-EXECUTION (in CortexAgent, deterministic)
  validate_query() checks:
    - Partition filter present (BLOCKING)
    - Fields non-empty
    - Model + explore resolved
    - Field count sanity
    - No injection patterns
  This runs BEFORE any Looker MCP call.

Stage 2: POST-GENERATION / PRE-EXECUTION (in query_agent, after query_sql)
  validate_sql_post_execution() checks:
    - Partition field in WHERE clause
    - Expected fields in SELECT
    - SELECT-only (no DML)
    - Field name alignment with RetrievalResult
  This runs AFTER Looker generates SQL but BEFORE execution.
```

### 8.2 Looker MCP Tool Separation (Critical Finding)

Looker MCP Toolbox exposes **two separate tools**:
- **`query_sql`**: Takes (model, explore, fields, filters) and returns the generated SQL string. **Does NOT execute.**
- **`query`**: Takes the same parameters and **executes**, returning data rows.

This separation is exactly what we need. The query_agent instruction tells the LLM:
1. Call `query_sql` first (get SQL)
2. Call `validate_sql_post_execution` (validate)
3. If valid, call `query` (execute)
4. If invalid, stop and report

### 8.3 Validation Failure Handling

```
Validation fails at Stage 1 (pre-execution):
  --> Pipeline stops. User sees: "I found the right dataset but
      the query has issues: [list]. Let me try a different approach."
  --> PipelineStepEvent(step="validate_query", status=BLOCKED)
  --> No Looker MCP calls made. No BigQuery cost.

Validation fails at Stage 2 (post-generation):
  --> query_agent reports issue to user via response.
  --> query_agent does NOT call query tool.
  --> User sees: "The generated SQL has potential issues: [list].
      Want me to try with adjusted parameters?"
  --> Retry: CortexAgent can re-run Phase 2 with adjusted filters.
```

### 8.4 Partition Filter Defense in Depth

The partition filter is checked at THREE levels:
1. `resolve_filters()` auto-injects mandatory partition filter if user did not specify one
2. `validate_query()` checks it exists in the filter dict (Stage 1)
3. `validate_sql_post_execution()` checks it appears in the SQL WHERE clause (Stage 2)

If all three fail, the query still goes through Looker MCP which has its own `always_filter` enforcement on the LookML explore. Four layers of protection against $50K full-table scans.

---

## 9. SSE Streaming Protocol

### 9.1 FastAPI SSE Endpoint

```python
# src/api/server.py (relevant excerpt)
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import json


app = FastAPI(title="Cortex API", version="0.2.0")

# Singleton agent + runner (initialized at startup)
_runner: Runner | None = None


@app.on_event("startup")
async def startup():
    """Initialize Cortex agent and ADK runner."""
    global _runner
    from src.pipeline.bootstrap import create_cortex_agent
    agent = await create_cortex_agent()
    session_service = InMemorySessionService()
    _runner = Runner(
        agent=agent,
        app_name="cortex",
        session_service=session_service,
    )


@app.post("/query/stream")
async def query_stream(request: QueryRequest) -> StreamingResponse:
    """SSE endpoint. Streams pipeline events + final response.

    Event types:
      pipeline_step: Step boundary events (started/completed/failed)
      tool_call: LLM decided to call a tool
      tool_result: Tool returned a result
      text: Incremental text from response agent
      trace: Full PipelineTrace (final event)
      done: Stream complete
    """
    async def event_generator():
        session = await _runner.session_service.create_session(
            app_name="cortex",
            user_id=request.user_id or "anonymous",
        )

        # Inject conversation history into session state
        if request.history:
            session.state["conversation_history"] = request.history

        from google.genai.types import Content, Part
        user_content = Content(
            role="user",
            parts=[Part(text=request.query)],
        )

        async for event in _runner.run_async(
            user_id=request.user_id or "anonymous",
            session_id=session.id,
            new_message=user_content,
        ):
            # Pipeline step events (from CortexAgent)
            if isinstance(event, PipelineStepEvent):
                yield f"data: {json.dumps(event.to_sse_dict())}\n\n"

            # Tool call/result events (from ADK's LlmAgent)
            elif hasattr(event, "tool_calls"):
                for tc in event.tool_calls:
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tc.name, 'args': tc.args})}\n\n"

            # Text content events
            elif hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if part.text:
                        yield f"data: {json.dumps({'type': 'text', 'content': part.text})}\n\n"

        # Final trace
        trace = session.state.get("pipeline_trace")
        if trace:
            yield f"data: {json.dumps({'type': 'trace', 'trace': trace})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

### 9.2 Frontend Event Protocol

```
SSE Event Stream:

event: pipeline_step
data: {"type":"pipeline_step","step":"classify_intent","status":"started","detail":"","duration_ms":0}

event: pipeline_step
data: {"type":"pipeline_step","step":"classify_intent","status":"completed","detail":"intent=data_query (97%)","duration_ms":195.2}

event: pipeline_step
data: {"type":"pipeline_step","step":"retrieve_fields","status":"started","detail":"","duration_ms":0}

event: pipeline_step
data: {"type":"pipeline_step","step":"retrieve_fields","status":"completed","detail":"action=proceed explore=card_member_spend confidence=91%","duration_ms":248.1}

event: pipeline_step
data: {"type":"pipeline_step","step":"resolve_filters","status":"completed","detail":"filters={bus_seg: OPEN, partition_date: last 1 quarters}","duration_ms":11.8}

event: pipeline_step
data: {"type":"pipeline_step","step":"validate_query","status":"completed","detail":"valid=True issues=[]","duration_ms":2.9}

event: pipeline_step
data: {"type":"pipeline_step","step":"query_execution","status":"started","detail":"","duration_ms":0}

event: tool_call
data: {"type":"tool_call","tool":"query_sql","args":{"model_name":"cortex_finance","explore_name":"card_member_spend","fields":["total_billed_business"],"filters":{"bus_seg":"OPEN","partition_date":"last 1 quarters"}}}

event: tool_result
data: {"type":"tool_result","tool":"query_sql","result":"SELECT SUM(total_billed_business) FROM ..."}

event: tool_call
data: {"type":"tool_call","tool":"validate_sql_post_execution","args":{"sql":"SELECT ...","retrieval_result_dict":{...}}}

event: tool_result
data: {"type":"tool_result","tool":"validate_sql_post_execution","result":{"valid":true,"issues":[]}}

event: tool_call
data: {"type":"tool_call","tool":"query","args":{"model_name":"cortex_finance","explore_name":"card_member_spend","fields":["total_billed_business"],"filters":{"bus_seg":"OPEN","partition_date":"last 1 quarters"}}}

event: tool_result
data: {"type":"tool_result","tool":"query","result":{"rows":[{"total_billed_business":4200000000}]}}

event: pipeline_step
data: {"type":"pipeline_step","step":"query_execution","status":"completed","detail":"","duration_ms":1850.3}

event: pipeline_step
data: {"type":"pipeline_step","step":"format_response","status":"started","detail":"","duration_ms":0}

event: text
data: {"type":"text","content":"Total billed business for Small Business (OPEN) last quarter was $4.2B.\n\n| Metric | Value |\n|---|---|\n| Total Billed Business | $4.2B |\n\n```sql\nSELECT SUM(total_billed_business) FROM ...\n```\n\nFollow-ups:\n- Break down by card product\n- Compare to previous quarter\n- Filter for Platinum cards only"}

event: trace
data: {"type":"trace","trace":{"trace_id":"abc-123","query":"What was total billed business...","total_duration_ms":2450,"llm_calls":3,"mcp_calls":2,"confidence":0.91,"action":"proceed","steps":[...]}}

event: done
data: {"type":"done"}
```

---

## 10. Assembly: Bootstrap Function

```python
# src/pipeline/bootstrap.py
"""Bootstrap the Cortex agent with all dependencies.

This is the single entry point that wires everything together.
Called once at server startup.
"""

from __future__ import annotations

import os
import logging

from src.connectors.safechain_client import (
    get_config,
    create_classifier_llm,
    create_react_llm,
    create_reasoning_llm,
)
from src.connectors.mcp_tools import get_looker_toolset
from src.pipeline.agent import CortexAgent
from src.pipeline.sub_agents import (
    create_query_agent,
    create_response_agent,
    create_disambiguation_agent,
    create_clarification_agent,
    create_boundary_agent,
)
from src.retrieval.orchestrator import RetrievalOrchestrator

logger = logging.getLogger(__name__)


async def create_cortex_agent() -> CortexAgent:
    """Wire up all dependencies and return the root CortexAgent.

    Dependency graph:
      Config
        |
        +-- classifier_llm (Flash, no tools)
        +-- react_llm (Flash, with MCP tools)
        +-- reasoning_llm (Pro, no tools)
        |
      pg_conn (pgvector + AGE)
        |
        +-- embed_fn (sentence-transformers or SafeChain BGE)
        +-- RetrievalOrchestrator
        |
      Looker MCP tools (via ADK McpToolset)
        |
        +-- query_agent (LlmAgent)
        +-- response_agent (LlmAgent)
        +-- disambiguation_agent (LlmAgent)
        +-- clarification_agent (LlmAgent)
        +-- boundary_agent (LlmAgent)
        |
      CortexAgent (BaseAgent, root)
    """
    # -- SafeChain config --
    config = await get_config()

    # -- LLM instances --
    classifier_llm = await create_classifier_llm(config)
    react_llm = await create_react_llm(config)
    reasoning_llm = await create_reasoning_llm(config)

    # -- Looker MCP tools (ADK-native) --
    looker_tools = await get_looker_toolset()

    # -- PostgreSQL connection (pgvector + AGE) --
    from src.connectors.postgres_age_client import get_connection
    pg_conn = get_connection()

    # -- Embedding function --
    # TODO: Switch to SafeChain BGE endpoint when available.
    # Fallback: local sentence-transformers model.
    from src.retrieval.model_adapter import get_embed_fn
    embed_fn = get_embed_fn()

    # -- Retrieval orchestrator --
    retrieval = RetrievalOrchestrator(
        pg_conn=pg_conn,
        embed_fn=embed_fn,
        model_name=os.getenv("CORTEX_MODEL_NAME", "cortex_finance"),
    )

    # -- Taxonomy terms (for intent classification prompt) --
    taxonomy_terms = _load_taxonomy_terms()

    # -- Sub-agents --
    query_agent = create_query_agent(react_llm, looker_tools)
    response_agent = create_response_agent(classifier_llm)  # Flash is fine for formatting
    disambiguation_agent = create_disambiguation_agent(reasoning_llm)
    clarification_agent = create_clarification_agent(reasoning_llm)
    boundary_agent = create_boundary_agent(classifier_llm)

    # -- Root agent --
    agent = CortexAgent(
        query_agent=query_agent,
        response_agent=response_agent,
        disambiguation_agent=disambiguation_agent,
        clarification_agent=clarification_agent,
        boundary_agent=boundary_agent,
        retrieval_orchestrator=retrieval,
        embed_fn=embed_fn,
        pg_conn=pg_conn,
        taxonomy_terms=taxonomy_terms,
    )

    logger.info(
        "CortexAgent initialized: %d sub-agents, %d MCP tools, %d taxonomy terms",
        len(agent.sub_agents),
        len(looker_tools),
        len(taxonomy_terms),
    )
    return agent


def _load_taxonomy_terms() -> list[str]:
    """Load business terms for intent classification.

    Sources (in priority order):
      1. config/taxonomy.yaml (manually curated)
      2. Field descriptions from pgvector (auto-extracted)
    """
    import yaml
    from pathlib import Path

    taxonomy_path = Path(__file__).resolve().parents[2] / "config" / "taxonomy.yaml"
    if taxonomy_path.exists():
        with open(taxonomy_path) as f:
            data = yaml.safe_load(f)
        return data.get("terms", [])
    return []
```

---

## 11. What Needs to Be Built vs. What Exists

| File | Status | Owner | Effort | Dependency |
|------|--------|-------|--------|------------|
| `src/connectors/safechain_llm.py` | **NEW** | Saheb | 2 days | SafeChain + ADK BaseLlm interface verification |
| `src/connectors/safechain_client.py` | **REWRITE** (stub exists) | Saheb | 1 day | safechain_llm.py |
| `src/pipeline/agent.py` | **REWRITE** (stub exists) | Saheb | 2 days | tools.py + sub_agents.py |
| `src/pipeline/tools.py` | **NEW** | Likhita (classify_intent), Saheb (validate_*) | 2 days | retrieval orchestrator + filters |
| `src/pipeline/sub_agents.py` | **NEW** | Saheb | 1 day | safechain_client.py |
| `src/pipeline/events.py` | **NEW** | Ravikanth | 0.5 day | None |
| `src/pipeline/bootstrap.py` | **NEW** | Saheb | 1 day | Everything else |
| `src/pipeline/trace.py` | **NEW** (spec in design doc) | Ravikanth | 1 day | None |
| `src/pipeline/prompts.py` | **NEW** (spec in design doc) | Likhita + Saheb | 1 day | Taxonomy finalized |
| `src/connectors/mcp_tools.py` | **IMPLEMENT** (stub exists) | Rajesh | 0.5 day | MCP Toolbox running |
| `src/api/server.py` | **NEW** | Ravikanth | 1.5 days | bootstrap.py + events.py |
| `src/retrieval/orchestrator.py` | **EXISTS** | -- | -- | -- |
| `src/retrieval/filters.py` | **EXISTS** | -- | -- | -- |
| `src/retrieval/models.py` | **EXISTS** | -- | -- | -- |
| `src/pipeline/state.py` | **EXISTS** (extend) | Saheb | 0.5 day | -- |

### Critical Path (Build Order)

```
Week 1 (Saheb, parallel with Likhita):
  Day 1-2: safechain_llm.py + safechain_client.py
           VERIFY: BaseLlm.generate_content_async() contract matches SafeChain
           This is the riskiest piece. If it doesn't work, we need the
           LiteLLM proxy escape hatch immediately.

  Day 2-3: tools.py (validate_query, validate_sql, resolve_filters wrapper)
           sub_agents.py (all 5 sub-agents)

  Day 3-4: agent.py (CortexAgent custom BaseAgent)
           bootstrap.py (assembly)

  Day 5:   Integration test: full pipeline against Looker dev instance

Week 1 (Likhita, parallel with Saheb):
  Day 1-2: prompts.py (classification prompt + few-shot examples)
  Day 3-4: classify_intent in tools.py (JSON parsing, error handling)
  Day 5:   Classification accuracy eval (target: >95% on 50 test queries)

Week 1 (Rajesh):
  Day 1:   mcp_tools.py (implement get_looker_toolset with McpToolset)
  Day 2-3: Integration test: ADK McpToolset -> Looker MCP -> query_sql

Week 1 (Ravikanth):
  Day 1:   events.py + trace.py
  Day 2-3: api/server.py (FastAPI + SSE)
  Day 4-5: Frontend SSE consumer (ChatGPT plugin or custom UI)
```

### Escape Hatch: If BaseLlm Adapter Fails

If SafeChainLlm cannot implement BaseLlm's generate_content_async() correctly (most likely failure: ADK expects Gemini-specific Content types that SafeChain doesn't produce), the fallback is:

1. Run a local HTTP proxy (50 lines of FastAPI) that wraps SafeChain as an OpenAI-compatible endpoint
2. Use ADK's LiteLLM integration: `model=LiteLlm(model="openai/safechain-gemini-flash", api_base="http://localhost:8081")`
3. This adds ~10ms latency per LLM call (local loopback) but preserves the full ADK agent architecture

The proxy is a 1-day build. It is the insurance policy.

---

## 12. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| BaseLlm adapter format mismatch | HIGH (blocks all LLM calls) | MEDIUM | LiteLLM proxy escape hatch (1 day) |
| ADK McpToolset incompatible with SafeChain MCP | HIGH (no Looker access) | LOW | Fall back to SafeChain MCPToolLoader (proven in PoC) |
| query_agent ignores instruction, explores instead of using provided fields | MEDIUM (slow, less accurate) | MEDIUM | Tighter instruction, reduce max_iterations to 3, add guardrail callback |
| PipelineStepEvent not recognized by ADK runner | LOW (breaks streaming) | MEDIUM | Fall back to session state polling instead of event streaming |
| query_sql and query parameters diverge | HIGH (validated SQL != executed SQL) | LOW | Assert parameter equality in validate_sql |
| SafeChain token refresh during pipeline | MEDIUM (one step fails) | LOW | MCPToolAgent handles refresh internally (verified in PoC) |

---

## 13. Implementation Status (March 13, 2026)

All files listed in Section 11 have been implemented. The code is in the source tree, not just in this document.

### Files Implemented (code written, needs integration testing)

| File | Lines | Status |
|------|-------|--------|
| `src/connectors/safechain_llm.py` | ~307 | SafeChainLlm(BaseLlm) adapter with ADK<->LangChain format translation |
| `src/connectors/safechain_client.py` | ~120 | Factory functions: create_classifier_llm, create_react_llm, create_reasoning_llm |
| `src/connectors/mcp_tools.py` | ~85 | ADK McpToolset integration with tool_filter (6 production tools including query + query_sql) |
| `src/pipeline/agent.py` | ~300 | CortexAgent(BaseAgent) with _run_async_impl: classify -> retrieve -> filter -> validate -> execute -> format |
| `src/pipeline/tools.py` | ~340 | classify_intent, retrieve_fields, resolve_filters, validate_query, validate_sql_post_execution |
| `src/pipeline/sub_agents.py` | ~260 | query_agent, response_agent, disambiguation_agent, clarification_agent, boundary_agent |
| `src/pipeline/events.py` | ~115 | PipelineStepEvent, StepStatus, ThinkingEvent (SSE-compatible) |
| `src/pipeline/trace.py` | ~263 | StepTrace (frozen), PipelineTrace (frozen), TraceBuilder with start_step/end_step pattern |
| `src/pipeline/prompts.py` | ~175 | CLASSIFY_AND_EXTRACT_PROMPT, AUGMENTED_PROMPT_TEMPLATE, build_augmented_prompt() |
| `src/pipeline/bootstrap.py` | ~150 | create_cortex_agent() wiring function with 7-step initialization |
| `src/api/server.py` | ~250 | FastAPI: /query, /query/stream (SSE), /health, /feedback |

### Files That Already Existed (untouched)

| File | Notes |
|------|-------|
| `src/retrieval/orchestrator.py` | 10-step hybrid retrieval pipeline. Used as-is. |
| `src/retrieval/filters.py` | 5-pass filter resolution with namespace architecture. Used as-is. |
| `src/retrieval/models.py` | FieldCandidate, RetrievalResult, GoldenQuery. Used as-is. |
| `src/pipeline/state.py` | CortexState dataclass. Used as-is (ADK session state is the runtime equivalent). |
| `src/pipeline/errors.py` | CortexError hierarchy. Used by cortex_orchestrator.py (composition path). |
| `src/pipeline/cortex_orchestrator.py` | Composition-based orchestrator wrapping PoC AgentOrchestrator. Parallel path to ADK agent.py. |
| `src/connectors/postgres_age_client.py` | SQLAlchemy engine + AGE session init. Used as-is by bootstrap.py. |
| `src/adapters/model_adapter.py` | Embedding function (SafeChain BGE or local sentence-transformers). Used as-is by bootstrap.py. |

### Two Parallel Orchestration Paths

The codebase now has two orchestration paths. This is intentional:

1. **ADK path** (NEW): `agent.py` + `sub_agents.py` + `bootstrap.py` + `api/server.py`
   - Uses ADK BaseAgent + LlmAgent + Runner
   - SafeChainLlm adapter routes LLM calls through SafeChain
   - Pipeline steps are deterministic, sub-agent calls are LLM-driven
   - SSE streaming via ADK event system

2. **Composition path** (EXISTING): `cortex_orchestrator.py`
   - Wraps PoC AgentOrchestrator directly
   - Same pipeline logic (classify -> retrieve -> filter -> execute)
   - No ADK dependency -- uses SafeChain MCPToolAgent directly
   - Streaming via custom event dicts

**Why both exist:** The ADK path is the target architecture. The composition path is the proven fallback. If SafeChainLlm's BaseLlm adapter hits integration issues with ADK's internal LLM flow (Risk #1 in Section 12), we switch to the composition path in 1 day because it uses the exact same retrieval pipeline, filter resolver, and prompt templates.

### What Still Needs Testing

1. **SafeChainLlm adapter (HIGHEST RISK):** Does `generate_content_async` produce LlmResponse objects that ADK's internal flow accepts? The format translation (ADK Content -> LangChain Messages -> SafeChain -> back) has not been tested end-to-end against live SafeChain.

2. **ADK McpToolset connection:** Does the SSE connection to MCP Toolbox work through ADK's McpToolset? The PoC used SafeChain's MCPToolLoader, not ADK's McpToolset.

3. **PipelineStepEvent yielding:** CortexAgent yields PipelineStepEvents from `_run_async_impl`. ADK's Runner needs to propagate these without filtering. Verify the Runner does not swallow non-standard events.

4. **query_agent instruction override:** CortexAgent dynamically sets `self._query_agent.instruction = augmented_prompt`. Verify that ADK LlmAgent supports runtime instruction mutation (vs. only at construction time).

5. **Sub-agent context passing:** Session state is used to pass retrieval_result, augmented_prompt, and alternatives between CortexAgent and sub-agents. Verify that sub-agents can read state written by the parent.

---

## Sources

- [ADK Documentation - Models](https://google.github.io/adk-docs/agents/models/)
- [ADK Custom Agents](https://google.github.io/adk-docs/agents/custom-agents/)
- [ADK Custom Tools](https://google.github.io/adk-docs/tools-custom/)
- [ADK API Reference](https://google.github.io/adk-docs/api-reference/python/)
- [ADK LiteLLM Integration](https://google.github.io/adk-docs/agents/models/litellm/)
- [Looker MCP query_sql Tool](https://googleapis.github.io/genai-toolbox/resources/tools/looker/looker-query-sql/)
- [ADK Python GitHub](https://github.com/google/adk-python)
- [Google Cloud Blog - Multi-Agent Systems with ADK](https://cloud.google.com/blog/topics/developers-practitioners/building-collaborative-ai-a-developers-guide-to-multi-agent-systems-with-adk)
