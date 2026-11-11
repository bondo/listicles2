#!/usr/bin/env python3
"""PostToolUse hook: once context use reaches the threshold, remind the agent ONCE per session to finish the step,
write handoff/<branch>.md from handoff/TEMPLATE.md, commit and end (PLAN 9.3).

Usage source (works headless/in the cloud, where the statusline never runs): the last main-thread assistant record in
transcript_path, context = input + cache_creation + cache_read + output tokens of that call. If scripts/statusline.sh did
record a value for the session (interactive CLI), the larger of the two is used.
Window: LISTICLES_CONTEXT_WINDOW (tokens), else the hook input's context_window.context_window_size, else 1,000,000
(the models used here have a 1M window; a 200k default fired the reminder at ~100k tokens). Garbage values fall back.
Env: LISTICLES_CONTEXT_THRESHOLD (percent, default 50). Output: hookSpecificOutput.additionalContext. Never fails."""

import json
import os
import re
import sys

TAIL_BYTES = 512 * 1024
DEFAULT_WINDOW = 1_000_000
DEFAULT_THRESHOLD = 50
FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def last_usage(path):
    """Context tokens of the last main-thread assistant record, reading only the end of the file."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - TAIL_BYTES))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = data.split("\n")
    if size > TAIL_BYTES:
        lines = lines[1:]  # the first line is probably cut in half
    for line in reversed(lines):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message") if isinstance(o, dict) else None
        if o.get("type") != "assistant" or o.get("isSidechain") or not isinstance(m, dict) or not isinstance(m.get("usage"), dict):
            continue
        u = m["usage"]
        total = sum(u[k] for k in FIELDS if isinstance(u.get(k), int))
        if total > 0:
            return total
    return None


def positive_int(value):
    """int(value) when it is a plain positive integer, else None (garbage falls back to the default)."""
    s = str(value).strip() if value is not None else ""
    return int(s) if s.isdigit() and int(s) > 0 else None


def window_of(data):
    """LISTICLES_CONTEXT_WINDOW, else the hook input's context_window.context_window_size, else 1,000,000."""
    cw = data.get("context_window")
    from_input = positive_int(cw.get("context_window_size")) if isinstance(cw, dict) else None
    return positive_int(os.environ.get("LISTICLES_CONTEXT_WINDOW")) or from_input or DEFAULT_WINDOW


def main():
    data = json.load(sys.stdin)
    sid = str(data.get("session_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "listicles-ctx")
    pcts = []
    try:
        pcts.append(int(open(os.path.join(base, sid)).read().strip()))
    except (OSError, ValueError):
        pass
    tp = data.get("transcript_path")
    found = last_usage(tp) if isinstance(tp, str) and tp else None
    if found:
        pcts.append(found * 100 // window_of(data))
    if not pcts:
        return
    pct = max(pcts)
    limit = positive_int(os.environ.get("LISTICLES_CONTEXT_THRESHOLD")) or DEFAULT_THRESHOLD
    flag = os.path.join(base, sid + ".warned")
    if pct < limit or os.path.exists(flag):
        return
    os.makedirs(base, exist_ok=True)
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
