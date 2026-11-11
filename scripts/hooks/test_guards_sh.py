"""Tests for scripts/guards.sh, run against throwaway git repos. Run: python3 -I -m unittest discover -s scripts/hooks

Every guard has a case that must fail and a neighbouring case that must pass, so a guard that
stops firing (or starts firing on clean code) breaks this suite.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import gitenv  # noqa: F401  (drops GIT_DIR and friends, see gitenv.py)

HERE = os.path.dirname(os.path.abspath(__file__))
GUARDS = os.path.join(HERE, "..", "guards.sh")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


class Repo:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="guards-test-")
        os.makedirs(os.path.join(self.dir, "scripts"))
        shutil.copy(GUARDS, os.path.join(self.dir, "scripts", "guards.sh"))
        self.git("init", "-q", "-b", "work")
        self.write("README.txt", "hello\n")
        self.commit("base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, env=dict(os.environ, **GIT_ENV))
        assert r.returncode == 0, (args, r.stderr)
        return r.stdout

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def commit(self, msg="c"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def guards(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("CI", "GUARD_BASE", "GOLDEN_UPDATE", "GUARD_MAX_DIFF")}
        e.update(env)
        r = subprocess.run(["bash", "scripts/guards.sh", *args], cwd=self.dir, capture_output=True, text=True, env=e)
        return r.returncode, r.stdout + r.stderr

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class GuardsCase(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def assertFails(self, needle, *args, **env):
        rc, out = self.repo.guards(*args, **env)
        self.assertNotEqual(rc, 0, out)
        self.assertIn(needle, out)

    def assertPasses(self, *args, **env):
        rc, out = self.repo.guards(*args, **env)
        self.assertEqual(rc, 0, out)
        self.assertIn("guards: ok", out)


class CleanAndDisabledTests(GuardsCase):
    def test_clean_repo_passes(self):
        self.repo.write("app/src/test/kotlin/A.kt", "class A { @Test fun ok() {} }\n")
        self.repo.commit()
        self.assertPasses()

    def test_disabled_annotation_forms_fail(self):
        forms = [
            "@Ignore", "@Ignored", "@org.junit.Ignore", "@kotlin.test.Ignore", "@Disabled", "@Disabled(\"x\")",
            "@DisabledOnOs(OS.LINUX)", "@org.junit.jupiter.api.Disabled", "@org.junit.jupiter.api.DisabledIf(\"c\")",
            "@EnabledIf(\"c\")", "@org.junit.jupiter.api.condition.EnabledOnOs(OS.MAC)",
        ]
        for form in forms:
            with self.subTest(form=form):
                self.repo.write("core/src/test/kotlin/B.kt", f"class B {{ {form} @Test fun t() {{}} }}\n")
                self.repo.commit()
                self.assertFails("guard: disabled test:")
        self.repo.write("core/src/test/kotlin/B.kt", "class B { @Test fun t() {} }\n")
        self.repo.commit()
        self.assertPasses()

    def test_aliased_and_backticked_disabled_annotations_fail(self):
        """R10-11."""
        forms = [
            "import org.junit.jupiter.api.Disabled as Off\nclass B { @Off @Test fun t() {} }",
            "typealias Later = org.junit.Ignore\nclass B { @Later @Test fun t() {} }",
            "class B { @`Disabled` @Test fun t() {} }",
            "class B { @org.junit.jupiter.api.`Disabled` @Test fun t() {} }",
        ]
        for form in forms:
            with self.subTest(form=form):
                self.repo.write("core/src/test/kotlin/B.kt", form + "\n")
                self.repo.commit()
                self.assertFails("guard: disabled test:")
        self.repo.write("core/src/test/kotlin/B.kt", "import org.junit.jupiter.api.Test as T\nclass B { @T fun t() {} }\n")
        self.repo.commit()
        self.assertPasses()

    def test_python_skip_forms_in_hook_tests_fail_even_in_the_guard_suite(self):
        """R10-10: the hook suites are a CI gate, so skipping one must fail like skipping a Kotlin test."""
        forms = ["@unittest." + "skip('flaky')", "@unittest." + "skip" + "If(True, 'x')", "@unittest." + "skip" + "Unless(False, 'x')",
                 "self.skip" + "Test('x')", "raise unittest.Skip" + "Test('x')", "@unittest.expected" + "Failure"]
        for name in ("test_something.py", "test_guards_sh.py"):
            for form in forms:
                with self.subTest(file=name, form=form):
                    self.repo.write("scripts/hooks/" + name, f"import unittest\nclass T(unittest.TestCase):\n    {form}\n    def test_a(self): pass\n")
                    self.repo.commit()
                    self.assertFails("guard: skipped python test:")
        self.repo.write("scripts/hooks/test_something.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self): pass\n")
        self.repo.write("scripts/hooks/test_guards_sh.py", "# skipped diff-based checks are mentioned in prose\n")
        self.repo.commit()
        self.assertPasses()

    def test_focused_and_skipped_js_tests_fail(self):
        for form in ["it.only('a', () => {})", "describe.skip('a', () => {})", "xit('a', () => {})", "fit('a', () => {})"]:
            with self.subTest(form=form):
                self.repo.write("firebase/test/a.test.js", form + "\n")
                self.repo.commit()
                self.assertFails("guard: disabled")
        self.repo.write("firebase/test/a.test.js", "it('a', () => {})\n")
        self.repo.commit()
        self.assertPasses()

    def test_enabled_false_is_allowed_in_production_code_only(self):
        self.repo.write("app/src/main/kotlin/P.kt", "val x = Feature(enabled = false)\n")
        self.repo.commit()
        self.assertPasses()
        self.repo.write("app/src/test/kotlin/P.kt", "val x = Feature(enabled = false)\n")
        self.repo.commit()
        self.assertFails("guard: disabled or focused test:")

    def test_disabling_tests_through_build_config_fails(self):
        for line in ["tasks.test { enabled = false }", "excludeTests(\"x\")", "failOnNoDiscoveredTests = false"]:
            with self.subTest(line=line):
                self.repo.write("core/build.gradle.kts", line + "\n")
                self.repo.commit()
                rc, out = self.repo.guards()
                self.assertNotEqual(rc, 0, out)
        self.repo.write("core/build.gradle.kts", "plugins { kotlin(\"jvm\") }\n")
        self.repo.commit()
        self.assertPasses()


class Suppressions(GuardsCase):
    def test_unjustified_suppression_fails_and_justified_passes(self):
        self.repo.write("app/src/main/kotlin/S.kt", "@Suppress(\"X\") fun f() {}\n")
        self.repo.commit()
        self.assertFails("guard: unjustified suppression:")
        self.repo.write("app/src/main/kotlin/S.kt", "@Suppress(\"X\") fun f() {} // justified: generated callback signature\n")
        self.repo.commit()
        self.assertPasses()

    def test_empty_justification_fails(self):
        self.repo.write("app/src/main/kotlin/S.kt", "@Suppress(\"X\") fun f() {} // justified:\n")
        self.repo.commit()
        self.assertFails("guard: unjustified suppression:")

    def test_weakened_settings_fail(self):
        for line in ["ignoreFailures = true", "abortOnError = false", "warningsAsErrors = false", "active: false", "maxIssues: 5",
                     "disable += \"MissingTranslation\""]:
            with self.subTest(line=line):
                self.repo.write("config/x.txt", line + "\n")
                self.repo.commit()
                self.assertFails("guard: unjustified suppression:")


class Baselines(GuardsCase):
    def test_baseline_file_name_fails(self):
        self.repo.write("config/detekt/baseline.xml", "<x/>\n")
        self.repo.commit()
        self.assertFails("guard: baseline file:")

    def test_baseline_wiring_fails(self):
        self.repo.write("build.gradle.kts", "detekt { baseline = file(\"x\") }\n")
        self.repo.commit()
        self.assertFails("guard: baseline wiring:")


class DiffChecks(GuardsCase):
    def test_lowered_threshold_fails_and_raised_passes(self):
        self.repo.write("app/build.gradle.kts", "kover { minBound(80) }\n")
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.repo.write("app/build.gradle.kts", "kover { minBound(90) }\n")
        self.repo.commit()
        self.assertPasses()
        self.repo.write("app/build.gradle.kts", "kover { minBound(70) }\n")
        self.repo.commit()
        self.assertFails("guard: lowered threshold:")

    def test_removed_check_setting_fails(self):
        self.repo.write("app/build.gradle.kts", "kover { minBound(80) }\n")
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.repo.write("app/build.gradle.kts", "kover { }\n")
        self.repo.commit()
        self.assertFails("guard: removed check setting:")

    def test_screenshot_reference_change_needs_label(self):
        self.repo.write("app/src/test/snapshots/a.png", "png1")
        self.repo.commit()
        self.assertFails("screenshot references changed", GUARD_BASE="origin/main")
        self.assertPasses(GOLDEN_UPDATE="1")

    def test_diff_size_limit_is_enforced_only_in_ci(self):
        self.repo.write("notes.txt", "x\n" * 50)
        self.repo.commit()
        self.assertPasses()  # not CI
        self.assertFails("changed lines (limit 10)", CI="true", GUARD_MAX_DIFF="10")
        self.assertPasses(CI="true", GUARD_MAX_DIFF="100")

    def test_non_numeric_diff_limit_fails(self):
        self.assertFails("GUARD_MAX_DIFF is not a number", CI="true", GUARD_MAX_DIFF="lots")

    def test_missing_base_is_a_hard_failure_in_ci_only(self):
        self.repo.git("update-ref", "-d", "refs/remotes/origin/main")
        rc, out = self.repo.guards()
        self.assertEqual(rc, 0, out)
        self.assertIn("skipped diff-based checks", out)
        self.assertFails("no base/merge-base", CI="true")


class StagedMode(GuardsCase):
    def test_staged_flags_only_the_index(self):
        self.repo.write("app/src/main/kotlin/S.kt", "@Suppress(\"X\") fun f() {}\n")
        self.assertPasses("--staged")  # present on disk but not staged
        self.repo.git("add", "app/src/main/kotlin/S.kt")
        self.assertFails("guard: unjustified suppression:", "--staged")

    def test_staged_ignores_a_fixed_working_tree(self):
        self.repo.write("app/src/main/kotlin/S.kt", "@Suppress(\"X\") fun f() {}\n")
        self.repo.git("add", "app/src/main/kotlin/S.kt")
        self.repo.write("app/src/main/kotlin/S.kt", "fun f() {}\n")  # fixed on disk, index still bad
        self.assertFails("guard: unjustified suppression:", "--staged")

    def test_staged_baseline_file_fails(self):
        self.repo.write("config/baseline.xml", "<x/>\n")
        self.repo.git("add", "config/baseline.xml")
        self.assertFails("guard: baseline file:", "--staged")

    def test_staged_clean_passes_without_a_base_ref(self):
        self.repo.git("update-ref", "-d", "refs/remotes/origin/main")
        self.repo.write("app/src/main/kotlin/S.kt", "fun f() {}\n")
        self.repo.git("add", "app/src/main/kotlin/S.kt")
        self.assertPasses("--staged", CI="true")


class Exclusions(GuardsCase):
    def test_prose_and_docs_may_mention_patterns(self):
        self.repo.write("docs/notes.md", "Use @Ignore never; baseline.xml is forbidden; Suppress(\"x\")\n")
        self.repo.write("handoff/h.md", "@Disabled\n")
        self.repo.commit()
        self.assertPasses()


if __name__ == "__main__":
    unittest.main()
