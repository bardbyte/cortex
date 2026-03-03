.PHONY: check check-env lint test unit-test integration-test eval setup clean

setup:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	@echo "Setup complete. Run: source .venv/bin/activate"

check:
	@echo "Checking Python version..."
	python --version
	@echo "Checking environment..."
	@test -f .env && echo ".env: found" || echo ".env: MISSING (copy .env.example to .env)"
	@echo "Checking Neo4j..."
	docker compose ps neo4j 2>/dev/null && echo "Neo4j: running" || echo "Neo4j: not running (run 'docker compose up neo4j')"

check-env:
	python examples/verify_setup.py

lint:
	ruff check src/ tests/
	mypy src/

test: unit-test

unit-test:
	pytest tests/unit/ -v

integration-test:
	pytest tests/integration/ -v --timeout=60

eval:
	python scripts/run_eval.py --dataset=tests/golden_queries/

clean:
	rm -rf .venv __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
