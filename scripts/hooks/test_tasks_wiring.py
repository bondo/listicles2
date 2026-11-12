"""Wiring tests for M0-10: scripts/tasks.py and its tests must run in verify.sh and CI, and the process docs need explicit
CODEOWNERS entries. Includes negative cases for the helpers, so a commented-out step or a missing entry cannot pass.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import re
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TASKS_TESTS = "python3 -I scripts/test_tasks.py"
TASKS_VALIDATE = "python3 -I scripts/tasks.py validate"
PROCESS_DOCS = (
    "docs/ORCHESTRATION.md",
    "docs/orchestrator-state.md",
    "docs/tasks.toml",
    "docs/FOLLOW-UPS.md",
    "scripts/tasks.py",
)
OWNER = "@bondo"


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def active_lines(text):
    """Non-empty lines that are not comments (so a commented-out step does not count)."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def runs(text, command):
    return any(command in ln for ln in active_lines(text))


def top_level_step(text, command):
    return runs(text, command)


def job(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def explicit_owners(codeowners, path):
    """Owners of a line that names exactly /<path> (a directory pattern such as /scripts/ does not count)."""
    for ln in active_lines(codeowners):
        parts = ln.split()
        if parts and parts[0] == "/" + path:
            return parts[1:]
    return None


class HelperNegativeCases(unittest.TestCase):
    def test_commented_out_command_does_not_count(self):
        self.assertFalse(runs(f"# {TASKS_VALIDATE}\n", TASKS_VALIDATE))
        self.assertTrue(runs(f"step tasks {TASKS_VALIDATE}\n", TASKS_VALIDATE))

    def test_missing_job_is_none(self):
        self.assertIsNone(job("jobs:\n  a:\n    x: 1\n", "tasks"))

    def test_directory_pattern_is_not_an_explicit_entry(self):
        self.assertIsNone(explicit_owners("/scripts/    @bondo\n", "scripts/tasks.py"))
        self.assertIsNone(explicit_owners("# /scripts/tasks.py @bondo\n", "scripts/tasks.py"))
        self.assertEqual(explicit_owners("/scripts/tasks.py @bondo\n", "scripts/tasks.py"), ["@bondo"])

    def test_entry_without_owner_is_not_ownership(self):
        self.assertEqual(explicit_owners("/docs/tasks.toml\n", "docs/tasks.toml"), [])


class RunsNegativeCases(unittest.TestCase):
    def test_masked_exit_status_does_not_count(self):
        self.assertFalse(runs(f"step tasks-validate {TASKS_VALIDATE} || true\n", TASKS_VALIDATE))
        self.assertFalse(runs(f"        run: {TASKS_VALIDATE} || true\n", TASKS_VALIDATE))
        self.assertFalse(runs(f"        run: {TASKS_VALIDATE} ; true\n", TASKS_VALIDATE))
        self.assertFalse(runs(f"step t {TASKS_VALIDATE} && true\n", TASKS_VALIDATE))

    def test_extra_arguments_or_prefix_do_not_count(self):
        self.assertFalse(runs(f"step t echo {TASKS_VALIDATE}\n", TASKS_VALIDATE))
        self.assertFalse(runs(f"step t {TASKS_VALIDATE} --dry\n", TASKS_VALIDATE))

    def test_plain_forms_count(self):
        self.assertTrue(runs(f"step tasks-validate {TASKS_VALIDATE}\n", TASKS_VALIDATE))
        self.assertTrue(runs(f"      - run: {TASKS_VALIDATE}\n", TASKS_VALIDATE))
        self.assertTrue(runs(f"        run: {TASKS_VALIDATE}\n", TASKS_VALIDATE))

    def test_step_inside_a_branch_is_not_top_level(self):
        nested = f"if [ \"$FAST\" = 0 ]; then\n  step t {TASKS_VALIDATE}\nelse\n  echo skip\nfi\n"
        self.assertFalse(top_level_step(nested, TASKS_VALIDATE))
        self.assertTrue(top_level_step(f"step t {TASKS_VALIDATE}\n", TASKS_VALIDATE))
        self.assertFalse(top_level_step(f"# step t {TASKS_VALIDATE}\n", TASKS_VALIDATE))
        self.assertFalse(top_level_step(f"step t {TASKS_VALIDATE} || true\n", TASKS_VALIDATE))


class VerifyRunsTasks(unittest.TestCase):
    def test_verify_runs_tasks_tests(self):
        self.assertTrue(top_level_step(read("scripts", "verify.sh"), TASKS_TESTS))

    def test_verify_runs_tasks_validate(self):
        self.assertTrue(top_level_step(read("scripts", "verify.sh"), TASKS_VALIDATE))

    def test_verify_runs_them_even_in_fast_mode(self):
        """They take under a second; --fast only skips the slow Gradle tests."""
        verify = read("scripts", "verify.sh")
        fast = re.search(r'if \[ "\$FAST" = 0 \]; then(.*?)\nelse', verify, re.S)
        self.assertIsNotNone(fast, "verify.sh FAST block not found")
        self.assertNotIn("tasks.py", fast.group(1))
        self.assertNotIn("test_tasks.py", fast.group(1))


class CiRunsTasks(unittest.TestCase):
    def setUp(self):
        self.ci = read(".github", "workflows", "ci.yml")
        self.tasks_job = job(self.ci, "tasks")

    def test_ci_has_a_tasks_job(self):
        self.assertIsNotNone(self.tasks_job, "ci.yml needs a `tasks` job")

    def test_tasks_job_checks_out_and_runs_both_commands(self):
        self.assertIn("actions/checkout", self.tasks_job)
        self.assertTrue(runs(self.tasks_job, TASKS_TESTS))
        self.assertTrue(runs(self.tasks_job, TASKS_VALIDATE))

    def test_tasks_job_is_not_disabled_or_allowed_to_fail(self):
        self.assertNotRegex(self.tasks_job, r"(?m)^\s*if:")
        self.assertNotIn("continue-on-error", self.tasks_job)


class CodeownersCoverProcessDocs(unittest.TestCase):
    def test_every_process_doc_has_an_explicit_owner_entry(self):
        owners = read(".github", "CODEOWNERS")
        for path in PROCESS_DOCS:
            self.assertEqual(explicit_owners(owners, path), [OWNER], path)


if __name__ == "__main__":
    unittest.main()
