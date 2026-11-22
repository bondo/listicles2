"""Tests for scripts/screenshots.sh and the wiring of the screenshot gate (M1-03).

Run: python3 -I scripts/test_screenshots.py

screenshots.sh runs against a fake ./gradlew in a temporary tree, so no Gradle build is needed. The wiring check
(scripts/check_screenshots.py) runs against the real files and against mutated copies, which must each be reported.
"""

import contextlib
import io
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

    def test_the_gate_and_check_steps_must_not_be_skipped_by_an_if(self):
        for cmd in (c.GATE_CMD, c.TESTS_CMD, c.CHECK_CMD):
            for condition in ("if: false", "if: github.event_name == 'push'"):
                with self.subTest(cmd=cmd, condition=condition):
                    self.setUp()
                    got = self.mutated(".github/workflows/ci.yml", f"run: {cmd}", f"{condition}\n        run: {cmd}")
                    self.assertEqual(got, [f"ci.yml step running {cmd} has if:"])

    def test_a_folded_continuation_line_after_a_run_command_is_reported(self):
        # YAML folds a more-indented line into the run value, so `|| true` neuters the step without changing its first line.
        for cmd in (c.GATE_CMD, c.TESTS_CMD, c.CHECK_CMD):
            with self.subTest(cmd=cmd):
                self.setUp()
                got = self.mutated(".github/workflows/ci.yml", f"run: {cmd}\n", f"run: {cmd}\n          || true\n")
                self.assertEqual(got, [f"ci.yml step running {cmd} is followed by a more-indented line (a folded `|| true` or extra arguments)"])

    def test_verify_sh_must_run_the_wiring_check(self):
        got = self.mutated("scripts/verify.sh", "step screenshots-wiring python3 -I scripts/check_screenshots.py\n", "")
        self.assertEqual(got, ["verify.sh has no active step: step screenshots-wiring python3 -I scripts/check_screenshots.py"])

    def test_the_tasks_job_must_run_the_wiring_check(self):
        got = self.mutated(".github/workflows/ci.yml", "run: python3 -I scripts/check_screenshots.py", "run: true")
        self.assertEqual(got, ["ci.yml tasks job has no step running: python3 -I scripts/check_screenshots.py"])

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

    def test_every_screen_needs_the_four_light_dark_en_da_goldens_and_the_200_percent_danish_one(self):
        for name in c.screen_goldens("Lists")[:-1]:  # all but the font200 golden
            (self.dir / name).write_bytes(PNG + name.encode())
        self.assertEqual(c.golden_problems(self.root), [f"missing golden {c.GOLDEN_DIR}/Lists_da_light_font200.png"])

    def test_a_second_screen_with_its_full_set_has_no_problems(self):
        for name in c.screen_goldens("Lists"):
            (self.dir / name).write_bytes(PNG + name.encode())
        self.assertEqual(c.golden_problems(self.root), [])

    def test_a_golden_that_does_not_follow_the_naming_scheme_is_reported(self):
        (self.dir / "Lists_en.png").write_bytes(PNG + b"x")
        self.assertEqual(c.golden_problems(self.root), [f"unexpected file {c.GOLDEN_DIR}/Lists_en.png"])

    def test_an_extra_font_scale_variant_is_reported(self):
        (self.dir / "TallyApp_en_light_font200.png").write_bytes(b"not a png")
        self.assertEqual(c.golden_problems(self.root), [f"unexpected file {c.GOLDEN_DIR}/TallyApp_en_light_font200.png"])

    def test_an_empty_golden_directory_reports_the_five_tally_app_goldens(self):
        for path in self.dir.glob("*.png"):
            path.unlink()
        self.assertEqual(c.golden_problems(self.root), [f"missing golden {c.GOLDEN_DIR}/{name}" for name in c.GOLDENS])

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
        got = self.mutated("app/build.gradle.kts", 'fileTree("src/test/screenshots")', 'fileTree("src/test/other")')
        self.assertEqual(got, [c.INPUT_PROBLEM])

    def test_the_tokens_file_must_be_a_tracked_input_passed_without_its_absolute_path(self):
        # M1-04 R1-02: ThemeTokensTest reads design/tokens.json. As an @InputFile argument provider the content is the cache key and
        # the checkout path is not; a plain systemProperty puts the absolute path into the key and tracks nothing by itself.
        self.assertEqual(c.build_problems(ROOT), [])
        got = self.mutated("app/build.gradle.kts", "@get:InputFile", "@get:Internal")
        self.assertEqual(got, [c.TOKENS_PROBLEM])

    def test_a_plain_system_property_for_the_tokens_file_is_reported(self):
        got = self.mutated("app/build.gradle.kts", "TokensArgs(", 'systemProperty("tally.tokensFile", "x"); TokensArgs(')
        self.assertEqual(got, [c.TOKENS_PROBLEM])

    def test_the_tokens_provider_must_be_added_to_the_test_tasks(self):
        got = self.mutated("app/build.gradle.kts", "jvmArgumentProviders.add(\n        TokensArgs(", "jvmArgumentProviders.add(\n        Other(")
        self.assertEqual(got, [c.TOKENS_PROBLEM])

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

    def test_a_capture_without_the_exact_options_is_reported(self):
        other = self.root / "app/src/test/kotlin/dk/bjarkebjarke/tally/ListsScreenshotTest.kt"
        calls = (
            'onRoot().captureRoboImage("src/test/screenshots/Lists_en_light.png")',
            "captureRoboImage(path, roborazziOptions = RoborazziOptions())",
            'captureScreenRoboImage("src/test/screenshots/Dialog_en_light.png")',
            "captureRoboLastImage()",
            "captureRoboGif(path)",
            "captureRoboAllImage()",
            "captureRoboImage(path, roborazziOptions = ScreenshotOptions.exact.copy(compareOptions = RoborazziOptions.CompareOptions()))",
            "RoborazziRule(options = RoborazziRule.Options())",
        )
        for call in calls:
            with self.subTest(call=call):
                other.write_text(f"fun capture() {{ {call} }}\n")
                want = "app/src/test/kotlin/dk/bjarkebjarke/tally/ListsScreenshotTest.kt captures without roborazziOptions = ScreenshotOptions.exact"
                self.assertEqual(c.build_problems(self.root), [want])

    def test_a_second_threshold_validator_in_the_options_file_is_reported(self):
        got = self.mutated(
            "app/src/test/kotlin/dk/bjarkebjarke/tally/ScreenshotOptions.kt", "ThresholdValidator(0f)", "ThresholdValidator(0f) + ThresholdValidator(0.5f)"
        )
        self.assertEqual(got, ["ScreenshotOptions.kt must compare exactly: ThresholdValidator(0f), maxDistance = 0f, hShift = 0, vShift = 0"])

    def test_a_capture_with_the_exact_options_is_accepted(self):
        other = self.root / "app/src/test/kotlin/dk/bjarkebjarke/tally/ListsScreenshotTest.kt"
        for call in (
            "node.captureRoboImage(f(a, (b)), roborazziOptions = ScreenshotOptions.exact)",
            'captureScreenRoboImage("x.png", roborazziOptions = ScreenshotOptions.exact)',
            "RoborazziRule(options = RoborazziRule.Options(roborazziOptions = ScreenshotOptions.exact))",
        ):
            with self.subTest(call=call):
                other.write_text(f"fun capture() {{ {call} }}\n")
                self.assertEqual(c.build_problems(self.root), [])

    def test_a_tolerance_in_any_other_test_source_is_reported(self):
        tolerances = ("CompareOptions(changeThreshold = 0.5f)", "ThresholdValidator(0.5f)", "SimpleImageComparator()")
        for tolerance in (*tolerances, "resultValidator = { true }", "imageComparator = null"):
            with self.subTest(tolerance=tolerance):
                other = self.root / "app/src/test/kotlin/dk/bjarkebjarke/tally/OtherTest.kt"
                other.write_text(f"val o = {tolerance}\n")
                self.assertEqual(c.build_problems(self.root), ["app/src/test/kotlin/dk/bjarkebjarke/tally/OtherTest.kt sets a comparison tolerance"])


