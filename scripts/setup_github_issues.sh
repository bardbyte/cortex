#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Cortex — GitHub Issues Setup
# ─────────────────────────────────────────────────────────────────
# Run this from inside your cloned repo (enterprise or public).
#
# Prerequisites:
#   gh auth login (or gh auth login --hostname your-enterprise.com)
#   cd <repo-root>
#
# Usage:
#   chmod +x scripts/setup_github_issues.sh
#   ./scripts/setup_github_issues.sh
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

# ─── AUTO-DETECT REPO ─────────────────────────────────────────
# Extract owner/repo from git remote (works with SSH and HTTPS, enterprise or public)
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE_URL" ]; then
  echo "ERROR: No git remote 'origin' found. Run this from inside your repo."
  exit 1
fi

# Strip protocol, host, .git suffix → owner/repo
REPO_SLUG=$(echo "$REMOTE_URL" | sed -E 's#^(https?://[^/]+/|git@[^:]+:)##' | sed 's/\.git$//')
echo "Detected repo: $REPO_SLUG"

# Detect enterprise hostname for gh api calls
if echo "$REMOTE_URL" | grep -qE '^git@'; then
  GH_HOST=$(echo "$REMOTE_URL" | sed -E 's/^git@([^:]+):.*/\1/')
elif echo "$REMOTE_URL" | grep -qE '^https?://'; then
  GH_HOST=$(echo "$REMOTE_URL" | sed -E 's#^https?://([^/]+)/.*#\1#')
else
  GH_HOST="github.com"
fi

# Set GH_HOST env for enterprise (gh uses this for API routing)
if [ "$GH_HOST" != "github.com" ]; then
  export GH_HOST
  echo "Enterprise host: $GH_HOST"
fi

echo "=== Setting up Cortex GitHub project management ==="

# ─── HELPER: create issue using temp file (avoids shell quoting issues) ───
create_issue() {
  local title="$1"
  local labels="$2"
  local milestone="$3"
  local body="$4"

  local tmpfile
  tmpfile=$(mktemp)
  echo "$body" > "$tmpfile"

  gh issue create \
    --title "$title" \
    --label "$labels" \
    --milestone "$milestone" \
    --body-file "$tmpfile" 2>&1 || echo "  WARN: Failed to create: $title"

  rm -f "$tmpfile"
}

# ─── LABELS ─────────────────────────────────────────────────────
echo ""
echo "Creating labels..."

gh label create "retrieval"     --color "1d76db" --description "Hybrid retrieval system" --force
gh label create "pipeline"      --color "0e8a16" --description "ADK agent orchestration" --force
gh label create "taxonomy"      --color "d93f0b" --description "Business term taxonomy" --force
gh label create "evaluation"    --color "fbca04" --description "Golden dataset + accuracy" --force
gh label create "deployment"    --color "5319e7" --description "GKE, infra, CI/CD" --force
gh label create "connector"     --color "006b75" --description "Looker MCP, LLM access" --force
gh label create "ui"            --color "c2e0c6" --description "UI components" --force
gh label create "P0-critical"   --color "b60205" --description "Blocks May deadline" --force
gh label create "P1-important"  --color "e99695" --description "Important but not blocking" --force
gh label create "P2-nice"       --color "c5def5" --description "Nice to have" --force
gh label create "spike"         --color "d4c5f9" --description "Research / exploration" --force

# ─── MILESTONES ─────────────────────────────────────────────────
echo ""
echo "Creating milestones..."

gh api "repos/$REPO_SLUG/milestones" \
  -f title="M1: Prove the Loop" \
  -f description="One query end-to-end: NL -> intent -> retrieval -> Looker MCP -> BigQuery -> answer" \
  -f due_on="2026-03-21T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "  M1 exists"

gh api "repos/$REPO_SLUG/milestones" \
  -f title="M2: Reliable Retrieval" \
  -f description=">85% retrieval accuracy. All 3 channels operational." \
  -f due_on="2026-04-11T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "  M2 exists"

gh api "repos/$REPO_SLUG/milestones" \
  -f title="M3: Handle the Edges" \
  -f description=">90% accuracy. Boundary detection, disambiguation, caching." \
  -f due_on="2026-05-02T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "  M3 exists"

