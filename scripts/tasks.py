#!/usr/bin/env python3
"""Task graph for Listicles: validate docs/tasks.toml and list ready tasks deterministically.

Process: docs/ORCHESTRATION.md section 4. Standard library only (Python 3.11+ for tomllib).

Usage:
  scripts/tasks.py [--file PATH | --ref GITREF] [--issues JSON] [--prs JSON] [--claimed IDS]
                   [--assignee owner|agent|ROLE] [--json] {validate,ready,status,drift}

  validate  schema, ids, dependencies and cycles; exit 1 on any error
  ready     todo tasks whose dependencies are all satisfied and that nobody has claimed
  status    every task with its derived state and unmet dependencies
  drift     places where the file disagrees with GitHub (closed issue / merged PR vs. status)

--issues: JSON array of {"number", "title", "state"} (GitHub issue list or search items).
--prs:    JSON array of {"number", "state", "merged"} or {"number", "merged_at"}.
--claimed: comma-separated task ids held by running sessions (the state issue's Sessions table).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FILE = "docs/tasks.toml"
STATUSES = ("todo", "done", "dropped")
RISKS = ("normal", "high")
ASSIGNEES = ("owner", "implementer", "planner", "process", "retro")
REQUIRED = ("id", "title", "milestone", "status", "assignee", "risk", "depends_on")
OPTIONAL = ("issue", "pr", "notes")
MILESTONE_DEP = "milestone:"
OWNER_TITLE = re.compile(r"^\[owner\]\s+([A-Za-z0-9.]+-[A-Za-z0-9]+)\b")


class TaskFileError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass
class Task:
    id: str
    title: str
    milestone: str
    status: str
    assignee: str
    risk: str
    depends_on: list[str]
    index: int
    issue: int | None = None
    pr: int | None = None
    notes: str = ""


@dataclass
class Graph:
    milestones: list[str]
    tasks: list[Task]
    by_id: dict[str, Task] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_id = {t.id: t for t in self.tasks}


def parse(text: str) -> Graph:
    """Parse and validate. Raises TaskFileError listing every problem found."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise TaskFileError([f"invalid TOML: {e}"]) from e
    errors: list[str] = []
    unknown_top = set(data) - {"milestones", "task"}
    if unknown_top:
        errors.append(f"unknown top-level keys: {sorted(unknown_top)}")
    milestones = data.get("milestones")
    if not isinstance(milestones, list) or not milestones or not all(isinstance(m, str) for m in milestones):
        errors.append("milestones must be a non-empty list of strings")
        milestones = []
    if len(set(milestones)) != len(milestones):
        errors.append("milestones contains duplicates")
    raw_tasks = data.get("task", [])
    if not isinstance(raw_tasks, list):
        raise TaskFileError(errors + ["task must be an array of tables ([[task]])"])

    tasks: list[Task] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_tasks):
        where = f"task #{i + 1} ({raw.get('id', '?')})"
        missing = [k for k in REQUIRED if k not in raw]
        unknown = sorted(set(raw) - set(REQUIRED) - set(OPTIONAL))
        if missing:
            errors.append(f"{where}: missing {missing}")
        if unknown:
            errors.append(f"{where}: unknown fields {unknown}")
        if missing:
            continue
        t = Task(
            id=raw["id"], title=raw["title"], milestone=raw["milestone"], status=raw["status"],
            assignee=raw["assignee"], risk=raw["risk"], depends_on=raw["depends_on"], index=i,
            issue=raw.get("issue"), pr=raw.get("pr"), notes=raw.get("notes", ""),
        )
        if not isinstance(t.id, str) or not re.fullmatch(r"[A-Za-z0-9.]+-(\d{2}|O\d+)", t.id):
            errors.append(f"{where}: id must look like M1-03 (agent) or M1-O2 (owner)")
        elif t.id in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(str(t.id))
        if t.milestone not in milestones:
            errors.append(f"{where}: milestone {t.milestone!r} not in milestones")
        elif isinstance(t.id, str) and not t.id.startswith(t.milestone + "-"):
            errors.append(f"{where}: id must start with its milestone ({t.milestone}-)")
        if t.status not in STATUSES:
            errors.append(f"{where}: status must be one of {STATUSES}")
        if t.assignee not in ASSIGNEES:
            errors.append(f"{where}: assignee must be one of {ASSIGNEES}")
        if t.risk not in RISKS:
            errors.append(f"{where}: risk must be one of {RISKS}")
        owner_id = isinstance(t.id, str) and re.search(r"-O\d+$", t.id) is not None
        if owner_id != (t.assignee == "owner"):
            errors.append(f"{where}: owner tasks (and only they) use ids like {t.milestone}-O1")
        if not isinstance(t.depends_on, list) or not all(isinstance(d, str) for d in t.depends_on):
            errors.append(f"{where}: depends_on must be a list of strings")
            t.depends_on = []
        for key in ("issue", "pr"):
            v = getattr(t, key)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
                errors.append(f"{where}: {key} must be a positive integer")
        if not isinstance(t.title, str) or not t.title.strip():
            errors.append(f"{where}: title must be a non-empty string")
        tasks.append(t)

    ids = {t.id for t in tasks}
    for t in tasks:
        for d in t.depends_on:
            if d.startswith(MILESTONE_DEP):
                m = d[len(MILESTONE_DEP):]
                if m not in milestones:
                    errors.append(f"{t.id}: depends on unknown milestone {m!r}")
                elif m == t.milestone:
                    errors.append(f"{t.id}: cannot depend on its own milestone")
            elif d not in ids:
                errors.append(f"{t.id}: depends on unknown task {d!r}")
            elif d == t.id:
                errors.append(f"{t.id}: depends on itself")
    if errors:
        raise TaskFileError(errors)
    graph = Graph(milestones, tasks)
    cycle = find_cycle(graph)
    if cycle:
        raise TaskFileError(["dependency cycle: " + " -> ".join(cycle)])
    return graph


