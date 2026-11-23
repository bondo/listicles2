"""Tests for scripts/check_ci_hardening.py, the CI hardening rules of M1-44 (issues 189 and 127).

Run: python3 -I scripts/test_check_ci_hardening.py

The check runs on the real files first, then on copies with one defect each, which must each be reported: a job without a
timeout, python3 or node taken from the runner image, `npm ci` that runs install scripts, a gitleaks download without
retries or https-only redirects.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_ci_hardening as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
CI = ".github/workflows/ci.yml"
STATUS = ".github/workflows/status.yml"
VERIFY = "scripts/verify.sh"
ADR = "docs/adr/0003-gradle-dependency-verification.md"
REQ_CI = "scripts/requirements-ci.txt"
INSTALL_CI = "pip install -r scripts/requirements-ci.txt"


class Rules(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in (CI, STATUS, VERIFY, ADR, REQ_CI, *(p.relative_to(ROOT).as_posix() for p in (ROOT / "scripts").glob("*.sh"))):
            if not (ROOT / name).exists():
                continue  # a missing file is the check's finding, not the test's crash
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def edit(self, name, old, new):
        """Apply one text edit to the copied file `name` and report the problems; the old text must exist."""
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new, 1))
        return c.problems(self.root)

    def edit_yaml(self, name, change):
        """Load the copied workflow, apply `change(workflow)`, write it back, and report the problems."""
        path = self.root / name
        workflow = yaml.safe_load(path.read_text())
        change(workflow)
        path.write_text(yaml.safe_dump(workflow, sort_keys=False, width=10000))
        return c.problems(self.root)

    def set_text(self, name, text):
        (self.root / name).write_text(text)
        return c.problems(self.root)

    def flagged(self, found, *words):
        self.assertTrue(any(all(w in p for w in words) for p in found), f"no problem mentions {words}: {found}")

    def test_the_repository_is_clean(self):
        self.assertEqual(c.problems(ROOT), [])

    def test_every_job_has_a_timeout_of_at_most_an_hour(self):
        for value in (None, 61, 0, "${{ vars.T }}", True, 30.5):
            with self.subTest(value=value):
                self.setUp()

                def change(w, value=value):
                    w["jobs"]["static"].pop("timeout-minutes", None)
                    if value is not None:
                        w["jobs"]["static"]["timeout-minutes"] = value

                self.flagged(self.edit_yaml(CI, change), "static", "timeout")
        self.flagged(self.edit(STATUS, "    timeout-minutes: 10\n", ""), "publish", "timeout")

    def test_python_comes_from_setup_python_in_every_job_that_runs_it(self):
        ci = yaml.safe_load((ROOT / CI).read_text())
        for job in ("static", "unit", "firebase", "guards", "tasks", "workflow-lint", "python-lint"):
            with self.subTest(job):
                self.assertTrue(any(is_use(s, "actions/setup-python@") for s in ci["jobs"][job]["steps"]), f"{job}: update the test")
                self.setUp()
                self.flagged(self.edit_yaml(CI, lambda w, job=job: drop(w, job, "actions/setup-python@")), job, "setup-python")
        self.flagged(self.edit_yaml(STATUS, lambda w: drop(w, "publish", "actions/setup-python@")), "publish", "setup-python")

    def test_a_job_that_only_calls_a_shell_script_that_runs_python_needs_it_too(self):
        self.assertIn("python3", (ROOT / "scripts/check_owner_drift.sh").read_text())
        self.assertEqual(c.problems(self.root), [])

        def add(w):
            w["jobs"]["wrapper"]["steps"].append({"run": "scripts/check_owner_drift.sh"})

        self.flagged(self.edit_yaml(CI, add), "wrapper", "setup-python")

    def test_the_python_version_must_be_one_exact_minor_everywhere(self):
        for bad in ("3.11", "3.12", "3.x", "3", "3.13.1", "latest"):
            with self.subTest(bad):
                self.setUp()
                self.flagged(self.edit_yaml(CI, set_with("tasks", "actions/setup-python@", "python-version", bad)), "python-version")
        self.flagged(self.edit_yaml(CI, lambda w: setup(w, "tasks", "actions/setup-python@").pop("with")), "python-version")

    def test_setup_python_must_come_before_the_first_step_that_runs_python(self):
        def change(w):
            steps = w["jobs"]["tasks"]["steps"]
            i = next(i for i, s in enumerate(steps) if is_use(s, "actions/setup-python@"))
            steps.append(steps.pop(i))

        self.flagged(self.edit_yaml(CI, change), "tasks", "before")

    def test_node_comes_from_setup_node_in_every_job_that_runs_it(self):
        ci = yaml.safe_load((ROOT / CI).read_text())
        for job in ("firebase", "ui", "tasks"):
            with self.subTest(job):
                self.assertTrue(any(is_use(s, "actions/setup-node@") for s in ci["jobs"][job]["steps"]), f"{job}: update the test")
                self.setUp()
                self.flagged(self.edit_yaml(CI, lambda w, job=job: drop(w, job, "actions/setup-node@")), job, "setup-node")

    def test_node_version_must_be_one_pinned_major(self):
        for bad in ("lts/*", "20", "22.x", "latest"):
            with self.subTest(bad):
                self.setUp()
                self.flagged(self.edit_yaml(CI, set_with("tasks", "actions/setup-node@", "node-version", bad)), "node-version")
        self.flagged(self.edit_yaml(CI, set_with("firebase", "actions/setup-node@", "node-version", 24)), "node-version")

    def test_a_job_that_does_not_run_node_needs_no_pin(self):
        self.assertEqual(self.edit_yaml(CI, lambda w: drop(w, "static", "actions/setup-node@")), [])

    def test_python_jobs_install_pyyaml_right_after_setup_python(self):
        """R1-01: setup-python's interpreter has no PyYAML (the runner image's had), and most gate scripts import yaml."""
        ci = yaml.safe_load((ROOT / CI).read_text())
        for job in ("static", "unit", "firebase", "guards", "tasks", "workflow-lint", "python-lint"):
            with self.subTest(job):
                self.assertTrue(any(s.get("run") == INSTALL_CI for s in ci["jobs"][job]["steps"]), f"{job}: update the test")
                self.setUp()
                self.flagged(self.edit_yaml(CI, lambda w, job=job: drop_run(w, job, INSTALL_CI)), job, "requirements-ci.txt")
        self.flagged(self.edit_yaml(STATUS, lambda w: drop_run(w, "publish", INSTALL_CI)), "publish", "requirements-ci.txt")

    def test_the_pyyaml_install_must_come_before_the_first_python_step(self):
        def change(workflow):
            steps = workflow["jobs"]["tasks"]["steps"]
            i = next(i for i, s in enumerate(steps) if s.get("run") == INSTALL_CI)
            steps.append(steps.pop(i))

        self.flagged(self.edit_yaml(CI, change), "tasks", "before")

    def test_the_ci_requirements_pin_pyyaml_exactly(self):
        self.assertRegex((ROOT / REQ_CI).read_text(), r"(?m)^PyYAML==\d+\.\d+\.\d+$")
        for bad in ("PyYAML>=6\n", "PyYAML\n", "PyYAML==6.*\n", "requests==2.0.0\n", ""):
            with self.subTest(bad):
                self.flagged(self.set_text(REQ_CI, bad), "requirements-ci.txt")
        (self.root / REQ_CI).unlink()
        self.flagged(c.problems(self.root), "requirements-ci.txt")

    def test_a_gradle_job_that_reaches_a_python_task_needs_setup_python(self):
        """R1-03: :app:testDebugUnitTest is finalized by an Exec of python3 (checkUnitTestResults), so the screenshots job needs it."""
        self.flagged(self.edit_yaml(CI, lambda w: drop(w, "screenshots", "actions/setup-python@")), "screenshots", "setup-python")

    def test_gradle_jobs_that_reach_no_python_task_need_no_pin(self):
        ci = yaml.safe_load((ROOT / CI).read_text())
        for job in ("ui", "release-smoke", "wrapper", "secrets"):
            self.assertFalse(any(is_use(s, "actions/setup-python@") for s in ci["jobs"][job]["steps"]), job)
        self.assertEqual(c.problems(ROOT), [])

    def test_the_gradle_tasks_that_run_python_are_still_those_in_the_build_files(self):
        app = (ROOT / "app/build.gradle.kts").read_text()
        checks = (ROOT / "build-logic/src/main/kotlin/ModuleChecks.kt").read_text()
        root = (ROOT / "build.gradle.kts").read_text()
        self.assertIn('"python3"', app)
        self.assertIn("checkUnitTestResults", app)
        self.assertIn('executable = "python3"', checks)
        self.assertIn('"checkJavaApiLevel"', checks)
        self.assertTrue({"testDebugUnitTest", "verifyRoborazziDebug", "checkJavaApiLevel"} <= set(c.GRADLE_PYTHON_TASKS))
        # M1-68 part B3: checkJavaApiLevel is in each JVM library module's listiclesChecks, which the root's detekt runs.
        self.assertIn('dependsOn(warnings, release, "checkTestSettings", apiLevel)', checks)
        self.assertIn('tasks.named("detekt") { dependsOn(listiclesModules.map { "$it:listiclesChecks" }) }', root)
        self.assertTrue({"detekt", "listiclesChecks"} <= set(c.GRADLE_PYTHON_TASKS))

    def test_npm_ci_never_runs_install_scripts(self):
        self.flagged(self.edit(CI, "npm ci --ignore-scripts --silent", "npm ci --silent"), "npm ci", "ignore-scripts")
        self.flagged(self.edit(VERIFY, "npm ci --ignore-scripts --silent", "npm ci --silent"), "verify.sh", "ignore-scripts")

    def test_gitleaks_download_retries_and_stays_on_https(self):
        for flag in ("--proto =https ", "--proto-redir =https ", "--retry 5 "):
            with self.subTest(flag):
                self.setUp()
                self.flagged(self.edit(CI, flag, ""), "gitleaks", flag.split()[0])

    def test_gitleaks_uses_the_git_command_and_keeps_its_checksum(self):
        self.flagged(self.edit(CI, "./gitleaks git ", "./gitleaks detect "), "gitleaks", "git")
        self.setUp()
        self.flagged(self.edit(CI, "sha256sum -c -", "cat"), "gitleaks", "sha256sum")
        self.setUp()
        self.flagged(self.edit(CI, "./gitleaks git --redact --no-banner .", "./gitleaks git --source . --redact --no-banner"), "gitleaks", "--source")

    def test_verify_sh_runs_the_check_and_its_tests(self):
        self.flagged(self.edit(VERIFY, "step ci-hardening python3 -I scripts/check_ci_hardening.py\n", ""), "verify.sh", "check_ci_hardening.py")
        self.setUp()
        self.flagged(self.edit(VERIFY, f"step ci-hardening-tests {c.TESTS_CMD}\n", ""), "verify.sh", "test_check_ci_hardening.py")

    def test_ci_tasks_job_runs_the_check_and_its_tests(self):
        for cmd in ("python3 -I scripts/check_ci_hardening.py", "python3 -I scripts/test_check_ci_hardening.py"):
            with self.subTest(cmd):
                self.setUp()
                self.flagged(self.edit(CI, f"        run: {cmd}\n", "        run: 'true'\n"), "ci.yml", cmd)

    def test_the_adr_records_the_checksum_only_decision(self):
        self.flagged(self.set_text(ADR, "# ADR 0003\n"), "ADR", "verify-signatures")
        (self.root / ADR).unlink()
        self.flagged(c.problems(self.root), "ADR")


def is_use(step, prefix):
    return isinstance(step, dict) and str(step.get("uses", "")).startswith(prefix)


def setup(workflow, job, prefix):
    return next(s for s in workflow["jobs"][job]["steps"] if is_use(s, prefix))


def set_with(job, prefix, key, value):
    def change(workflow):
        setup(workflow, job, prefix).setdefault("with", {})[key] = value

    return change


def drop_run(workflow, job, command):
    workflow["jobs"][job]["steps"] = [s for s in workflow["jobs"][job]["steps"] if s.get("run") != command]


def drop(workflow, job, prefix):
    workflow["jobs"][job]["steps"] = [s for s in workflow["jobs"][job]["steps"] if not is_use(s, prefix)]


class Cli(unittest.TestCase):
    def test_exit_status_is_zero_on_the_repository(self):
        done = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/check_ci_hardening.py")], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)


if __name__ == "__main__":
    unittest.main()
