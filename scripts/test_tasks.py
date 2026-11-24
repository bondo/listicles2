"""Tests for scripts/tasks.py. Run: python3 -I -m unittest discover -s scripts -p 'test_tasks.py'"""

import io
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402  # justified: must follow the sys.path insert above

def milestone_tables(*ids):
    return "".join(f'[[milestone]]\nid = "{m}"\ntitle = "Title {m}"\npurpose = "Purpose {m}."\n\n' for m in ids)


HEADER = 'milestones = ["M0", "M1"]\n\n' + milestone_tables("M0", "M1")


def task(tid, milestone="M0", status="todo", assignee="implementer", deps=(), **extra):
    lines = [
        "[[task]]", f'id = "{tid}"', f'title = "t {tid}"', f'milestone = "{milestone}"',
        f'status = "{status}"', f'assignee = "{assignee}"', 'risk = "normal"',
        "depends_on = [" + ", ".join(f'"{d}"' for d in deps) + "]",
    ]
    lines += [f"{k} = {json.dumps(v)}" for k, v in extra.items()]
    return "\n".join(lines) + "\n"


def graph(*parts):
    return tasks.parse(HEADER + "\n".join(parts), burn_down=False)


def errors_of(*parts, header=HEADER, burn_down=False):
    with unittest.TestCase().assertRaises(tasks.TaskFileError) as cm:
        tasks.parse(header + "\n".join(parts), burn_down=burn_down)
    return "\n".join(cm.exception.errors)


def fu_issue(number, severity="minor", target="M0", labels=(), state="open"):
    names = ["follow-up", f"severity:{severity}", f"target:{target}", *labels]
    return {"number": number, "title": f"[follow-up] thing {number}", "state": state,
            "labels": [{"name": n} for n in names]}


def ready_ids(g, **kw):
    d = tasks.derive(g, **kw)
    return [t.id for t in sorted(g.tasks, key=lambda t: tasks.order_key(g, t)) if d[t.id]["state"] == "ready"]


class MilestoneNamesTest(unittest.TestCase):
    def test_every_milestone_has_a_title_and_purpose(self):
        g = graph(task("M0-01"))
        self.assertEqual((g.info["M0"].title, g.info["M0"].purpose), ("Title M0", "Purpose M0."))
        self.assertEqual(list(g.info), ["M0", "M1"])

    def test_repository_milestones_have_human_friendly_names(self):
        path = Path(__file__).resolve().parent.parent / tasks.DEFAULT_FILE
        g = tasks.parse(path.read_text(encoding="utf-8"))
        self.assertEqual(list(g.info), g.milestones)
        self.assertEqual(g.info["M0"].title, "Foundation and process")
        for info in g.info.values():
            self.assertTrue(info.title and info.purpose)
            self.assertLessEqual(len(info.title), tasks.MAX_MILESTONE_TITLE)

    def test_a_milestone_without_a_table_fails(self):
        header = 'milestones = ["M0", "M1"]\n\n' + milestone_tables("M0")
        self.assertIn("M1 has no [[milestone]] table", errors_of(task("M0-01"), header=header))

    def test_a_table_for_an_unknown_milestone_fails(self):
        header = HEADER + milestone_tables("M9")
        self.assertIn("unknown milestone 'M9'", errors_of(task("M0-01"), header=header))

    def test_duplicate_tables_fail(self):
        header = HEADER + milestone_tables("M0")
        self.assertIn("duplicate [[milestone]] table for M0", errors_of(task("M0-01"), header=header))

    def test_empty_blank_or_non_string_titles_fail(self):
        for bad in ('""', '"   "', "3"):
            with self.subTest(bad):
                header = f'milestones = ["M0"]\n\n[[milestone]]\nid = "M0"\ntitle = {bad}\npurpose = "p"\n'
                self.assertIn("M0: title must be a non-empty string", errors_of(task("M0-01"), header=header))

    def test_missing_title_or_purpose_fails(self):
        for field in ("title", "purpose"):
            with self.subTest(field):
                other = "purpose" if field == "title" else "title"
                header = f'milestones = ["M0"]\n\n[[milestone]]\nid = "M0"\n{other} = "x"\n'
                self.assertIn(f"M0: missing {field}", errors_of(task("M0-01"), header=header))

    def test_overlong_title_or_purpose_fails(self):
        header = ('milestones = ["M0"]\n\n[[milestone]]\nid = "M0"\n'
                  f'title = "{"t" * (tasks.MAX_MILESTONE_TITLE + 1)}"\npurpose = "{"p" * (tasks.MAX_MILESTONE_PURPOSE + 1)}"\n')
        errs = errors_of(task("M0-01"), header=header)
        self.assertIn("M0: title is longer than", errs)
        self.assertIn("M0: purpose is longer than", errs)

    def test_unknown_fields_in_a_table_fail(self):
        header = 'milestones = ["M0"]\n\n[[milestone]]\nid = "M0"\ntitle = "t"\npurpose = "p"\nowner = "x"\n'
        self.assertIn("M0: unknown fields ['owner']", errors_of(task("M0-01"), header=header))

    def test_a_milestone_table_must_be_an_array_of_tables(self):
        header = 'milestones = ["M0"]\nmilestone = 3\n'
        self.assertIn("milestone must be an array of tables", errors_of(task("M0-01"), header=header))


