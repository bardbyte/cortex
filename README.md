# Cortex

> Natural language to SQL over enterprise data — no LLM-generated SQL.

Cortex translates business questions into correct, cost-controlled SQL queries using Looker's semantic layer. The LLM picks the right fields; Looker MCP generates the SQL deterministically.

## How It Works

```
User Question
    ↓
Intent Classification → Entity Extraction
    ↓
Hybrid Retrieval (Vector + Graph + Few-shot)
    ↓
Looker MCP → Deterministic SQL
    ↓
BigQuery → Formatted Answer
```

**Three retrieval channels find the right LookML fields:**
- **Vector Search** (Vertex AI) — semantic similarity on field descriptions
- **Graph Search** (Neo4j) — structural validation (are these fields in the same explore?)
- **Few-shot Match** (FAISS) — match against known-good query patterns

## Getting Started

```bash
git clone <repo-url> && cd cortex
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # Fill in Looker + Neo4j credentials
python examples/verify_setup.py
```

## Contributing

**Pick an issue from the [issue board](../../issues).** Each issue maps to a module, has clear acceptance criteria, and tells you where to start.

### How the repo works

Every module has **interfaces defined, implementation left to you**. Functions raise `NotImplementedError` with a hint. Read the docstring, implement the function, write a test.

**Contracts** (don't change signatures):
- `src/retrieval/models.py` — data models
- `src/pipeline/state.py` — pipeline state
- `src/taxonomy/schema.py` — taxonomy validation
- `src/evaluation/golden.py` — golden dataset evaluation

### Workflow

1. Pick an issue → branch `feature/<description>` from `main`
2. Implement the interface (stub has hints in its docstring)
3. Write tests in `tests/unit/`
4. `make lint && make test` — both must pass
5. PR → review → merge

## Project Structure

```
src/
├── pipeline/        # ADK agent orchestration
├── retrieval/       # Hybrid retrieval (vector + graph + fewshot + fusion)
├── taxonomy/        # Business term → LookML field mapping
├── evaluation/      # Golden dataset accuracy measurement
└── connectors/      # Looker MCP + LLM access clients
config/              # Retrieval weights, model config, MCP tools
tests/               # Unit, integration, golden queries
scripts/             # Setup, data loading, evaluation
taxonomy/            # Business term definitions (YAML)
```

## Key Decisions

- **ADK** for agent orchestration
- **Looker MCP** generates all SQL — we never write SQL
- **Hybrid retrieval** with RRF fusion — graph search is the quality gate
- **Per-field chunking** for vector search (not per-view)
- **Neo4j** stores LookML structure for structural validation
