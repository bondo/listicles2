"""Wiring tests: process files must keep naming the checks and rules they exist for (R9-03, R9-08, owner rules).
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import re
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TYPE_RESOLVED = (":core:domain:detektMain", ":core:domain:detektTest")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def ci_job(name):
    """Text of one top-level job of ci.yml (jobs are indented two spaces under `jobs:`)."""
    text = read(".github", "workflows", "ci.yml")
    m = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|\Z)", text, re.S | re.M)
    if not m:
        raise AssertionError(f"job {name} not found in ci.yml")
    return m.group(1)


def roles():
    """agents/roles.yaml role -> effort (small purpose-built parser: the file is two levels of plain key: value)."""
    out, role = {}, None
    for line in read("agents", "roles.yaml").splitlines():
        m = re.match(r"^  ([\w-]+):\s*$", line)
        if m:
            role = m.group(1)
        m = re.match(r"^    effort:\s*(\w+)\s*$", line)
        if m and role:
            out[role] = m.group(1)
    return out


class DiffCap(unittest.TestCase):
    """The guards job caps diff size: 600 by default, 1500 with the big-pr label (owner decision)."""

    def cap_expr(self):
        m = re.search(r"GUARD_MAX_DIFF:\s*\$\{\{(.*?)\}\}", ci_job("guards"))
        self.assertIsNotNone(m, "guards job must set GUARD_MAX_DIFF")
        return m.group(1)

    def test_big_pr_cap_is_1500(self):
        m = re.search(r"'big-pr'\)\s*&&\s*'(\d+)'\s*\|\|\s*'(\d+)'", self.cap_expr())
        self.assertIsNotNone(m, "GUARD_MAX_DIFF must be `big-pr label && '<cap>' || '<default>'`")
        self.assertEqual(m.group(1), "1500")

    def test_default_cap_stays_600(self):
        m = re.search(r"&&\s*'(\d+)'\s*\|\|\s*'(\d+)'", self.cap_expr())
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), "600")

    def test_no_stale_3000_cap(self):
        self.assertNotIn("3000", self.cap_expr())

    def test_no_stale_6000_cap(self):
        self.assertNotIn("6000", self.cap_expr())


class TypeResolvedDetekt(unittest.TestCase):
    def test_ci_static_job_runs_type_resolved_detekt(self):
        job = ci_job("static")
        for task in TYPE_RESOLVED:
            self.assertIn(task, job, f"ci.yml static job must run {task}")

    def test_pre_commit_runs_type_resolved_detekt(self):
        hook = read(".githooks", "pre-commit")
        for task in TYPE_RESOLVED:
            self.assertIn(task, hook, f".githooks/pre-commit must run {task}")

    def test_verify_runs_type_resolved_detekt(self):
        verify = read("scripts", "verify.sh")
        for task in TYPE_RESOLVED:
            self.assertIn(task, verify)

    def test_negative_job_lookup_fails_loudly(self):
        with self.assertRaises(AssertionError):
            ci_job("no-such-job")


class TestsAreWired(unittest.TestCase):
    def test_ci_guards_job_runs_the_hook_tests(self):
        self.assertIn("unittest discover -s scripts/hooks", ci_job("guards"))

    def test_verify_runs_the_hook_tests(self):
        self.assertIn("unittest discover -s scripts/hooks", read("scripts", "verify.sh"))

    def test_pre_push_uses_the_scope_script_and_runs_hook_tests(self):
        hook = read(".githooks", "pre-push")
        self.assertIn("prepush_scope.py", hook)
        self.assertIn("unittest discover -s scripts/hooks", hook)


class AgentEffort(unittest.TestCase):
    def test_subagent_frontmatter_effort_matches_roles_yaml(self):
        efforts = roles()
        for name in ("explorer", "ci-triage"):
            front = read(".claude", "agents", f"{name}.md").split("---")[1]
            m = re.search(r"^effort:\s*(\w+)\s*$", front, re.M)
            self.assertIsNotNone(m, f"{name}.md frontmatter lacks effort")
            self.assertEqual(m.group(1), efforts[name], name)

    def test_roles_parser_sees_all_roles(self):
        self.assertEqual(set(roles()), {"orchestrator", "planner", "implementer", "reviewer", "explorer", "ci-triage"})


class GitEnvImports(unittest.TestCase):
    def test_every_hook_test_that_runs_git_imports_gitenv_directly(self):
        """R12-51: protection through another module's import is accidental; discover order must not matter."""
        d = os.path.join(ROOT, "scripts", "hooks")
        for name in sorted(os.listdir(d)):
            if name.startswith("test_") and name.endswith(".py") and name != "test_wiring.py":
                src = read("scripts", "hooks", name)
                if re.search(r"""\[\s*["']git["']|"git",|subprocess""", src):
                    self.assertRegex(src, r"(?m)^import gitenv", name)
