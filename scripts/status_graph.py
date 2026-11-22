#!/usr/bin/env python3
"""Render the dependency graph of the open tasks (status-graph.svg), the second picture under the README status picture.

Nodes are the tasks that are not done (done and dropped tasks are not drawn); one band per milestone with open tasks, its
label says how many of its tasks are done. An arrow runs from a dependency to the task that waits on it, between open tasks
only, with transitive arrows removed (A to C is not drawn when A to B to C exists). Dependencies on done tasks and on a whole
milestone are not drawn; the legend counts them. A node is coloured and shaped by its derived state (ready, in progress,
blocked, owner to-do), the same states and marker shapes as status.svg.

Used by scripts/status_visual.py render, which writes the file next to status.svg. Offline, standard library only,
deterministic: the same model gives the same bytes, and there is no clock in the picture. A pure layered layout: a task's
column is the length of its longest chain of open dependencies, rows are ordered by a few barycentre sweeps.
Every title is untrusted text: stripped of control characters, clipped and escaped (it only appears in the node tooltips).
"""

import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

PAD, MIN_WIDTH = 24, 880
NODE_H, ROW, HEADER, BAND_GAP, GAP = 22, 28, 24, 10, 26
CHAR, NODE_PAD = 7, 26  # node width = id width * CHAR + NODE_PAD (marker and padding)
SWEEPS = 3
WORDS = {"ready": "ready", "review": "in progress", "blocked": "blocked", "owner": "owner to-do"}
MARKS = (("ready", "ok", "mk-ready"), ("review", "info", "mk-progress"), ("blocked", "warn", "mk-blocked"), ("owner", "bad", "mk-owner"))
MARK = {state: (cls, shape) for state, cls, shape in MARKS}
TITLE = "Open tasks and their dependencies"

CSS = (
    ".bg{fill:#ffffff}.card{fill:#f6f8fa}.fg{fill:#1f2328}.muted{fill:#59636e}.ok{fill:#1a7f37}.info{fill:#0969da}"
    ".warn{fill:#9a6700}.bad{fill:#cf222e}.edge{stroke:#8c959f;fill:none;stroke-width:1.2}.ah{fill:#8c959f}"
    ".nd-ready{fill:#dafbe1;stroke:#1a7f37}.nd-review{fill:#ddf4ff;stroke:#0969da}"
    ".nd-blocked{fill:#fff8c5;stroke:#9a6700}.nd-owner{fill:#ffebe9;stroke:#cf222e}"
    "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:13px}"
    ".t{font-size:20px;font-weight:600}.h{font-size:13px;font-weight:600}.s{font-size:12px}.n{font-size:11px;font-weight:600}"
    "@media (prefers-color-scheme: dark){.bg{fill:#0d1117}.card{fill:#161b22}.fg{fill:#e6edf3}.muted{fill:#9198a1}"
    ".ok{fill:#3fb950}.info{fill:#4493f8}.warn{fill:#d29922}.bad{fill:#f85149}.edge{stroke:#6e7681}.ah{fill:#6e7681}"
    ".nd-ready{fill:#12261e;stroke:#3fb950}.nd-review{fill:#10294d;stroke:#4493f8}"
    ".nd-blocked{fill:#2f2408;stroke:#d29922}.nd-owner{fill:#3b1219;stroke:#f85149}}"
)


def reduce(edges):
    """Transitive reduction of a DAG given as (from, to) pairs: (kept edges in first-seen order, number removed).
    Duplicates collapse without counting. An edge goes when its target is reachable from its source another way."""
    unique = list(dict.fromkeys(edges))
    succ = {}
    for a, b in unique:
        succ.setdefault(a, []).append(b)
    memo = {}

    def reach(n):
        if n not in memo:
            memo[n] = set()  # also stops a cycle from recursing forever (the task file validator rejects cycles)
            for m in succ.get(n, ()):
                memo[n] |= {m} | reach(m)
        return memo[n]

    kept = [(a, b) for a, b in unique if not any(b in reach(w) for w in succ[a] if w != b)]
    return kept, len(unique) - len(kept)


