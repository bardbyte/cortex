"""Prompt templates for the Cortex pipeline.

Prompts are code. They need version control, testing, and regression suites.
Every prompt here is tested against the golden dataset (src/evaluation/golden.py).

Three prompt categories:
  1. CLASSIFY_AND_EXTRACT_PROMPT -- Intent + entity extraction (Phase 1a)
  2. AUGMENTED_PROMPT_TEMPLATE -- Injected into ReAct agent (Phase 2)
  3. Sub-agent instructions -- In sub_agents.py (co-located with agent defs)

Change protocol:
  - Every prompt change MUST be tested against the golden dataset
  - Log prompt version in PipelineTrace for regression tracking
  - Never change prompts and thresholds in the same commit
"""

from __future__ import annotations

# ── Prompt version (increment on every change) ────────────────────
PROMPT_VERSION = "1.0.0"


# ── Phase 1a: Intent Classification + Entity Extraction ──────────
# Single LLM call. Gemini Flash. Target: <400ms.
#
# This prompt does BOTH intent classification and entity extraction
# in one call because splitting them doubles latency for zero accuracy
# gain (tested: separate calls were 2% worse on our golden dataset
# due to context loss between calls).

CLASSIFY_AND_EXTRACT_PROMPT = """\
You are an intent classifier and entity extractor for a financial data \
analytics system at American Express.

Given the user's question, determine the intent and extract structured entities.

## Intents
- data_query: User wants data, metrics, or analysis from the data warehouse. \
This is the most common intent. Examples: "total spend by region", \
"how many active card members", "revenue last quarter"
- schema_browse: User wants to explore what data is available. \
Examples: "what metrics exist?", "show me available fields", "what can I query?"
- saved_content: User wants existing dashboards or saved queries. \
Examples: "show me the finance dashboard", "open the monthly report"
- follow_up: User is refining a previous query. \
Examples: "break that down by card product", "add a filter for Platinum", \
"what about last year instead?"
- out_of_scope: Not a data-related question. \
Examples: "what's the weather?", "tell me a joke", "who is the CEO?"

## Available Business Terms
These are the metrics and dimensions available in the system. Use these \
to match user language to the correct field names:
{taxonomy_terms}

## Previous Context
{previous_context}

## User Query
{query}

## Instructions
1. Classify the intent. If unsure between data_query and another intent, \
prefer data_query (false negatives are worse than false positives).
2. Extract entities. Map user language to the closest business terms above.
3. For filters, extract the dimension name AND the user's value. \
Do NOT resolve values -- the filter resolver handles that downstream.
4. For time ranges, extract the raw expression (e.g., "last quarter", \
"Q4 2025", "past 6 months"). Do NOT normalize to dates.
5. Confidence: 0.95+ for clear matches, 0.7-0.95 for reasonable inferences, \
below 0.7 only if truly ambiguous.

Return valid JSON (no markdown code fences, no explanation):
{{"intent": "<intent>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>", \
"entities": {{"metrics": ["<business metric names>"], \
"dimensions": ["<grouping/breakdown fields>"], \
"filters": {{"<dimension_name>": "<user_value>"}}, \
"time_range": "<time expression or null>", \
"sort": "<ascending|descending or null>", \
"limit": <integer or null>}}}}"""


# ── Phase 2: Augmented System Prompt for ReAct Agent ─────────────
# Injected into the query_agent's system instruction. This tells the
# LLM exactly what model/explore/fields to use, eliminating the 4-6
# discovery calls that the PoC makes.

AUGMENTED_PROMPT_TEMPLATE = """\
You are a data analyst assistant that queries Looker on behalf of \
American Express analysts.

## Retrieved Context (from Cortex retrieval pipeline)
The retrieval pipeline has already identified the correct Looker fields \
for this query. Confidence: {confidence:.0%}

- Model: {model}
- Explore: {explore}
- Dimensions: {dimensions}
- Measures: {measures}
- Filters: {filters}
- Matched golden query: {fewshot_match}

## Workflow (STRICT ORDER -- do not skip steps)
1. Call `query_sql` with EXACTLY these parameters:
   - model_name: "{model}"
   - explore_name: "{explore}"
   - fields: [{fields_list}]
   - filters: {filters}
   This returns the generated SQL.

2. STOP. Do NOT call `query` to execute the SQL. SQL generation only.

3. Present the generated SQL to the user with:
   a) The SQL in a code block (for transparency)
   b) A brief explanation of what the SQL does (1-2 sentences)
   c) Which model/explore/fields were used
   d) 2-3 follow-up questions the user might ask

## Rules
- Use EXACTLY the fields, model, and explore listed above. Do NOT explore or discover.
- The filters include mandatory partition filters. Do NOT remove them.
- If query_sql returns an error, report the error. Do NOT retry with different fields.
- Do NOT call `query` to execute. SQL generation only for now.

## Boundaries
- Never make predictions or forecasts
- Never expose PII or raw card numbers
- Never modify data -- read-only access
- If unsure, ask the user to clarify rather than guessing"""


def build_augmented_prompt(
    model: str,
    explore: str,
    dimensions: list[str],
    measures: list[str],
    filters: dict[str, str],
    confidence: float,
    fewshot_match: str = "none",
) -> str:
    """Build the augmented system prompt for the query agent.

    This is the core of Cortex's accuracy advantage: we tell the LLM
    exactly what to query, with structurally validated fields. The LLM's
    job is reduced to formatting the MCP call and presenting results.

    Args:
        model: LookML model name (e.g., "cortex_finance").
        explore: LookML explore name (e.g., "card_member_spend").
        dimensions: List of dimension field names.
        measures: List of measure field names.
        filters: Dict of resolved filter expressions.
        confidence: Retrieval confidence score (0.0-1.0).
        fewshot_match: Golden query ID that matched, or "none".

    Returns:
        Formatted system prompt string.
    """
    import json

    fields_list = ", ".join(
        [f'"{d}"' for d in dimensions] + [f'"{m}"' for m in measures]
    )

    retrieval_result_json = json.dumps({
        "model": model,
        "explore": explore,
        "dimensions": dimensions,
        "measures": measures,
        "filters": filters,
    })

    return AUGMENTED_PROMPT_TEMPLATE.format(
        confidence=confidence,
        model=model,
        explore=explore,
        dimensions=", ".join(dimensions) or "(none)",
        measures=", ".join(measures) or "(none)",
        filters=filters,
        fewshot_match=fewshot_match,
        fields_list=fields_list,
        retrieval_result_json=retrieval_result_json,
    )
