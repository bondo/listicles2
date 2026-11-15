"""Pins the project permission allow list in .claude/settings.json: exactly one rule, for scripts/mark-ready.sh, nothing else.
The wrapper (test_mark_ready.py) validates the PR number; no rule may allow `gh api` directly, because `*` in a rule also matches spaces
and slashes. Owner-only change (CODEOWNERS covers /.claude/ and /scripts/). Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import re
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ONLY_RULE = "Bash(scripts/mark-ready.sh *)"


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def allow_problems(allow):
    """Reasons an allow list is not exactly the one wrapper rule (empty list = fine)."""
    problems = [f"not allowed: {r!r}" for r in allow if r != ONLY_RULE]
    if ONLY_RULE not in allow:
        problems.append(f"missing: {ONLY_RULE!r}")
    if allow.count(ONLY_RULE) > 1:
        problems.append("duplicate rule")
    return problems


def rule_regex(rule):
    """Claude Code matches `*` as any characters, spaces and slashes included; model that to see what a rule can match."""
    inner = re.fullmatch(r"Bash\((.*)\)", rule).group(1)
    return re.compile("".join(".*" if c == "*" else re.escape(c) for c in inner), re.S)


class AllowListChecker(unittest.TestCase):
    """Negative cases for the checker itself."""

    def test_exact_rule_passes(self):
        self.assertEqual(allow_problems([ONLY_RULE]), [])

    def test_missing_rule_fails(self):
        self.assertTrue(allow_problems([]))

    def test_old_and_broader_rules_fail(self):
        for extra in ["Bash(gh api -X POST repos/bondo/listicles2/pulls/*/ccr/ready_for_review *)",
                      "Bash(gh api -X POST repos/bondo/listicles2/pulls/*/ccr/ready_for_review)", "Bash(gh api *)", "Bash(gh pr merge *)",
                      "Bash(gh *)", "Bash", "Bash(*)", "Bash(scripts/*)", "Bash(scripts/mark-ready.sh)", "Bash(bash scripts/mark-ready.sh *)",
                      "mcp__github__merge_pull_request", "Bash(gh api -X PUT repos/bondo/listicles2/pulls/*/merge *)"]:
            self.assertTrue(allow_problems([ONLY_RULE, extra]), extra)

    def test_duplicates_fail(self):
        self.assertTrue(allow_problems([ONLY_RULE, ONLY_RULE]))

    def test_rule_regex_models_wildcard_spanning_spaces_and_slashes(self):
        rx = rule_regex("Bash(gh api -X POST repos/bondo/listicles2/pulls/*/ccr/ready_for_review)")
        self.assertTrue(rx.fullmatch("gh api -X POST repos/bondo/listicles2/pulls/12/merge -X PUT -f t=x/ccr/ready_for_review"))


class ProjectSettings(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads(read(".claude", "settings.json"))

    def test_allow_list_is_exactly_the_wrapper_rule(self):
        self.assertEqual(allow_problems(self.settings.get("permissions", {}).get("allow", [])), [])

    def test_no_other_permission_keys_loosen_anything(self):
        perms = self.settings.get("permissions", {})
        self.assertEqual(set(perms) - {"allow"}, set(), "only permissions.allow is pinned; ask the owner before adding keys")

    def test_rule_can_only_match_commands_that_start_with_the_wrapper(self):
        """Pin what the rule can match: its literal part is the wrapper path, so the rule never matches a raw gh or merge command."""
        rx = rule_regex(ONLY_RULE)
        for cmd in ["scripts/mark-ready.sh 12", "scripts/mark-ready.sh 12 extra"]:
            self.assertTrue(rx.fullmatch(cmd), cmd)
        for cmd in ["gh api -X POST repos/bondo/listicles2/pulls/12/ccr/ready_for_review",
                    "gh api -X POST repos/bondo/listicles2/pulls/12/merge -X PUT -f t=x/ccr/ready_for_review",
                    "gh api -X PUT repos/bondo/listicles2/pulls/12/merge", "gh pr merge 12", "scripts/mark-ready.sh", "bash scripts/mark-ready.sh 12",
                    "scripts/mark-ready.shx 12", "cat scripts/mark-ready.sh 12"]:
            self.assertFalse(rx.fullmatch(cmd), cmd)

    def test_no_gh_api_or_merge_pattern_anywhere_in_permissions(self):
        text = json.dumps(self.settings.get("permissions", {}))
        for bad in ("gh", "api", "merge", "PUT", "DELETE", "bypassPermissions", "dangerously", "ccr/"):
            self.assertNotIn(bad, text)

    def test_existing_hooks_and_status_line_kept(self):
        self.assertEqual(set(self.settings["hooks"]), {"SessionStart", "PreToolUse", "PostToolUse", "SessionEnd"})
        self.assertIn("statusline.sh", self.settings["statusLine"]["command"])

    def test_codeowners_cover_claude_dir_and_scripts(self):
        text = read(".github", "CODEOWNERS")
        self.assertRegex(text, r"(?m)^/\.claude/\s+@bondo\b")
        self.assertRegex(text, r"(?m)^/scripts/\s+@bondo\b")

    def test_orchestration_documents_the_wrapper_and_who_merges(self):
        text = read("docs", "ORCHESTRATION.md")
        m = re.search(r"\* \*\*Marking a PR ready:\*\*.*?(?=\n\* \*\*|\n\n)", text, re.S)
        self.assertIsNotNone(m, "ORCHESTRATION must have a 'Marking a PR ready' bullet")
        bullet = m.group(0)
        self.assertIn("scripts/mark-ready.sh", bullet)
        self.assertIn(ONLY_RULE, bullet)
        self.assertRegex(bullet, r"(?i)merg\w* stays with the (merge agent|owner)")
        self.assertRegex(bullet, r"(?i)orchestrator")
        self.assertIn("SHA-256", bullet)  # R3-01: the guard pins the wrapper's content
        self.assertRegex(bullet, r"first word")  # R3-02: say what the run check really covers
        self.assertNotIn("any command that runs", bullet)
        for stale in ("any agent session", "no wildcard on the repo", "gh api"):
            self.assertNotIn(stale, bullet, stale)


if __name__ == "__main__":
    unittest.main()