def edges(graph: Graph, t: Task) -> list[str]:
    """Task-level dependencies, with milestone dependencies expanded to their tasks."""
    out: list[str] = []
    for d in t.depends_on:
        if d.startswith(MILESTONE_DEP):
            m = d[len(MILESTONE_DEP):]
            out.extend(x.id for x in graph.tasks if x.milestone == m)
        else:
            out.append(d)
    return out


def find_cycle(graph: Graph) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(tid: str) -> list[str] | None:
        state[tid] = 1
        stack.append(tid)
        for d in edges(graph, graph.by_id[tid]):
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if d not in state:
                found = visit(d)
                if found:
                    return found
        stack.pop()
        state[tid] = 2
        return None

    for t in graph.tasks:
        if t.id not in state:
            found = visit(t.id)
            if found:
                return found
    return None


def load_github(issues: list[dict] | None, prs: list[dict] | None) -> tuple[dict, dict, set[int]]:
    """Return (issue number -> closed?, owner task id from issue title -> closed?, merged PR numbers)."""
    by_number: dict[int, bool] = {}
    by_title: dict[str, bool] = {}
    for it in issues or []:
        closed = str(it.get("state", "")).lower() == "closed"
        by_number[int(it["number"])] = closed
        m = OWNER_TITLE.match(str(it.get("title", "")))
        if m:
            by_title[m.group(1)] = closed
    merged = {
        int(p["number"]) for p in prs or []
        if p.get("merged") is True or p.get("merged_at") or str(p.get("state", "")).lower() == "merged"
    }
    return by_number, by_title, merged


def derive(graph: Graph, issues=None, prs=None, claimed=()) -> dict[str, dict]:
    """Derived state per task: done | dropped | claimed | ready | blocked, plus unmet dependencies."""
    by_number, by_title, merged = load_github(issues, prs)
    claimed = set(claimed)

    def finished(t: Task) -> bool:
        if t.status == "done":
            return True
        if t.assignee != "owner" or t.status != "todo":
            return False
        if t.issue is not None and by_number.get(t.issue):
            return True
        if by_title.get(t.id):
            return True
        return t.pr is not None and t.pr in merged

    out: dict[str, dict] = {}
    for t in graph.tasks:
        def satisfied(tid: str) -> bool:
            return graph.by_id[tid].status == "dropped" or finished(graph.by_id[tid])

        unmet = []
        for d in t.depends_on:
            if d.startswith(MILESTONE_DEP):
                m = d[len(MILESTONE_DEP):]
                if not all(satisfied(x.id) for x in graph.tasks if x.milestone == m):
                    unmet.append(d)
            elif not satisfied(d):
                unmet.append(d)
        if t.status == "dropped":
            state = "dropped"
        elif finished(t):
            state = "done"
        elif t.id in claimed:
            state = "claimed"
        elif unmet:
            state = "blocked"
        else:
            state = "ready"
        out[t.id] = {"state": state, "unmet": unmet}
    return out


