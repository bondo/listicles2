"""Tests for scripts/guards.sh, run against throwaway git repos. Run: python3 -I -m unittest discover -s scripts/hooks

Every guard has a case that must fail and a neighbouring case that must pass, so a guard that
stops firing (or starts firing on clean code) breaks this suite.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest

import gitenv  # noqa: F401  # justified: imported for its side effect, drops GIT_DIR and friends (see gitenv.py)

HERE = os.path.dirname(os.path.abspath(__file__))
GUARDS = os.path.join(HERE, "..", "guards.sh")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def pad_short_reasons(text):
    """Owner decision (#46): a `justified:` reason needs 3 words. Most fixtures below predate that and use a short reason
    ("CLI output") only as the marker that must waive a hit, so write() pads a reason of 1 or 2 words. A reason with no
    letter or digit at all is left alone, and the tests of the rule itself write with raw=True."""
    def pad(m):
        n = len(re.findall(r"[A-Za-z]{2,}", m.group(2)))
        return m.group(1) + ("fixture padding words " if n < 3 and re.search(r"[A-Za-z0-9]", m.group(2)) else "") + m.group(2)
    return re.sub(r"(justified:[ \t]*)([^\n]*)", pad, text)


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

    def write(self, rel, text, raw=False):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text if raw else pad_short_reasons(text))

    def write_bytes(self, rel, size):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * size)

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

    def test_typealias_pattern_does_not_flag_production_types_named_disabled_in_on_for(self):
        """R12-03 (#27): only the real JUnit Disabled* annotation names count, not any type that starts with them."""
        self.repo.write("app/src/main/kotlin/Y.kt", "typealias A = DisabledInventory\ntypealias B = DisabledOnboardingStep\ntypealias C = DisabledForecast\n"
                        "typealias D = DisabledIfaceNotes\ntypealias E = com.example.DisabledInput\n")
        self.repo.commit()
        self.assertPasses()

    def test_typealias_pattern_still_flags_every_real_junit_disabled_annotation(self):
        """R12-03 (#27) negative cases: the aliases the pattern was written for must keep failing."""
        names = ["Disabled", "DisabledIf", "DisabledIfEnvironmentVariable", "DisabledIfEnvironmentVariables", "DisabledIfSystemProperty",
                 "DisabledIfSystemProperties", "DisabledOnOs", "DisabledOnJre", "DisabledOnJreRange", "DisabledForJreRange", "DisabledInNativeImage"]
        for name in names:
            with self.subTest(name=name):
                self.repo.write("core/src/test/kotlin/Z.kt", f"typealias Later = org.junit.jupiter.api.condition.{name}\n")
                self.repo.commit()
                self.assertFails("guard: disabled test:")

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
    # R1-03: inline ESLint rule config and mypy per-file flags
    ("a.js", "/* eslint no-console: \"off\" */", "/* eslint no-console: \"off\" -- justified: CLI output */"),
    ("a.js", "/* eslint no-console: 0 */", "/* eslint no-console: 0 -- justified: CLI output */"),
    ("a.ts", "/*eslint eqeqeq: 0*/", "/*eslint eqeqeq: 0 -- justified: legacy */"),
    ("a.py", "# mypy: no-strict-optional", "# mypy: no-strict-optional  # justified: migration in progress"),
    ("a.py", "# mypy: no-warn-unused-ignores", "# mypy: no-warn-unused-ignores  # justified: migration in progress"),
    ("a.py", "# mypy: disallow-untyped-defs=False", "# mypy: disallow-untyped-defs=False  # justified: migration in progress"),
    ("a.py", "# mypy: check-untyped-defs=False", "# mypy: check-untyped-defs=False  # justified: migration in progress"),
    ("a.py", "# mypy: ignore-missing-imports", "# mypy: ignore-missing-imports  # justified: untyped dependency"),
    ("a.py", "# mypy: follow-imports=skip", "# mypy: follow-imports=skip  # justified: untyped dependency"),
    # R1-04: coverage.py accepts these spellings of its default exclude regex
    ("a.py", "if x:  # pragma no cover", "if x:  # pragma no cover  # justified: debug only"),
    ("a.py", "if x:  # PRAGMA: NO COVER", "if x:  # PRAGMA: NO COVER  # justified: debug only"),
    ("a.py", "for i in y:  # pragma nobranch", "for i in y:  # pragma nobranch  # justified: loop always runs"),
]

# (path, unjustified line, same line with a justification)
CONFIG_RELAXATIONS = [
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
    # R1-02: dotted and quoted keys, inline tables, configparser booleans
    ("pyproject.toml", "lint.ignore = [\"E501\"]", "lint.ignore = [\"E501\"]  # justified: long URLs"),
    ("pyproject.toml", "tool.ruff.lint.extend-ignore = [\"E501\"]", "tool.ruff.lint.extend-ignore = [\"E501\"]  # justified: long URLs"),
    ("ruff.toml", "lint.extend-ignore = [\"E501\"]", "lint.extend-ignore = [\"E501\"]  # justified: long URLs"),
    ("ruff.toml", "lint = { ignore = [\"E501\"] }", "lint = { ignore = [\"E501\"] }  # justified: long URLs"),
    ("ruff.toml", "lint = { extend-ignore = [\"E501\"] }", "lint = { extend-ignore = [\"E501\"] }  # justified: long URLs"),
    ("ruff.toml", "\"ignore\" = [\"E501\"]", "\"ignore\" = [\"E501\"]  # justified: long URLs"),
    ("pyproject.toml", "'extend-ignore' = [\"E501\"]", "'extend-ignore' = [\"E501\"]  # justified: long URLs"),
    ("ruff.toml", "lint.exclude = [\"gen\"]", "lint.exclude = [\"gen\"]  # justified: generated code"),
    ("pyproject.toml", "\"exclude_also\" = [\"if x:\"]", "\"exclude_also\" = [\"if x:\"]  # justified: debug only"),
    ("mypy.ini", "ignore_errors = yes", "ignore_errors = yes  # justified: vendored module"),
    ("mypy.ini", "ignore_errors=on", "ignore_errors=on  # justified: vendored module"),
    ("mypy.ini", "ignore_errors = ON", "ignore_errors = ON  # justified: vendored module"),
    ("mypy.ini", "ignore_missing_imports = Yes", "ignore_missing_imports = Yes  # justified: untyped dependency"),
    ("mypy.ini", "strict = off", "strict = off  # justified: migration in progress"),
    ("mypy.ini", "strict=No", "strict=No  # justified: migration in progress"),
    ("mypy.ini", "disallow_untyped_defs = no", "disallow_untyped_defs = no  # justified: migration in progress"),
    ("mypy.ini", "warn_unused_ignores = OFF", "warn_unused_ignores = OFF  # justified: migration in progress"),
    ("pyproject.toml", "\"strict\" = false", "\"strict\" = false  # justified: migration in progress"),
    ("pyproject.toml", "tool.mypy.ignore_errors = true", "tool.mypy.ignore_errors = true  # justified: vendored module"),
    ("pyproject.toml", "mypy = { strict = false }", "mypy = { strict = false }  # justified: migration in progress"),
    # R1-05: noCheck turns type checking off, and a base config outside *tsconfig*.json is not scanned
    ("tsconfig.json", "\"noCheck\": true", "\"noCheck\": true // justified: migration in progress"),
    ("tsconfig.json", "\"extends\": \"./base.json\",", "\"extends\": \"./base.json\", // justified: base is a strict preset"),
    ("tsconfig.json", "\"extends\": [\"./tsconfig.a.json\", \"./base.json\"],",
     "\"extends\": [\"./tsconfig.a.json\", \"./base.json\"], // justified: base is a strict preset"),
    # R1-06: prettier skips files without a pragma
    (".prettierrc.json", "\"requirePragma\": true,", "\"requirePragma\": true, // justified: legacy repo"),
    (".prettierrc", "requirePragma: true", "requirePragma: true  # justified: legacy repo"),
    ("prettier.config.js", "requirePragma: true,", "requirePragma: true, // justified: legacy repo"),
    (".prettierrc.toml", "requirePragma = true", "requirePragma = true  # justified: legacy repo"),
    (".prettierrc.json", "\"ignorePath\": \".gitignore\",", "\"ignorePath\": \".gitignore\", // justified: generated code"),
]

# R1-01: a justification on a table header or an array opener must not waive the entry lines after it. Every relaxing entry line
# carries its own justification. (path, text with an unjustified entry, same text with every entry justified)
MULTILINE_RELAXATIONS = [
    ("pyproject.toml",
     "[tool.ruff.lint.per-file-ignores]  # justified: tests may assert\n\"src/*\" = [\"ALL\"]",
     "[tool.ruff.lint.per-file-ignores]  # justified: tests may assert\n\"src/*\" = [\"ALL\"]  # justified: generated code"),
    ("pyproject.toml",
     "[tool.ruff.lint.per-file-ignores]\n\"src/*\" = [\"ALL\"]  # justified: generated code",
     "[tool.ruff.lint.per-file-ignores]  # justified: tests may assert\n\"src/*\" = [\"ALL\"]  # justified: generated code"),
    ("ruff.toml",
     "[lint.per-file-ignores]  # justified: tests\n\"tests/*\" = [\"S101\"]  # justified: asserts\n\"gen/*\" = [\"ALL\"]",
     "[lint.per-file-ignores]  # justified: tests\n\"tests/*\" = [\"S101\"]  # justified: asserts\n\"gen/*\" = [\"ALL\"]  # justified: generated"),
    ("pyproject.toml",
     "[tool.ruff.lint]\nignore = [  # justified: long URLs\n  \"E501\",\n]",
     "[tool.ruff.lint]\nignore = [  # justified: long URLs\n  \"E501\",  # justified: long URLs\n]"),
    ("ruff.toml",
     "[lint]\nextend-ignore = [  # justified: long URLs\n  \"E501\",  # justified: long URLs\n  \"F401\",\n]",
     "[lint]\nextend-ignore = [  # justified: long URLs\n  \"E501\",  # justified: long URLs\n  \"F401\",  # justified: re-exports\n]"),
    ("ruff.toml",
     "lint.ignore = [  # justified: long URLs\n  \"E501\", \"F401\"\n]",
     "lint.ignore = [  # justified: long URLs\n  \"E501\", \"F401\"  # justified: long URLs and re-exports\n]"),
    ("pyproject.toml",
     "[tool.coverage.report]\nexclude_lines = [  # justified: debug only\n  \"if TYPE_CHECKING:\",\n]",
     "[tool.coverage.report]\nexclude_lines = [  # justified: debug only\n  \"if TYPE_CHECKING:\",  # justified: typing only\n]"),
    (".coveragerc",
     "[report]\nexclude_lines =  # justified: debug only\n    if TYPE_CHECKING:",
     "[report]\nexclude_lines =  # justified: debug only\n    if TYPE_CHECKING:  # justified: typing only"),
    (".flake8",
     "[flake8]\nignore =  # justified: legacy\n    E501\n    W503",
     "[flake8]\nignore =  # justified: legacy\n    E501  # justified: long URLs\n    W503  # justified: black style"),
    ("eslint.config.js",
     "export default [{\n  ignores: [  // justified: generated\n    'gen/**',\n  ],\n}];",
     "export default [{\n  ignores: [  // justified: generated\n    'gen/**', // justified: generated\n  ],\n}];"),
    ("eslint.config.js",
     "export default [{rules: {\n  'no-console': [\n    'warn',\n    { allow: ['error'] },\n  ],\n}}];",
     "export default [{rules: {\n  'no-console': [\n    'warn', // justified: CLI output\n    { allow: ['error'] },\n  ],\n}}];"),
    ("eslint.config.js",
     "export default [{rules: {\n  'no-console': [\n    0,\n  ],\n}}];",
     "export default [{rules: {\n  'no-console': [\n    0, // justified: CLI output\n  ],\n}}];"),
    ("jest.config.js",
     "module.exports = {\n  coveragePathIgnorePatterns: [  // justified: generated\n    'gen',\n  ],\n};",
     "module.exports = {\n  coveragePathIgnorePatterns: [  // justified: generated\n    'gen', // justified: generated\n  ],\n};"),
]

# Valid, strict settings in the same files must not fire.
CONFIG_CLEAN = [
    ("pyproject.toml", "[tool.ruff.lint]\nselect = [\"E\", \"F\", \"B\"]\n[tool.mypy]\nstrict = true\nwarn_unused_ignores = true\n"),
    ("mypy.ini", "[mypy]\nstrict = True\ndisallow_untyped_defs = True\nignore_errors = False\n"),
    ("tsconfig.json", "{\n  \"compilerOptions\": {\"strict\": true, \"noImplicitAny\": true, \"noEmit\": true}\n}\n"),
    ("eslint.config.js", "export default [{rules: {'no-console': 'error', 'eqeqeq': ['error', 'always'], 'max-len': [2, 120]}}];\n"),
    # R1-09: option objects hold numbers that are not rule severities
    ("eslint.config.js", "export default [{rules: {'max-params': ['error', { max: 1 }], 'max-depth': ['error', { max: 0 }]}}];\n"),
    (".eslintrc.json", "{\"rules\": {\"max-params\": [\"error\", {\"max\": 1}]}}\n"),
    ("eslint.config.js", "export default [{rules: {\n  'max-params': [\n    'error',\n    { max: 1 },\n  ],\n}}];\n"),
    # multi-line strict settings, other keys that merely contain the words, indented TOML keys
    ("pyproject.toml", "[tool.ruff.lint]\nselect = [\n  \"E\",\n  \"F\",\n]\nignore-init-module-imports = true\n"
     "[tool.ruff.format]\nquote-style = \"double\"\n"),
    ("pyproject.toml", "[tool.ruff]\n  ignore = [\"E501\"]  # justified: long URLs\n  line-length = 100\n  target-version = \"py311\"\n"),
    ("pyproject.toml", "[tool.ruff.lint.per-file-ignores]  # justified: tests\n\"tests/*\" = [\"S101\"]  # justified: asserts\n"
     "[tool.mypy]\nstrict = true\nenable_error_code = [\"ignore-without-code\"]\n"),
    ("eslint.config.js", "export default [{rules: {\n  'eqeqeq': [\n    'error',\n    'always',\n  ],\n}}];\n"),
    ("mypy.ini", "[mypy]\nignore_errors = off\nignore_missing_imports = no\nstrict = on\nwarn_unused_ignores = yes\ndisallow_untyped_defs = 1\n"),
    ("tsconfig.json", "{\n  \"extends\": \"./tsconfig.base.json\",\n  \"compilerOptions\": {\"noCheck\": false}\n}\n"),
    ("tsconfig.app.json", "{\n  \"extends\": \"@tsconfig/node20/tsconfig.json\"\n}\n"),
    ("tsconfig.web.json", "{\n  \"extends\": [\"./tsconfig.a.json\", \"./tsconfig.b.json\"]\n}\n"),
    (".prettierrc.json", "{\"semi\": true, \"requirePragma\": false}\n"),
    ("a.py", "# mypy: disallow-untyped-defs=True\n# mypy: warn-unused-ignores\n# mypy: enable-error-code=ignore-without-code\n# pragma: once\n"),
    ("a.js", "/* eslint-env node */\n"),
]


# Round 2 (R2-01..R2-05). (path, text with an unjustified relaxation, same text fully justified)
ROUND2_RELAXATIONS = [
    # R2-01: the opener line need not end in a bracket; every entry carries its own justification
    ("ruff.toml", "[lint]\nignore = [\"E501\",  # justified: x\n  \"F401\",\n]",
     "[lint]\nignore = [\"E501\",  # justified: x\n  \"F401\",  # justified: y\n]"),
    ("eslint.config.js", "export default [{\n  ignores: ['dist/**', // justified: x\n    'src/**',\n  ],\n}];",
     "export default [{\n  ignores: ['dist/**', // justified: x\n    'src/**', // justified: y\n  ],\n}];"),
    ("pyproject.toml", "[tool.coverage.report]\nexclude_lines = [\"if X:\",  # justified: x\n  \"def \",\n]",
     "[tool.coverage.report]\nexclude_lines = [\"if X:\",  # justified: x\n  \"def \",  # justified: y\n]"),
    ("pyproject.toml", "[tool.mypy]\ndisable_error_code = [ # justified: x\n  \"attr-defined\",\n]",
     "[tool.mypy]\ndisable_error_code = [ # justified: x\n  \"attr-defined\",  # justified: y\n]"),
    ("mypy.ini", "[mypy]\ndisable_error_code = # justified: x\n    attr-defined\n    misc",
     "[mypy]\ndisable_error_code = # justified: x\n    attr-defined  # justified: y\n    misc  # justified: z"),
    # R2-02: forms real mypy applies
    ("pyproject.toml", "no_strict_optional = true", "no_strict_optional = true  # justified: migration"),
    ("mypy.ini", "no_warn_no_return = True", "no_warn_no_return = True  # justified: migration"),
    ("mypy.ini", "ignore_errors: yes", "ignore_errors: yes  # justified: vendored"),
    ("mypy.ini", "strict_optional: false", "strict_optional: false  # justified: migration"),
    ("a.py", "# mypy:no-strict-optional", "# mypy:no-strict-optional  # justified: migration"),
    ("a.py", "# mypy:allow-untyped-defs", "# mypy:allow-untyped-defs  # justified: migration"),
    ("a.py", "# mypy: strict-optional,no-warn-unused-ignores", "# mypy: strict-optional,no-warn-unused-ignores  # justified: migration"),
    # R2-03
    ("tox.ini", "[flake8]\nextend_ignore = F401", "[flake8]\nextend_ignore = F401  # justified: re-exports"),
    ("setup.cfg", "[flake8]\nignore: F401", "[flake8]\nignore: F401  # justified: re-exports"),
    # R2-04: ESLint 9 treats 0 as off, also for a later key on the line
    ("eslint.config.js", "export default [{rules: { eqeqeq: 'error', 'no-console': 0 }}];",
     "export default [{rules: { eqeqeq: 'error', 'no-console': 0 }}]; // justified: CLI output"),
    # R2-05: tsc reads nocheck case-insensitively
    ("a.ts", "// @TS-NOCHECK", "// @TS-NOCHECK  // justified: generated"),
    ("a.ts", "// @Ts-NoCheck", "// @Ts-NoCheck  // justified: generated"),
]

ROUND2_CLEAN = [
    ("mypy.ini", "[mypy]\nno_implicit_optional = True\nno_implicit_reexport = True\nstrict_optional: true\nignore_errors: no\n"),
    ("pyproject.toml", "[tool.mypy]\nno_strict_optional = false\nno_warn_no_return = false\n"),
    ("tox.ini", "[flake8]\nmax-line-length = 100\nextend_select = B\n"),
    ("eslint.config.js", "export default [{rules: { eqeqeq: 'error', 'max-params': ['error', { max: 0, min: 1 }], 'no-console': 'error' }}];\n"),
    ("a.py", "# mypy: strict-optional, warn-unused-ignores\n# mypy:disallow-untyped-defs\n"),
    ("a.ts", "// @ts-check\n"),
    ("ruff.toml", "[lint]\nignore = [\"E501\",  # justified: x\n  \"F401\",  # justified: y\n]\n"),
    ("eslint.config.js", "export default [{\n  ignores: ['dist/**', // justified: x\n    'src/**', // justified: y\n  ],\n}];\n"),
]


# Round 3 (R3-01..R3-03). (path, text with an unjustified relaxation, same text fully justified)
ROUND3_RELAXATIONS = [
    # R3-01: mypy reads inline flags with underscores too
    ("a.py", "# mypy: ignore_errors", "# mypy: ignore_errors  # justified: vendored"),
    ("a.py", "# mypy: disable_error_code=\"assignment\"", "# mypy: disable_error_code=\"assignment\"  # justified: stubs"),
    ("a.py", "# mypy: allow_untyped_defs", "# mypy: allow_untyped_defs  # justified: migration"),
    ("a.py", "# mypy: no_strict_optional", "# mypy: no_strict_optional  # justified: migration"),
    ("a.py", "# mypy: ignore_missing_imports", "# mypy: ignore_missing_imports  # justified: untyped dependency"),
    ("a.py", "# mypy: follow_imports=skip", "# mypy: follow_imports=skip  # justified: untyped dependency"),
    ("a.py", "# mypy: no_warn_unused_ignores", "# mypy: no_warn_unused_ignores  # justified: migration"),
    # R3-02: flake8 underscore spellings
    ("setup.cfg", "[flake8]\nper_file_ignores = a.py: E501", "[flake8]\nper_file_ignores = a.py: E501  # justified: long URLs"),
    ("tox.ini", "[flake8]\nextend_per_file_ignores =  # justified: tests\n    a.py: E501",
     "[flake8]\nextend_per_file_ignores =  # justified: tests\n    a.py: E501  # justified: long URLs"),
    ("tox.ini", "[flake8]\nper_file_ignores =  # justified: tests\n    a.py: E501\n    b.py: F401",
     "[flake8]\nper_file_ignores =  # justified: tests\n    a.py: E501  # justified: urls\n    b.py: F401  # justified: re-exports"),
    # R3-03: implicit_optional = True relaxes mypy
    ("pyproject.toml", "[tool.mypy]\nimplicit_optional = true", "[tool.mypy]\nimplicit_optional = true  # justified: migration"),
    ("mypy.ini", "[mypy]\nimplicit_optional = True", "[mypy]\nimplicit_optional = True  # justified: migration"),
    ("a.py", "# mypy: implicit-optional", "# mypy: implicit-optional  # justified: migration"),
    ("a.py", "# mypy: implicit_optional", "# mypy: implicit_optional  # justified: migration"),
]

# Strict forms stay clean (R3-07: no-implicit-reexport and no-implicit-optional are strict, not relaxing).
ROUND3_CLEAN = [
    ("a.py", "# mypy: no-implicit-reexport\n# mypy: no-implicit-optional\n# mypy: no_implicit_optional\n# mypy: no_implicit_reexport\n"),
    ("a.py", "# mypy: strict_optional, warn_unused_ignores\n# mypy: disallow_untyped_defs=True\n# mypy: enable_error_code=ignore-without-code\n"),
    ("mypy.ini", "[mypy]\nimplicit_optional = False\nno_implicit_optional = True\n"),
    ("tox.ini", "[flake8]\nper_file_ignores =  # justified: tests\n    a.py: E501  # justified: urls\nmax-line-length = 100\n"),
]


class LinterSuppressions(GuardsCase):
    def drop(self, path):
        """Remove a fixture so that one failing case cannot make the cases after it fail too."""
        self.repo.git("rm", "-q", "-f", "--ignore-unmatch", path)
        self.repo.commit("drop")

    def check_pair(self, path, bad, good):
        try:
            self.repo.write(path, bad + "\n")
            self.repo.commit()
            self.assertFails("guard: unjustified suppression:")
            self.repo.write(path, good + "\n")
            self.repo.commit()
            self.assertPasses()
        finally:
            self.drop(path)

    def test_each_linter_suppression_needs_a_justification(self):
        for path, bad, good in SUPPRESSION_SYNTAX:
            with self.subTest(line=bad):
                self.check_pair(path, bad, good)

    def test_each_config_relaxation_needs_a_justification(self):
        for path, bad, good in CONFIG_RELAXATIONS:
            with self.subTest(path=path, line=bad):
                self.check_pair(path, bad, good)

    def test_a_justification_must_sit_on_each_relaxing_entry_line(self):
        for path, bad, good in MULTILINE_RELAXATIONS:
            with self.subTest(path=path, text=bad):
                self.check_pair(path, bad, good)

    def test_round2_relaxations_need_a_justification(self):
        for path, bad, good in ROUND2_RELAXATIONS:
            with self.subTest(path=path, text=bad):
                self.check_pair(path, bad, good)

    def test_round2_legitimate_settings_do_not_fire(self):
        for path, text in ROUND2_CLEAN:
            with self.subTest(path=path, text=text):
                self.repo.write(path, text)
                self.repo.commit()
                try:
                    self.assertPasses()
                finally:
                    self.drop(path)

    def test_round3_relaxations_need_a_justification(self):
        for path, bad, good in ROUND3_RELAXATIONS:
            with self.subTest(path=path, text=bad):
                self.check_pair(path, bad, good)

    def test_round3_strict_forms_do_not_fire(self):
        for path, text in ROUND3_CLEAN:
            with self.subTest(path=path, text=text):
                self.repo.write(path, text)
                self.repo.commit()
                try:
                    self.assertPasses()
                finally:
                    self.drop(path)

    def test_multiline_relaxations_are_checked_in_staged_mode_from_the_index(self):
        self.repo.write("pyproject.toml", "[tool.ruff.lint]\nignore = [  # justified: long URLs\n  \"E501\",\n]\n")
        self.repo.git("add", "-A")
        self.repo.write("pyproject.toml", "[tool.ruff.lint]\nignore = [  # justified: long URLs\n  \"E501\",  # justified: long URLs\n]\n")
        self.assertFails("guard: unjustified suppression:", "--staged")  # index still has the unjustified entry
        self.repo.git("add", "-A")
        self.assertPasses("--staged")

    def test_a_justified_path_does_not_waive_suppressions_inside_it(self):
        """R1-08: the justification is read from the line, not from `path:line:` in front of it."""
        self.repo.write("justified:x/a.py", "import os  # noqa\n")
        self.repo.commit()
        self.assertFails("guard:")

    def test_a_justified_path_is_refused_in_staged_mode_too(self):
        self.repo.write("justified:x/a.py", "import os  # noqa\n")
        self.repo.git("add", "-A")
        self.assertFails("guard:", "--staged")

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
            with self.subTest(path=path, text=text):
                self.repo.write(path, text)
                self.repo.commit()
                try:
                    self.assertPasses()
                finally:
                    self.drop(path)

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


class FileSizeChecks(GuardsCase):
    """Owner decision (#15 comment 6974778901): Git LFS is not adopted, so a guard keeps big binaries out of the repo.
    Any added or changed file over 1 MB fails, and so does a *.png over 300 KB outside docs/product/wireframes/.
    Units are binary (1 MB = 1048576 bytes, 300 KB = 307200 bytes); a file exactly at the limit passes."""

    MB = 1024 * 1024
    PNG = 300 * 1024

    def test_file_at_the_1mb_limit_passes_and_one_byte_over_fails(self):
        self.repo.write_bytes("data/blob.bin", self.MB)
        self.repo.commit()
        self.assertPasses()
        self.repo.write_bytes("data/blob.bin", self.MB + 1)
        self.repo.commit()
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        for needle in ("guard: file too large:", "data/blob.bin", str(self.MB + 1), str(self.MB), "Git LFS"):
            self.assertIn(needle, out)

    def test_png_at_the_300kb_limit_passes_and_one_byte_over_fails(self):
        self.repo.write_bytes("app/src/main/res/drawable/art.png", self.PNG)
        self.repo.commit()
        self.assertPasses()
        self.repo.write_bytes("app/src/main/res/drawable/art.png", self.PNG + 1)
        self.repo.commit()
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        for needle in ("guard: file too large:", "app/src/main/res/drawable/art.png", str(self.PNG + 1), str(self.PNG), "Git LFS"):
            self.assertIn(needle, out)

    def test_png_extension_is_matched_case_insensitively(self):
        self.repo.write_bytes("art/Photo.PNG", self.PNG + 1)
        self.repo.commit()
        self.assertFails("guard: file too large: art/Photo.PNG")

    def test_large_png_inside_wireframes_passes_but_the_1mb_limit_still_applies(self):
        self.repo.write_bytes("docs/product/wireframes/tokens-sheet.png", self.MB)
        self.repo.commit()
        self.assertPasses()
        self.repo.write_bytes("docs/product/wireframes/tokens-sheet.png", self.MB + 1)
        self.repo.commit()
        self.assertFails("guard: file too large: docs/product/wireframes/tokens-sheet.png")

    def test_wireframes_exemption_is_only_for_that_directory(self):
        self.repo.write_bytes("docs/product/wireframes-old/a.png", self.PNG + 1)
        self.repo.write_bytes("docs/product/other/wireframes/b.png", self.PNG + 1)
        # Git paths are case-sensitive: other casings of the directory are other directories (R1-02).
        self.repo.write_bytes("DOCS/PRODUCT/WIREFRAMES/c.png", self.PNG + 1)
        self.repo.write_bytes("Docs/Product/Wireframes/d.png", self.PNG + 1)
        self.repo.commit()
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        for path in ("docs/product/wireframes-old/a.png", "docs/product/other/wireframes/b.png",
                     "DOCS/PRODUCT/WIREFRAMES/c.png", "Docs/Product/Wireframes/d.png"):
            self.assertIn(f"guard: file too large: {path}", out)

    def test_renaming_a_large_png_out_of_wireframes_fails_and_within_wireframes_passes(self):
        """R1-01: renames must be seen as an added file (git diff --no-renames), or the new path is never checked."""
        self.repo.write_bytes("docs/product/wireframes/w.png", 400 * 1024)
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.repo.git("mv", "docs/product/wireframes/w.png", "docs/product/wireframes/w2.png")
        self.repo.commit()
        self.assertPasses()
        os.makedirs(os.path.join(self.repo.dir, "app"))
        self.repo.git("mv", "docs/product/wireframes/w2.png", "app/w.png")
        self.repo.commit()
        self.assertFails("guard: file too large: app/w.png")

    def test_non_png_between_300kb_and_1mb_passes(self):
        self.repo.write_bytes("data/photo.jpg", 600 * 1024)
        self.repo.write_bytes("data/blob.bin", self.MB - 1)
        self.repo.commit()
        self.assertPasses()

    def test_deleted_large_files_are_ignored(self):
        self.repo.write_bytes("data/blob.bin", 2 * self.MB)
        self.repo.write_bytes("app/art.png", 2 * self.PNG)
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.repo.git("rm", "-q", "data/blob.bin", "app/art.png")
        self.repo.commit()
        self.assertPasses()

    def test_a_large_file_added_and_removed_on_the_branch_is_ignored(self):
        self.repo.write_bytes("data/blob.bin", 2 * self.MB)
        self.repo.commit()
        self.repo.git("rm", "-q", "data/blob.bin")
        self.repo.commit()
        self.assertPasses()

    def test_changing_an_already_large_file_fails(self):
        self.repo.write_bytes("data/blob.bin", 2 * self.MB)
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertPasses()  # untouched since the base
        self.repo.write_bytes("data/blob.bin", 2 * self.MB + 5)
        self.repo.commit()
        self.assertFails("guard: file too large: data/blob.bin")

    def test_every_offending_file_is_named_and_odd_paths_work(self):
        self.repo.write_bytes("data/with space.bin", self.MB + 1)
        self.repo.write_bytes("data/\u00e6\u00f8.bin", self.MB + 2)
        self.repo.write_bytes("data/small.bin", 10)
        self.repo.commit()
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        self.assertIn("data/with space.bin", out)
        self.assertIn("data/\u00e6\u00f8.bin", out)
        self.assertNotIn("small.bin", out)

    def test_it_fails_outside_ci_too(self):
        self.repo.write_bytes("data/blob.bin", self.MB + 1)
        self.repo.commit()
        self.assertFails("guard: file too large:")
        self.assertFails("guard: file too large:", CI="true")

    def test_staged_mode_checks_the_index(self):
        self.repo.write_bytes("data/blob.bin", self.MB)
        self.repo.write_bytes("art/a.png", self.PNG)
        self.repo.git("add", "-A")
        self.assertPasses("--staged")
        self.repo.write_bytes("data/blob.bin", self.MB + 1)
        self.repo.write_bytes("art/a.png", self.PNG + 1)
        self.repo.git("add", "-A")
        rc, out = self.repo.guards("--staged")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("guard: file too large: data/blob.bin", out)
        self.assertIn("guard: file too large: art/a.png", out)

    def test_a_symlink_replaced_by_a_large_file_is_a_type_change_and_fails(self):
        """R3-01: git reports file-for-symlink at the same path as status T; --diff-filter must include it (AMT, not AM)."""
        os.symlink("target", os.path.join(self.repo.dir, "data-link"))
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
        os.remove(os.path.join(self.repo.dir, "data-link"))
        self.repo.write_bytes("data-link", 2 * self.MB)
        self.repo.git("add", "-A")
        self.assertFails("guard: file too large: data-link", "--staged")
        self.repo.commit()
        self.assertFails("guard: file too large: data-link")

    def test_a_submodule_pointer_is_not_a_file_and_is_skipped(self):
        """R2-01: a gitlink (mode 160000) has no blob to size. Its commit is not in this repo (a real submodule is not fetched),
        so without the skip `git cat-file -s` fails."""
        first, second = "1" * 40, "2" * 40
        self.repo.git("update-index", "--add", "--cacheinfo", f"160000,{first},sub")
        self.assertPasses("--staged")
        self.repo.git("commit", "-q", "-m", "add pointer")  # not commit(): its `add -A` would drop the gitlink
        self.assertPasses()
        self.repo.git("update-index", "--cacheinfo", f"160000,{second},sub")  # a changed pointer too
        self.assertPasses("--staged")  # index against HEAD is a real modification (M) here (R3-02)
        self.repo.git("commit", "-q", "-m", "move pointer")
        self.assertPasses()

    def test_staged_mode_ignores_deleted_files_and_unstaged_changes(self):
        self.repo.write_bytes("data/blob.bin", 2 * self.MB)
        self.repo.commit()
        self.repo.git("rm", "-q", "data/blob.bin")
        self.assertPasses("--staged")
        self.repo.write_bytes("data/new.bin", 2 * self.MB)  # not staged
        self.assertPasses("--staged")


class ThresholdTestNames(GuardsCase):
    """Owner decision (#15): a test FUNCTION NAME containing a check keyword is not a check setting.

    Only the declared name is ignored; the rest of the line and every other line still count.
    """

    PY = "scripts/hooks/test_x.py"
    KT = "app/src/test/kotlin/XTest.kt"

    def base(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def change(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()

    def test_removing_or_renaming_a_python_test_named_threshold_passes(self):
        self.base(self.PY, "def test_boundaries_threshold(self):\n    pass\n\n\ndef test_other(self):\n    pass\n")
        self.change(self.PY, "def test_other(self):\n    pass\n")
        self.assertPasses()
        self.base(self.PY, "class T:\n    def test_threshold_env_default(self):\n        pass\n")
        self.change(self.PY, "class T:\n    def test_stage_env_default(self):\n        pass\n")
        self.assertPasses()

    def test_removing_or_renaming_a_kotlin_test_named_threshold_passes(self):
        self.base(self.KT, "class XTest {\n    fun `lowered threshold fails`() {}\n    fun testThresholdEdge() {}\n}\n")
        self.change(self.KT, "class XTest {\n    fun `new stage fails`() {}\n}\n")
        self.assertPasses()

    def test_removing_a_real_setting_in_config_files_still_fails(self):
        for rel, line in (
            ("app/build.gradle.kts", "kover { minBound(80) }"),
            ("pyproject.toml", "fail_threshold = 50"),
            ("config/detekt.yml", "  maxIssues: 0"),
            ("settings.json", '{"threshold": 50}'),
        ):
            with self.subTest(rel=rel):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_removing_or_lowering_a_threshold_in_code_still_fails(self):
        self.base("scripts/tool.py", "threshold = 50\n")
        self.change("scripts/tool.py", "\n")
        self.assertFails("guard: removed check setting:")
        self.base("scripts/tool.py", "limit = env.get('X', threshold=50)\n")
        self.change("scripts/tool.py", "limit = env.get('X', threshold=40)\n")
        self.assertFails("guard: lowered threshold:")

    def test_a_non_test_function_named_threshold_still_fails(self):
        self.base("scripts/tool.py", "def threshold_default():\n    return 50\n")
        self.change("scripts/tool.py", "def other():\n    return 50\n")
        self.assertFails("guard: removed check setting: def threshold_default")
        self.base(self.KT, "fun threshold() = 80\n")
        self.change(self.KT, "fun other() = 80\n")
        self.assertFails("guard: removed check setting: fun threshold")

    def test_threshold_lines_inside_a_test_body_still_fail(self):
        self.base(self.PY, "def test_a(self):\n    threshold = 50\n    self.assertEqual(run(), threshold)\n")
        self.change(self.PY, "def test_a(self):\n    self.assertEqual(run(), 50)\n")
        self.assertFails("guard: removed check setting: threshold = 50")
        self.base(self.PY, "def test_a(self):\n    self.assertEqual(threshold(), 50)\n")
        self.change(self.PY, "def test_a(self):\n    self.assertEqual(threshold(), 40)\n")
        self.assertFails("guard: lowered threshold:")

    def test_a_setting_on_the_same_line_as_a_test_declaration_still_fails(self):
        self.base(self.PY, "def test_a(self): threshold = 50\n")
        self.change(self.PY, "def test_b(self): pass\n")
        self.assertFails("guard: removed check setting:")
        self.base(self.KT, "fun `t`() { val threshold = 80 }\n")
        self.change(self.KT, "fun `t`() { val x = 80 }\n")
        self.assertFails("guard: removed check setting:")

    def test_a_value_on_the_same_line_as_a_keyword_test_name_still_fails(self):
        # R1-01: the name is only ignored for a bare declaration; a value on the line keeps it a check setting.
        self.base(self.PY, "def test_threshold(): return 50\n")
        self.change(self.PY, "def test_threshold(): return 40\n")
        self.assertFails("guard: lowered threshold:")
        self.base(self.PY, "def test_threshold(): return 50\n")
        self.change(self.PY, "\n")
        self.assertFails("guard: removed check setting:")
        self.base(self.PY, "def test_threshold(): return 50\n")
        self.change(self.PY, "def test_threshold(): return\n")
        self.assertFails("guard: removed check setting:")
        self.base(self.KT, "fun test_threshold() = 80\n")
        self.change(self.KT, "fun test_threshold() = 60\n")
        self.assertFails("guard: lowered threshold:")

    def test_names_are_only_ignored_in_test_files(self):
        self.base("app/src/main/kotlin/Cfg.kt", "fun `threshold`() = 80\n")
        self.change("app/src/main/kotlin/Cfg.kt", "fun `threshold`() = 60\n")
        self.assertFails("guard: lowered threshold:")
        self.base("app/build.gradle.kts", "fun test_minBound() = 80\n")
        self.change("app/build.gradle.kts", "fun test_minBound() = 60\n")
        self.assertFails("guard: lowered threshold:")
        self.base("scripts/tool.py", "def test_threshold(self):\n    pass\n")
        self.change("scripts/tool.py", "def test_other(self):\n    pass\n")
        self.assertFails("guard: removed check setting:")

    def test_a_non_numeric_same_line_value_after_a_keyword_name_still_fails(self):
        # R2-01: bare means the rest of the line is only the end of the signature.
        self.base(self.KT, "fun `maxIssues`() = ZERO\n")
        self.change(self.KT, "\n")
        self.assertFails("guard: removed check setting:")
        self.base(self.KT, "fun test_warningsAsErrors() = true\n")
        self.change(self.KT, "fun test_warningsAsErrors() = false\n")
        self.assertFails("guard: removed check setting:")
        self.base(self.PY, "def test_threshold(): return MIN_COV\n")
        self.change(self.PY, "def test_threshold(): return LOW\n")
        self.assertFails("guard: removed check setting:")

    def test_signature_ends_with_annotations_and_empty_bodies_are_still_bare(self):
        self.base(self.PY, "def test_threshold(self) -> None:\n    pass\n")
        self.change(self.PY, "def test_stage(self) -> None:\n    pass\n")
        self.assertPasses()
        self.base(self.KT, "fun `threshold`(): Unit {\n}\nfun testMaxIssues() {}\n")
        self.change(self.KT, "fun `stage`(): Unit {\n}\n")
        self.assertPasses()

    def test_only_real_test_directories_count_as_test_files(self):
        # R2-02: src/latest, src/contest and a CfgTest.kt under src/main are not test files.
        for rel in ("app/src/latest/kotlin/Cfg.kt", "app/src/contest/kotlin/Cfg.kt", "app/src/main/kotlin/CfgTest.kt"):
            with self.subTest(rel=rel):
                self.base(rel, "fun `threshold`() {}\n")
                self.change(rel, "fun `stage`() {}\n")
                self.assertFails("guard: removed check setting:")
        for rel in ("app/src/androidTest/kotlin/Cfg.kt", "app/src/testFixtures/kotlin/Cfg.kt", "app/src/integrationTest/kotlin/Cfg.kt"):
            with self.subTest(rel=rel):
                self.base(rel, "fun `threshold`() {}\n")
                self.change(rel, "fun `stage`() {}\n")
                self.assertPasses()

    def test_moving_a_file_out_of_a_test_directory_loses_the_exemption(self):
        # R2-02: classify on both the old and the new path.
        filler = "".join(f"val line{i} = {i}\n" for i in range(30))
        self.base(self.KT, filler + "fun `warningsAsErrors`() = true\n")
        os.makedirs(os.path.join(self.repo.dir, "app/src/main/kotlin"))
        self.repo.git("mv", self.KT, "app/src/main/kotlin/X.kt")
        self.repo.write("app/src/main/kotlin/X.kt", filler + "fun `warningsAsErrors`() = false\n")
        self.repo.commit()
        self.assertFails("guard: removed check setting:")

    def test_non_bare_declarations_are_keyed_on_the_full_line(self):
        # R3-01: with the name dropped from the key every `fun X() = N` collapsed to one key and hid a removal.
        self.base(self.KT, "fun `maxIssues`() = 0\nfun `threshold`() = 80\n")
        self.change(self.KT, "fun `threshold`() = 90\n")
        self.assertFails("guard: removed check setting: fun `maxIssues`() = 0")
        self.base(self.PY, "def test_minBound(): return 70\ndef test_threshold(): return 80\n")
        self.change(self.PY, "def test_threshold(): return 90\n")
        self.assertFails("guard: removed check setting: def test_minBound(): return 70")

    def test_parameters_and_return_types_make_a_declaration_non_bare(self):
        # R3-02: bare = empty parameter list (Python: only self/cls) and no or a plain identifier return type.
        for rel, old, new, needle in (
            (self.PY, "def test_threshold(x=50):\n", "def test_threshold(x=10):\n", "guard: lowered threshold:"),
            (self.PY, "def test_threshold(self, x=50):\n", "def test_threshold(self, x=10):\n", "guard: lowered threshold:"),
            (self.PY, "def test_threshold(minimum=MIN_COV):\n", "def test_threshold(minimum=LOW):\n", "guard: removed check setting:"),
            (self.PY, "def test_threshold() -> Annotated[int, 50]:\n", "def test_threshold() -> Annotated[int, 40]:\n", "guard: lowered threshold:"),
            (self.KT, "fun test_threshold(x: Int = 50) {\n", "fun test_threshold(x: Int = 10) {\n", "guard: lowered threshold:"),
            (self.KT, "fun `maxIssues`(x: Int = ZERO) {}\n", "\n", "guard: removed check setting:"),
            (self.KT, "fun `threshold`(): Limit<50> {\n", "fun `threshold`(): Limit<40> {\n", "guard: lowered threshold:"),
        ):
            with self.subTest(old=old):
                self.base(rel, old)
                self.change(rel, new)
                self.assertFails(needle)

    def test_self_cls_and_identifier_return_types_stay_bare(self):
        self.base(self.PY, "def test_threshold(cls) -> None:\n    pass\n")
        self.change(self.PY, "def test_stage(cls) -> None:\n    pass\n")
        self.assertPasses()
        self.base(self.KT, "fun `threshold`(): Unit { }\n")
        self.change(self.KT, "fun `stage`(): Unit { }\n")
        self.assertPasses()

    def test_a_test_directory_nested_below_a_source_set_is_not_a_test_file(self):
        # R3-03: the test directory must sit directly under a top-level module (app, core/<name>).
        for rel in ("app/src/main/kotlin/a/src/test/Cfg.kt", "app/src/main/kotlin/src/test/Cfg.kt"):
            with self.subTest(rel=rel):
                self.base(rel, "fun `threshold`() {}\n")
                self.change(rel, "fun `stage`() {}\n")
                self.assertFails("guard: removed check setting:")
        self.base("core/domain/src/test/kotlin/Cfg.kt", "fun `threshold`() {}\n")
        self.change("core/domain/src/test/kotlin/Cfg.kt", "fun `stage`() {}\n")
        self.assertPasses()

    def test_a_digit_in_the_test_name_does_not_hide_a_lowered_value(self):
        # R1-03: the first number on the line must not come from the name.
        self.base(self.PY, "def test_2(self): threshold = 50\n")
        self.change(self.PY, "def test_2(self): threshold = 10\n")
        self.assertFails("guard: lowered threshold:")

    def test_lowering_a_number_in_a_test_name_is_ignored_but_not_in_the_body(self):
        self.base(self.PY, "def test_threshold_50(self):\n    threshold = 50\n")
        self.change(self.PY, "def test_threshold_40(self):\n    threshold = 40\n")
        self.assertFails("guard: lowered threshold: threshold = 40")


class ThresholdProse(GuardsCase):
    """Owner decision (#15, comment 6969709604): the word `threshold` inside prose is not a check setting.

    Only an occurrence with a word on each side (`gate or threshold changes`) is prose. Identifiers, keys,
    assignments and calls still count, and so does every other keyword on the same line.
    """

    def base(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def change(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()

    def test_prose_lines_that_merely_mention_a_threshold_pass(self):
        # The three real false positives from redesign PR 4: role-prompt prose, a test pair and a rule regex.
        for rel, old in (
            (
                "agents/prompts/orchestrator.md",
                "Owner acceptance is the only alternative, and never for gate or threshold changes, which always get a delta review.\n",
            ),
            (
                "scripts/test_prompt_rules.py",
                '    ("never for gate or threshold changes, which always get a delta review", "also for gate or threshold changes"),\n',
            ),
            (
                "scripts/prompt_rules.py",
                '    r"owner acceptance is the only alternative, and never for gate or threshold changes, which always get a delta review",\n',
            ),
        ):
            with self.subTest(rel=rel):
                self.base(rel, old)
                self.change(rel, "\n")
                self.assertPasses()

    def test_real_settings_still_fail(self):
        for rel, line in (
            ("scripts/tool.py", "threshold = 50"),
            ("scripts/tool.py", "limit = env.get('X', threshold=50)"),
            ("scripts/tool.py", 'CONFIG = {"threshold": 50}'),
            ("config/detekt.yml", "  threshold: 11"),
            ("pyproject.toml", "fail_threshold = 50"),
            ("app/build.gradle.kts", "val mutationThreshold = 80"),
            ("app/build.gradle.kts", "kover { minBound(80) }"),
            ("app/src/main/kotlin/Cfg.kt", "val threshold = 80"),
        ):
            with self.subTest(rel=rel, line=line):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_a_setting_with_a_prose_comment_on_the_same_line_still_fails(self):
        self.base("scripts/tool.py", "threshold = 50  # only raise the threshold with a review\n")
        self.change("scripts/tool.py", "\n")
        self.assertFails("guard: removed check setting:")
        self.base("scripts/tool.py", "limit = 50  # the maxIssues of this threshold are fixed\n")
        self.change("scripts/tool.py", "\n")
        self.assertFails("guard: removed check setting:")

    def test_lowering_a_setting_next_to_prose_still_fails(self):
        self.base("scripts/tool.py", "threshold = 50  # a threshold with a comment\n")
        self.change("scripts/tool.py", "threshold = 40  # a threshold with a comment\n")
        self.assertFails("guard: lowered threshold:")

    def test_code_with_a_word_on_each_side_of_threshold_still_fails(self):
        # PR 135 R1-01: only prose (a markdown file, or inside a double-quoted string, and no digit) is masked.
        for rel, line in (
            ("app/build.gradle.kts", "val threshold by extra(80)"),
            ("app/build.gradle.kts", "val threshold by extra(DEFAULT)"),
            ("app/src/main/kotlin/Cfg.kt", "private val threshold get() = 80"),
            ("scripts/tool.py", "sys.exit(1) if threshold and pct < 80 else None"),
            ("scripts/tool.py", "sys.exit(1) if threshold and pct < LOW else None"),
            ("scripts/tool.py", 'x = 80  # say "a threshold b"'),
        ):
            with self.subTest(rel=rel, line=line):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_lowering_a_number_on_a_line_whose_comment_mentions_threshold_still_fails(self):
        # PR 135 R1-02.
        self.base("pyproject.toml", "fail_under = 80  # coverage threshold in percent\n")
        self.change("pyproject.toml", "fail_under = 40  # coverage threshold in percent\n")
        self.assertFails("guard: lowered threshold:")
        self.base("pyproject.toml", "fail_under = LOW  # coverage threshold in percent\n")
        self.change("pyproject.toml", "\n")
        self.assertFails("guard: removed check setting:")

    def test_a_stray_quote_or_escape_earlier_on_a_code_line_does_not_mask_threshold(self):
        # PR 135 R2-01: a char literal or an escaped quote must not turn code into "a string".
        for rel, line in (
            ("app/build.gradle.kts", "val sep = '\"'; val threshold by extra(LOW)"),
            ("app/src/main/kotlin/Cfg.kt", 'val cells = line.split("\\""); val threshold by lazy { LOW }'),
            ("scripts/tool.py", "if c == '\"' or threshold and pct < LOW: sys.exit(EXIT)"),
            ("scripts/tool.py", "if c == '\"' or threshold and pct < LOW: sys.exit(\"a b\")"),
        ):
            with self.subTest(rel=rel, line=line):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_quoted_text_that_is_not_a_bare_string_line_still_fails(self):
        # PR 135 R2-02: comments, help strings and config values are not prose lines; only a line made of nothing but
        # string literals and punctuation is.
        for rel, line in (
            ("scripts/tool.py", 'fail_under = LOW  # see "coverage threshold rules"'),
            ("scripts/tool.py", 'parser.add_argument("--min", default=LOW, help="fail below this coverage threshold value")'),
            ("config/x.json", '"mode": "fail on threshold breach",'),
            ("config/x.yml", 'level: "coverage threshold low"'),
            ("pyproject.toml", 'mode = "strict threshold check"'),
            ("scripts/x.sh", 'step "mutation threshold gate" ./gradlew pitest'),
        ):
            with self.subTest(rel=rel, line=line):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_quoted_words_that_run_code_or_sit_in_config_still_fail(self):
        # PR 135 R3-01: shell/Makefile lines of only quoted words are commands, `$` and `{}` inside a literal run code,
        # an f-string is code, and a quoted list element in a config file is a config value. Only a .py file counts.
        for rel, line in (
            ("scripts/x.sh", '"$ROOT/scripts/step" "coverage threshold check" "$ROOT/gradlew" "koverVerify"'),
            ("scripts/x.sh", '"$STEP" "mutation threshold gate" "$GRADLEW" "pitest"'),
            ("scripts/x.sh", '"$(fail_below threshold LOW)"'),
            ("Makefile", '\t"$(PITEST)" "mutation threshold gate"'),
            ("scripts/tool.py", 'f"{check threshold LOW}"'),
            ("scripts/tool.py", '"${check threshold LOW}",'),
            ("config/x.json", '["coverage threshold check"],'),
            ("app/build.gradle.kts", '"coverage threshold check",'),
        ):
            with self.subTest(rel=rel, line=line):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_only_markdown_is_prose_by_file_type(self):
        # PR 135 R3-02: .txt and .rst files are gate config or code here (allowlists, pins, CMake), not prose.
        for rel, line in (
            ("scripts/gate.txt", "fail on threshold breach"),
            ("config/licensee/x.txt", "coverage threshold check"),
            ("CMakeLists.txt", "set(CHECK threshold ON)"),
            ("app/x.rst", "val threshold by extra(LOW)"),
        ):
            with self.subTest(rel=rel, line=line):
                self.base(rel, line + "\n")
                self.change(rel, "\n")
                self.assertFails("guard: removed check setting:")

    def test_a_line_of_only_string_literals_is_prose(self):
        self.base("scripts/tool.py", '    "never for gate or threshold changes",\n    ("a", r"also for gate or threshold changes"),\n')
        self.change("scripts/tool.py", "\n")
        self.assertPasses()


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


class DiffCase(GuardsCase):
    """Diff checks compare the head with origin/main: base() sets the starting point, change() is the PR."""

    def base(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()
        self.repo.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def change(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()


class JustifiedReasonWords(GuardsCase):
    """Owner decision (#46, comment 6989538612): a `justified:` reason needs at least 3 words of letters. A word is a run of
    2 or more ASCII letters, so "-", "x", "ok", "two words" and "123 456 789" are refused. Reviewers still judge the content."""

    KT = 'app/src/main/kotlin/S.kt'

    def line(self, reason, closer=""):
        return f'@Suppress("X") fun f() {{}} // justified: {reason}{closer}\n'

    def test_reasons_with_fewer_than_three_words_fail(self):
        for reason in ["-", "x", "ok", "two words", "a b c d", "123 456 789", "!!! ??? ...", "e.g. x", "ok.", "", "does-it"]:
            with self.subTest(reason=reason):
                self.repo.write(self.KT, self.line(reason), raw=True)
                self.repo.commit()
                self.assertFails("guard: unjustified suppression:")

    def test_reasons_with_three_words_pass(self):
        for reason in ["the only hook", "generated by the compiler", "well-known JDK hook", "step 2 of rollout", "kun for generated kode", "a to the max"]:
            with self.subTest(reason=reason):
                self.repo.write(self.KT, self.line(reason), raw=True)
                self.repo.commit()
                self.assertPasses()

    def test_a_block_comment_closer_does_not_count_as_a_word(self):
        self.repo.write(self.KT, '@Suppress("X") fun f() {} /* justified: two words */\n', raw=True)
        self.repo.commit()
        self.assertFails("guard: unjustified suppression:")
        self.repo.write(self.KT, '@Suppress("X") fun f() {} /* justified: three real words */\n', raw=True)
        self.repo.commit()
        self.assertPasses()

    def test_code_and_directives_after_the_reason_are_not_counted(self):
        """R1-02: only the reason itself counts, up to a closing */ or the next comment."""
        for path, text in [
            (self.KT, '/* justified: */ @Suppress("UNCHECKED_CAST") fun f() {}'),
            ("a.js", "foo(); /* justified: x */ // eslint-disable-line no-console"),
            (self.KT, '@Suppress("X") fun f() {} /* justified: ok */ val abc = def'),
            ("a.py", "x = 1  # justified: x  # noqa: ARG001, PLR0913"),
            ("a.py", "x = 1  # noqa: ARG001  # justified: x  # more words follow here"),
        ]:
            with self.subTest(text=text):
                self.repo.write(path, text + "\n", raw=True)
                self.repo.commit()
                self.assertFails("guard: unjustified suppression:")
                self.repo.git("rm", "-q", "-f", path)
                self.repo.commit()

    def test_a_url_or_an_issue_number_inside_the_reason_does_not_cut_it(self):
        for reason in ["see http://example.invalid/a for details", "tracked in issue #46 upstream", "upstream bug, see https://x.invalid/y"]:
            with self.subTest(reason=reason):
                self.repo.write(self.KT, self.line(reason), raw=True)
                self.repo.commit()
                self.assertPasses()
        self.repo.write("a.py", "import os  # noqa: F401  # justified: re-export for callers\n", raw=True)
        self.repo.commit()
        self.assertPasses()

    def test_the_same_rule_holds_for_linter_directives(self):
        for path, bad, good in [
            ("a.py", "import os  # noqa: F401  # justified: ok", "import os  # noqa: F401  # justified: re-export for callers"),
            ("a.ts", "// @ts-ignore justified: -", "// @ts-ignore justified: upstream typing bug"),
        ]:
            with self.subTest(line=bad):
                self.repo.write(path, bad + "\n", raw=True)
                self.repo.commit()
                self.assertFails("guard: unjustified suppression:")
                self.repo.write(path, good + "\n", raw=True)
                self.repo.commit()
                self.assertPasses()

    HDR = '[lint.per-file-ignores]  # justified: the table header is covered\n'

    def test_the_same_rule_holds_for_config_relaxations(self):
        for path, bad, good in [
            ("tsconfig.json", '{ "compilerOptions": { "strict": false // justified: x\n } }',
             '{ "compilerOptions": { "strict": false // justified: migration in progress\n } }'),
            ("ruff.toml", self.HDR + '"a.py" = ["E501"]  # justified: ok\n', self.HDR + '"a.py" = ["E501"]  # justified: long URLs here\n'),
            ("tsconfig.json", '{ "extends": "@org/base" // justified: -\n }', '{ "extends": "@org/base" // justified: shared strict base\n }'),
        ]:
            with self.subTest(line=bad):
                self.repo.write(path, bad + "\n", raw=True)
                self.repo.commit()
                self.assertFails("guard: unjustified suppression:")
                self.repo.write(path, good + "\n", raw=True)
                self.repo.commit()
                self.assertPasses()
                self.repo.git("rm", "-q", "-f", path)
                self.repo.commit()

    def test_a_multi_line_table_checks_each_entry_reason(self):
        self.repo.write("ruff.toml", self.HDR + '"a.py" = ["E501"]  # justified: long URLs here\n"b.py" = ["F401"]  # justified: ok\n', raw=True)
        self.repo.commit()
        self.assertFails("b.py")


class CoverageThresholdDiffs(DiffCase):
    """#46: coverageThreshold (Jest), fail_under (coverage.py) and the per-metric values on their own lines."""

    JEST = "firebase/jest.config.cjs"
    MULTI = "module.exports = {\n  coverageThreshold: {\n    global: {\n      branches: 80,\n      lines: 90,\n    },\n  },\n};\n"

    def test_lowering_a_single_line_coverage_threshold_fails_and_raising_passes(self):
        self.base(self.JEST, "module.exports = { coverageThreshold: { global: { branches: 80 } } };\n")
        self.change(self.JEST, "module.exports = { coverageThreshold: { global: { branches: 90 } } };\n")
        self.assertPasses()
        self.change(self.JEST, "module.exports = { coverageThreshold: { global: { branches: 70 } } };\n")
        self.assertFails("guard: lowered threshold:")

    def test_removing_the_coverage_threshold_fails(self):
        self.base(self.JEST, "module.exports = { coverageThreshold: { global: { branches: 80 } } };\n")
        self.change(self.JEST, "module.exports = {};\n")
        self.assertFails("guard: removed check setting:")

    def test_lowering_a_metric_on_its_own_line_fails(self):
        for rel in (self.JEST, "firebase/vitest.config.ts", "firebase/vite.config.ts", "firebase/.nycrc.json"):
            with self.subTest(file=rel):
                self.base(rel, self.MULTI)
                self.change(rel, self.MULTI.replace("lines: 90", "lines: 70"))
                self.assertFails("guard: lowered threshold:")

    def test_raising_removing_or_reindenting_a_metric(self):
        self.base(self.JEST, self.MULTI)
        self.change(self.JEST, self.MULTI.replace("lines: 90", "lines: 95"))
        self.assertPasses()
        self.change(self.JEST, self.MULTI.replace("      lines: 90,\n", "          lines: 90,\n"))
        self.assertPasses()
        self.change(self.JEST, self.MULTI.replace("      lines: 90,\n", ""))
        self.assertFails("guard: removed check setting:")

    def test_the_same_key_in_ordinary_code_is_not_a_check_setting(self):
        self.base("app/src/main/kotlin/Cfg.kt", "val limits = mapOf(\n    lines: 90,\n)\n")
        self.change("app/src/main/kotlin/Cfg.kt", "val limits = mapOf(\n    lines: 10,\n)\n")
        self.assertPasses()

    def test_lowering_or_removing_fail_under_fails(self):
        for rel, text in [
            (".coveragerc", "[report]\nfail_under = 80\n"),
            ("pyproject.toml", "[tool.coverage.report]\nfail_under = 80\n"),
            ("pyproject.toml", "[tool.pytest.ini_options]\naddopts = \"--cov-fail-under=80\"\n"),
            ("setup.cfg", "[coverage:report]\nfail_under = 80\n"),
        ]:
            with self.subTest(file=rel, text=text):
                self.base(rel, text)
                self.change(rel, text.replace("80", "90"))
                self.assertPasses()
                self.change(rel, text.replace("80", "70"))
                self.assertFails("guard: lowered threshold:")
                self.change(rel, text.replace("fail_under = 80\n", "").replace("addopts = \"--cov-fail-under=80\"\n", ""))
                self.assertFails("guard: removed check setting:")


class EmbeddedPackageJsonConfig(GuardsCase):
    """#46: eslintConfig, prettier, jest, nyc and c8 inside package.json are not scanned by the config checks, and JSON has no comment
    to hold a justification, so the config has to live in the dedicated file."""

    def test_embedded_config_objects_fail(self):
        for key in ("eslintConfig", "prettier", "jest", "nyc", "c8"):
            for opener in ('"%s": {', '"%s":{', '  "%s" : {', '"%s":'):
                with self.subTest(key=key, opener=opener):
                    self.repo.write("firebase/package.json", '{\n  "name": "x",\n  ' + (opener % key) + '\n    "rules": {}\n  }\n}\n')
                    self.repo.commit()
                    self.assertFails("guard: embedded config:")

    def test_eslintconfig_in_any_value_form_fails(self):
        self.repo.write("package.json", '{ "eslintConfig": "./legacy.json" }\n')
        self.repo.commit()
        self.assertFails("guard: embedded config:")

    def test_dependency_entries_and_scripts_with_the_same_words_pass(self):
        self.repo.write("firebase/package.json", '{\n  "scripts": { "test": "jest --runInBand", "format": "prettier --check ." },\n'
                        '  "devDependencies": { "jest": "30.5.2", "prettier": "3.10.1", "eslint": "10.15.0", "nyc": "^17.0.0" }\n}\n')
        self.repo.commit()
        self.assertPasses()

    def test_nested_keys_with_the_same_names_pass_and_eslintignore_fails(self):
        """R1-05: only top-level keys are config. `overrides` and `peerDependenciesMeta` hold dependency data."""
        self.repo.write("firebase/package.json", '{\n  "overrides": {\n    "jest": {\n      "glob": "11.0.0"\n    }\n  },\n'
                        '  "peerDependenciesMeta": { "prettier": { "optional": true } }\n}\n')
        self.repo.commit()
        self.assertPasses()
        self.repo.write("firebase/package.json", '{ "name": "x", "eslintIgnore": ["src/**"] }\n')
        self.repo.commit()
        self.assertFails("guard: embedded config:")
        self.repo.write("firebase/package.json", '{ "name": "x", "nested": { "a": 1 }, "jest": { "preset": "ts-jest" } }\n')
        self.repo.commit()
        self.assertFails("guard: embedded config:")

    def test_a_staged_package_json_is_checked_too(self):
        self.repo.write("package.json", '{ "jest": {} }\n')
        self.repo.git("add", "package.json")
        self.assertFails("guard: embedded config:", "--staged")

    def test_a_lock_file_and_node_modules_are_not_scanned(self):
        self.repo.write("package-lock.json", '{ "packages": { "node_modules/jest": { "jest": {} } } }\n')
        self.repo.write("firebase/node_modules/x/package.json", '{ "jest": {} }\n')
        self.repo.commit()
        self.assertPasses()


class GlobalDirective(GuardsCase):
    """#46: `/* global foo */` (ESLint) switches off no-undef for the names. Only a comma list of identifiers closed on the same line
    in a JS or TS file counts, so ordinary block comments that start with the word pass."""

    def test_global_directives_need_a_justification(self):
        for text in ["/* global foo */", "/*global foo*/", "/* globals foo, bar */", "/* global foo:readonly, bar:writable */", "/* global $, _ */",
                     "/* global foo -- injected by the emulator */", "/* global foo bar */", "/* global state is kept in the store */"]:
            with self.subTest(text=text):
                for ext in ("js", "mjs", "ts", "tsx", "cjs"):
                    self.repo.write(f"firebase/a.{ext}", text + "\nexport {};\n")
                    self.repo.commit()
                    self.assertFails("guard: unjustified suppression:")
                self.repo.write("firebase/a.ts", text + " // justified: the emulator injects it\n")
                for ext in ("js", "mjs", "tsx", "cjs"):
                    self.repo.git("rm", "-q", "-f", f"firebase/a.{ext}")
                self.repo.commit()
                self.assertPasses()

    def test_ordinary_block_comments_and_other_files_pass(self):
        for rel, text in [
            ("firebase/a.ts", "/* the global state is kept in the store */\n"),
            ("firebase/a.ts", "/*\n * global foo\n */\n"),
            ("app/src/main/kotlin/A.kt", "/* global foo */\n"),
            ("firebase/a.ts", "const globalFoo = 1; // global foo\n"),
        ]:
            with self.subTest(rel=rel, text=text):
                self.repo.write(rel, text)
                self.repo.commit()
                self.assertPasses()
                self.repo.git("rm", "-q", "-f", rel)
                self.repo.commit()


class LineLengthDiffs(DiffCase):
    """#46: a raised line length weakens the style check, like a lowered threshold. A lowered or removed one is stricter and passes."""

    CASES = [
        ("ruff.toml", "line-length = %d\n"),
        ("pyproject.toml", "[tool.ruff]\nline-length = %d\n"),
        (".flake8", "[flake8]\nmax-line-length = %d\n"),
        ("tox.ini", "[flake8]\nmax_line_length = %d\n"),
        (".editorconfig", "[*.{kt,kts}]\nmax_line_length = %d\n"),
        ("firebase/.prettierrc.json", '{ "printWidth": %d }\n'),
        ("config/detekt/detekt.yml", "style:\n  MaxLineLength:\n    maxLineLength: %d\n"),
    ]

    def test_raising_a_line_length_fails(self):
        for rel, tpl in self.CASES:
            with self.subTest(file=rel):
                self.base(rel, tpl % 100)
                self.change(rel, tpl % 160)
                self.assertFails("guard: raised line length:")

    def test_lowering_keeping_or_removing_a_line_length_passes(self):
        for rel, tpl in self.CASES:
            with self.subTest(file=rel):
                self.base(rel, tpl % 120)
                self.change(rel, tpl % 100)
                self.assertPasses()
                self.change(rel, "# nothing here\n")
                self.assertPasses()

    def test_any_other_edit_of_the_setting_line_does_not_hide_a_raise(self):
        """R1-01: the setting is keyed by its name, not by the whole line."""
        for rel, old, new in [
            ("ruff.toml", "line-length = 100\n", "line-length = 160  # wide tables\n"),
            ("ruff.toml", "line-length = 100\n", "line-length=160\n"),
            ("firebase/.prettierrc.json", '{ "printWidth": 100 }\n', '{ "printWidth": 160, "semi": true }\n'),
            ("firebase/.prettierrc.json", '{ "semi": true, "printWidth": 100 }\n', '{ "printWidth": 160, "semi": true }\n'),
            (".editorconfig", "[*.kt]\nmax_line_length = 100\n", "[*.kt]\nmax_line_length = off\n"),
        ]:
            with self.subTest(file=rel, new=new):
                self.base(rel, old)
                self.change(rel, new)
                self.assertFails("guard: raised line length:")

    def test_other_edits_of_the_setting_line_that_do_not_raise_pass(self):
        for rel, old, new in [
            ("ruff.toml", "line-length = 100\n", "line-length = 90  # tighter\n"),
            ("firebase/.prettierrc.json", '{ "printWidth": 100 }\n', '{ "printWidth": 100, "semi": true }\n'),
            (".editorconfig", "[*.kt]\nmax_line_length = off\n", "[*.kt]\nmax_line_length = 120\n"),
        ]:
            with self.subTest(file=rel, new=new):
                self.base(rel, old)
                self.change(rel, new)
                self.assertPasses()

    def test_the_words_outside_the_style_config_files_are_not_a_setting(self):
        self.base("app/src/main/kotlin/L.kt", "val maxLineLength = 100\n")
        self.change("app/src/main/kotlin/L.kt", "val maxLineLength = 160\n")
        self.assertPasses()
        self.base("scripts/tool.py", "line_length = 100\n")
        self.change("scripts/tool.py", "line_length = 160\n")
        self.assertPasses()


class WeakerPresets(DiffCase):
    """#46: a lint preset swapped for a weaker one (strictTypeChecked, strict, recommendedTypeChecked, recommended, in that order)."""

    FLAT = "firebase/eslint.config.mjs"

    def flat(self, *presets):
        return "export default defineConfig({\n    extends: [" + ", ".join(presets) + "],\n});\n"

    def test_swapping_a_flat_config_preset_for_a_weaker_one_fails(self):
        order = ["strictTypeChecked", "strict", "recommendedTypeChecked", "recommended"]
        for i, strong in enumerate(order):
            for weak in order[i + 1:]:
                with self.subTest(strong=strong, weak=weak):
                    self.base(self.FLAT, self.flat("eslint.configs.recommended", f"tseslint.configs.{strong}"))
                    self.change(self.FLAT, self.flat("eslint.configs.recommended", f"tseslint.configs.{weak}"))
                    self.assertFails("guard: weaker lint preset:")

    def test_removing_the_preset_fails(self):
        self.base(self.FLAT, self.flat("eslint.configs.recommended", "tseslint.configs.strictTypeChecked"))
        self.change(self.FLAT, self.flat("eslint.configs.recommended"))
        self.assertFails("guard: weaker lint preset:")

    def test_eslintrc_plugin_presets_count_too(self):
        self.base(".eslintrc.json", '{ "extends": ["plugin:@typescript-eslint/strict-type-checked"] }\n')
        self.change(".eslintrc.json", '{ "extends": ["plugin:@typescript-eslint/recommended"] }\n')
        self.assertFails("guard: weaker lint preset:")

    def test_stronger_equal_moved_and_unrelated_presets_pass(self):
        self.base(self.FLAT, self.flat("eslint.configs.recommended", "tseslint.configs.recommended"))
        self.change(self.FLAT, self.flat("eslint.configs.recommended", "tseslint.configs.strictTypeChecked"))
        self.assertPasses()
        self.change(self.FLAT, self.flat("tseslint.configs.strictTypeChecked", "eslint.configs.recommended"))  # reordered
        self.assertPasses()
        self.change(self.FLAT, self.flat("eslint.configs.recommended", "tseslint.configs.strictTypeChecked", "tseslint.configs.stylistic"))
        self.assertPasses()
        self.change(self.FLAT, self.flat("eslint.configs.recommended", "tseslint.configs.strictTypeChecked").replace("    extends", "        extends"))
        self.assertPasses()

    def test_a_weaker_preset_of_another_plugin_does_not_hide_behind_a_stronger_one(self):
        self.base(self.FLAT, self.flat("tseslint.configs.strictTypeChecked", "react.configs.strict"))
        self.change(self.FLAT, self.flat("tseslint.configs.strictTypeChecked", "react.configs.recommended"))
        self.assertFails("guard: weaker lint preset:")

    def test_the_same_names_outside_eslint_config_files_pass(self):
        self.base("app/src/main/kotlin/P.kt", "val p = tseslint.configs.strictTypeChecked\n")
        self.change("app/src/main/kotlin/P.kt", "val p = tseslint.configs.recommended\n")
        self.assertPasses()


class NarrowedLists(DiffCase):
    """#46: ruff select, tsconfig include and tsconfig exclude, compared with the base. Arrays may span lines."""

    def test_dropping_a_ruff_select_item_fails(self):
        for rel, text in [
            ("ruff.toml", '[lint]\nselect = ["E", "F", "W"]\n'),
            ("ruff.toml", '[lint]\nselect = [\n    "E",\n    "F",\n    "W",\n]\n'),
            ("ruff.toml", "[lint]\nselect = ['E', 'F', 'W']\n"),
            ("ruff.toml", 'lint.select = ["E", "F", "W"]\n'),
            ("ruff.toml", '[lint]\nextend-select = ["E", "F", "W"]\n'),
            ("pyproject.toml", '[tool.ruff.lint]\nselect = ["E", "F", "W"]\n'),
        ]:
            with self.subTest(file=rel, text=text):
                self.base(rel, text)
                self.change(rel, text.replace('"W"', '"E"').replace("'W'", "'E'").replace('    "W",\n', ""))
                self.assertFails("guard: narrowed ruff select:")

    def test_adding_reordering_or_widening_a_ruff_select_passes(self):
        text = '[lint]\nselect = ["E", "F", "W"]\n'
        self.base("ruff.toml", text)
        self.change("ruff.toml", '[lint]\nselect = ["E", "F", "W", "B"]\n')
        self.assertPasses()
        self.change("ruff.toml", '[lint]\nselect = ["W", "F", "E"]\n')
        self.assertPasses()
        self.change("ruff.toml", '[lint]\nselect = ["ALL"]\n')
        self.assertPasses()
        self.change("ruff.toml", '[lint]\nselect = [\n    "E",\n    "F",\n    "W",\n]\n')
        self.assertPasses()

    def test_a_new_ruff_config_and_other_arrays_pass(self):
        self.base("notes.txt", "hello\n")
        self.change("ruff.toml", '[lint]\nselect = ["E"]\n')
        self.assertPasses()
        self.base("pyproject.toml", '[tool.other]\nitems = ["a", "b"]\n[tool.ruff.lint]\nselect = ["E"]\n')
        self.change("pyproject.toml", '[tool.other]\nitems = ["a"]\n[tool.ruff.lint]\nselect = ["E"]\n')
        self.assertPasses()

    def test_comments_do_not_hide_a_removed_preset_or_include_entry(self):
        """R1-04."""
        base = "export default defineConfig({\n    extends: [tseslint.configs.strictTypeChecked],\n});\n"
        for new in ["    extends: [tseslint.configs.recommended], // was tseslint.configs.strictTypeChecked\n",
                    "    extends: [tseslint.configs.recommended], /* tseslint.configs.strictTypeChecked */\n"]:
            with self.subTest(new=new):
                self.base("firebase/eslint.config.mjs", base)
                self.change("firebase/eslint.config.mjs", base.replace("    extends: [tseslint.configs.strictTypeChecked],\n", new))
                self.assertFails("guard: weaker lint preset:")
        for new in ['{ "include": ["src/**/*.ts" /* , "test/**/*.ts" */] }\n',
                    '{\n  "include": [\n    "src/**/*.ts",\n    /*\n    "test/**/*.ts"\n    */\n  ]\n}\n']:
            with self.subTest(new=new):
                self.base("firebase/tsconfig.json", '{ "include": ["src/**/*.ts", "test/**/*.ts"] }\n')
                self.change("firebase/tsconfig.json", new)
                self.assertFails("guard: narrowed tsconfig include:")

    def test_comments_that_keep_every_item_pass(self):
        self.base("firebase/tsconfig.json", '{ "include": ["src/**/*.ts", "test/**/*.ts"] }\n')
        self.change("firebase/tsconfig.json", '{ "include": ["src/**/*.ts", /* tests */ "test/**/*.ts"] } // note\n')
        self.assertPasses()

    def test_renaming_or_moving_a_config_does_not_hide_a_dropped_item(self):
        """R1-03: a rename or a move shows as a deleted file plus a new one."""
        text = '[lint]\nselect = ["E", "F", "W"]\n'
        less = '[lint]\nselect = ["E", "F"]\n'
        self.base("ruff.toml", text)
        self.repo.git("mv", "ruff.toml", ".ruff.toml")
        self.change(".ruff.toml", less)
        self.assertFails("guard: narrowed ruff select:")
        self.repo.git("rm", "-q", "-f", ".ruff.toml")
        self.base("ruff.toml", text)
        self.repo.git("rm", "-q", "-f", "ruff.toml")
        self.change("pyproject.toml", '[tool.ruff.lint]\nselect = ["E", "F"]\n')
        self.assertFails("guard: narrowed ruff select:")
        self.base("firebase/tsconfig.json", '{ "include": ["src/**/*.ts", "test/**/*.ts"] }\n')
        self.repo.git("mv", "firebase/tsconfig.json", "firebase/tsconfig.app.json")
        self.change("firebase/tsconfig.app.json", '{ "include": ["src/**/*.ts"] }\n')
        self.assertFails("guard: narrowed tsconfig include:")

    def test_renaming_or_moving_a_config_that_keeps_every_item_passes(self):
        text = '[lint]\nselect = ["E", "F", "W"]\n'
        self.base("ruff.toml", text)
        self.repo.git("mv", "ruff.toml", ".ruff.toml")
        self.change(".ruff.toml", text + 'extend-select = ["B"]\n')
        self.assertPasses()
        self.repo.git("rm", "-q", "-f", ".ruff.toml")
        self.base("ruff.toml", text)
        self.repo.git("rm", "-q", "-f", "ruff.toml")
        self.change("pyproject.toml", '[tool.ruff.lint]\nselect = ["E", "F", "W", "B"]\n')
        self.assertPasses()

    def test_dropping_a_tsconfig_include_entry_fails(self):
        for rel, text in [
            ("firebase/tsconfig.json", '{ "include": ["src/**/*.ts", "test/**/*.ts"] }\n'),
            ("firebase/tsconfig.json", '{\n  "include": [\n    "src/**/*.ts",\n    "test/**/*.ts"\n  ]\n}\n'),
            ("tsconfig.app.json", '{ "include": ["src/**/*.ts", "test/**/*.ts"] }\n'),
        ]:
            with self.subTest(file=rel, text=text):
                self.base(rel, text)
                self.change(rel, text.replace('"test/**/*.ts"', '"src/other.ts"').replace(', "src/other.ts"', "").replace(',\n    "src/other.ts"', ""))
                self.assertFails("guard: narrowed tsconfig include:")

    def test_adding_an_include_entry_or_dropping_an_exclude_entry_passes(self):
        self.base("firebase/tsconfig.json", '{ "include": ["src/**/*.ts"], "exclude": ["node_modules", "dist"] }\n')
        self.change("firebase/tsconfig.json", '{ "include": ["src/**/*.ts", "test/**/*.ts"], "exclude": ["node_modules"] }\n')
        self.assertPasses()

    def test_adding_a_tsconfig_exclude_entry_needs_a_justification(self):
        self.base("firebase/tsconfig.json", '{ "exclude": ["node_modules"] }\n')
        self.change("firebase/tsconfig.json", '{ "exclude": ["node_modules", "test"] }\n')
        self.assertFails("guard: widened tsconfig exclude:")
        self.change("firebase/tsconfig.json", '{ "exclude": ["node_modules", "test"] } // justified: tests have their own project\n')
        self.assertPasses()
        self.change("firebase/tsconfig.json", '{ "exclude": ["node_modules", "dist"] } // justified: ok\n'.replace("ok", "-"))
        self.assertFails("guard: widened tsconfig exclude:")

    def test_a_multi_line_exclude_needs_the_justification_on_the_added_entry(self):
        nm = '"node_modules", // justified: dependencies are not ours'
        self.base("firebase/tsconfig.json", '{\n  "exclude": [\n    ' + nm + '\n  ]\n}\n')
        self.change("firebase/tsconfig.json", '{\n  "exclude": [\n    ' + nm + '\n    "dist" // justified: build output is generated\n  ]\n}\n')
        self.assertPasses()
        self.change("firebase/tsconfig.json", '{\n  "exclude": [\n    ' + nm + '\n    "dist" // justified: -\n  ]\n}\n')
        self.assertFails("guard: widened tsconfig exclude:")


class SkipLibCheck(GuardsCase):
    """#46: skipLibCheck hides errors in declaration files; it does not touch our own code, so a short justification is enough."""

    def test_skip_lib_check_true_needs_a_justification(self):
        for text in ['{ "compilerOptions": { "skipLibCheck": true } }', '{ "compilerOptions": { "skipLibCheck":true } }',
                     '{ "compilerOptions": {\n "skipDefaultLibCheck": true,\n "skipLibCheck": true\n } }']:
            with self.subTest(text=text):
                self.repo.write("firebase/tsconfig.json", text + "\n")
                self.repo.commit()
                self.assertFails("guard: unjustified suppression:")
        self.repo.write("firebase/tsconfig.json", '{ "compilerOptions": {\n "skipLibCheck": true // justified: a vendored typing is broken\n } }\n')
        self.repo.commit()
        self.assertPasses()

    def test_skip_lib_check_false_and_other_files_pass(self):
        self.repo.write("firebase/tsconfig.json", '{ "compilerOptions": { "skipLibCheck": false } }\n')
        self.repo.write("firebase/notes.json", '{ "skipLibCheck": true }\n')
        self.repo.commit()
        self.assertPasses()


class Exclusions(GuardsCase):
    def test_prose_and_docs_may_mention_patterns(self):
        self.repo.write("docs/notes.md", "Use @Ignore never; baseline.xml is forbidden; Suppress(\"x\")\n")
        self.repo.write("handoff/h.md", "@Disabled\n")
        self.repo.commit()
        self.assertPasses()


if __name__ == "__main__":
    unittest.main()
