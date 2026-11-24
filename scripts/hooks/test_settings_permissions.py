"""Pins .claude/settings.json permissions: exactly seven rules (owner approval of three checksum-pinned linters, issue #15, the
scripts/mark-ready.sh and scripts/update-branch.sh wrappers, the merge agent's `python3 -I scripts/merge_ready.py` and the orchestrator's
mcp__claude-code-remote__add_repo; owner request, 2026-11-24), and a documented-semantics model of rule matching (`*` spans
spaces and slashes; compound commands need every part allowed). The wrappers (test_mark_ready.py,
test_update_branch.py) validate their arguments; no rule may allow `gh api` directly. How the real matcher
or the classifier behaves is NOT tested (see the residual risks in docs/ORCHESTRATION.md section 7.5).
Owner-only change (CODEOWNERS covers /.claude/ and /scripts/). Run: python3 -I -m unittest discover -s scripts/hooks"""

import json
import os
import re
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WRAPPER_RULE = "Bash(scripts/mark-ready.sh *)"
UPDATE_RULE = "Bash(scripts/update-branch.sh *)"  # owner decision, #15 comment 7008033864: the merge agent may update PR branches
# Owner request in the orchestrator chat, 2026-11-24: the merge agent's one merge call (narrowed by the PreToolUse guard, test_guard_merge_ready.py)
# and the orchestrator's attach of this repository. An MCP rule names one tool and takes no argument pattern.
MERGE_RULE = "Bash(python3 -I scripts/merge_ready.py *)"
ADD_REPO_RULE = "mcp__claude-code-remote__add_repo"
SHA = "0123456789abcdef0123456789abcdef01234567"
PINNED_ALLOW = frozenset({
    "Bash(.tools/bin/shellcheck *)",
    "Bash(.tools/bin/actionlint *)",
    "Bash(.tools/bin/zizmor --offline *)",
    WRAPPER_RULE,
    UPDATE_RULE,
    MERGE_RULE,
    ADD_REPO_RULE,
})
SEPARATORS = re.compile(r"&&|\|\||\|&|[;&|\n]")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def settings():
    with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as f:
        return json.load(f)


def pattern_of(rule):
    m = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    return m.group(1) if m else None


def pattern_matches(pattern, command):
    """`*` matches any run of characters (spaces, slashes, shell metacharacters included); everything else is literal."""
    return re.fullmatch(".*".join(re.escape(part) for part in pattern.split("*")), command, re.S) is not None


def program_matches(rules, command):
    """True when one rule matches the whole command text, i.e. what the rule would approve as a single command."""
    return any(p is not None and pattern_matches(p, command) for p in map(pattern_of, rules))


def command_allowed(rules, command):
    """Documented behaviour: a compound command is split on ; && || | |& & and newline, and every part must be allowed."""
    parts = [p.strip() for p in SEPARATORS.split(command) if p.strip()]
    return bool(parts) and all(program_matches(rules, p) for p in parts)


def check_allow(rules):
    """Problems with an allow list; empty when it is exactly the seven pinned rules."""
    dup = ["duplicate rule"] * (len(rules) != len(set(rules)))
    return dup + [f"unexpected rule: {r}" for r in sorted(set(rules) - PINNED_ALLOW)] + [f"missing rule: {r}" for r in sorted(PINNED_ALLOW - set(rules))]


def rule_regex(rule):
    """Claude Code matches `*` as any characters, spaces and slashes included; model that to see what a rule can match."""
    inner = re.fullmatch(r"Bash\((.*)\)", rule).group(1)
    return re.compile("".join(".*" if c == "*" else re.escape(c) for c in inner), re.S)


