#!/usr/bin/env python3
"""Render the dependency graph of the open tasks (status-graph.svg), the second picture under the README status picture.

Nodes are the tasks that are not done (done and dropped tasks are not drawn); one band per milestone with open tasks, its
label says how many of its tasks are done. An arrow runs from a dependency to the task that waits on it, between open tasks
only, with transitive arrows removed (A to C is not drawn when A to B to C exists). Dependencies on done tasks and on a whole
milestone are not drawn; the legend counts them. A node is coloured and shaped by its derived state (ready, in progress,
blocked, owner to-do), the same states and marker shapes as status.svg.

Task M1-70 (written by `status_visual.py render` next to status.svg, published by `status_publish.py`). Offline, standard library
only, deterministic: the same model gives the same bytes, and there is no clock in the picture. A pure layered layout: a task's column
is the length of its longest chain of open dependencies; the boxes inside a column are ordered by barycentre sweeps (the order with
the fewest crossings, counted as straight lines between the boxes' column and row, wins; never worse than the model order); arrows are
orthogonal polylines in the gaps between columns and the channels between rows, never through a box, one track per arrow where they
share a gap (task M1-75).
Every title is untrusted text: stripped of control characters, clipped and escaped (it only appears in the node tooltips).
"""

import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

PAD, MIN_WIDTH, MAX_WIDTH = 24, 960, 1290  # 14 px text is 9 px or more at the 830 px README column up to 1291 px
NODE_H, HEADER, BAND_GAP = 24, 26, 10
CHAR, NODE_PAD = 8, 24  # node width = id width * CHAR + NODE_PAD (marker and padding)
SWEEPS = 4
TRACK, LEAD, TAIL, CHANNEL_MIN = 4, 4, 10, 6  # px between parallel arrows; a gap holds LEAD, its tracks, then TAIL (room for the arrowhead)
WORDS = {"ready": "ready", "review": "in progress", "blocked": "blocked", "owner": "owner to-do"}
MARKS = (("ready", "ok", "mk-ready"), ("review", "info", "mk-progress"), ("blocked", "warn", "mk-blocked"), ("owner", "bad", "mk-owner"))
MARK = {state: (cls, shape) for state, cls, shape in MARKS}
TITLE = "Open tasks and their dependencies"