class ValidateTest(unittest.TestCase):
    def test_repository_task_file_is_valid(self):
        path = Path(__file__).resolve().parent.parent / tasks.DEFAULT_FILE
        g = tasks.parse(path.read_text(encoding="utf-8"))  # strict: burn-down tasks required
        self.assertGreater(len(g.tasks), 0)

    def test_agent_ids_take_two_or_three_digits(self):
        # M1-99 was used, so M1-100 and up must validate; the pattern is pinned at two or three digits.
        for tid in ("M1-03", "M1-99", "M1-100", "M1-999", "M1-001"):
            self.assertIn(tid, graph(task(tid, milestone="M1")).by_id)
        for tid in ("M1-1", "M1-1000", "M1-0100", "M1-ABC", "M1-1O0", "M1-10x", "M1-O", "M1-FU1", "M1-1 00"):
            self.assertIn("id must look like", errors_of(task(tid, milestone="M1")), tid)

    def test_three_digit_ids_keep_file_order_and_owner_ids(self):
        g = graph(task("M1-100", milestone="M1"), task("M1-99", milestone="M1"), task("M1-O1", milestone="M1", assignee="owner"))
        self.assertEqual(ready_ids(g), ["M1-100", "M1-99", "M1-O1"])  # position in the file, not id order
        self.assertIn("owner tasks (and only they)", errors_of(task("M1-100", milestone="M1", assignee="owner")))
        self.assertIn("id must look like", errors_of(task("M1-O100x", milestone="M1", assignee="owner")))

    def test_rejects_duplicate_ids(self):
        self.assertIn("duplicate id", errors_of(task("M0-01"), task("M0-01")))

    def test_rejects_unknown_dependency(self):
        self.assertIn("unknown task 'M0-09'", errors_of(task("M0-01", deps=["M0-09"])))

    def test_rejects_unknown_and_own_milestone_dependency(self):
        self.assertIn("unknown milestone 'M9'", errors_of(task("M0-01", deps=["milestone:M9"])))
        self.assertIn("its own milestone", errors_of(task("M0-01", deps=["milestone:M0"])))

    def test_rejects_cycles_including_through_milestones(self):
        self.assertIn("cycle", errors_of(task("M0-01", deps=["M0-02"]), task("M0-02", deps=["M0-01"])))
        self.assertIn("cycle", errors_of(task("M0-01", deps=["M1-01"]),
                                         task("M1-01", milestone="M1", deps=["milestone:M0"])))

    def test_rejects_unknown_fields_and_bad_enums(self):
        msg = errors_of(task("M0-01", status="doing", depends="x"))
        self.assertIn("unknown fields ['depends']", msg)
        self.assertIn("status must be one of", msg)

    def test_owner_ids_and_assignee_must_agree(self):
        self.assertIn("owner tasks", errors_of(task("M0-O1", assignee="implementer")))
        self.assertIn("owner tasks", errors_of(task("M0-01", assignee="owner")))

    def test_id_prefix_must_match_milestone(self):
        self.assertIn("must start with its milestone", errors_of(task("M1-01", milestone="M0")))

    def test_rejects_duplicate_dependencies_and_non_string_notes(self):
        self.assertIn("duplicates", errors_of(task("M0-01"), task("M0-02", deps=["M0-01", "M0-01"])))
        self.assertIn("notes must be a string", errors_of(task("M0-01", notes=5)))

    def test_done_task_cannot_depend_on_todo_agent_task(self):
        self.assertIn("still todo", errors_of(task("M0-01"), task("M0-02", status="done", deps=["M0-01"])))
        # an owner dependency may be finished on GitHub only (drift), so it is allowed
        graph(task("M0-O1", assignee="owner"), task("M0-02", status="done", deps=["M0-O1"]))
        # owner-only todo members of a milestone are derived from GitHub, so they don't make the file invalid
        graph(task("M0-O1", assignee="owner"), task("M1-01", milestone="M1", status="done", deps=["milestone:M0"]))
        msg = errors_of(task("M0-01"), task("M1-01", milestone="M1", status="done", deps=["milestone:M0"]))
        self.assertIn("still todo", msg)

    def test_rejects_missing_required_field(self):
        self.assertIn("missing ['risk']", errors_of(task("M0-01").replace('risk = "normal"\n', "")))


class BurnDownTest(unittest.TestCase):
    """Every milestone with agent work has an Mx-FU task that runs after all of that work."""

    def test_milestone_with_agent_tasks_needs_a_burn_down(self):
        self.assertIn("M0 has no burn-down task M0-FU", errors_of(task("M0-01"), burn_down=True))

    def test_milestone_with_only_owner_tasks_needs_none(self):
        tasks.parse(HEADER + task("M0-O1", assignee="owner"))

    def test_burn_down_must_depend_on_every_other_agent_task(self):
        msg = errors_of(task("M0-01"), task("M0-02"), task("M0-FU", deps=["M0-01"]), burn_down=True)
        self.assertIn("M0-FU must depend on M0-02", msg)
        self.assertNotIn("M0-FU must depend on M0-01", msg)

    def test_burn_down_need_not_depend_on_owner_tasks(self):
        tasks.parse(HEADER + "\n".join([task("M0-01"), task("M0-O1", assignee="owner"),
                                        task("M0-FU", deps=["M0-01"])]))

    def test_burn_down_is_assigned_to_implementer(self):
        msg = errors_of(task("M0-01"), task("M0-FU", assignee="planner", deps=["M0-01"]), burn_down=True)
        self.assertIn("M0-FU must be assigned to implementer", msg)

    def test_ids_other_than_nn_owner_or_fu_are_rejected(self):
        self.assertIn("id must look like", errors_of(task("M0-XX")))
        self.assertIn("id must look like", errors_of(task("M0-FUX")))

    def test_tasks_may_depend_on_the_burn_down_without_a_cycle(self):
        # a task may depend on the burn-down (e.g. the milestone merge) without creating a cycle
        tasks.parse(HEADER + "\n".join([task("M0-01"), task("M0-FU", deps=["M0-01"]),
                                        task("M0-O1", assignee="owner", deps=["M0-FU"])]))


