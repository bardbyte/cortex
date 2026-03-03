# Cortex

> Semantic intelligence pipeline for natural language data access.

Cortex translates natural language questions into correct, cost-controlled SQL queries over enterprise data warehouses. It solves three problems:

1. **Understand** — Intent classification + entity extraction
2. **Find** — Hybrid retrieval to select the right semantic model elements (75% of error budget)
3. **Generate** — Deterministic SQL via Looker MCP (no LLM-generated SQL)

## Architecture

```
Query → Intent → Entities → ┌─ Vector Search (Vertex AI) ─┐
                             ├─ Graph Search (Neo4j)       ├→ RRF Fusion → Looker MCP → BigQuery → Response
                             └─ Few-Shot Match (FAISS)     ┘
```

## Project Structure

```
cortex/
├── src/
│   ├── pipeline/           # ADK agent orchestration
│   │   ├── agent.py        # ADK agent definition + tool registration
│   │   └── state.py        # Pipeline state schema
│   ├── retrieval/          # Hybrid retrieval system
│   │   ├── vector.py       # Vertex AI Search
│   │   ├── graph_search.py # Neo4j structural search
│   │   ├── fewshot.py      # FAISS golden query matching
│   │   ├── fusion.py       # RRF + structural validation
│   │   └── models.py       # Shared data models
│   ├── taxonomy/           # Business term management
│   │   └── schema.py       # Taxonomy YAML validation
│   ├── evaluation/         # Accuracy measurement
│   │   └── golden.py       # Golden dataset evaluation
│   └── connectors/         # External service clients
│       ├── safechain_client.py  # SafeChain LLM auth (CIBIS)
│       └── mcp_tools.py         # ADK McpToolset for Looker
├── config/
│   ├── models.yaml         # LLM model configuration
│   ├── retrieval.yaml      # Retrieval weights + thresholds
│   └── tools.yaml          # Looker MCP Toolbox configuration
├── examples/               # Runnable setup verification
│   └── verify_setup.py     # 5-check script: env → deps → auth → tools → LLM
├── tests/
│   ├── unit/               # Unit tests (pytest)
│   ├── integration/
│   └── golden_queries/     # Ground truth test sets
├── scripts/
│   ├── setup_github_issues.sh   # Creates issues + milestones via gh CLI
│   ├── load_lookml_to_neo4j.py  # LookML → Neo4j graph loader
│   └── run_eval.py              # Golden dataset evaluation runner
├── taxonomy/               # Canonical term definitions (YAML)
├── deployment/             # GKE + Terraform
└── notebooks/              # Exploration + benchmarking
```

## Getting Started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env         # Fill in your credentials (see below)
make check                   # Verify environment
```

### Environment Setup

All LLM access goes through **SafeChain** (CIBIS authentication). You need:

| Variable | Source | Purpose |
|----------|--------|---------|
| `CIBIS_CONSUMER_KEY` | IdaaS portal | SafeChain auth |
| `CIBIS_CONSUMER_SECRET` | IdaaS portal | SafeChain auth |
| `CIBIS_CONFIGURATION_ID` | IdaaS portal | SafeChain auth |
| `CONFIG_PATH` | Local file | SafeChain config (default: `config.yml`) |
| `LOOKER_INSTANCE_URL` | Looker admin | Looker MCP connection |
| `LOOKER_CLIENT_ID` | Looker admin | Looker API auth |
| `LOOKER_CLIENT_SECRET` | Looker admin | Looker API auth |

**Verify your setup:**
```bash
# Terminal 1: Start MCP Toolbox
source .env && export LOOKER_INSTANCE_URL LOOKER_CLIENT_ID LOOKER_CLIENT_SECRET
./toolbox --tools-file config/tools.yaml

# Terminal 2: Run all checks
python examples/verify_setup.py
```

### Local Development

```bash
docker compose up neo4j                                          # Start graph DB
python scripts/load_lookml_to_neo4j.py --lookml-dir=<path>      # Load LookML → graph
python -m src.pipeline.agent --query "total spend last quarter"  # Run pipeline
make test                                                        # Run tests
python scripts/run_eval.py --dataset=tests/golden_queries/       # Run evaluation
```

## Key Interfaces

These are the contracts between components. Changes require review.

### Taxonomy Entry (YAML)
```yaml
canonical_name: "Customer Acquisition Cost"
definition: "Total cost to acquire a new primary cardmember..."
synonyms: ["CAC", "CPNC", "Cost Per New Cardmember"]
lookml_target: { model: finance, explore: acquisitions, field: acquisitions.cac }
```

### Golden Query (JSON)
```json
{
  "id": "GQ-fin-001",
  "natural_language": "What was total spend by merchant category last quarter?",
  "model": "finance",
  "explore": "transactions",
  "dimensions": ["merchants.category_name"],
  "measures": ["transactions.total_amount"]
}
```

### Retrieval Result (Python)
```python
@dataclass
class RetrievalResult:
    action: str          # "proceed" | "disambiguate" | "clarify" | "no_match"
    model: str
    explore: str
    dimensions: list[str]
    measures: list[str]
    confidence: float
```

## Contributing

### How this repo works

Every module in `src/` has **interfaces defined, implementation left to you**. Functions that need implementation raise `NotImplementedError` with a comment pointing you to the pattern. Contracts (`models.py`, `state.py`, `schema.py`, `golden.py`) are fully implemented — don't change their signatures without review.

### Setup

```bash
python examples/verify_setup.py              # Must pass all 5 checks before you write code
scripts/setup_github_issues.sh               # Creates issues + milestones (run once per repo)
```

### Workflow

1. Pick an issue from the [issue board](../../issues)
2. Branch: `feature/<description>` from `main`
3. Implement the interface — each stub has hints in its docstring
4. Write tests in `tests/unit/` alongside your implementation
5. `make lint && make test` — both must pass
6. PR → 1 approval required → CI passes (lint + unit + golden eval)
7. Merge to `main`

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Credentials: CIBIS, Looker, GCP (from `.env.example`) |
| `config/tools.yaml` | Looker MCP Toolbox server configuration |
| `config/retrieval.yaml` | Fusion weights, thresholds, cache TTLs |
| `config/models.yaml` | LLM model selection per pipeline stage |
| `docker-compose.yaml` | Local Neo4j for development |
