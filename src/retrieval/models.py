"""Shared data models for the retrieval system.

These are the CONTRACTS between retrieval channels and the fusion layer.
Change with care — all three channels and the pipeline depend on these.
"""

from dataclasses import dataclass, field


@dataclass
class FieldCandidate:
    """A single LookML field returned by any retrieval channel."""

    field_name: str  # e.g. "total_amount"
    field_type: str  # "dimension" | "measure"
    data_type: str  # "string" | "number" | "date" | "yesno"
    view: str  # e.g. "transactions"
    explore: str  # e.g. "transactions"
    model: str  # e.g. "finance"
    description: str  # LookML description
    score: float  # Source-specific relevance score
    source: str  # "vector" | "graph" | "fewshot"
    group_label: str = ""
    synonyms: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Final fused retrieval output — the input to Looker MCP."""

    action: str  # "proceed" | "disambiguate" | "clarify" | "no_match"
    model: str = ""
    explore: str = ""
    dimensions: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    coverage: float = 0.0
    alternatives: list[dict] = field(default_factory=list)  # For disambiguation
    fewshot_matches: list[str] = field(default_factory=list)  # Golden query IDs


@dataclass
class GoldenQuery:
    """A verified question→answer pair for few-shot retrieval and evaluation."""

    id: str  # e.g. "GQ-fin-001"
    natural_language: str
    model: str
    explore: str
    dimensions: list[str]
    measures: list[str]
    filters: dict[str, str] = field(default_factory=dict)
    complexity: str = "moderate"  # simple | moderate | complex
    domain: str = ""  # e.g. "spending_analysis"
    validated: bool = False
    validated_by: str = ""
