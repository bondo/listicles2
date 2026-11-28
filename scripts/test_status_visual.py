"""Tests for scripts/status_visual.py (renderer) and scripts/status_fetch.py (API fetch, with a fake API).
Run: python3 -I scripts/test_status_visual.py"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_fetch  # noqa: E402  # justified: must follow the sys.path insert above
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

SCRIPT = Path(__file__).resolve().parent / "status_visual.py"
NOW = "2026-11-13T12:00:00Z"

TASKS = """
milestones = ["A", "B", "C"]

[[milestone]]
id = "A"
title = "Alpha name"
purpose = "Build the alpha."

[[milestone]]
id = "B"
title = "Beta name"
purpose = "Build the beta."

[[milestone]]
id = "C"
title = "Gamma name"
purpose = "Build the gamma."

[[task]]
id = "A-01"
title = "Done thing"
milestone = "A"
status = "done"
assignee = "implementer"
risk = "normal"
depends_on = []

[[task]]
id = "A-02"
title = "Ready thing"
milestone = "A"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["A-01"]

[[task]]
id = "A-03"
title = "Dropped thing"
milestone = "A"
status = "dropped"
assignee = "implementer"
risk = "normal"
depends_on = []

[[task]]
id = "A-O1"
title = "Owner thing"
milestone = "A"
status = "todo"
assignee = "owner"
risk = "normal"
depends_on = []

[[task]]
id = "A-04"
title = "Waits for the owner"
milestone = "A"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["A-O1"]

