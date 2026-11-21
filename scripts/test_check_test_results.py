"""Tests for scripts/check_test_results.py. Run: python3 -I scripts/test_check_test_results.py"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_test_results as c  # noqa: E402  # justified: must follow the sys.path insert above

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_test_results.py"
JUNIT4 = "package a.b\n\nimport org.junit.Test\n\nclass OldTest {\n    @Test\n    fun x() {}\n}\n"
JUPITER = "package a.b\n\nimport org.junit.jupiter.api.Test\n\nclass NewTest {\n    @Test\n    fun x() {}\n}\n"
HELPER = "package a.b\n\nclass FakeThing\n"


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.src = Path(tmp.name) / "src"
        self.results = Path(tmp.name) / "results"
        self.src.mkdir()
        self.results.mkdir()

    def write(self, name, text):
        (self.src / name).write_text(text)

    def result(self, fqcn):
        (self.results / f"TEST-{fqcn}.xml").write_text("<testsuite/>")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True)


class Gate(Fixture):
    def test_all_classes_have_results(self):
        self.write("OldTest.kt", JUNIT4)
        self.write("NewTest.kt", JUPITER)
        self.result("a.b.OldTest")
        self.result("a.b.NewTest")
        self.assertEqual(c.missing(self.src, self.results), [])

    def test_junit4_class_without_result_is_reported(self):
        self.write("OldTest.kt", JUNIT4)
        self.write("NewTest.kt", JUPITER)
        self.result("a.b.NewTest")
        self.assertEqual(c.missing(self.src, self.results), ["a.b.OldTest"])

    def test_files_without_test_annotations_are_ignored(self):
        self.write("FakeThing.kt", HELPER)
        self.assertEqual(c.missing(self.src, self.results), [])

    def test_result_for_other_class_does_not_count(self):
        self.write("OldTest.kt", JUNIT4)
        self.result("a.b.OldTestExtra")
        self.assertEqual(c.missing(self.src, self.results), ["a.b.OldTest"])


class HelperClasses(Fixture):
    def test_private_helper_next_to_a_real_test_is_ignored(self):
        self.write("FooTest.kt", JUNIT4.replace("OldTest", "FooTest") + "\nprivate class FakeRepo\n")
        self.result("a.b.FooTest")
        self.assertEqual(c.missing(self.src, self.results), [])

    def test_plain_helper_next_to_a_real_test_is_ignored(self):
        self.write("FooTest.kt", JUNIT4.replace("OldTest", "FooTest") + "\nclass FakeRepo {\n    fun get() = 1\n}\n")
        self.result("a.b.FooTest")
        self.assertEqual(c.missing(self.src, self.results), [])

    def test_abstract_base_with_tests_is_ignored(self):
        self.write("BaseTest.kt", JUNIT4.replace("class OldTest", "abstract class BaseTest"))
        self.assertEqual(c.missing(self.src, self.results), [])

    def test_helper_before_the_test_class_does_not_hide_a_skipped_test(self):
        self.write("OldTest.kt", "package a.b\n\nimport org.junit.Test\n\nclass Helper\n\nclass OldTest {\n    @Test\n    fun x() {}\n}\n")
        self.assertEqual(c.missing(self.src, self.results), ["a.b.OldTest"])


class Cli(Fixture):
    def test_exit_0_when_complete(self):
        self.write("NewTest.kt", JUPITER)
        self.result("a.b.NewTest")
        self.assertEqual(self.run_cli(str(self.src), str(self.results)).returncode, 0)

    def test_exit_1_and_names_class_when_skipped(self):
        self.write("OldTest.kt", JUNIT4)
        r = self.run_cli(str(self.src), str(self.results))
        self.assertEqual(r.returncode, 1)
        self.assertIn("a.b.OldTest", r.stderr)

    def test_filtered_run_skips_the_check(self):
        self.write("OldTest.kt", JUNIT4)
        self.assertEqual(self.run_cli(str(self.src), str(self.results), "--filtered").returncode, 0)

    def test_missing_results_dir_fails(self):
        self.write("OldTest.kt", JUNIT4)
        self.assertEqual(self.run_cli(str(self.src), str(self.results / "nope")).returncode, 1)

    def test_missing_source_dir_is_usage_error(self):
        self.assertEqual(self.run_cli(str(self.src / "nope"), str(self.results)).returncode, 2)

    def test_wrong_arg_count_is_usage_error(self):
        self.assertEqual(self.run_cli(str(self.src)).returncode, 2)


class Wiring(unittest.TestCase):
    def test_verify_runs_these_tests(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text()
        self.assertIn("python3 -I scripts/test_check_test_results.py", verify)


def gradle(*args):
    return subprocess.run(
        [str(ROOT / "gradlew"), "-q", "--console=plain", *args], cwd=ROOT, capture_output=True, text=True
    )


class GradleWiring(unittest.TestCase):
    """Behaviour of the real build: the gate must follow testDebugUnitTest, but not a filtered run."""

    def test_gate_is_scheduled_after_the_unit_test_task(self):
        r = gradle("--dry-run", ":app:testDebugUnitTest")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(":app:checkUnitTestResults", r.stdout)

    def test_filtered_run_does_not_fail_the_gate(self):
        r = gradle(":app:testDebugUnitTest", "--tests", "dk.bjarkebjarke.tally.ThemeTest")
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