class DarkThemeUiTest(unittest.TestCase):
    def test_ui_test_inspects_rendered_pixels_for_both_themes(self):
        """R9-09: a text-presence assertion passes whatever the theme; the test must read pixels and compare both themes."""
        src = read("app", "src", "androidTest", "kotlin", "dev", "listicles", "app", "ListiclesAppTest.kt")
        for needle in ("captureToImage", "luminance", "darkTheme = dark.value", "dark.value = false"):
            self.assertIn(needle, src)


class OwnerRules(unittest.TestCase):
    """The owner rules must stay written down where agents read them."""

    def has(self, text, *needles):
        low = " ".join(text.lower().split())  # line wrapping must not matter
        for n in needles:
            self.assertIn(n.lower(), low, n)

    def test_review_md_states_reviewer_never_edits_or_pushes(self):
        self.has(read("REVIEW.md"), "never edit or push", "throwaway", "report only", "fix-now", "defer")

    def test_review_md_states_test_first_and_untested_flags(self):
        self.has(read("REVIEW.md"), "test-first", "failing test", "negative case", "untested", "tooling")

    def test_review_md_allows_deferring_minor_and_nit_after_blockers(self):
        self.has(read("REVIEW.md"), "follow-up issue", "no blocker or major")

    def test_deferral_is_part_of_status_verdict_and_author_duties(self):
        """R10-54: a deferred minor must not keep the verdict at changes_requested."""
        review = read("REVIEW.md")
        self.has(review, "`deferred`", "every remaining minor is deferred")
        for text in (review, read("docs", "PLAN.md")):  # R10-54: the merge condition must agree with the verdict rule
            self.has(text, "only nits or deferred minors remain", "deferred minors do not count")  # R12-53: the round-4 cap
        self.has(read("agents", "prompts", "implementer.md"), "defer")
        self.has(read("docs", "PLAN.md"), "deferred")

    def test_throwaway_rule_is_identical_everywhere(self):
        """R10-57: never pushed anywhere, deleted afterwards."""
        for parts in (("REVIEW.md",), ("agents", "prompts", "reviewer.md"), ("CLAUDE.md",)):
            self.has(read(*parts), "never pushed anywhere", "deleted afterwards")

    def test_plan_describes_the_pre_push_scope_skip(self):
        """R10-58"""
        self.has(read("docs", "PLAN.md"), "pre-push", "skips the gradle unit tests")

    def test_reviewer_prompt_has_the_rules(self):
        self.has(read("agents", "prompts", "reviewer.md"), "never edit or push", "report only", "fix-now", "defer", "untested", "throwaway")

    def test_implementer_prompt_has_test_first_for_tooling(self):
        self.has(read("agents", "prompts", "implementer.md"), "test-first", "failing test", "negative case", "tooling", "verify.sh")

    def test_claude_md_has_test_first_for_tooling(self):
        self.has(read("CLAUDE.md"), "test-first", "tooling", "negative case", "verify.sh")


if __name__ == "__main__":
    unittest.main()