def layers(ids, edges):
    """Column of each task: 0 without open dependencies, else one more than its deepest dependency."""
    preds = {i: [] for i in ids}
    for a, b in edges:
        preds[b].append(a)
    out = {}

    def depth(i):
        if i not in out:
            out[i] = 0  # cycle guard
            out[i] = 1 + max((depth(p) for p in preds[i]), default=-1)
        return out[i]

    return {i: depth(i) for i in ids}


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def open_graph(model):
    """The open tasks (model order), the reduced edges and what is left out, from status_visual.build_model()."""
    nodes = [{"id": t["id"], "title": t["title"], "state": t["state"], "milestone": m["id"]}
             for m in model["milestones"] for t in m["tasks"] if t["state"] not in status_visual.FINISHED]
    open_ids = {n["id"] for n in nodes}
    raw, outside_done, outside_milestone = [], 0, 0
    for m in model["milestones"]:
        for t in m["tasks"]:
            if t["id"] not in open_ids:
                continue
            for d in t["deps"]:
                if d.startswith(status_visual.tasks.MILESTONE_DEP):
                    outside_milestone += 1
                elif d in open_ids:
                    raw.append((d, t["id"]))
                else:
                    outside_done += 1
    edges, dropped = reduce(raw)
    bands = [{"id": m["id"], "title": m["title"], "done": m["done"], "total": m["total"]}
             for m in model["milestones"] if any(n["milestone"] == m["id"] for n in nodes)]
    return {"nodes": nodes, "edges": edges, "dropped_transitive": dropped, "outside_done": outside_done,
            "outside_milestone": outside_milestone, "bands": bands,
            "finished": [m for m in model["milestones"] if not m["planned"] and m["done"] == m["total"]],
            "planned": [m["id"] for m in model["milestones"] if m["planned"]]}


def _order(graph, layer):
    """Cells (band, column) -> task ids top to bottom, ordered by a few sweeps over the average row of the neighbours."""
    cells, band_of = {}, {n["id"]: n["milestone"] for n in graph["nodes"]}
    for n in graph["nodes"]:
        cells.setdefault((band_of[n["id"]], layer[n["id"]]), []).append(n["id"])
    slots = {b["id"]: max(len(v) for (bb, _), v in cells.items() if bb == b["id"]) for b in graph["bands"]}
    offset, top = {}, 0
    for b in graph["bands"]:
        offset[b["id"]] = top
        top += 2 * slots[b["id"]] + 3
    preds, succs = {i: [] for i in band_of}, {i: [] for i in band_of}
    for a, b in graph["edges"]:
        preds[b].append(a)
        succs[a].append(b)

    def half_row(i):
        cell = cells[(band_of[i], layer[i])]
        return offset[band_of[i]] + 2 * cell.index(i) + slots[band_of[i]] - len(cell)

    def sweep(columns, near):
        for c in columns:
            for key, cell in cells.items():
                if key[1] == c:
                    keys = {i: (sum(map(half_row, near[i])) / len(near[i]) if near[i] else half_row(i)) for i in cell}
                    cell.sort(key=lambda i: keys[i])

    last = max(layer.values(), default=0)
    for _ in range(SWEEPS):
        sweep(range(last, -1, -1), succs)
        sweep(range(last + 1), preds)
    return cells, slots, band_of