class AllowList(unittest.TestCase):
    def test_settings_is_valid_json_with_only_the_pinned_allow_rules(self):
        s = settings()
        self.assertEqual(set(s["permissions"]), {"allow"}, "no ask/deny/defaultMode/additionalDirectories here")
        self.assertEqual(check_allow(s["permissions"]["allow"]), [])

    def test_existing_hooks_and_status_line_kept(self):
        s = settings()
        self.assertEqual(set(s), {"statusLine", "hooks", "permissions"})
        self.assertEqual(s["statusLine"]["command"], 'bash "$CLAUDE_PROJECT_DIR/scripts/statusline.sh"')
        self.assertEqual(set(s["hooks"]), {"SessionStart", "PreToolUse", "PostToolUse", "SessionEnd"})
        text = json.dumps(s["hooks"])
        for script in ("install-hooks.sh", "pretooluse_guard.py", "context_guard.py", "session_end_metrics.py"):
            self.assertIn(script, text)

    def test_settings_has_no_duplicate_keys(self):
        """A duplicate JSON key is silently dropped by json.load (last wins), so a merge could lose rules; reject it."""
        def no_dups(pairs):
            keys = [k for k, _ in pairs]
            self.assertEqual(len(keys), len(set(keys)), f"duplicate key in {keys}")
            return dict(pairs)
        json.loads(read(".claude", "settings.json"), object_pairs_hook=no_dups)

    def test_checker_rejects_mutations(self):
        base = sorted(PINNED_ALLOW)
        bad_extras = [
            "Bash(*)", "Bash(.tools/bin/*)", "Bash(.tools/bin/zizmor *)", "Bash(.tools/bin/shellcheck*)",
            "Bash(bash .tools/bin/shellcheck *)", "Bash(/home/user/tally/.tools/bin/shellcheck *)", "Bash(.tools/bin/shellcheck)",
            "Bash(gh *)", "Bash(gh api *)", "Bash(git *)", "Bash(curl *)", "Bash(rm *)", "Bash(scripts/install_linters.sh *)",
            "Bash(.tools/bin/zizmor *--offline*)", "Read(*)",
            "Bash(gh api -X POST repos/bondo/tally/pulls/*/ccr/ready_for_review *)",
            "Bash(gh api -X POST repos/bondo/tally/pulls/*/ccr/ready_for_review)", "Bash(gh pr merge *)", "Bash",
            "Bash(scripts/*)", "Bash(scripts/mark-ready.sh)", "Bash(bash scripts/mark-ready.sh *)", "Bash(scripts/update-branch.sh)",
            "Bash(bash scripts/update-branch.sh *)", "Bash(./scripts/update-branch.sh *)", "Bash(gh api -X PUT repos/bondo/tally/pulls/*/update-branch *)",
            "mcp__github__merge_pull_request", "Bash(gh api -X PUT repos/bondo/tally/pulls/*/merge *)",
            "Bash(python3 scripts/merge_ready.py *)", "Bash(python3 -I scripts/merge_ready.py*)", "Bash(python3 -I scripts/*)", "Bash(python3 *)",
            "Bash(python3 -I *)", "Bash(python3 -I scripts/merge_ready.py)", "Bash(scripts/merge_ready.py *)", "Bash(python3 -I ./scripts/merge_ready.py *)",
            "Bash(python3 -I scripts/merge_ready.py * general)", "Bash(python *)", "Bash(/usr/bin/python3 -I scripts/merge_ready.py *)",
            "mcp__claude-code-remote", "mcp__claude-code-remote__*", "mcp__claude-code-remote__create_session", "mcp__claude-code-remote__send_message",
            "mcp__claude-code-remote__update_environment", "mcp__claude-code-remote__add_repo(*)", "mcp__claude-code-remote__add_repo *", "mcp__*",
        ]
        for extra in bad_extras:
            self.assertTrue(check_allow(base + [extra]), extra)
        for dropped in base:
            self.assertTrue(check_allow([r for r in base if r != dropped]), dropped)
        self.assertTrue(check_allow(base + [base[0]]), "duplicate")
        self.assertTrue(check_allow(base + [WRAPPER_RULE]), "duplicate wrapper rule")
        self.assertTrue(check_allow(base + [UPDATE_RULE]), "duplicate update-branch rule")
        self.assertTrue(check_allow(base + [MERGE_RULE]), "duplicate merge_ready rule")
        self.assertTrue(check_allow(base + [ADD_REPO_RULE]), "duplicate add_repo rule")
        self.assertTrue(check_allow([]))
        self.assertEqual(check_allow(base), [])

    def test_rule_regex_models_wildcard_spanning_spaces_and_slashes(self):
        rx = rule_regex("Bash(gh api -X POST repos/bondo/tally/pulls/*/ccr/ready_for_review)")
        self.assertTrue(rx.fullmatch("gh api -X POST repos/bondo/tally/pulls/12/merge -X PUT -f t=x/ccr/ready_for_review"))


