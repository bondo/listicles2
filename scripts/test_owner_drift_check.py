"""Tests for scripts/check_owner_drift.sh (#92): the CI gate that fails when an owner task is `todo` while its GitHub
issue is closed or its PR is merged. A fake `gh` on PATH stands in for GitHub.
Run: python3 -I scripts/test_owner_drift_check.py"""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_owner_drift.sh"

FAKE_GH = """#!/usr/bin/env bash
# Fake gh: records every call, fails the first FAKE_GH_FAILS calls, then answers from fixture files.
echo "$*" >> "$FAKE_GH_LOG"
n=$(wc -l < "$FAKE_GH_LOG")
if [ "$n" -le "${FAKE_GH_FAILS:-0}" ]; then echo "gh: HTTP 502" >&2; exit 1; fi
case "$*" in
  *is:pr*) cat "$FAKE_GH_PRS" ;;
  *) cat "$FAKE_GH_ISSUES" ;;
esac
"""

TASKS = """milestones = ["M0"]

[[milestone]]
id = "M0"
title = "Title M0"
purpose = "Purpose M0."

[[task]]
id = "M0-01"
title = "agent work"
milestone = "M0"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = []

[[task]]
id = "M0-O1"
title = "owner work"
milestone = "M0"
status = "todo"
assignee = "owner"
risk = "normal"
depends_on = []
issue = 12

[[task]]
id = "M0-FU"
title = "burn down"
milestone = "M0"
status = "todo"
assignee = "implementer"
risk = "normal"
depends_on = ["M0-01"]
"""


def slurp(*items):
    return json.dumps([{"total_count": len(items), "items": list(items)}])


class OwnerDriftScriptTest(unittest.TestCase):
    def run_script(self, issues, prs="[]", fails=0, retries="3"):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bin").mkdir()
            gh = d / "bin" / "gh"
            gh.write_text(FAKE_GH)
            gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
            (d / "issues.json").write_text(issues)
            (d / "prs.json").write_text(prs)
            (d / "tasks.toml").write_text(TASKS)
            env = {
                "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "HOME": str(d),
                "FAKE_GH_LOG": str(d / "gh.log"), "FAKE_GH_ISSUES": str(d / "issues.json"),
                "FAKE_GH_PRS": str(d / "prs.json"), "FAKE_GH_FAILS": str(fails),
                "GITHUB_REPOSITORY": "acme/widgets", "OWNER_DRIFT_TASKS": str(d / "tasks.toml"),
                "OWNER_DRIFT_RETRIES": retries, "OWNER_DRIFT_SLEEP": "0",
            }
            (d / "gh.log").write_text("")
            p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env, cwd=ROOT)
            return p.returncode, p.stdout + p.stderr, (d / "gh.log").read_text().splitlines()

    def test_open_issue_with_todo_row_passes(self):
        code, out, _ = self.run_script(slurp({"number": 12, "title": "[owner] M0-O1: x", "state": "open"}))
        self.assertEqual(code, 0, out)
        self.assertIn("no drift", out)

    def test_closed_issue_with_todo_row_fails_and_names_the_task(self):
        code, out, _ = self.run_script(slurp({"number": 12, "title": "[owner] M0-O1: x", "state": "closed"}))
        self.assertEqual(code, 1, out)
        self.assertIn("M0-O1", out)

    def test_searches_the_repository_in_github_repository(self):
        _, _, calls = self.run_script(slurp({"number": 12, "title": "", "state": "open"}))
        self.assertTrue(calls and all("repo:acme/widgets" in c for c in calls), calls)

    def test_persistent_gh_failure_fails_the_check_after_retries(self):
        code, out, calls = self.run_script(slurp(), fails=99, retries="3")
        self.assertEqual(code, 1, out)
        self.assertEqual(len(calls), 3)
        self.assertIn("gh", out)

    def test_transient_gh_failure_is_retried(self):
        code, out, _ = self.run_script(slurp({"number": 12, "title": "", "state": "open"}), fails=1)
        self.assertEqual(code, 0, out)

    def test_empty_gh_output_is_an_error_not_no_drift(self):
        code, out, _ = self.run_script("")
        self.assertEqual(code, 1, out)
        self.assertNotIn("no drift", out)


class ScriptFileTest(unittest.TestCase):
    def test_script_exists_and_is_executable(self):
        self.assertTrue(SCRIPT.is_file(), "scripts/check_owner_drift.sh must exist")
        self.assertTrue(os.access(SCRIPT, os.X_OK), "scripts/check_owner_drift.sh must be executable")


if __name__ == "__main__":
    unittest.main()
