#!/bin/bash
# PostToolUse hook: After a successful git push, comments "/gemini review"
# on the open PR for the current branch (if one exists).
# Requires: gh CLI authenticated.
# Exit codes: 0 = always (non-blocking, informational only).
set -uo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# Only act on Bash tool
if [ "$TOOL" != "Bash" ]; then
  exit 0
fi

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

# Only act on git push commands
if ! echo "$CMD" | grep -qE 'git\s+push'; then
  exit 0
fi

# Check if push was successful (exit code 0 in tool output)
TOOL_EXIT=$(echo "$INPUT" | jq -r '.tool_output.exit_code // .tool_output.exitCode // "0"' 2>/dev/null || echo "0")
if [ "$TOOL_EXIT" != "0" ]; then
  exit 0
fi

# Detect repo from git remote
REPO=$(git remote get-url origin 2>/dev/null | sed -E 's|.*github\.com[:/]||; s|\.git$||')
if [ -z "$REPO" ]; then
  exit 0
fi

# Get current branch
BRANCH=$(git branch --show-current 2>/dev/null)
if [ -z "$BRANCH" ] || [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  exit 0
fi

# Find open PR for this branch
PR_NUMBER=$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --json number --jq '.[0].number' 2>/dev/null)
if [ -z "$PR_NUMBER" ] || [ "$PR_NUMBER" = "null" ]; then
  exit 0
fi

# Comment /gemini review
gh pr comment "$PR_NUMBER" --repo "$REPO" --body "/gemini review" 2>/dev/null && \
  echo "✅ /gemini review → PR #$PR_NUMBER ($REPO)" >&2 || true

exit 0
