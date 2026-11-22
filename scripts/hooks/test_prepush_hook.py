"""Behaviour tests for .githooks/pre-push (R10-52): the real hook runs in a throwaway repo with stub guards.sh and gradlew.
Owner decision 7075952806 item 1 on #15: the hook tests run (with --jobs 4) only when the push changes a hook-suite input
(prepush_scope.py --hook-tests); guards.sh runs on every push. Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ZERO = "0" * 40


class PrePushHook(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        os.makedirs(os.path.join(self.repo, ".githooks"))
        os.makedirs(os.path.join(self.repo, "scripts", "hooks"))
        shutil.copy(os.path.join(ROOT, ".githooks", "pre-push"), os.path.join(self.repo, ".githooks", "pre-push"))
        shutil.copy(os.path.join(ROOT, "scripts", "hooks", "prepush_scope.py"), os.path.join(self.repo, "scripts", "hooks"))
        shutil.copy(os.path.join(ROOT, "scripts", "hooks", "run_hook_tests.py"), os.path.join(self.repo, "scripts", "hooks"))
        self.stub("scripts/guards.sh", "exit ${STUB_GUARDS:-0}")
        self.stub("gradlew", 'echo called >> "$STUB_LOG"; exit ${STUB_GRADLE:-0}')
        self.hook_test(passes=True)
        self.run_git("init", "-q", "-b", "main")
        self.run_git("config", "user.email", "t@example.com")
        self.run_git("config", "user.name", "t")
        self.commit("README.md", "a")
        self.base = self.rev()
        self.log = os.path.join(self.repo, "gradle.log")

    def stub(self, rel, body):
        path = os.path.join(self.repo, rel)
        with open(path, "w") as f:
            f.write("#!/usr/bin/env bash\n" + body + "\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def hook_test(self, passes):
        with open(os.path.join(self.repo, "scripts", "hooks", "test_stub.py"), "w") as f:
            f.write(f"import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue({passes})\n")

    def run_git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def rev(self):
        return self.run_git("rev-parse", "HEAD")

    def commit(self, path, content):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        self.run_git("add", "-A")
        self.run_git("commit", "-q", "-m", "c")

    def push(self, stdin=None, **env):
        stdin = f"refs/heads/b {self.rev()} refs/heads/b {self.base}\n" if stdin is None else stdin
        e = dict(os.environ, STUB_LOG=self.log, **env)
        r = subprocess.run(["bash", os.path.join(self.repo, ".githooks", "pre-push")], input=stdin, cwd=self.repo, env=e,
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def gradle_called(self):
        return os.path.exists(self.log)

    def test_docs_only_push_passes_without_gradle(self):
        self.commit("docs/a.md", "x")
        rc, out = self.push()
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.gradle_called())
        self.assertIn("skipping Gradle", out)

    def test_android_push_runs_gradle_and_passes_its_exit_code_through(self):
        self.commit("app/src/main/A.kt", "x")
        self.assertEqual(self.push()[0], 0)
        self.assertTrue(self.gradle_called())
        os.remove(self.log)
        rc, _ = self.push(STUB_GRADLE="3")
        self.assertEqual(rc, 3)
        self.assertTrue(self.gradle_called())

    def test_failing_hook_tests_block_a_hook_change_push_and_skip_gradle(self):
        self.commit("scripts/hooks/note.md", "x")
        self.hook_test(passes=False)
        rc, _ = self.push()
        self.assertNotEqual(rc, 0)
        self.assertFalse(self.gradle_called())

    def test_a_skipped_hook_test_blocks_the_push_and_skips_gradle(self):
        """R12-04 (#28): the pre-push hook runs the skip gate, not a bare discover."""
        self.commit("scripts/guards.sh", "exit 0")
        with open(os.path.join(self.repo, "scripts", "hooks", "test_stub.py"), "w") as f:
            f.write("import unittest as ut\n\nclass T(ut.TestCase):\n    @ut.sk" + "ip('later')\n    def test_x(self):\n        pass\n")
        rc, out = self.push()
        self.assertNotEqual(rc, 0, out)
        self.assertFalse(self.gradle_called())

    def test_failing_guards_block_before_anything_else(self):
        self.commit("docs/a.md", "x")
        rc, _ = self.push(STUB_GUARDS="1")
        self.assertEqual(rc, 1)
        self.assertFalse(self.gradle_called())

    def test_garbage_stdin_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.push(stdin="nonsense\n")[0], 0)
        self.assertTrue(self.gradle_called())

    def test_missing_scope_script_builds(self):
        self.commit("docs/a.md", "x")
        os.remove(os.path.join(self.repo, "scripts", "hooks", "prepush_scope.py"))
        self.assertEqual(self.push()[0], 0)
        self.assertTrue(self.gradle_called())

    def test_hook_does_not_leak_git_dir_into_what_it_runs(self):
        """R11-51: git exports GIT_DIR when pushing from a linked worktree; the guards and tests the hook runs must not inherit it."""
        sentinel = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", sentinel], check=True)
        probe = ("import subprocess, unittest\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                 "        subprocess.run(['git', 'config', 'leak.probe', '1'], check=True)\n")
        with open(os.path.join(self.repo, "scripts", "hooks", "test_stub.py"), "w") as f:
            f.write(probe)
        self.commit(".githooks/note.md", "x")
        rc, out = self.push(GIT_DIR=os.path.join(sentinel, ".git"))
        self.assertEqual(rc, 0, out)
        self.assertIn("shards", out)  # the probe ran
        sentinel_cfg = subprocess.run(["git", "config", "--local", "--list"], cwd=sentinel, capture_output=True, text=True).stdout
        self.assertNotIn("leak.probe", sentinel_cfg)

    def test_new_branch_without_origin_main_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.push(stdin=f"refs/heads/b {self.rev()} refs/heads/b {ZERO}\n")[0], 0)
        self.assertTrue(self.gradle_called())

    def hook_tests_ran(self, out):
        return "hook tests: ran" in out

    def test_app_only_push_skips_the_hook_tests_but_not_guards_or_gradle(self):
        self.commit("app/src/main/A.kt", "x")
        self.commit("docs/product/a.md", "x")
        self.hook_test(passes=False)
        rc, out = self.push()
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.hook_tests_ran(out), out)
        self.assertIn("skipping the hook tests", out)
        self.assertTrue(self.gradle_called())
        self.assertEqual(self.push(STUB_GUARDS="1")[0], 1)  # guards.sh still runs on every push

    def test_docs_only_push_with_a_failing_hook_test_passes(self):
        self.commit("docs/product/a.md", "x")
        self.hook_test(passes=False)
        rc, out = self.push()
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.gradle_called())

    def test_hook_inputs_run_the_hook_tests_in_four_jobs(self):
        with open(os.path.join(self.repo, "scripts", "hooks", "test_stub2.py"), "w") as f:
            f.write("import unittest\n\nclass T(unittest.TestCase):\n    def test_y(self):\n        pass\n")
        for path in ("scripts/hooks/x.py", "scripts/verify.sh", ".githooks/pre-commit", ".claude/settings.json", "docs/PLAN.md"):
            with self.subTest(path):  # .githooks/pre-push and scripts/guards.sh are the hook and stub under test, so not rewritten here
                self.base = self.rev()
                self.commit(path, "#" + path)
                rc, out = self.push()
                self.assertEqual(rc, 0, out)
                self.assertIn("hook tests: ran 2 tests in 2 shards", out)  # serial mode prints no shard line

    def test_a_deleted_hook_file_runs_the_hook_tests(self):
        self.commit("scripts/hooks/old_helper.py", "x")
        self.base = self.rev()
        self.run_git("rm", "-q", "scripts/hooks/old_helper.py")
        self.run_git("commit", "-q", "-m", "rm")
        self.hook_test(passes=False)
        self.assertNotEqual(self.push()[0], 0)

    def test_unknown_or_empty_ranges_run_the_hook_tests(self):
        self.commit("app/src/main/A.kt", "x")
        self.hook_test(passes=False)
        for stdin in ("nonsense\n", "", f"refs/heads/b {self.rev()} refs/heads/b {'1' * 40}\n",
                      f"refs/heads/b {self.rev()} refs/heads/b {self.rev()}\n", f"refs/heads/b {self.rev()} refs/heads/b {ZERO}\n"):
            with self.subTest(stdin):
                rc, out = self.push(stdin=stdin)
                self.assertNotEqual(rc, 0, out)
                self.assertTrue(self.hook_tests_ran(out), out)

    def test_missing_scope_script_runs_the_hook_tests(self):
        self.commit("app/src/main/A.kt", "x")
        self.hook_test(passes=False)
        os.remove(os.path.join(self.repo, "scripts", "hooks", "prepush_scope.py"))
        self.assertNotEqual(self.push()[0], 0)


if __name__ == "__main__":
    unittest.main()
