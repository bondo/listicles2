#!/usr/bin/env python3
"""Task graph for Listicles: validate docs/tasks.toml and list ready tasks deterministically.

Process: docs/ORCHESTRATION.md section 4. Standard library only (Python 3.11+ for tomllib).

Usage:
  scripts/tasks.py [--file PATH | --ref GITREF] [--issues JSON] [--prs JSON] [--claimed IDS]
                   [--in-review IDS] [--assignee owner|agent|ROLE] [--json]
                   {validate,ready,review,status,drift}

  validate  schema, ids, dependencies and cycles; exit 1 on any error
  ready     todo tasks whose dependencies are all satisfied and that nobody has claimed or delivered
  review    todo tasks delivered on a branch and awaiting review or merge (the pick list for review rounds)
  status    every task with its derived state and unmet dependencies
  drift     places where the file disagrees with GitHub (closed issue / merged PR vs. status);
            needs --issues and/or --prs, otherwise exit 2

--issues: JSON from GitHub issue list or search: an array of {"number", "title", "state", "state_reason"},
          {"items": [...]}, an array of such pages (gh api --paginate --slurp), or JSON lines.
          An issue closed with state_reason "not_planned" does NOT finish an owner task.
--prs:    same shapes, items {"number", "state", "merged"} or {"number", "merged_at"} or a search item with pull_request.merged_at.
--claimed: comma-separated task ids held by running sessions (the state issue's Sessions table).
--in-review: comma-separated task ids committed on a branch and awaiting review or merge
          (the state issue's Branches table). They are not ready, and `review` lists them.
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
        if not isinstance(t.notes, str):
            errors.append(f"{where}: notes must be a string")
        if len(set(t.depends_on)) != len(t.depends_on):
            errors.append(f"{where}: depends_on has duplicates")
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
    by_id = {t.id: t for t in tasks}
    for t in tasks:
        if t.status != "done" or t.assignee == "owner":
            continue
        for d in t.depends_on:
            if d.startswith(MILESTONE_DEP):
                for x in tasks:
                    if x.milestone == d[len(MILESTONE_DEP):] and x.assignee != "owner" and x.status == "todo":
                        errors.append(f"{t.id}: status done but depends on {d}, where {x.id} is still todo")
                        break
                continue
            dep = by_id.get(d)
            if dep is not None and dep.assignee != "owner" and dep.status == "todo":
                errors.append(f"{t.id}: status done but depends on {d}, which is still todo")
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
    """Return (issue number -> issue state, owner task id from title -> issue state, merged PR numbers).

    Issue state is "open", "completed" or "not_planned" (any close reason other than completed). Several
    issues titled for one task id are combined independent of their order: any open one wins, then any
    completed one.
    """
    by_number: dict[int, str] = {}
    by_title: dict[str, str] = {}
    rank = {"open": 0, "completed": 1, "not_planned": 2}
    for it in issues or []:
        if str(it.get("state", "")).lower() != "closed":
            st = "open"
        elif str(it.get("state_reason") or "completed").lower() != "completed":
            st = "not_planned"  # not_planned, duplicate, ...: closed without the work being done
        else:
            st = "completed"
        by_number[int(it["number"])] = st
        m = OWNER_TITLE.match(str(it.get("title", "")))
        if m and (m.group(1) not in by_title or rank[st] < rank[by_title[m.group(1)]]):
            by_title[m.group(1)] = st
    merged = {
        int(p["number"]) for p in prs or []
        if p.get("merged") is True or p.get("merged_at") or str(p.get("state", "")).lower() == "merged"
        or (p.get("pull_request") or {}).get("merged_at")  # search/issues item shape
    }
    return by_number, by_title, merged


def owner_issue_state(t: Task, by_number: dict, by_title: dict) -> str | None:
    """Combined GitHub state of a task's issues (linked by number or by title): open > completed > not_planned."""
    states = {s for s in (by_number.get(t.issue) if t.issue is not None else None, by_title.get(t.id)) if s}
    for st in ("open", "completed", "not_planned"):
        if st in states:
            return st
    return None


