"""Tests for scripts/guards.sh, run against throwaway git repos. Run: python3 -I -m unittest discover -s scripts/hooks

Every guard has a case that must fail and a neighbouring case that must pass, so a guard that
stops firing (or starts firing on clean code) breaks this suite.
"""

import os
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
    ("tsconfig.json", "{\n  \"compilerOptions\": {\"strict\": true, \"noImplicitAny\": true, \"skipLibCheck\": true}\n}\n"),
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
