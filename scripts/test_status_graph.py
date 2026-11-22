"""Tests for scripts/status_graph.py: the dependency graph of the open tasks (status-graph.svg, task M1-70).
Run: python3 -I scripts/test_status_graph.py"""

import json
import random
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_graph  # noqa: E402  # justified: must follow the sys.path insert above
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

NS = "{http://www.w3.org/2000/svg}"
NOW = "2026-11-22T12:00:00Z"


def task(tid, milestone, status="todo", deps=(), assignee="implementer", title=None):
    ds = ", ".join(f'"{d}"' for d in deps)
    return (f'\n[[task]]\nid = "{tid}"\ntitle = {json.dumps(title or tid + " title")}\nmilestone = "{milestone}"\nstatus = "{status}"\n'
            f'assignee = "{assignee}"\nrisk = "normal"\ndepends_on = [{ds}]\n')


def tasks_text(*rows, milestones=("A", "B", "C", "D")):
    head = "milestones = [" + ", ".join(f'"{m}"' for m in milestones) + "]\n"
    for m in milestones:
        head += f'\n[[milestone]]\nid = "{m}"\ntitle = "{m} name"\npurpose = "Purpose of {m}."\n'
    return head + "".join(rows)


# A-01 done, A-03 dropped; A-O1 -> A-04 -> A-05 -> B-01 -> B-02, plus the shortcuts A-O1 -> A-05 and A-05 -> B-02
# (transitive) and A-02 -> B-02 (not transitive). Milestone C has no tasks yet, milestone D is all done.
ROWS = (
    task("A-01", "A", "done"),
    task("A-02", "A", deps=["A-01"]),
    task("A-03", "A", "dropped"),
    task("A-O1", "A", assignee="owner"),
    task("A-04", "A", deps=["A-O1", "A-03"]),
    task("A-05", "A", deps=["A-04", "A-O1"]),
    task("B-01", "B", deps=["A-05", "milestone:A"]),
    task("B-02", "B", deps=["A-02", "B-01", "A-05"]),
    task("D-01", "D", "done"),
)
TASKS = tasks_text(*ROWS)
OPEN = ["A-02", "A-O1", "A-04", "A-05", "B-01", "B-02"]


def model(text=TASKS, prs=None, issues=None):
    return status_visual.build_model(text, {"prs": prs or [], "issues": issues or []}, NOW)


def svg_of(text=TASKS, **kw):
    return status_graph.render_graph_svg(model(text, **kw))


def nodes(svg):
    root = ET.fromstring(svg)
    return {g.get("data-id"): g for g in root.iter(NS + "g") if g.get("data-id")}


def edges(svg):
    root = ET.fromstring(svg)
    return sorted((p.get("data-from"), p.get("data-to")) for p in root.iter(NS + "path") if p.get("data-from"))


def texts(svg):
    return [" ".join("".join(el.itertext()).split()) for el in ET.fromstring(svg).iter(NS + "text")]


def box(g):
    r = g.find(NS + "rect")
    return float(r.get("x")), float(r.get("y")), float(r.get("width")), float(r.get("height"))


