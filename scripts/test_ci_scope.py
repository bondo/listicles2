"""Tests for scripts/ci_scope.py and its CI wiring (issue 229, see also 216). Run: python3 -I scripts/test_ci_scope.py

ci_scope.py decides whether the slow Gradle gate self-tests (warnings gate, JDK release gate, licensee gate) can be
affected by a pull request. It only ever answers `skip` when every changed path is known to be unrelated, and answers `run`
for anything else: unknown paths, an empty list, a push, a diff that cannot be computed. The decision is made inside
ci_scope.py (`selftests`, `gradle-exclude`); the CI jobs have no condition at all (no `if:`, `needs:` or `paths:`), so every
required check always runs and reports."""

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
        if not os.path.exists(self.marker):
            return []
        with open(self.marker, encoding="utf-8") as f:
            return f.read().split()

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


def job_in(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def wiring_problems(text):
    """What is wrong with a ci.yml text, as a list of messages (empty when the wiring is right)."""
    problems = []
    if re.search(r"^\s+paths(-ignore)?:", text, re.M):
        problems.append("workflow-level paths filter")
    for name in REQUIRED_JOBS:
        body = job_in(text, name)
        if body is None:
            problems.append(f"{name}: job missing")
            continue
        if not re.search(rf"^    name: {re.escape(name)}$", body, re.M):
            problems.append(f"{name}: check name changed")
        if re.search(r"^    if:", body, re.M):
            problems.append(f"{name}: job-level if")
        if re.search(r"^    needs:", body, re.M):
            problems.append(f"{name}: needs")
    static = job_in(text, "static") or ""
    if re.search(r"(?m)^\s*(?:-\s+)?if:", static) or "continue-on-error" in static:
        problems.append("static: if or continue-on-error")
    if "fetch-depth: 2" not in static:
        problems.append("static: no two-commit checkout")
    if not re.search(r"(?m)^        run: python3 -I scripts/ci_scope\.py selftests$", static):
        problems.append("static: does not run ci_scope.py selftests")
    if not re.search(r"read -ra exclude <<< \"\$\(python3 -I scripts/ci_scope\.py gradle-exclude\)\"", static) or not re.search(
        r"\./gradlew [^\n]*:app:lintDebug \"\$\{exclude\[@\]\}\"\n", static
    ):
        problems.append("static: gradle step does not use gradle-exclude")
    for script in ci_scope.SELFTESTS:
        if script in static:
            problems.append(f"static: calls {script} directly")
    if "scripts/hooks/run_hook_tests.py --jobs 4" not in (job_in(text, "guards") or ""):
        problems.append("guards: hook tests not run with --jobs 4")
    if "python3 -I scripts/test_ci_scope.py" not in text:
        problems.append("ci.yml does not run test_ci_scope.py")
    return problems


class CiWiring(unittest.TestCase):
    def test_real_ci_yml_has_no_problems(self):
        self.assertEqual(wiring_problems(ci_text()), [])

    def mutated(self, old, new):
        text = ci_text()
        self.assertIn(old, text)
        return wiring_problems(text.replace(old, new, 1))

    def test_job_level_if_is_flagged_on_every_required_job(self):
        for name in REQUIRED_JOBS:
            got = self.mutated(f"  {name}:\n    name: {name}\n", f"  {name}:\n    name: {name}\n    if: github.event_name == 'push'\n")
            self.assertIn(f"{name}: job-level if", got)

    def test_needs_is_flagged_on_every_required_job(self):
        for name in REQUIRED_JOBS:
            got = self.mutated(f"  {name}:\n    name: {name}\n", f"  {name}:\n    name: {name}\n    needs: [wrapper]\n")
            self.assertIn(f"{name}: needs", got)

    def test_renamed_check_is_flagged(self):
        self.assertIn("workflow-lint: check name changed", self.mutated("    name: workflow-lint\n", "    name: workflow-linting\n"))

    def test_removed_job_is_flagged(self):
        self.assertIn("secrets: job missing", self.mutated("  secrets:\n    name: secrets\n", "  secrets-moved:\n    name: secrets-moved\n"))

    def test_paths_filters_are_flagged(self):
        for key in ("paths", "paths-ignore"):
            got = self.mutated("on:\n  pull_request:\n", f"on:\n  pull_request:\n    {key}: ['docs/**']\n")
            self.assertIn("workflow-level paths filter", got)

    def test_condition_in_static_is_flagged(self):
        got = self.mutated("      - name: gradle repos check tests", "      - if: false\n        name: gradle repos check tests")
        self.assertIn("static: if or continue-on-error", got)

    def test_static_without_the_scope_script_is_flagged(self):
        self.assertIn("static: does not run ci_scope.py selftests", self.mutated("ci_scope.py selftests", "ci_scope.py nothing"))
        self.assertIn("static: gradle step does not use gradle-exclude", self.mutated(':app:lintDebug "${exclude[@]}"', ":app:lintDebug"))
        self.assertIn("static: no two-commit checkout", self.mutated("fetch-depth: 2", "fetch-depth: 1"))

    def test_direct_call_of_a_self_test_in_static_is_flagged(self):
        got = self.mutated("      - name: gradle repos check tests", "      - run: python3 -I scripts/test_warnings_gate.py\n      - name: gradle repos check tests")
        self.assertIn("static: calls scripts/test_warnings_gate.py directly", got)

    def test_hook_tests_without_jobs_are_flagged(self):
        self.assertIn("guards: hook tests not run with --jobs 4", self.mutated("run_hook_tests.py --jobs 4", "run_hook_tests.py"))

    def test_job_lookup_of_a_missing_job_is_none(self):
        self.assertIsNone(job_in(ci_text(), "no-such-job"))

    def test_jdk_release_gate_tests_are_in_the_ci_selftest_list(self):
        """225 R2-01: ci.yml reaches test_jdk_release_gate.py through `ci_scope.py selftests`."""
        self.assertIn("scripts/test_jdk_release_gate.py", ci_scope.SELFTESTS)

    def test_scope_tests_run_in_ci_and_verify(self):
        self.assertIn("python3 -I scripts/test_ci_scope.py", ci_text())
        self.assertIn("python3 -I scripts/test_ci_scope.py", (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8"))

    def test_hook_tests_run_in_parallel_in_verify(self):
        self.assertIn("scripts/hooks/run_hook_tests.py --jobs 4", (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
