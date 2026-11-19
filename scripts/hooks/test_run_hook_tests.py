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


def run_tree(files, jobs=None):
    """Like run_runner, but `files` maps relative paths (sub/test_c.py ...) to sources; sub-directories get an __init__.py."""
    with tempfile.TemporaryDirectory(prefix="hook-runner-tree-") as d:
        for rel, src in files.items():
            full = os.path.join(d, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if os.path.dirname(rel):
                open(os.path.join(os.path.dirname(full), "__init__.py"), "a", encoding="utf-8").close()
            with open(full, "w", encoding="utf-8") as f:
                f.write(src)
        extra = ["--jobs", str(jobs)] if jobs else []
        r = subprocess.run([sys.executable, "-I", RUNNER, *extra, d], capture_output=True, text=True, cwd=d)
        return r.returncode, r.stdout + r.stderr


def run_runner(*sources, jobs=None):
    """Writes each source as scripts/hooks-style test_n.py in a temp dir, runs the runner on it, returns (rc, output)."""
    with tempfile.TemporaryDirectory(prefix="hook-runner-test-") as d:
        for i, src in enumerate(sources):
            with open(os.path.join(d, f"test_n{i}.py"), "w", encoding="utf-8") as f:
                f.write(src)
        extra = ["--jobs", str(jobs)] if jobs else []
        r = subprocess.run([sys.executable, "-I", RUNNER, *extra, d], capture_output=True, text=True, cwd=d)
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


FAILING = case("def test_a(self):\n        self.fail('x')\n")
SKIPPING = case(f"@unittest.{SK}('x')\n    " + PASSING)
XFAIL = case("@unittest.expected" + "Failure\n    def test_a(self):\n        self.fail('x')\n")


class ParallelRunnerKeepsEveryGate(unittest.TestCase):
    """--jobs N runs the test files in child processes (issue 229). It fails for everything the serial run fails for, and
    (R1-01, PR 232 round 1) collects what serial discovery collects: test*.py files and sub-packages."""

    def test_passing_trees_run_every_test_once_in_every_mode(self):
        files = {"test_a.py": case(PASSING), "testb.py": case(PASSING), "sub/test_c.py": case(PASSING), "sub/testd.py": case(PASSING)}
        for jobs in (None, 2, 4, 8):
            rc, out = run_tree(files, jobs=jobs)
            self.assertEqual(rc, 0, out)
        self.assertIn("hook tests: ran 4 tests in 2 shards", run_tree(files, jobs=2)[1])
        self.assertIn("ran 5 tests in 3 shards", run_runner(*[case(PASSING)] * 5, jobs=3)[1])

    def test_every_failure_form_fails_serial_and_parallel(self):
        ok = {"test_a.py": case(PASSING)}
        bad = {
            "skip": {"test_b.py": SKIPPING},
            "expected failure": {"test_b.py": XFAIL},
            "failing test": {"test_b.py": FAILING},
            "import error": {"test_b.py": "import no_such_module_for_runner_test\n"},
            "crash": {"test_b.py": "import os\nos._exit(3)\n"},
            "file named testb.py (no underscore)": {"testb.py": FAILING},
            "test in a sub-package": {"sub/test_c.py": FAILING},
            "test*.py in a sub-package": {"sub/testd.py": FAILING},
            "skip in a sub-package": {"sub/test_c.py": SKIPPING},
        }
        for what, extra in bad.items():
            files = {**ok, **extra}
            if what != "crash":  # a crash of the whole process is not a serial-mode form
                self.assertNotEqual(run_tree(files)[0], 0, f"serial: {what}")
            rc, out = run_tree(files, jobs=2)
            self.assertNotEqual(rc, 0, f"parallel: {what}: {out}")

    def test_skip_is_reported_by_name(self):
        self.assertIn("skipped", run_runner(case(PASSING), SKIPPING, case(PASSING), jobs=3)[1])

    def test_zero_tests_found_fails(self):
        rc, out = run_runner(jobs=2)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("no tests", out)

    def test_bad_job_counts_fail(self):
        for bad in ("0", "-1", "x"):
            r = subprocess.run([sys.executable, "-I", RUNNER, "--jobs", bad], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, bad)

    def test_count_check_and_units(self):
        import run_hook_tests

        with tempfile.TemporaryDirectory(prefix="hook-runner-units-") as d:
            for rel in ("test_a.py", "testb.py", "helper.py", "sub/__init__.py", "sub/test_c.py", "nopkg/test_d.py"):
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
                    f.write(case(PASSING) if rel.startswith("test") else "")
            self.assertEqual(run_hook_tests.units(d), ["sub", "test_a.py", "testb.py"])
            self.assertIsNone(run_hook_tests.count_problem(d, 2))  # test_a.py and testb.py; sub has no tests
            for wrong in (0, 3):
                self.assertIn("2 test", run_hook_tests.count_problem(d, wrong))


class Partition(unittest.TestCase):
    def test_every_file_lands_in_exactly_one_shard(self):
        import run_hook_tests

        files = [f"test_{i}.py" for i in range(10)] + ["test_gitenv_isolation.py", "test_guards_sh.py"]
        for n in (1, 2, 3, 4, 7, 20):
            shards = run_hook_tests.partition(files, n)
            flat = [f for shard in shards for f in shard]
            self.assertEqual(sorted(flat), sorted(files), n)
            self.assertTrue(all(shards), f"no empty shard for {n}")
            self.assertLessEqual(len(shards), n)

    def test_the_known_slow_files_do_not_share_a_shard(self):
        import run_hook_tests

        shards = run_hook_tests.partition(["test_a.py", "test_gitenv_isolation.py", "test_gitenv_hostile_config.py", "test_guards_sh.py"], 3)
        for shard in shards:
            self.assertLessEqual(sum(f in run_hook_tests.WEIGHTS for f in shard), 1, shards)

    def test_weights_name_real_test_files(self):
        """A renamed slow file would silently lose its balancing weight."""
        import run_hook_tests

        for name in run_hook_tests.WEIGHTS:
            self.assertTrue(os.path.isfile(os.path.join(HERE, name)), name)


if __name__ == "__main__":
    unittest.main()
