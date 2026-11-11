"""Tests for scripts/tasks.py. Run: python3 -I -m unittest discover -s scripts -p 'test_tasks.py'"""

import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks  # noqa: E402

HEADER = 'milestones = ["M0", "M1"]\n'


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


class ValidateTest(unittest.TestCase):
    def test_repository_task_file_is_valid(self):
        path = Path(__file__).resolve().parent.parent / tasks.DEFAULT_FILE
        g = tasks.parse(path.read_text(encoding="utf-8"))  # strict: burn-down tasks required
        self.assertGreater(len(g.tasks), 0)

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

    def test_burn_down_id_is_reserved_for_burn_down(self):
        self.assertIn("id must look like", errors_of(task("M0-XX")))

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

    def test_ready_json_is_deterministic(self):
        text = task("M0-01") + task("M0-O1", assignee="owner")
        code, out, _ = self.run_cli(text, "--json", "--assignee", "agent", "ready")
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in json.loads(out)], ["M0-01"])
        self.assertEqual(out, self.run_cli(text, "--json", "--assignee", "agent", "ready")[1])

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
        self.assertIn("open follow-ups: 1 (blocker 0, major 0, minor 1, nit 0)", out)

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


if __name__ == "__main__":
    unittest.main()
