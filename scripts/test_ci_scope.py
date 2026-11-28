"""Tests for scripts/ci_scope.py and its CI wiring (issue 229, see also 216). Run: python3 -I scripts/test_ci_scope.py

ci_scope.py decides whether the slow Gradle gate self-tests (warnings gate, JDK release gate, licensee gate) can be
affected by a pull request. It only ever answers `skip` when every changed path is known to be unrelated, and answers `run`
for anything else: unknown paths, an empty list, a push, a diff that cannot be computed. The decision is made inside
ci_scope.py (`selftests`, `gradle-exclude`); the CI jobs have no condition at all (no `if:`, `needs:` or `paths:`), so every
required check always runs and reports."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_scope  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ci_scope.py"
DEBUG_APK_IF = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
REQUIRED_JOBS = ("wrapper", "static", "unit", "firebase", "ui", "screenshots", "release-smoke", "guards", "secrets", "tasks", "python-lint", "workflow-lint")


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


def rename_merge_repo(old, new):
    """Like merge_repo, but the PR renames `old` (present on main) to `new`."""
    d = merge_repo(old)
    for args in (("checkout", "-q", "-b", "pr2"), ("mv", old, new), ("commit", "-q", "-m", "rename"), ("checkout", "-q", "main"),
                 ("merge", "-q", "--no-ff", "-m", "merge", "pr2")):
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
            ("gate script renamed to a docs path", rename_merge_repo("scripts/test_warnings_gate.py", "README.md"), "pull_request", keep),
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

    def test_the_default_scripts_are_the_warnings_jdk_and_java_api_gate_tests(self):
        self.assertEqual(
            ci_scope.SELFTESTS,
            ("scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py", "scripts/test_java_api_level_gate.py",
             "scripts/test_google_services_release_gate.py", "scripts/test_test_settings_gate.py", "scripts/test_spotless_gate.py"),
        )
        for p in ci_scope.SELFTESTS:
            self.assertTrue((ROOT / p).is_file(), p)


def ci_text():
    return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def job_in(text, name):
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    return m.group(1) if m else None


# Steps that merged PRs could not add themselves (ci.yml is protected): (job, command, source finding).
# Each also runs in verify.sh. Sources: PR 224 R1-02, PR 231, PR 235 R1-04, PR 239 R2-02, M1-51.
CI_STEPS = [
    ("static", "python3 -I scripts/test_check_gradle_wrapper.py", "PR 231"),
    ("static", "python3 -I scripts/check_gradle_wrapper.py", "PR 231"),
    ("static", "python3 -I scripts/test_gitignore_secrets.py", "PR 235 R1-04"),
    ("tasks", "python3 -I scripts/test_dependency_floors.py", "PR 224 R1-02"),
    ("tasks", "python3 -I scripts/dependency_floors.py", "PR 224 R1-02"),
    ("unit", "python3 -I scripts/test_check_test_results.py", "PR 239 R2-02"),
    ("unit", "python3 -I scripts/test_coverage_impact.py", "M1-07"),
    ("tasks", "python3 -I scripts/test_check_build_guards.py", "M1-51"),
    ("tasks", "python3 -I scripts/check_build_guards.py", "M1-51"),
    ("tasks", "python3 -I scripts/test_state_body.py", "M1-77"),
]


def wiring_problems(text):
    """What is wrong with a ci.yml text, as a list of messages (empty when the wiring is right)."""
    problems = []
    for job, cmd, _source in CI_STEPS:
        body = job_in(text, job) or ""
        # No `$` match followed by a more-indented line: YAML folds that line into the run scalar (`|| true`, `--help`).
        if not re.search(rf"(?m)^        run: {re.escape(cmd)}$(?!\n {{9}})", body):
            problems.append(f"{job}: does not run {cmd}")
    for job in dict.fromkeys(job for job, _cmd, _source in CI_STEPS):
        body = job_in(text, job) or ""
        # M1-63: the unit job's debug APK upload step has the one allowed `if:` (push to main only; scripts/check_debug_apk.py freezes the step).
        if job == "unit":
            body = body.replace(f"        if: {DEBUG_APK_IF}\n", "", 1)
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
    if (re.search(r"(?m)^\s*(?:-\s+)?if:", static) or "continue-on-error" in static) and "static: if or continue-on-error" not in problems:
        problems.append("static: if or continue-on-error")
    if "fetch-depth: 2" not in static:
        problems.append("static: no two-commit checkout")
    if not re.search(r"(?m)^        run: python3 -I scripts/ci_scope\.py selftests$(?!\n {9})", static):
        problems.append("static: does not run ci_scope.py selftests")
    if not re.search(r"read -ra exclude <<< \"\$\(python3 -I scripts/ci_scope\.py gradle-exclude\)\"", static) or not re.search(
        r"\./gradlew [^\n]*:app:lintDebug \"\$\{exclude\[@\]\}\"\n", static
    ):
        problems.append("static: gradle step does not use gradle-exclude")
    for script in ci_scope.SELFTESTS:
        if script in static:
            problems.append(f"static: calls {script} directly")
    if "scripts/hooks/run_hook_tests.py --jobs 8" not in (job_in(text, "guards") or ""):
        problems.append("guards: hook tests not run with --jobs 8")
    if "python3 -I scripts/test_ci_scope.py" not in text:
        problems.append("ci.yml does not run test_ci_scope.py")
    return problems


def verify_problems(verify):
    """Problems with how verify.sh runs the CI_STEPS commands: each must be an active, top-level `step <name> <cmd>` line."""
    lines = verify.splitlines()
    return [
        f"verify.sh does not run `{cmd}` as a top-level step"
        for _job, cmd, _source in CI_STEPS
        if not any(re.fullmatch(rf"step \S+ {re.escape(cmd)}", ln) for ln in lines)
    ]


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
            ("guards: hook tests not run with --jobs 8", "run_hook_tests.py --jobs 8", "run_hook_tests.py --jobs 4"),
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

    def test_the_unit_job_may_carry_the_one_debug_apk_upload_condition(self):
        # M1-63: the debug APK upload runs on pushes to main only, so its step has the one allowed `if:`; every other `if:` stays flagged.
        step = f"      - name: upload\n        if: {DEBUG_APK_IF}\n        run: 'true'\n"
        before = "      - name: coverage impact tests (M1-07)"
        text = ci_text()
        self.assertEqual(text.count(f"        if: {DEBUG_APK_IF}\n"), 1, "ci.yml has the debug APK upload step")
        self.assertEqual(wiring_problems(text), [])
        twice = text.replace(before, step + before, 1)
        self.assertIn("unit: if or continue-on-error", wiring_problems(twice))

    def test_the_debug_apk_condition_is_allowed_in_no_other_job_and_in_no_other_form(self):
        step = f"      - name: upload\n        if: {DEBUG_APK_IF}\n        run: 'true'\n"
        in_static = ci_text().replace("      - name: gradle wrapper checksum check tests", step + "      - name: gradle wrapper checksum check tests", 1)
        self.assertIn("static: if or continue-on-error", wiring_problems(in_static))
        before = "      - name: coverage impact tests (M1-07)"
        for other in ("github.event_name == 'push'", "github.ref == 'refs/heads/main'", "always()", f"{DEBUG_APK_IF} || true",
                      "github.event_name == 'push' && github.ref == 'refs/heads/dev'"):
            with self.subTest(other):
                text = ci_text().replace(before, step.replace(DEBUG_APK_IF, other) + before, 1)
                self.assertIn("unit: if or continue-on-error", wiring_problems(text))
        with_coe = ci_text().replace(before, step + "        continue-on-error: true\n" + before, 1)
        self.assertIn("unit: if or continue-on-error", wiring_problems(with_coe))

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


# Issue 216, owner decision 7003898899: the owner's input classes, each with paths that must run the gate self-tests.
OWNER_INPUTS = {
    "licensee config": ("config/licensee/google-sdk-terms.txt", "config/licensee/policy.gradle"),
    "licensee version and versions catalog": ("gradle/libs.versions.toml",),
    "gate scripts": ("scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py", "scripts/ci_scope.py"),
    "gate code": ("build.gradle.kts",),
    "their fixtures": ("config/licensee/fixture/build.gradle.kts", "config/licensee/fixture/approved-a1.txt", "config/detekt/fixtures/clean/A.kt"),
    "build-logic": ("build-logic/src/main/kotlin/X.kt", "buildSrc/build.gradle.kts", "settings.gradle.kts", "gradle.properties",
                    "core/domain/build.gradle.kts", "gradle/patched-dependencies.properties"),
    "Gradle wrapper": ("gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.properties", "gradle/wrapper/gradle-wrapper.jar"),
}


class OwnerInputClasses(unittest.TestCase):
    def test_a_change_to_each_owner_input_class_runs(self):
        for what, paths in OWNER_INPUTS.items():
            for p in paths:
                self.assertEqual(ci_scope.gradle_selftests([p]), "run", (what, p))
                self.assertEqual(ci_scope.gradle_selftests(["docs/a.md", p, "app/src/main/kotlin/A.kt"]), "run", (what, p))


def setUpModule():  # every temporary repository of this file goes into one directory, removed at the end
    global TMP_ROOT
    TMP_ROOT = tempfile.mkdtemp(prefix="ci-scope-tests-")
    tempfile.tempdir = TMP_ROOT


def tearDownModule():
    tempfile.tempdir = None
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


def local_repo(shallow_depth=None):
    """A clone (like an agent container) with origin/main and a branch `pr` at main's tip; with `shallow_depth`, a shallow one."""
    src = tempfile.mkdtemp(prefix="ci-scope-origin-")
    git(src, "init", "-q", "-b", "main")
    for i in range(4):
        git(src, "commit", "-q", "--allow-empty", "-m", f"main {i}")
    d = tempfile.mkdtemp(prefix="ci-scope-clone-")
    depth = ["--depth", str(shallow_depth)] if shallow_depth else []
    git(d, "clone", "-q", *depth, f"file://{src}", ".")
    git(d, "checkout", "-q", "-b", "pr")
    return src, d