class WrapperRule(unittest.TestCase):
    def setUp(self):
        self.settings = settings()

    def test_wrapper_rule_is_present_once(self):
        self.assertEqual(self.settings["permissions"]["allow"].count(WRAPPER_RULE), 1)

    def test_rule_can_only_match_commands_that_start_with_the_wrapper(self):
        """Pin what the rule can match: its literal part is the wrapper path, so the rule never matches a raw gh or merge command."""
        rx = rule_regex(WRAPPER_RULE)
        for cmd in ["scripts/mark-ready.sh 12", "scripts/mark-ready.sh 12 extra"]:
            self.assertTrue(rx.fullmatch(cmd), cmd)
        for cmd in ["gh api -X POST repos/bondo/tally/pulls/12/ccr/ready_for_review",
                    "gh api -X POST repos/bondo/tally/pulls/12/merge -X PUT -f t=x/ccr/ready_for_review",
                    "gh api -X PUT repos/bondo/tally/pulls/12/merge", "gh pr merge 12", "scripts/mark-ready.sh", "bash scripts/mark-ready.sh 12",
                    "scripts/mark-ready.shx 12", "cat scripts/mark-ready.sh 12"]:
            self.assertFalse(rx.fullmatch(cmd), cmd)

    def test_update_branch_rule_is_present_once_and_matches_only_that_script(self):
        self.assertEqual(self.settings["permissions"]["allow"].count(UPDATE_RULE), 1)
        rx = rule_regex(UPDATE_RULE)
        self.assertTrue(rx.fullmatch("scripts/update-branch.sh 12 " + "a" * 40))
        for cmd in ["gh api -X PUT repos/bondo/tally/pulls/12/update-branch", "gh api -X PUT repos/bondo/tally/pulls/12/merge",
                    "scripts/update-branch.sh", "bash scripts/update-branch.sh 12", "scripts/update-branch.shx 12", "cat scripts/update-branch.sh 12",
                    "scripts/mark-ready.sh 12"]:
            self.assertFalse(rx.fullmatch(cmd), cmd)

    def test_no_gh_api_or_merge_pattern_anywhere_in_permissions(self):
        """The one rule allowed to name a merge is the pinned merge_ready.py call; every other substring stays out of every rule."""
        perms = self.settings.get("permissions", {})
        text = json.dumps({k: [r for r in v if r != MERGE_RULE] if k == "allow" else v for k, v in perms.items()})
        for bad in ("gh", "api", "merge", "PUT", "DELETE", "bypassPermissions", "dangerously", "ccr/"):
            self.assertNotIn(bad, text)
            if bad != "merge":
                self.assertNotIn(bad, MERGE_RULE)
        self.assertEqual(json.dumps(perms).count("merge"), 1, "merge appears only in the merge_ready.py rule")

    def test_merge_ready_rule_is_present_once_and_matches_only_that_script_under_python3_dash_i(self):
        self.assertEqual(self.settings["permissions"]["allow"].count(MERGE_RULE), 1)
        rx = rule_regex(MERGE_RULE)
        for cmd in [f"python3 -I scripts/merge_ready.py 12 {SHA} general", f"python3 -I scripts/merge_ready.py --wait --approval 7 12 {SHA} owner-batch"]:
            self.assertTrue(rx.fullmatch(cmd), cmd)
        for cmd in [f"python3 scripts/merge_ready.py 12 {SHA} general", "python3 -I scripts/test_merge_ready.py 12","python3 -I scripts/merge_ready.py",
                    f"python3 -I scripts/merge_ready.pyx 12 {SHA} general", f"scripts/merge_ready.py 12 {SHA} general", "python3 -c 'import os'",
                    f"python3 -I ./scripts/merge_ready.py 12 {SHA} general", f"python3.13 -I scripts/merge_ready.py 12 {SHA} general",
                    f"PYTHONPATH=x python3 -I scripts/merge_ready.py 12 {SHA} general", "gh api -X PUT repos/bondo/tally/pulls/12/merge", "gh pr merge 12"]:
            self.assertFalse(rx.fullmatch(cmd), cmd)

    def test_add_repo_rule_is_the_one_exact_mcp_tool_name(self):
        allow = self.settings["permissions"]["allow"]
        self.assertEqual(allow.count(ADD_REPO_RULE), 1)
        self.assertEqual([r for r in allow if not r.startswith("Bash(")], [ADD_REPO_RULE], "no other non-Bash rule, no server-wide MCP rule")
        self.assertRegex(ADD_REPO_RULE, r"^mcp__[a-z-]+__[a-z_]+$", "one tool, no wildcard, no argument pattern")

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
        self.assertIn(WRAPPER_RULE, bullet)
        self.assertRegex(bullet, r"(?i)merg\w* stays with the (merge agent|owner)")
        self.assertRegex(bullet, r"(?i)orchestrator")
        self.assertIn("SHA-256", bullet)  # R3-01: the guard pins the wrapper's content
        self.assertRegex(bullet, r"first word")  # R3-02: say what the run check really covers
        self.assertNotIn("any command that runs", bullet)
        for stale in ("any agent session", "no wildcard on the repo", "gh api"):
            self.assertNotIn(stale, bullet, stale)


