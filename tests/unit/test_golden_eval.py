"""Tests for golden dataset evaluation logic."""

from src.evaluation.golden import evaluate_retrieval


def test_perfect_retrieval():
    predicted = {
        "model": "finance",
        "explore": "transactions",
        "dimensions": ["merchants.category_name"],
        "measures": ["transactions.total_amount"],
    }
    expected = {
        "model": "finance",
        "explore": "transactions",
        "dimensions": ["merchants.category_name"],
        "measures": ["transactions.total_amount"],
    }
    result = evaluate_retrieval(predicted, expected)
    assert result["model_correct"] is True
    assert result["explore_correct"] is True
    assert result["dimension_recall"] == 1.0
    assert result["measure_recall"] == 1.0


def test_wrong_model():
    predicted = {"model": "marketing", "explore": "transactions",
                 "dimensions": [], "measures": []}
    expected = {"model": "finance", "explore": "transactions",
                "dimensions": [], "measures": []}
    result = evaluate_retrieval(predicted, expected)
    assert result["model_correct"] is False


def test_partial_dimension_recall():
    predicted = {"model": "finance", "explore": "transactions",
                 "dimensions": ["merchants.category_name"],
                 "measures": ["transactions.total_amount"]}
    expected = {"model": "finance", "explore": "transactions",
                "dimensions": ["merchants.category_name", "merchants.region"],
                "measures": ["transactions.total_amount"]}
    result = evaluate_retrieval(predicted, expected)
    assert result["dimension_recall"] == 0.5
