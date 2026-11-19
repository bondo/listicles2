"""Tests for scripts/ci_scope.py and its CI wiring (issue 229, see also 216). Run: python3 -I scripts/test_ci_scope.py

ci_scope.py decides whether the slow Gradle gate self-tests (warnings gate, JDK release gate, licensee gate) can be
affected by a pull request. It only ever answers `skip` when every changed path is known to be unrelated, and answers `run`
for anything else: unknown paths, an empty list, a push, a diff that cannot be computed. The CI jobs keep reporting either
way (the decision is a step-level `if:`, never a job-level one, so a required check is never skipped or missing)."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_scope  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ci_scope.py"
REQUIRED_JOBS = ("wrapper", "static", "unit", "firebase", "ui", "guards", "secrets", "tasks", "python-lint", "workflow-lint")


class Classify(unittest.TestCase):
    def test_prose_and_tooling_paths_skip(self):
        for p in ("docs/PLAN.md", "handoff/x.md", "agents/prompts/reviewer.md", "firebase/test/rules.test.ts", "scripts/tasks.py",
                  ".githooks/pre-push", ".claude/settings.json", "CLAUDE.md", "README.md", "app/src/main/kotlin/A.kt",
                  "core/domain/src/test/kotlin/B.kt", "app/src/main/res/values-da/strings.xml"):
            self.assertEqual(ci_scope.gradle_selftests([p]), "skip", p)

    def test_every_gradle_input_runs(self):
        for p in ("build.gradle.kts", "settings.gradle.kts", "app/build.gradle.kts", "core/domain/build.gradle.kts",
                  "gradle/libs.versions.toml", "gradle/verification-metadata.xml", "gradle/wrapper/gradle-wrapper.properties",
                  "gradle.properties", "gradlew", "config/licensee/fixture/build.gradle.kts", "config/detekt/detekt.yml",
                  "buildSrc/src/main/kotlin/x.kt", "scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py",
                  "scripts/ci_scope.py", ".github/workflows/ci.yml", "app/src/main/build.gradle.kts"):
            self.assertEqual(ci_scope.gradle_selftests([p]), "run", p)

    def test_one_relevant_path_among_unrelated_ones_runs(self):
        self.assertEqual(ci_scope.gradle_selftests(["docs/a.md", "docs/b.md", "gradle/libs.versions.toml"]), "run")

    def test_unknown_paths_run(self):
        for p in ("new-top-level-dir/x", "Makefile", "x.kt", "src/main/A.kt", "docs/../build.gradle.kts", "/abs/path", ""):
            self.assertEqual(ci_scope.gradle_selftests([p]), "run", p)

    def test_empty_list_runs(self):
        self.assertEqual(ci_scope.gradle_selftests([]), "run")


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def merge_repo(path_to_change):
    """A repo whose HEAD is a merge commit (like the pull_request checkout) that changes `path_to_change` against its first parent."""
    d = tempfile.mkdtemp(prefix="ci-scope-")
    git(d, "init", "-q", "-b", "main")
    git(d, "commit", "-q", "--allow-empty", "-m", "base")
    git(d, "checkout", "-q", "-b", "pr")
    full = os.path.join(d, path_to_change)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write("x\n")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "change")
    git(d, "checkout", "-q", "main")
    git(d, "commit", "-q", "--allow-empty", "-m", "main moved")
    git(d, "merge", "-q", "--no-ff", "-m", "merge", "pr")
    return d


def run_cli(cwd, *args, event="pull_request"):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GITHUB_EVENT_NAME")}
    if event is not None:
        env["GITHUB_EVENT_NAME"] = event
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


class GradleExclude(unittest.TestCase):
    """`gradle-exclude` prints the Gradle arguments that drop the licensee self-test, or nothing."""

    SKIP = (0, "-x testLicenseeGate")
    RUN = (0, "")

    def test_docs_only_pull_request_excludes_it(self):
        self.assertEqual(run_cli(merge_repo("docs/x.md"), "gradle-exclude"), self.SKIP)

    def test_build_file_pull_request_keeps_it(self):
        self.assertEqual(run_cli(merge_repo("gradle/libs.versions.toml"), "gradle-exclude"), self.RUN)

    def test_licensee_config_keeps_it(self):
        self.assertEqual(run_cli(merge_repo("config/licensee/allowed.txt"), "gradle-exclude"), self.RUN)

    def test_push_keeps_it(self):
        self.assertEqual(run_cli(merge_repo("docs/x.md"), "gradle-exclude", event="push"), self.RUN)

    def test_missing_event_keeps_it(self):
        self.assertEqual(run_cli(merge_repo("docs/x.md"), "gradle-exclude", event=None), self.RUN)

    def test_head_without_two_parents_keeps_it(self):
        d = tempfile.mkdtemp(prefix="ci-scope-")
        git(d, "init", "-q", "-b", "main")
        git(d, "commit", "-q", "--allow-empty", "-m", "only")
        self.assertEqual(run_cli(d, "gradle-exclude"), self.RUN)

    def test_not_a_repository_keeps_it(self):
        self.assertEqual(run_cli(tempfile.mkdtemp(prefix="ci-scope-nogit-"), "gradle-exclude"), self.RUN)

    def test_odd_file_names_are_read_literally(self):
        self.assertEqual(run_cli(merge_repo("docs/a b\"c.md"), "gradle-exclude"), self.SKIP)
        self.assertEqual(run_cli(merge_repo("weird dir/x.md"), "gradle-exclude"), self.RUN)

    def test_unknown_command_fails(self):
        self.assertNotEqual(run_cli(merge_repo("docs/x.md"), "nope")[0], 0)
        self.assertNotEqual(run_cli(merge_repo("docs/x.md"))[0], 0)


# A fake self-test script appends its word to a `marker` file next to it.
MARK = "import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marker'), 'a').write('%s\\n')\n"


class Selftests(unittest.TestCase):
    """`selftests [--scripts a b]` runs the gate self-test scripts when the PR can affect them, else none of them."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ci-scope-fakes-")
        self.marker = os.path.join(self.tmp, "marker")
        self.ok = os.path.join(self.tmp, "ok.py")
        self.bad = os.path.join(self.tmp, "bad.py")
        with open(self.ok, "w", encoding="utf-8") as f:
            f.write(MARK % "ok")
        with open(self.bad, "w", encoding="utf-8") as f:
            f.write(MARK % "bad" + "raise SystemExit(1)\n")

    def ran(self):
        return open(self.marker, encoding="utf-8").read().split() if os.path.exists(self.marker) else []

    def selftests(self, repo, *scripts, event="pull_request"):
        return run_cli(repo, "selftests", "--scripts", *scripts, event=event)

    def test_docs_only_pull_request_runs_none(self):
        rc, out = self.selftests(merge_repo("docs/x.md"), self.ok, self.bad)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.ran(), [])
        self.assertIn("skipped", out)

    def test_build_file_pull_request_runs_all(self):
        rc, out = self.selftests(merge_repo("build.gradle.kts"), self.ok, self.ok)
        self.assertEqual((rc, self.ran()), (0, ["ok", "ok"]), out)

    def test_push_runs_all(self):
        rc, out = self.selftests(merge_repo("docs/x.md"), self.ok, event="push")
        self.assertEqual((rc, self.ran()), (0, ["ok"]), out)

    def test_a_failing_script_fails_the_step_and_the_others_still_run(self):
        rc, out = self.selftests(merge_repo("build.gradle.kts"), self.bad, self.ok)
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(sorted(self.ran()), ["bad", "ok"])

    def test_a_missing_script_fails_the_step(self):
        rc, out = self.selftests(merge_repo("build.gradle.kts"), os.path.join(self.tmp, "nope.py"))
        self.assertNotEqual(rc, 0, out)

    def test_the_default_scripts_are_the_warnings_and_jdk_gate_tests(self):
        self.assertEqual(ci_scope.SELFTESTS, ("scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py"))
        for p in ci_scope.SELFTESTS:
            self.assertTrue((ROOT / p).is_file(), p)