def write(repo, path, text="x\n"):
    full = Path(repo, path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")


def local_scope(cwd):
    rc, out = run_cli(cwd, "local-scope", event=None)
    return out if rc == 0 else f"exit {rc}: {out}"


class LocalScope(unittest.TestCase):
    """`local-scope` (verify.sh): `skip` only when nothing changed since the merge base with origin/main touches a gate input."""

    def test_unrelated_changes_skip_committed_staged_unstaged_or_untracked(self):
        _src, repo = local_repo()
        write(repo, "docs/committed.md")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "docs")
        self.assertEqual(local_scope(repo), "skip")
        write(repo, "app/src/main/kotlin/Staged.kt")
        git(repo, "add", "-A")
        write(repo, "docs/committed.md", "changed\n")
        write(repo, "scripts/untracked.py")
        self.assertEqual(local_scope(repo), "skip")

    def test_each_owner_input_class_runs_committed_staged_unstaged_or_untracked(self):
        for what, paths in OWNER_INPUTS.items():
            for p in paths:
                modes = ("committed", "staged", "unstaged", "untracked", "deleted", "renamed-staged", "renamed-committed")
                for how in modes if p == paths[0] else ("committed",):
                    _src, repo = local_repo()
                    write(repo, "docs/unrelated.md")
                    if how in ("unstaged", "deleted") or how.startswith("renamed"):  # the file exists on the branch already
                        write(repo, p, "before\n")
                    git(repo, "add", "-A")
                    git(repo, "commit", "-q", "-m", "setup")
                    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")  # the setup commit is on main, not a change
                    if how == "deleted":
                        os.unlink(Path(repo, p))
                    elif how.startswith("renamed"):  # to a path that skips: only the old path makes it run (--no-renames)
                        git(repo, "mv", p, "docs/moved.txt")
                    else:
                        write(repo, p, "after\n")
                    if how in ("committed", "staged"):
                        git(repo, "add", "-A")
                    if how in ("committed", "renamed-committed"):
                        git(repo, "commit", "-q", "-m", "change")
                    self.assertEqual(local_scope(repo), "run", (what, p, how))

    def test_a_change_merged_in_from_main_is_not_a_change_of_the_branch(self):
        src, repo = local_repo()
        write(src, "build.gradle.kts")
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "main moves on")
        git(repo, "fetch", "-q", "origin")
        git(repo, "merge", "-q", "--no-ff", "-m", "update from main", "origin/main")
        write(repo, "docs/x.md")
        self.assertEqual(local_scope(repo), "skip")

    def test_a_shallow_clone_whose_cut_is_below_the_merge_base_is_scoped(self):
        _src, repo = local_repo(shallow_depth=2)
        self.assertEqual(git_out(repo, "rev-parse", "--is-shallow-repository"), "true")
        write(repo, "docs/x.md")
        self.assertEqual(local_scope(repo), "skip")
        write(repo, "gradle/libs.versions.toml")
        self.assertEqual(local_scope(repo), "run")

    def test_a_cut_equal_to_the_merge_base_is_scoped(self):
        _src, repo = local_repo(shallow_depth=1)  # the only cut is main's tip, which is HEAD and the merge base
        write(repo, "docs/x.md")
        self.assertEqual(local_scope(repo), "skip")

    def test_the_shallow_rule_is_anchored_on_the_merge_base(self):
        """Owner rule 7060652618: every cut must be an ancestor of the merge base, not of HEAD or of origin/main."""
        # A branch that merged main, cloned with limited depth: cuts p2 (the branch's own, above the merge base) and m3.
        src = tempfile.mkdtemp(prefix="ci-scope-origin-")
        for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "m0"), ("commit", "-q", "--allow-empty", "-m", "m1"),
                     ("checkout", "-q", "-b", "pr"), ("commit", "-q", "--allow-empty", "-m", "p1"), ("commit", "-q", "--allow-empty", "-m", "p2"),
                     ("checkout", "-q", "main"), ("commit", "-q", "--allow-empty", "-m", "m2"), ("commit", "-q", "--allow-empty", "-m", "m3"),
                     ("checkout", "-q", "pr"), ("merge", "-q", "--no-ff", "-m", "update", "main"), ("commit", "-q", "--allow-empty", "-m", "p3"),
                     ("commit", "-q", "--allow-empty", "-m", "p4")):
            git(src, *args)
        above_base = tempfile.mkdtemp(prefix="ci-scope-clone-")
        git(above_base, "clone", "-q", "--depth", "4", "--branch", "pr", f"file://{src}", ".")
        git(above_base, "fetch", "-q", "origin", "main:refs/remotes/origin/main")
        # main merged the branch's p2; full branch history, main fetched with depth 2: cut m2 (on main), merge base p2.
        src2 = tempfile.mkdtemp(prefix="ci-scope-origin-")
        for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "m0"), ("checkout", "-q", "-b", "pr"),
                     ("commit", "-q", "--allow-empty", "-m", "p1"), ("commit", "-q", "--allow-empty", "-m", "p2"), ("checkout", "-q", "main"),
                     ("commit", "-q", "--allow-empty", "-m", "m1"), ("commit", "-q", "--allow-empty", "-m", "m2"),
                     ("merge", "-q", "--no-ff", "-m", "m3 merges p2", "pr"), ("checkout", "-q", "pr"), ("commit", "-q", "--allow-empty", "-m", "p3")):
            git(src2, *args)
        on_main = tempfile.mkdtemp(prefix="ci-scope-clone-")
        git(on_main, "clone", "-q", "--branch", "pr", f"file://{src2}", ".")
        git(on_main, "fetch", "-q", "--depth", "2", "origin", "main:refs/remotes/origin/main")
        for what, repo, cut in (("cut on the branch above the merge base", above_base, "p2"), ("cut on main above the merge base", on_main, "m2")):
            cuts = Path(repo, git_out(repo, "rev-parse", "--git-path", "shallow")).read_text(encoding="utf-8").split()
            self.assertIn(cut, [git_out(repo, "log", "-1", "--format=%s", c) for c in cuts], what)
            write(repo, "docs/x.md")
            self.assertEqual(local_scope(repo), "run", what)

    def test_a_linked_worktree_of_a_shallow_clone_is_scoped(self):
        _src, repo = local_repo(shallow_depth=2)
        tree = os.path.join(tempfile.mkdtemp(prefix="ci-scope-tree-"), "wt")
        git(repo, "worktree", "add", "-q", "-b", "pr2", tree, "HEAD")
        write(tree, "docs/x.md")
        self.assertEqual(local_scope(tree), "skip")
        write(tree, "gradlew")
        self.assertEqual(local_scope(tree), "run")

    def test_failure_modes_run(self):
        cases = []
        _src, repo = local_repo()
        write(repo, "docs/x.md")
        git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        cases.append(("no origin/main", repo))
        _src, repo = local_repo()
        git(repo, "checkout", "-q", "--orphan", "unrelated")
        write(repo, "docs/x.md")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "no common history")
        cases.append(("no merge base", repo))
        _src, repo = local_repo()
        cases.append(("nothing changed", repo))
        cases.append(("not a repository", tempfile.mkdtemp(prefix="ci-scope-nogit-")))
        src, repo = local_repo(shallow_depth=2)
        git(src, "checkout", "-q", "-b", "other", "HEAD~3")
        git(src, "commit", "-q", "--allow-empty", "-m", "other")
        git(repo, "fetch", "-q", "--depth", "1", "origin", "other")  # a second cut, not below the merge base
        write(repo, "docs/x.md")
        cases.append(("shallow, a cut that is not below the merge base", repo))
        src, repo = local_repo(shallow_depth=1)
        git(src, "checkout", "-q", "main")
        git(src, "commit", "-q", "--allow-empty", "-m", "main moves on")
        git(src, "commit", "-q", "--allow-empty", "-m", "and again")
        git(repo, "fetch", "-q", "--depth", "1", "origin", "main")  # origin/main is cut off above HEAD: no merge base
        write(repo, "docs/x.md")
        cases.append(("shallow, merge base not fetched", repo))
        _src, repo = local_repo()
        fd = os.open(os.path.join(os.fsencode(repo), b"docs-\xff.md"), os.O_CREAT | os.O_WRONLY)
        os.close(fd)
        cases.append(("a path that is not UTF-8", repo))
        for what, repo in cases:
            self.assertEqual(local_scope(repo), "run", what)

    def test_unknown_mode_arguments_fail(self):
        _src, repo = local_repo()
        self.assertNotEqual(run_cli(repo, "local-scope", "extra", event=None)[0], 0)


