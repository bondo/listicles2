"""Tests for the command-line flag check in scripts/guards.sh (issue 45). Run: python3 -I -m unittest discover -s scripts/hooks

Relaxations passed as flags on a tool invocation line (ruff, mypy, tsc, ESLint, Prettier, shellcheck) in shell scripts, git hooks,
CI workflows and package.json need `justified: <reason>` on the same logical line (a backslash continuation is one line).
Every tool has lines that must fail and neighbouring strict or ordinary lines that must pass.
"""

import unittest

import test_guards_sh as base

MARK = "guard: unjustified CLI flag"

# (tool, relaxing invocations, strict or ordinary invocations)
CASES = [
    ("ruff",
     ["ruff check --ignore E501 scripts", "ruff check --extend-ignore=E501 scripts", "ruff check --per-file-ignores 'a.py:E501' .",
      "ruff check --exclude build .", "ruff check --extend-exclude=gen .", "ruff check --exit-zero .", "ruff check --isolated ."],
     ["ruff check --config ruff.toml --no-cache --output-format concise scripts", "ruff format --check ."]),
    ("mypy",
     ["mypy --ignore-missing-imports scripts", "mypy --allow-untyped-defs scripts", "mypy --allow-redefinition scripts",
      "mypy --no-strict-optional scripts", "mypy --no-check-untyped-defs scripts", "mypy --no-warn-unused-ignores scripts",
      "mypy --disable-error-code=arg-type scripts", "mypy --follow-imports=skip scripts", "mypy --follow-imports silent scripts",
      "mypy --implicit-optional scripts", "mypy --exclude build scripts"],
     ["mypy --config-file mypy.ini scripts", "mypy --strict scripts", "mypy --no-implicit-reexport scripts", "mypy --disallow-any-generics scripts",
      "mypy --follow-imports=normal scripts", "mypy --warn-unused-ignores scripts"]),
    ("tsc",
     ["tsc --noCheck", "npx tsc --noEmit --noCheck -p tsconfig.json", "tsc --skipLibCheck -p .", "tsc --strict false", "tsc --noImplicitAny=false",
      "tsc --allowUnreachableCode", "tsc --strictNullChecks false"],
     ["tsc --noEmit -p tsconfig.json", "npx tsc --noEmit --strict", "tsc --strict true -p .", "tsc --noUnusedLocals"]),
    ("eslint",
     ["eslint --quiet .", "eslint --rule 'no-console: off' .", "eslint --rule \"no-console: [0]\" .", "eslint --rule 'eqeqeq: warn' .",
      "eslint --max-warnings -1 .", "eslint --max-warnings 5 .", "eslint --ignore-pattern 'gen/**' .", "eslint --ignore-path .gitignore .",
      "eslint --no-eslintrc .", "eslint --no-config-lookup ."],
     ["eslint --max-warnings 0 .", "eslint --rule 'no-console: error' .", "eslint --rule 'eqeqeq: [2, always]' .",
      "eslint --rule 'max-depth: [error, 1]' --max-warnings 0 .", "eslint --report-unused-disable-directives .",
      "eslint --no-inline-config ."]),
    ("prettier",
     ["prettier --check --ignore-path .gitignore .", "prettier --check --require-pragma .", "prettier --check --no-error-on-unmatched-pattern .",
      "prettier --check --ignore-unknown .", "prettier --check -u ."],
     ["prettier --check .", "prettier --check --config .prettierrc.json .", "prettier --write ."]),
    ("shellcheck",
     ["shellcheck -e SC2086 a.sh", "shellcheck -eSC2086 a.sh", "shellcheck --exclude=SC2086 a.sh", "shellcheck --exclude SC2086 a.sh",
      "shellcheck -S error a.sh", "shellcheck --severity=error a.sh", "shellcheck -i SC2086 a.sh", "shellcheck --include=SC2086 a.sh"],
     ["shellcheck -S warning -x -- a.sh", "shellcheck --severity=style a.sh", "shellcheck -x a.sh", "shellcheck -o all a.sh",
      "bash -e a.sh && shellcheck a.sh"]),
]


