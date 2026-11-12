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

    def test_typealias_pattern_does_not_flag_ordinary_production_types(self):
        """R11-09."""
        self.repo.write("app/src/main/kotlin/X.kt", "class DisabledReasons\ntypealias Reasons = DisabledReasons\ntypealias L = OnDisabledChangeListener\n")
        self.repo.commit()
        self.assertPasses()

    def test_imported_python_skip_decorators_fail(self):
        """R10-10: the plain imported form."""
        for body in ("from unittest imp" + "ort skip\n@" + "skip('x')\n", "from unittest imp" + "ort skip" + "If\n@" + "skip" + "If(True, 'x')\n"):
            with self.subTest(body=body):
                self.repo.write("scripts/hooks/test_a.py", "import unittest\n" + body + "class T(unittest.TestCase):\n    def test_a(self): pass\n")
                self.repo.commit()
                self.assertFails("guard: skipped python test:")

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


# (path, unjustified line, same line with the language's justification). The justified form must pass, the bare one must fail.
SUPPRESSION_SYNTAX = [
    ("a.py", "import os  # noqa: F401", "import os  # noqa: F401  # justified: re-export for callers"),
    ("a.py", "import os  # NOQA", "import os  # NOQA  # justified: re-export for callers"),
    ("a.py", "# ruff: noqa: E402", "# ruff: noqa: E402  # justified: path set up first"),
    ("a.py", "# flake8: noqa", "# flake8: noqa  # justified: generated file"),
    ("a.py", "x: int = f()  # type: ignore[attr-defined]", "x: int = f()  # type: ignore[attr-defined]  # justified: stub lacks attr"),
    ("a.py", "# mypy: ignore-errors", "# mypy: ignore-errors  # justified: vendored module"),
    ("a.py", "if x:  # pragma: no cover", "if x:  # pragma: no cover  # justified: debug only"),
    ("a.py", "if x:  # pragma: no branch", "if x:  # pragma: no branch  # justified: loop always runs"),
    ("a.py", "# fmt: off", "# fmt: off  # justified: aligned table"),
    ("a.py", "y = 1  # fmt: skip", "y = 1  # fmt: skip  # justified: aligned table"),
    ("a.py", "# yapf: disable", "# yapf: disable  # justified: aligned table"),
    ("a.py", "import b  # isort: skip", "import b  # isort: skip  # justified: order matters"),
    ("a.ts", "// eslint-disable-next-line no-console", "// eslint-disable-next-line no-console -- justified: CLI output"),
    ("a.ts", "foo(); // eslint-disable-line no-console", "foo(); // eslint-disable-line no-console // justified: CLI output"),
    ("a.js", "/* eslint-disable */", "/* eslint-disable -- justified: generated file */"),
    ("a.ts", "// @ts-ignore", "// @ts-ignore justified: upstream typing bug"),
    ("a.ts", "// @ts-expect-error", "// @ts-expect-error justified: upstream typing bug"),
    ("a.ts", "// @ts-nocheck", "// @ts-nocheck justified: generated file"),
    ("a.js", "/* c8 ignore next */", "/* c8 ignore next -- justified: unreachable guard */"),
    ("a.ts", "/* istanbul ignore next */", "/* istanbul ignore next -- justified: unreachable guard */"),
    ("a.ts", "/* v8 ignore next */", "/* v8 ignore next -- justified: unreachable guard */"),
    ("a.ts", "// prettier-ignore", "// prettier-ignore justified: aligned table"),
    ("a.ts", "// biome-ignore lint/suspicious/noExplicitAny: ok", "// biome-ignore lint/suspicious/noExplicitAny: ok // justified: JSON boundary"),
    ("app/src/main/kotlin/F.kt", "// @formatter:off", "// @formatter:off // justified: aligned table"),
]

