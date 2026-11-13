#!/usr/bin/env python3
"""Render the project status (docs/tasks.toml plus pre-fetched GitHub data) as one deterministic SVG.

Usage:
  python3 -I scripts/status_visual.py render --tasks docs/tasks.toml --input input.json [--now 2026-11-13T12:00:00Z]
                                              --svg status.svg --json status.json
  python3 -I scripts/status_visual.py same OLD.svg NEW.svg      exit 0 if equal ignoring the stamp, 1 if not, 2 on error

input.json is what scripts/status_fetch.py writes: {"prs": [{number, title, draft, ci, behind}],
"issues": [{number, title, state, state_reason, created_at, labels: [name]}]}. Offline: no network, standard library only.
Every title is untrusted text: it is stripped of control and invisible characters, clipped and XML-escaped. Only
numbers, label names compared to a fixed list, and task ids from docs/tasks.toml are used as data. Exit 2 on bad input.
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, UTC
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402  # justified: must follow the sys.path insert above

MAX_TITLE = 60
WIDE_LATIN = "WMwm@"
MAX_CHAIN = 8
MAX_QUEUE = 8
MAX_BLOCKERS = 14
STAMP_ID = "generated"
WIDTH = 880
PR_TASK = re.compile(r"^([A-Za-z0-9.]+-(?:\d{2}|O\d+|FU)):")
KIND_ORDER = ("owner-todo", "blocked", "needs-owner", "pr-waiting", "task")
LABEL_KINDS = (("owner-todo", "owner-todo"), ("blocked", "blocked"), ("needs-owner", "needs-owner"))
CI_STATES = ("passing", "failing", "pending", "none")


class StatusError(Exception):
    pass


def text_width(text):
    """Display width in units: East Asian wide and fullwidth characters and the widest Latin glyphs count 2, the rest 1."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" or c in WIDE_LATIN else 1 for c in text)


def clip(text, n):
    """Plain text safe to show: no control, format, surrogate or private characters; one line; at most n width units."""
    if not isinstance(text, str):
        return ""
    kept = "".join(" " if c.isspace() else c for c in text if c.isspace() or unicodedata.category(c)[0] != "C")
    kept = " ".join(kept.split())
    if text_width(kept) <= n:
        return kept
    out, used = [], 0
    for c in kept:
        used += text_width(c)
        if used > n - 1:
            break
        out.append(c)
    return "".join(out) + "…"


def label(text, n=MAX_TITLE):
    return escape(clip(text, n), {'"': "&quot;", "'": "&apos;"})


def _ts(value, what):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise StatusError(f"{what} must be an ISO 8601 time with a zone, like 2026-11-13T12:00:00Z") from None
    if dt.tzinfo is None:
        raise StatusError(f"{what} needs a time zone")
    return dt.astimezone(UTC)


def _number(item, what):
    n = item.get("number") if isinstance(item, dict) else None
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise StatusError(f"{what}: number must be a positive integer")
    return n


def _checked_input(data):
    if not isinstance(data, dict) or not isinstance(data.get("prs"), list) or not isinstance(data.get("issues"), list):
        raise StatusError('input must be {"prs": [...], "issues": [...]}')
    outside = data.get("outside_questions", 0)
    if not isinstance(outside, int) or isinstance(outside, bool) or outside < 0:
        raise StatusError("outside_questions must be a whole number, 0 or more")
    prs, issues = [], []
    for p in data["prs"]:
        ci = p.get("ci") if isinstance(p, dict) else None
        prs.append({"number": _number(p, "pr"), "title": p.get("title", ""), "draft": p.get("draft") is True,
                    "behind": p.get("behind") is True, "merge_unknown": p.get("merge_unknown") is True, "ci": ci if ci in CI_STATES else "none"})
    for i in data["issues"]:
        labels = i.get("labels") if isinstance(i, dict) else None
        issues.append({"number": _number(i, "issue"), "title": i.get("title", ""), "state": i.get("state", "open"),
                       "state_reason": i.get("state_reason"), "created_at": i.get("created_at"),
                       "labels": [x for x in labels if isinstance(x, str)] if isinstance(labels, list) else []})
    return prs, issues, outside