class CliFlagCase(base.GuardsCase):
    def put(self, rel, line):
        self.repo.write(rel, line + "\n")
        self.repo.commit()


class PerToolTests(CliFlagCase):
    def test_relaxing_flags_fail_and_strict_forms_pass(self):
        for tool, bad, good in CASES:
            for line in bad:
                with self.subTest(tool=tool, line=line):
                    self.put("scripts/lint.sh", line)
                    self.assertFails(MARK + ": scripts/lint.sh:1:")
            for line in good:
                with self.subTest(tool=tool, ok=line):
                    self.put("scripts/lint.sh", line)
                    self.assertPasses()

    def test_same_line_justification_passes(self):
        for tool, bad, _ in CASES:
            with self.subTest(tool=tool):
                self.put("scripts/lint.sh", bad[0] + " # justified: generated code, owner approved in #15")
                self.assertPasses()

    def test_empty_or_wrong_line_justification_fails(self):
        self.put("scripts/lint.sh", "ruff check --ignore E501 scripts # justified:")
        self.assertFails(MARK)
        self.repo.write("scripts/lint.sh", "# justified: generated code\nruff check --ignore E501 scripts\n")
        self.repo.commit()
        self.assertFails(MARK + ": scripts/lint.sh:2:")

    def test_justification_in_the_path_does_not_waive(self):
        self.put("scripts/justified: x.sh", "ruff check --ignore E501 scripts")
        rc, out = self.repo.guards()
        self.assertNotEqual(rc, 0, out)
        self.assertIn(MARK, out)


class WhereTheInvocationLivesTests(CliFlagCase):
    def test_all_covered_file_kinds_fail(self):
        files = {
            "scripts/verify.sh": "step lint ruff check --ignore E501 scripts",
            ".githooks/pre-commit": "ruff check --ignore E501 scripts",
            ".github/workflows/ci.yml": "        run: ruff check --extend-ignore=E501 scripts",
            "firebase/package.json": '    "lint": "eslint --quiet ."',
            "package.json": '    "typecheck": "tsc --noEmit --noCheck"',
        }
        for path, line in files.items():
            with self.subTest(path=path):
                self.put(path, line)
                self.assertFails(MARK + ": " + path + ":1:")
                self.repo.git("rm", "-q", path)
                self.repo.commit()

    def test_package_json_strict_scripts_and_npm_passthrough(self):
        self.put("firebase/package.json", '    "lint": "eslint --max-warnings 0 .",\n    "format:check": "prettier --check ."')
        self.assertPasses()
        self.put("scripts/lint.sh", "npm run lint -- --quiet")
        self.assertFails(MARK + ": scripts/lint.sh:1:")
        self.put("scripts/lint.sh", "npm run typecheck -- --noCheck")
        self.assertFails(MARK)
        self.put("scripts/lint.sh", "npm run lint --silent")
        self.assertPasses()

    def test_prose_markdown_and_full_line_comments_are_not_scanned(self):
        self.repo.write("docs/NOTES.md", "never run `ruff check --ignore E501`\n")
        self.repo.write("scripts/lint.sh", "# ruff check --ignore E501 is not allowed\necho ok\n")
        self.repo.commit()
        self.assertPasses()

    def test_a_tool_name_without_a_command_position_does_not_match(self):
        self.put("scripts/lint.sh", "grep -e foo a.sh # shellchecker -e\npip install ruff --ignore-installed\necho 'ruffian --ignore'")
        self.assertPasses()