# (path, unjustified line, same line with a justification)
CONFIG_RELAXATIONS = [
    ("pyproject.toml", "[tool.ruff.lint.per-file-ignores]", "[tool.ruff.lint.per-file-ignores]  # justified: tests may assert"),
    ("ruff.toml", "extend-per-file-ignores = {}", "extend-per-file-ignores = {}  # justified: tests may assert"),
    ("pyproject.toml", "ignore = [\"E501\"]", "ignore = [\"E501\"]  # justified: long URLs"),
    ("ruff.toml", "extend-ignore = [\"E501\"]", "extend-ignore = [\"E501\"]  # justified: long URLs"),
    ("ruff.toml", "exclude = [\"gen\"]", "exclude = [\"gen\"]  # justified: generated code"),
    ("ruff.toml", "extend-exclude = [\"gen\"]", "extend-exclude = [\"gen\"]  # justified: generated code"),
    (".flake8", "ignore = E501", "ignore = E501  # justified: long URLs"),
    ("mypy.ini", "ignore_errors = True", "ignore_errors = True  # justified: vendored module"),
    ("pyproject.toml", "ignore_errors = true", "ignore_errors = true  # justified: vendored module"),
    ("mypy.ini", "ignore_missing_imports = True", "ignore_missing_imports = True  # justified: untyped dependency"),
    ("mypy.ini", "strict = False", "strict = False  # justified: migration in progress"),
    ("pyproject.toml", "strict = false", "strict = false  # justified: migration in progress"),
    ("mypy.ini", "disallow_untyped_defs = False", "disallow_untyped_defs = False  # justified: migration in progress"),
    ("mypy.ini", "check_untyped_defs = false", "check_untyped_defs = false  # justified: migration in progress"),
    ("mypy.ini", "warn_unused_ignores = False", "warn_unused_ignores = False  # justified: migration in progress"),
    ("mypy.ini", "follow_imports = skip", "follow_imports = skip  # justified: untyped dependency"),
    ("mypy.ini", "disable_error_code = attr-defined", "disable_error_code = attr-defined  # justified: stub lacks attr"),
    ("mypy.ini", "allow_untyped_defs = True", "allow_untyped_defs = True  # justified: migration in progress"),
    ("tsconfig.json", "\"strict\": false,", "\"strict\": false, // justified: migration in progress"),
    ("firebase/test/tsconfig.json", "\"noImplicitAny\": false,", "\"noImplicitAny\": false, // justified: migration in progress"),
    ("tsconfig.json", "\"noUncheckedIndexedAccess\": false", "\"noUncheckedIndexedAccess\": false // justified: migration in progress"),
    ("tsconfig.json", "\"exactOptionalPropertyTypes\": false", "\"exactOptionalPropertyTypes\": false // justified: migration in progress"),
    ("tsconfig.base.json", "\"checkJs\": false", "\"checkJs\": false // justified: migration in progress"),
    ("eslint.config.js", "'no-console': 'off',", "'no-console': 'off', // justified: CLI output"),
    ("eslint.config.mjs", "\"no-console\": 0,", "\"no-console\": 0, // justified: CLI output"),
    ("eslint.config.js", "'no-console': ['off'],", "'no-console': ['off'], // justified: CLI output"),
    ("eslint.config.js", "'no-console': 'warn',", "'no-console': 'warn', // justified: CLI output"),
    ("eslint.config.js", "ignores: ['gen/**'],", "ignores: ['gen/**'], // justified: generated code"),
    (".eslintrc.json", "\"ignorePatterns\": [\"gen\"],", "\"ignorePatterns\": [\"gen\"], // justified: generated code"),
    ("eslint.config.js", "reportUnusedDisableDirectives: false,", "reportUnusedDisableDirectives: false, // justified: legacy"),
    (".coveragerc", "omit = */tests/*", "omit = */tests/*  # justified: test code"),
    (".coveragerc", "exclude_lines =", "exclude_lines =  # justified: debug only"),
    ("pyproject.toml", "exclude_also = [\"if x:\"]", "exclude_also = [\"if x:\"]  # justified: debug only"),
    ("vitest.config.ts", "coveragePathIgnorePatterns: ['gen'],", "coveragePathIgnorePatterns: ['gen'], // justified: generated code"),
    ("jest.config.js", "coveragePathIgnorePatterns: ['gen'],", "coveragePathIgnorePatterns: ['gen'], // justified: generated code"),
]

# Valid, strict settings in the same files must not fire.
CONFIG_CLEAN = [
    ("pyproject.toml", "[tool.ruff.lint]\nselect = [\"E\", \"F\", \"B\"]\n[tool.mypy]\nstrict = true\nwarn_unused_ignores = true\n"),
    ("mypy.ini", "[mypy]\nstrict = True\ndisallow_untyped_defs = True\nignore_errors = False\n"),
    ("tsconfig.json", "{\n  \"compilerOptions\": {\"strict\": true, \"noImplicitAny\": true, \"skipLibCheck\": true}\n}\n"),
    ("eslint.config.js", "export default [{rules: {'no-console': 'error', 'eqeqeq': ['error', 'always'], 'max-len': [2, 120]}}];\n"),
]