gh api "repos/$REPO_SLUG/milestones" \
  -f title="M4: Production Ready" \
  -f description="May deadline: 3 BUs, feedback loop, cost controls, monitoring." \
  -f due_on="2026-05-30T00:00:00Z" \
  -f state="open" 2>/dev/null || echo "  M4 exists"

# ─── ISSUES ─────────────────────────────────────────────────────
# Title convention: [Module] Verb + description
# Body convention: Objective, Deliverables, Starting Point, Acceptance Criteria, Owner, Due
echo ""
echo "Creating issues..."

# ──── M1: Prove the Loop ────

create_issue \
  "[Connector] Set up LLM access pathway via SafeChain" \
  "connector,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Set up SafeChain LLM access so the pipeline can call Gemini through Amex CIBIS auth.

## Deliverables
- [ ] Implement \`src/connectors/safechain_client.py\` -- bridge SafeChain to ADK BaseLlm
- [ ] Add CIBIS credentials to \`.env.example\` once validated
- [ ] Add safechain + ee_config + langchain-core==0.3.83 to dependencies
- [ ] Update \`examples/verify_setup.py\` with SafeChain + LLM checks
- [ ] Document setup in README

## Starting Point
- PoC in \`access_llm/\` demonstrates the pattern: Config.from_env -> MCPToolLoader.load_tools -> MCPToolAgent
- Two integration paths to evaluate: custom BaseLlm wrapper vs SafeChain MCPToolAgent with ADK orchestration

## Acceptance Criteria
- [ ] verify_setup.py includes SafeChain auth check + Gemini LLM call check
- [ ] A simple query through SafeChain returns a valid response
- [ ] Team can replicate setup with .env.example + README

## Owner
Saheb

## Due
End of Week 1"

create_issue \
  "[Spike] Set up Conversational Analytics API PoC" \
  "spike,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Stand up a working PoC of Google Conversational Analytics API. Run test queries and document capabilities vs limitations for Build vs Compose decision.

## Deliverables
- [ ] Working notebook: \`notebooks/conv_analytics_poc.ipynb\`
- [ ] 10 test queries -- simple to complex -- with results documented
- [ ] Capabilities table: what it handles vs what it does not
- [ ] Latency measurements per query
- [ ] Comparison notes: where Cortex adds value over raw API

## Acceptance Criteria
- [ ] 10 queries executed and results documented
- [ ] Clear table of capabilities and limitations
- [ ] Recommendation on where API fits in Compose strategy

## Owner
Saheb

## Due
March 7"

create_issue \
  "[Taxonomy] Enhance Finance BU LookML field descriptions" \
  "taxonomy,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Enrich Finance BU LookML with field descriptions, labels, and group_labels so Cortex retrieval can find the right fields from natural language.

## Deliverables
- [ ] Review all Finance BU views -- 7 views, 1 model
- [ ] Add/improve \`description\` on every dimension and measure
- [ ] Add \`group_label\` for logical grouping -- e.g. Transaction Metrics, Customer Attributes
- [ ] Add \`label\` where the dimension name is not intuitive
- [ ] Ensure \`always_filter\` is set on partitioned tables
- [ ] Document which explores exist and their join relationships

## Why This Matters
Retrieval accuracy is directly proportional to field description quality. A field with no description is invisible to vector search. Every description you add directly improves accuracy.

## Description Format
Include the business definition + common synonyms:
\`\`\`
description: \"Total dollar amount of all transactions. Also known as: total spend, transaction volume, gross amount.\"
\`\`\`

## Acceptance Criteria
- [ ] Every dimension and measure has a non-empty description
- [ ] Descriptions include business synonyms
- [ ] Group labels applied consistently
- [ ] LookML validates and deploys cleanly

## Owner
Ayush -- Animesh can help with UI if needed

## Due
March 10"

create_issue \
  "[UI] Build Finance BU Looker project viewer" \
  "ui,P1-important" \
  "M1: Prove the Loop" \
"## Objective
Build a read-only UI to browse the Finance BU Looker project structure. Helps the team see models, explores, views, and fields without needing Looker access.

## Deliverables
- [ ] Web UI showing model -> explore -> view -> field hierarchy
- [ ] Search by field name or description
- [ ] Show field descriptions, types, and join relationships
- [ ] Read-only -- no modifications

## Acceptance Criteria
- [ ] Can browse full Finance BU model structure
- [ ] Can search and find fields by name or description

## Owner
Ayush + Animesh

## Due
March 10"

create_issue \
  "[Retrieval] Load LookML into Neo4j knowledge graph" \
  "retrieval,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Parse LookML files and load model/explore/view/dimension/measure structure into Neo4j.

## Deliverables
- [ ] Script that parses \`.lkml\` files using the \`lkml\` library
- [ ] Creates Neo4j nodes: Model, Explore, View, Dimension, Measure
- [ ] Creates edges: CONTAINS, BASE_VIEW, JOINS, HAS_DIMENSION, HAS_MEASURE
- [ ] Handles \`always_filter\`, \`sql_on\`, join relationship types
- [ ] Unit tests for parser + graph loading
- [ ] Works on Finance BU LookML -- 7 views, 1 model

## Starting Point
- \`scripts/load_lookml_to_neo4j.py\` -- starter script with schema
- \`src/retrieval/graph_search.py\` -- Cypher queries this enables
- Run Neo4j locally: \`docker compose up neo4j\`

## Acceptance Criteria
- [ ] Can load all Finance BU LookML into Neo4j
- [ ] Can query: \"What explores exist in the finance model?\" -- correct answer
- [ ] Script is idempotent -- re-run safely

## Due
End of Week 2"

create_issue \
  "[Deployment] Deploy Looker MCP Server on GKE" \
  "deployment,connector,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Deploy Looker MCP Server so the pipeline can call \`query_sql\` for deterministic SQL generation.

## Deliverables
- [ ] GKE deployment manifest for Looker MCP server
- [ ] Service account with Looker API credentials
- [ ] Health check endpoint
- [ ] Verify critical MCP tools: get_models, get_explores, get_dimensions, get_measures, query_sql
- [ ] Document endpoint URL and auth for team use

## Acceptance Criteria
- [ ] MCP server running on GKE and accessible from dev environment
- [ ] \`query_sql\` returns valid BigQuery SQL for a test query
- [ ] Other team members can call the endpoint

## Due
End of Week 2"

create_issue \
  "[Retrieval] Index LookML fields into Vertex AI Search" \
  "retrieval,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Build the Vertex AI Search corpus from LookML field descriptions for semantic search.

## Deliverables
- [ ] Script to build corpus: one document per field, enriched with explore/view context
- [ ] Each document includes: field name, type, description, view, explore, model
- [ ] Search function that returns top-K fields by semantic similarity
- [ ] Unit tests

## Starting Point
- \`src/retrieval/vector.py\` -- \`build_search_corpus\` ready to implement

## Key Design Decision
Per-field chunking is intentional. Per-view returns too many irrelevant fields.

## Acceptance Criteria
- [ ] Corpus built from Finance BU LookML
- [ ] Search \"total spend\" returns \`transactions.total_amount\` in top-3

## Due
End of Week 2"

create_issue \
  "[Pipeline] Build end-to-end pipeline skeleton with ADK" \
  "pipeline,P0-critical" \
  "M1: Prove the Loop" \
"## Objective
Wire up the ADK agent with tools for each pipeline stage so ONE query works end-to-end.

## Deliverables
- [ ] ADK root agent with system instruction enforcing pipeline sequence
- [ ] Tools: classify_intent, extract_entities, retrieve_fields, validate_sql, format_response
- [ ] McpToolset connected to deployed Looker MCP server
- [ ] One working query: \"What was total spend last quarter?\" returns correct answer

## Starting Point
- \`src/pipeline/agent.py\` -- ADK agent structure and implementation guide
- \`src/pipeline/state.py\` -- state schema

## Dependencies
- Needs: LLM access, Neo4j loaded, Looker MCP deployed, Vertex Search indexed

## Acceptance Criteria
- [ ] \`python -m src.pipeline.agent --query \"What was total spend last quarter?\"\` returns correct answer
- [ ] Can trace each tool call in the output

## Due
End of Week 3"

# ──── M2: Reliable Retrieval ────

create_issue \
  "[Taxonomy] Map business terms to LookML for Finance BU" \
  "taxonomy,P0-critical" \
  "M2: Reliable Retrieval" \
"## Objective
Create taxonomy YAML entries for all business terms in Finance BU -- 7 views, 1 model.

## Deliverables
- [ ] 30-50 taxonomy YAML entries
- [ ] Each entry: canonical_name, definition, synonyms, lookml_target
- [ ] Focus on SYNONYM QUALITY -- list every name people use for each concept
- [ ] Validate: \`python -m src.taxonomy.schema validate taxonomy/finance/\`

## Why Synonyms Matter
\"CAC\" -> \`acq_cost_per_unit\` only works if the synonym is in the taxonomy.

## Acceptance Criteria
- [ ] 30+ entries, each with 3+ synonyms
- [ ] All pass schema validation

## Due
End of Week 4"

create_issue \
  "[Retrieval] Implement structural validation gate in Neo4j" \
  "retrieval,P0-critical" \
  "M2: Reliable Retrieval" \
"## Objective
Implement Neo4j Cypher queries that validate candidate fields are reachable from a single Explore. This is the number one quality gate.

## Deliverables
- [ ] \`validate_fields_in_explore\` -- find explores containing ALL given fields
- [ ] \`get_explore_schema\` -- all fields in an explore
- [ ] \`resolve_business_term\` -- business term to LookML fields
- [ ] \`get_partition_filters\` -- required filters for cost control
- [ ] Integration tests with real Neo4j

## Starting Point
- \`src/retrieval/graph_search.py\` -- Cypher queries written, class structure ready

## Acceptance Criteria
- [ ] Given [\"total_amount\", \"category_name\"], returns \"transactions\" explore
- [ ] Given fields from different explores, returns empty -- correctly rejects

## Due
End of Week 5"

create_issue \
  "[Evaluation] Build golden dataset -- 50 queries for Finance BU" \
  "evaluation,P0-critical" \
  "M2: Reliable Retrieval" \
"## Objective
Create 50 human-verified question-to-answer pairs for Finance BU.

## Three Sources
1. **Looker Query History** -- export top 100 queries, generate NL versions
2. **SME Questions** -- ask Finance analysts their top 20 questions
3. **Synthetic** -- LLM-generated, manually validated

## Deliverables
- [ ] 50+ golden queries in \`tests/golden_queries/finance/\`
- [ ] Mix: simple 20, moderate 20, complex 10
- [ ] Run: \`python scripts/run_eval.py --dataset=tests/golden_queries/finance/\`

## Starting Point
- \`tests/golden_queries/finance/_template.json\`
- \`src/evaluation/golden.py\` -- loader + evaluator

## Due
End of Week 5"

create_issue \
  "[Retrieval] Implement RRF fusion layer" \
  "retrieval,P0-critical" \
  "M2: Reliable Retrieval" \
"## Objective
Implement Reciprocal Rank Fusion to merge vector + graph + fewshot retrieval results.

## Deliverables
- [ ] \`reciprocal_rank_fusion\` -- merge ranked lists with configurable weights
- [ ] \`fuse_and_validate\` -- RRF, group by explore, validate, decide
- [ ] Decision logic: proceed / disambiguate / clarify / no_match
- [ ] Weights: graph=1.5, fewshot=1.2, vector=1.0
- [ ] Unit tests with mock retrieval results

## Starting Point
- \`src/retrieval/fusion.py\`
- \`config/retrieval.yaml\`

## Due
End of Week 5"

create_issue \
  "[Spike] Evaluate Conversational Analytics API vs Cortex" \
  "spike,P0-critical" \
  "M2: Reliable Retrieval" \
"## Objective
Run 20 queries through both Google Conversational Analytics API and Cortex. Data-driven Build vs Compose decision.

## Deliverables
- [ ] Benchmark notebook: \`notebooks/conv_analytics_comparison.ipynb\`
- [ ] Per-query comparison table -- accuracy, latency, cost
- [ ] Decision document: Compose confirmed or revised

## Dependencies
- Conv Analytics API PoC
- Golden dataset

## Due
End of Week 5"

# ──── M3: Handle the Edges ────

create_issue \
  "[Pipeline] Add boundary detection for graceful refusal" \
  "pipeline,P1-important" \
  "M3: Handle the Edges" \
"## Objective
Detect unanswerable queries and refuse gracefully with helpful alternatives.

## Out-of-Scope Queries
- Predictions: \"Predict next quarter's revenue\"
- Causal: \"Why did X happen?\"
- Data mods: \"Update/delete X\"
- PII: \"Show me customer SSNs\"

## Deliverables
- [ ] Boundary detection in intent classification
- [ ] Graceful refusal with 2-3 alternative suggestions
- [ ] 20+ boundary test cases

## Due
End of Week 7"

create_issue \
  "[Pipeline] Add complexity-aware query routing" \
  "pipeline,P1-important" \
  "M3: Handle the Edges" \
"## Objective
Route simple queries directly to Looker MCP -- skip retrieval, save 40% of tokens.

## Routing
- Simple: fast path, skip retrieval
- Moderate: standard path with retrieval
- Complex: decompose into sub-queries

## Deliverables
- [ ] Complexity classifier in intent stage
- [ ] Simple query fast path
- [ ] Complex query decomposition
- [ ] Token savings measurements

## Due
End of Week 8"

create_issue \
  "[Pipeline] Add disambiguation flow for ambiguous queries" \
  "pipeline,P1-important" \
  "M3: Handle the Edges" \
"## Objective
When query is ambiguous, present options to the user instead of guessing.

## Deliverables
- [ ] Disambiguation detection in fusion layer
- [ ] User-facing options with clear descriptions
- [ ] 10+ disambiguation test cases

## Due
End of Week 8"

create_issue \
  "[Pipeline] Implement 3-layer caching" \
  "pipeline,P1-important" \
  "M3: Handle the Edges" \
"## Objective
Add caching: exact match at 15min TTL, semantic at 1hr, metadata at 5min. Target 60%+ hit rate.

## Deliverables
- [ ] Exact match cache
- [ ] Semantic cache -- embedding similarity > 0.95
- [ ] Metadata cache -- Looker MCP responses
- [ ] TTLs configurable via \`config/retrieval.yaml\`

## Due
End of Week 9"

# ──── M4: Production Ready ────

create_issue \
  "[Pipeline] Build feedback loop from user corrections" \
  "pipeline,P1-important" \
  "M4: Production Ready" \
"## Objective
User corrections feed back to improve accuracy over time.

## Deliverables
- [ ] Feedback capture -- thumbs up/down, \"I meant X\"
- [ ] Correction to golden dataset queue
- [ ] New synonym to taxonomy update PR

## Due
End of Week 12"

create_issue \
  "[Deployment] Add observability dashboards" \
  "pipeline,deployment,P1-important" \
  "M4: Production Ready" \
"## Objective
Full visibility into pipeline health, accuracy, and cost.

## Deliverables
- [ ] Structured logging at each pipeline stage
- [ ] Dashboard: latency P50/P90/P99 by stage
- [ ] Dashboard: accuracy trend, cost per query
- [ ] Alerting: accuracy < 85%, latency P90 > 10s

## Due
End of Week 13"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Created:"
echo "  - 11 labels"
echo "  - 4 milestones (M1-M4)"
echo "  - 19 issues"
echo ""
echo "Issue naming convention: [Module] Verb + description"
echo "  Modules: Connector, Spike, Taxonomy, UI, Retrieval, Deployment, Pipeline, Evaluation"
echo ""
echo "Team assignments:"
echo "  Saheb:             [Connector] LLM access, [Spike] Conv Analytics API PoC"
echo "  Ayush:             [Taxonomy] LookML enhancement, [UI] Viewer -- due March 10"
echo "  Ayush + Animesh:   [UI] Viewer"
echo "  Rajesh + Likhita:  [Retrieval] Neo4j, [Deployment] GKE"
echo "  Animesh:           [Evaluation] Golden dataset"
