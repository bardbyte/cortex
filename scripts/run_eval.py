"""Run golden dataset evaluation.

Usage:
    python scripts/run_eval.py --dataset=tests/golden_queries/finance/
    python scripts/run_eval.py --dataset=tests/golden_queries/ --output=eval_results/

What this should do:
  1. Load golden queries from the specified directory
  2. For each query, run through the Cortex pipeline (or a retrieval-only mode)
  3. Compare predicted {model, explore, dimensions, measures} against expected
  4. Compute per-component metrics:
     - Model accuracy (target: >98%)
     - Explore accuracy (target: >95%)
     - Dimension recall (target: >90%)
     - Dimension precision (target: >85%)
     - Measure accuracy (target: >95%)
  5. Save results to JSON and print summary

Dependencies:
  - src/evaluation/golden.py (loader + evaluator — already implemented)
  - A predict_fn that takes NL query → returns retrieval result dict

See: src/evaluation/golden.py for the evaluation logic.
See: tests/golden_queries/finance/_template.json for the golden query format.
"""

if __name__ == "__main__":
    raise NotImplementedError(
        "Implement: load golden dataset, run predictions, call run_evaluation(), save results"
    )
