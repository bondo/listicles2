"""Tests for scripts/check_release_smoke.py, the release smoke build with R8 in CI (M1-33, checklist follow-up 7).

Run: python3 -I scripts/test_check_release_smoke.py

The check runs on the real files first, then on copies with one defect each, which must each be reported. The Gradle side (a release
build without -Ptally.allowStandInRelease=true still fails) is tested by scripts/test_google_services_release_gate.py.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_release_smoke as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
CI = ".github/workflows/ci.yml"
STATUS = ".github/workflows/status.yml"
VERIFY = "scripts/verify.sh"
APP_BUILD = "app/build.gradle.kts"
PROPERTIES = "gradle.properties"
FLAG = "-Ptally.allowStandInRelease=true"
JOB_PROBLEM = c.JOB_PROBLEM


class Wiring(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in (CI, STATUS, VERIFY, APP_BUILD, PROPERTIES):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def mutated(self, name, old, new, count=1):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new, count))
        return c.problems(self.root)

    def append(self, name, extra):
        path = self.root / name
        path.write_text(path.read_text() + extra)
        return c.problems(self.root)

    # The real repository, and the smoke job itself.
    def test_the_repository_wiring_is_complete(self):
        self.assertEqual(c.problems(ROOT), [])

    def test_the_job_builds_release_with_the_flag_and_checks_that_r8_ran(self):
        job = c.EXPECTED_JOB
        runs = [s["run"] for s in job["steps"] if "run" in s]
        self.assertIn(f"./gradlew -q --console=plain {FLAG} :app:assembleRelease", runs)
        self.assertTrue(any("mapping.txt" in r for r in runs), "no step checks the R8 mapping file")
        self.assertTrue(any("-release-unsigned.apk" in r for r in runs), "no step checks the unsigned APK")

    def test_no_job_means_no_smoke_build(self):
        text = (self.root / CI).read_text()
        start = text.index("  release-smoke:\n")
        end = text.index("\n  guards:\n")  # the job is placed before `guards`; the next job key ends it
        (self.root / CI).write_text(text[:start] + text[end + 1 :])
        self.assertEqual(c.problems(self.root), [JOB_PROBLEM])

    def test_dropping_the_flag_is_reported(self):
        self.assertEqual(self.mutated(CI, f"--console=plain {FLAG} :app:assembleRelease", "--console=plain :app:assembleRelease"), [JOB_PROBLEM])

    def test_building_debug_instead_of_release_is_reported(self):
        self.assertEqual(self.mutated(CI, f"{FLAG} :app:assembleRelease", f"{FLAG} :app:assembleDebug"), [JOB_PROBLEM])

    def test_skipping_r8_is_reported(self):
        self.assertEqual(self.mutated(CI, ":app:assembleRelease\n", ":app:assembleRelease -x minifyReleaseWithR8\n"), [JOB_PROBLEM])

    def test_a_dry_run_is_reported(self):
        self.assertEqual(self.mutated(CI, ":app:assembleRelease\n", ":app:assembleRelease --dry-run\n"), [JOB_PROBLEM])

    def test_an_if_on_the_job_is_reported(self):
        self.assertEqual(self.mutated(CI, "  release-smoke:\n", "  release-smoke:\n    if: false\n"), [JOB_PROBLEM])

    def test_continue_on_error_is_reported(self):
        self.assertEqual(self.mutated(CI, "  release-smoke:\n", "  release-smoke:\n    continue-on-error: true\n"), [JOB_PROBLEM])

    def test_an_upload_step_is_reported(self):
        upload = (
            "      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a\n"
            "        with: { name: apk, path: app/build/outputs/apk/release }\n"
        )
        marker = "      - name: release build with R8"
        self.assertEqual(self.mutated(CI, marker, upload + marker), [JOB_PROBLEM])

    def test_a_secret_in_the_job_is_reported(self):
        self.assertEqual(
            self.mutated(CI, "  release-smoke:\n", "  release-smoke:\n    env:\n      KEYSTORE_PASSWORD: ${{ secrets.KEYSTORE_PASSWORD }}\n"),
            [JOB_PROBLEM],
        )

    def test_a_different_runner_is_reported(self):
        old = "  release-smoke:\n    name: release-smoke\n    runs-on: ubuntu-latest\n"
        self.assertEqual(self.mutated(CI, old, old.replace("ubuntu-latest", "macos-latest")), [JOB_PROBLEM])

    def test_a_missing_timeout_is_reported(self):
        self.assertEqual(self.mutated(CI, "    timeout-minutes: 30\n    steps:\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n        with:\n          persist-credentials: false\n      - uses: actions/setup-java@d1374f8ac74474200d16ef8ecee22c7ae7a51880 # v6.3.0\n        with: { distribution: temurin, java-version: 21 }\n      - uses: gradle/actions/setup-gradle@8da46b539cd8fe6ab27ca75128919a18d757604c # v6.4.1\n      - name: release build with R8", "    steps:\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n        with:\n          persist-credentials: false\n      - uses: actions/setup-java@d1374f8ac74474200d16ef8ecee22c7ae7a51880 # v6.3.0\n        with: { distribution: temurin, java-version: 21 }\n      - uses: gradle/actions/setup-gradle@8da46b539cd8fe6ab27ca75128919a18d757604c # v6.4.1\n      - name: release build with R8"), [JOB_PROBLEM])

    # The flag is for this one job only (M1-30: any other release build must still fail).
    def test_the_flag_in_another_ci_job_is_reported(self):
        got = self.mutated(CI, ":app:assembleDebug :app:assembleDebugAndroidTest\n", f":app:assembleDebug :app:assembleDebugAndroidTest {FLAG}\n")
        self.assertEqual(got, [c.flag_problem("ci.yml job unit")])

    def test_the_flag_in_another_workflow_is_reported(self):
        got = self.append(STATUS, f"# trailing\n      - run: ./gradlew {FLAG} :app:assembleRelease\n")
        self.assertEqual(got, [c.flag_problem("status.yml")])

    def test_the_flag_in_verify_sh_is_reported(self):
        got = self.append(VERIFY, f"step release gradle {FLAG} :app:assembleRelease\n")
        self.assertEqual(got, [c.flag_problem("scripts/verify.sh")])

    def test_the_flag_in_gradle_properties_is_reported(self):
        got = self.append(PROPERTIES, "\ntally.allowStandInRelease=true\n")
        self.assertEqual(got, [c.flag_problem("gradle.properties")])

    def test_the_flag_in_a_comment_is_not_reported(self):
        self.assertEqual(self.append(VERIFY, f"# the CI smoke build passes {FLAG}\n"), [])

    # The release variant must really run R8, or the smoke build proves nothing.
    def test_turning_r8_off_for_release_is_reported(self):
        got = self.mutated(APP_BUILD, "isMinifyEnabled = true", "isMinifyEnabled = false")
        self.assertEqual(got, [c.MINIFY_PROBLEM])

    def test_a_missing_release_build_type_is_reported(self):
        got = self.mutated(APP_BUILD, "        release {\n", "        staging {\n")
        self.assertEqual(got, [c.MINIFY_PROBLEM])

    # Wiring: verify.sh and the tasks job run the check and its tests.
    def test_verify_sh_must_run_the_tests_and_the_check(self):
        for step in c.VERIFY_STEPS:
            got = self.mutated(VERIFY, step + "\n", "")
            self.assertEqual(got, [f"verify.sh has no active step: {step}"])
            self.setUp()

    def test_a_commented_out_verify_step_is_reported(self):
        step = c.VERIFY_STEPS[1]
        self.assertEqual(self.mutated(VERIFY, step + "\n", "# " + step + "\n"), [f"verify.sh has no active step: {step}"])

    def test_the_tasks_job_must_run_the_tests_and_the_check(self):
        for cmd in (c.TESTS_CMD, c.CHECK_CMD):
            got = self.mutated(CI, f"        run: {cmd}\n", "        run: true\n")
            self.assertEqual(got, [f"ci.yml tasks job has no step running: {cmd}"])
            self.setUp()


if __name__ == "__main__":
    unittest.main()
