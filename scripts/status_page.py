#!/usr/bin/env python3
"""Render the status detail page (status.md): per milestone its name and purpose, a table of all its tasks and a Mermaid
graph of the open tasks and what blocks them, then every blocker. Pure text in, text out; deterministic (no clock, no ages),
so the publisher only rewrites it when something changes.

Used by scripts/status_visual.py render (it writes status.md next to the SVG). Every title is untrusted text: it is clipped,
stripped of control characters and escaped for a Markdown table cell or a quoted Mermaid label. Standard library only.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

MAX_PAGE_TITLE = 100
MAX_DEPS_CELL = 2000  # ids are short; a burn-down task lists a whole milestone and must not lose any
MAX_GRAPH_TITLE = 40
WWW = re.compile(r"(?i)\b(www)\.")  # "www.host" autolinks without a scheme
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
WORDS = {"done": "done", "dropped": "dropped", "ready": "ready", "review": "in progress", "blocked": "blocked", "owner": "owner to-do"}
CELL_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", "|": "&#124;", "`": "&#96;", "[": "&#91;", "]": "&#93;", "\\": "&#92;",
                ":": "&#58;", "@": "&#64;"}  # no "scheme:" or "user@host" for GFM to autolink
LABEL_ESCAPES = {'"': "#quot;", "<": "#lt;", ">": "#gt;", "`": "#96;", "[": "#91;", "]": "#93;", "|": "#124;", "\\": "#92;",
                 "&": "#38;", "#": "#35;", ";": "#59;", "%": "#37;"}
CLASS_DEFS = (
    "classDef ready fill:#dafbe1,stroke:#1a7f37,color:#1f2328",
    "classDef progress fill:#ddf4ff,stroke:#0969da,color:#1f2328",
    "classDef blocked fill:#fff8c5,stroke:#9a6700,color:#1f2328",
    "classDef owner fill:#ffebe9,stroke:#cf222e,color:#1f2328,stroke-dasharray:4 3",
    "classDef ext fill:#eaeef2,stroke:#59636e,color:#1f2328,stroke-dasharray:2 2",
)
NODE_CLASS = {"ready": "ready", "review": "progress", "blocked": "blocked", "owner": "owner"}


class PageError(Exception):
    pass


def _escape(text, table):
    return "".join(table.get(c, c) for c in text)


def cell(text, n=MAX_PAGE_TITLE):
    """Text safe inside a Markdown table cell or list item: one line, clipped, no markup characters."""
    return WWW.sub(r"\1&#46;", _escape(status_visual.clip(text, n), CELL_ESCAPES))


def mermaid_label(text):
    """Text safe inside a double-quoted Mermaid label: every special character becomes an entity (#quot; #35; ...)."""
    return _escape(status_visual.clip(text, 200), LABEL_ESCAPES)


def _ref(number, repo):
    return f"[#{int(number)}](https://github.com/{repo}/issues/{int(number)})" if repo else f"#{int(number)}"


def _deps(t):
    deps = [("all of " + d[len(status_visual.tasks.MILESTONE_DEP):]) if d.startswith(status_visual.tasks.MILESTONE_DEP) else d for d in t["deps"]]
    return cell(", ".join(deps), MAX_DEPS_CELL) if deps else "none"


def _status(t, repo):
    word = WORDS[t["state"]]
    if t["flag"] and t["state"] == "blocked":
        return f"blocked by {_ref(int(t['flag'][1:]), repo)}"
    return word


def _task_table(m, repo):
    out = ["| Task | Title | Status | Depends on | Who | PR |", "|---|---|---|---|---|---|"]
    for t in m["tasks"]:
        number = t["pr"] or t["toml_pr"]
        out.append(f"| {cell(t['id'], 16)} | {cell(t['title'])} | {_status(t, repo)} | {_deps(t)} | {cell(t['assignee'], 16)} | "
                   f"{_ref(number, repo) if number else ''} |")
    return out


def _graph(m, by_id, home):
    """Mermaid flowchart of the open tasks of one milestone; an arrow points from what is waited on to the waiting task."""
    open_tasks = [t for t in m["tasks"] if t["state"] not in status_visual.FINISHED]
    nodes, lines, edges = {}, ["flowchart LR"], []

    def node(key, label, cls):
        if key not in nodes:
            nodes[key] = f"n{len(nodes)}"
            lines.append(f'    {nodes[key]}["{label}"]:::{cls}')
        return nodes[key]

    def task_node(t, cls=None):
        label = f"{mermaid_label(t['id'])} {mermaid_label(status_visual.clip(t['title'], MAX_GRAPH_TITLE))} ({WORDS[t['state']]})"
        return node(t["id"], label, cls or NODE_CLASS[t["state"]])

    for t in open_tasks:
        task_node(t)
    for t in open_tasks:
        for u in t["unmet"]:
            if u["milestone"]:
                src = node(u["ref"], "all of " + mermaid_label(u["ref"][len(status_visual.tasks.MILESTONE_DEP):]), "ext")
            else:
                src = task_node(by_id[u["ref"]], None if home[u["ref"]] == m["id"] else "ext")  # other milestones: dashed grey, status word kept
            edge = f"    {src} --> {nodes[t['id']]}"
            if edge not in edges:
                edges.append(edge)
    return lines + edges + [f"    {d}" for d in CLASS_DEFS]


def render_page(model, repo=None):
    if repo is not None and not (isinstance(repo, str) and REPO.fullmatch(repo) and ".." not in repo):
        raise PageError("repo must look like OWNER/NAME")
    by_id = {t["id"]: t for m in model["milestones"] for t in m["tasks"]}
    home = {t["id"]: m["id"] for m in model["milestones"] for t in m["tasks"]}
    out = ["# Tally status detail", "",
           "Milestones, their tasks, what each open task waits on, and every blocker, generated from `docs/tasks.toml` and the open "
           "PRs and issues. The picture on the front page (`status.svg`) shows the same state. Status words: **done**, **ready** (all "
           "dependencies met), **in progress** (an open PR names the task), **blocked** (unmet dependencies or a `blocked` label), "
           "**owner to-do** (needs the owner).", "", "## Overview", "",
           "| Milestone | Name | Done | Open |", "|---|---|---|---|"]
    for m in model["milestones"]:
        progress = "not planned yet" if m["planned"] else f"{m['done']}/{m['total']} ({m['pct']}%)"
        out.append(f"| {cell(m['id'], 16)} | {cell(m['title'], 60)} | {progress} | {m['total'] - m['done']} |")
    for m in model["milestones"]:
        out += ["", f"## {cell(m['id'], 16)} {cell(m['title'], 60)}", "", cell(m["purpose"], 160), ""]
        if m["planned"]:
            out.append("Not planned yet.")
            continue
        out += [f"**Progress:** {m['done']}/{m['total']} done ({m['pct']}%), {m['total'] - m['done']} open.", "", "### Tasks", ""]
        out += _task_table(m, repo)
        out += ["", "### Open tasks and what blocks them", ""]
        if all(t["state"] in status_visual.FINISHED for t in m["tasks"]):
            out.append("Nothing open.")
        else:
            out += ["An arrow points from what a task waits on to the task. Dashed grey boxes are outside this milestone.", "",
                    "```mermaid", *_graph(m, by_id, home), "```"]
    out += ["", "## Blockers", ""]
    if not model["all_blockers"]:
        out.append("No blockers.")
    for b in model["all_blockers"]:
        ref = _ref(b["ref"][1:], repo) if b["ref"].startswith("#") else cell(b["ref"], 16)
        out.append(f"- **{status_visual.KIND_TEXT[b['kind']][0]}** {ref}: {cell(b['text'])}")
    return "\n".join(out) + "\n"
