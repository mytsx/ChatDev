#!/bin/bash
# Stop/AfterAgent hook: Checks agent output for required verdict keywords.
# Usage: VERDICT_KEYWORDS="REVIEW_PASS,REVIEW_FAIL" ./verdict-check.sh
# Input: Receives agent output on stdin (JSON for Claude/Gemini, text for Copilot).
# Exit codes: 0 = keyword found, 2 = keyword missing (agent continues).
set -euo pipefail

INPUT=$(cat)
KEYWORDS="${VERDICT_KEYWORDS:-REVIEW_PASS,REVIEW_FAIL}"

IFS=',' read -ra KW_ARRAY <<< "$KEYWORDS"
for kw in "${KW_ARRAY[@]}"; do
  kw=$(echo "$kw" | xargs)  # trim whitespace
  if echo "$INPUT" | grep -q "$kw"; then
    exit 0
  fi
done

echo "Missing required verdict keyword. Must include one of: $KEYWORDS" >&2
exit 2
