"""Behaviour tests for .githooks/pre-commit (Agent Usage Redesign, tooling PR 1): the real hook runs in a throwaway repo with
stub guards.sh and gradlew. Gradle (spotless, detekt) is skipped when no staged file can affect Kotlin or Gradle; the guards
always run; unknown means build.
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


class PreCommitHook(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        os.makedirs(os.path.join(self.repo, ".githooks"))
        os.makedirs(os.path.join(self.repo, "scripts", "hooks"))
        shutil.copy(os.path.join(ROOT, ".githooks", "pre-commit"), os.path.join(self.repo, ".githooks", "pre-commit"))
        shutil.copy(os.path.join(ROOT, "scripts", "hooks", "prepush_scope.py"), os.path.join(self.repo, "scripts", "hooks"))
        self.stub("scripts/guards.sh", 'echo "guards $*" >> "$STUB_LOG"; exit ${STUB_GUARDS:-0}')
        self.stub("gradlew", 'echo "gradle $*" >> "$STUB_LOG"; exit ${STUB_GRADLE:-0}')
        self.run_git("init", "-q", "-b", "main")
        self.run_git("config", "user.email", "t@example.com")
        self.run_git("config", "user.name", "t")
        self.write("README.md", "a")
        self.run_git("add", "-A")
        self.run_git("commit", "-q", "-m", "base")
        self.log = os.path.join(self.repo, "stub.log")

    def stub(self, rel, body):
        path = os.path.join(self.repo, rel)
        with open(path, "w") as f:
            f.write("#!/usr/bin/env bash\n" + body + "\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def write(self, path, content):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)

    def run_git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def stage(self, path, content="x"):
        self.write(path, content)
        self.run_git("add", path)

    def hook(self, **env):
        e = dict(os.environ, STUB_LOG=self.log, **env)
        r = subprocess.run(["bash", os.path.join(self.repo, ".githooks", "pre-commit")], cwd=self.repo, env=e, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return f.read().splitlines()

    def gradle_called(self):
        return any(c.startswith("gradle") for c in self.calls())

    def test_docs_only_commit_runs_the_guards_but_not_gradle(self):
        self.stage("docs/a.md")
        rc, out = self.hook()
        self.assertEqual(rc, 0, out)
        self.assertIn("guards --staged", self.calls())
        self.assertFalse(self.gradle_called())

    def test_scripts_hooks_and_process_files_skip_gradle(self):
        for path in ("scripts/x.py", ".githooks/pre-push", ".claude/settings.json", "agents/roles.yaml", "CLAUDE.md", ".github/workflows/ci.yml"):
            self.stage(path)
        self.assertEqual(self.hook()[0], 0)
        self.assertFalse(self.gradle_called())

    def test_a_kotlin_file_runs_gradle_spotless_and_detekt(self):
        self.stage("app/src/main/A.kt")
        rc, out = self.hook()
        self.assertEqual(rc, 0, out)
        self.assertTrue(any("spotlessCheck" in c and "detekt" in c for c in self.calls()), self.calls())

    def test_one_kotlin_file_among_docs_builds(self):
        self.stage("docs/a.md")
        self.stage("core/domain/src/main/kotlin/B.kt")
        self.assertEqual(self.hook()[0], 0)
        self.assertTrue(self.gradle_called())

    def test_gradle_build_files_and_config_build(self):
        for path in ("build.gradle.kts", "gradle/libs.versions.toml", "config/detekt/detekt.yml", ".editorconfig"):
            if os.path.exists(self.log):
                os.remove(self.log)
            self.stage(path)
            self.assertEqual(self.hook()[0], 0)
            self.assertTrue(self.gradle_called(), path)

    def test_deleting_a_kotlin_file_builds(self):
        self.stage("app/src/main/A.kt")
        self.run_git("commit", "-q", "-m", "kt")
        self.run_git("rm", "-q", "app/src/main/A.kt")
        self.assertEqual(self.hook()[0], 0)
        self.assertTrue(self.gradle_called())

    def test_moving_a_kotlin_file_into_docs_builds(self):
        """Rename detection would hide the source path; the hook lists both paths."""
        self.stage("app/src/main/Foo.kt", "class Foo")
        self.run_git("commit", "-q", "-m", "kt")
        os.makedirs(os.path.join(self.repo, "docs"))
        self.run_git("mv", "app/src/main/Foo.kt", "docs/Foo.kt")
        self.assertEqual(self.hook()[0], 0)
        self.assertTrue(self.gradle_called())

    def test_nothing_staged_builds_because_unknown_means_build(self):
        self.assertEqual(self.hook()[0], 0)
        self.assertTrue(self.gradle_called())

    def test_failing_guards_block_before_gradle(self):
        self.stage("app/src/main/A.kt")
        rc, _ = self.hook(STUB_GUARDS="1")
        self.assertEqual(rc, 1)
        self.assertFalse(self.gradle_called())

    def test_failing_guards_block_a_docs_only_commit_too(self):
        self.stage("docs/a.md")
        self.assertEqual(self.hook(STUB_GUARDS="1")[0], 1)

    def test_gradle_exit_code_passes_through(self):
        self.stage("app/src/main/A.kt")
        self.assertEqual(self.hook(STUB_GRADLE="3")[0], 3)

    def test_missing_scope_script_builds(self):
        self.stage("docs/a.md")
        os.remove(os.path.join(self.repo, "scripts", "hooks", "prepush_scope.py"))
        self.assertEqual(self.hook()[0], 0)
        self.assertTrue(self.gradle_called())


if __name__ == "__main__":
    unittest.main()
