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
        for p in ("docs/PLAN.md", "handoff/x.md", "agents/prompts/reviewer.md", "firebase/test/rules.test.ts", "scripts/tasks.py", ".githooks/pre-push",
                  ".claude/settings.json", "CLAUDE.md", "README.md", "app/src/main/kotlin/A.kt", "core/domain/src/test/kotlin/B.kt",
                  "app/src/main/res/values-da/strings.xml"):
            self.assertEqual(ci_scope.gradle_selftests([p]), "skip", p)

    def test_every_gradle_input_runs(self):
        for p in ("build.gradle.kts", "settings.gradle.kts", "app/build.gradle.kts", "core/domain/build.gradle.kts", "gradle/libs.versions.toml",
                  "gradle/verification-metadata.xml", "gradle/wrapper/gradle-wrapper.properties", "gradle.properties", "gradlew",
                  "config/licensee/fixture/build.gradle.kts", "config/detekt/detekt.yml", "buildSrc/src/main/kotlin/x.kt",
                  "scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py", "scripts/ci_scope.py", ".github/workflows/ci.yml",
                  "app/src/main/build.gradle.kts"):
            self.assertEqual(ci_scope.gradle_selftests([p]), "run", p)

    def test_unknown_paths_run(self):
        for p in ("new-top-level-dir/x", "Makefile", "x.kt", "src/main/A.kt", "docs/../build.gradle.kts", "/abs/path", ""):
            self.assertEqual(ci_scope.gradle_selftests([p]), "run", p)

    def test_empty_list_and_one_relevant_path_among_unrelated_ones_run(self):
        self.assertEqual(ci_scope.gradle_selftests([]), "run")
        self.assertEqual(ci_scope.gradle_selftests(["docs/a.md", "docs/b.md", "gradle/libs.versions.toml"]), "run")


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def merge_repo(path_to_change):
    """A repo whose HEAD is a merge commit (like the pull_request checkout) that changes `path_to_change` against its first parent."""
    d = tempfile.mkdtemp(prefix="ci-scope-")
    for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "base"), ("checkout", "-q", "-b", "pr")):
        git(d, *args)
    full = Path(d, path_to_change)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text("x\n", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "change"), ("checkout", "-q", "main"), ("commit", "-q", "--allow-empty", "-m", "moved"),
                 ("merge", "-q", "--no-ff", "-m", "merge", "pr")):
        git(d, *args)
    return d


def run_cli(cwd, *args, event="pull_request"):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GITHUB_EVENT_NAME")}
    if event is not None:
        env["GITHUB_EVENT_NAME"] = event
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


class GradleExclude(unittest.TestCase):
    """`gradle-exclude` prints the Gradle arguments that drop the licensee self-test, or nothing (fail closed)."""

    def test_cases(self):
        single = tempfile.mkdtemp(prefix="ci-scope-")  # HEAD is not a merge commit
        git(single, "init", "-q", "-b", "main")
        git(single, "commit", "-q", "--allow-empty", "-m", "only")
        skip, keep = (0, "-x testLicenseeGate"), (0, "")
        cases = [  # (what, repo, event, expected)
            ("docs-only PR", merge_repo("docs/x.md"), "pull_request", skip),
            ("odd file name", merge_repo('docs/a b"c.md'), "pull_request", skip),
            ("build file PR", merge_repo("gradle/libs.versions.toml"), "pull_request", keep),
            ("licensee config PR", merge_repo("config/licensee/allowed.txt"), "pull_request", keep),
            ("unknown directory with a space", merge_repo("weird dir/x.md"), "pull_request", keep),
            ("push", merge_repo("docs/x.md"), "push", keep),
            ("no event", merge_repo("docs/x.md"), None, keep),
            ("not a merge commit", single, "pull_request", keep),
            ("not a repository", tempfile.mkdtemp(prefix="ci-scope-nogit-"), "pull_request", keep),
        ]
        for what, repo, event, want in cases:
            self.assertEqual(run_cli(repo, "gradle-exclude", event=event), want, what)

    def test_unknown_command_fails(self):
        repo = merge_repo("docs/x.md")
        self.assertNotEqual(run_cli(repo, "nope")[0], 0)
        self.assertNotEqual(run_cli(repo)[0], 0)


# A fake self-test script appends its word to a `marker` file next to it.
MARK = "import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marker'), 'a').write('%s\\n')\n"


