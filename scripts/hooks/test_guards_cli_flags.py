"""Tests for the command-line flag check in scripts/guards.sh (issue 45). Run: python3 -I -m unittest discover -s scripts/hooks

A flag passed to a tool (ruff, mypy, tsc, ESLint, Prettier, shellcheck, actionlint) in shell scripts, git hooks, CI workflows,
package.json, Makefiles and pre-commit config passes only when it is on that tool's allowlist (issue 177); any other flag needs
`justified: <reason>` on the same logical line (a backslash continuation is one line). Every tool has lines that must fail and
neighbouring strict or ordinary lines that must pass. The first classes were written for the blocklist of PR 157 and still hold
unchanged: every flag they call relaxing is also off the allowlist. AllowlistTests and the classes after it are the new ones.
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


class ReasonWordsTests(CliFlagCase):
    """Owner decision (#46): a `justified:` reason needs 3 words of letters, on command-line flag lines too (check 2c uses just())."""

    RUFF = "ruff check --ignore E501 scripts # justified: %s"

    def raw(self, rel, line):
        self.repo.write(rel, line + "\n", raw=True)
        self.repo.commit()

    def test_a_reason_under_three_words_does_not_waive_a_flag(self):
        for reason in ["-", "x", "ok", "two words", "123 456 789"]:
            with self.subTest(reason=reason):
                self.raw("scripts/lint.sh", self.RUFF % reason)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_three_words_waive_a_flag(self):
        for reason in ["generated code here", "the legacy long URLs", "well-known stub gap"]:
            with self.subTest(reason=reason):
                self.raw("scripts/lint.sh", self.RUFF % reason)
                self.assertPasses()

    def test_the_other_forms_follow_the_same_rule(self):
        for rel, short, good in [
            (".github/workflows/ci.yml", '        SHELLCHECK_OPTS: "-e SC2086" # justified: ok',
             '        SHELLCHECK_OPTS: "-e SC2086" # justified: generated file here'),
            ("scripts/lint.sh", "ruff check \\\n  --ignore E501 # justified: ok", "ruff check \\\n  --ignore E501 # justified: generated code here"),
            ("firebase/package.json", '    "lint": "eslint --quiet ." // justified: x', '    "lint": "eslint --quiet ." // justified: noisy generated code'),
        ]:
            with self.subTest(file=rel, line=short):
                self.raw(rel, short)
                self.assertFails(MARK)
                self.raw(rel, good)
                self.assertPasses()

    def test_words_after_the_reason_are_not_counted(self):
        self.raw("scripts/lint.sh", "ruff check --ignore E501 scripts # justified: x # more words follow here")
        self.assertFails(MARK + ": scripts/lint.sh:1:")


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
        "shellcheck --sev=error a.sh", "shellcheck --se=error a.sh", "shellcheck --se error a.sh", 'SHELLCHECK_OPTS="--se=error" shellcheck a.sh',
        "ruff check --diff .", "ruff check --line-length 200 .", "ruff check --line-length=100 .",
    ]
    GOOD = [
        "eslint --prune-suppressions .", "ruff check --extend-select E .", "mypy --config-file mypy.ini b.py", "mypy --config mypy.ini b.py",
        "mypy --follow-imports=normal b.py", "mypy --strict --warn-unused-ignores b.py", "tsc -b --verbose", "tsc -b tsconfig.json --force",
        "shellcheck --norc a.sh", "shellcheck --sev=style a.sh", "shellcheck --se=warning a.sh", "ruff format --diff .", "ruff format --check .",
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


class AllowlistTests(CliFlagCase):
    """Issue 177 (owner decision, #15): a flag on a tool invocation passes only when it is on that tool's allowlist; any other flag
    needs `justified:`. UNKNOWN lines carry flags no blocklist ever named: each must fail. ALLOWED lines use only listed flags."""

    UNKNOWN = [
        ("ruff", ["ruff check --fix .", "ruff check --target-version py37 .", "ruff check --unsafe-fixes .", "ruff check --preview .",
                  "ruff check --respect-gitignore=false .", "ruff format --line-length 120 .", "ruff format --target-version py37 ."]),
        ("mypy", ["mypy --platform win32 scripts", "mypy --always-false FLAG scripts", "mypy --python-version 3.8 scripts",
                  "mypy --no-site-packages scripts", "mypy --enable-incomplete-feature=NewGenericSyntax scripts"]),
        ("tsc", ["tsc --target es5 -p .", "tsc --lib es5 -p .", "tsc --types node -p .", "tsc --typeRoots x -p .", "tsc --jsx react -p ."]),
        ("eslint", ["eslint --fix .", "eslint --global foo .", "eslint --env browser .", "eslint --parser x .", "eslint --plugin x .",
                    "eslint --cache ."]),
        ("prettier", ["prettier --check --plugin x .", "prettier --check --no-config .", "prettier --check --no-editorconfig .",
                      "prettier --check --config-precedence prefer-file .", "prettier --write --cache ."]),
        ("shellcheck", ["shellcheck -s sh a.sh", "shellcheck --shell=sh a.sh", "shellcheck -W 0 a.sh", "shellcheck --wiki-link-count=0 a.sh",
                        "shellcheck -f json1 -s dash a.sh"]),
        ("actionlint", ["actionlint -ignore 'SC2086' .github/workflows/ci.yml", "actionlint -ignore=SC2086 .github/workflows/ci.yml",
                        "actionlint --ignore x .github/workflows/ci.yml", "actionlint -config-file ci.yaml",
                        "actionlint -stdin-filename x.yml"]),
    ]
    ALLOWED = [
        "ruff check --config ruff.toml --no-cache --output-format concise --extend-select E scripts", "ruff format --check --diff scripts",
        "ruff --config ruff.toml format --diff .", "ruff check scripts", "ruff --version",
        "mypy --strict --warn-unused-ignores --warn-redundant-casts --disallow-untyped-defs --check-untyped-defs scripts",
        "mypy --config-file mypy.ini --follow-imports=normal scripts", "mypy --strict-equality --no-implicit-optional --extra-checks scripts",
        "tsc --noEmit -p tsconfig.json --pretty", "tsc -b --force --verbose", "tsc --noEmit --strict --noUnusedLocals --noImplicitAny true",
        "tsc --outDir build --outFile dist/out.js -p .", "tsc --version",
        "eslint --max-warnings 0 --config eslint.config.mjs --format stylish .", "eslint --rule 'no-console: error' --no-inline-config .",
        "eslint --report-unused-disable-directives-severity error --color .", "eslint --version",
        "prettier --check --config .prettierrc.json --log-level warn .", "prettier --write --list-different .", "prettier --version",
        "shellcheck -S warning -x -a -o all --color=never -f gcc a.sh", "shellcheck --severity=style --external-sources --check-sourced a.sh",
        "shellcheck -P SCRIPTDIR --source-path=SCRIPTDIR a.sh", "shellcheck --version",
        "actionlint", "actionlint -color -verbose -oneline .github/workflows/ci.yml", "actionlint -shellcheck=.tools/bin/shellcheck x.yml",
        "actionlint -no-color -format '{{json .}}' -pyflakes=/opt/pyflakes", "actionlint -version",
    ]

    def test_flags_off_the_allowlist_fail(self):
        for tool, lines in self.UNKNOWN:
            for line in lines:
                with self.subTest(tool=tool, line=line):
                    self.put("scripts/lint.sh", line)
                    self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_allowlisted_flags_pass(self):
        for line in self.ALLOWED:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_a_justified_unknown_flag_passes(self):
        for tool, lines in self.UNKNOWN:
            with self.subTest(tool=tool):
                self.put("scripts/lint.sh", lines[0] + " # justified: generated code, owner approved in #15")
                self.assertPasses()

    def test_a_reason_under_three_words_does_not_waive_an_unknown_flag(self):
        for tool, lines in self.UNKNOWN:
            for reason in ["-", "ok", "two words"]:
                with self.subTest(tool=tool, reason=reason):
                    self.repo.write("scripts/lint.sh", lines[0] + " # justified: " + reason + "\n", raw=True)
                    self.repo.commit()
                    self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_staged_mode_reads_the_index(self):
        """Also the R5-01 nit of issue 176: the 3-word rule on 2c lines in --staged mode."""
        for tool, lines in self.UNKNOWN:
            with self.subTest(tool=tool):
                self.repo.write("scripts/lint.sh", lines[0] + "\n")
                self.repo.git("add", "scripts/lint.sh")
                self.assertFails(MARK + ": scripts/lint.sh:1:", "--staged")
                self.repo.write("scripts/lint.sh", lines[0] + " # justified: ok\n", raw=True)
                self.repo.git("add", "scripts/lint.sh")
                self.assertFails(MARK + ": scripts/lint.sh:1:", "--staged")
                self.repo.write("scripts/lint.sh", lines[0] + " # justified: generated code here\n", raw=True)
                self.repo.git("add", "scripts/lint.sh")
                self.assertPasses("--staged")
                self.repo.git("rm", "-qf", "scripts/lint.sh")

    def test_the_value_of_an_allowed_flag_is_still_checked(self):
        for line in ["tsc --strict false -p .", "tsc --noUnusedLocals=false", "eslint --max-warnings 3 .", "eslint --max-warnings=-1 .",
                     "eslint --report-unused-disable-directives-severity warn .", "mypy --follow-imports silent scripts",
                     "shellcheck -S error a.sh", "shellcheck --severity=error a.sh", "ruff check --config ci.toml .",
                     "actionlint -shellcheck= x.yml", "actionlint -pyflakes= x.yml", 'actionlint -shellcheck "" x.yml',
                     "actionlint --pyflakes= x.yml"]:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_tsc_option_names_are_case_insensitive(self):
        """TypeScript reads --NoCheck like --noCheck, so a blocklist of exact spellings misses it."""
        for line in ["tsc --NoCheck", "tsc --NOCHECK -p .", "tsc --skiplibcheck -p .", "tsc --STRICT false -p ."]:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")
        self.put("scripts/lint.sh", "tsc --NOEMIT --STRICT -p .")
        self.assertPasses()

    def test_unknown_flags_in_npm_passthrough_and_package_json_fail(self):
        self.put("firebase/package.json", '    "lint": "eslint --fix ."')
        self.assertFails(MARK + ": firebase/package.json:1:")
        self.repo.git("rm", "-q", "firebase/package.json")
        self.repo.commit()
        self.put("scripts/lint.sh", "npm run lint -- --fix")
        self.assertFails(MARK + ": scripts/lint.sh:1:")
        self.put("scripts/lint.sh", "npm run lint -- --max-warnings 0 --config eslint.config.mjs")
        self.assertPasses()

    def test_only_the_text_after_a_bare_double_dash_is_a_file_list(self):
        self.put("scripts/lint.sh", "shellcheck -S warning -x -- a.sh -e.sh")
        self.assertPasses()


class RuffSubcommandTests(CliFlagCase):
    """Issue 174 and its R5-01 comment: a ruff option before the subcommand must not hide the subcommand's options."""

    def test_global_option_before_the_subcommand_does_not_hide_diff(self):
        for line in ["ruff --quiet check --diff .", "ruff --config ruff.toml check --diff .", "ruff --config ruff.toml check --fix .",
                     "ruff --no-cache check --target-version py37 ."]:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_the_format_subcommand_keeps_its_own_flags(self):
        for line in ["ruff --config ruff.toml format --diff .", "ruff --config ruff.toml format --check .", "ruff format --check --diff ."]:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()
        self.put("scripts/lint.sh", "ruff format --fix .")
        self.assertFails(MARK + ": scripts/lint.sh:1:")


class FalsePositiveFixTests(CliFlagCase):
    """Issue 164 items 4 and 5 (R3-06, R4-03) and installers: a tool name that is data, not a command, needs no flag review."""

    GOOD = [
        "uvx mypy@1.15 scripts", "uvx --from mypy@1.15 mypy --strict scripts", "tsc -b > build.log", "tsc -b tsconfig.json 2> build.log",
        "tsc --build --verbose >build.log", "tsc --outFile dist/out.js -p .", "tsc --outDir dist -p .",
        "pip install ruff --ignore-installed", "pip3 install -r r.txt ruff==0.4.0 --upgrade", "python3 -m pip install mypy --quiet --no-cache-dir",
        "npm install --save-dev eslint --save-exact", "npm i -D prettier --legacy-peer-deps", "npm ci --ignore-scripts eslint",
        "apt-get install -y shellcheck --no-install-recommends", "brew install shellcheck --quiet", "uv tool install ruff --force",
        "cargo install --locked ruff", "go install github.com/rhysd/actionlint/cmd/actionlint@latest -v",
    ]
    BAD = [
        "uvx mypy @args.txt scripts", "mypy @args.txt scripts", "tsc -b ci.json > build.log", "tsc -b > build.log ci.json",
        "tsc --outFile dist/out.js --skipLibCheck -p .", "npx --yes eslint --quiet .", "python3 -m ruff check --fix .",
    ]

    def test_data_uses_of_a_tool_name_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_the_neighbouring_real_invocations_still_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")


class ActionlintTests(CliFlagCase):
    """Issue 164 item 1 (owner decision, #15): `-ignore` with any value and an empty `-pyflakes=` or `-shellcheck=` are relaxations;
    a non-empty `-shellcheck=<path>` passes."""

    def test_ignore_and_disabled_integrations_fail_in_each_file_kind(self):
        files = {
            "scripts/lint_workflows.sh": '"$bin/actionlint" -ignore "SC2086" "${files[@]}"',
            ".githooks/pre-commit": "actionlint -pyflakes= .github/workflows/ci.yml",
            ".github/workflows/ci.yml": "        run: actionlint -shellcheck= .github/workflows/ci.yml",
            "scripts/install_linters.sh": "  printf 'exec \"$d/actionlint\" \"-shellcheck=$d/shellcheck\" -pyflakes= \"$@\"\\n' > wrapper",
        }
        for path, line in files.items():
            with self.subTest(path=path):
                self.put(path, line)
                self.assertFails(MARK + ": " + path + ":1:")
                self.repo.git("rm", "-q", path)
                self.repo.commit()

    def test_a_nonempty_shellcheck_path_passes_and_a_reason_waives_the_rest(self):
        self.put("scripts/lint.sh", 'exec "$d/../libexec/actionlint" "-shellcheck=$d/shellcheck" "$@"')
        self.assertPasses()
        self.put("scripts/lint.sh", 'exec "$d/actionlint" "-shellcheck=$d/shellcheck" -pyflakes= "$@" # justified: pyflakes needs Python here')
        self.assertPasses()


class MoreFileKindsTests(CliFlagCase):
    """Issue 164 item 2 (the parts a line scan can read): Makefiles, composite actions and pre-commit config are scanned too."""

    def test_invocations_in_these_files_fail(self):
        files = {
            "Makefile": "\truff check --fix .",
            "tools/Makefile": "\tmypy --ignore-missing-imports scripts",
            "ci.mk": "\teslint --quiet .",
            ".github/actions/lint/action.yml": "      run: eslint --quiet .",
            ".pre-commit-config.yaml": "        entry: ruff check --ignore E501",
        }
        for path, line in files.items():
            with self.subTest(path=path):
                self.put(path, line)
                self.assertFails(MARK + ": " + path + ":1:")
                self.repo.git("rm", "-q", path)
                self.repo.commit()

    def test_strict_lines_in_these_files_pass(self):
        for path, line in [("Makefile", "\truff check scripts"), (".pre-commit-config.yaml", "        entry: eslint --max-warnings 0")]:
            with self.subTest(path=path):
                self.put(path, line)
                self.assertPasses()


class ReviewRound1Tests(CliFlagCase):
    """PR 183 review round 1: R1-01 npm `--` tail with a tool name on the line, R1-02 pipx run and conda run, R1-03 actionlint programs,
    R1-04 camelCase tsc flags after npm `--`, R1-05 tsc response files, R1-06 --noImplicitUseStrict."""

    BAD = [
        "npm run lint:eslint -- --quiet", "npm run eslint -- --quiet", "npm exec eslint -- --quiet .", "npm run typecheck:tsc -- --noCheck",
        "yarn run lint:eslint -- --quiet", "npm ci && npm run eslint -- --quiet",
        "pipx run ruff check --ignore E501 .", "pipx run mypy --ignore-missing-imports scripts", "conda run -n x ruff check --ignore E501 .",
        "time pipx run ruff check --exit-zero .", "sudo pipx run ruff check --fix .",
        "actionlint -pyflakes=true x.yml", "actionlint -shellcheck=/bin/true x.yml", "actionlint -shellcheck=shellcheck-stub x.yml",
        "tsc @relax.txt", "tsc -p tsconfig.json @relax.txt", "tsc --noImplicitUseStrict -p .",
    ]
    GOOD = [
        "npm run lint:eslint -- --max-warnings 0", "npm exec eslint -- --max-warnings 0 .", "npm run typecheck -- --noEmit",
        "npm run typecheck -- --noImplicitAny", "npm run typecheck:tsc -- --noEmit --strict",
        "pipx install ruff --force", "pipx upgrade ruff --verbose", "pipx inject ruff plugin --quiet", "conda install -n x ruff --yes",
        "apt-get -y install shellcheck --no-install-recommends", "sudo apt install -y shellcheck --no-install-recommends", "pip install --upgrade ruff --quiet",
        'exec "$d/actionlint" "-shellcheck=$d/shellcheck" x.yml', "actionlint -pyflakes=/opt/bin/pyflakes x.yml",
        "tsc --noImplicitAny --noImplicitThis --noImplicitReturns --noImplicitOverride -p .",
    ]

    def test_holes_the_review_found_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_neighbouring_lines_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_the_workflow_form_of_pipx_run_fails(self):
        self.put(".github/workflows/ci.yml", "      - run: pipx run ruff check --ignore E501 .")
        self.assertFails(MARK + ": .github/workflows/ci.yml:1:")

    def test_a_justified_reason_waives_these_too(self):
        self.put("scripts/lint.sh", "npm run lint:eslint -- --quiet # justified: generated code, owner approved")
        self.assertPasses()


class ReviewRound2Tests(CliFlagCase):
    """PR 183 review round 2: R2-01 tsc @response file through npm `--`, R2-02 an option value that reads as an installer verb, R2-03 bun
    as a passthrough runner, R2-04 Makefile recipe prefixes, R2-05 ESLint formatter modules."""

    BAD = [
        "npm run typecheck -- @relax.txt", "npm exec tsc -- @relax.txt", "npm run typecheck -- --noEmit @relax.txt",
        "npm --prefix install exec eslint --quiet .", "npm -w install exec eslint --quiet .", "npm --loglevel install exec eslint -- --quiet",
        "conda -n install run ruff check --ignore E501 .", "uv --directory add run ruff check --fix .",
        "bun run lint:eslint -- --quiet", "bun run typecheck:tsc -- --noCheck",
        "eslint -f ./fmt.cjs .", "eslint --format ./fmt.cjs .", "eslint --format=eslint-formatter-x .", "npm run lint -- -f ./fmt.cjs",
    ]
    GOOD = [
        "npm run lint -- -f json", "eslint -f stylish --max-warnings 0 .", "eslint --format=html .", "eslint --format json-with-metadata .",
        "bun run lint -- --max-warnings 0", "bun install eslint --save-exact", "npm install --save-dev eslint --save-exact",
        "npm run typecheck -- --noEmit",
    ]

    def test_holes_the_review_found_fail(self):
        for line in self.BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")

    def test_neighbouring_lines_pass(self):
        for line in self.GOOD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertPasses()

    def test_makefile_recipe_prefixes_do_not_hide_the_tool(self):
        for line in ["\t-ruff check --fix .", "\t@-eslint --quiet .", "\t-mypy --ignore-missing-imports scripts", "\t+tsc --noCheck",
                     "\t@+-shellcheck -e SC2086 a.sh"]:
            with self.subTest(line=line):
                self.put("Makefile", line)
                self.assertFails(MARK + ": Makefile:1:")
        for line in ["\t-ruff check scripts", "\t@eslint --max-warnings 0 .", "\t@-tsc --noEmit -p tsconfig.json"]:
            with self.subTest(line=line):
                self.put("Makefile", line)
                self.assertPasses()


class ReviewRound3Tests(CliFlagCase):
    """PR 183 review round 3: R3-01 blanks between Makefile recipe prefixes, R3-02 npm script verbs after an option value, R3-03 makefile
    and GNUmakefile."""

    NPM_BAD = [
        "npm --prefix install test -- --quiet", "npm -w install t -- --quiet", "npm --prefix ci start -- --quiet", "npm --prefix install test -- @relax.txt",
        "npm --prefix install urn typecheck -- --noCheck", "pnpm --dir add test -- --quiet", "yarn --cwd add test -- --quiet",
        "npm --prefix install rum lint -- --quiet", "npm --prefix install restart -- --quiet", "npm --prefix install tst -- --quiet",
        "pnpm --dir add lint -- --quiet", "yarn --cwd add lint -- --quiet",
    ]

    def test_npm_script_verbs_after_an_option_value_do_not_hide_the_tail(self):
        for line in self.NPM_BAD:
            with self.subTest(line=line):
                self.put("scripts/lint.sh", line)
                self.assertFails(MARK + ": scripts/lint.sh:1:")
        self.put("scripts/lint.sh", "npm install --save-dev eslint --save-exact")
        self.assertPasses()

    def test_blanks_between_recipe_prefixes_do_not_hide_the_tool(self):
        for line in ["\t@ -ruff check --fix .", "\t+ -eslint --quiet .", "\t@ -mypy --ignore-missing-imports scripts",
                     "lint: ; @ -ruff check --fix .", "\t- @eslint --quiet ."]:
            with self.subTest(line=line):
                self.put("Makefile", line)
                self.assertFails(MARK + ": Makefile:1:")
        self.put("Makefile", "\t@ -ruff check scripts")
        self.assertPasses()

    def test_makefile_spellings_are_scanned(self):
        for path in ["makefile", "GNUmakefile", "tools/makefile", "tools/GNUmakefile"]:
            with self.subTest(path=path):
                self.put(path, "\truff check --fix .")
                self.assertFails(MARK + ": " + path + ":1:")
                self.repo.git("rm", "-q", path)
                self.repo.commit()
        self.put("makefile", "\truff check scripts")
        self.assertPasses()


class YamlArgsAndActionlintConfigTests(CliFlagCase):
    """Issue 164 (split from PR 309, ruling 7084379032): the args-like keys of a workflow step or a pre-commit hook (`with: args:`,
    `eslint_flags:`, pre-commit `args:`) are flags of the tool its `uses:`, `entry:` or `id:` names, and check 2b reads the `ignore:`
    entries of `.github/actionlint.y*ml`. Both only add failures to main."""

    WF, STEP = ".github/workflows/ci.yml", "jobs:\n  a:\n    steps:\n"

    def write(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()

    def check(self, path, bad, good):
        for text, n in bad:
            with self.subTest(text=text):
                self.write(path, text)
                self.assertFails(f"{MARK}: {path}:{n}:")
        for text in good:
            with self.subTest(ok=text):
                self.write(path, text)
                self.assertPasses()

    def fails(self, path, cases, mark=MARK):
        for text, n in cases:
            with self.subTest(text=text):
                self.write(path, text)
                self.assertFails(f"{mark}: {path}:{n}:")

    def test_lint_action_args_are_the_tool_flags(self):
        bad = [
            ("      - uses: astral-sh/ruff-action@v3\n        with:\n          args: check --ignore E501\n", 3),
            ("      - name: lint\n        with:\n          args: 'check --fix'\n        uses: astral-sh/ruff-action@v3\n", 3),
            ("      - uses: reviewdog/action-eslint@v1\n        with:\n          eslint_flags: '--quiet src'\n", 3),
            ("      - uses: reviewdog/action-actionlint@v1\n        with:\n          actionlint_flags: -ignore SC2086\n", 3),
            ("      - uses: astral-sh/ruff-action@v3\n        with:\n          args: >\n            check\n            --exit-zero\n", 3),
            ("      - uses: docker://rhysd/actionlint:1.7.7\n        with:\n          args: -pyflakes= .github/workflows/ci.yml\n", 3),
        ]
        for text, n in bad:
            with self.subTest(text=text):
                self.write(".github/workflows/ci.yml", text)
                self.assertFails(f"{MARK}: .github/workflows/ci.yml:{n}:")

    def test_allowed_action_args_other_actions_and_reasons_pass(self):
        for text in [
            "      - uses: astral-sh/ruff-action@v3\n        with:\n          args: check --config ruff.toml\n",
            "      - uses: astral-sh/ruff-action@v3\n        with:\n          args: format --check\n",
            "      - uses: astral-sh/ruff-action@v3\n        with:\n          args: check\n      - uses: actions/upload-artifact@v4\n"
            "        with:\n          args: --fix\n",
            "      - uses: astral-sh/ruff-action@v3\n        with:\n          args: check --fix # justified: formatting job commits the result\n",
            "      - id: ruff\n        uses: actions/upload-artifact@v4\n        with:\n          args: --fix\n",
        ]:
            with self.subTest(text=text):
                self.write(".github/workflows/ci.yml", text)
                self.assertPasses()

    def test_pre_commit_args_are_the_hook_flags(self):
        head = "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.8.0\n    hooks:\n"
        bad = [
            (head + "      - id: ruff\n        args: [--fix]\n      - id: ruff-format\n", 6),
            (head + "      - id: ruff-check\n        args: [--target-version, py37]\n", 6),
            (head + "      - id: mypy\n        args:\n        - --ignore-missing-imports\n", 6),
            (head + "      - id: mypy\n        args:\n          - --strict\n          - --allow-untyped-defs\n", 6),
            (head + "      - id: lint\n        entry: eslint\n        language: system\n        args: ['--quiet']\n", 8),
            (head + "      - {id: ruff, args: [--fix]}\n", 5),
            (head + "      - id: ruff-format\n        args: [--line-length=120]\n", 6),
        ]
        for text, n in bad:
            with self.subTest(text=text):
                self.write(".pre-commit-config.yaml", text)
                self.assertFails(f"{MARK}: .pre-commit-config.yaml:{n}:")
        for text in [
            head + "      - id: ruff-format\n        args: [--check]\n      - id: ruff\n        args: [--config, ruff.toml]\n",
            head + "      - id: mypy\n        args: [--strict]\n        additional_dependencies:\n          - types-requests\n",
            head + "      - id: check-yaml\n        args: [--unsafe]\n",
            head + "      - id: ruff\n        args: [--fix]  # justified: local hook only, CI checks again\n",
        ]:
            with self.subTest(ok=text):
                self.write(".pre-commit-config.yaml", text)
                self.assertPasses()

    def test_actionlint_config_ignore_entries_need_a_reason_each(self):
        SUP = "guard: unjustified suppression: "
        for path in [".github/actionlint.yaml", ".github/actionlint.yml"]:
            with self.subTest(path=path):
                self.write(path, "paths:\n  .github/workflows/**/*.yml:\n    ignore:\n      - 'SC2086'\n")
                self.assertFails(SUP + path + ":3:")
                self.write(path, "paths:\n  .github/workflows/**/*.yml:\n    ignore: # justified: upstream false positive tracked\n      - 'SC2086'\n")
                self.assertFails(SUP + path + ":4:")
                self.write(path, "paths:\n  x.yml:\n    ignore: ['SC2086']\n")
                self.assertFails(SUP + path + ":3:")
                self.repo.git("rm", "-q", path)
                self.repo.commit()
        self.write(".github/actionlint.yaml", "paths:\n  .github/workflows/**/*.yml:\n    ignore: # justified: upstream false positive tracked\n"
                   "      - 'SC2086' # justified: upstream false positive tracked\nself-hosted-runner:\n  labels: [big]\n")
        self.assertPasses()

    def test_workflow_args_keys(self):
        ruff, rd = "      - uses: astral-sh/ruff-action@v3\n        with:\n", "      - uses: reviewdog/action-eslint@v1\n        with:\n"
        self.check(".github/workflows/ci.yml", [
            (ruff + "          args: check --ignore E501\n          x_args: ok\n", 3),
            (rd + "          eslint_flags: --quiet\n          reviewdog_flags: ''\n", 3),
            (ruff + '          "args": check --ignore E501\n', 3),
            ("      - uses: astral-sh/ruff-action@v3\n        with: {args: check --ignore E501}\n", 2),
            ('      - "uses": astral-sh/ruff-action@v3\n        with:\n          args: check --fix\n', 3),
        ], [rd + "          reviewdog_flags: -fail-level=error\n          eslint_flags: --max-warnings 0\n"])

    def test_pre_commit_args_keys(self):
        head = "repos:\n  - repo: local\n    hooks:\n"
        self.check(".pre-commit-config.yaml", [
            (head + "      - id: ruff\n        args: [--ignore, E501]\n        verbose_args: []\n", 5),
            (head + '      - "id": ruff\n        args: [--fix]\n', 5),
        ], [])

    def test_actionlint_config_quoted_and_flow_ignore(self):
        for text, n in [('paths:\n  x.yml:\n    "ignore":\n      - SC2086\n', 3), ("paths:\n  x.yml:\n    'ignore': [SC2086]\n", 3),
                        ("paths:\n  x.yml: {ignore: [SC2086]}\n", 2)]:
            with self.subTest(text=text):
                self.write(".github/actionlint.yaml", text)
                self.assertFails(f"guard: unjustified suppression: .github/actionlint.yaml:{n}:")

    def test_actionlint_ignore_anchor_tag_and_alias(self):
        r = " # justified: upstream false positive tracked\n"
        self.fails(".github/actionlint.yaml", [
            ("paths:\n  x.yml:\n    ignore: &a" + r + "      - SC2086\n      - SC2046\n", 4),
            ("paths:\n  x.yml:\n    ignore: !!seq" + r + "      - SC2086\n", 4),
            ("x: &l\n  - SC2086\npaths:\n  x.yml:\n    ignore: *l" + r, 5),
        ], "guard: unjustified suppression")

    def test_bare_dash_items_and_key_case(self):
        s, w = self.STEP, "        with:\n"
        self.fails(self.WF, [
            (s + "      -\n        uses: astral-sh/ruff-action@v3\n" + w + "          args: check --fix\n", 7),
            (s + "      - uses: astral-sh/ruff-action@v3\n" + w + "          ARGS: check --fix\n", 6),
            (s + "      - uses: astral-sh/ruff-action@v3\n" + w + "          Args: check --fix\n", 6),
        ])

    def test_a_reason_waives_only_its_own_line_of_an_args_key(self):
        h = "repos:\n  - repo: x\n    hooks:\n      - id: ruff\n"
        r = " # justified: three words here\n"
        self.fails(".pre-commit-config.yaml", [
            (h + "        args:\n          - --ignore=E501\n          - --config=ruff.toml" + r, 5),
            (h + "        args:" + r + "          - --fix\n", 5),
            (h + "        args: [--config=ruff.toml," + r + "          --fix]\n", 5),
        ])
        self.write(".pre-commit-config.yaml", h + "        args:\n          - --fix" + r + "          - --config=ruff.toml\n")
        self.assertPasses()


class PrReviewRound1SplitTests(CliFlagCase):
    """PR 321 review round 1: R1-01 a flow list splits on every comma outside quotes, R1-02 a double-quoted YAML key written with an
    escape fails closed in the actionlint config and in a workflow step or pre-commit hook."""

    def write(self, rel, text):
        self.repo.write(rel, text)
        self.repo.commit()

    def test_flow_lists_and_escaped_keys(self):
        pc, h = ".pre-commit-config.yaml", "repos:\n  - repo: local\n    hooks:\n"
        wf, step = ".github/workflows/ci.yml", "jobs:\n  a:\n    steps:\n      - uses: astral-sh/ruff-action@v3\n        with:\n"
        for path, text, n, mark in [
            (pc, h + "      - id: ruff\n        args: [.,--fix]\n", 5, MARK),
            (pc, h + "      - id: lint\n        entry: eslint\n        args: [src,--quiet]\n", 6, MARK),
            (pc, h + "      - {id: ruff, args: [.,--fix]}\n", 4, MARK),
            (pc, h + '      - id: ruff\n        "ar\\x67s": [--fix]\n', 5, MARK),
            (wf, step + '          "ar\\u0067s": check --fix\n', 6, MARK),
            (".github/actionlint.yaml", 'paths:\n  x.yml:\n    "ign\\x6Fre":\n      - SC2086\n', 3, "guard: unjustified suppression"),
        ]:
            with self.subTest(text=text):
                self.write(path, text)
                self.assertFails(f"{mark}: {path}:{n}:")
                self.repo.git("rm", "-q", path)
                self.repo.commit()
        for text in [h + "      - id: ruff\n        args: [--config,ruff.toml]\n", h + "      - id: ruff\n        args: ['--output-format=a,--b']\n"]:
            with self.subTest(ok=text):
                self.write(pc, text)
                self.assertPasses()


class NpmTailResolutionTests(CliFlagCase):
    """Task M1-65 (issue 164 item 3, PR 309 ruling 7084379032): an npm `--` tail is resolved through the package.json scripts only for
    the npm forms, and only when every tracked definition of the script ends in a plain `[npx] <runner> <words>`. Any other layout, any
    `"scripts"` token outside the one strict layout and any `\\u` make every tail unknown, and an unknown tail keeps main's union check."""

    JEST = '{\n  "scripts": {\n    "test": "jest"\n  }\n}\n'
    LINE = "cd tools && npm test -- --quiet"

    def write(self, rel, text):
        self.repo.write(rel, text, raw=True)
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "--allow-empty", "-m", "c")

    def scripts(self, entries):
        return '{\n  "name": "t",\n  "scripts": {\n' + ",\n".join(f'    "{k}": "{v}"' for k, v in entries) + '\n  }\n}\n'

    def fails_with(self, pkg, line=LINE):
        self.write("tools/package.json", pkg)
        self.write("scripts/lint.sh", line + "\n")
        self.assertFails(MARK + ": scripts/lint.sh:1:")

    def setUp(self):
        super().setUp()
        self.write("firebase/package.json", self.JEST)

    def test_a_tail_that_reaches_a_test_runner_passes(self):
        self.write("tools/package.json", self.scripts([
            ("test", "jest"), ("e2e", "npx playwright test"), ("unit", "tsc --noEmit && vitest run"), ("m", "mocha --recursive"),
            ("cy", "cypress run --spec a/b.cy.ts"), ("ci", "npm test -- -u")]))
        for line in ["cd tools && npm test -- -u", "npm run e2e -- -c x.ts", "npm t -- --coverage", "npm tst -- -u",
                     "npm run-script unit -- --watch", "npm -s test -- -u", "npm run --silent e2e -- --headed", "npm rum m -- --quiet",
                     "npm urn cy -- --browser chrome", "npm test -- -- --quiet"]:
            with self.subTest(ok=line):
                self.write("scripts/lint.sh", line + "\n")
                self.assertPasses()
        self.write("scripts/lint.sh", "true\n")
        self.write(".github/workflows/ci.yml", "jobs:\n  a:\n    steps:\n      - run: cd tools && npm test -- -u\n")
        self.assertPasses()
        self.write("tools/package.json", self.scripts([("test", "jest")]).replace("\n", "\r\n"))
        self.write("scripts/lint.sh", "cd tools && npm test -- -u\n")
        self.assertPasses()

    def test_r4_01_and_n1_to_n4_any_other_scripts_layout_makes_every_tail_unknown(self):
        strict = self.JEST[:-2] + ",\n"
        for pkg in [
            '{\n  "name": "t",\n  "scripts"\n  : {\n    "test": "eslint ."\n  }\n}\n',  # R4-01
            '{\n  "name": "t",\n  "scripts"\n  :\n  {\n    "test": "eslint ."\n  }\n}\n',
            '{\n  "name": "t",\n  "scripts"\r: {\n    "test": "eslint ."\n  }\n}\n',
            strict + '  "scripts"\n  : {\n    "test": "eslint ."\n  }\n}\n',
            '{\n  "x": {\n    "a": 1}, "scripts": {\n    "test": "eslint ."\n  }\n}\n',  # N1
            '{\n  "x": {\n    "a": 1}, "scr\\u0069pts": {\n    "test": "eslint ."\n  }\n}\n',  # N2
            '{\n  "x": {\n    "a": 1\n  }, "scripts"\n  : {\n    "test": "eslint ."\n  }\n}\n',  # N3
            '{ "scripts"\n: {\n    "test": "eslint ."\n  }\n}\n',  # N4
            strict + '  "scripts": {\n    "test": "eslint ."\n  }\n}\n',
            strict + '  "scr\\u0069pts": {\n    "test": "eslint ."\n  }\n}\n',
            '{\n  "scripts": {"test": "jest"}\n}\n',
            '{\n  "x": {\n    "scripts": {\n      "test": "jest"\n    }\n  },\n  "scripts": {\n    "test": "jest"\n  }\n}\n',
            '{\n  "description": "scripts",\n  "scripts": {\n    "test": "jest"\n  }\n}\n',
            '{\n  "description": "caf\\u00e9",\n  "scripts": {\n    "test": "jest"\n  }\n}\n',  # R3-03: fails closed
            '{\n  "scripts": {\n    "test": "jest", "lint": "eslint ."\n  }\n}\n',
            '{\n  "scripts": {\n\n    "test": "jest"\n  }\n}\n',
            '{\n  "scripts": {\n    "test": "jest"\n',
        ]:
            with self.subTest(pkg=pkg):
                self.fails_with(pkg)

    def test_a_script_that_is_not_a_plain_runner_keeps_the_union_check(self):
        for cmd in ["eslint .", "jest && eslint .", "jest; eslint .", "jest | eslint .", "jest || eslint .", "jest & eslint .",
                    "eslint . \\\; jest", "jest \\\"$X\\\"", "jest $(eslint)", "jest `x`", "CI=1 jest", "npx -y jest", "node jest.js",
                    "firebase emulators:exec --only firestore", "npx", "jest;", "(jest)", "jest # x", "./node_modules/.bin/jest",
                    "jest > out", "jest ~/x", "jest \\u0026\\u0026 eslint ."]:
            with self.subTest(cmd=cmd):
                self.fails_with(self.scripts([("test", cmd)]))
        self.write("firebase/package.json", self.scripts([("test", "eslint .")]))  # every definition of the name must be a runner
        self.fails_with(self.scripts([("test", "jest")]))

    def test_c1_c2_npm_forms_only(self):
        pkg = self.scripts([("t", "eslint ."), ("tst", "eslint ."), ("test", "jest")])
        for line in ["cd tools && yarn t -- --quiet", "cd tools && yarn tst -- --quiet", "yarn test -- --quiet", "pnpm test -- --quiet",
                     "bun test -- --quiet", "npx jest -- --quiet", "npm exec jest -- --quiet", "npm run t -- --quiet",
                     "npm --prefix tools test -- --quiet", "npm --workspace=tools test -- --quiet", "npm start -- --quiet",
                     "npm run -- test --quiet", "npm run --prefix x test -- --quiet", "npm it -- --quiet"]:
            with self.subTest(line=line):
                self.fails_with(pkg, line)
        for line in ["cd tools && npm t -- --quiet", "npm tst -- --quiet", "npm run test -- --quiet"]:
            with self.subTest(ok=line):
                self.write("scripts/lint.sh", line + "\n")
                self.assertPasses()

    def test_a_reason_still_waives_an_unknown_tail_and_staged_mode_reads_the_index(self):
        self.write("tools/package.json", self.scripts([("test", "eslint .")]))
        self.write("scripts/lint.sh", self.LINE + " # justified: three words here\n")
        self.assertPasses()
        self.repo.write("scripts/lint.sh", "cd tools && npm test -- -u\n", raw=True)
        self.repo.git("add", "scripts/lint.sh")
        self.assertFails(MARK + ": scripts/lint.sh:1:", "--staged")
        self.repo.write("tools/package.json", self.scripts([("test", "jest")]), raw=True)  # the worktree resolves, the index does not
        self.assertFails(MARK + ": scripts/lint.sh:1:", "--staged")
        self.repo.git("add", "tools/package.json")
        self.assertPasses("--staged")


if __name__ == "__main__":
    unittest.main()