class Nodes(unittest.TestCase):
    def test_only_open_tasks_are_nodes(self):
        self.assertEqual(sorted(nodes(svg_of())), sorted(OPEN))

    def test_done_dropped_and_planned_tasks_are_never_nodes(self):
        found = nodes(svg_of())
        for gone in ("A-01", "A-03", "D-01"):
            self.assertNotIn(gone, found)

    def test_a_task_becoming_done_removes_its_node_and_its_edges(self):
        text = tasks_text(*(r.replace('id = "A-04"\ntitle = "A-04 title"\nmilestone = "A"\nstatus = "todo"',
                                      'id = "A-04"\ntitle = "A-04 title"\nmilestone = "A"\nstatus = "done"') for r in ROWS))
        svg = svg_of(text)
        self.assertNotIn("A-04", nodes(svg))
        self.assertTrue(all("A-04" not in e for e in edges(svg)))

    def test_nodes_carry_their_derived_state(self):
        found = nodes(svg_of(prs=[{"number": 9, "title": "A-02: in review", "draft": True, "ci": "none"}]))
        self.assertEqual({k: g.get("data-state") for k, g in found.items()},
                         {"A-02": "review", "A-O1": "owner", "A-04": "blocked", "A-05": "blocked", "B-01": "blocked", "B-02": "blocked"})

    def test_a_blocked_label_makes_a_ready_task_blocked(self):
        text = tasks_text(task("A-01", "A"), milestones=("A",))
        stuck = {"number": 5, "title": "A-01: stuck", "state": "open", "labels": ["blocked"], "created_at": "2026-11-20T00:00:00Z"}
        found = nodes(svg_of(text, issues=[stuck]))
        self.assertEqual(found["A-01"].get("data-state"), "blocked")
        self.assertEqual(nodes(svg_of(text))["A-01"].get("data-state"), "ready")

    def test_the_full_title_is_a_tooltip_and_the_id_is_the_label(self):
        g = nodes(svg_of(tasks_text(task("A-01", "A", title="Hello & <b>bye</b>"), milestones=("A",))))["A-01"]
        self.assertEqual(g.find(NS + "title").text, "A-01: Hello & <b>bye</b> (ready)")
        self.assertEqual(" ".join("".join(g.find(NS + "text").itertext()).split()), "A-01")


class Edges(unittest.TestCase):
    def test_edges_follow_depends_on_among_open_tasks(self):
        self.assertIn(("A-O1", "A-04"), edges(svg_of()))
        self.assertIn(("A-02", "B-02"), edges(svg_of()))

    def test_the_direction_is_dependency_to_dependent(self):
        found = edges(svg_of())
        self.assertNotIn(("A-04", "A-O1"), found)
        self.assertNotIn(("B-02", "A-02"), found)

    def test_transitive_edges_are_dropped(self):
        found = edges(svg_of())
        self.assertEqual(found, sorted([("A-O1", "A-04"), ("A-04", "A-05"), ("A-05", "B-01"), ("A-02", "B-02"), ("B-01", "B-02")]))
        self.assertNotIn(("A-O1", "A-05"), found)
        self.assertNotIn(("A-05", "B-02"), found)

    def test_dependencies_outside_the_open_set_are_not_drawn(self):
        found = edges(svg_of())
        for src, dst in found:
            self.assertIn(src, OPEN)
            self.assertIn(dst, OPEN)

    def test_every_edge_ends_at_a_node_that_exists(self):
        svg = svg_of()
        for a, b in edges(svg):
            self.assertIn(a, nodes(svg))
            self.assertIn(b, nodes(svg))

    def test_open_graph_counts_what_it_leaves_out(self):
        g = status_graph.open_graph(model())
        self.assertEqual(g["dropped_transitive"], 2)
        self.assertEqual(g["outside_done"], 2)  # A-02 -> A-01 (done), A-04 -> A-03 (dropped)
        self.assertEqual(g["outside_milestone"], 1)  # B-01 waits on all of A
        self.assertEqual(sorted(g["edges"]), sorted([("A-O1", "A-04"), ("A-04", "A-05"), ("A-05", "B-01"), ("A-02", "B-02"), ("B-01", "B-02")]))

    def test_a_milestone_dependency_is_not_a_node_or_an_edge(self):
        svg = svg_of()
        self.assertFalse([k for k in nodes(svg) if k.startswith("milestone")])
        self.assertFalse([e for e in edges(svg) if any(x.startswith("milestone") for x in e)])


def closure(edges_):
    succ = {}
    for a, b in edges_:
        succ.setdefault(a, set()).add(b)
    seen = {}

    def reach(n):
        if n not in seen:
            seen[n] = set()
            for m in succ.get(n, ()):
                seen[n] |= {m} | reach(m)
        return seen[n]

    return {n: reach(n) for n in {x for e in edges_ for x in e}}


