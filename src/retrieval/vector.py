"""Entity extraction and vector field matching for retrieval.

This module implements a query-to-entities retrieval flow:
  1) Extract structured entities from natural language using LLM.
  2) Normalize extracted entities to reduce model drift.
  3) Generate embeddings for measures/dimensions with BGE instruction prefix.
  4) Search pgvector 'field_embeddings' for top-k similar fields.
  5) Return output with candidates and filters for downstream SQL planning.

Usage:
    python -m src.retrieval.vector
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import text
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """Custom SQLAlchemy type for pgvector."""
    cache_ok = True
    name = "vector"


from src.adapters.model_adapter import get_model
from config.constants import (
    LLM_MODEL_IDX,
    EMBED_MODEL_IDX,
    BGE_QUERY_PREFIX,
    SQL_SEARCH_SIMILAR_FIELDS,
    SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE,
)
from src.connectors.postgres_age_client import get_engine

logger = logging.getLogger(__name__)


def _bootstrap_environment() -> None:
    """Load .env and ensure CONFIG_PATH is available for safechain/ee_config."""
    load_dotenv(find_dotenv())
    if not os.getenv("CONFIG_PATH"):
        repo_root = Path(__file__).resolve().parents[2]
        default_config_path = repo_root / "config" / "config.yml"
        os.environ["CONFIG_PATH"] = str(default_config_path)
        logger.info("[retrieval.vector] CONFIG_PATH set to: %s", default_config_path)
    else:
        logger.info("[retrieval.vector] CONFIG_PATH already set to: %s", os.getenv("CONFIG_PATH"))


_bootstrap_environment()


@dataclass
class ExtractedEntity:
    """Represents an extracted entity from user query."""
    entity_type: str
    raw_text: str
    embedding: list[float] | None = None


@dataclass
class FieldMatch:
    """Represents a matched field from the database."""
    field_key: str
    field_name: str
    label: str | None
    explore_name: str
    view_name: str
    similarity: float
    field_type: str | None = None
    measure_type: str | None = None


@dataclass
class EntityCandidate:
    """Represents a candidate field match for an entity."""
    explore: str
    field_key: str
    field_name: str
    similarity: float


@dataclass
class Entity:
    """Represents an entity in the structured output format."""
    id: str
    type: str
    weight: float
    candidates: list[EntityCandidate] | None = None
    operators: list[str] | None = None
    values: list[str] | None = None


@dataclass
class ExtractedEntities:
    """Structured entity extraction result."""
    measures: list[str]
    dimensions: list[str]
    time_range: str | None
    filters: list[dict[str, Any]]


class EntityExtractor:
    """Extract entities from user queries and match them to database fields."""

    ENTITY_EXTRACTION_PROMPT = """You are an expert at extracting structured entities from natural language queries about business data.

Given a user question, extract:
1. measures: KPIs or numerics being requested
2. dimensions: categories/attributes being requested (do not include filter values here)
3. time_range: time expression if present
4. filters: explicit filter conditions

For filters:
  - Use "field_hint" to describe the conceptual field
  - Extract raw values exactly as written
  - Do NOT add partition filters
  - Do NOT duplicate filter values in dimensions
  - If there is no explicit aggregation intent (count/sum/avg/total), prefer returning dimensions + filters and keep measures empty

Return ONLY valid JSON.

Example:
  User: "Customer counts for Millennial customers last quarter"
  Output:
  {{
    "measures": ["customer count"],
    "dimensions": ["generation"],
    "time_range": "last quarter",
    "filters": [
        {{"field_hint": "generation",
         "values": ["Millennial"],
         "operator": "="}}
    ]
  }}

Now extract entities from this query:
  User: "{query}"
  Output:
"""

    METRIC_INTENT_TERMS = {
        "count", "number", "numbers", "total", "sum", "average",
        "maximum", "max", "minimum", "min", "rate", "ratio", "percent",
        "how many", "highest", "lowest", "top",
    }

    GENERIC_CUSTOMER_MEASURES = {
        "customer count",
        "customer's count",
    }

    def __init__(self, llm_model_idx: str = LLM_MODEL_IDX, embedding_model_idx: str = EMBED_MODEL_IDX):
        self.llm_model_idx = llm_model_idx
        self.embedding_model_idx = embedding_model_idx
        logger.info("Initializing LLM model '%s' for entity extraction", llm_model_idx)
        self.llm_client = get_model(llm_model_idx)
        logger.info("Initializing embedding model '%s' for vector search", embedding_model_idx)
        self.embedding_client = get_model(embedding_model_idx)

    def _has_metric_intent(self, query: str) -> bool:
        lowered = query.lower()
        return any(term in lowered for term in self.METRIC_INTENT_TERMS)

    def _normalize_terms(self, query: str, extracted: ExtractedEntities) -> ExtractedEntities:
        logger.info("Normalizing entities for query '%s'", query)
        logger.info(
            "Extracted: measures=%d, dimensions=%d, filters=%d",
            len(extracted.measures),
            len(extracted.dimensions),
            len(extracted.filters),
        )

        dimensions = list(extracted.dimensions)
        measures = list(extracted.measures)

        has_metric_intent = self._has_metric_intent(query)
        query_lower = query.lower()

        if not dimensions and ("customer" in query_lower or "customers" in query_lower):
            dimensions.append("customer")

        if has_metric_intent and not measures:
            for term in self.GENERIC_CUSTOMER_MEASURES:
                if term in query_lower:
                    measures.append(term)
                    break

        if has_metric_intent and not measures:
            measures.append("count")

        return ExtractedEntities(
            measures=measures,
            dimensions=dimensions,
            time_range=extracted.time_range,
            filters=extracted.filters,
        )

    @staticmethod
    def _extract_json_from_llm_response(raw: str) -> str:
        """Extract JSON object from LLM response that may contain markdown fences or preamble.

        Handles:
          - ```json { ... } ```
          - ``` { ... } ```
          - Preamble text before the JSON object
          - Trailing text after the JSON object
        """
        text = raw.strip()

        # Strip markdown code fences
        if "```" in text:
            # Find content between first ``` and last ```
            parts = text.split("```")
            for part in parts:
                candidate = part.strip()
                # Skip the language tag (e.g., "json")
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    text = candidate
                    break

        # Find the first { and last } to extract the JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]

        return text

    def _parse_entity_json(self, json_str: str) -> ExtractedEntities:
        """Parse LLM JSON response into ExtractedEntities, tolerating key variations."""
        cleaned = self._extract_json_from_llm_response(json_str)
        entities_dict = json.loads(cleaned)

        measures = (entities_dict.get("measures")
                    or entities_dict.get("Metrics")
                    or entities_dict.get("metrics")
                    or [])
        dimensions = (entities_dict.get("dimensions")
                      or entities_dict.get("Dimensions")
                      or [])
        time_range = (entities_dict.get("time_range")
                      or entities_dict.get("Time_range"))
        filters = (entities_dict.get("filters")
                   or entities_dict.get("Filters")
                   or [])

        return ExtractedEntities(
            measures=measures or [],
            dimensions=dimensions or [],
            time_range=time_range,
            filters=filters or [],
        )

    MAX_EXTRACTION_RETRIES = 3

    def extract_entities(self, query: str) -> ExtractedEntities:
        """Extract entities from query with retry on LLM/JSON failure.

        On failure: retries once (LLM responses are non-deterministic, a retry
        often produces valid JSON). If both attempts fail, returns empty entities
        and logs at ERROR level so the pipeline's confidence gate can reject.
        """
        prompt = self.ENTITY_EXTRACTION_PROMPT.replace("{query}", query)

        for attempt in range(1, self.MAX_EXTRACTION_RETRIES + 1):
            try:
                response = self.llm_client.invoke(prompt)
                # SafeChain returns LangChain AIMessage, not raw string
                json_str = response.content if hasattr(response, 'content') else str(response)
                logger.debug("LLM raw response (attempt %d): %s", attempt, json_str[:200])
                return self._parse_entity_json(json_str)
            except json.JSONDecodeError as exc:
                # Log the raw response so we can see what the LLM actually returned
                logger.warning(
                    "Attempt %d/%d: Failed to parse LLM response as JSON: %s\n  Raw: %.200s",
                    attempt, self.MAX_EXTRACTION_RETRIES, exc, json_str,
                )
            except Exception as exc:
                logger.warning(
                    "Attempt %d/%d: Error during entity extraction: %s",
                    attempt, self.MAX_EXTRACTION_RETRIES, exc,
                )

        logger.error(
            "Entity extraction failed after %d attempts for query: %s",
            self.MAX_EXTRACTION_RETRIES, query,
        )
        return ExtractedEntities(measures=[], dimensions=[], time_range=None, filters=[])

    def embed_text(self, text: str, is_query: bool = True) -> list[float]:
        """Generate embedding with BGE instruction prefix for queries.

        BGE-large-en-v1.5 was trained with asymmetric instructions:
        - Queries need prefix: "Represent this sentence for searching relevant passages: "
        - Documents do NOT get a prefix (they're embedded as-is)
        Omitting the prefix on queries reduces accuracy by 2-5%.
        """
        if is_query:
            text = BGE_QUERY_PREFIX + text
        logger.info("Generating embedding for text snippet (len=%d, is_query=%s)", len(text), is_query)
        return self.embedding_client.embed_query(text)

    def search_similar_fields(
        self,
        entity_text: str,
        embedding: list[float],
        limit: int = 10,
        field_type: str | None = None,
    ) -> list[FieldMatch]:
        """Search pgvector for similar fields, optionally filtered by type."""
        engine = get_engine()
        embedding_literal = "[" + ", ".join(str(x) for x in embedding) + "]"

        with engine.connect() as conn:
            if field_type:
                result = conn.execute(
                    text(SQL_SEARCH_SIMILAR_FIELDS_BY_TYPE).bindparams(
                        embedding=embedding_literal,
                        field_type=field_type,
                        limit=limit,
                    )
                )
            else:
                result = conn.execute(
                    text(SQL_SEARCH_SIMILAR_FIELDS).bindparams(
                        embedding=embedding_literal,
                        limit=limit,
                    )
                )
            rows = result.fetchall()

        results = [
            FieldMatch(
                field_key=row[0],
                field_name=row[1],
                label=row[2],
                explore_name=row[3],
                view_name=row[4],
                field_type=row[5],
                measure_type=row[6],
                similarity=float(row[7]),
            )
            for row in rows
        ]
        return results

    def process_query(self, query: str, top_k: int = 5) -> dict[str, Any]:
        logger.info("Starting process_query for query='%s' with top_k=%d", query, top_k)
        extracted = self.extract_entities(query)
        extracted = self._normalize_terms(query, extracted)

        entities: list[dict[str, Any]] = []
        entity_id_counter = 1

        for measure_text in extracted.measures:
            logger.info("Processing measure entity '%s'", measure_text)
            embedding = self.embed_text(measure_text, is_query=True)
            matches = self.search_similar_fields(
                measure_text, embedding, limit=top_k, field_type="measure"
            )
            candidates = [
                {
                    "explore": match.explore_name,
                    "field_key": match.field_key,
                    "field_name": match.field_name,
                    "label": match.label,
                    "view_name": match.view_name,
                    "measure_type": match.measure_type,
                    "similarity": match.similarity,
                }
                for match in matches
            ]
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "measure",
                "name": measure_text,
                "weight": 1.0,
                "candidates": candidates,
            })
            entity_id_counter += 1

        for dimension_text in extracted.dimensions:
            logger.info("Processing dimension entity '%s'", dimension_text)
            # No generic enrichment — embed the raw dimension text.
            # The embedding documents already contain rich synonyms via LookML descriptions.
            embedding = self.embed_text(dimension_text, is_query=True)
            matches = self.search_similar_fields(
                dimension_text, embedding, limit=top_k, field_type="dimension"
            )
            candidates = [
                {
                    "explore": match.explore_name,
                    "field_key": match.field_key,
                    "field_name": match.field_name,
                    "label": match.label,
                    "view_name": match.view_name,
                    "measure_type": match.measure_type,
                    "similarity": match.similarity,
                }
                for match in matches
            ]
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "dimension",
                "name": dimension_text,
                "weight": 1.0,
                "candidates": candidates,
            })
            entity_id_counter += 1

        for filter_item in extracted.filters:
            logger.info("Processing filter entity '%s'", filter_item)
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "filter",
                "name": filter_item.get("field_hint", "filter"),
                "operator": filter_item.get("operator", "IN"),
                "values": filter_item.get("values", []),
                "weight": 0.8,
            })
            entity_id_counter += 1

        if extracted.time_range:
            logger.info("Processing time range filter '%s'", extracted.time_range)
            entities.append({
                "id": f"E{entity_id_counter}",
                "type": "time_range",
                "name": "time_range",
                "operator": "IN",
                "values": [extracted.time_range],
                "weight": 0.8,
            })

        logger.info("process_query complete: total_entities=%d", len(entities))
        return {"query": query, "entities": entities}

    def format_results(self, results: dict[str, Any]) -> str:
        output = []
        output.append(f"\nQUERY: {results['query']}")
        output.append("=" * 80)

        entities = results.get("entities", [])
        for entity in entities:
            if entity["type"] in ("measure", "dimension"):
                output.append(f"\n  {entity['name']}  (Weight: {entity['weight']:.1f})")
                output.append(f"    Type: {entity['type'].upper()}")
                if entity.get("candidates"):
                    for rank, candidate in enumerate(entity["candidates"], start=1):
                        output.append(
                            f"     Rank {rank}: {candidate.get('field_name', ''):<30} "
                            f"view={candidate.get('view_name', ''):<30} "
                            f"sim={candidate.get('similarity', 0.0):.4f}"
                        )
                else:
                    output.append("     (No candidates found)")
            elif entity["type"] == "filter":
                output.append(f"\n  {entity['name']}  (Weight: {entity['weight']:.1f})")
                output.append(f"    FILTER: {entity.get('name', '')}")
                output.append(f"    Operator: {entity.get('operator', 'IN')}")
                output.append(f"    Values: {entity.get('values', [])}")

        output.append("\n" + "=" * 80)
        return "\n".join(output)


def _demo_run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\nEntity Extractor Demo (src.retrieval.vector)")
    print("=" * 80)
    print("[1/4] Initializing extractor...")
    extractor = EntityExtractor()

    sample_query = "Total billed business by generation"
    print(f"[2/4] Running query: {sample_query}")
    results = extractor.process_query(sample_query, top_k=5)

    print("[3/4] Rendering formatted output...")
    print(extractor.format_results(results))

    print(f"[4/4] JSON output:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    _demo_run()
