# ADR-002: One Looker Project Per Business Unit

**Date:** February 25, 2026  
**Status:** Accepted  
**Decider:** Saheb  
**Consulted:** Sulabh, Renuka

---

## Decision

Each Business Unit gets its own Looker project with a dedicated git repository, model file, views, and explores.

## Context

As we scale from 1 BU (Finance) to 3 and eventually more, we need a Looker organization strategy. Options:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. Single project | All BUs in one Looker project | Simple, one repo | Merge conflicts, blast radius, ownership unclear |
| B. Project per BU | Each BU gets own project + git repo | Isolation, clear ownership, independent deploys | More repos to manage, shared patterns may diverge |
| C. Shared + BU projects | Shared base project + BU-specific projects | Reuse common patterns | Complex includes, dependency management |

## Rationale

**Option B — Project per BU** because:

1. **Blast radius isolation:** When BU2 adds a metric, Finance views are untouched. No risk of breaking a working BU.
2. **Independent git workflows:** Each BU can have its own PR cycle, reviewers, and deploy cadence. Renuka's enrichment pipeline targets one project without touching others.
3. **Clear ownership:** Each project has an owner. "Who owns the Finance Looker model?" has a one-word answer.
4. **Scalability:** Going from 3 to 10 BUs means creating new projects from a template. The pattern repeats without restructuring.
5. **MCP Toolbox compatibility:** `get_models` returns all models. With separate projects, each BU has a distinct model name that the Entity Resolver can match against.

## Naming Convention

```
Project name:  cortex_{bu_name}
Model name:    {bu_name}_model  
Connection:    {bu_name}_bigquery (or shared connection if same BQ project)
Explore names: {bu_name}_{domain}_explore
View names:    {table_name}.view.lkml
```

## Consequences

- Need a project creation template/script for new BUs
- Shared patterns (common dimensions like date, common measures) need to be manually kept in sync or use Looker's `local_dependency` feature
- More git repos to manage (mitigated by standardized structure)
