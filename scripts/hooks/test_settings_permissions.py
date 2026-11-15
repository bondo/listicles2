"""Pins the project permission allow list in .claude/settings.json: exactly the two ready_for_review rules, nothing broader.
Owner-only change (CODEOWNERS covers /.claude/). Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import re
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RULE = "Bash(gh api -X POST repos/bondo/listicles2/pulls/*/ccr/ready_for_review"
ALLOWED = (RULE + " *)", RULE + ")")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def allow_problems(allow):
    """Reasons an allow list is not exactly the two ready_for_review rules (empty list = fine)."""
    problems = [f"not allowed: {r!r}" for r in allow if r not in ALLOWED]
    problems += [f"missing: {r!r}" for r in ALLOWED if r not in allow]
    problems += [f"duplicate: {r!r}" for r in set(allow) if allow.count(r) > 1]
    return problems


class AllowListChecker(unittest.TestCase):
    """Negative cases for the checker itself."""

    def test_exact_pair_passes(self):
        self.assertEqual(allow_problems(list(ALLOWED)), [])

    def test_missing_rule_fails(self):
        self.assertTrue(allow_problems([ALLOWED[0]]))
        self.assertTrue(allow_problems([]))

    def test_broader_rules_fail(self):
        for extra in ["Bash(gh api *)", "Bash(gh api -X POST repos/bondo/listicles2/*)", "Bash(gh api -X POST repos/bondo/listicles2/pulls/*/merge *)",
                      "Bash(gh pr merge *)", "Bash(gh *)", "Bash", "Bash(*)", "mcp__github__merge_pull_request",
                      "Bash(gh api -X PUT repos/bondo/listicles2/pulls/*/merge *)", "Bash(gh api -X POST repos/bondo/listicles2/pulls/*/ccr/*)",
                      "Bash(gh api -X POST repos/bondo/*/pulls/*/ccr/ready_for_review *)"]:
            self.assertTrue(allow_problems(list(ALLOWED) + [extra]), extra)

    def test_duplicates_fail(self):
        self.assertTrue(allow_problems(list(ALLOWED) + [ALLOWED[0]]))


class ProjectSettings(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads(read(".claude", "settings.json"))

    def test_allow_list_is_exactly_the_two_ready_for_review_rules(self):
        allow = self.settings.get("permissions", {}).get("allow", [])
        self.assertEqual(allow_problems(allow), [])

    def test_no_other_permission_keys_loosen_anything(self):
        perms = self.settings.get("permissions", {})
        self.assertEqual(set(perms) - {"allow"}, set(), "only permissions.allow is pinned; ask the owner before adding keys")
        self.assertNotIn("defaultMode", perms)

    def test_no_merge_or_broad_gh_pattern_anywhere_in_permissions(self):
        text = json.dumps(self.settings.get("permissions", {}))
        for bad in ("merge", "gh pr", "bypassPermissions", "dangerously"):
            self.assertNotIn(bad, text)
        for rule in self.settings.get("permissions", {}).get("allow", []):
            self.assertTrue(re.fullmatch(r"Bash\(gh api -X POST repos/bondo/listicles2/pulls/\*/ccr/ready_for_review( \*)?\)", rule), rule)

    def test_existing_hooks_and_status_line_kept(self):
        self.assertEqual(set(self.settings["hooks"]), {"SessionStart", "PreToolUse", "PostToolUse", "SessionEnd"})
        self.assertIn("statusline.sh", self.settings["statusLine"]["command"])

    def test_codeowners_cover_claude_dir(self):
        self.assertRegex(read(".github", "CODEOWNERS"), r"(?m)^/\.claude/\s+@bondo\b")

    def test_orchestration_documents_the_rule_and_who_merges(self):
        text = read("docs", "ORCHESTRATION.md")
        self.assertIn("ccr/ready_for_review", text)
        self.assertIn(".claude/settings.json", text)
        m = re.search(r"(?is)ready_for_review.{0,1500}", text)
        self.assertIsNotNone(m)
        self.assertRegex(m.group(0), r"(?i)merg\w* stays with the (merge agent|owner)")


if __name__ == "__main__":
    unittest.main()
