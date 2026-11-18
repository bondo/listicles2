"""Wiring tests: process files must keep naming the checks and rules they exist for (R9-03, R9-08, owner rules).
Run: python3 -I -m unittest discover -s scripts/hooks"""

import os
import re
import sys
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TYPE_RESOLVED = (
    ":core:domain:detektMain",
    ":core:domain:detektTest",
    ":core:testing:detektMain",
    ":core:testing:detektTest",
)


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


def roles_file():
    """agents/roles.yaml as nested dicts and lists (small purpose-built parser: `key: value`, `key:` and `- item` lines)."""
    root = {}
    stack = [(-1, root, None, None)]  # (indent, container, parent container, key in parent)
    for raw in read("agents", "roles.yaml").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        while stack[-1][0] >= indent:
            stack.pop()
        _, node, parent, key = stack[-1]
        text = line.strip()
        if text.startswith("- "):
            if isinstance(node, dict) and not node:  # the `key:` above turned out to head a list
                node = []
                parent[key] = node
                stack[-1] = (stack[-1][0], node, parent, key)
            node.append(text[2:].strip())
            continue
        name, _, value = text.partition(":")
        value = value.strip()
        if value:
            node[name] = int(value) if value.isdigit() else (None if value == "null" else value)
        else:
            node[name] = {}
            stack.append((indent, node[name], node, name))
    return root


def roles():
    """agents/roles.yaml role -> effort (the active `roles:` section only)."""
    return {name: r["effort"] for name, r in roles_file()["roles"].items()}


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

    def test_verify_runs_them_in_the_detekt_step(self):
        """A mention elsewhere (a comment, another step) does not count: the `step detekt` line itself must name the tasks."""
        lines = [ln for ln in read("scripts", "verify.sh").splitlines() if ln.startswith("step detekt ")]
        self.assertEqual(len(lines), 1, lines)
        for task in TYPE_RESOLVED:
            self.assertIn(task, lines[0])

    def test_every_module_applying_detekt_is_type_resolved_in_verify(self):
        """#68 R2-07: a module that applies the detekt plugin gets detektMain and detektTest, or they run nowhere."""
        step = [ln for ln in read("scripts", "verify.sh").splitlines() if ln.startswith("step detekt ")][0]
        for module in sorted(os.listdir(os.path.join(ROOT, "core"))):
            gradle = os.path.join(ROOT, "core", module, "build.gradle.kts")
            if os.path.exists(gradle) and "libs.plugins.detekt" in read("core", module, "build.gradle.kts"):
                for task in ("detektMain", "detektTest"):
                    self.assertIn(f":core:{module}:{task}", step)

    def test_negative_job_lookup_fails_loudly(self):
        with self.assertRaises(AssertionError):
            ci_job("no-such-job")


class TestsAreWired(unittest.TestCase):
    def test_ci_guards_job_runs_the_hook_tests(self):
        self.assertIn("scripts/hooks/run_hook_tests.py", ci_job("guards"))

    def test_verify_runs_the_hook_tests(self):
        self.assertIn("scripts/hooks/run_hook_tests.py", read("scripts", "verify.sh"))

    def test_pre_push_uses_the_scope_script_and_runs_hook_tests(self):
        hook = read(".githooks", "pre-push")
        self.assertIn("prepush_scope.py", hook)
        self.assertIn("scripts/hooks/run_hook_tests.py", hook)


class HookTestsRunThroughTheSkipGate(unittest.TestCase):
    """R12-04 (#28): a bare `unittest discover` lets a skipped hook test pass; every entry point must use the runner."""

    def test_no_entry_point_runs_bare_unittest_discover_on_the_hook_tests(self):
        for name, text in (("ci.yml guards", ci_job("guards")), ("verify.sh", read("scripts", "verify.sh")), ("pre-push", read(".githooks", "pre-push"))):
            self.assertNotIn("-m unittest discover -s scripts/hooks", text, name)


# Agent Usage Redesign, tooling PR 1 (rev 46, "Roles and models"): role -> (model, effort).
NEW_ROLES = {
    "orchestrator": ("opus", "medium"),
    "planner": ("opus", "high"),
    "implementer": ("opus", "high"),
    "reviewer": ("opus", "high"),
    "second-reviewer": ("opus", "high"),
    "escalation-reviewer": ("opus", "max"),
    "verifier": ("opus", "high"),
    "design-reviewer": ("opus", "high"),
    "explorer": ("sonnet", "medium"),
    "ci-triage": ("sonnet", "medium"),
    "retro": ("opus", "high"),
}
# The pre-pilot values, kept as the kill-switch fallback set (the orchestrator spawns with them after PILOT-STOP).
FALLBACK = {
    "orchestrator": ("sonnet", "low"),
    "planner": ("opus", "high"),
    "implementer": ("sonnet", "medium"),
    "reviewer": ("opus", "high"),
    "design-reviewer": ("opus", "high"),
    "explorer": ("haiku", "low"),
    "ci-triage": ("haiku", "low"),
}


def frontmatter(name):
    return read(".claude", "agents", f"{name}.md").split("---")[1]


