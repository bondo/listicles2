#!/usr/bin/env python3
"""PostToolUse hook: once context use (written by scripts/statusline.sh) reaches the threshold, remind the agent
ONCE per session to finish the step, write handoff/<branch>.md from handoff/TEMPLATE.md, commit and end (PLAN 9.3).
Threshold: LISTICLES_CONTEXT_THRESHOLD (default 50). Output: hookSpecificOutput.additionalContext. Never fails."""

import json
import os
import re
import sys


def main():
    data = json.load(sys.stdin)
    sid = str(data.get("session_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "listicles-ctx")
    try:
        pct = int(open(os.path.join(base, sid)).read().strip())
    except (OSError, ValueError):
        return
    limit = int(os.environ.get("LISTICLES_CONTEXT_THRESHOLD", "50"))
    flag = os.path.join(base, sid + ".warned")
    if pct < limit or os.path.exists(flag):
        return
    open(flag, "w").close()
    msg = (f"CONTEXT {pct}% (limit {limit}%). Finish the current step only, then: write handoff/<branch>.md from "
           "handoff/TEMPLATE.md, commit it, and end the session. Do not start new work.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"context_guard: {e}", file=sys.stderr)
    sys.exit(0)
