"""Tests for scripts/tasks.py. Run: python3 -I -m unittest discover -s scripts -p 'test_tasks.py'"""

import io
import itertools
import json
import os
import subprocess
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
    return tasks.parse(HEADER + "\n".join(parts))


def errors_of(*parts, header=HEADER):
    with unittest.TestCase().assertRaises(tasks.TaskFileError) as cm:
        tasks.parse(header + "\n".join(parts))
    return "\n".join(cm.exception.errors)


def ready_ids(g, **kw):
    d = tasks.derive(g, **kw)
    return [t.id for t in sorted(g.tasks, key=lambda t: tasks.order_key(g, t)) if d[t.id]["state"] == "ready"]


class ValidateTest(unittest.TestCase):
    def test_repository_task_file_is_valid(self):
        path = Path(__file__).resolve().parent.parent / tasks.DEFAULT_FILE
        g = tasks.parse(path.read_text(encoding="utf-8"))
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
        g = tasks.parse('milestones = ["M0", "M1", "M2"]\n' + task("M1-01", milestone="M1", deps=["milestone:M2"]))
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

    def test_reports_not_planned_close(self):
        g = graph(task("M0-O1", assignee="owner", issue=12))
        issues = [{"number": 12, "title": "", "state": "closed", "state_reason": "not_planned"}]
        self.assertIn("closed without completion", "\n".join(tasks.drift(g, issues, [])))


class CliTest(unittest.TestCase):
    def run_cli(self, text, *args):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "tasks.toml")
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

    def test_issues_file_accepts_search_api_shape(self):
        text = task("M0-O1", assignee="owner", issue=12) + task("M0-01", deps=["M0-O1"])
        with tempfile.TemporaryDirectory() as d:
            issues = Path(d, "issues.json")
            issues.write_text(json.dumps({"items": [{"number": 12, "title": "", "state": "closed"}]}))
            code, out, _ = self.run_cli(text, "--issues", str(issues), "ready")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("M0-01"))

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


if __name__ == "__main__":
    unittest.main()
