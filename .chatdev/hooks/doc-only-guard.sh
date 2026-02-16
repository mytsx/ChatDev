#!/bin/bash
# PreToolUse hook: Allows modifications only to documentation files.
# Passes: .md, .txt, .rst, .html, .css, .yml, .yaml, .json, docs/, README, CHANGELOG, LICENSE
# Blocks: all other file modifications.
# Exit codes: 0 = allowed, 2 = blocked.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

if [ -z "$TOOL" ]; then
  exit 0
fi

# Only check Edit/Write tools
case "$TOOL" in
  Edit|Write|NotebookEdit)
    FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
    if [ -z "$FILE" ]; then
      exit 0
    fi
    if echo "$FILE" | grep -qiE '\.(md|txt|rst|html|css|yml|yaml|json)$|README|CHANGELOG|LICENSE|docs/'; then
      exit 0
    fi
    echo "Technical Writer: Only documentation files can be modified" >&2
    exit 2
    ;;
esac

exit 0