class LogicalLineTests(CliFlagCase):
    def test_backslash_continuation_is_one_line(self):
        self.put("scripts/lint.sh", "ruff check \\\n  --ignore E501 \\\n  scripts")
        self.assertFails(MARK + ": scripts/lint.sh:1:")
        self.put("scripts/lint.sh", "ruff check \\\n  --ignore E501 \\\n  scripts # justified: generated code")
        self.assertPasses()
        self.put("scripts/lint.sh", "ruff check \\\n  --config ruff.toml \\\n  scripts")
        self.assertPasses()

    def test_flags_of_one_command_do_not_leak_into_the_next(self):
        self.put("scripts/lint.sh", "shellcheck a.sh && bash -e b.sh; mypy --strict x | grep -e y")
        self.assertPasses()
        self.put("scripts/lint.sh", "bash -e b.sh && shellcheck -e SC2086 a.sh")
        self.assertFails(MARK)
        self.put("scripts/lint.sh", "cd firebase && npx eslint --quiet . || true")
        self.assertFails(MARK)

    def test_one_justification_covers_the_logical_line(self):
        self.put("scripts/lint.sh", "ruff check scripts && mypy --ignore-missing-imports scripts # justified: stubs missing upstream")
        self.assertPasses()


class StagedModeTests(CliFlagCase):
    def test_staged_scan_reads_the_index(self):
        self.repo.write("scripts/lint.sh", "ruff check --ignore E501 scripts\n")
        self.repo.git("add", "scripts/lint.sh")
        self.assertFails(MARK + ": scripts/lint.sh:1:", "--staged")
        self.repo.write("scripts/lint.sh", "ruff check scripts\n")  # worktree is clean, the index is not
        self.assertFails(MARK, "--staged")
        self.repo.git("add", "scripts/lint.sh")
        self.assertPasses("--staged")


class ConfigIndirectionTests(CliFlagCase):
    """R1-01: config handed over on the command line. An inline override or a path the 2b config scan does not cover is a relaxation."""

    BAD = [
        "ruff check --config \"lint.ignore = ['F401']\" scripts", "ruff check --config 'lint.ignore=[\"F401\"]' scripts",
        "ruff check --config ci.toml scripts",
        "mypy --config-file ci.ini scripts", "mypy --config-file=ci.ini scripts", "eslint -c ci.js .", "eslint --config relaxed.mjs .",
        "prettier --check --config ci.json .", "tsc -p ci.json", "tsc --project ci.json", "npm run lint -- --config relaxed.mjs",
    ]
    GOOD = [
        "ruff check --config ruff.toml scripts", "ruff check --config=ruff.toml scripts", "ruff check --config pyproject.toml scripts",
        "ruff check --config sub/.ruff.toml scripts", "mypy --config-file mypy.ini scripts", "mypy --config-file setup.cfg scripts",
        "eslint -c eslint.config.mjs .", "eslint --config .eslintrc.json .", "prettier --check --config .prettierrc.json .",
        "prettier --check --config prettier.config.mjs .", "tsc -p tsconfig.json", "tsc -p tsconfig.build.json", "tsc -p .",
        "tsc --project firebase/tsconfig.json", "npm run lint -- --config eslint.config.mjs",
    ]

    def test_inline_overrides_and_unscanned_config_files_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_config_files_the_config_scan_covers_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_config_paths_inside_package_json_strings(self):
        """The value ends at the closing quote and comma of the JSON string, not at whitespace."""
        good = ['    "typecheck": "tsc --noEmit -p tsconfig.json",', '    "lint": "eslint -c eslint.config.mjs",',
                '    "lint": "ruff check --config ruff.toml"', '    "fmt": "prettier --check --config .prettierrc.json ."']
        bad = ['    "typecheck": "tsc --noEmit -p ci.json",', '    "lint": "eslint -c relaxed.mjs",', '    "lint": "ruff check --config ci.toml"']
        for line in good:
            with self.subTest(line=line):
                self.put("firebase/package.json", line)
                self.assertPasses()
        for line in bad:
            with self.subTest(line=line):
                self.put("firebase/package.json", line)
                self.assertFails(MARK + ": firebase/package.json:1:")

    def test_justification_waives_a_config_path(self):
        self.put("scripts/lint.sh", "ruff check --config ci.toml scripts # justified: ci.toml is the generated-code profile, owner approved")
        self.assertPasses()