class Accessibility(unittest.TestCase):
    """Every Compose UI test in androidTest runs with ATF accessibility checks on (P15); a test that turns them off is reported."""

    TEST = "app/src/androidTest/kotlin/dk/bjarkebjarke/tally/TallyAppTest.kt"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        # Every androidTest source, so that moving or adding a test file cannot break these tests again (R1-01).
        names = ["app/build.gradle.kts", *(str(p.relative_to(ROOT)) for p in ROOT.glob("**/src/androidTest/**/*.kt"))]
        self.assertIn(self.TEST, names)
        for name in names:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def mutated(self, name, old, new):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text, f"{name} no longer contains {old!r}: update the test")
        path.write_text(text.replace(old, new))
        return c.accessibility_problems(self.root)

    def test_the_repository_ui_tests_run_with_accessibility_checks(self):
        self.assertEqual(c.accessibility_problems(ROOT), [])

    def test_a_compose_ui_test_without_the_checks_is_reported(self):
        got = self.mutated(self.TEST, "enableAccessibilityChecks()", "doNothing()")
        self.assertEqual(got, [f"{self.TEST} uses a Compose test rule but never calls enableAccessibilityChecks()"])

    def test_a_compose_ui_test_that_never_runs_the_checks_is_reported(self):
        # enableAccessibilityChecks() alone checks nothing until an action runs; assertions and captureToImage() run no check (R1-03).
        got = self.mutated(self.TEST, "tryPerformAccessibilityChecks()", "assertExists()")
        self.assertEqual(got, [f"{self.TEST} never calls tryPerformAccessibilityChecks(), so the checks never evaluate the screen"])

    def test_a_new_compose_ui_test_file_without_the_checks_is_reported(self):
        extra = self.root / "app/src/androidTest/kotlin/NewScreenTest.kt"
        extra.write_text("class NewScreenTest { val rule = createAndroidComposeRule<ComponentActivity>() }\n")
        want = "app/src/androidTest/kotlin/NewScreenTest.kt uses a Compose test rule but never calls enableAccessibilityChecks()"
        self.assertEqual(c.accessibility_problems(self.root), [want])

    def test_every_way_to_start_a_compose_ui_test_needs_the_checks(self):
        starters = (
            "createEmptyComposeRule()",
            "createAndroidComposeRule<ComponentActivity>()",
            "runAndroidComposeUiTest<MainActivity> { }",
            "runComposeUiTest { }",
        )
        for starter in starters:
            with self.subTest(starter=starter):
                extra = self.root / "app/src/androidTest/kotlin/StartTest.kt"
                extra.write_text(f"fun t() {{ {starter} }}\n")
                want = "app/src/androidTest/kotlin/StartTest.kt uses a Compose test rule but never calls enableAccessibilityChecks()"
                self.assertEqual(c.accessibility_problems(self.root), [want])

    def test_a_rule_that_enables_the_checks_but_never_runs_them_is_reported_for_every_rule_kind(self):
        extra = self.root / "app/src/androidTest/kotlin/EnableOnlyTest.kt"
        extra.write_text("fun t() { val r = createAndroidComposeRule<ComponentActivity>(); r.enableAccessibilityChecks() }\n")
        want = "app/src/androidTest/kotlin/EnableOnlyTest.kt never calls tryPerformAccessibilityChecks(), so the checks never evaluate the screen"
        self.assertEqual(c.accessibility_problems(self.root), [want])

    def test_turning_the_checks_off_is_reported(self):
        extra = self.root / "app/src/androidTest/kotlin/OffTest.kt"
        extra.write_text("fun off() { rule.enableAccessibilityChecks(); rule.disableAccessibilityChecks() }\n")
        self.assertEqual(c.accessibility_problems(self.root), ["app/src/androidTest/kotlin/OffTest.kt calls disableAccessibilityChecks()"])

    def test_the_accessibility_test_library_must_be_on_the_android_test_classpath(self):
        got = self.mutated("app/build.gradle.kts", "androidTestImplementation(libs.compose.ui.test.junit4.accessibility)", "")
        self.assertEqual(got, ["app/build.gradle.kts does not add compose.ui.test.junit4.accessibility to androidTestImplementation"])


