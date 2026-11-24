#!/usr/bin/env python3
"""PostToolUse hook: once context use reaches the threshold, remind the agent ONCE per session to finish the step,
write handoff/<branch>.md from handoff/TEMPLATE.md, commit and end (PLAN 9.3). Since the Agent Usage Redesign (rev 46) there are
two thresholds, each reminded ONCE per session: a step-boundary stage (60% of a 1M window, 40% of a 200k one: hand off at the next
step boundary) and a hard stage (80% / 60%: finish the current step only, then hand off). The numbers are mirrored in
agents/roles.yaml (a test ties the two).

Usage source (works headless/in the cloud, where the statusline never runs): the last main-thread assistant record in
transcript_path, context = input + cache_creation + cache_read + output tokens of that call. If scripts/statusline.sh did
record a value for the session (interactive CLI), the larger of the two is used.
Window: the one the status line recorded for the session, else TALLY_CONTEXT_WINDOW (tokens), else 1,000,000 (the models used
here have a 1M window). A window of up to 200,000 tokens uses the small-window stages. Set TALLY_CONTEXT_WINDOW at spawn for a
smaller window. Garbage values fall back.
Calls made inside subagents (hook input has agent_id) are ignored.
Env: TALLY_CONTEXT_THRESHOLD (percent) replaces the hard stage and switches the step-boundary stage off; garbage falls back to
the window defaults. Output: hookSpecificOutput.additionalContext. Never fails."""

import contextlib
import json
import os
import re
import sys

TAIL_BYTES = 512 * 1024
DEFAULT_WINDOW = 1_000_000
SMALL_WINDOW_MAX = 200_000
THRESHOLDS_LARGE = (60, 80)  # (step boundary, hard) in percent of a window above SMALL_WINDOW_MAX
THRESHOLDS_SMALL = (40, 60)  # the same for a window of up to SMALL_WINDOW_MAX
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


def window_of(base="", sid=""):
    """The window the status line recorded for this session (<base>/<sid>.window), else TALLY_CONTEXT_WINDOW, else 1,000,000.
    (PostToolUse input has no window field; only the statusline JSON does, so the statusline records it. Garbage is ignored.)"""
    recorded = None
    with contextlib.suppress(OSError, ValueError), open(os.path.join(base, sid + ".window")) as f:
        recorded = positive_int(f.read())
    return recorded or positive_int(os.environ.get("TALLY_CONTEXT_WINDOW")) or DEFAULT_WINDOW


def stages(window):
    """(step-boundary %, hard %) for this window; TALLY_CONTEXT_THRESHOLD replaces the hard stage and drops the soft one."""
    soft, hard = THRESHOLDS_SMALL if window <= SMALL_WINDOW_MAX else THRESHOLDS_LARGE
    override = positive_int(os.environ.get("TALLY_CONTEXT_THRESHOLD"))
    return (None, override) if override else (soft, hard)


def main():
    data = json.load(sys.stdin)
    if data.get("agent_id"):  # PostToolUse also fires inside subagents: neither warn them nor use up the main reminder
        return
    sid = str(data.get("session_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "tally-ctx")
    pcts = []
    with contextlib.suppress(OSError, ValueError), open(os.path.join(base, sid)) as f:
        pcts.append(int(f.read().strip()))
    tp = data.get("transcript_path")
    found = last_usage(tp) if isinstance(tp, str) and tp else None
    if found:
        pcts.append(found * 100 // window_of(base, sid))
    if not pcts:
        return
    pct = max(pcts)
    soft, hard = stages(window_of(base, sid))
    flag = os.path.join(base, sid + ".warned")
    soft_flag = os.path.join(base, sid + ".soft")
    if pct >= hard:
        if os.path.exists(flag):
            return
        msg = (f"CONTEXT {pct}% (limit {hard}%). Finish the current step only, then: write handoff/<branch>.md from "
               "handoff/TEMPLATE.md, commit it, and end the session. Do not start new work.")
        marks = (flag, soft_flag)
    elif soft is not None and pct >= soft:
        if os.path.exists(soft_flag):
            return
        msg = (f"CONTEXT {pct}% (step-boundary limit {soft}%, hard limit {hard}%). At the next step boundary: write handoff/<branch>.md "
               "from handoff/TEMPLATE.md, commit it, and end the session. Do not start a new step after that.")
        marks = (soft_flag,)
    else:
        return
    os.makedirs(base, exist_ok=True)
    for mark in marks:
        open(mark, "w").close()
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"context_guard: {e}", file=sys.stderr)
    sys.exit(0)