[[task]]
id = "B-01"
title = "Next milestone"
milestone = "B"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["milestone:A"]
"""


def pr(number, title="A-02: do the thing", draft=False, ci="passing", behind=False, merge_unknown=False):
    return {"number": number, "title": title, "draft": draft, "ci": ci, "behind": behind, "merge_unknown": merge_unknown}


def issue(number, title, labels, created="2026-11-10T12:00:00Z", state="open", reason=None):
    return {"number": number, "title": title, "state": state, "state_reason": reason,
            "created_at": created, "labels": labels}


def data(prs=None, issues=None):
    return {"prs": prs if prs is not None else [], "issues": issues if issues is not None else []}


def model(prs=None, issues=None, now=NOW, tasks=TASKS):
    return status_visual.build_model(tasks, data(prs, issues), now)


def texts(svg):
    """All text content of the <text> elements; parsing also proves the SVG is well-formed XML."""
    root = ET.fromstring(svg)
    return [" ".join("".join(el.itertext()).split()) for el in root.iter("{http://www.w3.org/2000/svg}text")]


class Clip(unittest.TestCase):
    def test_strips_control_bidi_and_invisible_characters(self):
        self.assertEqual(status_visual.clip("a\x00b\x1b[31mc‮d​e﻿", 50), "ab[31mcde")

    def test_collapses_whitespace_and_newlines(self):
        self.assertEqual(status_visual.clip("a \n\t b   c", 50), "a b c")

    def test_truncates_with_ellipsis_to_the_limit(self):
        out = status_visual.clip("x" * 500, 20)
        self.assertEqual(len(out), 20)
        self.assertTrue(out.endswith("…"))

    def test_wide_characters_count_double(self):
        out = status_visual.clip("\u6f22" * 50, 20)
        self.assertLessEqual(status_visual.text_width(out), 20)
        self.assertTrue(out.endswith("\u2026"))
        self.assertEqual(status_visual.text_width("a\u6f22\uff21"), 5)

    def test_wide_latin_letters_count_double(self):
        self.assertEqual(status_visual.text_width("WMwm@"), 10)
        self.assertEqual(status_visual.text_width("abc"), 3)
        out = status_visual.clip("W" * 100, 20)
        self.assertLessEqual(status_visual.text_width(out), 20)

    def test_short_text_is_untouched(self):
        self.assertEqual(status_visual.clip("short", 20), "short")

    def test_non_strings_become_empty(self):
        self.assertEqual(status_visual.clip(None, 20), "")
        self.assertEqual(status_visual.clip(12, 20), "")

    def test_lone_surrogates_are_removed(self):
        self.assertEqual(status_visual.clip("a\ud800b", 20), "ab")


class TaskIdPatterns(unittest.TestCase):
    def test_pr_and_flag_titles_take_two_or_three_digit_task_ids(self):
        for title, want in (("M1-99: x", "M1-99"), ("M1-100: x", "M1-100"), ("[owner] M1-999: x", "M1-999"), ("M1-O2: x", "M1-O2"), ("M1-FU: x", "M1-FU")):
            m = status_visual.FLAG_TASK.match(title)
            self.assertIsNotNone(m, title)
            self.assertEqual(m.group(1), want)
        for title in ("M1-1: x", "M1-1000: x", "M1-ABC: x", "M1-100 x"):
            self.assertIsNone(status_visual.PR_TASK.match(title), title)
        self.assertEqual(status_visual.PR_TASK.match("M1-100: x").group(1), "M1-100")


class BuildModel(unittest.TestCase):
    def test_milestone_progress_counts_dropped_as_done(self):
        ms = {m["id"]: m for m in model()["milestones"]}
        self.assertEqual((ms["A"]["done"], ms["A"]["total"], ms["A"]["pct"]), (2, 5, 40))
        self.assertEqual((ms["B"]["done"], ms["B"]["total"], ms["B"]["pct"]), (0, 1, 0))
        self.assertEqual((ms["C"]["done"], ms["C"]["total"], ms["C"]["pct"]), (0, 0, 0))

    def test_current_milestone_is_the_first_unfinished_one(self):
        self.assertEqual(model()["current"], "A")

    def test_milestones_carry_their_human_friendly_names(self):
        ms = {m["id"]: m for m in model()["milestones"]}
        self.assertEqual((ms["A"]["title"], ms["A"]["purpose"]), ("Alpha name", "Build the alpha."))
        self.assertEqual(ms["C"]["title"], "Gamma name")
        self.assertEqual([m["planned"] for m in model()["milestones"]], [False, False, True])

    def test_tasks_of_a_milestone_are_listed_in_order_with_a_visual_state(self):
        ms = {m["id"]: m for m in model()["milestones"]}
        tasks_a = {t["id"]: t for t in ms["A"]["tasks"]}
        self.assertEqual([t["id"] for t in ms["A"]["tasks"]], ["A-01", "A-02", "A-03", "A-O1", "A-04"])
        self.assertEqual({k: v["state"] for k, v in tasks_a.items()},
                         {"A-01": "done", "A-02": "ready", "A-03": "dropped", "A-O1": "owner", "A-04": "blocked"})
        self.assertEqual(tasks_a["A-04"]["unmet"], [{"ref": "A-O1", "owner": True, "milestone": False}])
        self.assertEqual(tasks_a["A-04"]["deps"], ["A-O1"])
        self.assertEqual(tasks_a["A-02"]["title"], "Ready thing")
        self.assertEqual(tasks_a["A-O1"]["assignee"], "owner")

    def test_a_burn_down_task_lists_its_implied_dependencies_as_deps(self):
        # owner decision 7242447401 item 2: the Mx-FU line of the file is empty, the page still draws its edges
        fu = ('\n[[task]]\nid = "A-FU"\ntitle = "Burn down"\nmilestone = "A"\nstatus = "todo"\nassignee = "implementer"\n'
              'risk = "normal"\ndepends_on = []\n')
        ms = {m["id"]: m for m in model(tasks=TASKS + fu)["milestones"]}
        row = next(t for t in ms["A"]["tasks"] if t["id"] == "A-FU")
        self.assertEqual(row["deps"], ["A-01", "A-02", "A-03", "A-04"])
        self.assertEqual(row["unmet"], [{"ref": r, "owner": False, "milestone": False} for r in ("A-02", "A-04")])

    def test_tasks_carry_the_pr_number_from_the_task_file(self):
        text = TASKS.replace('title = "Done thing"', 'title = "Done thing"\npr = 5', 1)
        tasks_a = {t["id"]: t for t in model(tasks=text)["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-01"]["toml_pr"], tasks_a["A-02"]["toml_pr"]), (5, None))

    def test_all_blockers_are_kept_beyond_the_picture_cap(self):
        issues = [issue(100 + n, f"Waiting {n}", ["blocked"]) for n in range(status_visual.MAX_BLOCKERS + 6)]
        m = model(issues=issues)
        self.assertEqual(len(m["blockers"]), status_visual.MAX_BLOCKERS)
        self.assertEqual(len(m["all_blockers"]), m["blockers_total"])
        self.assertEqual(m["blockers_total"], status_visual.MAX_BLOCKERS + 6 + 1)  # plus the task blocker A-04

    def test_milestone_dependencies_are_shown_as_a_milestone(self):
        b01 = model()["milestones"][1]["tasks"][0]
        self.assertEqual(b01["state"], "blocked")
        self.assertEqual(b01["unmet"], [{"ref": "milestone:A", "owner": False, "milestone": True}])

    def test_open_pr_titled_with_a_task_id_puts_the_task_in_progress(self):
        tasks_a = {t["id"]: t for t in model(prs=[pr(20, "A-02: do the thing")])["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-02"]["state"], tasks_a["A-02"]["pr"]), ("review", 20))

    def test_a_draft_or_other_title_still_counts_only_by_leading_task_id(self):
        tasks_a = {t["id"]: t for t in model(prs=[pr(20, "mention A-02 in passing")])["milestones"][0]["tasks"]}
        self.assertEqual(tasks_a["A-02"]["state"], "ready")

    def test_closed_completed_owner_issue_finishes_the_owner_task(self):
        closed = issue(7, "[owner] A-O1: do it", ["owner-todo"], state="closed", reason="completed")
        tasks_a = {t["id"]: t for t in model(issues=[closed])["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-O1"]["state"], tasks_a["A-04"]["state"]), ("done", "ready"))

    def test_an_open_blocked_labelled_issue_or_pr_naming_the_task_flags_it(self):
        flagged = issue(8, "A-02: waiting for the API", ["blocked"])
        tasks_a = {t["id"]: t for t in model(issues=[flagged])["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-02"]["state"], tasks_a["A-02"]["flag"]), ("blocked", "#8"))
        labelled_pr = dict(pr(21, "A-02: do the thing"), labels=["blocked"])
        tasks_a = {t["id"]: t for t in model(prs=[labelled_pr])["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-02"]["state"], tasks_a["A-02"]["flag"]), ("blocked", "#21"))

    def test_blocked_labels_on_closed_or_unrelated_items_flag_nothing(self):
        items = [issue(8, "A-02: x", ["blocked"], state="closed", reason="completed"), issue(9, "no task id", ["blocked"]),
                 issue(10, "A-02: y", ["follow-up"]), issue(11, "Z-99: unknown task", ["blocked"])]
        tasks_a = {t["id"]: t for t in model(issues=items)["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-02"]["state"], tasks_a["A-02"]["flag"]), ("ready", None))

    def test_an_owner_task_stays_an_owner_task_even_when_it_waits(self):
        text = TASKS.replace('id = "A-O1"\ntitle = "Owner thing"\nmilestone = "A"\nstatus = "todo"\nassignee = "owner"\nrisk = "normal"\ndepends_on = []',
                             'id = "A-O1"\ntitle = "Owner thing"\nmilestone = "A"\nstatus = "todo"\nassignee = "owner"\nrisk = "normal"\ndepends_on = ["A-02"]')
        tasks_a = {t["id"]: t for t in model(tasks=text)["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-O1"]["state"], [u["ref"] for u in tasks_a["A-O1"]["unmet"]]), ("owner", ["A-02"]))

    def test_owner_queue_is_non_draft_prs_only(self):
        m = model(prs=[pr(20), pr(21, draft=True, ci="pending"), pr(22, ci="failing", behind=True)])
        self.assertEqual([p["number"] for p in m["queue"]], [20, 22])
        self.assertEqual((m["queue"][1]["ci"], m["queue"][1]["behind"]), ("failing", True))

    def test_blockers_cover_tasks_issues_labels_and_prs_waiting(self):
        issues = [
            issue(7, "[owner] A-O1: do it", ["owner-todo"]),
            issue(8, "Waiting for the API", ["blocked"]),
            issue(9, "Pick a colour", ["needs-owner", "idea"]),
            issue(10, "Some follow-up", ["follow-up"]),
            issue(11, "Old owner thing", ["owner-todo"], state="closed", reason="completed"),
            issue(12, "Unlabelled", []),
        ]
        m = model(prs=[pr(20), pr(21, draft=True), pr(22, ci="failing"), pr(23, behind=True)], issues=issues)
        by_kind = {}
        for b in m["blockers"]:
            by_kind.setdefault(b["kind"], []).append(b)
        self.assertEqual([b["ref"] for b in by_kind["task"]], ["A-04"])
        self.assertIn("A-O1", by_kind["task"][0]["text"])
        self.assertEqual([(b["ref"], b["age"]) for b in by_kind["owner-todo"]], [("#7", 3)])
        self.assertEqual([b["ref"] for b in by_kind["blocked"]], ["#8"])
        self.assertEqual([b["ref"] for b in by_kind["needs-owner"]], ["#9"])
        self.assertEqual([b["ref"] for b in by_kind["pr-waiting"]], ["#20"])
        self.assertEqual(m["followups"], 1)
        refs = [b["ref"] for b in m["blockers"]]
        for absent in ("#10", "#11", "#12", "#21", "#22", "#23"):
            self.assertNotIn(absent, refs)

    def test_no_blockers_when_nothing_waits(self):
        solo = TASKS.split("[[task]]\nid = \"A-04\"")[0]
        m = model(tasks=solo)
        self.assertEqual([b for b in m["blockers"] if b["kind"] == "task"], [])

    def test_blocked_tasks_of_other_milestones_are_not_blockers(self):
        self.assertNotIn("B-01", [b["ref"] for b in model()["blockers"]])

    def test_bad_task_file_raises(self):
        with self.assertRaises(status_visual.StatusError):
            status_visual.build_model("milestones = 3", data(), NOW)

    def test_milestone_without_a_title_raises(self):
        text = TASKS.replace('title = "Gamma name"\n', "")
        with self.assertRaisesRegex(status_visual.StatusError, "has no title|missing"):
            status_visual.build_model(text, data(), NOW)

    def test_unknown_milestone_table_raises(self):
        with self.assertRaisesRegex(status_visual.StatusError, "unknown milestone"):
            status_visual.build_model(TASKS + '\n[[milestone]]\nid = "Z"\ntitle = "t"\npurpose = "p"\n', data(), NOW)

    def test_dependency_cycles_still_raise(self):
        text = TASKS.replace('risk = "normal"\ndepends_on = []\n\n[[task]]\nid = "A-04"', 'risk = "normal"\ndepends_on = ["A-04"]\n\n[[task]]\nid = "A-04"')
        with self.assertRaisesRegex(status_visual.StatusError, "cycle"):
            status_visual.build_model(text, data(), NOW)

    def test_pr_labels_are_optional_and_must_be_strings(self):
        d = data(prs=[dict(pr(20), labels=["blocked", 7, None])])
        self.assertEqual(status_visual.build_model(TASKS, d, NOW)["queue"][0]["number"], 20)

    def test_bad_input_shape_raises(self):
        with self.assertRaises(status_visual.StatusError):
            status_visual.build_model(TASKS, {"prs": "nope", "issues": []}, NOW)
        with self.assertRaises(status_visual.StatusError):
            status_visual.build_model(TASKS, [], NOW)

    def test_bad_now_raises(self):
        with self.assertRaises(status_visual.StatusError):
            status_visual.build_model(TASKS, data(), "yesterday")


class RenderSvg(unittest.TestCase):
    def svg(self, **kw):
        return status_visual.render_svg(model(**kw))

    def test_shows_milestones_chain_queue_blockers_and_stamp(self):
        svg = self.svg(prs=[pr(20)], issues=[issue(7, "[owner] A-O1: do it", ["owner-todo"])])
        joined = "\n".join(texts(svg))
        for needle in ("40%", "A-02", "A-04", "#20", "BLOCKERS", "#7", "3d", "2026-11-13 12:00 UTC", "Owner queue"):
            self.assertIn(needle, joined)

    def test_each_milestone_is_a_card_with_id_prefixed_name_purpose_and_counts(self):
        lines = texts(self.svg())
        for needle in ("A Alpha name", "Build the alpha.", "40% 2/5", "B Beta name", "0% 0/1", "C Gamma name", "Build the gamma."):
            self.assertIn(needle, lines)
        self.assertEqual(sum(1 for line in lines if line.endswith("current")), 1)
        self.assertIn("ready", lines)  # A-02 has no PR

    def test_a_milestone_without_tasks_shows_its_planned_name_and_not_planned_yet(self):
        lines = texts(self.svg())
        self.assertEqual(lines.count("not planned yet"), 1)
        self.assertIn("C Gamma name", lines)

    def test_open_tasks_are_listed_in_full_with_a_status_word_and_what_they_wait_on(self):
        lines = texts(self.svg(prs=[pr(20)]))
        joined = "\n".join(lines)
        for needle in ("A-02", "Ready thing", "in progress #20", "A-O1", "Owner thing", "owner to-do", "A-04", "Waits for the owner",
                       "blocked", "B-01", "Next milestone"):
            self.assertIn(needle, joined)
        self.assertIn("waits on A-O1 (owner)", lines)
        self.assertIn("waits on all of A", lines)

    def test_flagged_tasks_say_what_blocks_them(self):
        lines = texts(self.svg(issues=[issue(8, "A-02: waiting for the API", ["blocked"])]))
        self.assertIn("blocked by #8", lines)

    def test_finished_tasks_are_collapsed_into_a_count(self):
        lines = texts(self.svg())
        self.assertIn("2 done", lines)
        joined = "\n".join(lines)
        self.assertNotIn("Done thing", joined)
        self.assertNotIn("Dropped thing", joined)

    def test_a_fully_done_milestone_shows_only_its_count(self):
        text = TASKS.replace('status = "todo"\nassignee = "implementer"\nrisk = "normal"\ndepends_on = ["milestone:A"]',
                             'status = "done"\nassignee = "implementer"\nrisk = "normal"\ndepends_on = []')
        lines = texts(status_visual.render_svg(model(tasks=text)))
        self.assertIn("1 done", lines)
        self.assertIn("100% 1/1", lines)

    def test_big_milestones_show_a_capped_number_of_open_tasks_and_count_the_rest(self):
        extra = "".join(
            f'\n[[task]]\nid = "A-{n:02d}"\ntitle = "Extra {n}"\nmilestone = "A"\nstatus = "todo"\n'
            f'assignee = "implementer"\nrisk = "normal"\ndepends_on = []\n' for n in range(10, 40))
        lines = texts(status_visual.render_svg(model(tasks=TASKS + extra)))
        shown = [line for line in lines if line.startswith("Extra ")]
        self.assertEqual(len(shown), status_visual.MAX_OPEN_PER_MILESTONE - 3)  # A-02, A-O1 and A-04 come first
        self.assertIn(f"+{3 + 30 - status_visual.MAX_OPEN_PER_MILESTONE} more open tasks", lines)

    def test_the_svg_has_an_accessible_title_and_description(self):
        root = ET.fromstring(self.svg(prs=[pr(20)]))
        ns = "{http://www.w3.org/2000/svg}"
        self.assertEqual(root.get("role"), "img")
        self.assertEqual(root.find(ns + "title").text, "Tally status")
        desc = root.find(ns + "desc").text
        self.assertIn("3 milestones", desc)
        self.assertIn("Alpha name", desc)

    def test_every_text_color_has_enough_contrast_on_its_background_in_both_schemes(self):
        css = status_visual.CSS
        light, dark = css.split("@media (prefers-color-scheme: dark){")
        def fills(block):
            return {m.group(1): m.group(2) for m in re.finditer(r"\.(\w+)\{fill:(#[0-9a-f]{3,6})\}", block)}
        def lum(hexcolor):
            if len(hexcolor) == 4:
                hexcolor = "#" + "".join(c * 2 for c in hexcolor[1:])
            ch = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
            return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
        def ratio(a, b):
            hi, lo = sorted((lum(a), lum(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)
        base = fills(light)
        scheme_light = dict(base)
        scheme_dark = dict(base, **fills(dark))
        for name, scheme in (("light", scheme_light), ("dark", scheme_dark)):
            for bg in ("bg", "card"):
                for fg in ("fg", "muted", "ok", "info", "warn", "bad"):
                    with self.subTest(scheme=name, bg=bg, fg=fg):
                        self.assertGreaterEqual(ratio(scheme[fg], scheme[bg]), 4.5)

    def test_cards_and_markers_use_theme_classes_only(self):
        svg = self.svg(prs=[pr(20)])
        self.assertNotRegex(svg, r'fill="#|stroke="#|style="')
        self.assertIn('class="card"', svg)

    def test_task_states_have_distinct_marker_shapes(self):
        extra = ('\n[[task]]\nid = "A-05"\ntitle = "Another ready thing"\nmilestone = "A"\nstatus = "todo"\n'
                 'assignee = "implementer"\nrisk = "normal"\ndepends_on = []\n')
        svg = self.svg(prs=[pr(20)], tasks=TASKS + extra)
        for shape in ("mk-ready", "mk-progress", "mk-blocked", "mk-owner", "mk-done"):
            self.assertIn(shape, svg)

    def test_is_deterministic(self):
        self.assertEqual(self.svg(prs=[pr(20)]), self.svg(prs=[pr(20)]))

    def test_only_the_stamp_changes_with_the_clock(self):
        a = status_visual.render_svg(model(now="2026-11-13T12:00:00Z"))
        b = status_visual.render_svg(model(now="2026-11-13T12:30:00Z"))
        self.assertNotEqual(a, b)
        self.assertEqual(status_visual.strip_stamp(a), status_visual.strip_stamp(b))

    def test_same_ignoring_stamp_detects_real_changes(self):
        a = status_visual.render_svg(model(now="2026-11-13T12:00:00Z"))
        self.assertTrue(status_visual.same_ignoring_stamp(a, status_visual.render_svg(model(now="2026-11-13T12:30:00Z"))))
        self.assertFalse(status_visual.same_ignoring_stamp(a, status_visual.render_svg(model(prs=[pr(20)]))))

    def test_has_dark_mode_and_no_active_or_external_content(self):
        svg = self.svg(prs=[pr(20)])
        self.assertIn("prefers-color-scheme: dark", svg)
        low = svg.lower()
        for bad in ("<script", "<foreignobject", "<image", "href=", "javascript:", "http://www.w3.org/1999/xlink", "onload", "@import", "url("):
            self.assertNotIn(bad, low)

    def test_hostile_titles_are_escaped_and_the_svg_stays_well_formed(self):
        nasty = ['<script>alert(1)</script>', '"><svg onload=alert(1)>', "]]><!-- x -->", "a&b&amp;c", "\x00\x08\x1b",
                 "‮⁦evil", "x" * 5000, "<![CDATA[ x ]]>", "</text></svg><svg>"]
        for n, title in enumerate(nasty):
            with self.subTest(title=title[:20]):
                svg = self.svg(prs=[pr(100 + n, title)], issues=[
                    issue(200 + n, title, ["blocked", "owner-todo", "needs-owner"])])
                texts(svg)  # raises unless well-formed
                self.assertNotIn("<script", svg)
                self.assertNotIn("onload", svg.replace("onload=alert(1)&gt;", ""))
                self.assertLess(len(svg), 40_000)

    def test_hostile_task_and_milestone_text_is_escaped_clipped_and_well_formed(self):
        nasty = ['<script>alert(1)</script>', '"><svg onload=alert(1)>', "a&b&amp;c", "</text></svg><svg>", "\u202eevil",
                 "x" * 3000, "\u6f22" * 300, "<![CDATA[ x ]]>"]
        for title in nasty:
            with self.subTest(title=title[:20]):
                text = (TASKS.replace('title = "Ready thing"', f"title = {json.dumps(title)}")
                        .replace('title = "Alpha name"', f"title = {json.dumps(title[:30])}")
                        .replace('purpose = "Build the alpha."', f"purpose = {json.dumps(title[:100])}"))
                svg = status_visual.render_svg(model(tasks=text))
                lines = texts(svg)  # raises unless well-formed
                self.assertNotIn("<script", svg)
                self.assertNotIn("<svg onload", svg)
                self.assertLess(len(svg), 60_000)
                for line in lines:
                    self.assertLessEqual(status_visual.text_width(line), 140, line[:40])

    def test_very_long_task_titles_are_truncated_with_an_ellipsis(self):
        svg = self.svg(tasks=TASKS.replace("Ready thing", "R" * 400))
        lines = [t for t in texts(svg) if t.startswith("R")]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("…"))
        self.assertLessEqual(status_visual.text_width(lines[0]), status_visual.MAX_TASK_TITLE)

    def test_every_text_has_a_fill_class_so_dark_mode_is_legible(self):
        svg = self.svg(prs=[pr(20), pr(21, ci="failing", behind=True)], issues=[
            issue(7, "[owner] A-O1: do it", ["owner-todo"]), issue(8, "b", ["blocked"]), issue(9, "n", ["needs-owner"])])
        fills = {"fg", "muted", "ok", "info", "warn", "bad"}
        els = list(ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}text"))
        self.assertGreater(len(els), 20)
        for el in els:
            self.assertTrue(fills & set(el.get("class", "").split()), ET.tostring(el, encoding="unicode"))

    def test_wide_characters_cannot_overflow_the_columns(self):
        svg = self.svg(prs=[pr(20, "\u6f22" * 70)], issues=[issue(8, "\u6f22" * 70, ["blocked"])])
        titles = [t for t in texts(svg) if "\u6f22" in t]
        self.assertEqual(len(titles), 3)  # queue row, PR-to-merge blocker, blocked issue
        for t in titles:
            self.assertLessEqual(status_visual.text_width(t), status_visual.MAX_TITLE, t)

    def test_unknown_merge_state_is_shown_and_never_ready_to_merge(self):
        m = model(prs=[pr(20, merge_unknown=True)])
        self.assertEqual([b for b in m["blockers"] if b["kind"] == "pr-waiting"], [])
        self.assertIn("merge state unknown", "\n".join(texts(status_visual.render_svg(m))))

    def test_long_titles_are_clipped(self):
        svg = self.svg(prs=[pr(20, "y" * 400)])
        self.assertNotIn("y" * (status_visual.MAX_TITLE + 1), svg)

    def test_outside_questions_are_a_count_without_titles(self):
        d = data()
        d["outside_questions"] = 3
        svg = status_visual.render_svg(status_visual.build_model(TASKS, d, NOW))
        self.assertIn("Outside questions: 3", "\n".join(texts(svg)))
        self.assertEqual(json.loads(status_visual.status_json(status_visual.build_model(TASKS, d, NOW)))["outside_questions"], 3)

    def test_bad_outside_count_is_zero_or_an_error(self):
        for bad in (-1, "3", None, True, 1.5):
            with self.subTest(bad):
                d = data()
                d["outside_questions"] = bad
                with self.assertRaises(status_visual.StatusError):
                    status_visual.build_model(TASKS, d, NOW)
        self.assertEqual(model()["outside"], 0)

    def test_lists_state_empty_messages(self):
        svg = status_visual.render_svg(model(tasks=TASKS.split('[[task]]\nid = "A-O1"')[0]))
        joined = "\n".join(texts(svg))
        self.assertIn("No open PRs waiting for the owner", joined)
        self.assertIn("No blockers", joined)

    def test_status_json_is_small_and_complete(self):
        out = json.loads(status_visual.status_json(model(prs=[pr(20)])))
        self.assertEqual(out["generated_at"], NOW)
        self.assertEqual(out["current_milestone"], "A")
        self.assertEqual(out["owner_queue"], 1)
        self.assertEqual(out["milestones"][0], {"id": "A", "title": "Alpha name", "done": 2, "total": 5})
        self.assertIn("blockers", out)


class Cli(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def render(self, d, *extra, env=None):
        (d / "t.toml").write_text(TASKS)
        (d / "in.json").write_text(json.dumps(data(prs=[pr(20)])))
        return self.run_cli("render", "--tasks", str(d / "t.toml"), "--input", str(d / "in.json"), "--now", NOW,
                            "--svg", str(d / "s.svg"), "--json", str(d / "s.json"), *extra, env=env)

    def test_render_writes_the_detail_page_next_to_the_svg_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.render(Path(d))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("## A Alpha name", (Path(d) / "status.md").read_text())

    def test_render_md_path_and_repo_options(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.render(Path(d), "--md", str(Path(d) / "page.md"), "--repo", "o/r")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("](https://github.com/o/r/issues/20)", (Path(d) / "page.md").read_text())
            self.assertFalse((Path(d) / "status.md").exists())

    def test_render_takes_the_repo_from_github_repository_when_valid(self):
        with tempfile.TemporaryDirectory() as d:
            ok = self.render(Path(d), env={"GITHUB_REPOSITORY": "o/r", "PATH": ""})
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("github.com/o/r/issues/20", (Path(d) / "status.md").read_text())

    def test_a_bad_repo_exits_2_without_writing_anything(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.render(Path(d), "--repo", "not a repo")
            self.assertEqual(r.returncode, 2)
            self.assertFalse((Path(d) / "s.svg").exists() or (Path(d) / "status.md").exists())

    def test_render_writes_svg_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.toml").write_text(TASKS)
            (d / "in.json").write_text(json.dumps(data(prs=[pr(20)])))
            r = self.run_cli("render", "--tasks", str(d / "t.toml"), "--input", str(d / "in.json"), "--now", NOW,
                             "--svg", str(d / "s.svg"), "--json", str(d / "s.json"))
            self.assertEqual(r.returncode, 0, r.stderr)
            texts((d / "s.svg").read_text())
            self.assertEqual(json.loads((d / "s.json").read_text())["generated_at"], NOW)

    def test_bad_input_exits_2_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.toml").write_text(TASKS)
            (d / "in.json").write_text("{not json")
            r = self.run_cli("render", "--tasks", str(d / "t.toml"), "--input", str(d / "in.json"), "--now", NOW,
                             "--svg", str(d / "s.svg"), "--json", str(d / "s.json"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("error", r.stderr)
            self.assertFalse((d / "s.svg").exists())

    def test_missing_input_file_exits_2(self):
        r = self.run_cli("render", "--tasks", "/nonexistent.toml", "--input", "/nonexistent.json", "--now", NOW,
                         "--svg", "/tmp/never.svg", "--json", "/tmp/never.json")
        self.assertEqual(r.returncode, 2)

    def test_same_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.svg").write_text(status_visual.render_svg(model(now="2026-11-13T12:00:00Z")))
            (d / "b.svg").write_text(status_visual.render_svg(model(now="2026-11-13T13:00:00Z")))
            (d / "c.svg").write_text(status_visual.render_svg(model(prs=[pr(20)])))
            self.assertEqual(self.run_cli("same", str(d / "a.svg"), str(d / "b.svg")).returncode, 0)
            self.assertEqual(self.run_cli("same", str(d / "a.svg"), str(d / "c.svg")).returncode, 1)
            self.assertEqual(self.run_cli("same", str(d / "a.svg"), str(d / "missing.svg")).returncode, 2)


class FakeApi:
    """Stands in for `gh api`: records every path, answers from canned data."""

    def __init__(self, pulls=(), mergeable=None, runs=None, issues=None):
        self.pulls, self.mergeable, self.runs, self.issues = list(pulls), mergeable or {}, runs or {}, issues or {}
        self.paths = []
        self.mergeable = {k: list(v) if isinstance(v, list) else [v] for k, v in self.mergeable.items()}

    def __call__(self, path):
        self.paths.append(path)
        if "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/")[0]
            return {"check_runs": self.runs.get(sha, [])}
        if "/pulls/" in path:
            n = int(path.split("/pulls/")[1].split("?")[0])
            seq = self.mergeable.get(n, ["clean"])
            return {"number": n, "mergeable_state": seq.pop(0) if len(seq) > 1 else seq[0]}
        if "/pulls?" in path:
            return self.pulls
        if "/issues?" in path:
            label = path.split("labels=")[1].split("&")[0]
            return self.issues.get(label, [])
        raise AssertionError(f"unexpected path {path}")


def api_pr(number, sha, draft=False, title="t", repo="o/r", assoc="OWNER", labels=()):
    head = {"sha": sha, "repo": {"full_name": repo} if repo else None}
    return {"number": number, "title": title, "draft": draft, "head": head, "state": "open", "author_association": assoc,
            "labels": [{"name": x} for x in labels]}


def run(status, conclusion=None, name="unit"):
    return {"name": name, "status": status, "conclusion": conclusion}


def api_issue(number, labels, title="t", state="open", pull=False, assoc="OWNER"):
    d = {"number": number, "title": title, "state": state, "state_reason": None, "author_association": assoc,
         "created_at": "2026-11-10T12:00:00Z", "labels": [{"name": x} for x in labels]}
    if pull:
        d["pull_request"] = {"url": "x"}
    return d


class Fetch(unittest.TestCase):
    def fetch(self, api, sleeps=None):
        return status_fetch.fetch(api, "o/r", sleep=(sleeps if sleeps is not None else []).append)

    def ci(self, runs):
        api = FakeApi(pulls=[api_pr(1, "sha1")], runs={"sha1": runs})
        return self.fetch(api)["prs"][0]["ci"]

    def test_ci_is_failing_when_any_run_failed(self):
        for bad in ("failure", "timed_out", "cancelled", "action_required"):
            with self.subTest(bad):
                self.assertEqual(self.ci([run("completed", "success"), run("completed", bad)]), "failing")

    def test_failing_beats_pending(self):
        self.assertEqual(self.ci([run("in_progress"), run("completed", "failure")]), "failing")

    def test_ci_is_pending_while_anything_runs(self):
        self.assertEqual(self.ci([run("completed", "success"), run("queued")]), "pending")

    def test_ci_is_passing_when_all_succeed_or_skip(self):
        self.assertEqual(self.ci([run("completed", "success"), run("completed", "skipped"), run("completed", "neutral")]), "passing")

    def test_ci_is_none_without_runs(self):
        self.assertEqual(self.ci([]), "none")

    def test_the_status_workflows_own_check_run_never_counts(self):
        ok = run("completed", "success")
        self.assertEqual(self.ci([ok, run("in_progress", name="publish")]), "passing")
        self.assertEqual(self.ci([ok, run("completed", "failure", name="publish")]), "passing")
        self.assertEqual(self.ci([ok, run("completed", "cancelled", name="publish")]), "passing")
        self.assertEqual(self.ci([run("in_progress", name="publish")]), "none")
        self.assertEqual(self.ci([run("completed", "failure"), run("in_progress", name="publish")]), "failing")

    def test_fork_prs_from_outsiders_are_dropped_before_any_other_call(self):
        api = FakeApi(pulls=[api_pr(1, "s1"), api_pr(2, "s2", repo="evil/r", assoc="NONE"),
                             api_pr(3, "s3", repo=None, assoc="CONTRIBUTOR"), api_pr(4, "s4", repo="x/r", assoc="FIRST_TIME_CONTRIBUTOR"),
                             api_pr(5, "s5", repo="friend/r", assoc="COLLABORATOR"), api_pr(6, "s6", repo="o/r", assoc="NONE")])
        self.assertEqual([p["number"] for p in self.fetch(api)["prs"]], [1, 5, 6])
        self.assertFalse(any(f"/pulls/{n}" in p or f"s{n}/" in p for p in api.paths for n in (2, 3, 4)), api.paths)

    def test_unknown_merge_state_is_retried_once(self):
        api = FakeApi(pulls=[api_pr(1, "s1")], mergeable={1: ["unknown", "behind"]})
        sleeps = []
        pr1 = self.fetch(api, sleeps)["prs"][0]
        self.assertEqual((pr1["behind"], pr1["merge_unknown"], len(sleeps)), (True, False, 1))

    def test_still_unknown_after_the_retry_is_flagged(self):
        api = FakeApi(pulls=[api_pr(1, "s1")], mergeable={1: "unknown"})
        sleeps = []
        pr1 = self.fetch(api, sleeps)["prs"][0]
        self.assertEqual((pr1["behind"], pr1["merge_unknown"], len(sleeps)), (False, True, 1))

    def test_known_merge_state_is_not_retried(self):
        sleeps = []
        pr1 = self.fetch(FakeApi(pulls=[api_pr(1, "s1")]), sleeps)["prs"][0]
        self.assertEqual((pr1["merge_unknown"], sleeps), (False, []))

    def test_pr_fields_and_behind(self):
        api = FakeApi(pulls=[api_pr(1, "s1", draft=True, title="T1"), api_pr(2, "s2")], mergeable={2: "behind"})
        prs = {p["number"]: p for p in self.fetch(api)["prs"]}
        self.assertEqual((prs[1]["draft"], prs[1]["behind"], prs[1]["title"]), (True, False, "T1"))
        self.assertTrue(prs[2]["behind"])

    def test_pr_labels_are_kept_as_names(self):
        api = FakeApi(pulls=[api_pr(1, "s1", labels=["blocked", "risk:high"]), api_pr(2, "s2")])
        prs = {p["number"]: p for p in self.fetch(api)["prs"]}
        self.assertEqual((prs[1]["labels"], prs[2]["labels"]), (["blocked", "risk:high"], []))

    def test_issues_are_merged_by_number_without_prs_and_labels_flattened(self):
        api = FakeApi(issues={
            "owner-todo": [api_issue(7, ["owner-todo", "needs-owner"]), api_issue(8, ["owner-todo"], state="closed")],
            "needs-owner": [api_issue(7, ["owner-todo", "needs-owner"]), api_issue(30, ["needs-owner"], pull=True)],
            "blocked": [api_issue(9, ["blocked"])],
            "follow-up": [api_issue(10, ["follow-up"])],
        })
        issues = {i["number"]: i for i in self.fetch(api)["issues"]}
        self.assertEqual(sorted(issues), [7, 8, 9, 10])
        self.assertEqual(issues[7]["labels"], ["owner-todo", "needs-owner"])
        self.assertEqual(issues[8]["state"], "closed")

    def test_issues_from_outsiders_never_reach_the_output(self):
        for label in ("owner-todo", "needs-owner", "blocked", "follow-up"):
            for assoc in ("NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "MANNEQUIN"):
                with self.subTest(label=label, assoc=assoc):
                    api = FakeApi(issues={label: [api_issue(99, [label], title="BUY CHEAP STUFF at evil.example", assoc=assoc),
                                                  api_issue(5, [label], title="mine")]})
                    out = self.fetch(api)
                    self.assertEqual([i["number"] for i in out["issues"]], [5])
                    self.assertNotIn("evil.example", json.dumps(out))

    def test_write_access_authors_are_trusted(self):
        api = FakeApi(issues={"blocked": [api_issue(n, ["blocked"], assoc=a) for n, a in ((1, "OWNER"), (2, "MEMBER"), (3, "COLLABORATOR"))]})
        self.assertEqual([i["number"] for i in self.fetch(api)["issues"]], [1, 2, 3])

    def test_outside_questions_are_only_counted(self):
        api = FakeApi(issues={"needs-owner": [
            api_issue(10, ["needs-owner"], title="outside one", assoc="NONE"),
            api_issue(11, ["needs-owner"], title="outside two", assoc="CONTRIBUTOR"),
            api_issue(12, ["needs-owner"], title="trusted", assoc="OWNER"),
            api_issue(13, ["needs-owner"], title="closed", assoc="NONE", state="closed"),
            api_issue(14, ["needs-owner"], title="a pull", assoc="NONE", pull=True)],
            "blocked": [api_issue(15, ["blocked"], assoc="NONE")]})
        out = self.fetch(api)
        self.assertEqual(out["outside_questions"], 2)
        self.assertEqual([i["number"] for i in out["issues"]], [12])
        self.assertNotIn("outside one", json.dumps(out))

    def test_an_outsider_issue_titled_like_an_owner_task_cannot_change_the_task(self):
        real = api_issue(7, ["owner-todo"], title="[owner] A-O1: do it", state="closed")
        real["state_reason"] = "completed"
        fake = api_issue(99, ["needs-owner"], title="[owner] A-O1 x", assoc="NONE")
        out = self.fetch(FakeApi(issues={"owner-todo": [real], "needs-owner": [fake]}))
        tasks_a = {t["id"]: t for t in status_visual.build_model(TASKS, out, NOW)["milestones"][0]["tasks"]}
        self.assertEqual((tasks_a["A-O1"]["state"], tasks_a["A-04"]["state"]), ("done", "ready"))

    def test_owner_todo_includes_closed_issues_others_only_open(self):
        api = FakeApi()
        self.fetch(api)
        issue_paths = [p for p in api.paths if "/issues?" in p]
        self.assertEqual(len(issue_paths), 4)
        self.assertTrue(any("labels=owner-todo" in p and "state=all" in p for p in issue_paths))
        self.assertTrue(all("state=open" in p for p in issue_paths if "owner-todo" not in p))

    def test_output_is_what_the_renderer_accepts(self):
        api = FakeApi(pulls=[api_pr(20, "s", title="A-02: x")], issues={"blocked": [api_issue(8, ["blocked"], title="B")]})
        out = self.fetch(api)
        self.assertIn("fetched_at", out)
        m = status_visual.build_model(TASKS, out, NOW)
        self.assertEqual([b["ref"] for b in m["blockers"] if b["kind"] == "blocked"], ["#8"])

    def test_api_failure_raises_fetch_error(self):
        def boom(path):
            raise status_fetch.FetchError("HTTP 403")

        with self.assertRaises(status_fetch.FetchError):
            self.fetch(boom)

    def test_repo_must_look_like_owner_slash_name(self):
        for bad in ("", "noslash", "a/b/c", "a/b; rm -rf /", "../x", "a b/c"):
            with self.subTest(bad), self.assertRaises(status_fetch.FetchError):
                status_fetch.fetch(FakeApi(), bad)


class GhApi(unittest.TestCase):
    """gh_api against a fake `gh` process: --paginate --slurp output shapes."""

    def call(self, stdout, returncode=0, stderr=""):
        done = subprocess.CompletedProcess([], returncode, stdout, stderr)
        with mock.patch.object(status_fetch.subprocess, "run", return_value=done) as m:
            result = status_fetch.gh_api("repos/o/r/x")
        self.assertEqual(m.call_args.args[0][:2], ["gh", "api"])
        return result

    def test_pages_of_arrays_are_flattened(self):
        self.assertEqual(self.call('[[{"n": 1}, {"n": 2}], [{"n": 3}]]'), [{"n": 1}, {"n": 2}, {"n": 3}])

    def test_one_object_comes_back_as_the_object(self):
        self.assertEqual(self.call('[{"mergeable_state": "clean"}]'), {"mergeable_state": "clean"})

    def test_pages_of_check_runs_are_merged(self):
        pages = [{"total_count": 3, "check_runs": [{"name": "a"}, {"name": "b"}]}, {"total_count": 3, "check_runs": [{"name": "c"}]}]
        self.assertEqual([r["name"] for r in self.call(json.dumps(pages))["check_runs"]], ["a", "b", "c"])

    def test_an_empty_array_stays_empty(self):
        self.assertEqual(self.call("[]"), [])
        self.assertEqual(self.call("[[]]"), [])

    def test_failures_raise_fetch_error(self):
        with self.assertRaises(status_fetch.FetchError):
            self.call("", returncode=1, stderr="HTTP 403")
        with self.assertRaises(status_fetch.FetchError):
            self.call("not json")


if __name__ == "__main__":
    unittest.main()
