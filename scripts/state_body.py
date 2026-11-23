#!/usr/bin/env python3
"""State issue body (M1-77, owner decision 7076085601 item 2): validate the one JSON block that holds the state.

The body is free prose plus exactly one fenced ```json block with usage, sessions, branches, triggers, the owner queue
and the next steps. M1-80 adds `render` (a short summary above the block) and tasks.py --state. Standard library only.

Usage:
  scripts/state_body.py validate BODY   exit 1 with every problem on stderr; BODY is a file or - for stdin

Read the body with: gh api repos/bondo/listicles2/issues/15 --jq .body > state.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

FENCE_OPEN, FENCE_CLOSE = "```json", "```"
SCHEMA = 1

Check = Callable[[Any, str, list[str]], None]


class StateError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def kind(ok: Callable[[Any], bool], what: str) -> Check:
    def check(v: Any, path: str, errs: list[str]) -> None:
        if not ok(v):
            errs.append(f"{path}: expected {what}, got {json.dumps(v)[:60]}")
    return check


def pattern(rx: str, what: str) -> Check:
    return kind(lambda v: isinstance(v, str) and re.fullmatch(rx, v) is not None, what)


def one_of(*values: str) -> Check:
    return kind(lambda v: v in values, "one of " + ", ".join(values))


def nullable(inner: Check) -> Check:
    def check(v: Any, path: str, errs: list[str]) -> None:
        if v is not None:
            inner(v, path, errs)
    return check


def list_of(inner: Check, lo: int = 0, hi: int | None = None) -> Check:
    def check(v: Any, path: str, errs: list[str]) -> None:
        if not isinstance(v, list):
            errs.append(f"{path}: expected a list, got {json.dumps(v)[:60]}")
            return
        if len(v) < lo or (hi is not None and len(v) > hi):
            errs.append(f"{path}: expected {lo} to {hi} items, got {len(v)}")
        for i, item in enumerate(v):
            inner(item, f"{path}[{i}]", errs)
    return check


def obj(fields: dict[str, Check], optional: frozenset[str] = frozenset()) -> Check:
    def check(v: Any, path: str, errs: list[str]) -> None:
        where = f"{path}: " if path else ""
        if not isinstance(v, dict):
            errs.append(f"{where}expected an object, got {json.dumps(v)[:60]}")
            return
        errs.extend(f"{where}unknown field {k!r}" for k in v if k not in fields)
        errs.extend(f"{where}missing field {k!r}" for k in fields if k not in v and k not in optional)
        for k, c in fields.items():
            if k in v:
                c(v[k], f"{path}.{k}" if path else k, errs)
    return check


TEXT = kind(lambda v: isinstance(v, str) and v.strip() != "" and not set(v) & {"\n", "\r"}, "a non-empty string on one line")
COUNT = kind(lambda v: type(v) is int and v >= 0, "a whole number >= 0")
NUMBER = kind(lambda v: type(v) is int and v > 0, "a PR or issue number")
TIME = pattern(r"\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?Z", "a UTC time like 2026-11-23T05:33Z")
SESSION = pattern(r"session_[A-Za-z0-9]+", "a session id")
TASK = pattern(r"M\d+(\.\d+)?-(\d\d|O\d+|FU)", "a task id")
SHA = pattern(r"[0-9a-f]{7,40}", "a commit SHA")
ROLE = pattern(r"[a-z][a-z-]*", "a role (lower case, e.g. implementer)")
USAGE = pattern(r"ok|near limit \((5-hour(, forecast|, rateLimitType unknown)?|7-day|overage)\)|paused until \d\d:\d\d UTC",
                "one of the ORCHESTRATION.md 3.1 usage states")
STATUSES = ("running", "idle-with-result", "idle-no-result", "failed", "archived", "interrupted (usage)")

SESSION_ROW = obj({"id": SESSION, "role": ROLE, "branch": nullable(TEXT), "pr": nullable(NUMBER), "tasks": list_of(TASK),
                   "spawned": TIME, "expects": TEXT, "checked": TIME, "status": one_of(*STATUSES), "note": TEXT},
                  optional=frozenset({"note"}))
BRANCH_ROW = obj({"name": TEXT, "holder": nullable(SESSION), "pr": nullable(NUMBER), "in_review": list_of(TASK),
                  "reviewed_through": nullable(SHA), "unreviewed_since": nullable(SHA), "disposition": TEXT})
STATE = obj({
    "schema": kind(lambda v: type(v) is int and v == SCHEMA, str(SCHEMA)),
    "orchestrator": obj({"session": SESSION, "since": TIME, "predecessor": nullable(SESSION), "depth": COUNT}),
    "updated": obj({"at": TIME, "after": TEXT}),
    "inbox_since": TIME,
    "tasks_ref": TEXT,
    "usage": obj({"state": USAGE, "read_at": TIME}),
    "sessions": list_of(SESSION_ROW),
    "branches": list_of(BRANCH_ROW),
    "triggers": list_of(obj({"id": pattern(r"trig_[A-Za-z0-9]+", "a trigger id"), "fires_into": SESSION, "purpose": TEXT,
                             "next_run": nullable(TIME)})),
    "subscriptions": list_of(NUMBER),
    "owner_queue": list_of(obj({"kind": one_of("todo", "question", "approval"), "task": nullable(TASK),
                                "issue": nullable(NUMBER), "text": TEXT, "then": TEXT})),
    "follow_ups": obj({k: COUNT for k in ("open", "blocker", "major", "minor", "nit")}),
    "next": list_of(TEXT, 1, 3),
    "decisions": list_of(obj({"comment": NUMBER, "what": TEXT})),
})


def cross_checks(data: dict) -> list[str]:
    """Rules across rows; only called once the shape is valid."""
    errs = []
    for key, label, name in (("sessions", "session", "id"), ("branches", "branch", "name")):
        seen = [row[name] for row in data[key]]
        errs += [f"duplicate {label} {x}" for x in sorted({x for x in seen if seen.count(x) > 1})]
    claims = [t for row in data["sessions"] for t in row["tasks"]]
    errs += [f"{t} is claimed by {claims.count(t)} sessions" for t in sorted({t for t in claims if claims.count(t) > 1})]
    for i, row in enumerate(data["sessions"]):
        if row["status"] in ("archived", "failed") and row["tasks"]:
            errs.append(f"sessions[{i}]: {row['status']} but still claims {', '.join(row['tasks'])} (release the claim)")
    fu = data["follow_ups"]
    total = sum(fu[k] for k in ("blocker", "major", "minor", "nit"))
    if fu["open"] != total:
        errs.append(f"follow_ups.open: {fu['open']} is not the sum of the severities ({total})")
    return errs


def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    keys = [k for k, _ in pairs]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        raise ValueError(f"duplicate key {dup[0]!r}")
    return dict(pairs)


def find_block(lines: list[str]) -> tuple[int, int]:
    """Line indexes of the opening and closing fence of the one ```json block."""
    opens = [i for i, ln in enumerate(lines) if ln.rstrip() == FENCE_OPEN]
    if not opens:
        raise StateError([f"no {FENCE_OPEN} block in the body"])
    if len(opens) > 1:
        raise StateError([f"{len(opens)} {FENCE_OPEN} blocks in the body; exactly one holds the state"])
    close = next((i for i in range(opens[0] + 1, len(lines)) if lines[i].rstrip() == FENCE_CLOSE), None)
    if close is None:
        raise StateError([f"the {FENCE_OPEN} block is not closed with {FENCE_CLOSE}"])
    return opens[0], close


def load(text: str) -> dict:
    """The validated state; raises StateError with every problem found."""
    if not text.strip():
        raise StateError(["the body is empty (a failed gh call?); refusing to read it as no state"])
    lines = text.splitlines()
    start, end = find_block(lines)
    try:
        data = json.loads("\n".join(lines[start + 1:end]), object_pairs_hook=no_duplicate_keys)
    except ValueError as e:
        raise StateError([f"malformed JSON in the state block: {e}"]) from None
    if not isinstance(data, dict):
        raise StateError(["the state block must be a JSON object"])
    errs: list[str] = []
    STATE(data, "", errs)
    if errs:
        raise StateError(errs)
    errs = cross_checks(data)
    if errs:
        raise StateError(errs)
    return data


def read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise StateError([f"cannot read {path}: {e.strerror}"]) from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("validate",))
    ap.add_argument("body", help="the state issue body (a file, or - for stdin)")
    a = ap.parse_args(argv)
    try:
        d = load(read(a.body))
    except StateError as e:
        for msg in e.errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    claimed = sum(len(s["tasks"]) for s in d["sessions"])
    in_review = sum(len(b["in_review"]) for b in d["branches"])
    print(f"ok: {len(d['sessions'])} sessions, {len(d['branches'])} branches, {claimed} claimed, {in_review} in review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