class DeriveTest(unittest.TestCase):
    def test_ready_needs_all_dependencies_done(self):
        g = graph(task("M0-01", status="done"), task("M0-02", deps=["M0-01"]), task("M0-03", deps=["M0-02"]))
        self.assertEqual(ready_ids(g), ["M0-02"])

    def test_claimed_tasks_are_not_ready(self):
        g = graph(task("M0-01"), task("M0-02"))
        self.assertEqual(ready_ids(g, claimed=["M0-01"]), ["M0-02"])

    def test_dropped_dependency_counts_as_satisfied_and_dropped_is_never_ready(self):
        g = graph(task("M0-01", status="dropped"), task("M0-02", deps=["M0-01"]))
        self.assertEqual(ready_ids(g), ["M0-02"])

    def test_milestone_dependency_waits_for_every_task_in_it(self):
        g = graph(task("M0-01", status="done"), task("M0-02"), task("M1-01", milestone="M1", deps=["milestone:M0"]))
        self.assertEqual(ready_ids(g), ["M0-02"])
        self.assertEqual(tasks.derive(g)["M1-01"]["unmet"], ["milestone:M0"])
        g = graph(task("M0-01", status="done"), task("M0-02", status="dropped"),
                  task("M1-01", milestone="M1", deps=["milestone:M0"]))
        self.assertEqual(ready_ids(g), ["M1-01"])

    def test_owner_task_done_when_linked_issue_closed(self):
        g = graph(task("M0-O1", assignee="owner", issue=12), task("M0-01", deps=["M0-O1"]))
        self.assertEqual(ready_ids(g), ["M0-O1"])
        issues = [{"number": 12, "title": "[owner] Add label", "state": "CLOSED"}]
        self.assertEqual(ready_ids(g, issues=issues), ["M0-01"])
        self.assertEqual(ready_ids(g, issues=[{"number": 12, "title": "x", "state": "open"}]), ["M0-O1"])

    def test_owner_task_done_when_issue_title_names_it(self):
        g = graph(task("M0-O2", assignee="owner"), task("M0-01", deps=["M0-O2"]))
        issues = [{"number": 40, "title": "[owner] M0-O2: Do the thing", "state": "closed"}]
        self.assertEqual(ready_ids(g, issues=issues), ["M0-01"])

    def test_closed_issue_does_not_finish_agent_tasks(self):
        g = graph(task("M0-01", issue=5), task("M0-02", deps=["M0-01"]))
        self.assertEqual(ready_ids(g, issues=[{"number": 5, "title": "", "state": "closed"}]), ["M0-01"])

    def test_owner_merge_task_done_when_pr_merged(self):
        g = graph(task("M0-O1", assignee="owner", pr=1), task("M1-01", milestone="M1", deps=["milestone:M0"]))
        self.assertEqual(ready_ids(g, prs=[{"number": 1, "merged": False}]), ["M0-O1"])
        self.assertEqual(ready_ids(g, prs=[{"number": 1, "merged_at": "2026-11-12T00:00:00Z"}]), ["M1-01"])

    def test_not_planned_issue_does_not_finish_owner_task(self):
        g = graph(task("M0-O1", assignee="owner", issue=12), task("M0-01", deps=["M0-O1"]))
        issues = [{"number": 12, "title": "", "state": "closed", "state_reason": "not_planned"}]
        self.assertEqual(ready_ids(g, issues=issues), ["M0-O1"])
        issues[0]["state_reason"] = "completed"
        self.assertEqual(ready_ids(g, issues=issues), ["M0-01"])

    def test_search_item_shape_merged_pr_is_detected(self):
        g = graph(task("M0-O1", assignee="owner", pr=1), task("M0-01", deps=["M0-O1"]))
        item = {"number": 1, "state": "closed", "pull_request": {"merged_at": "2026-11-12T00:00:00Z"}}
        self.assertEqual(ready_ids(g, prs=[item]), ["M0-01"])
        item["pull_request"]["merged_at"] = None
        self.assertEqual(ready_ids(g, prs=[item]), ["M0-O1"])

    def test_duplicate_close_reason_does_not_finish_and_open_issue_wins(self):
        g = graph(task("M0-O1", assignee="owner", issue=12), task("M0-01", deps=["M0-O1"]))
        dup = {"number": 12, "title": "", "state": "closed", "state_reason": "duplicate"}
        self.assertEqual(ready_ids(g, issues=[dup]), ["M0-O1"])
        stray = {"number": 50, "title": "[owner] M0-O1: stray", "state": "closed", "state_reason": "completed"}
        opened = {"number": 12, "title": "", "state": "open"}
        self.assertEqual(ready_ids(g, issues=[opened, stray]), ["M0-O1"])

    def test_duplicate_title_issues_are_order_independent(self):
        g = graph(task("M0-O2", assignee="owner"), task("M0-01", deps=["M0-O2"]))
        closed = {"number": 40, "title": "[owner] M0-O2: a", "state": "closed"}
        opened = {"number": 41, "title": "[owner] M0-O2: b", "state": "open"}
        for order in itertools.permutations([closed, opened]):
            self.assertEqual(ready_ids(g, issues=list(order)), ["M0-O2"])
        self.assertEqual(ready_ids(g, issues=[closed]), ["M0-01"])

    def test_empty_milestone_dependency_is_not_satisfied(self):
        g = tasks.parse('milestones = ["M0", "M1", "M2"]\n' + milestone_tables("M0", "M1", "M2") + task("M1-01", milestone="M1", deps=["milestone:M2"]),
                     burn_down=False)
        self.assertEqual(ready_ids(g), [])
        self.assertEqual(tasks.derive(g)["M1-01"]["unmet"], ["milestone:M2"])

    def test_in_review_is_not_ready_and_claim_wins(self):
        g = graph(task("M0-01"), task("M0-02", deps=["M0-01"]), task("M0-03"))
        self.assertEqual(ready_ids(g, in_review=["M0-01"]), ["M0-03"])
        d = tasks.derive(g, in_review=["M0-01"], claimed=["M0-01"])
        self.assertEqual(d["M0-01"]["state"], "claimed")
        self.assertEqual(tasks.derive(g, in_review=["M0-01"])["M0-01"]["state"], "in-review")
        self.assertEqual(tasks.derive(g, in_review=["M0-01"])["M0-02"]["state"], "blocked")

    def test_order_is_milestone_then_file_position(self):
        g = graph(task("M1-01", milestone="M1"), task("M0-02"), task("M0-01"))
        self.assertEqual(ready_ids(g), ["M0-02", "M0-01", "M1-01"])


