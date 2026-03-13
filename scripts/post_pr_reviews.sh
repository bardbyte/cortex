#!/usr/bin/env bash
# Post PR review comments for each file via GitHub CLI (gh).
#
# Usage:
#   ./scripts/post_pr_reviews.sh <PR_NUMBER>
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth login)
#   - PR must exist on the repository
#
# This script reads each review from docs/pr-reviews/ and posts it
# as a comment on the specified PR. Each review is posted as a
# separate comment so the team can address them independently.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <PR_NUMBER>"
    echo "Example: $0 14"
    exit 1
fi

PR_NUMBER="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REVIEWS_DIR="$SCRIPT_DIR/../docs/pr-reviews"

# Verify gh is installed and authenticated
if ! command -v gh &>/dev/null; then
    echo "Error: GitHub CLI (gh) is not installed."
    echo "Install: https://cli.github.com/"
    exit 1
fi

if ! gh auth status &>/dev/null 2>&1; then
    echo "Error: Not authenticated with GitHub CLI."
    echo "Run: gh auth login"
    exit 1
fi

# Verify the PR exists
if ! gh pr view "$PR_NUMBER" &>/dev/null 2>&1; then
    echo "Error: PR #$PR_NUMBER not found."
    exit 1
fi

echo "Posting PR reviews to PR #$PR_NUMBER..."
echo "========================================="

# Map review files to the source files they review
declare -A REVIEW_FILES=(
    ["postgres_age_client.md"]="src/connectors/postgres_age_client.py"
    ["graph_search.md"]="src/retrieval/graph_search.py"
    ["vector.md"]="src/retrieval/vector.py"
    ["pipeline.md"]="src/retrieval/pipeline.py"
    ["load_lookml_to_pgvector.md"]="scripts/load_lookml_to_pgvector.py"
    ["setup_optimized_age_schema.md"]="scripts/setup_optimized_age_schema.py"
    ["constants_and_docker.md"]="config/constants.py, config/config.yml, docker-compose.yaml, docker_spin.py, Dockerfile, .env.example"
)

SUCCESS=0
FAIL=0

for review_file in "$REVIEWS_DIR"/*.md; do
    filename="$(basename "$review_file")"
    source_files="${REVIEW_FILES[$filename]:-unknown}"

    echo ""
    echo "Posting: $filename (covers: $source_files)"

    # Read the review content
    review_content="$(cat "$review_file")"

    # Post as a PR comment
    if gh pr comment "$PR_NUMBER" --body "$review_content" 2>/dev/null; then
        echo "  Posted successfully."
        SUCCESS=$((SUCCESS + 1))
    else
        echo "  FAILED to post."
        FAIL=$((FAIL + 1))
    fi

    # Small delay to avoid rate limiting
    sleep 1
done

echo ""
echo "========================================="
echo "Done. Posted: $SUCCESS  Failed: $FAIL"
echo ""
echo "View PR: $(gh pr view "$PR_NUMBER" --json url -q .url)"