CSS = (
    ".bg{fill:#ffffff}.card{fill:#f6f8fa}.fg{fill:#1f2328}.muted{fill:#59636e}.ok{fill:#1a7f37}.info{fill:#0969da}"
    ".warn{fill:#9a6700}.bad{fill:#cf222e}.edge{stroke:#8c959f;fill:none;stroke-width:1.2}.ah{fill:#8c959f}"
    ".nd-ready{fill:#dafbe1;stroke:#1a7f37}.nd-review{fill:#ddf4ff;stroke:#0969da}"
    ".nd-blocked{fill:#fff8c5;stroke:#9a6700}.nd-owner{fill:#ffebe9;stroke:#cf222e}"
    "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:14px}"
    ".t{font-size:22px;font-weight:600}.h{font-size:14px;font-weight:600;paint-order:stroke;stroke:#f6f8fa;stroke-width:4px}.s{font-size:14px}.n{font-size:14px;font-weight:600}"
    "@media (prefers-color-scheme: dark){.bg{fill:#0d1117}.card{fill:#161b22}.fg{fill:#e6edf3}.muted{fill:#9198a1}"
    ".ok{fill:#3fb950}.info{fill:#4493f8}.warn{fill:#d29922}.bad{fill:#f85149}.edge{stroke:#6e7681}.h{stroke:#161b22}.ah{fill:#6e7681}"
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


def attr(value):
    return escape(value, {'"': "&quot;"})


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


def _near(graph):
    preds, succs = {n["id"]: [] for n in graph["nodes"]}, {n["id"]: [] for n in graph["nodes"]}
    for a, b in graph["edges"]:
        preds[b].append(a)
        succs[a].append(b)
    return preds, succs


def _rows(graph, layer, cells):
    """Row of each task inside its band: a column is filled top down in its order, a task wanting the (rounded down) average row of its
    dependencies in the same band, so a chain stays level; a task never sits above the one before it."""
    band_of, rows = {n["id"]: n["milestone"] for n in graph["nodes"]}, {}
    preds = _near(graph)[0]
    for col in range(max(layer.values(), default=0) + 1):
        for b in graph["bands"]:
            prev = -1
            for i in cells.get((b["id"], col), ()):
                near = [rows[p] for p in preds[i] if band_of[p] == b["id"]]
                want = (2 * sum(near) + len(near) - 1) // (2 * len(near)) if near else 0
                rows[i] = prev = max(want, prev + 1)
    return rows


def crossings(graph, layer, cells):
    """Number of pairs of arrows that cross when each is drawn as a straight line from (column, row) to (column, row), the bands
    stacked in order. Arrows sharing an end do not count. The measure the ordering minimises."""
    rows, base, top = _rows(graph, layer, cells), {}, 0
    for b in graph["bands"]:
        base[b["id"]] = top
        top += 1 + max((rows[n["id"]] for n in graph["nodes"] if n["milestone"] == b["id"]), default=0)
    band_of = {n["id"]: n["milestone"] for n in graph["nodes"]}
    point = {i: (layer[i], base[band_of[i]] + rows[i]) for i in rows}

    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    lines = [(point[a], point[b]) for a, b in graph["edges"]]
    return sum(side(q1, q2, p1) * side(q1, q2, p2) < 0 and side(p1, p2, q1) * side(p1, p2, q2) < 0
               for k, (p1, p2) in enumerate(lines) for q1, q2 in lines[k + 1:])


def order_cells(graph, layer, sweeps=SWEEPS):
    """Cells (band id, column) -> task ids top to bottom. Starts from the model order; each sweep reorders the columns left to
    right by the average position of the dependencies, then right to left by the dependents (barycentre). The order with the
    fewest crossings seen (counted as in crossings()), the first one on a tie, is kept, so the result never has more crossings than the model order."""
    cells = {}
    for n in graph["nodes"]:
        cells.setdefault((n["milestone"], layer[n["id"]]), []).append(n["id"])
    band_no = {b["id"]: k for k, b in enumerate(graph["bands"])}
    band_of = {n["id"]: n["milestone"] for n in graph["nodes"]}
    preds, succs = _near(graph)
    last = max(layer.values(), default=0)

    def pos(cur):
        return {i: band_no[band_of[i]] + (k + 0.5) / len(cell) for (_, _), cell in cur.items() for k, i in enumerate(cell)}

    best, best_count = {k: list(v) for k, v in cells.items()}, crossings(graph, layer, cells)
    for _ in range(sweeps):
        for columns, near in ((range(1, last + 1), preds), (range(last - 1, -1, -1), succs)):
            for c in columns:
                where = pos(cells)
                for key, cell in cells.items():
                    if key[1] == c:
                        keys = {i: sum(where[j] for j in near[i]) / len(near[i]) if near[i] else where[i] for i in cell}
                        cell.sort(key=lambda i: keys[i])  # stable: a tie keeps the current order
            count = crossings(graph, layer, cells)
            if count < best_count:
                best, best_count = {k: list(v) for k, v in cells.items()}, count
    return best


def _tracks(spans):
    """Track number per key for {key: (lo, hi)}: spans that overlap (ends included) never share a track; first fit in a fixed order."""
    free, out = [], {}
    for key, (lo, hi) in sorted(spans.items(), key=lambda kv: (kv[1], kv[0])):
        t = next((k for k, end in enumerate(free) if end < lo), len(free))
        if t == len(free):
            free.append(hi)
        free[t] = hi
        out[key] = t
    return out, len(free)


def _ports(count, odd):
    """y offsets from the node centre for count arrows at one side, in the order of their other ends. Arrows leave on odd offsets
    and arrive on even ones, so a leaving and an arriving arrow never run along one line in the gap between two columns."""
    slots = [o for o in range(-8, 9) if o % 2 == odd and o != 0]
    return [slots[(2 * k + 1) * len(slots) // (2 * count)] for k in range(count)]


def _route(graph, layer, cells, width_of, top):
    """Geometry from the final order. Arrows run in the gaps between columns and in the channels between rows. A short arrow (to the
    next column) leaves its source, runs along a track in the gap and arrives; a long one also runs along a track in the channel
    next to its source row, so it never passes behind a node. Arrows sharing a gap or channel get different tracks (TRACK px apart),
    and gaps and channels grow to hold them. An arrow between two nodes level in adjacent columns is one straight line.
    Returns where each band starts and how tall it is, each node's (x, y), and each arrow's path data."""
    band_of = {n["id"]: n["milestone"] for n in graph["nodes"]}
    band_no = {b["id"]: k for k, b in enumerate(graph["bands"])}
    rows = _rows(graph, layer, cells)
    height = {b["id"]: 1 + max(rows[n["id"]] for n in graph["nodes"] if n["milestone"] == b["id"]) for b in graph["bands"]}
    at = {i: (band_no[band_of[i]], rows[i]) for i in rows}
    edges = sorted(graph["edges"])
    flat = {e for e in edges if layer[e[1]] == layer[e[0]] + 1 and at[e[0]] == at[e[1]]}
    long = [e for e in edges if layer[e[1]] > layer[e[0]] + 1]
    # a long arrow runs in the channel (band, j: the line above row j) next to its source row, on the side of its target
    channel = {e: (band_of[e[0]], at[e[0]][1] + (at[e[1]] >= at[e[0]])) for e in long}
    ch_track, ch_count = {}, {}
    for ch in sorted({channel[e] for e in long}):
        tracks, ch_count[ch] = _tracks({e: (layer[e[0]], layer[e[1]] - 1) for e in long if channel[e] == ch})
        ch_track.update(tracks)
    band_top, band_h, row_y, ch_y = {}, {}, {}, {}
    for b in graph["bands"]:
        bid, y = b["id"], top
        band_top[bid] = top
        y += HEADER
        for j in range(height[bid] + 1):
            ch_y[(bid, j)] = y
            y += max(CHANNEL_MIN, TRACK * (ch_count.get((bid, j), 0) + 1))
            if j < height[bid]:
                row_y[(bid, j)] = y
                y += NODE_H
        band_h[bid] = y - top
        top = y + BAND_GAP
    # where on a node's side each arrow ends: a flat one at the centre, the others spread, in the order of their other ends
    out_off, in_off = {}, {}
    for i in rows:
        for table, mine, odd in ((out_off, sorted((e for e in edges if e[0] == i and e not in flat), key=lambda e: (at[e[1]], e[1])), 1),
                                 (in_off, sorted((e for e in edges if e[1] == i and e not in flat), key=lambda e: (at[e[0]], e[0])), 0)):
            if mine:
                table.update(zip(mine, _ports(len(mine), odd), strict=True))
    centre = {i: row_y[(band_of[i], rows[i])] + NODE_H // 2 for i in rows}
    y_from = {e: centre[e[0]] + out_off.get(e, 0) for e in edges}
    y_to = {e: centre[e[1]] + in_off.get(e, 0) for e in edges}
    y_run = {e: ch_y[channel[e]] + TRACK * (ch_track[e] + 1) for e in long}
    # vertical pieces in each gap g (between columns g and g + 1): (arrow, 0) near the source, (arrow, 1) near the target
    verticals = {}
    for e in edges:
        if e in long:
            verticals.setdefault(layer[e[0]], {})[(e, 0)] = tuple(sorted((y_from[e], y_run[e])))
            verticals.setdefault(layer[e[1]] - 1, {})[(e, 1)] = tuple(sorted((y_run[e], y_to[e])))
        elif e not in flat:
            verticals.setdefault(layer[e[0]], {})[(e, 0)] = tuple(sorted((y_from[e], y_to[e])))
    track, gap_count = {}, {}
    for g in sorted(verticals):
        tracks, gap_count[g] = _tracks(verticals[g])
        track.update({k: (g, t) for k, t in tracks.items()})
    columns = max(layer.values(), default=-1) + 1

    def columns_at(step):
        xs = [PAD + 10]
        for g in range(columns - 1):
            xs.append(xs[-1] + width_of + LEAD + max(0, gap_count.get(g, 0) - 1) * step + TAIL)
        return xs

    # the gaps grow with their tracks; squeeze the tracks (never below 1 px apart) so the picture stays within MAX_WIDTH
    step = next((t for t in range(TRACK, 1, -1) if columns_at(t)[-1] + width_of + 10 + PAD <= MAX_WIDTH), 1)
    col_x = columns_at(step)

    def lane(key):
        g, t = track[key]
        return col_x[g] + width_of + LEAD + t * step

    paths = {}
    for e in edges:
        a, b = e
        d = f"M{col_x[layer[a]] + width_of} {y_from[e]}"
        if e in long:
            d += f" H{lane((e, 0))} V{y_run[e]} H{lane((e, 1))} V{y_to[e]}"
        elif e not in flat:
            d += f" H{lane((e, 0))} V{y_to[e]}"
        paths[e] = d + f" H{col_x[layer[b]] - 1}"
    return {"band_top": band_top, "band_h": band_h, "end": top - BAND_GAP, "right": col_x[-1] + width_of if columns else 0,
            "node": {i: (col_x[layer[i]], row_y[(band_of[i], rows[i])]) for i in rows}, "paths": paths}


def render_graph_svg(model):
    graph = open_graph(model)
    nodes, edges = graph["nodes"], graph["edges"]
    layer = layers([n["id"] for n in nodes], edges)
    width_of = max((status_visual.text_width(n["id"]) for n in nodes), default=0) * CHAR + NODE_PAD
    width = MIN_WIDTH
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
        y += 20
    y += 6
    if not nodes:
        text(PAD, y + 10, "No open tasks.", "ok")
        y += 34

    shapes, edge_paths, node_svg, bands_svg = [], [], [], []
    if nodes:
        cells = order_cells(graph, layer)
        geo = _route(graph, layer, cells, width_of, y)
        width = max(MIN_WIDTH, geo["right"] + 10 + PAD)  # nodes sit 10 px inside their band
        for b in graph["bands"]:
            bid = b["id"]
            opened = sum(n["milestone"] == bid for n in nodes)
            name = status_visual.clip(bid + " " + b["title"], 40)
            label = f"{name}: {b['done']}/{b['total']} done, {opened} open"
            bands_svg.append(f'<rect x="{PAD}" y="{geo["band_top"][bid]}" width="{width - 2 * PAD}" height="{geo["band_h"][bid]}" rx="6" class="card"/>')
            node_svg.append(f'<text x="{PAD + 10}" y="{geo["band_top"][bid] + 18}" class="fg h">{escape(label)}</text>')
        for (a, b), d in sorted(geo["paths"].items()):
            edge_paths.append(f'<path d="{d}" class="edge" data-from="{attr(a)}" data-to="{attr(b)}" marker-end="url(#ah)"/>')
        for n in nodes:
            x, ny = geo["node"][n["id"]]
            mid = ny + NODE_H // 2
            node_svg.append(f'<g data-id="{attr(n["id"])}" data-state="{n["state"]}">'
                            f'<title>{escape(n["id"] + ": " + status_visual.clip(n["title"], 100) + " (" + WORDS[n["state"]] + ")")}</title>'
                            f'<rect x="{x}" y="{ny}" width="{width_of}" height="{NODE_H}" rx="4" class="nd-{n["state"]}"/>'
                            f'{_marker(n["state"], x + 10, mid, *MARK[n["state"]])}'
                            f'<text x="{x + 20}" y="{mid + 5}" class="fg n">{escape(status_visual.clip(n["id"], 12))}</text></g>')
        y = geo["end"]
    y += 4
    legend_y = y + 14
    x = PAD
    for state, cls, shape in MARKS:
        shapes.append(_marker(state, x + 6, legend_y - 4, cls, shape))
        shapes.append(f'<text x="{x + 16}" y="{legend_y}" class="fg s">{WORDS[state]}</text>')
        x += 24 + 8 * len(WORDS[state]) + 18
    notes = ["Arrows point from dependency to dependent. Transitive arrows (A to C when A to B to C exists) are not drawn:",
             f"{plural(graph['dropped_transitive'], 'transitive arrow', 'transitive arrows')} hidden.",
             "Also not drawn: " + plural(graph["outside_done"], "dependency", "dependencies") + " on done or dropped tasks, "
             + ("1 on a whole milestone." if graph["outside_milestone"] == 1 else f"{graph['outside_milestone']} on whole milestones.")]
    for k, ln in enumerate(notes):
        shapes.append(f'<text x="{PAD}" y="{legend_y + 24 + 20 * k}" class="muted s">{escape(ln)}</text>')
    height = legend_y + 24 + 20 * len(notes) + 12
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