class Main(unittest.TestCase):
    """main(root) is what verify.sh and CI run, and they read only its exit code: it must be 1 with one printed line per problem."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        names = [
            "scripts/verify.sh",
            ".github/workflows/ci.yml",
            "app/build.gradle.kts",
            "gradle/libs.versions.toml",
            *(str(p.relative_to(ROOT)) for p in ROOT.glob("app/src/*/kotlin/**/*.kt")),
            *(str(p.relative_to(ROOT)) for p in (ROOT / c.GOLDEN_DIR).glob("*.png")),
        ]
        for name in names:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = c.main(self.root)
        return code, out.getvalue().splitlines()

    def edit(self, name, old, new):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def test_a_complete_tree_exits_0_and_prints_nothing(self):
        self.assertEqual(self.run_main(), (0, []))

    def test_the_repository_exits_0(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(c.main(ROOT), 0)

    def test_each_group_of_problems_makes_it_exit_1_with_one_line_each(self):
        defects = {
            "wiring": (
                "scripts/verify.sh",
                "step screenshots ./scripts/screenshots.sh verify\n",
                "",
                "verify.sh has no active step: step screenshots ./scripts/screenshots.sh verify",
            ),
            "goldens": (f"{c.GOLDEN_DIR}/TallyApp_da_dark.png", None, None, f"missing golden {c.GOLDEN_DIR}/TallyApp_da_dark.png"),
            "build": ("app/build.gradle.kts", "alias(libs.plugins.roborazzi)", "", "app/build.gradle.kts does not apply the Roborazzi plugin"),
            "accessibility": (
                "app/build.gradle.kts",
                "androidTestImplementation(libs.compose.ui.test.junit4.accessibility)",
                "",
                "app/build.gradle.kts does not add compose.ui.test.junit4.accessibility to androidTestImplementation",
            ),
        }
        for group, (name, old, new, message) in defects.items():
            with self.subTest(group=group):
                self.setUp()
                if old is None:
                    (self.root / name).unlink()
                else:
                    self.edit(name, old, new)
                self.assertEqual(self.run_main(), (1, [f"check_screenshots: {message}"]))

    def test_problems_of_several_groups_are_all_printed(self):
        self.edit("scripts/verify.sh", "step screenshots ./scripts/screenshots.sh verify\n", "")
        (self.root / c.GOLDEN_DIR / "TallyApp_da_dark.png").unlink()
        code, lines = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