def render_graph_svg(model):
    graph = open_graph(model)
    nodes, edges = graph["nodes"], graph["edges"]
    layer = layers([n["id"] for n in nodes], edges)
    width_of = max((status_visual.text_width(n["id"]) for n in nodes), default=0) * CHAR + NODE_PAD
    pitch = width_of + GAP
    columns = max(layer.values(), default=-1) + 1
    width = max(MIN_WIDTH, 2 * PAD + columns * pitch - GAP)
    out = []

    def text(x, y, content, cls="fg", extra=""):
        out.append(f'<text x="{x}" y="{y}" class="{cls}"{extra}>{content}</text>')

    text(PAD, 36, TITLE, "fg t")
    y = 56
    lines = [f"{plural(len(nodes), 'open task', 'open tasks')} in {plural(len(graph['bands']), 'milestone', 'milestones')}. "
             "Task ids only; titles are on the status detail page."]
    if graph["finished"]:
        lines.append("All done: " + "; ".join(f"{m['id']} {m['done']}/{m['total']}" for m in graph["finished"]))
    if graph["planned"]:
        lines.append("Not planned yet: " + ", ".join(graph["planned"]))
    for ln in lines:
        text(PAD, y, escape(status_visual.clip(ln, 140)), "muted s")
        y += 18
    y += 6
    if not nodes:
        text(PAD, y + 10, "No open tasks.", "ok")
        y += 34

    shapes, edge_paths, node_svg, bands_svg = [], [], [], []
    if nodes:
        cells, slots, band_of = _order(graph, layer)
        pos = {}
        for b in graph["bands"]:
            top = y
            bid, rows = b["id"], slots[b["id"]]
            opened = sum(n["milestone"] == bid for n in nodes)
            name = status_visual.clip(bid + " " + b["title"], 40)
            label = f"{name}: {b['done']}/{b['total']} done, {opened} open"
            bands_svg.append(f'<rect x="{PAD}" y="{top}" width="{width - 2 * PAD}" height="{HEADER + rows * ROW + 4}" rx="6" class="card"/>')
            bands_svg.append(f'<text x="{PAD + 10}" y="{top + 17}" class="fg h">{escape(label)}</text>')
            for (bb, col), cell in cells.items():
                if bb == bid:
                    for idx, tid in enumerate(cell):
                        pos[tid] = (PAD + 10 + col * pitch, top + HEADER + (2 * idx + rows - len(cell)) * ROW // 2 + 3)
            y = top + HEADER + rows * ROW + 4 + BAND_GAP
        for a, b in sorted(edges):
            (x1, y1), (x2, y2) = pos[a], pos[b]
            x1, y1, y2 = x1 + width_of, y1 + NODE_H // 2, y2 + NODE_H // 2
            dx = max((x2 - x1) // 2, 12)
            curve = f"M{x1} {y1} C{x1 + dx} {y1} {x2 - dx} {y2} {x2 - 1} {y2}"
            edge_paths.append(f'<path d="{curve}" class="edge" data-from="{escape(a)}" data-to="{escape(b)}" marker-end="url(#ah)"/>')
        for n in nodes:
            x, ny = pos[n["id"]]
            mid = ny + NODE_H // 2
            node_svg.append(f'<g data-id="{escape(n["id"])}" data-state="{n["state"]}">'
                            f'<title>{escape(n["id"] + ": " + status_visual.clip(n["title"], 100) + " (" + WORDS[n["state"]] + ")")}</title>'
                            f'<rect x="{x}" y="{ny}" width="{width_of}" height="{NODE_H}" rx="4" class="nd-{n["state"]}"/>'
                            f'{_marker(n["state"], x + 10, mid, *MARK[n["state"]])}'
                            f'<text x="{x + 19}" y="{mid + 4}" class="fg n">{escape(status_visual.clip(n["id"], 12))}</text></g>')
    y += 4
    legend_y = y + 14
    x = PAD
    for state, cls, shape in MARKS:
        shapes.append(_marker(state, x + 6, legend_y - 4, cls, shape))
        shapes.append(f'<text x="{x + 16}" y="{legend_y}" class="fg s">{WORDS[state]}</text>')
        x += 24 + 7 * len(WORDS[state]) + 18
    notes = ["Arrows point from dependency to dependent. Transitive arrows are not drawn (A to C is skipped when A to B to C exists): "
             f"{plural(graph['dropped_transitive'], 'transitive arrow', 'transitive arrows')} hidden.",
             "Also not drawn: " + plural(graph["outside_done"], "dependency", "dependencies") + " on done tasks, "
             + ("1 on a whole milestone." if graph["outside_milestone"] == 1 else f"{graph['outside_milestone']} on whole milestones.")]
    for k, ln in enumerate(notes):
        shapes.append(f'<text x="{PAD}" y="{legend_y + 22 + 16 * k}" class="muted s">{escape(ln)}</text>')
    height = legend_y + 22 + 16 * len(notes) + 12
    summary = f"{plural(len(nodes), 'open task', 'open tasks')}, {plural(len(edges), 'dependency', 'dependencies')}"
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-labelledby="ti de"><title id="ti">{TITLE}</title><desc id="de">{escape(summary)}</desc><style>{CSS}</style>'
            '<defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
            '<path d="M0 0L8 4L0 8z" class="ah"/></marker></defs>'
            f'<rect width="{width}" height="{height}" class="bg"/>')
    return head + "\n" + "\n".join([*out, *bands_svg, *edge_paths, *node_svg, *shapes]) + "\n</svg>\n"


def _marker(state, x, cy, cls, shape):
    if state == "ready":
        return f'<circle cx="{x}" cy="{cy}" r="4.5" class="{cls} {shape}"/>'
    if state == "review":
        return f'<polygon points="{x - 5},{cy + 4} {x + 5},{cy + 4} {x},{cy - 5}" class="{cls} {shape}"/>'
    if state == "blocked":
        return f'<rect x="{x - 4}" y="{cy - 4}" width="8" height="8" class="{cls} {shape}"/>'
    return f'<polygon points="{x - 5},{cy} {x},{cy - 5} {x + 5},{cy} {x},{cy + 5}" class="{cls} {shape}"/>'