class DriftTest(unittest.TestCase):
    def test_reports_both_directions_and_unknown_titles(self):
        g = graph(task("M0-O1", assignee="owner", issue=12), task("M0-O2", assignee="owner", status="done", issue=13),
                  task("M0-01", pr=3))
        issues = [{"number": 12, "title": "", "state": "closed"}, {"number": 13, "title": "", "state": "open"},
                  {"number": 20, "title": "[owner] M0-O9: ghost", "state": "open"}]
        msgs = "\n".join(tasks.drift(g, issues, [{"number": 3, "merged": True}]))
        self.assertIn("M0-O1: issue closed but status is todo", msgs)
        self.assertIn("M0-O2: status done but its issue is still open", msgs)
        self.assertIn("M0-01: PR #3 merged", msgs)
        self.assertIn("M0-O9: owner issue title names an unknown task id", msgs)

    def test_reports_disagreeing_linked_issues(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        issues = [{"number": 12, "title": "", "state": "closed"},
                  {"number": 50, "title": "[owner] M0-O1: stray", "state": "open"}]
        self.assertIn("linked issues disagree", "\n".join(tasks.drift(g, issues, [])))

    def test_reports_disagreeing_title_linked_issues(self):
        g = graph(task("M0-O4", assignee="owner"))
        issues = [{"number": 60, "title": "[owner] M0-O4: a", "state": "closed"},
                  {"number": 61, "title": "[owner] M0-O4: b", "state": "open"}]
        self.assertIn("linked issues disagree", "\n".join(tasks.drift(g, issues, [])))

    def test_reports_not_planned_close(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        issues = [{"number": 12, "title": "", "state": "closed", "state_reason": "not_planned"}]
        self.assertIn("closed without completion", "\n".join(tasks.drift(g, issues, [])))


class FollowUpTest(unittest.TestCase):
    def test_parses_label_shapes_and_ignores_closed_and_unlabelled(self):
        items = [fu_issue(1, "nit", "M0"), fu_issue(2, "minor", "M1", state="closed"),
                 {"number": 3, "title": "x", "state": "open", "labels": ["follow-up", "severity:minor", "target:M0"]},
                 {"number": 4, "title": "no labels", "state": "open"}]
        fus = tasks.load_followups(items)
        self.assertEqual([(f.number, f.severity, f.target) for f in fus], [(1, "nit", "M0"), (3, "minor", "M0")])

    def test_summary_counts_by_severity_in_fixed_order(self):
        fus = tasks.load_followups([fu_issue(1, "nit"), fu_issue(2, "minor"), fu_issue(3, "minor", "M1")])
        self.assertEqual(tasks.followup_summary(fus), "open follow-ups: 3 (blocker 0, major 0, minor 2, nit 1)")
        self.assertEqual(tasks.followup_summary(fus, "M1"), "open follow-ups: 1 (blocker 0, major 0, minor 1, nit 0)")
        self.assertEqual(tasks.followup_summary([]), "open follow-ups: 0 (blocker 0, major 0, minor 0, nit 0)")

    def drift_of(self, items, *parts):
        g = graph(*parts)
        return "\n".join(tasks.followup_drift(g, tasks.load_followups(items)))

    def test_drift_missing_labels_and_unknown_target(self):
        items = [{"number": 5, "title": "x", "state": "open", "labels": ["follow-up"]},
                 fu_issue(6, target="M9")]
        msg = self.drift_of(items, task("M0-01"))
        self.assertIn("#5: follow-up has no severity:<level> label", msg)
        self.assertIn("#5: follow-up has no target:<milestone> label", msg)
        self.assertIn("#6: target milestone 'M9' is unknown", msg)

    def test_drift_blocker_is_never_deferrable(self):
        self.assertIn("#7: blockers are never deferred", self.drift_of([fu_issue(7, "blocker")], task("M0-01")))

    def test_drift_major_and_protected_areas_need_owner_ok(self):
        task0 = task("M0-01")
        self.assertIn("#8: major follow-up needs the owner-ok label", self.drift_of([fu_issue(8, "major")], task0))
        self.assertEqual("", self.drift_of([fu_issue(8, "major", labels=["owner-ok"])], task0))
        for area in ("security-rules", "sync-merge", "release"):
            msg = self.drift_of([fu_issue(9, "nit", labels=[f"area:{area}"])], task0)
            self.assertIn(f"#9: area:{area} follow-up needs the owner-ok label", msg)
            ok = self.drift_of([fu_issue(9, "nit", labels=[f"area:{area}", "owner-ok"])], task0)
            self.assertEqual("", ok)

    def test_drift_minor_and_nit_need_no_owner_ok(self):
        self.assertEqual("", self.drift_of([fu_issue(1, "minor"), fu_issue(2, "nit")], task("M0-01")))

    def test_drift_open_follow_up_after_burn_down_done(self):
        parts = [task("M0-01", status="done"), task("M0-FU", status="done", deps=["M0-01"])]
        msg = self.drift_of([fu_issue(1, "nit", "M0")], *parts)
        self.assertIn("#1: target M0 but burn-down M0-FU is already done", msg)
        self.assertEqual("", self.drift_of([fu_issue(1, "nit", "M1")], *parts))

    def test_drift_open_follow_up_after_burn_down_dropped(self):
        parts = [task("M0-01", status="done"), task("M0-FU", status="dropped", deps=["M0-01"])]
        msg = self.drift_of([fu_issue(1, "nit", "M0")], *parts)
        self.assertIn("#1: target M0 but burn-down M0-FU is already dropped", msg)

    def test_drift_open_follow_up_with_todo_burn_down_is_fine(self):
        parts = [task("M0-01"), task("M0-FU", deps=["M0-01"])]
        self.assertEqual("", self.drift_of([fu_issue(1, "nit", "M0")], *parts))

    def test_drift_conflicting_severity_or_target_labels(self):
        extra_sev = fu_issue(1, "minor", labels=["severity:major"])
        msg = self.drift_of([extra_sev], task("M0-01"))
        self.assertIn("#1: more than one severity: label", msg)
        extra_tgt = fu_issue(2, "minor", "M0", labels=["target:M1"])
        self.assertIn("#2: more than one target: label", self.drift_of([extra_tgt], task("M0-01")))

    def test_ready_burn_down_line_shows_its_open_follow_ups(self):
        g = graph(task("M0-01", status="done"), task("M0-FU", deps=["M0-01"]))
        fus = tasks.load_followups([fu_issue(1, "minor", "M0"), fu_issue(2, "nit", "M1")])
        notes = tasks.followup_notes(g, fus)
        self.assertEqual(notes, {"M0-FU": "open follow-ups: 1 (blocker 0, major 0, minor 1, nit 0)"})


class CliTest(unittest.TestCase):
    def run_cli(self, text, *args):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "tasks.toml")
            if "M0-FU" not in text:  # the CLI is strict: add the burn-down task the file must have
                text += task("M0-FU", deps=re.findall(r'id = "(M0-\d\d)"', text))
            f.write_text(HEADER + text, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = tasks.main(["--file", str(f), *args])
            return code, out.getvalue(), err.getvalue()

    def test_ready_json_filters_by_assignee(self):
        text = task("M0-01") + task("M0-O1", assignee="owner")
        code, out, _ = self.run_cli(text, "--json", "--assignee", "agent", "ready")
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in json.loads(out)], ["M0-01"])

    def test_output_is_independent_of_input_order_and_hash_seed(self):
        text = "".join(task(f"M0-0{i}") for i in range(1, 5)) + task("M0-O1", assignee="owner", issue=3)
        issues = [{"number": n, "title": f"[owner] M0-O{n}: x", "state": "open"} for n in (3, 4, 5)]
        outs = set()
        for claimed in itertools.permutations(["M0-01", "M0-02", "M0-03"]):
            for order in (issues, issues[::-1]):
                with tempfile.TemporaryDirectory() as d:
                    f = Path(d, "issues.json")
                    f.write_text(json.dumps(order))
                    outs.add(self.run_cli(text, "--json", "--issues", str(f),
                                          "--claimed", ",".join(claimed), "ready")[1])
        self.assertEqual(len(outs), 1)
        repo_file = Path(__file__).resolve().parent.parent / tasks.DEFAULT_FILE
        runs = {subprocess.run([sys.executable, "-I", tasks.__file__, "--file", str(repo_file), "--json", "status"],
                               capture_output=True, text=True, check=True,
                               env={**os.environ, "PYTHONHASHSEED": seed}).stdout for seed in ("0", "1", "42")}
        self.assertEqual(len(runs), 1)

    def test_review_lists_in_review_tasks_and_unknown_ids_exit_1(self):
        text = task("M0-01") + task("M0-02")
        code, out, _ = self.run_cli(text, "--in-review", "M0-01", "review")
        self.assertEqual((code, out.split()[0]), (0, "M0-01"))
        self.assertEqual(self.run_cli(text, "--in-review", "M0-01", "ready")[1].split()[0], "M0-02")
        code, _, err = self.run_cli(text, "--in-review", "M0-99", "review")
        self.assertEqual(code, 1)
        self.assertIn("--in-review", err)

    def test_bad_assignee_filter_exits_1(self):
        code, _, err = self.run_cli(task("M0-01"), "--assignee", "ownr", "ready")
        self.assertEqual(code, 1)
        self.assertIn("--assignee", err)

    def test_drift_without_github_input_exits_2(self):
        code, _, err = self.run_cli(task("M0-01"), "drift")
        self.assertEqual(code, 2)
        self.assertIn("--issues", err)

    def test_invalid_file_exits_1(self):
        code, _, err = self.run_cli(task("M0-01", deps=["nope"]), "ready")
        self.assertEqual(code, 1)
        self.assertIn("unknown task 'nope'", err)

    def test_unknown_claim_exits_1(self):
        code, _, err = self.run_cli(task("M0-01"), "--claimed", "M0-99", "ready")
        self.assertEqual(code, 1)
        self.assertIn("M0-99", err)

    def run_fu(self, text, items, *args):
        with tempfile.TemporaryDirectory() as d:
            fus = Path(d, "fu.json")
            fus.write_text(json.dumps({"items": items}))
            return self.run_cli(text, "--followups", str(fus), *args)

    def test_ready_prints_follow_up_summary_and_burn_down_note(self):
        text = task("M0-01", status="done") + task("M0-FU", deps=["M0-01"])
        code, out, _ = self.run_fu(text, [fu_issue(1, "minor", "M0")], "ready")
        self.assertEqual(code, 0)
        self.assertIn("M0-FU", out)
        self.assertIn("M0-FU", out.splitlines()[0])
        self.assertIn("[open follow-ups: 1 (blocker 0, major 0, minor 1, nit 0)]", out.splitlines()[0])
        # total differs from the milestone's count, so the note cannot be mistaken for the summary line
        code, out, _ = self.run_fu(text, [fu_issue(1, "minor", "M0"), fu_issue(2, "nit", "M1")], "ready")
        self.assertIn("[open follow-ups: 1 (", out.splitlines()[0])
        self.assertEqual(out.splitlines()[-1], "open follow-ups: 2 (blocker 0, major 0, minor 1, nit 1)")

    def test_plain_ready_output_is_unchanged_without_followups_file(self):
        text = task("M0-01", status="done") + task("M0-FU", deps=["M0-01"])
        code, out, _ = self.run_cli(text, "ready")
        self.assertEqual(code, 0)
        self.assertNotIn("follow-ups", out)

    def test_ready_json_stays_a_plain_list(self):
        text = task("M0-01")
        code, out, _ = self.run_fu(text, [fu_issue(1)], "--json", "ready")
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out), list)

    def test_followups_command_lists_and_summarises(self):
        text = task("M0-01")
        code, out, _ = self.run_fu(text, [fu_issue(1, "nit"), fu_issue(2, "minor")], "followups")
        self.assertEqual(code, 0)
        self.assertIn("#1", out)
        self.assertIn("open follow-ups: 2 (blocker 0, major 0, minor 1, nit 1)", out)
        code, out, _ = self.run_fu(text, [fu_issue(1, "nit"), fu_issue(2, "minor")], "--json", "followups")
        data = json.loads(out)
        self.assertEqual(data["counts"], {"blocker": 0, "major": 0, "minor": 1, "nit": 1})

    def test_drift_includes_follow_up_problems(self):
        code, out, _ = self.run_fu(task("M0-01"), [fu_issue(3, "blocker")], "drift")
        self.assertEqual(code, 0)
        self.assertIn("#3: blockers are never deferred", out)

    def test_followups_without_file_is_reported_not_guessed(self):
        code, out, _ = self.run_cli(task("M0-01"), "followups")
        self.assertEqual(code, 1)

    def test_issues_file_accepts_search_api_shape(self):
        text = task("M0-O1", assignee="owner", issue=12) + task("M0-01", deps=["M0-O1"])
        with tempfile.TemporaryDirectory() as d:
            issues = Path(d, "issues.json")
            issues.write_text(json.dumps({"items": [{"number": 12, "title": "", "state": "closed"}]}))
            code, out, _ = self.run_cli(text, "--issues", str(issues), "ready")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("M0-01"))

    def test_empty_github_input_file_is_an_error_not_zero_items(self):
        text = task("M0-01")
        for name, body in {"empty": "", "blank": "\n  \n"}.items():
            for flag in ("--issues", "--prs", "--followups"):
                with self.subTest(name, flag=flag), tempfile.TemporaryDirectory() as d:
                    f = Path(d, "in.json")
                    f.write_text(body)
                    code, _, err = self.run_cli(text, flag, str(f), "ready")
                    self.assertEqual(code, 1)
                    self.assertIn("empty", err)
        with tempfile.TemporaryDirectory() as d:  # a legitimately empty result is still fine
            f = Path(d, "in.json")
            f.write_text('[{"items": []}]')
            self.assertEqual(self.run_cli(text, "--followups", str(f), "ready")[0], 0)

    def test_issues_file_accepts_paginated_slurp_and_json_lines(self):
        text = task("M0-O1", assignee="owner", issue=12) + task("M0-01", deps=["M0-O1"])
        closed = {"number": 12, "title": "", "state": "closed"}
        shapes = {
            "slurp": json.dumps([{"items": [{"number": 1, "title": "", "state": "open"}]}, {"items": [closed]}]),
            "lines": json.dumps({"number": 1, "title": "", "state": "open"}) + "\n" + json.dumps(closed) + "\n",
        }
        for name, body in shapes.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                f = Path(d, "issues.json")
                f.write_text(body)
                self.assertTrue(self.run_cli(text, "--issues", str(f), "ready")[1].startswith("M0-01"))