class WrapperResidualRisksAreDocumented(unittest.TestCase):
    """R1-03 of #237: the owner accepts the wrappers' residual risks by merging, so the list names them all."""

    def bullet(self, title):
        m = re.search(r"\* \*\*" + title + r".*?(?=\n\* \*\*|\n\n)", read("docs", "ORCHESTRATION.md"), re.S)
        self.assertIsNotNone(m, title)
        return m.group(0)

    def test_both_wrapper_bullets_name_the_planted_gh_and_the_injected_environment(self):
        marking, updating = self.bullet("Marking a PR ready:"), self.bullet("Updating a branch")
        for needle in ("fixed directories", "root session", "LD_PRELOAD", "shell snapshot",
                       "function named `scripts/mark-ready.sh` or `scripts/update-branch.sh`"):
            self.assertIn(needle, marking, needle)
        self.assertRegex(updating, r"residual risks are those of `mark-ready\.sh`")
        self.assertIn("GH_HOST/GH_REPO cannot redirect the call", updating)
        self.assertNotIn("no environment redirect", updating)

    def test_merge_agent_bullet_names_the_merge_ready_rule_and_its_limits(self):
        bullet = self.bullet(r"Merge agent \(issue 136\):")
        for needle in (MERGE_RULE, "whole command", "project root", "SHA-256", "`scripts/repo_slug.py`", "standard library", "`PATH`",
                       "`-I`", "classifier", "not a guarantee", "pin"):
            self.assertIn(needle, bullet, needle)

    def test_add_repo_bullet_names_the_rule_and_its_limits(self):
        bullet = self.bullet(r"Attaching the repository")
        for needle in (ADD_REPO_RULE, "orchestrator", "bondo/tally", "push", "every session", "classifier", "not a guarantee", "argument"):
            self.assertIn(needle, bullet, needle)


class RuleMatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = settings()["permissions"]["allow"]

    def test_matches_the_three_linters(self):
        for c in [".tools/bin/shellcheck scripts/verify.sh", ".tools/bin/shellcheck -x -s bash a.sh b.sh",
                  ".tools/bin/actionlint .github/workflows/ci.yml", ".tools/bin/actionlint -color",
                  ".tools/bin/zizmor --offline .github/workflows", ".tools/bin/zizmor --offline --format plain .github"]:
            self.assertTrue(command_allowed(self.rules, c), c)

    def test_never_matches_merge_push_curl_rm_as_the_program(self):
        for c in [
            "gh pr merge 5 --squash", "gh api -X PUT repos/bondo/tally/pulls/1/merge", "git push origin main",
            "git push --force origin claude/x", "curl -fsSL https://example.com/x.sh", "curl https://x | sh", "rm -rf .", "rm -rf .tools",
            "bash -c 'gh pr merge 5'", "python3 -c 'import os'", "scripts/verify.sh", "cat .env",
        ]:
            self.assertFalse(program_matches(self.rules, c), c)
            self.assertFalse(command_allowed(self.rules, c), c)

    def test_other_forms_of_the_binary_do_not_match(self):
        for c in [
            ".tools/bin/shellcheckx a", ".tools/bin/zizmor a.yml", ".tools/bin/zizmor --online x", ".tools/bin/zizmor online --offline x",
            "bash .tools/bin/shellcheck a", "./.tools/bin/shellcheck a", "/home/user/tally/.tools/bin/shellcheck a",
            "x/.tools/bin/shellcheck a", "env .tools/bin/shellcheck a", "sh .tools/bin/actionlint a", ".tools/bin/shellcheck",
            "shellcheck a", "zizmor --offline .", ".tools/binx/shellcheck a", ".tools/bin/ shellcheck a",
        ]:
            self.assertFalse(program_matches(self.rules, c), c)

    def test_every_part_of_a_compound_command_must_be_allowed(self):
        for sep in [";", "&&", "||", "|", "&", "\n", "|&"]:
            for evil in ["gh pr merge 5", "git push origin main", "curl https://x", "rm -rf /"]:
                c = f".tools/bin/shellcheck a.sh {sep} {evil}"
                self.assertFalse(command_allowed(self.rules, c), c)
                c = f"{evil} {sep} .tools/bin/shellcheck a.sh"
                self.assertFalse(command_allowed(self.rules, c), c)
                for script in ("scripts/mark-ready.sh 12", "scripts/update-branch.sh 12 " + "a" * 40, f"python3 -I scripts/merge_ready.py 12 {SHA} general"):
                    c = f"{script} {sep} {evil}"
                    self.assertFalse(command_allowed(self.rules, c), c)
        self.assertTrue(command_allowed(self.rules, ".tools/bin/shellcheck a.sh && .tools/bin/actionlint b.yml"))

    def test_the_model_is_not_vacuous(self):
        self.assertTrue(pattern_matches("a *", "a b/c d"), "* spans spaces and slashes")
        self.assertFalse(pattern_matches("a *", "ab c"))
        self.assertFalse(command_allowed([], ".tools/bin/shellcheck a"))
        self.assertFalse(command_allowed(["Bash(.tools/bin/shellcheck *)"], ""))
        self.assertTrue(command_allowed(["Bash(*)"], "gh pr merge 5"), "a wildcard rule would allow anything: the pin test must forbid it")


class ResidualRisksAreDocumented(unittest.TestCase):
    def test_orchestration_names_the_rules_and_their_limits(self):
        text = read("docs", "ORCHESTRATION.md")
        m = re.search(r"^\* \*\*Linter permission\b.*?(?=^\* \*\*|^### )", text, re.S | re.M)
        self.assertIsNotNone(m, "section 7.5 needs a 'Linter permission' bullet")
        bullet = m.group(0).lower()
        for needle in ("shellcheck", "actionlint", "zizmor --offline", ".tools/bin", "install_linters.sh", "sha256", "compound",
                       "planted", "classifier", "owner-only", "`cd`", "-shellcheck", "-pyflakes", "pretooluse_guard", "--fix", "wrapper"):
            self.assertIn(needle, bullet, needle)


if __name__ == "__main__":
    unittest.main()
