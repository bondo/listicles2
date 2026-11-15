#!/usr/bin/env python3
"""PostToolUse hook: once context use reaches the threshold, remind the agent ONCE per session to finish the step,
write handoff/<branch>.md from handoff/TEMPLATE.md, commit and end (PLAN 9.3).

Usage source (works headless/in the cloud, where the statusline never runs): the last main-thread assistant record in
transcript_path, context = input + cache_creation + cache_read + output tokens of that call. If scripts/statusline.sh did
record a value for the session (interactive CLI), the larger of the two is used.
Window: LISTICLES_CONTEXT_WINDOW (tokens), else 1,000,000 (the models used here have a 1M window; a 200k default fired
the reminder at ~100k tokens). Set LISTICLES_CONTEXT_WINDOW at spawn for a smaller window. Garbage values fall back.
Calls made inside subagents (hook input has agent_id) are ignored.
Env: LISTICLES_CONTEXT_THRESHOLD (percent, default 50). Output: hookSpecificOutput.additionalContext. Never fails."""

import contextlib
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
    return int(s) if re.fullmatch(r"[0-9]+", s) and int(s) > 0 else None  # ASCII digits only: int("\u00b2") raises


def window_of():
    """LISTICLES_CONTEXT_WINDOW, else 1,000,000. (PostToolUse input has no window field; only the statusline JSON does.)"""
    return positive_int(os.environ.get("LISTICLES_CONTEXT_WINDOW")) or DEFAULT_WINDOW


def main():
    data = json.load(sys.stdin)
    if data.get("agent_id"):  # PostToolUse also fires inside subagents: neither warn them nor use up the main reminder
        return
    sid = str(data.get("session_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "listicles-ctx")
    pcts = []
    with contextlib.suppress(OSError, ValueError), open(os.path.join(base, sid)) as f:
        pcts.append(int(f.read().strip()))
    tp = data.get("transcript_path")
    found = last_usage(tp) if isinstance(tp, str) and tp else None
    if found:
        pcts.append(found * 100 // window_of())
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
