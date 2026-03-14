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

Escape hatch:
  If this adapter fails (most likely: ADK Content type mismatches),
  fall back to LiteLLM + local OpenAI-compat proxy wrapping SafeChain.
  See docs/design/adk-agent-orchestration-implementation.md, Section 11.

References:
  - ADK BaseLlm: https://google.github.io/adk-docs/agents/models/
  - ADK LiteLLM: https://google.github.io/adk-docs/agents/models/litellm/
  - SafeChain MCPToolAgent: access_llm/chat.py (PoC)
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai.types import Content, Part, FunctionCall, FunctionResponse
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
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
      - Response streaming (if supported)

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
                pass empty list. For ReAct execution, pass Looker MCP tools.
        """
        self._model_id = model_id
        self._config = config
        self._mcp_tools = mcp_tools or []
        self._agent: MCPToolAgent | None = None

    @property
    def model(self) -> str:
        """Model identifier used by SafeChain."""
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
        """Initialize SafeChain connection and MCPToolAgent.

        Idempotent -- safe to call multiple times.
        """
        if self._agent is not None:
            return

        if self._config is None:
            self._config = Config.from_env()

        self._agent = MCPToolAgent(self._model_id, self._mcp_tools)
        logger.info(
            "SafeChainLlm connected: model=%s, tools=%d",
            self._model_id,
            len(self._mcp_tools),
        )

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
    ) -> AsyncGenerator[LlmResponse, None]:
        """Translate ADK request -> SafeChain call -> ADK response.

        ADK's internal LLM flow calls this method. We:
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
            logger.error("SafeChain call failed: %s", e, exc_info=True)
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

    # -- Format Translation: ADK -> LangChain --

    @staticmethod
    def _adk_to_langchain(contents: list[Content]) -> list:
        """Convert ADK Content objects to LangChain message objects.

        ADK Content structure:
          Content(role="user"|"model", parts=[
            Part(text=...),
            Part(function_call=FunctionCall(name=..., args=...)),
            Part(function_response=FunctionResponse(name=..., response=...)),
          ])

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
                # Check for function calls (tool invocations by the model)
                fn_calls = [
                    p.function_call
                    for p in content.parts
                    if p.function_call
                ]
                if fn_calls:
                    messages.append(
                        AIMessage(
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
                        )
                    )
                else:
                    messages.append(AIMessage(content=combined_text))

            # Handle function responses (tool results fed back to model)
            fn_responses = [
                p.function_response
                for p in content.parts
                if p.function_response
            ]
            for fr in fn_responses:
                messages.append(
                    ToolMessage(
                        content=str(fr.response),
                        tool_call_id=f"call_{fr.name}",
                        name=fr.name,
                    )
                )

        return messages

    # -- Format Translation: SafeChain -> ADK --

    @staticmethod
    def _safechain_to_adk(result) -> LlmResponse:
        """Convert SafeChain MCPToolAgent result to ADK LlmResponse.

        SafeChain returns one of:
          - dict with "content" (str) and optional "tool_results" (list)
          - AIMessage with .content and optional .tool_calls
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
                    parts.append(
                        Part(
                            function_response=FunctionResponse(
                                name=tool_name,
                                response={"error": tr["error"]},
                            )
                        )
                    )
                else:
                    parts.append(
                        Part(
                            function_response=FunctionResponse(
                                name=tool_name,
                                response={"result": tr.get("result", "")},
                            )
                        )
                    )

        elif hasattr(result, "content"):
            content_str = str(result.content)
            parts.append(Part(text=content_str))

            # Check for tool_calls on AIMessage
            if hasattr(result, "tool_calls"):
                for tc in result.tool_calls:
                    parts.append(
                        Part(
                            function_call=FunctionCall(
                                name=tc.get("name", ""),
                                args=tc.get("args", {}),
                            )
                        )
                    )
        else:
            parts.append(Part(text=str(result)))

        return LlmResponse(
            content=Content(role="model", parts=parts),
        )


def _extract_text(content) -> str:
    """Extract text from a Content object or string."""
    if isinstance(content, str):
        return content
    if hasattr(content, "parts"):
        return "\n".join(p.text for p in content.parts if p.text)
    return str(content)