class LinterSuppressions(GuardsCase):
    def check_pair(self, path, bad, good):
        self.repo.write(path, bad + "\n")
        self.repo.commit()
        self.assertFails("guard: unjustified suppression:")
        self.repo.write(path, good + "\n")
        self.repo.commit()
        self.assertPasses()

    def test_each_linter_suppression_needs_a_justification(self):
        for path, bad, good in SUPPRESSION_SYNTAX:
            with self.subTest(line=bad):
                self.check_pair(path, bad, good)

    def test_each_config_relaxation_needs_a_justification(self):
        for path, bad, good in CONFIG_RELAXATIONS:
            with self.subTest(path=path, line=bad):
                self.check_pair(path, bad, good)

    def test_empty_justification_in_a_block_comment_fails(self):
        self.repo.write("a.js", "/* eslint-disable justified: */\n")
        self.repo.commit()
        self.assertFails("guard: unjustified suppression:")

    def test_justification_on_another_line_does_not_count(self):
        self.repo.write("a.py", "# justified: because\nimport os  # noqa: F401\n")
        self.repo.commit()
        self.assertFails("guard: unjustified suppression:")

    def test_strict_settings_do_not_fire(self):
        for path, text in CONFIG_CLEAN:
            with self.subTest(path=path):
                self.repo.write(path, text)
                self.repo.commit()
                self.assertPasses()

    def test_config_patterns_only_apply_to_config_files(self):
        # `ignore = x`, `strict = false` and rules set to 'off' are ordinary text outside linter config files.
        self.repo.write("app/src/main/kotlin/K.kt", "val a = mapOf(\"no-console\" to \"off\")\nval ignores = listOf(1)\nval strict = false\n")
        self.repo.write("config/data.txt", "ignore = x\nstrict = false\nexclude = y\n")
        self.repo.write("a.py", "ignore = 1\nstrict = False\nexclude = [1]\n")
        self.repo.commit()
        self.assertPasses()

    def test_staged_mode_catches_them_too(self):
        self.repo.write("a.ts", "// @ts-ignore\n")
        self.repo.git("add", "-A")
        self.assertFails("guard: unjustified suppression:", "--staged")

    def test_formatter_ignore_files_fail_without_escape_hatch(self):
        for name in (".prettierignore", ".eslintignore", ".stylelintignore", "web/.prettierignore"):
            with self.subTest(name=name):
                self.repo.write(name, "gen/ # justified: generated code\n")
                self.repo.commit()
                self.assertFails("guard: ignore file:")
                self.repo.git("rm", "-q", "-f", name)
                self.repo.commit()

    def test_prose_may_mention_the_directives(self):
        self.repo.write("docs/x.md", "Never write # noqa or // @ts-ignore or eslint-disable or .prettierignore\n")
        self.repo.commit()
        self.assertPasses()

    def test_existing_repo_files_do_not_trip_the_guard(self):
        # False-positive check: the guard run on this repository itself (content checks only) must pass.
        env = {k: v for k, v in os.environ.items() if k not in ("CI", "GOLDEN_UPDATE", "GUARD_MAX_DIFF")}
        env["GUARD_BASE"] = "refs/none/missing"
        r = subprocess.run(["bash", GUARDS], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("guards: ok", r.stdout)

    def test_every_noqa_in_the_repo_is_justified(self):
        root = os.path.join(HERE, "..", "..")
        r = subprocess.run(["git", "grep", "-nI", "-i", "noqa", "--", "*.py", ":!scripts/hooks/test_guards_sh.py"],
                           cwd=root, capture_output=True, text=True)
        lines = r.stdout.splitlines()
        self.assertTrue(lines, "expected the repository to carry noqa lines")
        bare = [ln for ln in lines if "justified:" not in ln]
        self.assertEqual(bare, [])


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

    def test_big_pr_cap_1500_boundaries(self):
        # CI passes GUARD_MAX_DIFF=1500 for PRs labelled big-pr (owner decision D2): above 1500 fails, up to 1500 passes.
        self.repo.write("notes.txt", "x\n" * 3500)
        self.repo.commit()
        self.assertFails("changed lines (limit 1500)", CI="true", GUARD_MAX_DIFF="1500")
        self.repo.write("notes.txt", "x\n" * 1499)
        self.repo.commit()
        self.assertPasses(CI="true", GUARD_MAX_DIFF="1500")  # just under the cap
        self.repo.write("notes.txt", "x\n" * 1500)
        self.repo.commit()
        self.assertPasses(CI="true", GUARD_MAX_DIFF="1500")  # exactly at the cap
        self.repo.write("notes.txt", "x\n" * 1501)
        self.repo.commit()
        self.assertFails("changed lines (limit 1500)", CI="true", GUARD_MAX_DIFF="1500")
        self.repo.write("notes.txt", "x\n" * 6000)
        self.repo.commit()
        self.assertFails("changed lines (limit 1500)", CI="true", GUARD_MAX_DIFF="1500")  # old 6000 cap no longer enough

    def test_default_cap_is_600_without_override(self):
        self.repo.write("notes.txt", "x\n" * 601)
        self.repo.commit()
        self.assertFails("changed lines (limit 600)", CI="true")
        self.repo.write("notes.txt", "x\n" * 600)
        self.repo.commit()
        self.assertPasses(CI="true")

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