class Reduce(unittest.TestCase):
    def test_a_shortcut_over_a_path_is_removed(self):
        self.assertEqual(status_graph.reduce([("a", "b"), ("b", "c"), ("a", "c")]), ([("a", "b"), ("b", "c")], 1))

    def test_a_diamond_keeps_all_four_edges(self):
        e = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]
        self.assertEqual(status_graph.reduce(e), (e, 0))

    def test_a_long_shortcut_is_removed(self):
        kept, dropped = status_graph.reduce([("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")])
        self.assertEqual((kept, dropped), ([("a", "b"), ("b", "c"), ("c", "d")], 1))

    def test_duplicates_collapse_and_the_empty_graph_is_empty(self):
        self.assertEqual(status_graph.reduce([("a", "b"), ("a", "b")]), ([("a", "b")], 0))
        self.assertEqual(status_graph.reduce([]), ([], 0))

    def test_random_dags_keep_reachability_and_have_no_redundant_edge(self):
        rng = random.Random(70)
        for _ in range(60):
            n = rng.randint(2, 14)
            e = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.3]
            kept, dropped = status_graph.reduce(e)
            self.assertEqual(closure(kept), closure(e))
            self.assertEqual(len(kept) + dropped, len(e))
            self.assertTrue(set(kept) <= set(e))
            for a, b in kept:  # minimal: without this edge the endpoint is no longer reachable
                rest = [x for x in kept if x != (a, b)]
                self.assertNotIn(b, closure(rest).get(a, set()))


class Layout(unittest.TestCase):
    def test_a_dependent_sits_to_the_right_of_its_dependency(self):
        found = nodes(svg_of())
        for a, b in edges(svg_of()):
            self.assertLess(box(found[a])[0] + box(found[a])[2], box(found[b])[0], (a, b))

    def test_no_two_nodes_overlap(self):
        boxes = [box(g) for g in nodes(svg_of()).values()]
        for i, (x1, y1, w1, h1) in enumerate(boxes):
            for x2, y2, w2, h2 in boxes[i + 1:]:
                self.assertTrue(x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)

    def test_everything_is_inside_the_canvas(self):
        svg = svg_of()
        root = ET.fromstring(svg)
        width, height = float(root.get("width")), float(root.get("height"))
        self.assertEqual(root.get("viewBox"), f"0 0 {root.get('width')} {root.get('height')}")
        for x, y, w, h in (box(g) for g in nodes(svg).values()):
            self.assertTrue(x >= 0 and x + w <= width and y >= 0 and y + h <= height)

    def test_every_node_sits_inside_a_milestone_band(self):
        svg = svg_of()
        bands = [(float(r.get("x")), float(r.get("y")), float(r.get("width")), float(r.get("height")))
                 for r in ET.fromstring(svg).iter(NS + "rect") if r.get("class") == "card"]
        self.assertEqual(len(bands), 2)
        for tid, g in nodes(svg).items():
            x, y, w, h = box(g)
            self.assertTrue(any(bx <= x and x + w <= bx + bw and by <= y and y + h <= by + bh for bx, by, bw, bh in bands), tid)

    def test_a_deep_graph_still_fits_its_bands(self):
        rows = [task(f"A-{i:02d}", "A", deps=[f"A-{i - 1:02d}"] if i > 1 else []) for i in range(1, 14)]
        svg = svg_of(tasks_text(*rows, milestones=("A",)))
        band = next(r for r in ET.fromstring(svg).iter(NS + "rect") if r.get("class") == "card")
        right = float(band.get("x")) + float(band.get("width"))
        for g in nodes(svg).values():
            self.assertLessEqual(box(g)[0] + box(g)[2], right)

    def test_the_text_fits_the_canvas_even_for_a_one_column_graph(self):
        svg = svg_of(tasks_text(task("A-01", "A"), milestones=("A",)))
        root = ET.fromstring(svg)
        width = float(root.get("width"))
        for el in root.iter(NS + "text"):
            content = "".join(el.itertext())
            self.assertLessEqual(float(el.get("x")) + status_visual.text_width(content) * 6.6, width, content)

    def test_nodes_are_grouped_into_one_band_per_milestone(self):
        found = nodes(svg_of())
        a = [box(found[k]) for k in ("A-02", "A-O1", "A-04", "A-05")]
        b = [box(found[k]) for k in ("B-01", "B-02")]
        self.assertLess(max(y + h for _, y, _, h in a), min(y for _, y, _, _ in b))

    def test_layers_follow_the_longest_path(self):
        ls = status_graph.layers(["a", "b", "c", "d"], [("a", "b"), ("b", "c"), ("a", "c"), ("a", "d")])
        self.assertEqual(ls, {"a": 0, "b": 1, "c": 2, "d": 1})

    def test_is_deterministic(self):
        self.assertEqual(svg_of(), svg_of())

    def test_a_bigger_graph_is_laid_out_without_overlap(self):
        rng = random.Random(7)
        rows = [task(f"A-{i:02d}", "A", deps=[f"A-{j:02d}" for j in range(1, i) if rng.random() < 0.15]) for i in range(1, 40)]
        found = nodes(svg_of(tasks_text(*rows, milestones=("A",))))
        self.assertEqual(len(found), 39)
        boxes = [box(g) for g in found.values()]
        for i, (x1, y1, w1, h1) in enumerate(boxes):
            for x2, y2, w2, h2 in boxes[i + 1:]:
                self.assertTrue(x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)