class AgentEffort(unittest.TestCase):
    def test_subagent_frontmatter_effort_matches_roles_yaml(self):
        efforts = roles()
        for name in ("explorer", "ci-triage"):
            m = re.search(r"^effort:\s*(\w+)\s*$", frontmatter(name), re.M)
            self.assertIsNotNone(m, f"{name}.md frontmatter lacks effort")
            self.assertEqual(m.group(1), efforts[name], name)

    def test_subagent_frontmatter_model_matches_roles_yaml(self):
        for name in ("explorer", "ci-triage"):
            m = re.search(r"^model:\s*(\w+)\s*$", frontmatter(name), re.M)
            self.assertIsNotNone(m, f"{name}.md frontmatter lacks model")
            self.assertEqual(m.group(1), roles_file()["roles"][name]["model"], name)

    def test_roles_parser_sees_all_roles(self):
        self.assertEqual(set(roles()), set(NEW_ROLES))


class RolesYaml(unittest.TestCase):
    """Agent Usage Redesign PR 1: strong models at high effort for roles that judge or write code; no token budgets."""

    def test_models_and_effort_follow_the_approved_table(self):
        for name, (model, effort) in NEW_ROLES.items():
            role = roles_file()["roles"][name]
            self.assertEqual((role["model"], role["effort"]), (model, effort), name)

    def test_no_active_role_has_a_token_budget(self):
        for name, role in roles_file()["roles"].items():
            self.assertNotIn("token_budget", role, name)

    def test_risk_high_raises_implementer_effort_to_max(self):
        impl = roles_file()["roles"]["implementer"]
        self.assertEqual(impl["max_effort_when"], ["the PR is tagged risk:high in the milestone doc"])
        self.assertNotIn("high_effort_when", impl)  # high is the default now; an agent may ask for more in its WORKER-RESULT

    def test_fallback_set_keeps_the_pre_pilot_values(self):
        fallback = roles_file()["fallback"]
        self.assertEqual(set(fallback), set(FALLBACK))
        for name, (model, effort) in FALLBACK.items():
            self.assertEqual((fallback[name]["model"], fallback[name]["effort"]), (model, effort), name)

    def test_fallback_keeps_the_old_budgets_and_escalation_rules(self):
        fallback = roles_file()["fallback"]
        self.assertEqual(fallback["implementer"]["token_budget"], 300000)
        self.assertEqual(len(fallback["implementer"]["high_effort_when"]), 3)
        self.assertEqual(fallback["planner"]["token_budget"], 150000)

    def test_fallback_is_not_read_as_active_roles(self):
        self.assertEqual(roles()["implementer"], "high")  # the fallback implementer is medium

    def test_design_reviewer_gets_three_rounds(self):
        self.assertIn("max 3 rounds", roles_file()["roles"]["design-reviewer"]["session"])

    def test_parser_reads_lists_and_nulls(self):
        self.assertIsInstance(roles_file()["fallback"]["implementer"]["high_effort_when"], list)
        self.assertIsNone(roles_file()["fallback"]["orchestrator"]["token_budget"])


class CiTriageReport(unittest.TestCase):
    def test_ci_triage_reports_up_to_60_lines_not_10(self):
        body = read(".claude", "agents", "ci-triage.md")
        self.assertIn("60 lines", body)
        self.assertNotIn("at most 10 lines", body)


class ContextThresholdsMatchTheHook(unittest.TestCase):
    """roles.yaml documents the handoff thresholds; the hook cannot parse YAML (stdlib, python -I), so a test ties the two."""

    def test_roles_yaml_context_section_equals_the_hook_constants(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "hooks"))
        try:
            import context_guard
        finally:
            sys.path.pop(0)
        ctx = roles_file()["context"]
        self.assertEqual((ctx["handoff_at_percent_1m"], ctx["step_boundary_after_percent_1m"]), context_guard.THRESHOLDS_LARGE[::-1])
        self.assertEqual((ctx["handoff_at_percent_200k"], ctx["step_boundary_after_percent_200k"]), context_guard.THRESHOLDS_SMALL[::-1])
        self.assertEqual(ctx["small_window_up_to_tokens"], context_guard.SMALL_WINDOW_MAX)
        self.assertEqual(ctx["handoff_template"], "handoff/TEMPLATE.md")


class PreCommitSkipsGradleForDocsOnly(unittest.TestCase):
    def test_pre_commit_uses_the_scope_script(self):
        self.assertIn("prepush_scope.py", read(".githooks", "pre-commit"))

    def test_pre_commit_still_runs_the_guards_unconditionally(self):
        hook = read(".githooks", "pre-commit")
        self.assertLess(hook.index("./scripts/guards.sh --staged"), hook.index("python3 -I scripts/hooks/prepush_scope.py"))


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


def lines_containing(text, needle):
    return [ln for ln in text.splitlines() if needle in ln]