def drift(graph: Graph, issues=None, prs=None) -> list[str]:
    by_number, by_title, merged = load_github(issues, prs)
    msgs: list[str] = []
    for t in graph.tasks:
        closed = by_number.get(t.issue) if t.issue is not None else None
        if t.id in by_title:
            closed = by_title[t.id] if closed is None else closed or by_title[t.id]
        if t.status == "todo" and closed:
            msgs.append(f"{t.id}: issue closed but status is todo (set done in the next PR)")
        if t.status == "done" and closed is False:
            msgs.append(f"{t.id}: status done but its issue is still open")
        if t.status == "todo" and t.pr is not None and t.pr in merged:
            msgs.append(f"{t.id}: PR #{t.pr} merged but status is todo (set done in the next PR)")
    known = {t.id for t in graph.tasks}
    for tid in sorted(set(by_title) - known):
        msgs.append(f"{tid}: owner issue title names an unknown task id")
    return msgs


def order_key(graph: Graph, t: Task) -> tuple[int, int]:
    return (graph.milestones.index(t.milestone), t.index)


def matches(t: Task, assignee: str | None) -> bool:
    if assignee is None:
        return True
    if assignee == "agent":
        return t.assignee != "owner"
    return t.assignee == assignee


def read_text(file: str | None, ref: str | None) -> str:
    if ref:
        res = subprocess.run(["git", "show", f"{ref}:{DEFAULT_FILE}"], capture_output=True, text=True)
        if res.returncode != 0:
            raise TaskFileError([f"cannot read {DEFAULT_FILE} at {ref}: {res.stderr.strip()}"])
        return res.stdout
    path = Path(file or Path(__file__).resolve().parent.parent / DEFAULT_FILE)
    return sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")


def read_json(path: str | None) -> list[dict] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("items", data) if isinstance(data, dict) else data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--file", help=f"path to the task file (default {DEFAULT_FILE}; '-' for stdin)")
    src.add_argument("--ref", help=f"read {DEFAULT_FILE} from this git ref, e.g. origin/main")
    ap.add_argument("--issues", help="JSON file with GitHub issues (number, title, state)")
    ap.add_argument("--prs", help="JSON file with GitHub PRs (number, merged / merged_at)")
    ap.add_argument("--claimed", default="", help="comma-separated task ids held by running sessions")
    ap.add_argument("--assignee", help="filter: owner, agent, or one role")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("command", choices=("validate", "ready", "status", "drift"))
    a = ap.parse_args(argv)

    try:
        graph = parse(read_text(a.file, a.ref))
    except TaskFileError as e:
        for msg in e.errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    issues, prs = read_json(a.issues), read_json(a.prs)
    claimed = [c.strip() for c in a.claimed.split(",") if c.strip()]
    unknown_claims = sorted(set(claimed) - set(graph.by_id))
    if unknown_claims:
        print(f"error: --claimed names unknown tasks: {unknown_claims}", file=sys.stderr)
        return 1

    if a.command == "validate":
        print(f"ok: {len(graph.tasks)} tasks in {len(graph.milestones)} milestones")
        return 0
    if a.command == "drift":
        msgs = drift(graph, issues, prs)
        print(json.dumps(msgs, indent=2) if a.json else "\n".join(msgs) or "no drift")
        return 0

    derived = derive(graph, issues, prs, claimed)
    rows = sorted((t for t in graph.tasks if matches(t, a.assignee)), key=lambda t: order_key(graph, t))
    if a.command == "ready":
        rows = [t for t in rows if derived[t.id]["state"] == "ready"]
    if a.json:
        print(json.dumps([{
            "id": t.id, "title": t.title, "milestone": t.milestone, "assignee": t.assignee, "risk": t.risk,
            "issue": t.issue, "pr": t.pr, **derived[t.id],
        } for t in rows], indent=2))
        return 0
    for t in rows:
        d = derived[t.id]
        line = f"{t.id:<9} {t.assignee:<11} {t.risk:<6} "
        if a.command == "status":
            line += f"{d['state']:<8} "
        line += t.title
        if a.command == "status" and d["unmet"] and d["state"] in ("blocked", "claimed"):
            line += f"  [waits on {', '.join(d['unmet'])}]"
        if t.issue:
            line += f"  (#{t.issue})"
        print(line)
    if a.command == "ready" and not rows:
        print("no ready tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
