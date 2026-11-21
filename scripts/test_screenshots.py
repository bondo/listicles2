"""Tests for scripts/screenshots.sh and the wiring of the screenshot gate (M1-03).

Run: python3 -I scripts/test_screenshots.py

screenshots.sh runs against a fake ./gradlew in a temporary tree, so no Gradle build is needed. The wiring check
(scripts/check_screenshots.py) runs against the real files and against mutated copies, which must each be reported.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_screenshots as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
DIFF_DIR = Path("app/build/outputs/roborazzi")
FAKE_GRADLEW = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
if [ -n "${FAKE_WRITE_DIFF:-}" ]; then
  mkdir -p app/build/outputs/roborazzi && : > app/build/outputs/roborazzi/new_compare.png
fi
exit "${FAKE_EXIT:-0}"
"""


class Script(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy(ROOT / "scripts" / "screenshots.sh", self.root / "scripts" / "screenshots.sh")
        gradlew = self.root / "gradlew"
        gradlew.write_text(FAKE_GRADLEW)
        gradlew.chmod(gradlew.stat().st_mode | stat.S_IXUSR)
        self.log = self.root / "gradlew.log"

    def run_script(self, *args, **env):
        return subprocess.run(
            [str(self.root / "scripts" / "screenshots.sh"), *args],
            capture_output=True,
            text=True,
            env={**os.environ, "FAKE_LOG": str(self.log), **env},
        )

    def gradle_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_script_is_executable_in_the_repository(self):
        self.assertTrue(os.access(ROOT / "scripts" / "screenshots.sh", os.X_OK))

    def test_verify_runs_only_the_roborazzi_verify_task(self):
        got = self.run_script("verify")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(len(self.gradle_calls()), 1)
        self.assertIn(":app:verifyRoborazziDebug", self.gradle_calls()[0])
        self.assertNotIn("record", self.gradle_calls()[0].lower())

    def test_record_runs_the_roborazzi_record_task(self):
        got = self.run_script("record")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(len(self.gradle_calls()), 1)
        self.assertIn(":app:recordRoborazziDebug", self.gradle_calls()[0])

    def test_a_failing_verify_fails_the_script_and_says_where_the_diffs_are(self):
        got = self.run_script("verify", FAKE_EXIT="1")
        self.assertEqual(got.returncode, 1)
        self.assertIn(str(DIFF_DIR), got.stdout + got.stderr)

    def test_a_failing_record_fails_the_script(self):
        self.assertEqual(self.run_script("record", FAKE_EXIT="1").returncode, 1)

    def test_no_argument_prints_usage_and_runs_no_build(self):
        got = self.run_script()
        self.assertEqual(got.returncode, 2)
        self.assertIn("Usage:", got.stdout + got.stderr)
        self.assertEqual(self.gradle_calls(), [])

    def test_unknown_mode_prints_usage_and_runs_no_build(self):
        for mode in ("bogus", "--help", "VERIFY", "verify extra"):
            with self.subTest(mode=mode):
                got = self.run_script(*mode.split())
                self.assertEqual(got.returncode, 2)
                self.assertEqual(self.gradle_calls(), [])

    def test_stale_diffs_are_removed_before_verify(self):
        stale = self.root / DIFF_DIR / "stale_compare.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"old")
        self.assertEqual(self.run_script("verify").returncode, 0)
        self.assertFalse(stale.exists())

    def test_diffs_of_a_failing_verify_stay_for_the_ci_artifact(self):
        got = self.run_script("verify", FAKE_EXIT="1", FAKE_WRITE_DIFF="1")
        self.assertEqual(got.returncode, 1)
        self.assertTrue((self.root / DIFF_DIR / "new_compare.png").exists())


class Wiring(unittest.TestCase):
    """check_screenshots.py on the real repository, then on copies with one defect each."""

    FILES = ("scripts/verify.sh", ".github/workflows/ci.yml")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in self.FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def mutated(self, name, old, new, count=1):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new, count))
        return c.wiring_problems(self.root)

    def test_the_repository_wiring_is_complete(self):
        self.assertEqual(c.wiring_problems(ROOT), [])

    def test_verify_sh_must_run_the_screenshot_gate(self):
        got = self.mutated("scripts/verify.sh", "step screenshots ./scripts/screenshots.sh verify\n", "")
        self.assertEqual(got, ["verify.sh has no active step: step screenshots ./scripts/screenshots.sh verify"])

    def test_a_commented_out_verify_step_does_not_count(self):
        got = self.mutated("scripts/verify.sh", "step screenshots ./scripts/screenshots.sh", "# step screenshots ./scripts/screenshots.sh")
        self.assertEqual(got, ["verify.sh has no active step: step screenshots ./scripts/screenshots.sh verify"])

    def test_verify_sh_must_run_the_wiring_tests(self):
        got = self.mutated("scripts/verify.sh", "step screenshots-tests python3 -I scripts/test_screenshots.py\n", "")
        self.assertEqual(got, ["verify.sh has no active step: step screenshots-tests python3 -I scripts/test_screenshots.py"])

    def test_ci_must_run_the_screenshot_gate_in_the_screenshots_job(self):
        got = self.mutated(".github/workflows/ci.yml", "run: ./scripts/screenshots.sh verify", "run: ./gradlew :app:testDebugUnitTest")
        self.assertEqual(got, ["ci.yml screenshots job has no step running: ./scripts/screenshots.sh verify"])

    def test_ci_must_upload_the_diffs(self):
        got = self.mutated(".github/workflows/ci.yml", "uses: actions/upload-artifact@", "uses: actions/cache@")
        self.assertEqual(got, ["ci.yml screenshots job has no actions/upload-artifact step"])

    def test_the_upload_must_run_when_the_gate_failed(self):
        got = self.mutated(".github/workflows/ci.yml", "if: failure()", "if: success()")
        self.assertEqual(got, ["ci.yml screenshot-diffs upload must have if: failure()"])

    def test_the_upload_must_come_after_the_gate(self):
        text = (self.root / ".github/workflows/ci.yml").read_text()
        step = text[text.index("      - name: screenshot diffs") :]
        step = step[: step.index("\n\n") if "\n\n" in step else len(step)]
        gate = "      - name: screenshots match the goldens"
        path = self.root / ".github/workflows/ci.yml"
        moved = text.replace(step + "\n", "", 1).replace(gate, step + "\n" + gate, 1)
        path.write_text(moved)
        self.assertEqual(c.wiring_problems(self.root), ["ci.yml screenshot-diffs upload must come after the screenshot gate step"])

    def test_the_upload_must_collect_the_roborazzi_output(self):
        got = self.mutated(".github/workflows/ci.yml", "path: app/build/outputs/roborazzi", "path: app/build/reports")
        self.assertEqual(got, ["ci.yml screenshot-diffs upload must have path: app/build/outputs/roborazzi"])

    def test_the_upload_action_must_be_pinned_to_a_commit(self):
        got = self.mutated(".github/workflows/ci.yml", "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "actions/upload-artifact@v7")
        self.assertEqual(got, ["ci.yml upload-artifact must be pinned to a 40-character commit SHA"])

    def test_the_gate_step_must_not_be_allowed_to_fail(self):
        gate = "run: ./scripts/screenshots.sh verify"
        got = self.mutated(".github/workflows/ci.yml", gate, f"continue-on-error: true\n        {gate}")
        self.assertEqual(got, ["ci.yml screenshot gate step has continue-on-error"])

    def test_the_wiring_tests_must_run_in_ci(self):
        got = self.mutated(".github/workflows/ci.yml", "run: python3 -I scripts/test_screenshots.py", "run: true")
        self.assertEqual(got, ["ci.yml tasks job has no step running: python3 -I scripts/test_screenshots.py"])


if __name__ == "__main__":
    unittest.main()
