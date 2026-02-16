#!/bin/bash
# PreToolUse hook: Blocks file modifications for read-only roles.
# Allows: Read, Glob, Grep, LS, and read-only Bash commands.
# Blocks: Edit, Write, NotebookEdit, and destructive Bash commands.
# Exit codes: 0 = allowed, 2 = blocked.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# If jq fails or no tool name, allow (non-standard input)
if [ -z "$TOOL" ]; then
  exit 0
fi

# Block Edit/Write tools
case "$TOOL" in
  Edit|Write|NotebookEdit)
    echo "File modifications not allowed for this role" >&2
    exit 2
    ;;
esac

# Bash tool — only allow read-only commands
if [ "$TOOL" = "Bash" ]; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
  if echo "$CMD" | grep -qE '^(cat |ls |find |grep |rg |head |tail |wc |diff |git log|git diff|git show|git status|git blame|tree |file |python -c )'; then
    exit 0
  fi
  echo "Only read-only bash commands allowed for this role" >&2
  exit 2
fi

# All other tools (Read, Glob, Grep, etc.) — allow
exit 0
