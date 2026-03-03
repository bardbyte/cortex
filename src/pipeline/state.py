"""Cortex pipeline state — shared context flowing through the agent.

This is the contract between all pipeline stages. Every tool, callback,
and sub-agent reads from and writes to this state. Change it carefully —
everything downstream depends on these field names and types.

Architecture note:
  We use Google ADK for agent orchestration. The state here maps to the
  agent's session state. ADK manages tool routing, but WE control which
  tools are available and what the agent's instructions are — keeping the
  pipeline deterministic where it matters.
"""

from dataclasses import dataclass, field


@dataclass
class CortexState:
    """The full state of a single query through the Cortex pipeline.

    Lifecycle:
      1. User query comes in → populate `user_query`
      2. Intent stage → fills `intent`, `complexity`, `is_answerable`
      3. Entity stage → fills `entities`, `resolved_terms`
      4. Retrieval stage → fills `retrieval_result`
      5. SQL generation → fills `generated_sql`, `looker_query_spec`
      6. Validation + execution → fills `validation`, `query_results`
      7. Response formatting → fills `formatted_response`
    """

    # ── Input ────────────────────────────────────────────────
    user_query: str = ""
    conversation_history: list[dict] = field(default_factory=list)

    # ── Stage 1: Intent Classification ───────────────────────
    # Populated by the intent classification tool.
    # Drives routing: answerable → retrieval, ambiguous → disambiguate,
    # out_of_scope → graceful refusal, follow_up → merge with history.
    # data_query | ambiguous | out_of_scope | follow_up | definition | discovery
    intent: str = ""
    complexity: str = ""      # simple | moderate | complex
    is_answerable: bool = False

    # ── Stage 2: Entity Extraction ───────────────────────────
    # Business concepts extracted from the query, resolved against taxonomy.
    # Example: {"metrics": ["total spend"], "dimensions": ["merchant category"],
    #           "filters": {}, "time_range": "last quarter"}
    entities: dict = field(default_factory=dict)
    resolved_terms: dict = field(default_factory=dict)  # user term → canonical name

    # ── Stage 3: Retrieval ───────────────────────────────────
    # Output of the hybrid retrieval system (vector + graph + fewshot → fusion).
    # This is a RetrievalResult dict — see src/retrieval/models.py for schema.
    retrieval_result: dict = field(default_factory=dict)

    # ── Stage 4: SQL Generation ──────────────────────────────
    # Looker MCP generates SQL deterministically. No LLM involved.
    generated_sql: str = ""
    # {model, explore, fields, filters, sorts}
    looker_query_spec: dict = field(default_factory=dict)

    # ── Stage 5: Validation + Execution ──────────────────────
    validation: dict = field(default_factory=dict)    # {valid, errors, bytes_estimate}
    query_results: dict = field(default_factory=dict)  # {rows, columns, row_count, bytes_scanned}

    # ── Stage 6: Response ────────────────────────────────────
    formatted_response: str = ""
    follow_up_suggestions: list[str] = field(default_factory=list)

    # ── Control ──────────────────────────────────────────────
    retry_count: int = 0
    errors: list[str] = field(default_factory=list)