def build_model(tasks_text, data, now):
    now_dt = _ts(now, "now")
    prs, issues, outside = _checked_input(data)
    try:
        graph = tasks.parse(tasks_text, burn_down=False)
    except tasks.TaskFileError as e:
        raise StatusError("docs/tasks.toml: " + "; ".join(e.errors[:3])) from None
    review_pr = {}
    for p in sorted(prs, key=lambda p: p["number"]):
        m = PR_TASK.match(clip(p["title"], 200))
        if m and m.group(1) in graph.by_id:
            review_pr.setdefault(m.group(1), p["number"])
    derived = tasks.derive(graph, issues=issues, in_review=set(review_pr))
    finished = ("done", "dropped")

    milestones, current = [], None
    for m in graph.milestones:
        mine = [t for t in graph.tasks if t.milestone == m]
        done = sum(derived[t.id]["state"] in finished for t in mine)
        milestones.append({"id": m, "done": done, "total": len(mine), "pct": done * 100 // len(mine) if mine else 0})
        if current is None and done < len(mine):
            current = m
    open_tasks = sorted((t for t in graph.tasks if t.milestone == current and derived[t.id]["state"] not in finished),
                        key=lambda t: tasks.order_key(graph, t))
    chain = [{"id": t.id, "title": t.title, "state": derived[t.id]["state"], "unmet": derived[t.id]["unmet"],
              "pr": review_pr.get(t.id)} for t in open_tasks]

    open_prs = sorted((p for p in prs if not p["draft"]), key=lambda p: p["number"])
    queue = [{k: p[k] for k in ("number", "title", "ci", "behind", "merge_unknown")} for p in open_prs]

    blockers, seen = [], set()
    for iss in sorted(issues, key=lambda i: (i["created_at"] or "", i["number"])):
        if str(iss["state"]).lower() != "open" or iss["number"] in seen:
            continue
        kind = next((k for name, k in LABEL_KINDS if name in iss["labels"]), None)
        if kind:
            seen.add(iss["number"])
            age = max((now_dt - _ts(iss["created_at"], f"issue #{iss['number']} created_at")).days, 0)
            blockers.append({"kind": kind, "ref": f"#{iss['number']}", "text": iss["title"], "age": age})
    blockers += [{"kind": "pr-waiting", "ref": f"#{p['number']}", "text": p["title"], "age": None}
                 for p in open_prs if p["ci"] == "passing" and not p["behind"] and not p["merge_unknown"]]
    for c in chain:
        if c["state"] == "blocked":
            more = f" +{len(c['unmet']) - 3}" if len(c["unmet"]) > 3 else ""
            blockers.append({"kind": "task", "ref": c["id"], "text": "waits on " + ", ".join(c["unmet"][:3]) + more,
                             "age": None})
    blockers.sort(key=lambda b: (KIND_ORDER.index(b["kind"]), -(b["age"] or 0)))
    followups = sum(1 for i in issues if str(i["state"]).lower() == "open" and "follow-up" in i["labels"])
    return {
        "generated": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "milestones": milestones, "current": current,
        "chain": chain[:MAX_CHAIN], "chain_more": max(len(chain) - MAX_CHAIN, 0),
        "queue": queue[:MAX_QUEUE], "queue_more": max(len(queue) - MAX_QUEUE, 0), "queue_total": len(queue),
        "blockers": blockers[:MAX_BLOCKERS], "blockers_more": max(len(blockers) - MAX_BLOCKERS, 0),
        "blockers_total": len(blockers), "followups": followups, "outside": outside,
    }


CSS = (
    ".bg{fill:#fff}.fg{fill:#1f2328}.muted{fill:#59636e}.track{fill:#d1d9e0}.bar{fill:#0969da}.full{fill:#1a7f37}"
    ".ok{fill:#1a7f37}.info{fill:#0969da}.warn{fill:#9a6700}.bad{fill:#cf222e}.rule{stroke:#d1d9e0}"
    "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:13px}"
    ".h{font-size:15px;font-weight:600}.t{font-size:20px;font-weight:600}.s{font-size:12px}"
    "@media (prefers-color-scheme: dark){.bg{fill:#0d1117}.fg{fill:#e6edf3}.muted{fill:#9198a1}.track{fill:#30363d}"
    ".bar{fill:#4493f8}.full{fill:#3fb950}.ok{fill:#3fb950}.info{fill:#4493f8}.warn{fill:#d29922}.bad{fill:#f85149}"
    ".rule{stroke:#30363d}}"
)
STATE_CLASS = {"ready": ("ready", "ok"), "in-review": ("in review", "info"), "blocked": ("blocked", "warn"),
               "claimed": ("claimed", "info")}
CI_CLASS = {"passing": "ok", "failing": "bad", "pending": "warn", "none": "muted"}
KIND_TEXT = {"owner-todo": ("owner to-do", "bad"), "blocked": ("blocked", "bad"), "needs-owner": ("needs owner", "warn"),
             "pr-waiting": ("PR to merge", "info"), "task": ("task", "warn")}


def stamp_text(generated):
    return _ts(generated, "generated").strftime("updated %Y-%m-%d %H:%M UTC")


def render_svg(model):
    out, y = [], 0

    def text(x, ypos, content, cls="fg", anchor=None, extra=""):
        a = f' text-anchor="{anchor}"' if anchor else ""
        out.append(f'<text x="{x}" y="{ypos}" class="{cls}"{a}{extra}>{content}</text>')

    def heading(title, note=""):
        nonlocal y
        y += 34
        text(24, y, escape(title), "fg h")
        if note:
            text(WIDTH - 24, y, escape(note), "muted s", "end")
        out.append(f'<line x1="24" y1="{y + 8}" x2="{WIDTH - 24}" y2="{y + 8}" class="rule"/>')
        y += 10

    text(24, 36, "Listicles status", "fg t")
    text(WIDTH - 24, 36, escape(stamp_text(model["generated"])), "muted", "end", f' id="{STAMP_ID}"')
    text(24, 56, "Checked every 30 minutes; the picture is rewritten only when something changes. "
         f"Open follow-ups: {int(model['followups'])}. Outside questions: {int(model['outside'])}.", "muted s")
    y = 56
    heading("Milestones")
    for m in model["milestones"]:
        y += 24
        cur = m["id"] == model["current"]
        text(24, y, label(m["id"], 8), "fg h" if cur else "fg")
        out.append(f'<rect x="90" y="{y - 11}" width="560" height="12" rx="3" class="track"/>')
        if m["total"] and m["done"]:
            width = max(560 * m["done"] // m["total"], 4)
            out.append(f'<rect x="90" y="{y - 11}" width="{width}" height="12" rx="3" '
                       f'class="{"full" if m["done"] == m["total"] else "bar"}"/>')
        note = f"{m['pct']}%  {m['done']}/{m['total']}" if m["total"] else "not planned yet"
        text(666, y, escape(note + ("  current" if cur else "")), "fg" if m["total"] else "muted")

    heading(f"Current chain: {clip(model['current'], 8)}" if model["current"] else "Current chain", "open tasks in order")
    if not model["chain"]:
        y += 22
        text(24, y, "Nothing open.", "muted")
    for c in model["chain"]:
        y += 22
        name, cls = STATE_CLASS.get(c["state"], (c["state"], "muted"))
        if c["pr"]:
            name += f" #{int(c['pr'])}"
        text(24, y, label(name, 20), cls)
        text(150, y, label(c["id"], 10), "fg h")
        text(220, y, label(c["title"]), "fg")
    if model["chain_more"]:
        y += 22
        text(24, y, f"+{int(model['chain_more'])} more in this milestone", "muted")

    heading("Owner queue", "open PRs that are not drafts")
    if not model["queue"]:
        y += 22
        text(24, y, "No open PRs waiting for the owner.", "muted")
    for p in model["queue"]:
        y += 22
        text(24, y, f"#{int(p['number'])}", "fg h")
        text(80, y, label(p["title"]), "fg")
        note = "  behind main" if p["behind"] else "  merge state unknown" if p["merge_unknown"] else ""
        text(WIDTH - 24, y, escape(f"CI {p['ci']}" + note), "warn" if note and p["ci"] == "passing" else CI_CLASS[p["ci"]], "end")
    if model["queue_more"]:
        y += 22
        text(24, y, f"+{int(model['queue_more'])} more", "muted")

    heading("BLOCKERS", f"{int(model['blockers_total'])} open")
    if not model["blockers"]:
        y += 22
        text(24, y, "No blockers.", "ok")
    for b in model["blockers"]:
        y += 22
        name, cls = KIND_TEXT[b["kind"]]
        text(24, y, escape(name), cls)
        text(120, y, label(b["ref"], 10), "fg h")
        text(190, y, label(b["text"]), "fg")
        if b["age"] is not None:
            text(WIDTH - 24, y, f"{int(b['age'])}d", "muted", "end")
    if model["blockers_more"]:
        y += 22
        text(24, y, f"+{int(model['blockers_more'])} more", "muted")
    y += 28
    height = y
    summary = f"{len(model['milestones'])} milestones, {int(model['queue_total'])} PRs waiting, {int(model['blockers_total'])} blockers"
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
            f'role="img" aria-labelledby="ti de"><title id="ti">Listicles status</title><desc id="de">{escape(summary)}</desc>'
            f"<style>{CSS}</style>"
            f'<rect width="{WIDTH}" height="{height}" class="bg"/>')
    return head + "\n" + "\n".join(out) + "\n</svg>\n"


_STAMP = re.compile(rf'(<text [^>]*id="{STAMP_ID}"[^>]*>).*?(</text>)', re.S)


def strip_stamp(svg):
    return _STAMP.sub(r"\1\2", svg, count=1)


def same_ignoring_stamp(a, b):
    return strip_stamp(a) == strip_stamp(b)


def status_json(model):
    return json.dumps({
        "generated_at": model["generated"], "current_milestone": model["current"],
        "milestones": [{"id": m["id"], "done": m["done"], "total": m["total"]} for m in model["milestones"]],
        "owner_queue": model["queue_total"], "blockers": model["blockers_total"], "followups": model["followups"],
        "outside_questions": model["outside"],
    }, indent=2, sort_keys=True) + "\n"


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise StatusError(f"{path}: cannot read ({e.strerror})") from None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the status SVG from docs/tasks.toml and fetched GitHub data.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--tasks", default="docs/tasks.toml")
    r.add_argument("--input", required=True)
    r.add_argument("--now", help="ISO 8601 with zone (default: the current time)")
    r.add_argument("--svg", required=True)
    r.add_argument("--json", required=True)
    s = sub.add_parser("same")
    s.add_argument("old")
    s.add_argument("new")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "same":
            return 0 if same_ignoring_stamp(_read(args.old), _read(args.new)) else 1
        try:
            data = json.loads(_read(args.input))
        except json.JSONDecodeError as e:
            raise StatusError(f"{args.input}: invalid JSON ({e.msg}, line {e.lineno})") from None
        now = args.now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        model = build_model(_read(args.tasks), data, now)
        svg, js = render_svg(model), status_json(model)
        Path(args.svg).write_text(svg, encoding="utf-8")
        Path(args.json).write_text(js, encoding="utf-8")
    except StatusError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