def ci_text():
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def job(name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", ci_text(), re.S | re.M)
    if not m:
        raise AssertionError(f"job {name} not found in ci.yml")
    return m.group(1)


class CiWiring(unittest.TestCase):
    def test_every_required_check_is_still_a_job_without_a_job_level_condition(self):
        """A job that is skipped by a job-level `if:` still reports success, but a renamed or removed one is missing."""
        for name in REQUIRED_JOBS:
            body = job(name)
            self.assertIsNotNone(re.search(rf"^    name: {re.escape(name)}$", body, re.M), f"{name}: the check name must stay {name}")
            self.assertIsNone(re.search(r"^    if:", body, re.M), f"{name}: no job-level if:, only step-level ones")
            self.assertIsNone(re.search(r"^    needs:", body, re.M), f"{name}: no needs:, so the jobs stay parallel")

    def test_no_paths_filter_on_the_workflow(self):
        self.assertIsNone(re.search(r"^\s+paths(-ignore)?:", ci_text(), re.M), "a workflow-level paths filter leaves required checks missing")

    def test_static_job_has_no_condition_at_all(self):
        """scripts/check_gradle_repos.py forbids if: and continue-on-error in the static job; the decision lives in ci_scope.py."""
        body = job("static")
        self.assertIsNone(re.search(r"(?m)^\s*(?:-\s+)?if:", body))
        self.assertNotIn("continue-on-error", body)

    def test_static_job_uses_a_two_commit_checkout_and_the_script_for_both_decisions(self):
        body = job("static")
        self.assertIn("fetch-depth: 2", body)
        self.assertRegex(body, r"(?m)^        run: python3 -I scripts/ci_scope\.py selftests$")
        self.assertRegex(body, r"exclude=\$\(python3 -I scripts/ci_scope\.py gradle-exclude\)")
        self.assertRegex(body, r"\./gradlew [^\n]*:app:lintDebug \$exclude\n")

    def test_the_self_tests_are_no_longer_called_directly_from_the_static_job(self):
        body = job("static")
        for script in ci_scope.SELFTESTS:
            self.assertNotIn(script, body)

    def test_jdk_release_gate_tests_are_in_the_ci_selftest_list(self):
        """225 R2-01: ci.yml reaches test_jdk_release_gate.py through `ci_scope.py selftests`."""
        self.assertIn("scripts/test_jdk_release_gate.py", ci_scope.SELFTESTS)

    def test_scope_tests_run_in_ci_and_verify(self):
        self.assertIn("python3 -I scripts/test_ci_scope.py", ci_text())
        self.assertIn("python3 -I scripts/test_ci_scope.py", (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8"))

    def test_hook_tests_run_in_parallel_in_ci_and_verify(self):
        self.assertIn("scripts/hooks/run_hook_tests.py --jobs 4", job("guards"))
        self.assertIn("scripts/hooks/run_hook_tests.py --jobs 4", (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8"))

    def test_job_lookup_fails_loudly(self):
        with self.assertRaises(AssertionError):
            job("no-such-job")


if __name__ == "__main__":
    unittest.main()
