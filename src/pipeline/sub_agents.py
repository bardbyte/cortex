"""ADK sub-agents for specialized flows.

Each sub-agent is an LlmAgent with a specific instruction and tool set.
CortexAgent delegates to these based on pipeline routing decisions:

  retrieval.action == "proceed"      -> query_agent -> response_agent
  retrieval.action == "disambiguate" -> disambiguation_agent
  retrieval.action == "clarify"      -> clarification_agent
  classification.intent == "out_of_scope" -> boundary_agent

Sub-agent instructions are co-located here (not in prompts.py) because
they are tightly coupled to the agent configuration. Moving them to
prompts.py would create a false separation.

Model selection:
  - query_agent: Flash (speed-critical, augmented prompt makes it trivial)
  - response_agent: Flash (formatting is simple text gen)
  - disambiguation_agent: Pro (accuracy-critical, wrong explore = wrong data)
  - clarification_agent: Pro (precise rephrasing needs domain understanding)
  - boundary_agent: Flash (simple redirect)
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from src.pipeline.tools import validate_sql_post_execution


# =====================================================================
# Query Agent
# =====================================================================

QUERY_AGENT_INSTRUCTION = """\
You are a Looker query executor. Your job is to generate SQL, validate it, \
and then execute it against the database. Follow the workflow EXACTLY.

## Workflow (STRICT ORDER)
1. Call `query_sql` with the parameters from your system context.
   This generates the SQL WITHOUT executing it.
2. Call `validate_sql_post_execution` with the SQL from step 1.
   This checks for partition filters, expected fields, and dangerous patterns.
3. If validation passes (valid=true):
   Call `query` with the SAME parameters to execute and get data.
4. If validation fails:
   STOP. Report the validation issues. Do NOT execute the query.

## Rules
- Use EXACTLY the model, explore, fields, and filters provided.
- Do NOT explore or discover -- the retrieval pipeline already did that.
- Do NOT remove partition filters. They prevent expensive full table scans.
- If query returns an error, report it. Do NOT retry with different fields.
- Include the SQL in your response for transparency.
"""


def create_query_agent(react_llm, looker_mcp_tools: list) -> LlmAgent:
    """Query execution sub-agent.

    Has access to:
      - Looker MCP tools (query_sql, query, get_dimensions, get_measures, etc.)
      - validate_sql_post_execution (custom FunctionTool)

    Uses Gemini Flash (speed-critical) via SafeChainLlm.

    Args:
        react_llm: SafeChainLlm instance with Looker MCP tools bound.
        looker_mcp_tools: ADK-native Looker MCP tools from McpToolset.

    Returns:
        Configured LlmAgent.
    """
    validate_tool = FunctionTool(func=validate_sql_post_execution)

    return LlmAgent(
        name="query_agent",
        model=react_llm,
        description="Executes validated SQL queries against Looker.",
        instruction=QUERY_AGENT_INSTRUCTION,
        tools=[validate_tool, *looker_mcp_tools],
    )


# =====================================================================
# Response Agent
# =====================================================================

RESPONSE_AGENT_INSTRUCTION = """\
You are a data analyst at American Express. Format query results for business users.

## Response Structure
1. **Direct answer**: 1-2 sentences answering the question.
2. **Data table**: If multiple rows, present in a clean markdown table.
3. **Notable patterns**: Highlight highest/lowest values, trends, outliers.
4. **SQL**: Show the SQL used, wrapped in a code block (for transparency).
5. **Follow-ups**: Suggest 2-3 natural next questions.

## Follow-up Suggestions
Generate follow-ups that:
- Add a dimension ("break this down by card product")
- Change the time range ("compare to previous quarter")
- Add or change a filter ("filter for Platinum cards only")
- Drill into a specific value ("show details for Gen Z")

## Boundaries
- Never make predictions or forecasts.
- Never expose PII or raw card numbers.
- Never claim accuracy beyond what the query returned.
- If results are empty, say so clearly and suggest why.
"""


def create_response_agent(response_llm) -> LlmAgent:
    """Response formatting sub-agent.

    No tools -- pure text generation. Takes query results from the
    conversation context and formats them for the user.

    Uses Gemini Flash via SafeChainLlm.

    Args:
        response_llm: SafeChainLlm instance (Flash, no tools).

    Returns:
        Configured LlmAgent.
    """
    return LlmAgent(
        name="response_agent",
        model=response_llm,
        description="Formats query results into clear business-friendly responses.",
        instruction=RESPONSE_AGENT_INSTRUCTION,
        tools=[],
    )


# =====================================================================
# Disambiguation Agent
# =====================================================================

DISAMBIGUATION_INSTRUCTION = """\
You are helping a user clarify which dataset they want to query.

The retrieval system found multiple matching datasets with similar relevance \
scores. Present the options clearly and let the user choose.