class Labels(unittest.TestCase):
    def test_each_milestone_band_says_how_many_tasks_are_done(self):
        joined = "\n".join(texts(svg_of()))
        self.assertIn("A A name: 2/6 done, 4 open", joined)  # A-01 done and A-03 dropped count as done
        self.assertIn("B B name: 0/2 done, 2 open", joined)

    def test_finished_and_planned_milestones_are_summarised_not_drawn(self):
        joined = "\n".join(texts(svg_of()))
        self.assertIn("All done: D 1/1", joined)
        self.assertIn("Not planned yet: C", joined)
        self.assertNotIn("D D name", joined)

    def test_the_legend_names_every_state_and_says_what_is_left_out(self):
        joined = "\n".join(texts(svg_of()))
        for word in ("ready", "in progress", "blocked", "owner to-do"):
            self.assertIn(word, joined)
        self.assertIn("transitive", joined)
        self.assertIn("2 transitive arrows hidden", joined)
        self.assertIn("2 dependencies on done or dropped tasks", joined)
        self.assertIn("1 on a whole milestone", joined)
        self.assertIn("dependency to dependent", joined)

    def test_the_title_and_description_are_accessible(self):
        root = ET.fromstring(svg_of())
        self.assertEqual(root.get("role"), "img")
        self.assertEqual(root.find(NS + "title").text, "Open tasks and their dependencies")
        desc = root.find(NS + "desc").text
        self.assertIn("6 open tasks", desc)
        self.assertIn("5 dependencies", desc)

    def test_there_is_no_clock_in_the_picture(self):
        self.assertNotRegex(svg_of(), r"20\d\d-\d\d-\d\d|updated")


class Empty(unittest.TestCase):
    ALL_DONE = tasks_text(task("A-01", "A", "done"), task("B-01", "B", "dropped"), milestones=("A", "B"))

    def test_an_empty_graph_is_a_valid_svg_with_a_message(self):
        svg = svg_of(self.ALL_DONE)
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, NS + "svg")
        self.assertEqual(nodes(svg), {})
        self.assertEqual(edges(svg), [])
        self.assertIn("No open tasks.", texts(svg))
        self.assertIn("All done: A 1/1; B 1/1", "\n".join(texts(svg)))
        self.assertGreater(float(root.get("height")), 0)

    def test_a_graph_without_any_task_is_valid_too(self):
        svg = svg_of(tasks_text(milestones=("A",)))
        self.assertIn("No open tasks.", texts(svg))
        self.assertIn("Not planned yet: A", "\n".join(texts(svg)))

    def test_open_tasks_without_dependencies_have_no_edges(self):
        svg = svg_of(tasks_text(task("A-01", "A"), task("A-02", "A"), milestones=("A",)))
        self.assertEqual(sorted(nodes(svg)), ["A-01", "A-02"])
        self.assertEqual(edges(svg), [])


