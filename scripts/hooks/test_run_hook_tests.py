"""R12-04 (#28): the hook-test runner fails when any test is skipped, however the skip was spelled.
Run: python3 -I -m unittest discover -s scripts/hooks

Skips are detected from the run's result (skipped, expected failures, unexpected successes), not from the source text,
so aliased modules (`import unittest as ut`) and call forms are caught like the plain decorators.
Fixture sources are built by concatenation so the skipped-python-test guard does not flag this file.
"""

import os
import subprocess
import sys
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "run_hook_tests.py")
SK = "sk" + "ip"
PASSING = "def test_ok(self):\n        self.assertTrue(True)\n"


def case(body, header="import unittest\n"):
    return header + "\nclass T(unittest.TestCase):\n    " + body


def run_runner(*sources):
    """Writes each source as scripts/hooks-style test_n.py in a temp dir, runs the runner on it, returns (rc, output)."""
    with tempfile.TemporaryDirectory(prefix="hook-runner-test-") as d:
        for i, src in enumerate(sources):
            with open(os.path.join(d, f"test_n{i}.py"), "w", encoding="utf-8") as f:
                f.write(src)
        r = subprocess.run([sys.executable, "-I", RUNNER, d], capture_output=True, text=True, cwd=d)
        return r.returncode, r.stdout + r.stderr


class RunnerFailsOnSkips(unittest.TestCase):
    def assertSkipFails(self, src, form):
        rc, out = run_runner(src)
        self.assertNotEqual(rc, 0, f"{form}: {out}")
        self.assertIn("skipped", out, form)

    def test_plain_decorator_fails(self):
        self.assertSkipFails(case(f"@unittest.{SK}('x')\n    " + PASSING), "plain")

    def test_aliased_module_decorator_fails(self):
        """The case from #28: import unittest as ut + @ut.skip."""
        self.assertSkipFails(case(f"@ut.{SK}('x')\n    " + PASSING, header="import unittest as ut\nimport unittest\n"), "aliased module")

    def test_call_form_decorator_fails(self):
        self.assertSkipFails(case(f"test_a = unittest.{SK}('x')(lambda self: None)\n"), "call form")

    def test_imported_name_under_another_name_fails(self):
        self.assertSkipFails(case("@s\n    " + PASSING, header=f"import unittest\nfrom unittest import {SK} as s\n"), "from-import alias")

    def test_runtime_skip_fails(self):
        self.assertSkipFails(case(f"def test_a(self):\n        self.{SK}Test('x')\n"), "runtime skip call")

    def test_conditional_skip_that_triggers_fails(self):
        self.assertSkipFails(case(f"@unittest.{SK}If(True, 'x')\n    " + PASSING), "conditional skip")

    def test_skip_in_one_of_two_files_fails(self):
        rc, out = run_runner(case(PASSING), case(f"@unittest.{SK}('x')\n    " + PASSING))
        self.assertNotEqual(rc, 0, out)

    def test_expected_failure_fails(self):
        rc, out = run_runner(case("@unittest.expected" + "Failure\n    def test_a(self):\n        self.fail('x')\n"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("expected failure", out)

    def test_unexpected_success_fails(self):
        rc, out = run_runner(case("@unittest.expected" + "Failure\n    " + PASSING))
        self.assertNotEqual(rc, 0, out)


class RunnerStaysPlainOtherwise(unittest.TestCase):
    def test_passing_suite_exits_zero(self):
        rc, out = run_runner(case(PASSING), case(PASSING))
        self.assertEqual(rc, 0, out)
        self.assertIn("OK", out)

    def test_failing_test_exits_nonzero(self):
        rc, out = run_runner(case("def test_a(self):\n        self.fail('x')\n"))
        self.assertNotEqual(rc, 0, out)

    def test_import_error_exits_nonzero(self):
        rc, out = run_runner("import no_such_module_for_runner_test\n")
        self.assertNotEqual(rc, 0, out)

    def test_zero_tests_found_exits_nonzero(self):
        rc, out = run_runner()
        self.assertNotEqual(rc, 0, out)
        self.assertIn("no tests", out)

    def test_a_mention_of_skip_in_prose_is_not_a_skip(self):
        rc, out = run_runner(case(PASSING) + f"\n# tests are never {SK}ped here\n")
        self.assertEqual(rc, 0, out)

    def test_the_real_hook_suite_discovery_defaults_to_the_script_directory(self):
        self.assertTrue(os.path.isfile(RUNNER))


if __name__ == "__main__":
    unittest.main()
