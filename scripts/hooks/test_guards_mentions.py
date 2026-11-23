"""Tests for two narrow exceptions of the guards.sh threshold scan (task 1b, owner decision on #15 comment 7085808506).

1. Plural `thresholds` in markdown prose is prose, even on a line with a digit (see #322 comment 7085656155).
2. A removed line of a non-test .py file that mentions useJUnitPlatform or failOnNoDiscoveredTests only in a comment or a string
   literal is not a check setting (M1-68 part B). Real settings, every other keyword and gate tests (test files) still count.

Run: python3 -I -m unittest discover -s scripts/hooks
"""

import unittest

import test_guards_sh as base

REMOVED = "guard: removed check setting:"
LOWERED = "guard: lowered threshold:"

# agents/prompts/orchestrator.md line 103 before and after PR 322 commit f7cb30e, verbatim.
L103 = (
    'Merge agent (§7.5): the merge agent merges every READY PR except the owner-only ones, one at a time. Owner-only: permissions and '
    '`.claude` settings, guard thresholds, branch protection, repository settings, network allowlists, licence acceptances, design and '
    'product sign-off, docs that are themselves a gate (a decision to approve before work relies on it), naming and protected process '
    'files. A `risk:high` PR is marked READY only after the independent second-reviewer pass is clean. Docs PRs whose owner approval '
    'can wait go to it too and carry the status line `working draft ...; not owner-approved (see issue #15)`. A merge agent you '
)
OLD_103 = L103 + (
    'create has no owner authorization in its own session: the owner authorizes it there before its first merge, and you never pass an '
    'approval on to it.\n'
)
NEW_103 = L103 + (
    'spawn needs no owner authorization in its own session (#15 comment 7085221356): it carries the tag `role:merge-agent`, its '
    '`parent_session_id` is you and the body of #15 names it as active; before its first merge it reads comment 7085221356 itself on '
    "#15 and checks that it is the owner's account, unedited, and that its first line starts with `decision (owner` (the same check as "
    'for a batch approval; the check proves the account, not the person); you never pass an approval on to it.\n'
)

# The three lines M1-68 part B changes, verbatim: scripts/check_build_guards.py line 526, scripts/check_ui_emulators.py 126 and 128.
BUILD_GUARDS_526 = (
    "# failOnNoDiscoveredTests stay in the modules for now: the guards script reads a check setting moved to another file as removed (M1-68).\n"
)
UI_EMULATORS_126 = '    if not re.search(r"(?m)^\\s*unitTests\\.all \\{ it\\.useJUnitPlatform\\(\\) \\}\\s*$", build):\n'
UI_EMULATORS_128 = '            ":core:data must run its unit tests on the JUnit Platform (unitTests.all { it.useJUnitPlatform() }), "\n'


class Case(base.DiffCase):
    def removed(self, rel, line, needle=REMOVED):
        """`line` (one line of `rel`) is removed by the PR."""
        self.base(rel, "x = 1\n" + line + "\n")
        self.change(rel, "x = 1\n")
        if needle:
            self.assertFails(needle)
        else:
            self.assertPasses()


class PluralThresholdsInMarkdownProse(Case):
    def test_the_pr_322_edit_of_orchestrator_md_line_103_passes(self):
        self.base("agents/prompts/orchestrator.md", "# Orchestrator\n" + OLD_103)
        self.change("agents/prompts/orchestrator.md", "# Orchestrator\n" + NEW_103)
        self.assertPasses()

    def test_plural_prose_with_a_digit_on_the_line_passes(self):
        for line in (
            "Owner-only (§7.5): guard thresholds, branch protection and 2 more.",
            "Raise guard thresholds only with the owner (#15).",
            "See #15 for the guard thresholds; they are owner-only.",
            "Owner-only since PR 322: the guard thresholds.",
        ):
            with self.subTest(line=line):
                self.removed("agents/prompts/x.md", line, needle=None)

    def test_a_real_threshold_in_markdown_still_fails(self):
        for line in (
            "threshold: 80",
            "thresholds: 80",
            "coverage thresholds: 80",
            "coverage thresholds = 80",
            "| coverage thresholds | 80 |",
            "the coverage thresholds 80 and 60",
            "guard thresholds, minBound(80)",
            "guard threshold 600, branch protection",
            "kover thresholds",
            "thresholds, 80",
            "kover.thresholds, 80",
            "coverage thresholds.line 80",
        ):
            with self.subTest(line=line):
                self.removed("agents/prompts/x.md", line)

    def test_lowering_a_threshold_in_markdown_still_fails(self):
        self.base("agents/prompts/x.md", "coverage thresholds: 80\n")
        self.change("agents/prompts/x.md", "coverage thresholds: 70\n")
        self.assertFails(LOWERED)

    def test_the_same_prose_outside_markdown_still_fails(self):
        for rel in ("agents/roles.yaml", "config/x.toml", "scripts/gate.txt", "scripts/x.sh"):
            with self.subTest(rel=rel):
                self.removed(rel, "owner-only (7.5): guard thresholds, branch protection")


