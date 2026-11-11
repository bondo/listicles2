#!/usr/bin/env python3
"""Task graph for Listicles: validate docs/tasks.toml and list ready tasks deterministically.

Process: docs/ORCHESTRATION.md section 4. Standard library only (Python 3.11+ for tomllib).

Usage:
  scripts/tasks.py [--file PATH | --ref GITREF] [--issues JSON] [--prs JSON] [--claimed IDS]
                   [--assignee owner|agent|ROLE] [--json] {validate,ready,status,drift}

  validate  schema, ids, dependencies and cycles; exit 1 on any error
  ready     todo tasks whose dependencies are all satisfied and that nobody has claimed
  status    every task with its derived state and unmet dependencies
  drift     places where the file disagrees with GitHub (closed issue / merged PR vs. status),
            plus follow-up rule violations when --followups is given
  followups open follow-up issues (docs/FOLLOW-UPS.md), counted by severity; needs --followups

--issues: JSON array of {"number", "title", "state"} (GitHub issue list or search items).
--prs:    JSON array of {"number", "state", "merged"} or {"number", "merged_at"}.
--followups: JSON of OPEN issues labelled `follow-up` (same shapes, plus "labels"). Labels:
          severity:<blocker|major|minor|nit>, target:<milestone>, area:<security-rules|sync-merge|release>, owner-ok.
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
SEVERITIES = ("blocker", "major", "minor", "nit")
PROTECTED_AREAS = ("security-rules", "sync-merge", "release")  # never deferred without owner-ok
BURN_DOWN = "FU"
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


def parse(text: str, burn_down: bool = True) -> Graph:
    """Parse and validate. Raises TaskFileError listing every problem found.

    burn_down: also require each milestone with agent work to have its Mx-FU task (see check_burn_downs).
    """
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
        if not isinstance(t.id, str) or not re.fullmatch(r"[A-Za-z0-9.]+-(\d{2}|O\d+|FU)", t.id):
            errors.append(f"{where}: id must look like M1-03 (agent), M1-O2 (owner) or M1-FU (burn-down)")
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
    if burn_down:
        errors += check_burn_downs(milestones, tasks)
    if errors:
        raise TaskFileError(errors)
    graph = Graph(milestones, tasks)
    cycle = find_cycle(graph)
    if cycle:
        raise TaskFileError(["dependency cycle: " + " -> ".join(cycle)])
    return graph


def check_burn_downs(milestones: list[str], tasks: list[Task]) -> list[str]:
    """Each milestone with non-owner work has one Mx-FU task: implementer, depending on all that work.

    That makes the follow-up burn-down the last agent task of its milestone, so `milestone:Mx`
    dependencies (and the merge task) cannot be satisfied while follow-ups are un-triaged.
    """
    errors: list[str] = []
    for m in milestones:
        mine = [t for t in tasks if t.milestone == m]
        work = [t for t in mine if t.assignee != "owner" and t.id != f"{m}-{BURN_DOWN}"]
        fu = next((t for t in mine if t.id == f"{m}-{BURN_DOWN}"), None)
        if fu is None:
            if work:
                errors.append(f"{m} has no burn-down task {m}-{BURN_DOWN} (docs/FOLLOW-UPS.md)")
            continue
        if fu.assignee != "implementer":
            errors.append(f"{fu.id} must be assigned to implementer")
        errors += [f"{fu.id} must depend on {t.id}" for t in work if t.id not in fu.depends_on]
    return errors


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


@dataclass
class FollowUp:
    number: int
    title: str
    severity: str | None
    target: str | None
    areas: list[str]
    owner_ok: bool
    conflicts: list[str] = field(default_factory=list)  # label prefixes that appear more than once


def load_followups(items: list[dict] | None) -> list[FollowUp]:
    """Open issues labelled `follow-up`. Labels may be strings or {"name": ...} objects."""
    out: list[FollowUp] = []
    for it in items or []:
        if str(it.get("state", "open")).lower() == "closed":
            continue
        names = [str(x.get("name", "") if isinstance(x, dict) else x) for x in it.get("labels") or []]
        if "follow-up" not in names:
            continue

        def one(prefix: str) -> str | None:
            vals = [n[len(prefix):] for n in names if n.startswith(prefix)]
            return vals[0] if vals else None

        out.append(FollowUp(
            number=int(it["number"]), title=str(it.get("title", "")), severity=one("severity:"),
            target=one("target:"), areas=[n[len("area:"):] for n in names if n.startswith("area:")],
            owner_ok="owner-ok" in names,
            conflicts=[p for p in ("severity:", "target:") if sum(n.startswith(p) for n in names) > 1],
        ))
    return out


def followup_counts(fus: list[FollowUp], target: str | None = None) -> dict[str, int]:
    counts = dict.fromkeys(SEVERITIES, 0)
    for f in fus:
        if (target is None or f.target == target) and f.severity in counts:
            counts[f.severity] += 1
    return counts


def followup_summary(fus: list[FollowUp], target: str | None = None) -> str:
    counts = followup_counts(fus, target)
    total = sum(1 for f in fus if target is None or f.target == target)
    return f"open follow-ups: {total} (" + ", ".join(f"{k} {v}" for k, v in counts.items()) + ")"


def followup_notes(graph: Graph, fus: list[FollowUp]) -> dict[str, str]:
    """Burn-down task id -> its milestone's open follow-ups, for the ready/status output."""
    return {t.id: followup_summary(fus, t.milestone) for t in graph.tasks
            if t.id == f"{t.milestone}-{BURN_DOWN}" and any(f.target == t.milestone for f in fus)}