def git_out(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


# verify.sh's gate block, run with a stub `step` and a stub python3 that prints what ci_scope.py would.
VERIFY_STUB = """set -u
step() { echo "RAN $1"; }
SKIPPED=0
%s
echo "EXCLUDE ${gate_exclude[*]:-}"
echo "SKIPPED $SKIPPED"
"""
GATE_STEPS = ("step warnings-gate-tests python3 -I scripts/test_warnings_gate.py",
              "step jdk-release-gate-tests python3 -I scripts/test_jdk_release_gate.py",
              "step java-api-level-gate-tests python3 -I scripts/test_java_api_level_gate.py",
              "step google-services-release-gate-tests python3 -I scripts/test_google_services_release_gate.py",
              "step test-settings-gate-tests python3 -I scripts/test_test_settings_gate.py",
              "step spotless-gate-tests python3 -I scripts/test_spotless_gate.py")


def gate_block(verify):
    """The top-level lines from `gate_exclude=()` through the `fi` that closes the ci_scope.py if, or None."""
    head = 'gate_exclude=()\nif gate_scope=$(python3 -I scripts/ci_scope.py local-scope 2>/dev/null) && [ "$gate_scope" = skip ]; then\n'
    m = re.search(rf"(?ms)^{re.escape(head)}.*?^fi$", verify)
    return m.group(0) if m else None


def run_gate_block(block, stdout, code=0):
    bin_dir = tempfile.mkdtemp(prefix="ci-scope-bin-")
    fake = Path(bin_dir, "python3")
    fake.write_text(f"#!/bin/sh\nprintf '%s' '{stdout}'\nexit {code}\n", encoding="utf-8")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": bin_dir + os.pathsep + os.environ["PATH"]}
    r = subprocess.run(["bash", "-c", VERIFY_STUB % block], env=env, capture_output=True, text=True)
    return r.stdout.splitlines()


def verify_gate_problems(verify):
    """What is wrong with how verify.sh scopes the gate self-tests (empty when right)."""
    block = gate_block(verify)
    if block is None:
        return ["verify.sh has no top-level ci_scope.py local-scope block"]
    problems = []
    run_all = ["RAN warnings-gate-tests", "RAN jdk-release-gate-tests", "RAN java-api-level-gate-tests", "RAN google-services-release-gate-tests",
               "RAN test-settings-gate-tests", "RAN spotless-gate-tests",
               "EXCLUDE ", "SKIPPED 0"]
    for stdout, code in (("run", 0), ("", 0), ("skip\nskip", 0), ("skip ", 0), ("Skip", 0), ("skip", 1), ("", 1)):
        if run_gate_block(block, stdout, code) != run_all:
            problems.append(f"does not run the self-tests for scope output {stdout!r}, exit {code}")
    if run_gate_block(block, "skip") != ["skip  warnings-gate-tests, jdk-release-gate-tests, java-api-level-gate-tests, "
                                         "google-services-release-gate-tests, test-settings-gate-tests, spotless-gate-tests, testLicenseeGate "
                                         "(no gate input changed since the merge base with origin/main; scripts/ci_scope.py)",
                                         "EXCLUDE -x testLicenseeGate", "SKIPPED 1"]:
        problems.append("does not skip the self-tests and testLicenseeGate for `skip`")
    for line in GATE_STEPS:
        if verify.count(line) != 1 or not re.search(rf"(?m)^  {re.escape(line)}$", block):
            problems.append(f"`{line}` is not run exactly once, inside the block")
    detekt = [ln for ln in verify.splitlines() if ln.startswith("step detekt ")]
    # ${a[@]+"${a[@]}"}: a bare "${a[@]}" of an empty array is an unbound variable under set -u in bash before 4.4 (macOS).
    if len(detekt) != 1 or not detekt[0].endswith(' ${gate_exclude[@]+"${gate_exclude[@]}"}') or verify.index(block) > verify.index(detekt[0]):
        problems.append("the detekt step does not end with the gate exclusion after the block")
    if verify.count("gate_exclude=") != 2:
        problems.append("gate_exclude is set outside the block")
    return problems


class VerifyGateWiring(unittest.TestCase):
    def verify(self):
        return (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")

    def test_real_verify_sh_has_no_problems(self):
        self.assertEqual(verify_gate_problems(self.verify()), [])

    def test_mutations_are_flagged(self):
        verify = self.verify()
        cases = [
            ('2>/dev/null) && [ "$gate_scope" = skip ]', '2>/dev/null); [ "$gate_scope" = skip ]'),
            ('[ "$gate_scope" = skip ]', '[ "$gate_scope" != run ]'),
            ("  gate_exclude=(-x testLicenseeGate)\n", "  gate_exclude=(-x testLicenseeGate -x testDetektRules)\n"),
            ("  SKIPPED=1\n", ""),
            (f"  {GATE_STEPS[0]}\n", ""),
            (f"  {GATE_STEPS[1]}\n", f"  # {GATE_STEPS[1]}\n"),
            (f"  {GATE_STEPS[0]}\n", f"  {GATE_STEPS[0]} || true\n"),
            (' ${gate_exclude[@]+"${gate_exclude[@]}"}\n', "\n"),
            (' ${gate_exclude[@]+"${gate_exclude[@]}"}\n', ' "${gate_exclude[@]}"\n'),
            ("gate_exclude=()\nif", "gate_exclude=(-x testLicenseeGate)\nif"),
            ("step lint gradle", "gate_exclude=(-x testLicenseeGate)\nstep lint gradle"),
        ]
        for old, new in cases:
            self.assertIn(old, verify, old)
            self.assertNotEqual(verify_gate_problems(verify.replace(old, new, 1)), [], (old, new))


class LicenseeGateInputs(unittest.TestCase):
    """Issue 216: a licensee version bump must make testLicenseeGate out of date, so the version is a declared task input."""

    @staticmethod
    def problems(build):
        m = re.search(r'(?ms)^val testLicenseeGate =\n.*?^    }$', build)
        body = m.group(0) if m else ""
        wanted = ('val pluginVersion = libs.versions.licensee.get()', 'inputs.property("licenseeVersion", pluginVersion)',
                  'inputs.dir(layout.projectDirectory.dir("config/licensee"))')
        return [w for w in wanted if not re.search(rf"(?m)^        {re.escape(w)}$", body)]

    def test_the_real_task_declares_the_version_and_the_config(self):
        self.assertEqual(self.problems((ROOT / "build.gradle.kts").read_text(encoding="utf-8")), [])

    def test_a_missing_or_commented_input_is_flagged(self):
        build = (ROOT / "build.gradle.kts").read_text(encoding="utf-8")
        line = '        inputs.property("licenseeVersion", pluginVersion)\n'
        self.assertIn(line, build)
        for new in ("", "        // " + line.lstrip(), line.replace("licenseeVersion", "otherName")):
            self.assertNotEqual(self.problems(build.replace(line, new, 1)), [], new)
        self.assertNotEqual(self.problems(build.replace("val testLicenseeGate =", "val renamedGate =", 1)), [])


if __name__ == "__main__":
    unittest.main()
