#!/usr/bin/env python3
"""Prompt hook emulator for Gemini CLI and Copilot CLI.

Claude Code supports native prompt hooks (type: "prompt"), but Gemini and
Copilot only support shell commands.  This script bridges the gap by doing
deterministic keyword checking on the agent output.

Usage:
    VERDICT_KEYWORDS="QA_PASS,QA_FAIL" python prompt-hook-wrapper.py

Input: Receives agent output on stdin (JSON or plain text).
Exit codes: 0 = keyword found, 2 = keyword missing.
"""

import json
import os
import sys


def main() -> int:
    keywords_raw = os.environ.get("VERDICT_KEYWORDS", "")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    if not keywords:
        return 0  # No keywords configured, pass through

    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    # Try to extract text from JSON structure
    text = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            text = json.dumps(data)
    except (json.JSONDecodeError, TypeError):
        pass

    for kw in keywords:
        if kw in text:
            return 0

    print(
        f"Required keyword not found. Expected one of: {', '.join(keywords)}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