class Selftests(unittest.TestCase):
    """`selftests [--scripts a b]` runs the gate self-test scripts when the PR can affect them, else none of them."""

    def run_case(self, change, *scripts, event="pull_request"):
        """Runs fake scripts ('ok', 'bad', 'nope' = missing) and returns (exit code, output, words the fakes recorded)."""
        tmp = tempfile.mkdtemp(prefix="ci-scope-fakes-")
        for name, tail in (("ok", ""), ("bad", "raise SystemExit(1)\n")):
            with open(os.path.join(tmp, name + ".py"), "w", encoding="utf-8") as f:
                f.write(MARK % name + tail)
        rc, out = run_cli(merge_repo(change), "selftests", "--scripts", *(os.path.join(tmp, n + ".py") for n in scripts), event=event)
        marker = Path(tmp, "marker")
        return rc, out, marker.read_text(encoding="utf-8").split() if marker.exists() else []

    def test_cases(self):
        rc, out, ran = self.run_case("docs/x.md", "ok", "bad")
        self.assertEqual((rc, ran), (0, []), out)
        self.assertIn("skipped", out)
        self.assertEqual(self.run_case("build.gradle.kts", "ok", "ok")[::2], (0, ["ok", "ok"]))
        self.assertEqual(self.run_case("docs/x.md", "ok", event="push")[::2], (0, ["ok"]))

    def test_a_failing_script_fails_the_step_and_the_others_still_run(self):
        rc, out, ran = self.run_case("build.gradle.kts", "bad", "ok")
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(sorted(ran), ["bad", "ok"])

    def test_a_missing_script_fails_the_step(self):
        self.assertNotEqual(self.run_case("build.gradle.kts", "nope")[0], 0)

    def test_the_default_scripts_are_the_warnings_and_jdk_gate_tests(self):
        self.assertEqual(ci_scope.SELFTESTS, ("scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py"))
        for p in ci_scope.SELFTESTS:
            self.assertTrue((ROOT / p).is_file(), p)


