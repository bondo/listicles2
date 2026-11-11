"""Behaviour tests for .githooks/pre-push (R10-52): the real hook runs in a throwaway repo with stub guards.sh and gradlew.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import gitenv  # noqa: F401  (drops GIT_DIR and friends, see gitenv.py)

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
            f.write("import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue(%s)\n" % passes)

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

    def test_failing_hook_tests_block_even_a_docs_only_push_and_skip_gradle(self):
        self.commit("docs/a.md", "x")
        self.hook_test(passes=False)
        rc, _ = self.push()
        self.assertNotEqual(rc, 0)
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
        self.commit("docs/a.md", "x")
        rc, out = self.push(GIT_DIR=os.path.join(sentinel, ".git"))
        self.assertEqual(rc, 0, out)
        sentinel_cfg = subprocess.run(["git", "config", "--local", "--list"], cwd=sentinel, capture_output=True, text=True).stdout
        self.assertNotIn("leak.probe", sentinel_cfg)

    def test_new_branch_without_origin_main_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.push(stdin=f"refs/heads/b {self.rev()} refs/heads/b {ZERO}\n")[0], 0)
        self.assertTrue(self.gradle_called())


if __name__ == "__main__":
    unittest.main()
