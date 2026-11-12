"""Turns the orchestrator's metrics CSV blocks (ORCHESTRATION section 6) into docs/agent-metrics.csv.

Input: text files holding state-issue comment bodies, saved as they were posted. The orchestrator pastes the
numbers from get_session (external_metadata.usage etc.) into the CSV blocks; this script never calls a
network or reads transcripts. A block starts with a marker line, then a header line, then one CSV row per line:

    # metrics:session | metrics:round | metrics:incident
    <header>
    <row>...

A block ends at a blank line, a code fence or another marker line; prose around blocks is ignored. Rows are
single-line CSV (quote fields containing commas). Empty fields mean "unknown"; numbers are never estimated.
Output: one CSV, first column row_type (session, round, incident), other columns empty where they do not apply,
rows sorted deterministically. Input is validated; every problem is reported as `file:line: message`, exit 1,
and nothing is written.

Usage: python3 -I scripts/agent_metrics.py [--check] [-o docs/agent-metrics.csv] [input ...]
  input defaults to docs/metrics/*.txt. --check exits 1 when the output file differs from what the inputs give.
"""

import argparse
import csv
import datetime
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = re.compile(r"^\s*#\s*metrics:(\S*)\s*$")
INT = re.compile(r"^\d+$")
MONEY = re.compile(r"^\d+(\.\d+)?$")

# kind -> (required columns, optional columns). Optional ones came later; older comments may omit them.
SESSION_REQ = ["date", "batch", "pr", "tasks", "role", "session_id", "model", "effort", "result", "cost_usd",
               "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "handoffs",
               "verify_fails_before_push", "ci_red_runs"]
SESSION_OPT = ["env", "post_cap_commits", "owner_interventions"]
ROUND_REQ = ["date", "batch", "pr", "round", "reviewer_session", "base_sha", "head_sha", "blocker", "major",
             "minor", "nit", "disputed", "withdrawn", "deferred", "verdict"]
INCIDENT_REQ = ["date", "batch", "session_id", "kind", "impact", "recovery", "prevention"]
SCHEMA = {
    "session": (SESSION_REQ, SESSION_OPT),
    "round": (ROUND_REQ, []),
    "incident": (INCIDENT_REQ, []),
}
RENAME = {"incident": {"kind": "incident_kind"}}  # `kind` would clash with the marker word in the output
INT_FIELDS = {"pr", "round", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
              "handoffs", "verify_fails_before_push", "ci_red_runs", "post_cap_commits", "owner_interventions",
              "blocker", "major", "minor", "nit", "disputed", "withdrawn", "deferred"}

COLUMNS = (["row_type", "date", "batch", "pr", "tasks", "role", "session_id", "model", "effort", "env", "result",
            "cost_usd", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "handoffs",
            "verify_fails_before_push", "ci_red_runs", "post_cap_commits", "owner_interventions", "round",
            "reviewer_session", "base_sha", "head_sha", "blocker", "major", "minor", "nit", "disputed",
            "withdrawn", "deferred", "verdict", "incident_kind", "impact", "recovery", "prevention"])
TYPE_ORDER = {"session": 0, "round": 1, "incident": 2}


def _check_values(kind, row):
    problems = []
    date = row.get("date", "")
    if date:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                raise ValueError
            datetime.date.fromisoformat(date)
        except ValueError:
            problems.append(f"date {date!r} is not YYYY-MM-DD")
    for field, value in row.items():
        if field in INT_FIELDS and value and not INT.match(value):
            problems.append(f"{field} {value!r} is not a whole number")
    cost = row.get("cost_usd", "")
    if cost and not MONEY.match(cost):
        problems.append(f"cost_usd {cost!r} is not a plain decimal number (no ~, $, sign or exponent)")
    if kind == "round":
        for field in ("pr", "round"):
            if not row.get(field):
                problems.append(f"{field} is required for a round row")
    return problems