def ci_text():
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def job_in(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


# Steps that merged PRs could not add themselves (ci.yml is protected): (job, command, source finding).
# Each also runs in verify.sh. Sources: PR 224 R1-02, PR 231, PR 235 R1-04, PR 239 R2-02.
CI_STEPS = [
    ("static", "python3 -I scripts/test_check_gradle_wrapper.py", "PR 231"),
    ("static", "python3 -I scripts/check_gradle_wrapper.py", "PR 231"),
    ("static", "python3 -I scripts/test_gitignore_secrets.py", "PR 235 R1-04"),
    ("tasks", "python3 -I scripts/test_dependency_floors.py", "PR 224 R1-02"),
    ("tasks", "python3 -I scripts/dependency_floors.py", "PR 224 R1-02"),
    ("unit", "python3 -I scripts/test_check_test_results.py", "PR 239 R2-02"),
]


def wiring_problems(text):
    """What is wrong with a ci.yml text, as a list of messages (empty when the wiring is right)."""
    problems = []
    for job, cmd, _source in CI_STEPS:
        body = job_in(text, job) or ""
        if not re.search(rf"(?m)^        run: {re.escape(cmd)}$", body):
            problems.append(f"{job}: does not run {cmd}")
        if re.search(r"(?m)^\s*(?:-\s+)?if:", body) or "continue-on-error" in body:
            problems.append(f"{job}: if or continue-on-error")
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


def verify_problems(verify):
    return []  # stub (red): the real check follows in the green commit


class CiWiring(unittest.TestCase):
    def test_real_ci_yml_has_no_problems(self):
        self.assertEqual(wiring_problems(ci_text()), [])

    def mutated(self, old, new):
        text = ci_text()
        self.assertIn(old, text)
        return wiring_problems(text.replace(old, new, 1))

    def test_every_mutation_is_flagged(self):
        step = "      - name: gradle repos check tests"
        cases = [
            *[(f"{n}: job-level if", f"  {n}:\n    name: {n}\n", f"  {n}:\n    name: {n}\n    if: github.event_name == 'push'\n") for n in REQUIRED_JOBS],
            *[(f"{n}: needs", f"  {n}:\n    name: {n}\n", f"  {n}:\n    name: {n}\n    needs: [wrapper]\n") for n in REQUIRED_JOBS],
            *[("workflow-level paths filter", "on:\n  pull_request:\n", f"on:\n  pull_request:\n    {k}: ['docs/**']\n") for k in ("paths", "paths-ignore")],
            ("workflow-lint: check name changed", "    name: workflow-lint\n", "    name: workflow-linting\n"),
            ("secrets: job missing", "  secrets:\n    name: secrets\n", "  secrets-moved:\n    name: secrets-moved\n"),
            ("static: if or continue-on-error", step, "      - if: false\n        name: gradle repos check tests"),
            ("static: does not run ci_scope.py selftests", "ci_scope.py selftests", "ci_scope.py nothing"),
            ("static: gradle step does not use gradle-exclude", ':app:lintDebug "${exclude[@]}"', ":app:lintDebug"),
            ("static: no two-commit checkout", "fetch-depth: 2", "fetch-depth: 1"),
            ("static: calls scripts/test_warnings_gate.py directly", step, "      - run: python3 -I scripts/test_warnings_gate.py\n" + step),
            ("guards: hook tests not run with --jobs 4", "run_hook_tests.py --jobs 4", "run_hook_tests.py"),
            ("ci.yml does not run test_ci_scope.py", "python3 -I scripts/test_ci_scope.py", "python3 -I scripts/test_nothing.py"),
            ("static: does not run ci_scope.py selftests", "ci_scope.py selftests\n", "ci_scope.py selftests\n          || true\n"),
        ]
        for job, cmd, _source in CI_STEPS:
            run = f"        run: {cmd}\n"
            problem = f"{job}: does not run {cmd}"
            cases += [
                (problem, cmd, "python3 -I scripts/test_nothing.py"),
                (problem, run, f"        # run: {cmd}\n"),
                (problem, run, run.rstrip() + " || true\n"),
                (problem, run, run + "          || true\n"),
                (problem, run, run + "          --help\n"),
                (problem, run, ""),
                (f"{job}: if or continue-on-error", run, run + "        continue-on-error: true\n"),
                (f"{job}: if or continue-on-error", run, run + "        if: false\n"),
                (f"{job}: if or continue-on-error", run, run + "        if: github.event_name == 'push'\n"),
            ]
        for problem, old, new in cases:
            self.assertIn(problem, self.mutated(old, new), problem)

    def test_an_if_in_a_job_is_reported_once(self):
        text = ci_text().replace("      - name: gradle wrapper checksum check tests", "      - if: false\n        name: gradle wrapper checksum check tests", 1)
        self.assertEqual(wiring_problems(text).count("static: if or continue-on-error"), 1)

    def test_a_step_moved_to_another_job_is_flagged(self):
        text = ci_text()
        for job, cmd, _source in CI_STEPS:
            run = f"        run: {cmd}\n"
            moved = text.replace(run, "", 1).replace("      - name: hook tests", f"      - name: moved\n{run}      - name: hook tests", 1)
            self.assertIn(run, moved)
            self.assertIn(f"{job}: does not run {cmd}", wiring_problems(moved), (job, cmd))

    def test_verify_runs_the_scope_tests_and_the_parallel_hook_tests(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 -I scripts/test_ci_scope.py", verify)
        self.assertIn("scripts/hooks/run_hook_tests.py --jobs 4", verify)

    def test_every_ci_step_exists_and_the_real_verify_sh_runs_it(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        self.assertEqual(verify_problems(verify), [])
        for _job, cmd, source in CI_STEPS:
            self.assertTrue((ROOT / cmd.rsplit(" ", 1)[1]).is_file(), (cmd, source))

    def test_verify_sh_mutations_are_flagged(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        for _job, cmd, source in CI_STEPS:
            line = next(ln for ln in verify.splitlines() if ln.endswith(f" {cmd}") and ln.startswith("step "))
            problem = f"verify.sh does not run `{cmd}` as a top-level step"
            for label, new in (
                ("removed", ""),
                ("commented out", f"# {line}"),
                ("indented (inside an if)", f"  {line}"),
                ("|| true", f"{line} || true"),
                ("other command", line.replace(cmd, "python3 -I scripts/test_nothing.py")),
            ):
                self.assertIn(problem, verify_problems(verify.replace(line, new, 1)), (source, label))


if __name__ == "__main__":
    unittest.main()