class OwnerDriftCheckTest(unittest.TestCase):
    """#92: an owner task that is todo while GitHub says it is finished must fail the check."""

    def check(self, g, issues=(), prs=()):
        return tasks.owner_drift(g, list(issues), list(prs))

    def test_closed_issue_with_todo_row_fails(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        msgs = "\n".join(self.check(g, [{"number": 12, "title": "", "state": "closed"}]))
        self.assertIn("M0-O1: issue #12 is closed but status is todo", msgs)

    def test_open_issue_with_todo_row_passes(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        self.assertEqual(self.check(g, [{"number": 12, "title": "", "state": "open"}]), [])

    def test_closed_issue_with_done_row_passes(self):
        g = graph(task("M0-O1", assignee="owner", status="done", issue=12))
        self.assertEqual(self.check(g, [{"number": 12, "title": "", "state": "closed"}]), [])

    def test_closed_not_planned_with_todo_row_fails_too(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        issues = [{"number": 12, "title": "", "state": "closed", "state_reason": "not_planned"}]
        self.assertIn("M0-O1", "\n".join(self.check(g, issues)))

    def test_issue_linked_by_title_counts(self):
        g = graph(task("M0-O4", assignee="owner"))
        issues = [{"number": 60, "title": "[owner] M0-O4: confirm the handle", "state": "closed"}]
        self.assertIn("M0-O4", "\n".join(self.check(g, issues)))

    def test_merged_pr_with_todo_owner_row_fails(self):
        g = graph(task("M0-O7", assignee="owner", pr=1))
        self.assertIn("M0-O7: PR #1 is merged but status is todo", "\n".join(self.check(g, prs=[{"number": 1, "merged": True}])))
        self.assertEqual(self.check(g, prs=[{"number": 1, "merged": False}]), [])

    def test_agent_tasks_are_not_part_of_the_check(self):
        g = graph(task("M0-01", pr=3, issue=12))
        issues = [{"number": 12, "title": "", "state": "closed"}]
        self.assertEqual(self.check(g, issues, [{"number": 3, "merged": True}]), [])

    def test_dropped_owner_task_passes(self):
        g = graph(task("M0-O1", assignee="owner", status="dropped", issue=12))
        self.assertEqual(self.check(g, [{"number": 12, "title": "", "state": "closed"}]), [])

    def test_missing_github_data_is_no_drift(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        self.assertEqual(tasks.owner_drift(g, None, None), [])

    def test_output_is_sorted_by_task_id_order_in_file(self):
        g = graph(task("M0-O2", assignee="owner", issue=2), task("M0-O1", assignee="owner", issue=1))
        issues = [{"number": n, "title": "", "state": "closed"} for n in (1, 2)]
        self.assertEqual([m.split(":")[0] for m in self.check(g, issues)], ["M0-O2", "M0-O1"])


class OwnerDriftCliTest(unittest.TestCase):
    run_cli = CliTest.run_cli

    def issues_file(self, d, items):
        f = Path(d, "issues.json")
        f.write_text(json.dumps(items))
        return str(f)

    def test_check_exits_1_and_names_the_task_on_drift(self):
        text = task("M0-O1", assignee="owner", issue=12)
        with tempfile.TemporaryDirectory() as d:
            f = self.issues_file(d, [{"number": 12, "title": "", "state": "closed"}])
            code, out, err = self.run_cli(text, "--issues", f, "drift", "--check")
        self.assertEqual(code, 1)
        self.assertIn("M0-O1", out + err)

    def test_check_exits_0_without_owner_drift(self):
        text = task("M0-O1", assignee="owner", issue=12)
        with tempfile.TemporaryDirectory() as d:
            f = self.issues_file(d, [{"number": 12, "title": "", "state": "open"}])
            code, out, _ = self.run_cli(text, "--issues", f, "drift", "--check")
        self.assertEqual((code, out.strip()), (0, "no drift"))

    def test_plain_drift_still_exits_0_on_drift(self):
        text = task("M0-O1", assignee="owner", issue=12)
        with tempfile.TemporaryDirectory() as d:
            f = self.issues_file(d, [{"number": 12, "title": "", "state": "closed"}])
            self.assertEqual(self.run_cli(text, "--issues", f, "drift")[0], 0)

    def test_check_ignores_follow_up_and_agent_drift(self):
        text = task("M0-01", pr=3) + task("M0-O1", assignee="owner", issue=12)
        with tempfile.TemporaryDirectory() as d:
            f = self.issues_file(d, [{"number": 12, "title": "", "state": "open"}])
            p = Path(d, "prs.json")
            p.write_text(json.dumps([{"number": 3, "merged": True}]))
            self.assertEqual(self.run_cli(text, "--issues", f, "--prs", str(p), "drift", "--check")[0], 0)

    def test_check_without_github_input_exits_2(self):
        code, _, err = self.run_cli(task("M0-O1", assignee="owner"), "drift", "--check")
        self.assertEqual(code, 2)
        self.assertIn("--issues", err)

    def test_check_with_another_command_exits_1(self):
        code, _, err = self.run_cli(task("M0-01"), "--check", "ready")
        self.assertEqual(code, 1)
        self.assertIn("--check", err)



class RetroTaskTests(unittest.TestCase):
    """Agent Usage Redesign PR 2: the R6 retro of M0.5 is a task, so M1 (which depends on milestone:M0.5) waits for it.
    The invariants must hold in every valid state of docs/tasks.toml, whatever is done (R1-01 of #128)."""

    TEXT = (Path(__file__).resolve().parent.parent / tasks.DEFAULT_FILE).read_text(encoding="utf-8")

    @staticmethod
    def mark_done(text, ids):
        """The tasks file with the given task ids set to status done."""
        blocks = text.split("[[task]]")
        for i, block in enumerate(blocks):
            if any(f'id = "{task_id}"\n' in block for task_id in ids):
                blocks[i] = block.replace('status = "todo"', 'status = "done"', 1)
        return "[[task]]".join(blocks)

    def invariants(self, graph):
        retro = [t for t in graph.tasks if t.milestone == "M0.5" and t.assignee == "retro"]
        self.assertEqual(len(retro), 1)  # whatever its status
        self.assertIn("R6", retro[0].title)
        before = {t.id for t in graph.tasks
                  if t.milestone == "M0.5" and t.id not in (retro[0].id, "M0.5-FU") and t.assignee != "owner"}
        self.assertLessEqual(before, set(retro[0].depends_on))  # every one of them, open or done: no status filter
        for t in graph.tasks:
            if t.milestone == "M0.5":
                self.assertEqual(retro[0].id in t.depends_on, t.id == "M0.5-FU", t.id)
        notes = retro[0].notes.lower()
        for word in ("baseline", "docs/agent-tuning.md", "docs/agent-metrics.csv", "pilot", "at most 3", "kill switch"):
            self.assertIn(word, notes)
        self.assertIn("milestone:M0.5", graph.by_id["M1-01"].depends_on)

    def test_the_invariants_hold_for_the_repository_file(self):
        self.invariants(tasks.parse(self.TEXT))

    def test_the_invariants_hold_when_tasks_are_marked_done_as_work_progresses(self):
        every = [t.id for t in tasks.parse(self.TEXT).tasks if t.milestone == "M0.5"]
        for done in (["M0.5-03", "M0.5-26"], ["M0.5-03", "M0.5-26", "M0.5-28"], every):
            with self.subTest(done=done[:3], n=len(done)):
                self.invariants(tasks.parse(self.mark_done(self.TEXT, done)))

    def test_the_invariants_still_catch_a_missing_dependency_and_a_missing_retro(self):
        at = self.TEXT.index('id = "M0.5-28"')
        text = self.TEXT[:at] + self.TEXT[at:].replace('"M0.5-27", ', '', 1)  # a done task must stay listed too
        self.assertNotEqual(text, self.TEXT)
        with self.assertRaises(AssertionError):
            self.invariants(tasks.parse(text))
        with self.assertRaises(AssertionError):
            self.invariants(tasks.parse(self.TEXT.replace('assignee = "retro"', 'assignee = "implementer"', 1)))


class StateBodyTest(unittest.TestCase):
    """M1-77: --state reads the claimed and in-review ids from the state issue body's JSON block."""

    TEXT = task("M0-01") + task("M0-02") + task("M0-03") + task("M0-04", deps=["M0-01"])

    def state(self, sessions=(("session_01a", ["M0-01"]),), branches=(("b/x", ["M0-02"]),), schema=1):
        data = {"schema": schema, "sessions": [{"id": sid, "tasks": ids} for sid, ids in sessions],
                "branches": [{"name": name, "in_review": ids} for name, ids in branches]}
        return f"Prose.\n\n```json\n{json.dumps(data)}\n```\n"

    def run_state(self, body, *args):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "state.md")
            f.write_text(body, encoding="utf-8")
            return CliTest.run_cli(self, self.TEXT, "--state", str(f), *args)

    def test_ready_and_review_take_their_ids_from_the_body(self):
        code, out, _ = self.run_state(self.state(), "ready")
        self.assertEqual((code, [ln.split()[0] for ln in out.splitlines()]), (0, ["M0-03"]))
        code, out, _ = self.run_state(self.state(), "review")
        self.assertEqual((code, [ln.split()[0] for ln in out.splitlines()]), (0, ["M0-02"]))
        code, out, _ = self.run_state(self.state(), "--json", "status")
        self.assertEqual({r["id"]: r["state"] for r in json.loads(out)},
                         {"M0-01": "claimed", "M0-02": "in-review", "M0-03": "ready", "M0-04": "blocked", "M0-FU": "blocked"})

    def test_state_and_explicit_lists_are_exclusive(self):
        for flag in ("--claimed", "--in-review"):
            code, _, err = self.run_state(self.state(), flag, "M0-03", "ready")
            self.assertEqual(code, 1)
            self.assertIn("--state", err)

    def test_bad_bodies_exit_1(self):
        cases = {
            "Prose only.\n": "no ```json block",
            self.state() + self.state(): "2 ```json blocks",
            "```json\n{\"schema\": 1,\n```\n": "malformed JSON",
            "```json\n{\"schema\": 1, \"sessions\": []}\n": "not closed",
            "```json\n[]\n```\n": "JSON object",
            self.state(schema=2): "schema",
            self.state(sessions=(("session_01a", "M0-01"),)): "sessions[0].tasks",
            self.state(branches=(("b/x", [1]),)): "branches[0].in_review",
            "```json\n{\"schema\": 1, \"sessions\": {}, \"branches\": []}\n```\n": "sessions",
            "```json\n{\"schema\": 1, \"sessions\": [\"x\"], \"branches\": []}\n```\n": "sessions[0]",
            "": "empty",
        }
        for body, needle in cases.items():
            with self.subTest(body=body[:40]):
                code, out, err = self.run_state(body, "ready")
                self.assertEqual((code, out), (1, ""))
                self.assertIn(needle, err)

    def test_unknown_ids_in_the_body_exit_1(self):
        code, _, err = self.run_state(self.state(sessions=(("session_01a", ["M0-99"]),)), "ready")
        self.assertEqual(code, 1)
        self.assertIn("--state", err)
        self.assertIn("M0-99", err)

    def test_reads_the_same_ids_as_state_body_py(self):
        import state_body
        import test_state_body as sample

        text = state_body.render(sample.body())
        claimed, in_review = tasks.state_ids(text)
        data = state_body.load(text)
        self.assertEqual(claimed, [t for s in data["sessions"] for t in s["tasks"]])
        self.assertEqual(in_review, [t for b in data["branches"] for t in b["in_review"]])
        self.assertEqual((claimed, in_review), (["M1-14"], ["M1-44"]))

    def test_splits_lines_and_matches_fences_like_state_body_py(self):
        import state_body
        import test_state_body as sample

        base = state_body.render(sample.body())
        data = sample.changed("next", ["line\u2028separator and next\x85line"])
        variants = {
            "crlf": base.replace("\n", "\r\n"),
            "cr": base.replace("\n", "\r"),
            # the raw characters (render dumps with ensure_ascii=False), so a str.splitlines() split breaks the JSON
            "unicode line separators inside a value": state_body.render(sample.body(data)),
            "trailing blanks on the fences": base.replace("```json\n", "```json \t\n").replace("\n```\n", "\n```\t\n"),
        }
        for name, text in variants.items():
            with self.subTest(name):
                expected = state_body.load(text)
                claimed, in_review = tasks.state_ids(text)
                self.assertEqual(claimed, [t for s in expected["sessions"] for t in s["tasks"]])
                self.assertEqual(in_review, [t for b in expected["branches"] for t in b["in_review"]])

    def test_a_fence_followed_by_a_non_fence_whitespace_char_is_no_fence_for_both_readers(self):
        import state_body
        import test_state_body as sample

        base = state_body.render(sample.body())
        self.assertTrue(base.endswith("\n```\n"))
        for ch in ("\u2028", "\x85", "\x0c"):
            texts = {
                "closing fence": base[:-4] + "```" + ch + "\nafter\n```\n",
                "opening fence": base.replace("```json\n", "```json" + ch + "\n", 1),
            }
            for name, text in texts.items():
                with self.subTest(char=repr(ch), fence=name):
                    with self.assertRaises(state_body.StateError):
                        state_body.load(text)
                    with self.assertRaises(tasks.InputError):
                        tasks.state_ids(text)


if __name__ == "__main__":
    unittest.main()
