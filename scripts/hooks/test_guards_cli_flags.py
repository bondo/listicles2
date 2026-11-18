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
     ["ruff check --config ruff.toml --no-cache --output-format concise scripts", "ruff check --select E,F .",
      "ruff format --check ."]),
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

    def test_chained_commands_each_need_their_own_check(self):
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


if __name__ == "__main__":
    unittest.main()