def derive(graph: Graph, issues=None, prs=None, claimed=(), in_review=()) -> dict[str, dict]:
    """Derived state per task: done | dropped | claimed | in-review | ready | blocked, plus unmet dependencies."""
    by_number, by_title, merged = load_github(issues, prs)
    claimed, in_review = set(claimed), set(in_review)

    def finished(t: Task) -> bool:
        if t.status == "done":
            return True
        if t.assignee != "owner" or t.status != "todo":
            return False
        if owner_issue_state(t, by_number, by_title) == "completed":
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
                members = [x for x in graph.tasks if x.milestone == m]
                # A milestone with no tasks yet (not planned) is not satisfied.
                if not members or not all(satisfied(x.id) for x in members):
                    unmet.append(d)
            elif not satisfied(d):
                unmet.append(d)
        if t.status == "dropped":
            state = "dropped"
        elif finished(t):
            state = "done"
        elif t.id in claimed:
            state = "claimed"
        elif t.id in in_review:
            state = "in-review"
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
        st = owner_issue_state(t, by_number, by_title)
        linked = {x for x in (by_number.get(t.issue) if t.issue is not None else None, by_title.get(t.id)) if x}
        if len(linked) > 1:
            msgs.append(f"{t.id}: linked issues disagree ({', '.join(sorted(linked))}); the task counts as {st}")
        if t.status == "todo" and st == "completed":
            msgs.append(f"{t.id}: issue closed but status is todo (set done in the next PR)")
        if t.status == "todo" and st == "not_planned":
            msgs.append(f"{t.id}: issue closed without completion (not planned, duplicate, ...; owner decides: drop the task, or reopen the issue)")
        if t.status == "done" and st == "open":
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
    """Accept an array, {"items": [...]}, an array of such pages (gh --paginate --slurp), or JSON lines."""
    if not path:
        return None
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    pages = data if isinstance(data, list) else [data]
    out: list[dict] = []
    for page in pages:
        if isinstance(page, dict) and "items" in page and "number" not in page:
            out.extend(page["items"])
        elif isinstance(page, list):
            out.extend(page)
        else:
            out.append(page)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--file", help=f"path to the task file (default {DEFAULT_FILE}; '-' for stdin)")
    src.add_argument("--ref", help=f"read {DEFAULT_FILE} from this git ref, e.g. origin/main")
    ap.add_argument("--issues", help="JSON file with GitHub issues (number, title, state)")
    ap.add_argument("--prs", help="JSON file with GitHub PRs (number, merged / merged_at)")
    ap.add_argument("--claimed", default="", help="comma-separated task ids held by running sessions")
    ap.add_argument("--in-review", default="", help="comma-separated task ids awaiting review or merge")
    ap.add_argument("--assignee", help="filter: owner, agent, or one role")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("command", choices=("validate", "ready", "review", "status", "drift"))
    a = ap.parse_args(argv)

    try:
        graph = parse(read_text(a.file, a.ref))
    except TaskFileError as e:
        for msg in e.errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    issues, prs = read_json(a.issues), read_json(a.prs)
    claimed = [c.strip() for c in a.claimed.split(",") if c.strip()]
    in_review = [c.strip() for c in a.in_review.split(",") if c.strip()]
    for flag, ids in (("--claimed", claimed), ("--in-review", in_review)):
        unknown_ids = sorted(set(ids) - set(graph.by_id))
        if unknown_ids:
            print(f"error: {flag} names unknown tasks: {unknown_ids}", file=sys.stderr)
            return 1
    if a.assignee is not None and a.assignee not in ("agent", *ASSIGNEES):
        print(f"error: --assignee must be agent or one of {ASSIGNEES}", file=sys.stderr)
        return 1

    if a.command == "validate":
        print(f"ok: {len(graph.tasks)} tasks in {len(graph.milestones)} milestones")
        return 0
    if a.command == "drift":
        if issues is None and prs is None:
            print("error: drift needs --issues and/or --prs (no GitHub input, so nothing to compare)", file=sys.stderr)
            return 2
        msgs = drift(graph, issues, prs)
        print(json.dumps(msgs, indent=2) if a.json else "\n".join(msgs) or "no drift")
        return 0

    derived = derive(graph, issues, prs, claimed, in_review)
    rows = sorted((t for t in graph.tasks if matches(t, a.assignee)), key=lambda t: order_key(graph, t))
    if a.command in ("ready", "review"):
        want = "ready" if a.command == "ready" else "in-review"
        rows = [t for t in rows if derived[t.id]["state"] == want]
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
            line += f"{d['state']:<10} "
        line += t.title
        if a.command == "status" and d["unmet"] and d["state"] in ("blocked", "claimed"):
            line += f"  [waits on {', '.join(d['unmet'])}]"
        if t.issue:
            line += f"  (#{t.issue})"
        print(line)
    if a.command in ("ready", "review") and not rows:
        print(f"no {'ready' if a.command == 'ready' else 'in-review'} tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