class CheckKeywordMentionsInPython(Case):
    def test_the_m1_68_part_b_lines_pass(self):
        for rel, line in (
            ("scripts/check_build_guards.py", BUILD_GUARDS_526),
            ("scripts/check_ui_emulators.py", UI_EMULATORS_126),
            ("scripts/check_ui_emulators.py", UI_EMULATORS_128),
        ):
            with self.subTest(rel=rel, line=line):
                self.removed(rel, line.rstrip("\n"), needle=None)

    def test_mentions_in_comments_and_plain_strings_pass(self):
        for line in (
            "x = 2  # failOnNoDiscoveredTests and useJUnitPlatform() move to build-logic",
            "msg = 'set failOnNoDiscoveredTests = true'  # useJUnitPlatform",
            'pat = rb"useJUnitPlatform\\(\\)", u"failOnNoDiscoveredTests"',
            'say("a \\" useJUnitPlatform()")',
        ):
            with self.subTest(line=line):
                self.removed("scripts/tool.py", line, needle=None)

    def test_a_real_setting_in_a_build_file_still_fails(self):
        for rel, line in (
            ("app/build.gradle.kts", "        unitTests.all { it.useJUnitPlatform() }"),
            ("app/build.gradle.kts", "    failOnNoDiscoveredTests = true"),
            ("app/build.gradle.kts", "    failOnNoDiscoveredTests = true // failOnNoDiscoveredTests"),
            ("app/build.gradle.kts", '    // useJUnitPlatform() moved: see "useJUnitPlatform"'),
            ("core/data/build.gradle", "    useJUnitPlatform()"),
            ("scripts/x.sh", "# failOnNoDiscoveredTests"),
        ):
            with self.subTest(rel=rel, line=line):
                self.removed(rel, line)

    def test_a_mention_removed_from_a_gate_test_still_fails(self):
        for rel in (
            "scripts/test_check_ui_emulators.py",
            "scripts/hooks/test_guards_x.py",
            "scripts/hooks/test_x",
            "scripts/check_ui_emulators_test.py",
        ):
            with self.subTest(rel=rel):
                self.removed(rel, UI_EMULATORS_128.rstrip("\n"))
                self.removed(rel, '        self.assertIn("failOnNoDiscoveredTests = true", out)  # pinned')

    def test_a_rename_to_or_from_a_test_or_non_python_file_still_fails(self):
        filler = "".join(f"value_{i} = compute_something_long({i})\n" for i in range(40))
        for old, new, line in (
            ("scripts/test_gate.py", "scripts/gate.py", UI_EMULATORS_128),
            ("scripts/gate2.py", "scripts/test_gate2.py", UI_EMULATORS_128),
            ("scripts/gate3.sh", "scripts/gate3.py", "# failOnNoDiscoveredTests\n"),
            ("scripts/gate4.py", "scripts/gate4.sh", "# failOnNoDiscoveredTests\n"),
        ):
            with self.subTest(old=old, new=new):
                self.base(old, filler + line)
                self.repo.git("mv", old, new)
                self.change(new, filler)
                self.assertIn(f"rename from {old}", self.repo.git("diff", "-M", "origin/main", "HEAD"))
                self.assertFails(REMOVED)

    def test_a_gate_test_in_a_path_with_spaces_still_fails(self):
        # The diff header splits on spaces, so `a/scripts/dir.py` and `x/y.py` must not read as the two paths.
        self.removed("scripts/dir.py x/y.py z/test_gate.py", UI_EMULATORS_128.rstrip("\n"))

    def test_a_keyword_in_code_still_fails(self):
        for line in (
            "useJUnitPlatform()  # the JUnit Platform runs every engine",
            "failOnNoDiscoveredTests = True  # see failOnNoDiscoveredTests",
            'run("x", failOnNoDiscoveredTests=True)  # "useJUnitPlatform"',
            "s = 'a' + useJUnitPlatform()",
            "s = 'a\\'' + useJUnitPlatform()",
            "s = 'unterminated useJUnitPlatform()",
            'x = f"{useJUnitPlatform()}"',
            'x = F"failOnNoDiscoveredTests"',
            'x = rf"failOnNoDiscoveredTests"',
            'x = """failOnNoDiscoveredTests',
        ):
            with self.subTest(line=line):
                self.removed("scripts/tool.py", line)

    def test_other_keywords_in_comments_and_strings_still_count(self):
        for line in (
            "x = 2  # useJUnitPlatform and warningsAsErrors",
            '"failOnNoDiscoveredTests at threshold 80",',
            "flags = ['useJUnitPlatform', 'maxIssues']",
        ):
            with self.subTest(line=line):
                self.removed("scripts/tool.py", line)


if __name__ == "__main__":
    unittest.main()