def _parse_block(kind, lines, start, name, errors):
    """lines[start] is the header line. Returns (rows as (lineno, dict), index after the block)."""
    required, optional = SCHEMA[kind]
    i = start
    if i >= len(lines) or not lines[i].strip() or lines[i].lstrip().startswith(("```", "#")):
        errors.append(f"{name}:{start}: metrics:{kind} block has no header line")
        return [], i
    header = next(csv.reader([lines[i]]))
    i += 1
    ok = True
    for col in dict.fromkeys(c for c in header if header.count(c) > 1):
        errors.append(f"{name}:{start + 1}: duplicate column {col!r}")
        ok = False
    for col in header:
        if col not in required and col not in optional:
            errors.append(f"{name}:{start + 1}: unknown column {col!r} for metrics:{kind}")
            ok = False
    for col in required:
        if col not in header:
            errors.append(f"{name}:{start + 1}: missing column {col!r} for metrics:{kind}")
            ok = False
    rows = []
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith(("```", "#")):
            break
        lineno = i + 1
        i += 1
        if not ok:
            continue
        fields = next(csv.reader([line]))
        if len(fields) != len(header):
            errors.append(f"{name}:{lineno}: row has {len(fields)} fields, header has {len(header)}")
            continue
        row = dict(zip(header, fields))
        for col in optional:
            row.setdefault(col, "")
        problems = _check_values(kind, row)
        for p in problems:
            errors.append(f"{name}:{lineno}: {p}")
        if not problems:
            rows.append((lineno, row))
    return rows, i


def build(texts, names=None):
    """Parse comment bodies. Returns (sorted rows as dicts keyed by COLUMNS, error strings)."""
    names = names or [f"input{n + 1}" for n in range(len(texts))]
    errors, out = [], []
    sessions, rounds = {}, {}
    for text, name in zip(texts, names):
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            m = MARKER.match(lines[i])
            if not m:
                i += 1
                continue
            kind = m.group(1)
            if kind not in SCHEMA:
                errors.append(f"{name}:{i + 1}: unknown metrics kind {kind!r}")
                i += 1
                continue
            rows, i = _parse_block(kind, lines, i + 1, name, errors)
            for lineno, row in rows:
                if kind == "session" and row["session_id"]:
                    prev = sessions.setdefault(row["session_id"], f"{name}:{lineno}")
                    if prev != f"{name}:{lineno}":
                        errors.append(f"{name}:{lineno}: duplicate session_id {row['session_id']!r} "
                                      f"(first at {prev})")
                        continue
                if kind == "round":
                    key = (row["pr"], row["round"])
                    prev = rounds.setdefault(key, f"{name}:{lineno}")
                    if prev != f"{name}:{lineno}":
                        errors.append(f"{name}:{lineno}: duplicate round {row['round']} for pr {row['pr']} "
                                      f"(first at {prev})")
                        continue
                renamed = {RENAME.get(kind, {}).get(k, k): v for k, v in row.items()}
                out.append({**{c: "" for c in COLUMNS}, "row_type": kind, **renamed})
    out.sort(key=lambda r: (TYPE_ORDER[r["row_type"]], r["date"] == "", r["date"],
                            int(r["pr"] or 0), int(r["round"] or 0), tuple(r[c] for c in COLUMNS)))
    return out, errors


def render(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="*", help="saved comment files (default docs/metrics/*.txt)")
    ap.add_argument("-o", "--output", default=str(ROOT / "docs/agent-metrics.csv"))
    ap.add_argument("--check", action="store_true", help="fail if the output file is not up to date")
    args = ap.parse_args(argv)
    paths = args.inputs or sorted(str(p) for p in (ROOT / "docs/metrics").glob("*.txt"))
    texts, errors = [], []
    for p in paths:
        try:
            texts.append(Path(p).read_text(encoding="utf-8"))
        except OSError as e:
            errors.append(f"{p}: cannot read input ({e.strerror})")
    if not paths:
        errors.append("no input files")
    rows, parse_errors = build(texts, [p for p in paths if Path(p).is_file()])
    errors += parse_errors
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    text = render(rows)
    out = Path(args.output)
    if args.check:
        if not out.is_file() or out.read_text(encoding="utf-8") != text:
            print(f"{args.output} is out of date: rerun scripts/agent_metrics.py", file=sys.stderr)
            return 1
        return 0
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
