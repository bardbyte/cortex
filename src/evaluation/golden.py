"""Golden dataset loader and evaluation runner.

Owner: Animesh

The golden dataset is the ground truth for measuring pipeline accuracy.
Each entry is a human-verified {question → expected answer} pair.

Three sources for building golden queries:
1. Looker query history (highest value — real usage patterns)
2. SME-generated questions (20 per BU from domain analysts)
3. Synthetic generation (LLM generates questions from explore schemas)

Evaluation levels:
- Component: retrieval accuracy (model/explore/dimension/measure selection)
- Pipeline: end-to-end execution accuracy (correct results?)
- User: satisfaction metrics (thumbs up/down, correction rate)
"""

import json
from dataclasses import asdict
from pathlib import Path

from src.retrieval.models import GoldenQuery


def load_golden_dataset(dataset_dir: str | Path) -> list[GoldenQuery]:
    """Load golden queries from JSON files."""
    path = Path(dataset_dir)
    queries = []
    for json_file in sorted(path.glob("*.json")):
        if json_file.name.startswith("_"):
            continue
        with open(json_file) as f:
            data = json.load(f)
        # Support both single query and list of queries per file
        if isinstance(data, list):
            queries.extend(GoldenQuery(**q) for q in data)
        else:
            queries.append(GoldenQuery(**data))
    return queries


def evaluate_retrieval(
    predicted: dict,
    expected: GoldenQuery,
) -> dict:
    """Evaluate a single retrieval prediction against golden truth.

    Returns per-component accuracy metrics:
    - model_correct: bool
    - explore_correct: bool
    - dimension_recall: float (0-1)
    - dimension_precision: float (0-1)
    - measure_recall: float (0-1)
    - measure_precision: float (0-1)
    """
    result = {}

    result["model_correct"] = predicted.get("model") == expected.model
    result["explore_correct"] = predicted.get("explore") == expected.explore

    # Dimension metrics
    pred_dims = set(predicted.get("dimensions", []))
    exp_dims = set(expected.dimensions)
    if exp_dims:
        result["dimension_recall"] = len(pred_dims & exp_dims) / len(exp_dims)
    else:
        result["dimension_recall"] = 1.0 if not pred_dims else 0.0
    if pred_dims:
        result["dimension_precision"] = len(pred_dims & exp_dims) / len(pred_dims)
    else:
        result["dimension_precision"] = 1.0 if not exp_dims else 0.0

    # Measure metrics
    pred_measures = set(predicted.get("measures", []))
    exp_measures = set(expected.measures)
    if exp_measures:
        result["measure_recall"] = len(pred_measures & exp_measures) / len(exp_measures)
    else:
        result["measure_recall"] = 1.0 if not pred_measures else 0.0
    if pred_measures:
        result["measure_precision"] = len(pred_measures & exp_measures) / len(pred_measures)
    else:
        result["measure_precision"] = 1.0 if not exp_measures else 0.0

    return result


def run_evaluation(
    golden_queries: list[GoldenQuery],
    predict_fn,
) -> dict:
    """Run evaluation across a full golden dataset.

    Args:
        golden_queries: List of golden queries to evaluate
        predict_fn: Function that takes a query string and returns retrieval result dict

    Returns:
        Aggregate metrics across all queries
    """
    results = []
    for gq in golden_queries:
        prediction = predict_fn(gq.natural_language)
        metrics = evaluate_retrieval(prediction, gq)
        metrics["query_id"] = gq.id
        metrics["complexity"] = gq.complexity
        results.append(metrics)

    # Aggregate
    n = len(results)
    if n == 0:
        return {"error": "No queries to evaluate"}

    return {
        "total_queries": n,
        "model_accuracy": sum(r["model_correct"] for r in results) / n,
        "explore_accuracy": sum(r["explore_correct"] for r in results) / n,
        "avg_dimension_recall": sum(r["dimension_recall"] for r in results) / n,
        "avg_dimension_precision": sum(r["dimension_precision"] for r in results) / n,
        "avg_measure_recall": sum(r["measure_recall"] for r in results) / n,
        "avg_measure_precision": sum(r["measure_precision"] for r in results) / n,
        "per_query": results,
    }
