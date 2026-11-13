"""Run: python3 -I -m unittest discover -s scripts/hooks
Tests prepush_scope.py: the pre-push hook skips the Android build for diffs that cannot affect it. Unknown paths build (fail closed)."""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prepush_scope  # noqa: E402  # justified: must follow the sys.path insert above

import gitenv  # noqa: E402, F401  # justified: after the sys.path insert, imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

ZERO = "0" * 40


class Classify(unittest.TestCase):
    def test_non_android_paths_skip(self):
        for p in ("docs/PLAN.md", "handoff/x.md", "README.md", "REVIEW.md", "scripts/verify.sh", "scripts/hooks/x.py",
                  ".githooks/pre-push", ".claude/settings.json", ".github/workflows/ci.yml", "agents/roles.yaml",
                  "firebase/firestore.rules", "metrics/sessions/a.json", "CLAUDE.md"):
            self.assertEqual(prepush_scope.classify([p]), "skip", p)

    def test_android_paths_build(self):
        for p in ("app/src/main/java/A.kt", "core/domain/src/main/kotlin/B.kt", "build.gradle.kts", "settings.gradle.kts",
                  "gradle/libs.versions.toml", "gradle.properties", "gradlew", "config/detekt/detekt.yml", "app/src/main/res/values/strings.xml"):
            self.assertEqual(prepush_scope.classify([p]), "android", p)

    def test_markdown_inside_modules_still_builds(self):
        self.assertEqual(prepush_scope.classify(["app/src/main/assets/notes.md"]), "android")
        self.assertEqual(prepush_scope.classify(["core/domain/README.md"]), "android")

    def test_mixed_builds(self):
        self.assertEqual(prepush_scope.classify(["docs/PLAN.md", "app/src/main/java/A.kt"]), "android")

    def test_unknown_path_builds(self):
        self.assertEqual(prepush_scope.classify(["newdir/file.txt"]), "android")
        self.assertEqual(prepush_scope.classify(["scripts/../app/A.kt"]), "android")

    def test_empty_diff_skips(self):
        self.assertEqual(prepush_scope.classify([]), "skip")


class Cli(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "core.hooksPath", "/dev/null")
        self.commit("README.md", "a")
        self.base = self.rev()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def rev(self):
        return self.git("rev-parse", "HEAD")

    def commit(self, path, content):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")

    def scope(self, local, remote, extra_env=None):
        line = f"refs/heads/b {local} refs/heads/b {remote}\n"
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py")], input=line, cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_docs_only_push_skips(self):
        self.commit("docs/a.md", "x")
        self.commit("scripts/t.sh", "x")
        self.assertEqual(self.scope(self.rev(), self.base), "skip")

    def test_code_change_in_any_pushed_commit_builds(self):
        self.commit("app/src/main/A.kt", "x")
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), self.base), "android")

    def test_unknown_remote_sha_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), "1" * 40), "android")

    def test_new_branch_without_origin_main_builds(self):
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), ZERO), "android")

    def test_new_branch_uses_merge_base_with_origin_main(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.commit("docs/a.md", "x")
        self.assertEqual(self.scope(self.rev(), ZERO), "skip")
        self.commit("app/src/main/A.kt", "x")
        self.assertEqual(self.scope(self.rev(), ZERO), "android")

    def test_moving_an_android_file_into_a_skip_directory_builds(self):
        """R10-53: rename detection hides the source path; the build lost a file."""
        self.commit("app/src/main/kotlin/Foo.kt", "class Foo")
        base = self.rev()
        os.makedirs(os.path.join(self.repo, "docs"))
        self.git("mv", "app/src/main/kotlin/Foo.kt", "docs/Foo.kt")
        self.git("commit", "-q", "-m", "move")
        self.assertEqual(self.scope(self.rev(), base), "android")

    def test_branch_delete_skips(self):
        self.assertEqual(self.scope(ZERO, self.base), "skip")

    def test_garbage_input_builds(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py")], input="nonsense\n", cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "android"))

    def test_no_input_builds(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "prepush_scope.py")], input="", cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "android"))


if __name__ == "__main__":
    unittest.main()
