# Slack Message — Likhita + Rajesh

**Channel:** DM or team channel
**Copy-paste ready:**

---

Hey Likhita, Rajesh — quick strategy update and next steps.

I built the full orchestration pipeline on top of your retrieval branch — SSE streaming, Looker MCP integration, multi-turn conversations, filter resolution, confidence scoring. Your entity extraction + vector search foundation held up well. Everything is running end-to-end on my local now.

**What's happening in parallel:**
- Ayush has the UI built — him and I are integrating it with the backend API this week
- I'll push my orchestrator branch (cleanup + final fixes) by tomorrow
- Your retrieval branch needs a few changes before merging to main (details below)

**For you two — two tracks:**

**Track 1: Merge your branch to main**
I stress-tested retrieval against a 12-query golden set and wrote a file-by-file review: `docs/pr-reviews/pr-likhita-rajesh-retrieval-cleanup.md` (on `saheb/orchestrator-v1`). Key fixes:
- Coverage scoring bug (always returns 1.0 — quick one-liner)
- Batch embedding (5 API calls → 1, saves ~800ms/query)
- Pre-extracted entity support so orchestrator doesn't double-call the LLM
- Confidence + action routing in `get_top_explore()`

Once you merge, I rebase orchestrator on top — your work stays as the foundation in git history.

**Track 2: Get us on Hydra**
Start working on deploying what we have to Hydra. We need the retrieval pipeline + API running there, not just local. Flag any infra blockers early — Docker config, SafeChain creds, pgvector access, networking.

**Also — I need your eyes on gaps:**
As you go through the pipeline and the Looker integration, keep a running list of what's missing or broken. Things like: fields we can't resolve, explores that don't score well, filter edge cases, LookML gaps. We're at 83% accuracy — I want to know what the remaining 17% looks like and what we need from the Looker side to close it.

Likhita — want to find 30 min this week to walk through the scoring formula change? Went from additive to multiplicative, 33% → 83% accuracy. Want your take on how it fits with intent classification long-term.

PR review has code snippets — should be straightforward. Flag me if anything's unclear.