def followup_drift(graph: Graph, fus: list[FollowUp]) -> list[str]:
    """Violations of the deferral rules that can be seen from labels alone."""
    msgs: list[str] = []
    for f in fus:
        n = f"#{f.number}"
        msgs += [f"{n}: more than one {c} label (keep exactly one)" for c in f.conflicts]
        if f.severity is None:
            msgs.append(f"{n}: follow-up has no severity:<level> label")
        elif f.severity not in SEVERITIES:
            msgs.append(f"{n}: unknown severity {f.severity!r}")
        elif f.severity == "blocker":
            msgs.append(f"{n}: blockers are never deferred")
        elif f.severity == "major" and not f.owner_ok:
            msgs.append(f"{n}: major follow-up needs the owner-ok label")
        if not f.owner_ok:
            msgs += [f"{n}: area:{a} follow-up needs the owner-ok label" for a in f.areas if a in PROTECTED_AREAS]
        if f.target is None:
            msgs.append(f"{n}: follow-up has no target:<milestone> label")
        elif f.target not in graph.milestones:
            msgs.append(f"{n}: target milestone {f.target!r} is unknown")
        else:
            fu = graph.by_id.get(f"{f.target}-{BURN_DOWN}")
            if fu is not None and fu.status in ("done", "dropped"):
                msgs.append(f"{n}: target {f.target} but burn-down {fu.id} is already {fu.status} (retarget with owner OK)")
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
    ap.add_argument("--followups", help="JSON file with OPEN `follow-up` issues (number, title, state, labels)")
    ap.add_argument("--claimed", default="", help="comma-separated task ids held by running sessions")
    ap.add_argument("--assignee", help="filter: owner, agent, or one role")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("command", choices=("validate", "ready", "status", "drift", "followups"))
    a = ap.parse_args(argv)

    try:
        graph = parse(read_text(a.file, a.ref))
    except TaskFileError as e:
        for msg in e.errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    issues, prs = read_json(a.issues), read_json(a.prs)
    fus = load_followups(read_json(a.followups))
    if a.command == "followups" and not a.followups:
        print("error: followups needs --followups (open issues labelled follow-up)", file=sys.stderr)
        return 1
    claimed = [c.strip() for c in a.claimed.split(",") if c.strip()]
    unknown_claims = sorted(set(claimed) - set(graph.by_id))
    if unknown_claims:
        print(f"error: --claimed names unknown tasks: {unknown_claims}", file=sys.stderr)
        return 1

    if a.command == "validate":
        print(f"ok: {len(graph.tasks)} tasks in {len(graph.milestones)} milestones")
        return 0
    if a.command == "drift":
        msgs = drift(graph, issues, prs) + followup_drift(graph, fus)
        print(json.dumps(msgs, indent=2) if a.json else "\n".join(msgs) or "no drift")
        return 0

    if a.command == "followups":
        if a.json:
            print(json.dumps({"counts": followup_counts(fus), "items": [
                {"number": f.number, "title": f.title, "severity": f.severity, "target": f.target,
                 "areas": f.areas, "owner_ok": f.owner_ok} for f in fus]}, indent=2))
            return 0
        for f in sorted(fus, key=lambda f: (SEVERITIES.index(f.severity) if f.severity in SEVERITIES else 9, f.number)):
            print(f"#{f.number:<5} {f.severity or '?':<8} {f.target or '?':<5} {f.title}")
        print(followup_summary(fus))
        return 0

    derived = derive(graph, issues, prs, claimed)
    rows = sorted((t for t in graph.tasks if matches(t, a.assignee)), key=lambda t: order_key(graph, t))
    if a.command == "ready":
        rows = [t for t in rows if derived[t.id]["state"] == "ready"]
    notes = followup_notes(graph, fus)
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
        if t.id in notes:
            line += f"  [{notes[t.id]}]"
        print(line)
    if a.command == "ready" and not rows:
        print("no ready tasks")
    if a.followups:
        print(followup_summary(fus))
    return 0


if __name__ == "__main__":
    sys.exit(main())