class Safety(unittest.TestCase):
    def test_hostile_text_is_escaped_clipped_and_well_formed(self):
        evil = '</title><script>alert(1)</script>"&\x00‮' + "x" * 300
        rows = (task("A-01", "A", title=evil),)
        svg = svg_of(tasks_text(*rows, milestones=("A",)))
        ET.fromstring(svg)
        self.assertNotIn("<script", svg)
        self.assertNotIn("‮", svg)
        self.assertLess(len(nodes(svg)["A-01"].find(NS + "title").text), 200)

    def test_theme_classes_only_and_no_active_or_external_content(self):
        svg = svg_of()
        self.assertNotRegex(svg, r'fill="#|stroke="#|style="')
        for bad in ("<script", "<foreignObject", "<image", "href=", "javascript:", "@import", "url(http"):
            self.assertNotIn(bad, svg)
        self.assertIn("prefers-color-scheme: dark", svg)

    def test_every_text_has_a_fill_class_so_dark_mode_is_legible(self):
        for m in re.finditer(r"<text [^>]*>", svg_of()):
            self.assertRegex(m.group(0), r'class="[^"]*\b(fg|muted|ok|info|warn|bad)\b')

    def test_node_text_has_enough_contrast_on_every_node_fill_in_both_schemes(self):
        css = status_graph.CSS
        light, dark = css.split("@media (prefers-color-scheme: dark){")

        def fills(block, prop):
            return {m.group(1): m.group(2) for m in re.finditer(r"\.([\w-]+)\{[^}]*?\b" + prop + r":(#[0-9a-f]{6})", block)}

        def lum(h):
            ch = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
            return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]

        def ratio(a, b):
            hi, lo = sorted((lum(a), lum(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)

        base = fills(light, "fill")
        for name, scheme in (("light", base), ("dark", dict(base, **fills(dark, "fill")))):
            for state in ("ready", "review", "blocked", "owner"):
                with self.subTest(scheme=name, state=state):
                    self.assertGreaterEqual(ratio(scheme["fg"], scheme[f"nd-{state}"]), 4.5)
            for bg in ("bg", "card"):
                for fg in ("fg", "muted"):
                    with self.subTest(scheme=name, bg=bg, fg=fg):
                        self.assertGreaterEqual(ratio(scheme[fg], scheme[bg]), 4.5)

    def test_states_differ_by_shape_and_by_colour(self):
        found = nodes(svg_of(prs=[{"number": 9, "title": "A-02: x", "draft": False, "ci": "none"}]))
        shapes = {s: [el.get("class") for el in found[k].iter() if "mk-" in (el.get("class") or "")]
                  for s, k in (("review", "A-02"), ("owner", "A-O1"), ("blocked", "A-04"))}
        self.assertEqual(shapes, {"review": ["info mk-progress"], "owner": ["bad mk-owner"], "blocked": ["warn mk-blocked"]})
        self.assertEqual(len({found[k].find(NS + "rect").get("class") for k in ("A-02", "A-O1", "A-04")}), 3)


class Cli(unittest.TestCase):
    SCRIPT = Path(__file__).resolve().parent / "status_visual.py"

    def render(self, d, *extra):
        (d / "t.toml").write_text(TASKS)
        (d / "in.json").write_text('{"prs": [], "issues": []}')
        return subprocess.run([sys.executable, "-I", str(self.SCRIPT), "render", "--tasks", str(d / "t.toml"), "--input", str(d / "in.json"),
                               "--now", NOW, "--svg", str(d / "s.svg"), "--json", str(d / "s.json"), *extra], capture_output=True, text=True)

    def test_render_writes_the_graph_next_to_the_svg_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.render(Path(d))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(nodes((Path(d) / "status-graph.svg").read_text())), sorted(OPEN))
            self.assertTrue((Path(d) / "s.svg").read_text().startswith("<svg"))  # the picture itself is unchanged

    def test_graph_option_overrides_the_path(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.render(Path(d), "--graph", str(Path(d) / "g.svg"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((Path(d) / "g.svg").exists())
            self.assertFalse((Path(d) / "status-graph.svg").exists())

    def test_the_status_picture_itself_has_no_graph_in_it(self):
        self.assertNotIn("Open tasks and their dependencies", status_visual.render_svg(model()))


if __name__ == "__main__":
    unittest.main()