class QuotingAndEnvironmentTests(CliFlagCase):
    """R1-02: a quote before the flag or before false, combined short options and SHELLCHECK_OPTS hide a relaxation."""

    BAD = [
        'ruff check "--ignore" E501 .', "ruff check '--ignore=E501' .", "prettier --check '-u' .", "tsc --strict 'false'",
        'tsc --strict "false"', "shellcheck -xe SC2086 a.sh", "shellcheck -Ce SC2086 a.sh", "shellcheck -xS error a.sh", "shellcheck -xi SC2086 a.sh",
        'SHELLCHECK_OPTS="-e SC2086" shellcheck a.sh', "export SHELLCHECK_OPTS='-e SC2086'", "SHELLCHECK_OPTS=-e shellcheck a.sh",
        'echo " #"; ruff check --ignore E501 .',
    ]
    GOOD = [
        'ruff check "--config" ruff.toml .', "tsc --strict 'true'", "shellcheck -x a.sh", "shellcheck -xS warning a.sh",
        'SHELLCHECK_OPTS="-S warning" shellcheck a.sh',
        "export SHELLCHECK_OPTS=-x", "shellcheck -Calways a.sh",
    ]

    def test_hidden_relaxations_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_neighbouring_strict_forms_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()


class MoreFlagsTests(CliFlagCase):
    """R1-03: relaxations the first flag lists missed."""

    BAD = [
        "mypy --strict --no-strict-bytes scripts", "mypy --no-strict-equality-for-none scripts", "mypy --no-extra-checks scripts",
        "mypy --untyped-calls-exclude=pkg scripts", "eslint --report-unused-disable-directives-severity off .",
        "eslint --report-unused-disable-directives-severity=0 .", "eslint --no-error-on-unmatched-pattern .", "eslint --pass-on-no-patterns .",
    ]
    GOOD = ["eslint --report-unused-disable-directives-severity error .", "eslint --report-unused-disable-directives-severity=2 .",
            "mypy --extra-checks scripts"]

    def test_listed_relaxations_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_strict_neighbours_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()


class FalsePositiveTests(CliFlagCase):
    """R1-04: ordinary and strict lines must not need a justification."""

    GOOD = [
        "npm ci --quiet", "npm install --quiet --no-audit", 'npx --quiet firebase emulators:exec "npm test"', "npm run lint --quiet",
        "eslint --rule 'complexity: [error, {max: 1}]' .", "eslint --rule 'max-depth: [error, 1]' .",
        "eslint --rule '{\"a\":[\"error\",{\"max\":1}]}' .", "grep -i shellcheck a.log",
        "ruff check . # --ignore E501 was dropped", "shellcheck a.sh # -e SC2086 was dropped",
    ]
    BAD = [
        "eslint --rule '{\"a\":\"error\",\"b\":\"off\"}' .", "npx --quiet eslint --quiet .", "npm exec -- eslint --quiet .",
        "ruff check --ignore E501 . # was dropped",
    ]

    def test_clean_lines_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_relaxations_next_to_comments_and_wrappers_still_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")


class ShellcheckOptsFormsTests(CliFlagCase):
    """R2-02: SHELLCHECK_OPTS as a workflow env: key or with += is the same relaxation as SHELLCHECK_OPTS=."""

    def test_yaml_env_key_and_append_forms_fail(self):
        yaml = ['        SHELLCHECK_OPTS: "-e SC2086"', "      SHELLCHECK_OPTS: -e SC2086", "      SHELLCHECK_OPTS: '--exclude=SC2086'"]
        for line in yaml:
            with self.subTest(line=line):
                self.put(".github/workflows/ci.yml", line)
                self.assertFails(MARK + ": .github/workflows/ci.yml:1:")
        for line in ['SHELLCHECK_OPTS+=" -e SC2086"', 'export SHELLCHECK_OPTS+=" -S error"']:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_strict_env_forms_pass(self):
        for line in ["      SHELLCHECK_OPTS: -S warning", '        SHELLCHECK_OPTS: "-x"']:
            with self.subTest(line=line):
                self.put(".github/workflows/ci.yml", line)
                self.assertPasses()
        self.put("scripts/lint.sh", 'SHELLCHECK_OPTS+=" -x"')
        self.assertPasses()

    def test_justification_waives_the_env_form(self):
        self.put(".github/workflows/ci.yml", '        SHELLCHECK_OPTS: "-e SC2086" # justified: generated file, owner approved')
        self.assertPasses()


