"""Tests for scripts/tasks.py. Run: python3 -I -m unittest discover -s scripts -p 'test_tasks.py'"""

import io
import json
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


class CliTest(unittest.TestCase):
    def run_cli(self, text, *args):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "tasks.toml")
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
