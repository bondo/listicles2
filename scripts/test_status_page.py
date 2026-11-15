"""Tests for scripts/status_page.py (the status.md detail page). Run: python3 -I scripts/test_status_page.py"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_page  # noqa: E402  # justified: must follow the sys.path insert above
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above
import test_status_visual as fx  # noqa: E402  # justified: shares the TASKS fixture; must follow the sys.path insert above

PAGE_REPO = "o/r"


def page(repo=None, **kw):
    return status_page.render_page(fx.model(**kw), repo)


def mermaid(text):
    m = re.search(r"```mermaid\n(.*?)\n```", text, re.S)
    return m.group(1).splitlines() if m else []


def milestone_section(text, mid):
    parts = re.split(r"(?m)^## ", text)
    return next(p for p in parts if p.startswith(mid + " "))


def with_title(task_id, title):
    old = {"A-02": "Ready thing", "A-O1": "Owner thing"}[task_id]
    return fx.TASKS.replace(f'title = "{old}"', f"title = {json.dumps(title)}")


class Structure(unittest.TestCase):
    def test_has_a_title_an_overview_and_one_section_per_milestone_in_order(self):
        text = page()
        self.assertTrue(text.startswith("# Listicles status detail\n"))
        headings = re.findall(r"(?m)^## (.*)$", text)
        self.assertEqual(headings, ["Overview", "A Alpha name", "B Beta name", "C Gamma name", "Blockers"])
        self.assertIn("| Milestone | Name | Done | Open |", text)
        self.assertRegex(text, r"\| A \| Alpha name \| 2/5 \(40%\) \| 3 \|")

    def test_each_milestone_has_name_purpose_and_a_table_of_all_its_tasks(self):
        sec = milestone_section(page(), "A")
        self.assertIn("Build the alpha.", sec)
        self.assertIn("| Task | Title | Status | Depends on | Who | PR |", sec)
        rows = [r for r in sec.splitlines() if r.startswith("| A-")]
        self.assertEqual([r.split("|")[1].strip() for r in rows], ["A-01", "A-02", "A-03", "A-O1", "A-04"])

    def test_a_long_depends_on_list_is_never_cut_off(self):
        # a burn-down task lists every task of its milestone; clipping the cell hid ids the graph only shows for open tasks
        ids = [f"A-{n:02d}" for n in range(10, 40)]
        extra = "".join(f'\n[[task]]\nid = "{i}"\ntitle = "t"\nmilestone = "A"\nstatus = "done"\nassignee = "implementer"\n'
                        f'risk = "normal"\ndepends_on = []\n' for i in ids)
        extra += ('\n[[task]]\nid = "A-FU"\ntitle = "Burn down"\nmilestone = "A"\nstatus = "todo"\nassignee = "implementer"\n'
                  'risk = "normal"\ndepends_on = ' + json.dumps(ids) + "\n")
        row = next(r for r in page(tasks=fx.TASKS + extra).splitlines() if r.startswith("| A-FU "))
        deps = row.split("|")[4]
        self.assertGreater(len(deps), 100)
        for i in ids:
            self.assertIn(i, deps)
        self.assertNotIn("\u2026", deps)

    def test_rows_show_status_dependencies_and_who(self):
        rows = {r.split("|")[1].strip(): [c.strip() for c in r.strip().strip("|").split("|")]
                for r in page().splitlines() if re.match(r"\| [AB]-", r)}
        self.assertEqual(rows["A-01"][2:], ["done", "none", "implementer", ""])
        self.assertEqual(rows["A-02"][2], "ready")
        self.assertEqual(rows["A-02"][3], "A-01")
        self.assertEqual(rows["A-03"][2], "dropped")
        self.assertEqual(rows["A-O1"][4], "owner")
        self.assertEqual(rows["A-O1"][2], "owner to-do")
        self.assertEqual(rows["A-04"][2:5], ["blocked", "A-O1", "implementer"])
        self.assertEqual(rows["B-01"][3], "all of A")

    def test_linked_prs_are_shown_with_links_only_for_a_valid_repo(self):
        text = page(PAGE_REPO, prs=[fx.pr(20, "A-02: do the thing")])
        self.assertIn("in progress", text)
        self.assertIn("[#20](https://github.com/o/r/issues/20)", text)
        self.assertIn("#20", page(prs=[fx.pr(20, "A-02: do the thing")]))
        self.assertNotIn("](https://github.com/", page(prs=[fx.pr(20, "A-02: do the thing")]))

    def test_merged_pr_numbers_from_the_task_file_are_shown(self):
        text = fx.TASKS.replace('title = "Done thing"', 'title = "Done thing"\npr = 5', 1)
        self.assertIn("| A-01 | Done thing | done | none | implementer | #5 |", page(tasks=text))

    def test_planned_milestones_say_so_and_have_no_table(self):
        sec = milestone_section(page(), "C")
        self.assertIn("Not planned yet.", sec)
        self.assertNotIn("| Task |", sec)

    def test_a_flagged_task_names_what_blocks_it(self):
        text = page(PAGE_REPO, issues=[fx.issue(8, "A-02: waiting for the API", ["blocked"])])
        self.assertRegex(text, r"\| A-02 \| Ready thing \| blocked by \[#8\]\(https://github.com/o/r/issues/8\) \|")

    def test_is_deterministic_and_has_no_clock(self):
        a = status_page.render_page(fx.model(now="2026-11-13T12:00:00Z", issues=[fx.issue(7, "[owner] A-O1: x", ["owner-todo"])]))
        b = status_page.render_page(fx.model(now="2026-12-01T00:00:00Z", issues=[fx.issue(7, "[owner] A-O1: x", ["owner-todo"])]))
        self.assertEqual(a, b)
        self.assertNotIn("2026", a)
        self.assertTrue(a.endswith("\n") and not a.endswith("\n\n"))

    def test_input_order_does_not_change_the_page(self):
        issues = [fx.issue(7, "[owner] A-O1: x", ["owner-todo"]), fx.issue(8, "Waiting", ["blocked"])]
        self.assertEqual(page(issues=issues), page(issues=list(reversed(issues))))


class Blockers(unittest.TestCase):
    def test_lists_every_blocker_not_just_the_picture_cap(self):
        issues = [fx.issue(100 + n, f"Waiting {n}", ["blocked"]) for n in range(status_visual.MAX_BLOCKERS + 6)]
        text = page(issues=issues)
        sec = text.split("## Blockers")[1]
        self.assertEqual(sec.count("Waiting "), status_visual.MAX_BLOCKERS + 6)

    def test_kinds_refs_and_no_ages(self):
        issues = [fx.issue(7, "[owner] A-O1: do it", ["owner-todo"]), fx.issue(8, "Waiting for the API", ["blocked"]),
                  fx.issue(9, "Pick a colour", ["needs-owner"])]
        sec = page(PAGE_REPO, prs=[fx.pr(20)], issues=issues).split("## Blockers")[1]
        for needle in ("owner to-do", "[#7](https://github.com/o/r/issues/7)", "blocked", "needs owner", "PR to merge",
                       "[#20](https://github.com/o/r/issues/20)", "A-04", "waits on A-O1"):
            self.assertIn(needle, sec)
        self.assertNotRegex(sec, r"\b\d+d\b")

    def test_empty_state(self):
        solo = fx.TASKS.split('[[task]]\nid = "A-04"')[0]
        self.assertIn("No blockers.", page(tasks=solo).split("## Blockers")[1])


class DependencyGraph(unittest.TestCase):
    def test_graph_shows_only_open_tasks_and_what_blocks_them(self):
        lines = mermaid(milestone_section(page(), "A"))
        body = "\n".join(lines)
        self.assertEqual(lines[0], "flowchart LR")
        for shown in ("A-02", "A-O1", "A-04"):
            self.assertIn(shown, body)
        for hidden in ("A-01", "A-03"):
            self.assertNotIn(hidden, body)
        ids = dict(re.findall(r'^\s+(n\d+)\["(\S+) ', body, re.M))
        by_label = {v: k for k, v in ids.items()}
        self.assertIn(f"{by_label['A-O1']} --> {by_label['A-04']}", body)

    def test_unmet_dependencies_elsewhere_become_external_nodes(self):
        body = "\n".join(mermaid(milestone_section(page(), "B")))
        self.assertIn("all of A", body)
        self.assertIn("B-01", body)
        self.assertRegex(body, r"-->")

    def test_states_are_classes(self):
        sec = milestone_section(page(prs=[fx.pr(20)]), "A")
        body = "\n".join(mermaid(sec))
        for cls in ("progress", "owner", "blocked"):
            self.assertIn(f":::{cls}", body)
            self.assertIn(f"classDef {cls} ", body)

    def test_a_milestone_with_nothing_open_has_no_graph(self):
        text = fx.TASKS.replace('status = "todo"\nassignee = "implementer"\nrisk = "normal"\ndepends_on = ["milestone:A"]',
                                'status = "done"\nassignee = "implementer"\nrisk = "normal"\ndepends_on = []')
        sec = milestone_section(page(tasks=text), "B")
        self.assertEqual(mermaid(sec), [])
        self.assertIn("Nothing open.", sec)

    def test_every_graph_line_has_a_known_shape_whatever_the_titles_say(self):
        nasty = ['x"]; click n1 href "javascript:alert(1)', "<script>alert(1)</script>", "a|b]c[d{e}(f)", "`code`", "#35; &amp; &quot;",
                 "line\nbreak\r\nand\ttab", "‮evil", "y" * 3000, "end\"\n```\n# injected heading", "%% comment", "--> n9"]
        shape = re.compile(r'^(flowchart LR|\s+n\d+\["[^"\n]*"\](:::\w+)?|\s+n\d+ --> n\d+|\s+classDef \w+ [^\n]*)$')
        for title in nasty:
            with self.subTest(title=title[:25]):
                text = page(tasks=with_title("A-02", title).replace('title = "Waits for the owner"', f"title = {json.dumps(title)}"))
                for line in mermaid(milestone_section(text, "A")):
                    self.assertRegex(line, shape)
                self.assertEqual(text.count("```mermaid"), 2)  # A and B only; the fence cannot be closed early
                self.assertEqual(text.count("```\n"), 2)
                self.assertNotIn("\n# injected heading", text)
                self.assertNotIn("<script", text)

    def test_mermaid_labels_are_clipped(self):
        body = "\n".join(mermaid(milestone_section(page(tasks=with_title("A-02", "z" * 500)), "A")))
        self.assertNotIn("z" * (status_page.MAX_GRAPH_TITLE + 1), body)
        self.assertIn("…", body)

    def test_label_helper_escapes_every_mermaid_special(self):
        out = status_page.mermaid_label('a"b<c>d`e[f]g|h&i#j;k\\l')
        self.assertIsNotNone(re.fullmatch(r'(?:[^&#;"<>`\[\]|\\]|#(?:\d+|[a-z]+);)*', out), out)


class CrossMilestone(unittest.TestCase):
    EXTRA = ('\n[[task]]\nid = "B-02"\ntitle = "Needs an alpha task"\nmilestone = "B"\nstatus = "todo"\nassignee = "implementer"\n'
             'risk = "normal"\ndepends_on = ["A-O1"]\n')

    def node_lines(self, mid):
        return [ln for ln in mermaid(milestone_section(page(tasks=fx.TASKS + self.EXTRA), mid)) if ln.strip().startswith("n") and "[" in ln]

    def test_a_dependency_from_another_milestone_is_a_dashed_grey_ext_box_that_keeps_its_status_word(self):
        line = next(ln for ln in self.node_lines("B") if "A-O1" in ln)
        self.assertTrue(line.endswith(":::ext"), line)
        self.assertIn("(owner to-do)", line)

    def test_a_dependency_inside_the_same_milestone_keeps_its_state_class(self):
        line = next(ln for ln in self.node_lines("A") if "A-O1" in ln)
        self.assertTrue(line.endswith(":::owner"), line)
        self.assertFalse([ln for ln in self.node_lines("A") if ln.endswith(":::ext") and "A-" in ln])

    def test_the_milestone_own_open_tasks_are_never_ext(self):
        for ln in self.node_lines("B"):
            if "B-02" in ln:
                self.assertFalse(ln.endswith(":::ext"), ln)


class Escaping(unittest.TestCase):
    def test_table_cells_cannot_break_the_row_or_inject_markup(self):
        nasty = ["a|b", "<script>alert(1)</script>", "[x](http://evil.example)", "![i](http://evil.example/p.png)", "line\nbreak",
                 "`tick`", "\\|", "<!-- c -->", "&lt;b&gt;", "x" * 3000, "‮evil", "| fake | row |"]
        for title in nasty:
            with self.subTest(title=title[:25]):
                text = page(tasks=with_title("A-02", title))
                row = next(r for r in text.splitlines() if r.startswith("| A-02 |"))
                self.assertEqual(len(re.findall(r"(?<!\\)\|", row)), 7, row)  # six cells
                self.assertNotRegex(row, r"[<>`\[\]]")
                self.assertLessEqual(len(row), 400)

    def test_bare_urls_and_addresses_do_not_autolink(self):
        for title in ("see https://example.com/x now", "http://a.example", "www.example.com/x", "mail me@example.com", "ftp://h/x"):
            with self.subTest(title=title):
                out = status_page.cell(title)
                self.assertNotRegex(out, r"(?i)(https?|ftp)://|\bwww\.|@")
                row = next(r for r in page(tasks=with_title("A-02", title)).splitlines() if r.startswith("| A-02 |"))
                self.assertNotRegex(row, r"(?i)(https?|ftp)://|\bwww\.|[^ ]@[^ ]")

    def test_cell_helper_clips_and_escapes(self):
        self.assertEqual(status_page.cell("a|b"), "a&#124;b")
        out = status_page.cell("x" * 500)
        self.assertEqual(len(out), status_page.MAX_PAGE_TITLE)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(status_page.cell(None), "")

    def test_hostile_blocker_titles_stay_inside_their_list_item(self):
        issues = [fx.issue(8 + n, t, ["blocked"]) for n, t in enumerate(("<b>x</b>\n- injected", "[a](http://evil.example)", "`x`"))]
        sec = page(issues=issues).split("## Blockers")[1]
        self.assertNotRegex(sec, r"[<>`\[\]]")
        self.assertEqual(len([ln for ln in sec.splitlines() if ln.startswith("- ")]), 4)  # 3 issues + task blocker A-04

    def test_a_repo_must_look_like_owner_slash_name(self):
        for bad in ("nope", "a/b/c", "a b/c", "../x", "o/r)](http://evil.example"):
            with self.subTest(bad), self.assertRaises(status_page.PageError):
                status_page.render_page(fx.model(), bad)


if __name__ == "__main__":
    unittest.main()