class ConfigPathReachTests(CliFlagCase):
    """R2-03: a config path the 2b scan cannot read (absolute, variable, outside the tree) and tsc forms that skip tsconfig."""

    BAD = [
        'ruff check --config "$tmp/ruff.toml" .', "ruff check --config /tmp/x/pyproject.toml .", "ruff check --config ~/ruff.toml .",
        "ruff check --config ../ruff.toml .", "mypy --config-file=$CFG scripts", 'tsc -p "$CFG"', "tsc -p $CFG", "tsc --project `mktemp`",
        "tsc -b ci.json", "tsc --build ci.json", "tsc --noEmit src/index.ts", "tsc index.ts", "npx tsc --noEmit lib/a.mts",
    ]
    GOOD = [
        "ruff check --config scripts/ruff.toml .", "tsc -p .", "tsc -b tsconfig.json", "tsc --build", "tsc -b --verbose", "tsc --noEmit -p tsconfig.json",
        "tsc --version", "npm run build -- src/index.ts",
    ]

    def test_unreachable_config_and_tsc_forms_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_reachable_config_and_ordinary_tsc_forms_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()


class RoundThreeTests(CliFlagCase):
    """R3-01 to R3-05: ESLint suppressions, ruff short and extra flags, abbreviated options, tsc -b arguments, shellcheck --rcfile."""

    BAD = [
        "eslint --suppress-all .", "eslint --suppress-rule no-console .", "eslint --suppressions-location x.json .",
        "eslint --pass-on-unpruned-suppressions .", "npm run lint -- --suppress-all",
        "ruff check -e .", "ruff check -ne .", "ruff check --select E .", "ruff check --select=E,F .", "ruff check --fix-only .",
        "mypy --ignore-missing c.py", "mypy --disable-error no-untyped-def b.py", "mypy @args.txt b.py", 'mypy --config-file "" b.py',
        "mypy --config-f ci.ini b.py", "mypy --config ci.ini b.py", "mypy --follow-imp=skip b.py",
        "tsc -b --verbose ci.json", "tsc --build --force ci.json", "tsc -b tsconfig.json ci.json",
        "shellcheck -S warning --rcfile ci.rc a.sh", "shellcheck --rcfile=.shellcheckrc a.sh", "shellcheck --rc ci.rc a.sh",
        "shellcheck --exc=SC2086 a.sh", "shellcheck --incl=SC2086 a.sh",
        "shellcheck --sev=error a.sh",
    ]
    GOOD = [
        "eslint --prune-suppressions .", "ruff check --extend-select E .", "mypy --config-file mypy.ini b.py", "mypy --config mypy.ini b.py",
        "mypy --follow-imports=normal b.py", "mypy --strict --warn-unused-ignores b.py", "tsc -b --verbose", "tsc -b tsconfig.json --force",
        "shellcheck --norc a.sh", "shellcheck --sev=style a.sh",
    ]

    def test_relaxing_forms_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_strict_neighbours_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_ruff_add_inline_ignore_flag_fails(self):
        self.put("scripts/lint.sh", "ruff check --add-noqa .")  # justified: fixture text for the CLI flag check, never run
        self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_eslint_suppressions_are_a_baseline_and_no_justification_waives_them(self):
        for line in ["eslint --suppress-all . # justified: legacy code", "npm run lint -- --suppress-rule x # justified: legacy code",
                     "eslint --suppressions-location s.json . # justified: legacy code"]:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")


if __name__ == "__main__":
    unittest.main()
