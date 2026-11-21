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


PNG = b"\x89PNG\r\n\x1a\n"


class Goldens(unittest.TestCase):
    """The golden set: light and dark x en and da, plus the one 200 % font-scale Danish light golden (Q3 A, #15 comment 7058176190)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dir = self.root / c.GOLDEN_DIR
        self.dir.mkdir(parents=True)
        for i, name in enumerate(c.GOLDENS):
            (self.dir / name).write_bytes(PNG + bytes([i]))

    def test_the_repository_goldens_are_complete(self):
        self.assertEqual(c.golden_problems(ROOT), [])

    def test_the_expected_set_is_light_and_dark_in_both_languages_plus_one_font_scale_golden(self):
        want = [f"TallyApp_{lang}_{mode}.png" for lang in ("en", "da") for mode in ("light", "dark")] + ["TallyApp_da_light_font200.png"]
        self.assertEqual(sorted(c.GOLDENS), sorted(want))

    def test_a_complete_synthetic_set_has_no_problems(self):
        self.assertEqual(c.golden_problems(self.root), [])

    def test_a_missing_golden_is_reported(self):
        (self.dir / "TallyApp_da_dark.png").unlink()
        self.assertEqual(c.golden_problems(self.root), [f"missing golden {c.GOLDEN_DIR}/TallyApp_da_dark.png"])

    def test_an_unexpected_png_is_reported(self):
        (self.dir / "TallyApp_fr_light.png").write_bytes(PNG + b"x")
        self.assertEqual(c.golden_problems(self.root), [f"unexpected file {c.GOLDEN_DIR}/TallyApp_fr_light.png"])

    def test_a_compare_or_actual_image_left_in_the_golden_directory_is_reported(self):
        (self.dir / "TallyApp_en_light_compare.png").write_bytes(PNG + b"x")
        self.assertEqual(c.golden_problems(self.root), [f"unexpected file {c.GOLDEN_DIR}/TallyApp_en_light_compare.png"])

    def test_a_file_that_is_not_a_png_is_reported(self):
        (self.dir / "TallyApp_en_dark.png").write_bytes(b"not a png")
        self.assertEqual(c.golden_problems(self.root), [f"{c.GOLDEN_DIR}/TallyApp_en_dark.png is not a PNG"])

    def test_a_golden_over_300_kb_is_reported(self):
        (self.dir / "TallyApp_en_dark.png").write_bytes(PNG + bytes(300 * 1024))
        self.assertEqual(c.golden_problems(self.root), [f"{c.GOLDEN_DIR}/TallyApp_en_dark.png is over 300 KB"])

    def test_two_identical_goldens_are_reported_because_a_variant_did_not_take_effect(self):
        (self.dir / "TallyApp_en_dark.png").write_bytes(PNG + bytes([0]))
        self.assertEqual(c.golden_problems(self.root), [f"{c.GOLDEN_DIR}/TallyApp_en_dark.png and TallyApp_en_light.png are identical"])


class Build(unittest.TestCase):
    """The Gradle and test-source side: plugin applied, exact comparison (changeThreshold 0), no tolerance anywhere."""

    FILES = ("app/build.gradle.kts", "app/src/test/kotlin/dk/bjarkebjarke/tally/ScreenshotOptions.kt", "gradle/libs.versions.toml")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in self.FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def mutated(self, name, old, new):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new, 1))
        return c.build_problems(self.root)

    def test_the_repository_build_is_set_up(self):
        self.assertEqual(c.build_problems(ROOT), [])

    def test_the_roborazzi_plugin_must_be_applied_to_app(self):
        got = self.mutated("app/build.gradle.kts", "alias(libs.plugins.roborazzi)", "")
        self.assertEqual(got, ["app/build.gradle.kts does not apply the Roborazzi plugin"])

    def test_the_plugin_must_be_in_the_version_catalog(self):
        got = self.mutated("gradle/libs.versions.toml", "roborazzi = { id =", "roborazziX = { id =")
        self.assertIn("libs.versions.toml has no roborazzi plugin", got)

    def test_the_goldens_must_be_an_input_of_the_test_task(self):
        # Without it Gradle reports testDebugUnitTest UP-TO-DATE (or takes it from the build cache) after a golden changed,
        # and the verify gate passes without comparing anything.
        got = self.mutated("app/build.gradle.kts", 'inputs.dir("src/test/screenshots")', 'inputs.dir("src/test/other")')
        self.assertEqual(got, ["app/build.gradle.kts must declare src/test/screenshots as an input of the test tasks (else verify is skipped when only goldens changed)"])

    def test_the_comparison_must_be_exact(self):
        want = ["ScreenshotOptions.kt must compare exactly: ThresholdValidator(0f), maxDistance = 0f, hShift = 0, vShift = 0"]
        for old, new in (
            ("ThresholdValidator(0f)", "ThresholdValidator(0.01f)"),
            ("maxDistance = 0f", "maxDistance = 0.007f"),
            ("hShift = 0", "hShift = 2"),
            ("vShift = 0", "vShift = 2"),
        ):
            with self.subTest(old=old):
                self.setUp()
                self.assertEqual(self.mutated("app/src/test/kotlin/dk/bjarkebjarke/tally/ScreenshotOptions.kt", old, new), want)

    def test_a_tolerance_in_any_other_test_source_is_reported(self):
        for tolerance in ("CompareOptions(changeThreshold = 0.5f)", "ThresholdValidator(0.5f)", "SimpleImageComparator()", "resultValidator = { true }", "imageComparator = null"):
            with self.subTest(tolerance=tolerance):
                other = self.root / "app/src/test/kotlin/dk/bjarkebjarke/tally/OtherTest.kt"
                other.write_text(f"val o = {tolerance}\n")
                self.assertEqual(c.build_problems(self.root), ["app/src/test/kotlin/dk/bjarkebjarke/tally/OtherTest.kt sets a comparison tolerance"])


if __name__ == "__main__":
    unittest.main()