def front_matter(text):
    """The `key: value` lines of a leading `---` block, or None when the file has no front matter."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    return dict(ln.split(":", 1) for ln in m.group(1).splitlines() if ":" in ln)


class HelperNegatives(unittest.TestCase):
    """The helpers below must reject bad input, or the M0-11 checks could never fail."""

    def test_lines_containing_is_exact(self):
        self.assertEqual(lines_containing("a 4 rounds\nb\n", "4 rounds"), ["a 4 rounds"])
        self.assertEqual(lines_containing("a\nb\n", "4 rounds"), [])

    def test_front_matter_rejects_missing_or_unclosed_blocks(self):
        self.assertIsNone(front_matter("no front matter\n"))
        self.assertIsNone(front_matter("---\nlabels: x\nno closing line\n"))
        self.assertEqual(front_matter("---\nlabels: follow-up\n---\nbody\n"), {"labels": " follow-up"})


class M011Alignment(unittest.TestCase):
    """M0-11: REVIEW.md, CLAUDE.md, templates and the handoff file agree with ORCHESTRATION and FOLLOW-UPS."""

    def has(self, text, *needles):
        low = " ".join(text.lower().split())
        for n in needles:
            self.assertIn(n.lower(), low, n)

    def test_round_cap_is_per_batch_in_review_md_and_claude_md(self):
        """ORCHESTRATION 6.2: the 4-round cap is per batch (a one-batch PR: per PR)."""
        for name in ("REVIEW.md", "CLAUDE.md"):
            lines = [ln for ln in lines_containing(read(name), "4 rounds")]
            self.assertTrue(lines, name)
            for ln in lines:
                self.assertIn("per batch", ln, f"{name}: {ln}")

    def test_claude_md_keeps_one_implementer_per_pr_and_a_fresh_reviewer_per_round(self):
        """M0.5-22 owns this rule; redesign PR 3 keeps the implementer across rounds, reviewers stay fresh."""
        self.has(read("CLAUDE.md"), "One implementer session per PR, kept across its review rounds", "fresh reviewer session per round")

    def test_findings_format_carries_area_recommend_and_deferred(self):
        review = read("REVIEW.md")
        self.has(review, '"area"', '"recommend"', '"recommend_reason"', "security-rules | sync-merge | release | process | general",
                 "`deferred`", "`ready_deferred`", "docs/FOLLOW-UPS.md")
        self.assertNotIn('"disposition"', review)

    def test_reviewer_recommends_and_never_decides(self):
        self.has(read("REVIEW.md"), "recommends", "never decides")
        self.has(read("agents", "prompts", "reviewer.md"), "`area`", "`recommend`", "never decide")

    def test_cap_and_only_nits_test_count_unresolved_non_deferred_findings(self):
        self.has(read("REVIEW.md"), "unresolved, non-deferred")

    def test_severity_table_covers_missing_tests(self):
        """ORCHESTRATION 2.0 hands severity of untested changes to REVIEW.md."""
        rows = {ln.split("|")[1].strip(" `"): ln for ln in read("REVIEW.md").splitlines() if ln.startswith("| `")}
        self.assertIn("untested", rows["major"].lower())
        self.assertIn("untested", rows["minor"].lower())
        self.has(rows["minor"], "docs/FOLLOW-UPS.md")

    def test_status_exception_no_longer_lists_m0_11(self):
        """R1-03: M0-11 is delivered by its own PR to main (the tasks ref), so 4.4's leave-it-todo exception must not name it."""
        rows = lines_containing(read("docs", "ORCHESTRATION.md"), "Exception: tasks whose PR branch is the tasks ref")
        self.assertEqual(len(rows), 1)
        self.assertNotIn("M0-11", rows[0])
        self.assertIn("M0-12", rows[0])

    def test_delivered_m0_11_notes_say_so(self):
        """R1-04: a done task's notes do not start with 'Still open'."""
        m = re.search(r'id = "M0-11"\n.*?\nnotes = """(.*?)"""', read("docs", "tasks.toml"), re.S)
        self.assertTrue(m)
        self.assertTrue(m.group(1).startswith("Delivered by PR #80."), m.group(1)[:40])
        self.assertNotIn("Still open", m.group(1))

    def test_handoff_template_refers_to_owner_work_by_number_only(self):
        self.has(read("handoff", "TEMPLATE.md"), "issue number only", "never restate")

    def test_follow_up_issue_template_matches_follow_ups_section_7(self):
        text = read(".github", "ISSUE_TEMPLATE", "follow-up.md")
        fm = front_matter(text)
        self.assertIsNotNone(fm)
        self.assertEqual(fm.get("labels", "").strip().strip("'\""), "follow-up")
        for field in ("Finding", "Where", "Source", "Problem", "Why deferred", "Suggested fix", "Burn down in", "Owner OK", "Decided by"):
            self.assertIn(f"**{field}:**", text)
        self.assertIn("[follow-up]", fm.get("title", ""))

    def test_pr_template_has_the_deferred_column_and_list(self):
        text = read(".github", "pull_request_template.md")
        self.has(text, "| Round | Blocker | Major | Minor | Nit | Deferred | Verdict |", "Deferred follow-ups")


if __name__ == "__main__":
    unittest.main()