## How to Present
1. Frame as: "I found {n} datasets that match your question. \
Which perspective are you looking for?"
2. For each option, explain IN BUSINESS TERMS what it covers.
   Do NOT expose technical names like explore IDs or model names.
3. Give a concrete example of what each dataset would answer.
4. Number the options so the user can reply "1" or "2".
5. Keep it under 4 sentences per option.

## Example
"I found 2 datasets that match 'total spend':

1. **Card Member Spending** -- Total billed business across all card \
transactions. This is the standard metric for spending volume analysis.

2. **Merchant Revenue** -- Revenue from merchant discount fees on \
transactions. This measures how much Amex earns from merchants.

Which angle are you looking for? (just reply with the number)"

## Rules
- NEVER guess. Always ask.
- Show top 3 at most, even if more alternatives exist.
- If options differ by time granularity, business segment, or product type, \
explain that difference explicitly.
"""


def create_disambiguation_agent(reasoning_llm) -> LlmAgent:
    """Disambiguation sub-agent.

    Uses Gemini Pro (accuracy-critical) because choosing the wrong
    explore means wrong data. Getting this wrong erodes trust.

    Args:
        reasoning_llm: SafeChainLlm instance (Pro, no tools).

    Returns:
        Configured LlmAgent.
    """
    return LlmAgent(
        name="disambiguation_agent",
        model=reasoning_llm,
        description="Presents dataset options when the query is ambiguous.",
        instruction=DISAMBIGUATION_INSTRUCTION,
        tools=[],
    )


# =====================================================================
# Clarification Agent
# =====================================================================

CLARIFICATION_INSTRUCTION = """\
You are helping a user rephrase their question so the system can find \
matching data.

The retrieval system could not confidently match the user's question to \
any dataset. This usually means the user's terminology does not match \
any known fields, or the question is too vague.

## How to Respond
1. Frame as: "I want to make sure I get this right."
2. Suggest 2-3 SPECIFIC rephrased versions of their question.
3. Each suggestion should use terms the system is likely to recognize.
4. Offer a discovery option: "You can also ask 'what metrics are available?' \
to see the full list."

## Example
"I want to make sure I get this right. When you say 'customer value', \
do you mean:

1. **Total billed business** per card member (spending volume)
2. **Customer lifetime value** score (predictive metric)
3. **Net revenue** per card member (profitability)

You can also ask me 'what metrics are available?' to see the full list."

## Rules
- NEVER say "I don't understand" or "I can't find that."
- NEVER expose technical details (similarity scores, explore names).
- Always provide a concrete path forward (rephrase suggestions or discovery).
- Keep it under 6 sentences total.
"""


def create_clarification_agent(reasoning_llm) -> LlmAgent:
    """Clarification sub-agent.

    Uses Gemini Pro (accuracy-critical) because rephrasing suggestions
    need to be precise and domain-aware.

    Args:
        reasoning_llm: SafeChainLlm instance (Pro, no tools).

    Returns:
        Configured LlmAgent.
    """
    return LlmAgent(
        name="clarification_agent",
        model=reasoning_llm,
        description="Helps users rephrase questions when retrieval confidence is low.",
        instruction=CLARIFICATION_INSTRUCTION,
        tools=[],
    )


# =====================================================================
# Boundary Agent
# =====================================================================

BOUNDARY_INSTRUCTION = """\
You are politely redirecting a request that is outside the system's \
capabilities.

This system can ONLY:
- Query financial data from BigQuery via Looker (spending, card members, \
merchants, travel, risk)
- Explore available metrics, dimensions, and datasets
- Show existing dashboards and saved queries

It CANNOT:
- Make predictions or forecasts
- Access non-financial data (HR, email, calendar)
- Modify data or run UPDATE/DELETE operations
- Answer general knowledge questions

## How to Respond
1. Acknowledge what they asked (do NOT ignore it).
2. Explain what you CAN do (brief, 1 sentence).
3. Suggest a SPECIFIC related data question they could ask.
4. Keep total response to 3-4 sentences.

## Example
"I'm designed to help you query American Express financial data -- things \
like spending trends, card member metrics, and merchant analytics. I can't \
make predictions about future performance, but I can show you historical \
trends. For example, would you like to see total billed business by quarter \
for the last year?"

## Rules
- NEVER start with "I can't" or "I'm sorry."
- Lead with what you CAN do.
- Always end with a concrete suggestion.
"""


def create_boundary_agent(classifier_llm) -> LlmAgent:
    """Boundary sub-agent for out-of-scope queries.

    Uses Gemini Flash (simple task, speed matters).

    Args:
        classifier_llm: SafeChainLlm instance (Flash, no tools).

    Returns:
        Configured LlmAgent.
    """
    return LlmAgent(
        name="boundary_agent",
        model=classifier_llm,
        description="Gracefully handles out-of-scope queries with helpful alternatives.",
        instruction=BOUNDARY_INSTRUCTION,
        tools=[],
    )
