"""Tests for scripts/prompt_rules.py (M0.5-19). Run: python3 -I scripts/test_prompt_rules.py

The checker must find each rule in the real prompts and fail when a rule is deleted or weakened.
"""

import itertools
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompt_rules  # noqa: E402  # justified: must follow the sys.path insert above
import tasks

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "agents" / "prompts"
ROLES = ("orchestrator", "implementer", "reviewer", "planner", "design-reviewer", "second-reviewer", "verifier",
         "escalation-reviewer")

TIER0 = {"feedback", "idea", "decision", "needs-collaborator", "needs-owner"}
NEVER = {"golden-update", "big-pr", "owner-todo", "orchestrator-state", "follow-up", "severity:*", "target:*", "owner-ok", "area:*"}


def real(role):
    return (PROMPTS / f"{role}.md").read_text(encoding="utf-8")


def ids(problems):
    return {p.split(":", 1)[0] for p in problems}


def delete_match(role, rule_id, pattern_index=0):
    """The real prompt with every match of one pattern of one rule removed."""
    rule = next(r for r in prompt_rules.RULES if r.id == rule_id)
    text = prompt_rules.normalize(real(role))
    out, n = re.subn(rule.patterns[pattern_index], "", text, flags=re.I)
    assert n, f"{rule_id} does not match {role}.md"
    return out


class RealPromptsTests(unittest.TestCase):
    def test_every_prompt_passes(self):
        for role in ROLES:
            with self.subTest(role=role):
                self.assertEqual(prompt_rules.check_text(role, real(role)), [])

    def test_check_dir_on_the_repo_passes(self):
        self.assertEqual(prompt_rules.check_dir(PROMPTS), [])

    def test_every_rule_names_existing_roles_and_has_patterns(self):
        self.assertGreaterEqual(len(prompt_rules.RULES), 10)
        self.assertEqual(len({r.id for r in prompt_rules.RULES}), len(prompt_rules.RULES), "duplicate rule id")
        for r in prompt_rules.RULES:
            self.assertTrue(r.patterns, r.id)
            self.assertTrue(set(r.roles) <= set(ROLES), r.id)

    def test_every_prompt_is_covered_by_a_rule(self):
        for role in ROLES:
            self.assertTrue([r for r in prompt_rules.RULES if role in r.roles], role)


class RuleNegativeTests(unittest.TestCase):
    """Delete the sentence a rule needs: the checker must report exactly that rule."""

    def test_deleting_any_pattern_fails_that_rule_in_each_of_its_roles(self):
        for rule in prompt_rules.RULES:
            for role in rule.roles:
                for i in range(len(rule.patterns)):
                    with self.subTest(rule=rule.id, role=role, pattern=i):
                        problems = prompt_rules.check_text(role, delete_match(role, rule.id, i))
                        self.assertIn(rule.id, ids(problems))

    def test_rule_met_by_another_role_does_not_count(self):
        # The orchestrator wording does not satisfy the implementer's own rules.
        self.assertIn("worker-foreign-commits", ids(prompt_rules.check_text("implementer", real("orchestrator"))))
        self.assertIn("inbox-script", ids(prompt_rules.check_text("orchestrator", real("implementer"))))

    def test_rule_text_inside_an_html_comment_does_not_count(self):
        hidden = "<!-- " + real("orchestrator") + " -->"
        self.assertIn("no-resolve-thread", ids(prompt_rules.check_text("orchestrator", hidden)))

    def test_line_wrapping_and_case_do_not_matter(self):
        text = real("implementer").replace(" ", "\n").upper()
        self.assertEqual(prompt_rules.check_text("implementer", text), [])

    def test_empty_prompt_reports_every_rule_of_its_role(self):
        for role in ROLES:
            want = {r.id for r in prompt_rules.RULES if role in r.roles}
            self.assertEqual(ids(prompt_rules.check_text(role, "")), want)

    def test_unknown_role_is_an_error(self):
        with self.assertRaises(ValueError):
            prompt_rules.check_text("intern", "anything")


class LabelLineTests(unittest.TestCase):
    def labels(self):
        text = prompt_rules.normalize(real("orchestrator"))
        return (
            set(prompt_rules.parse_label_list(text, prompt_rules.TIER0_LINE)),
            set(prompt_rules.parse_label_list(text, prompt_rules.NEVER_LINE)),
        )

    def test_orchestrator_label_lists_are_exactly_the_decided_ones(self):
        self.assertEqual(self.labels(), (TIER0, NEVER))

    def test_constants_match_decision_d4(self):
        self.assertEqual(set(prompt_rules.TIER0_LABELS), TIER0)
        self.assertEqual(set(prompt_rules.NEVER_LABELS), NEVER)
        self.assertFalse(set(prompt_rules.TIER0_LABELS) & set(prompt_rules.NEVER_LABELS))

    def mutate(self, old, new):
        text = real("orchestrator")
        self.assertIn(old, text)
        return prompt_rules.check_text("orchestrator", text.replace(old, new, 1))

    def test_ci_steering_label_added_to_tier0_is_rejected(self):
        self.assertIn("tier0-labels", ids(self.mutate("needs-owner.", "needs-owner, big-pr.")))
        self.assertIn("tier0-labels", ids(self.mutate("needs-owner.", "needs-owner, golden-update.")))

    def test_tier0_label_removed_is_rejected(self):
        self.assertIn("tier0-labels", ids(self.mutate("idea, ", "")))

    def test_label_dropped_from_never_list_is_rejected(self):
        self.assertIn("never-labels", ids(self.mutate("big-pr, ", "")))
        self.assertIn("never-labels", ids(self.mutate("area:*", "area:x")))

    def test_missing_label_lines_are_rejected(self):
        text = prompt_rules.normalize(real("orchestrator"))
        gone = re.sub(prompt_rules.TIER0_LINE + r"[^.]*\.", "", text, flags=re.I)
        self.assertIn("tier0-labels", ids(prompt_rules.check_text("orchestrator", gone)))
        gone = re.sub(prompt_rules.NEVER_LINE + r"[^.]*\.", "", text, flags=re.I)
        self.assertIn("never-labels", ids(prompt_rules.check_text("orchestrator", gone)))



class M011AlignmentTests(unittest.TestCase):
    """M0-11: the role prompts match ORCHESTRATION (1.1 autonomy, 4.4 done on the tasks ref, 5 handover, 7.2 reviewers)."""

    NEW_RULES = {
        "orchestrator": {"no-stale-state-files", "autonomy", "checkin", "handover", "lock-takeover", "orch-deferral"},
        "implementer": {"impl-test-first", "impl-done-on-tasks-ref", "impl-deferral"},
        "reviewer": {"reviewer-report-only"},
    }

    def test_the_new_rules_exist_for_their_roles(self):
        for role, want in self.NEW_RULES.items():
            have = {r.id for r in prompt_rules.RULES if role in r.roles}
            self.assertLessEqual(want, have, role)

    def test_a_forbidden_pattern_is_reported_even_when_the_required_text_is_there(self):
        for old in ("docs/status.md", "docs/STATUS.md", "handoff/orchestrator.md", "`handoff/Orchestrator.md`"):
            with self.subTest(old=old):
                problems = prompt_rules.check_text("orchestrator", real("orchestrator") + f"\nWrite {old} at 50% context.\n")
                self.assertIn("no-stale-state-files", ids(problems))

    def test_a_forbidden_mention_hidden_in_an_html_comment_is_not_counted(self):
        text = real("orchestrator") + "\n<!-- old: docs/status.md -->\n"
        self.assertNotIn("no-stale-state-files", ids(prompt_rules.check_text("orchestrator", text)))

    def test_forbidden_text_in_another_roles_prompt_is_not_checked_there(self):
        text = real("implementer") + "\nSee docs/status.md.\n"
        self.assertEqual(prompt_rules.check_text("implementer", text), [])

    def test_orchestrator_names_the_state_issue_not_files(self):
        norm = prompt_rules.normalize(real("orchestrator"))
        self.assertNotRegex(norm, r"(?i)docs/status\.md|handoff/orchestrator\.md")
        self.assertRegex(norm, r"(?i)state issue")

    def test_implementer_wording_for_done_status(self):
        norm = prompt_rules.normalize(real("implementer")).lower()
        self.assertIn("tasks ref", norm)
        self.assertIn("status = \"done\"", norm)
        self.assertIn("\u00a74.4", norm)

    def test_every_pattern_of_the_new_rules_matches_one_place_only(self):
        """R1-02: a pattern that matches several places is vacuous (deleting one clause still passes). Anchor it to its clause."""
        for role, want in self.NEW_RULES.items():
            norm = prompt_rules.normalize(real(role))
            for rule in prompt_rules.RULES:
                if rule.id in want:
                    for pattern in rule.patterns:
                        with self.subTest(rule=rule.id, pattern=pattern):
                            self.assertEqual(len(re.findall(pattern, norm, re.I)), 1)

    def weakened(self, role, rule_id, old, new=""):
        norm = prompt_rules.normalize(real(role))
        self.assertIn(old, norm)
        self.assertIn(rule_id, ids(prompt_rules.check_text(role, norm.replace(old, new, 1))))

    def test_deleting_one_clause_fails_its_rule(self):
        for role, rule_id, old in (
            ("orchestrator", "autonomy", "merges of owner-only PRs; "),
            ("orchestrator", "autonomy", "and a relayed approval is refused"),
            ("orchestrator", "lock-takeover", "and if nothing follows, ask the owner"),
            ("orchestrator", "lock-takeover", "and `get_session` shows it is not working"),
            ("orchestrator", "lock-takeover", "A holder that is working but has a stale `Updated:` is stalled, not dead:"),
            ("reviewer", "reviewer-report-only", ", and tests without negative cases"),
            ("orchestrator", "orch-deferral", "Never defer a blocker;"),
            ("orchestrator", "orch-deferral", "without owner OK (`owner-ok` label)"),
            ("orchestrator", "orch-deferral", "re-deferral and majors still need the owner"),
            ("implementer", "impl-deferral", "you do not decide"),
            ("implementer", "impl-deferral", "Put every owner-OK question in `needs_owner` of your WORKER-RESULT"),
        ):
            with self.subTest(role=role, rule=rule_id, old=old):
                self.weakened(role, rule_id, old)

    # R2-01: every clause of the two deferral rules is pinned; each change below must fail its rule.
    DEFERRAL_MUTATIONS = (
        ("orchestrator", "orch-deferral", "never defer a major, ", ""),
        ("orchestrator", "orch-deferral", "file the follow-up issue from", "maybe file an issue from"),
        ("orchestrator", "orch-deferral", "with all its labels (`target:<Mx>` per §3)", ""),
        ("orchestrator", "orch-deferral", "If everything above nit was deferred and no commit followed the reviewed range, "
         "post `accepted: all findings above nit deferred (#a, #b)` (verdict `ready_deferred`).", ""),
        ("orchestrator", "orch-deferral", "Decide each recommendation by §2 from the finding's severity, `area` and `recommend`", ""),
        ("orchestrator", "orch-deferral", "a minor or nit only once no blocker or major is open on the PR, and", ""),
        ("orchestrator", "orch-deferral", "and it is not a regression this PR introduced", ""),
        ("orchestrator", "orch-deferral", "the PR's own acceptance criteria and tests do not depend on it, ", ""),
        ("orchestrator", "orch-deferral", "The 4-round cap and the only-nits-remain test count only unresolved, non-deferred findings.", ""),
        ("orchestrator", "orch-deferral", "and record a `decision` comment on the state issue", ""),
        ("orchestrator", "orch-deferral", "Check that the returned issue carries every label; if one is missing, create it with `gh api` and "
         "re-label the issue; if that fails, close the issue, keep the finding open, stop deferring and ask the owner.", ""),
        ("reviewer", "reviewer-report-only", "A deferral that breaks `docs/FOLLOW-UPS.md` §2, or lacks its issue or decision record, "
         "is itself a `major` finding (area `process`).", ""),
        ("reviewer", "reviewer-report-only", "Re-check every deferral record you are given (issue, decision, section 2 rules).", ""),
        ("implementer", "impl-deferral", "the orchestrator decides which minor/nit findings are deferred to follow-up issues (status `deferred`), "
         "so fix everything it does not defer", "you may defer minor findings"),
        ("implementer", "impl-deferral", " (finding id, severity, `area`, reason)", ""),
        ("implementer", "impl-deferral", ", by the same §2 limits", ""),
        ("implementer", "impl-deferral", "never a blocker; never a major, or a finding in the security-rules, sync-merge or release areas "
         "or on a `risk:high` task, without owner OK",
         "never a blocker, a major, or any finding in the security-rules, sync-merge or release areas or on a `risk:high` task without owner OK"),
        ("implementer", "impl-deferral", "a minor or nit only once no blocker or major is open and the fix is not small; ", ""),
        ("implementer", "impl-deferral", ", and with more than 8 open follow-ups for the milestone ask the owner", ""),
        ("implementer", "impl-deferral", "post the `decision` comment and any `accepted:` comment (with its `metrics:round` block, "
         "verdict `ready_deferred`) on the PR (§4, §6)", ""),
    )

    def test_each_deferral_clause_is_pinned(self):
        for role, rule_id, old, new in self.DEFERRAL_MUTATIONS:
            with self.subTest(role=role, old=old[:50]):
                self.weakened(role, rule_id, old, new)

    def test_deleting_any_sentence_of_a_deferral_paragraph_fails_its_rule(self):
        """R2-01: no sentence or clause of the paragraph may be free text that nothing pins."""
        for role, rule_id, end in (("orchestrator", "orch-deferral", " Collaborator inbox"), ("implementer", "impl-deferral", " Finish with")):
            norm = prompt_rules.normalize(real(role))
            m = re.search(r"Deferral \(.*?(?=" + re.escape(end) + ")", norm)
            self.assertTrue(m, role)
            for frag in re.split(r"[;:.]\s+", m.group(0)):
                if len(frag.split()) >= 3:
                    with self.subTest(role=role, fragment=frag[:60]):
                        self.assertIn(rule_id, ids(prompt_rules.check_text(role, norm.replace(frag, "", 1))))

    def test_deferral_paragraphs_carry_the_follow_ups_section_2_and_4_limits(self):
        for role, blocker in (("orchestrator", "never defer a blocker; never defer a major"), ("implementer", "never a blocker; never a major")):
            norm = prompt_rules.normalize(real(role))
            for needle in (blocker, "security-rules, sync-merge or release", "`risk:high`", "owner OK",
                           "more than 8 open follow-ups", "`decision` comment", "`ready_deferred`", "not small", "no blocker or major is open"):
                self.assertIn(needle.lower(), norm.lower(), f"{role}: {needle}")

    def test_deferral_with_owner_ok_for_a_blocker_is_rejected(self):
        """R2-02: FOLLOW-UPS 2 says blockers are never deferred, owner OK or not."""
        for role in ("orchestrator", "implementer"):
            norm = prompt_rules.normalize(real(role))
            self.assertNotRegex(norm, r"never defer a blocker, a major")

    def test_an_implementer_prompt_that_lets_it_defer_alone_is_rejected(self):
        """R1-01: the old wording let an implementer defer a protected-area minor itself."""
        old = ("once no blocker or major is open, minor/nit findings may be deferred to follow-up issues "
               "(status `deferred`, link the issue)")
        text = prompt_rules.normalize(real("implementer"))
        self.assertNotIn(old, text)
        self.assertIn("impl-deferral", ids(prompt_rules.check_text("implementer", old)))

    def test_reviewer_rule_rejects_a_prompt_that_lets_the_reviewer_push(self):
        text = real("reviewer").replace("NEVER edit or push the PR branch", "You may fix the PR branch")
        self.assertIn("reviewer-report-only", ids(prompt_rules.check_text("reviewer", text)))


class Round1Tests(unittest.TestCase):
    """PR #67 review round 1 (R1-01..R1-08): each phrase must be in the prompt AND pinned by a rule."""

    def without(self, role, *phrases):
        text = prompt_rules.normalize(real(role))
        for ph in phrases:
            self.assertIn(ph, text, f"{role}.md lacks {ph!r}")
            text = text.replace(ph, "")
        return text

    def assert_pinned(self, rule_id, *phrases, role="orchestrator"):
        for ph in phrases:
            with self.subTest(rule=rule_id, phrase=ph):
                problems = prompt_rules.check_text(role, self.without(role, ph))
                self.assertIn(rule_id, ids(problems))

    def test_r1_01_paused_wake_exception(self):
        self.assert_pinned("paused-wake", "except while paused under §7.7")

    def test_r1_02_accident_hit_is_not_the_usage_pause(self):
        self.assert_pinned(
            "accident-not-usage-pause",
            "stop spawning and pushing on the affected PR and ask the owner",
            "this is not the §7.7 usage pause",
            "the 45-min check-in stays",
        )

    def test_r1_03_counted_never_quoted_is_pinned(self):
        self.assert_pinned("trust-by-role", "Others are counted, never quoted.")

    def test_r1_04_collaborators_flag_is_pinned(self):
        self.assert_pinned("inbox-script", "--collaborators", "required if the repo moves to an organisation")

    def test_r1_05_review_packet_goes_to_owner_and_collaborator(self):
        self.assert_pinned(
            "review-packet",
            "the owner and the collaborator together",
            "collaborator input is advisory",
        )

    def test_r1_05_tasks_toml_says_the_same(self):
        notes = (ROOT / "docs" / "tasks.toml").read_text(encoding="utf-8")
        self.assertIn("Review packet for the owner and the collaborator (same time)", notes)
        self.assertNotIn("Review packet for the collaborator (", notes)

    def test_r1_07_reviews_of_open_prs_filtered_by_submitted_at(self):
        self.assert_pinned("inbox-script", "reviews of open PRs", "the script filters by submitted_at")

    def test_r1_08_planner_checks_foreign_commits_before_push(self):
        self.assertIn("worker-foreign-commits", ids(prompt_rules.check_text("planner", "")))
        self.assert_pinned("worker-foreign-commits", "foreign commit", "stop and report", role="planner")

    def test_orchestration_section_76_matches_the_prompt(self):
        doc = prompt_rules.normalize((ROOT / "docs" / "ORCHESTRATION.md").read_text(encoding="utf-8"))
        start = doc.index("### 7.6 Collaborator inbox")
        sec = doc[start : doc.index("## 8. Spawn messages", start)]
        for ph in ("--collaborators", "reviews of open PRs", "submitted_at", "this is not the §7.7 usage pause"):
            with self.subTest(phrase=ph):
                self.assertIn(ph, sec)


class M025Tests(unittest.TestCase):
    """M0.5-25: usage-read and pause text, R3 digest, review ledger row, R10 owner-todo. Each step is pinned by a rule that
    fails when the step is deleted or weakened (a changed day, hour, window or limit counts as weakened)."""

    NEW_ORCH = ("usage-read", "usage-pause-protocol", "usage-limit-failure", "usage-resume", "r3-digest", "review-ledger", "r10-owner-todo")

    def mutate(self, role, old, new):
        text = prompt_rules.normalize(real(role))
        self.assertIn(old, text, f"{role}.md lacks {old!r}")
        return prompt_rules.check_text(role, text.replace(old, new, 1))

    def assert_fails(self, role, rule_id, old, new):
        with self.subTest(rule=rule_id, old=old, new=new):
            self.assertIn(rule_id, ids(self.mutate(role, old, new)))

    def test_rules_exist_for_the_right_roles(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        for rid in self.NEW_ORCH:
            self.assertEqual(by_id[rid].roles, ("orchestrator",), rid)
        self.assertEqual(by_id["usage-worker"].roles, ("implementer", "planner"))
        self.assertEqual(by_id["usage-reviewer"].roles, ("reviewer", "design-reviewer"))

    def test_real_prompts_pass_the_new_rules(self):
        for rid in self.NEW_ORCH:
            self.assertNotIn(rid, ids(prompt_rules.check_text("orchestrator", real("orchestrator"))))
        for role, rid in (("implementer", "usage-worker"), ("planner", "usage-worker"), ("reviewer", "usage-reviewer")):
            self.assertNotIn(rid, ids(prompt_rules.check_text(role, real(role))))

    def test_other_roles_wording_does_not_count(self):
        self.assertIn("usage-worker", ids(prompt_rules.check_text("implementer", real("reviewer"))))
        self.assertIn("usage-reviewer", ids(prompt_rules.check_text("reviewer", real("implementer"))))
        for rid in self.NEW_ORCH:
            self.assertIn(rid, ids(prompt_rules.check_text("orchestrator", real("implementer"))))

    def test_r3_digest_weakened(self):
        for old, new in (
            ("on a Monday", "on a Friday"), ("after 10:00 UTC", "after 06:00 UTC"),
            ("if nothing merged in the last 7 days", "if nothing merged in the last 30 days"),
            ("at most 25 lines", "at most 40 lines"), ("at most 3 proposals", "at most 5 proposals"),
            ("decides nothing, edits no file, spawns no worker", "decides what it likes"),
            ("never add the `review` rows' `cost_usd`", "add the `review` rows' `cost_usd`"),
            ("`Weekly ops digest <date>` comment on #15", "comment on #15"),
        ):
            self.assert_fails("orchestrator", "r3-digest", old, new)

    def test_r3_digest_deleted(self):
        text = prompt_rules.normalize(real("orchestrator"))
        gone = text[: text.index("R3 weekly digest")]
        self.assertIn("r3-digest", ids(prompt_rules.check_text("orchestrator", gone)))

    def test_review_ledger_weakened(self):
        for old, new in (
            ("post its `review` row at `window_end`", "post its `review` row when you like"),
            ("2 weeks after the run", "1 week after the run"),
            ("the end of the next milestone", "the end of the milestone"),
            ("list it on #15 as open with its `window_end`", "list it on #15"),
            ("unknown cost stays empty, never estimated", "estimate an unknown cost"),
            ("`# metrics:review` block in a #15 comment", "comment"),
            ("findings = acted_on + ignored + disputed + deferred", "findings = acted_on"),
        ):
            self.assert_fails("orchestrator", "review-ledger", old, new)

    def test_r10_weakened(self):
        for old, new in (
            ("from M2 on, never before", "from M1 on"), ("once per milestone", "now and then"),
            ("assigned to the owner", "assigned to nobody"), ("mentioning the collaborator", "mentioning no one"),
            ("the owner's scores decide", "the average score decides"), ("`owner-todo`", "`todo`"),
            ("`[owner] R10-<milestone>: device notes`", "`[owner] <task id>: device notes`"),
            ("never an id from `docs/tasks.toml`", "an id from `docs/tasks.toml`"),
        ):
            self.assert_fails("orchestrator", "r10-owner-todo", old, new)

    def test_r10_title_cannot_complete_a_task(self):  # R1-02: scripts/tasks.py maps `[owner] <id>` titles to task ids
        title = "[owner] R10-M2: device notes"
        m = tasks.OWNER_TITLE.match(title)
        self.assertIsNotNone(m)
        ids_in_file = set(tasks.parse((ROOT / "docs" / "tasks.toml").read_text(encoding="utf-8")).by_id)
        self.assertNotIn(m.group(1), ids_in_file)
        self.assertIn("`[owner] R10-<milestone>: device notes`", prompt_rules.normalize(real("orchestrator")))

    def test_no_capital_after_a_semicolon_in_the_orchestrator_prompt(self):  # R1-04
        self.assertNotRegex(prompt_rules.normalize(real("orchestrator")), r"; [A-Z][a-z]")

    def test_m025_row_is_done_in_tasks_toml(self):  # R1-01: ORCHESTRATION 4.4, the PR that finishes a task sets it done
        row = tasks.parse((ROOT / "docs" / "tasks.toml").read_text(encoding="utf-8")).by_id["M0.5-25"]
        self.assertEqual(row.status, "done")

    def test_no_new_suppression_in_this_file(self):  # R2-02: only the sys.path E402 one, which carries its reason
        marks = [ln for ln in Path(__file__).read_text(encoding="utf-8").splitlines() if re.search(r"#\s*no" + "qa", ln)]
        self.assertEqual(len(marks), 1, marks)
        self.assertIn("justified:", marks[0])

    def test_usage_resume_weakened(self):  # R1-03
        for old, new in (
            ("if the read still shows limit reached or a 5-hour warning, set a new `paused until` time", "carry on"),
            ("`send_later` again at the new reset time plus 5 minutes", "x"),
            ("delete the old reminder, whether or not it fired, and stop", "delete the old reminder and stop"),
            ("resume implementers before reviewers", "resume reviewers first"),
            ("re-arm the 45-minute check-in", "x"), ("post one line", "x"),
            ("a session that has gone is a normal dead worker (§7.4): respawn it from `handoff/<branch>.md`", "x"),
            ("respawn it from `handoff/<branch>.md`", "leave it"),
        ):
            self.assert_fails("orchestrator", "usage-resume", old, new)

    def test_usage_read_unknown_type_and_overage_weakened(self):  # R1-03
        for old, new in (
            ("an unknown or missing `rateLimitType` counts as 5-hour", "an unknown `rateLimitType` counts as ok"),
            ("`isUsingOverage` is true the state is near limit (overage): it never pauses either (throttle per §7.7.6)",
             "`isUsingOverage` is true the state is near limit (overage): pause"),
            ("never pauses either (throttle per §7.7.6)", "never pauses either"),
        ):
            self.assert_fails("orchestrator", "usage-read", old, new)

    def test_usage_read_weakened(self):
        for old, new in (
            ("usage, every wake, first step", "usage, sometimes"),
            ("`rateLimitType` and `status` together, never from `status` alone", "`status`"),
            ("a 7-day warning never pauses", "a 7-day warning pauses"),
            ("a missing `rate_limit_info` counts as ok", "a missing `rate_limit_info` pauses"),
            ("`Usage:` line", "state"),
        ):
            self.assert_fails("orchestrator", "usage-read", old, new)

    def test_pause_protocol_order_and_steps(self):
        text = prompt_rules.normalize(real("orchestrator"))
        steps = ("`send_later`", "`interrupt_session`", "`delete_trigger`", "`PAUSED (usage limit)`", "end the turn")
        start = text.index("`send_later`")
        pos = [text.index(x, start) for x in steps]
        self.assertEqual(pos, sorted(pos))
        for a, b in itertools.pairwise(steps):
            swapped = text.replace(a, "@@A@@").replace(b, a).replace("@@A@@", b)
            with self.subTest(swap=(a, b)):
                self.assertIn("usage-pause-protocol", ids(prompt_rules.check_text("orchestrator", swapped)))
        for old, new in (
            ("never guess a reset time", ""), ("`resetsAt` + 5 minutes", "`resetsAt`"),
            ("paused until HH:MM UTC", "paused"), ("no spawning, no review rounds and no merge requests", "carry on"),
        ):
            self.assert_fails("orchestrator", "usage-pause-protocol", old, new)

    def test_limit_failure_and_resume_weakened(self):
        for old, new in (
            ("a limit failure is not a stall", "a limit failure is a stall"), ("no respawn", "respawn"),
            ("two-failure stop", "x"), ("post `RESUMED`", "post a comment"),
        ):
            self.assert_fails("orchestrator", "usage-limit-failure", old, new)

    def test_worker_and_reviewer_usage_weakened(self):
        for role in ("implementer", "planner"):
            for old, new in (
                ("account-wide", "per-session"), ("commit and push at every step", "push at the end"),
                ("usage limit reset: continue", "x"), ("from your last pushed commit", "from scratch"),
                ("`interrupt_session`", "stop"),
            ):
                with self.subTest(role=role, old=old):
                    self.assertIn("usage-worker", ids(self.mutate(role, old, new)))
        for old, new in (
            ("usage limit reset: re-check your findings comment and finish the round", "x"),
            ("account-wide", "per-session"), ("not a stall", "a stall"),
        ):
            self.assert_fails("reviewer", "usage-reviewer", old, new)

    def test_the_prompts_name_sections_that_exist(self):
        doc = (ROOT / "docs" / "ORCHESTRATION.md").read_text(encoding="utf-8")
        for sec in ("§7.7.1 Early warning", "§7.7.2 Pause protocol", "§7.7.3 A limit failure", "§7.7.4 Resume"):
            self.assertIn(f"**{sec}", doc)
        reviews = (ROOT / "docs" / "reviews" / "README.md").read_text(encoding="utf-8")
        for head in ("### 3.1 R3 weekly ops digest", "### 3.5 R10 device notes", "### 5.1 Ledger"):
            self.assertIn(head, reviews)
        orch = real("orchestrator")
        for ref in ("§7.7.1", "§7.7.2", "§7.7.4", "§3.1", "§3.5", "§5.1"):
            self.assertIn(ref, orch)


class M015Tests(unittest.TestCase):
    """M0.5-15: design-reviewer role, PR-body refresh, delta review, environment pick. Each step is pinned by a rule that
    fails when the step is deleted or weakened (a changed number, role, word or ordering counts as weakened)."""

    ORCH = ("orch-env-pick", "orch-delta-review", "orch-merge-request", "orch-design-review")
    def mutate(self, role, old, new):
        text = prompt_rules.normalize(real(role)).lower()  # the rules are case-insensitive
        self.assertIn(old, text, f"{role}.md lacks {old!r}")
        return prompt_rules.check_text(role, text.replace(old, new, 1))

    def assert_fails(self, role, rule_id, old, new):
        with self.subTest(role=role, rule=rule_id, old=old, new=new):
            self.assertIn(rule_id, ids(self.mutate(role, old, new)))

    def test_rules_exist_for_the_right_roles(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        for rid in self.ORCH:
            self.assertEqual(by_id[rid].roles, ("orchestrator",), rid)
        for rid in ("dr-rubric", "dr-judge-limits", "dr-rounds", "dr-hand-off", "dr-handle-config", "dr-report-only"):
            self.assertEqual(by_id[rid].roles, ("design-reviewer",), rid)
        self.assertEqual(by_id["impl-pr-body"].roles, ("implementer",))
        self.assertEqual(by_id["reviewer-delta"].roles, ("reviewer",))
        self.assertIn("design-reviewer", by_id["usage-reviewer"].roles)
        self.assertIn("design-reviewer", by_id["worker-no-labels"].roles)

    def test_real_prompts_pass(self):
        self.assertEqual(prompt_rules.check_text("design-reviewer", real("design-reviewer")), [])
        self.assertEqual(prompt_rules.check_dir(PROMPTS), [])

    def test_other_roles_wording_does_not_count(self):
        for rid in self.ORCH:
            self.assertIn(rid, ids(prompt_rules.check_text("orchestrator", real("implementer"))))
        for rid in ("dr-rubric", "dr-judge-limits", "dr-rounds", "dr-hand-off", "dr-handle-config"):
            self.assertIn(rid, ids(prompt_rules.check_text("design-reviewer", real("reviewer"))))
        self.assertIn("impl-pr-body", ids(prompt_rules.check_text("implementer", real("orchestrator"))))
        self.assertIn("reviewer-delta", ids(prompt_rules.check_text("reviewer", real("design-reviewer"))))

    def test_environment_pick_weakened(self):
        for old, new in (
            ("a task that touches a process file", "a task that touches a docs file"),
            ("gets the tooling environment (`listicles_task=tooling`)", "gets the normal environment"),
            ("every other task gets the normal one", "every other task gets the tooling one"),
            ("`.githooks/`", "`.github-hooks/`"), ("`scripts/hooks/`", "`scripts/hook/`"), ("`scripts/guards.sh`", "`scripts/`"),
            ("before every `create_session`", "after every `create_session`"),
            ("a wrong pick blocks the worker", "a wrong pick is harmless"),
        ):
            self.assert_fails("orchestrator", "orch-env-pick", old, new)

    def test_delta_review_weakened(self):
        for old, new in (
            ("a commit after `reviewed_through` always gets one delta review before the merge request", "a commit after `reviewed_through` is merged"),
            ("a fresh reviewer with the whole pr diff and the findings json, focused on `reviewed_through..head_sha`",
             "a fresh reviewer on `reviewed_through..head_sha` only"),
            ("there is no owner-acceptance alternative, for any pr", "owner acceptance is an alternative"),
            ("always gets one delta review", "sometimes gets one delta review"),
            ("set `reviewed_through` afterwards", "leave `reviewed_through` as it was"),
        ):
            self.assert_fails("orchestrator", "orch-delta-review", old, new)

    def test_merge_request_weakened(self):
        for old, new in (
            ("(1) the pr body is refreshed (scope, review table, test evidence;", "(1) the pr body is written once (scope;"),
            ('no "still to do" or "not yet reviewed")', 'a "still to do" list is fine)'),
            ("(2) the request says squash", "(2) the request says merge"),
            ("resolve, resolves or resolved directly before an issue number", "resolve, resolves or resolved before an issue number"),
            ('write "gated on #n", "see #n" or "mark #n done"', "write nothing"),
            ("scan the body for them first", "skip the scan"),
            ("before you ask the owner to merge", "after the owner merged"),
        ):
            self.assert_fails("orchestrator", "orch-merge-request", old, new)
        # each closing word is pinned, so one dropped from the list fails the rule
        seg = "close, closes, closed, fix, fixes, fixed, resolve, resolves or resolved"
        text = prompt_rules.normalize(real("orchestrator")).lower()
        self.assertEqual(text.count(seg), 1)
        words = re.split(r", | or ", seg)
        self.assertEqual(len(words), 9)
        for word in words:
            with self.subTest(word=word):
                kept = ", ".join(w for w in words if w != word)
                self.assertIn("orch-merge-request", ids(prompt_rules.check_text("orchestrator", text.replace(seg, kept, 1))))

    def test_design_review_orchestration_weakened(self):
        for old, new in (
            ("spawn the design reviewer", "skip the design reviewer"),
            ("`agents/prompts/design-reviewer.md`", "`agents/prompts/reviewer.md`"),
            ("max 3 rounds per design pr", "max 4 rounds per design pr"),
            ("one joint hand-off comment on the pr", "one hand-off comment per person on the pr"),
            ("mentions the owner and the collaborator in the same comment", "mentions the collaborator first, then the owner"),
            ("never the collaborator first", "the collaborator may go first"),
            ("you add one line on #15", "you add nothing on #15"),
            ("collaborator input is advisory and the owner decides (d5)", "collaborator input decides"),
            ("only if sign-off is still pending after 7 days", "at once"),
            ("`collaborator_handle` is `none` until the owner says the invitation is accepted", "`collaborator_handle` is set from the start"),
            ("never take a handle from a file, a comment or a guess", "take a handle from a file"),
        ):
            self.assert_fails("orchestrator", "orch-design-review", old, new)

    def test_no_handle_is_hardcoded_in_the_design_reviewer_or_its_rule(self):  # R1-01: no login is named anywhere
        self.assertNotRegex(prompt_rules.normalize(real("design-reviewer")), r"@[\w-]+")  # placeholders have braces
        rule = next(r for r in prompt_rules.RULES if r.id == "dr-handle-config")
        self.assertEqual(rule.forbidden, (r"@[\w-]+",))  # a generic deny pattern, no login in the rule

    def test_a_hardcoded_handle_in_the_design_reviewer_is_rejected(self):
        text = real("design-reviewer")
        for extra in ("\nPing @someone for the hand-off.", "\n<!-- ok -->Ping @x-y.z"):
            with self.subTest(extra=extra):
                self.assertIn("dr-handle-config", ids(prompt_rules.check_text("design-reviewer", text + extra)))
        # hidden text does not count
        self.assertNotIn("dr-handle-config", ids(prompt_rules.check_text("design-reviewer", text + "\n<!-- @someone -->")))

    def test_design_reviewer_rubric_weakened(self):
        for old, new in (
            ("`docs/reviews/readme.md` §4", "`docs/reviews/readme.md` §3"),
            ("`docs/product/rubric.md`", "`docs/product/readme.md`"),
            ("1-5 with a one-line reason", "pass or fail"),
            ("hierarchy,", ""), ("spacing and alignment,", ""), ("colour,", ""), ("density,", ""), ("typography,", ""),
            ("consistency,", ""), ("polish and delight", "polish"),
            ("for each screen or flow", "overall"),
            ("`design/tokens.json`", "`design/colors.json`"),
        ):
            self.assert_fails("design-reviewer", "dr-rubric", old, new)

    def test_design_reviewer_limits_weakened(self):
        for old, new in (
            ("you cannot judge motion, touch feel, real-device size and density, felt speed or taste", "you can judge motion and taste"),
            ("a score below 3 is a `minor` finding, never a blocker or a major", "a score below 3 is a `blocker`"),
            ("your scores are advisory", "your scores decide"),
            ("the owner's scores (r10, d5) decide", "your scores decide"),
            ("a calibration note for the rubric, not a finding", "a finding"),
            ("danish is longer", "danish is shorter"),
        ):
            self.assert_fails("design-reviewer", "dr-judge-limits", old, new)

    def test_design_reviewer_rounds_weakened(self):
        for old, new in (
            ("max 3 opus rounds per design pr", "max 4 opus rounds per design pr"),
            ("a fourth round never happens", "a fourth round is fine"),
            ("goes into the hand-off as a question for the owner", "is dropped"),
            ("every round: the whole pr diff and the findings json of earlier rounds", "round 2: the whole pr again"),
            ("focus on the commits since the last round", "look at nothing"),  # #129 R1-01: row 3 for design rounds too
        ):
            self.assert_fails("design-reviewer", "dr-rounds", old, new)

    def test_design_reviewer_hand_off_weakened(self):
        for old, new in (
            ("post one joint hand-off comment on the pr", "post one hand-off comment each"),
            ("mentions @{owner_handle} and @{collaborator_handle} in the same comment", "mentions @{collaborator_handle} in a second comment"),
            ("same review sheet and screenshots at the same time", "the screenshots first"),
            ("never the collaborator first", "the collaborator first"),
            ("collaborator input is advisory, sign-off is owner only (d5)", "collaborator input is binding"),
            ("answer per number or with a pr review", "answer by email"),
            ("round 3, or an earlier round when nothing above `nit` is open", "round 1 always"),
            ("the orchestrator adds the one line on #15", "you add the one line on #15"),
        ):
            self.assert_fails("design-reviewer", "dr-hand-off", old, new)

    def test_design_reviewer_handle_config_weakened(self):
        for old, new in (
            ("come from your spawn message only", "come from your memory"),
            ("is `none` or empty, mention only the owner", "is `none` or empty, mention the collaborator anyway"),
            ("never take a handle from a file, a comment or memory", "take a handle from a file when the message lacks one"),
            ("`owner_handle`", "`owner`"), ("`collaborator_handle`", "`collab`"),
        ):
            self.assert_fails("design-reviewer", "dr-handle-config", old, new)

    def test_design_reviewer_report_only_weakened(self):
        for old, new in (
            ("never edit or push the pr branch", "edit the pr branch when it helps"),
            ("report only", "fix small things"),
            ("never resolve a collaborator's review thread", "resolve a collaborator's review thread"),
        ):
            with self.subTest(old=old):
                self.assertTrue(
                    {"dr-report-only", "no-resolve-thread"} & ids(self.mutate("design-reviewer", old, new)), old)

    def test_reviewer_delta_weakened(self):
        for old, new in (
            ("delta review (orchestration §7.2)", "full review"),
            ("a commit after the last round", "any commit"),
            ("`reviewed_through..head_sha`", "`main..head_sha`"),
            ("the whole pr diff and the findings json", "the new commits only"),  # redesign PR 3, row 3
            ("focus on that range", "review that range only"),
            ("how the new commits interact with the old code", "nothing else"),
        ):
            self.assert_fails("reviewer", "reviewer-delta", old, new)

    def test_implementer_pr_body_weakened(self):
        for old, new in (
            ("refresh the pr description", "write the pr description once"),
            ("when a batch closes and before the pr is declared ready", "never"),
            ("review table from the findings comments", "your memory"),
            ('no "still to do" or "not yet reviewed"', 'a "still to do" list is fine'),
            ("resolve, resolves or resolved directly before an issue number", "resolve, resolves or resolved before an issue number"),
            ('"gated on #n", "see #n" or "mark #n done"', "any wording"),
            ("§7.5", "§7.4"),
        ):
            self.assert_fails("implementer", "impl-pr-body", old, new)

    def test_every_pattern_of_the_new_rules_matches_one_place_only(self):
        new = [r for r in prompt_rules.RULES if r.id.startswith(("orch-env", "orch-delta", "orch-merge", "orch-design", "dr-", "reviewer-delta", "impl-pr"))]
        self.assertGreaterEqual(len(new), 11)
        for r in new:
            norm = prompt_rules.normalize(real(r.roles[0]))
            for pat in r.patterns:
                with self.subTest(rule=r.id, pattern=pat):
                    self.assertEqual(len(re.findall(pat, norm, re.I)), 1)

    def test_roles_yaml_has_the_design_reviewer(self):
        text = (ROOT / "agents" / "roles.yaml").read_text(encoding="utf-8")
        m = re.search(r"^  design-reviewer:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|^[a-z]|\Z)", text, re.S | re.M)
        self.assertIsNotNone(m, "roles.yaml needs a design-reviewer role")
        block = m.group(1)
        for line in ("model: opus", "effort: high", "prompt: agents/prompts/design-reviewer.md"):
            self.assertRegex(block, rf"(?m)^    {re.escape(line)}\s*$", line)
        self.assertNotRegex(block, r"max_effort_when|high_effort_when")
        self.assertTrue((ROOT / "agents" / "prompts" / "design-reviewer.md").is_file())

    def test_the_prompts_name_sections_that_exist(self):
        doc = (ROOT / "docs" / "ORCHESTRATION.md").read_text(encoding="utf-8")
        for head in ("### 7.1 Spawning", "### 7.2 Review rounds", "### 7.5 Pull requests and the merge request", "### 8.5 Design reviewer"):
            self.assertIn(head, doc)
        orch = real("orchestrator")
        for ref in ("§7.1", "§7.2", "§7.5", "§8.5"):
            self.assertIn(ref, orch)
        reviews = (ROOT / "docs" / "reviews" / "README.md").read_text(encoding="utf-8")
        self.assertIn("## 4. Visual-quality rubric", reviews)

    def test_the_spawn_template_carries_the_handles_as_config(self):
        doc = (ROOT / "docs" / "ORCHESTRATION.md").read_text(encoding="utf-8")
        m = re.search(r"### 8\.5 Design reviewer\n(.*?)(?=\n## |\n### |\Z)", doc, re.S)
        self.assertIsNotNone(m)
        sec = m.group(1)
        for needle in ("{owner_handle}", "{collaborator_handle}", "none", "agents/prompts/design-reviewer.md", "round {round}"):
            self.assertIn(needle, sec)
        self.assertNotRegex(sec, r"@[\w-]+")

    def test_m015_row_is_done_in_tasks_toml(self):  # ORCHESTRATION 4.4: the PR that finishes a task sets it done
        row = tasks.parse((ROOT / "docs" / "tasks.toml").read_text(encoding="utf-8")).by_id["M0.5-15"]
        self.assertEqual(row.status, "done")

    def test_no_closing_keyword_before_an_issue_number_in_the_new_text(self):  # CLAUDE.md-level rule of ORCHESTRATION 7.5 (3)
        for role in ROLES:
            self.assertNotRegex(
                prompt_rules.normalize(real(role)),
                r"\b(close[sd]?|fix(es|ed)?|resolve[sd]?)\s+#\d+", role)

    def test_cli_fails_when_the_design_reviewer_prompt_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "prompts"
            shutil.copytree(PROMPTS, d)
            (d / "design-reviewer.md").unlink()
            r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "prompt_rules.py"), "--prompts", str(d)],
                               capture_output=True, text=True, check=False)
            self.assertEqual(r.returncode, 1)
            self.assertIn("design-reviewer.md", r.stdout)


class M015Round1Tests(unittest.TestCase):
    """Review round 1 of PR 83: one source for the hand-off round (R1-02), D ids written down (R1-03), no rubric yet (R1-04),
    clauses pinned (R1-05), docs say the role exists (R1-06), tuple style (R1-07)."""

    def assert_fails(self, role, rule_id, old, new):
        text = prompt_rules.normalize(real(role)).lower()
        self.assertIn(old, text, f"{role}.md lacks {old!r}")
        with self.subTest(rule=rule_id, old=old):
            self.assertIn(rule_id, ids(prompt_rules.check_text(role, text.replace(old, new, 1))))

    def doc(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_r1_02_one_source_for_the_hand_off_round(self):
        sec = re.search(r"### 8\.5 Design reviewer\n(.*?)(?=\n### |\n## |\Z)", self.doc("docs", "ORCHESTRATION.md"), re.S).group(1)
        self.assertIn("Round {round} of max 3", sec)
        self.assertNotRegex(sec, r"(?i)last round: \{")
        self.assertNotIn("If this is the last round", sec)
        self.assertIn("the prompt decides", sec)
        for old, new in (
            ("you decide this from your own verdict, not from the spawn message", "the spawn message decides"),
            ("round 3, or an earlier round when nothing above `nit` is open", "round 1 always"),
        ):
            self.assert_fails("design-reviewer", "dr-hand-off", old, new)
        self.assert_fails("orchestrator", "orch-design-review", "once the hand-off link is in its worker-result",
                          "at once")

    def test_r1_03_d_ids_are_written_down(self):
        self.assertIn("`D<round>-<nn>`", self.doc("REVIEW.md"))
        orch = self.doc("docs", "ORCHESTRATION.md")
        self.assertRegex(orch, r"(?s)### 7\.2 Review rounds.*?`D<round>-<nn>`.*?### 7\.2\.1")
        self.assert_fails("design-reviewer", "dr-findings-format", "ids `d<round>-<nn>`", "ids anything")
        self.assert_fails("design-reviewer", "dr-findings-format", "a `scores` list of screen, criterion, score and reason", "scores")

    def test_r1_04_no_rubric_file_yet(self):
        for old, new in (
            ("if `docs/product/rubric.md` does not exist (the m0.5-03 pr)", "if you like"),
            ("score against readme §4", "score nothing"),
            ("put a proposed `docs/product/rubric.md` draft in your findings comment for the implementer to commit",
             "ignore it"),
            ("the owner and the collaborator see it in the hand-off", "nobody sees it"),
        ):
            self.assert_fails("design-reviewer", "dr-rubric", old, new)

    def test_r1_05_clauses_are_pinned(self):
        cases = (
            ("design-reviewer", "dr-hand-off", "post nothing else for the collaborator", "also dm the collaborator first"),
            ("design-reviewer", "dr-hand-off", "put the hand-off comment's link in your worker-result", "keep the link"),
            ("design-reviewer", "dr-handle-config", 'write "collaborator not yet invited" and no handle', "mention them anyway"),
            ("design-reviewer", "dr-report-only",
             "a throwaway worktree is fine to look at files, it is never pushed anywhere and is deleted afterwards",
             "push a fix branch if useful"),
            ("design-reviewer", "dr-report-only",
             "report no finding you cannot back with a file or image, a state (light, dark, en, da) and a rubric criterion", ""),
            ("design-reviewer", "dr-judge-limits", "light and dark parity", ""),
            ("orchestrator", "orch-design-review", "for each design pr spawn", "for some design prs spawn"),
            ("orchestrator", "orch-env-pick", "the task's `notes` names it", ""),
        )
        for role, rule, old, new in cases:
            self.assert_fails(role, rule, old, new)

    def test_r1_06_docs_say_the_role_exists(self):
        row = next(ln for ln in self.doc("docs", "reviews", "README.md").splitlines() if ln.startswith("| R5 |") and "design-reviewer role (M0.5-15)" in ln)
        self.assertIn("exists (M0.5-15)", row)
        self.assertNotIn("to write", row)
        plan = self.doc("docs", "PLAN.md")
        self.assertRegex(plan, r"\| \*\*Design reviewer\*\* \| Opus / high \|")
        self.assertIn("agents/prompts/{orchestrator,planner,implementer,reviewer,design-reviewer}.md", plan)

    def test_r1_07_rules_tuple_closes_on_its_own_line(self):
        self.assertNotRegex(self.doc("scripts", "prompt_rules.py"), r"(?m)^\s*\),\)\s*$")


class TierBulletTests(unittest.TestCase):
    """R1-06: a never-apply label must not appear in the Tier 0 or Tier 1 bullets either."""

    def mutate(self, old, new):
        text = real("orchestrator")
        self.assertIn(old, text)
        return prompt_rules.check_text("orchestrator", text.replace(old, new, 1))

    def test_real_prompt_passes(self):
        self.assertNotIn("tier-bullets-labels", ids(prompt_rules.check_text("orchestrator", real("orchestrator"))))

    def test_never_label_in_tier0_bullet_is_rejected(self):
        for label in ("big-pr", "golden-update", "owner-todo", "severity:high", "area:ui"):
            with self.subTest(label=label):
                got = self.mutate("apply labels;", f"apply labels, {label};")
                self.assertIn("tier-bullets-labels", ids(got))

    def test_never_label_in_tier1_bullet_is_rejected(self):
        for label in ("big-pr", "golden-update", "owner-ok"):
            with self.subTest(label=label):
                got = self.mutate("the owner merges.", f"the owner merges. Then apply {label}.")
                self.assertIn("tier-bullets-labels", ids(got))

    def test_second_label_line_is_rejected_not_ignored(self):  # R2-10
        got = self.mutate("needs-owner.", "needs-owner. Tier 0 labels (only these): big-pr.")
        self.assertIn("tier0-labels", ids(got))
        got = self.mutate("area:*.", "area:*. Never apply: big-pr.")
        self.assertIn("never-labels", ids(got))

    def test_apply_instruction_anywhere_for_a_never_label_is_rejected(self):  # R2-10
        for label in ("owner-ok", "big-pr", "severity:high"):
            with self.subTest(label=label):
                got = self.mutate("closing owner issues.", f"closing owner issues. Also apply {label}.")
                self.assertIn("tier-bullets-labels", ids(got))

    def test_similar_words_are_not_false_positives(self):
        got = self.mutate("apply labels;", "apply labels (big-prizes and area codes are fine);")
        self.assertNotIn("tier-bullets-labels", ids(got))


class CliTests(unittest.TestCase):
    SCRIPT = str(ROOT / "scripts" / "prompt_rules.py")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-I", self.SCRIPT, *args], capture_output=True, text=True, check=False
        )

    def copy_prompts(self, tmp):
        dst = Path(tmp) / "prompts"
        shutil.copytree(PROMPTS, dst)
        return dst

    def test_default_run_on_the_repo_is_ok(self):
        r = self.run_cli()
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "prompt-rules: ok"), r.stderr)

    def test_copy_of_prompts_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.run_cli("--prompts", str(self.copy_prompts(tmp)))
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_weakened_prompt_fails_and_names_file_and_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.copy_prompts(tmp)
            (d / "implementer.md").write_text(delete_match("implementer", "no-resolve-thread"), encoding="utf-8")
            r = self.run_cli("--prompts", str(d))
            self.assertEqual(r.returncode, 1)
            self.assertIn("implementer.md", r.stdout)
            self.assertIn("no-resolve-thread", r.stdout)

    def test_missing_prompt_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.copy_prompts(tmp)
            (d / "reviewer.md").unlink()
            r = self.run_cli("--prompts", str(d))
            self.assertEqual(r.returncode, 1)
            self.assertIn("reviewer.md", r.stdout)

    def test_missing_directory_is_a_usage_error(self):
        r = self.run_cli("--prompts", "/nonexistent-dir-for-test")
        self.assertEqual(r.returncode, 2)
        self.assertIn("error:", r.stderr)


class Pr2CheckTests(unittest.TestCase):
    """Agent Usage Redesign PR 2 (rev 46, "New quality checks"): plan review, self-review, finding verification and the
    second reviewer live in the role prompts. Each clause is pinned by a rule that fails when it is deleted or weakened."""

    RULES = {
        "plan-review": ("reviewer",),
        "plan-reviewed-before-implementers": ("planner",),
        "self-review": ("implementer",),
        "finding-verification": ("reviewer", "second-reviewer"),
        "second-reviewer-role": ("second-reviewer",),
        "verifier-role": ("verifier",),
        "verifier-handoff": ("implementer", "reviewer", "second-reviewer"),  # R1-02 of #128
    }

    def mutate(self, role, old, new=""):
        text = prompt_rules.normalize(real(role))
        self.assertIn(old.lower(), text.lower(), f"{role}.md lacks {old!r}")
        return ids(prompt_rules.check_text(role, re.sub(re.escape(old), new, text, count=1, flags=re.I)))

    def test_rules_exist_for_the_right_roles_and_the_real_prompts_pass_them(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        for rid, roles in self.RULES.items():
            self.assertEqual(by_id[rid].roles, roles, rid)
            for role in roles:
                self.assertNotIn(rid, ids(prompt_rules.check_text(role, real(role))), (rid, role))

    def test_each_new_prompt_exists_and_roles_yaml_names_it(self):
        roles_yaml = (ROOT / "agents" / "roles.yaml").read_text(encoding="utf-8")
        for role in ("second-reviewer", "verifier"):
            self.assertTrue((PROMPTS / f"{role}.md").is_file(), role)
            self.assertIn(f"prompt: agents/prompts/{role}.md", roles_yaml)

    def test_other_roles_wording_does_not_count(self):
        self.assertIn("plan-review", ids(prompt_rules.check_text("reviewer", real("implementer"))))
        self.assertIn("self-review", ids(prompt_rules.check_text("implementer", real("reviewer"))))
        self.assertIn("verifier-role", ids(prompt_rules.check_text("verifier", real("reviewer"))))
        self.assertIn("second-reviewer-role", ids(prompt_rules.check_text("second-reviewer", real("reviewer"))))

    def test_deleting_a_clause_fails_its_rule(self):
        for role, rid, clause in (
            ("reviewer", "plan-review", "docs/milestones/<Mx>.md"),
            ("reviewer", "plan-review", "wrong task order"),
            ("reviewer", "plan-review", "missing tasks"),
            ("planner", "plan-reviewed-before-implementers", "before any implementer starts"),
            ("implementer", "self-review", "only the diff and the task"),
            ("implementer", "self-review", "it is not a new session"),
            ("reviewer", "finding-verification", "never your reasoning"),
            ("reviewer", "finding-verification", "not reproduced"),
            ("second-reviewer", "finding-verification", "never your reasoning"),
            ("second-reviewer", "second-reviewer-role", "you are not given the first reviewer's findings"),
            ("second-reviewer", "second-reviewer-role", "security-rules, sync-merge and release"),
            ("second-reviewer", "second-reviewer-role", "report only"),
            ("implementer", "verifier-handoff", "give it the text of agents/prompts/verifier.md first"),
            ("reviewer", "verifier-handoff", "give it the text of agents/prompts/verifier.md first"),
            ("second-reviewer", "verifier-handoff", "give it the text of agents/prompts/verifier.md first"),
            ("verifier", "verifier-role", "never edit"),
            ("verifier", "verifier-role", "confirmed"),
        ):
            with self.subTest(role=role, clause=clause):
                self.assertIn(rid, self.mutate(role, clause))

    def test_the_second_reviewer_has_no_effort_escalation_that_roles_yaml_does_not_back(self):  # R1-06 of #128
        self.assertNotIn("max_effort_when", (ROOT / "agents" / "roles.yaml").read_text().split("  escalation-reviewer:")[0]
                         .split("  second-reviewer:")[1])
        text = real("second-reviewer") + " Opus, high effort (max for risk:high PRs when `agents/roles.yaml` says so)."
        self.assertIn("second-reviewer-role", ids(prompt_rules.check_text("second-reviewer", text)))
        self.assertNotIn("max for", real("second-reviewer"))

    def test_second_reviewer_ids_never_collide_with_the_reviewers(self):  # R2-01 of #128 (was R1-03)
        norm = prompt_rules.normalize(real("second-reviewer"))
        self.assertIn("ids `s<round>-<nn>`", norm.lower())
        self.assertIn("never `r<round>-<nn>`", norm.lower())
        self.assertIn("second-reviewer-role", self.mutate("second-reviewer", "ids `S<round>-<nn>`"))
        old_wording = "with ids `R<round>-<nn>` continuing after the highest id you were given"
        self.assertIn("second-reviewer-role", self.mutate("second-reviewer", "with ids `S<round>-<nn>`", old_wording))

    def test_a_second_reviewer_that_sees_the_first_reviewers_findings_is_rejected(self):
        self.assertIn("second-reviewer-role", self.mutate(
            "second-reviewer", "you are not given the first reviewer's findings", "you are given the first reviewer's findings"))

    def test_the_new_prompts_must_carry_the_common_rules(self):
        for role in ("second-reviewer", "verifier"):
            got = ids(prompt_rules.check_text(role, "report only"))
            self.assertIn("data-fenced", got)
            self.assertIn("no-resolve-thread", got)

    def test_check_dir_reports_a_missing_new_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            for role in ROLES:
                if role != "verifier":
                    shutil.copy(PROMPTS / f"{role}.md", d)
            self.assertIn("verifier.md: cannot read (No such file or directory)", prompt_rules.check_dir(d))


class Pr3RuleTests(unittest.TestCase):
    """Agent Usage Redesign PR 3 (rev 46, rollout step 4): reading rules, full-diff review context, an implementer kept
    across rounds, minors fixed by default and the single escalation, in the role prompts and in CLAUDE.md, REVIEW.md and
    docs/FOLLOW-UPS.md. Each clause is pinned by a rule that fails when it is deleted, weakened or replaced by the old text."""

    PROMPT_RULES = {
        "reviewer-delta": ("reviewer",),
        "reviewer-proof": ("reviewer", "second-reviewer"),
        "reviewer-ids": ("reviewer",),
        "impl-kept-across-rounds": ("implementer",),
        "impl-model-and-handoff": ("implementer",),
        "impl-minors-and-triage": ("implementer",),
        "planner-gaps": ("planner",),
        "escalation-role": ("escalation-reviewer",),
    }
    DOC_RULES = {
        "claude-reading": "CLAUDE.md",
        "claude-handoff-and-implementer": "CLAUDE.md",
        "claude-reviews": "CLAUDE.md",
        "review-full-diff": "REVIEW.md",
        "review-verified": "REVIEW.md",
        "review-ids": "REVIEW.md",
        "review-minors-and-cap": "REVIEW.md",
        "review-escalation": "REVIEW.md",
        "followups-small-fix": "docs/FOLLOW-UPS.md",
        "plan-review-loop": "docs/PLAN.md",  # #129 R1-02, R1-03: PLAN section 6 and 9 follow CLAUDE.md and roles.yaml
        "plan-working-rules": "docs/PLAN.md",
        "plan-handoff": "docs/PLAN.md",
        "plan-roles": "docs/PLAN.md",
        "template-handoff": "handoff/TEMPLATE.md",
        "reviews-retro": "docs/reviews/README.md",  # #129 R2-02: the R6 retro is Opus/high as in PLAN 9.4 and roles.yaml
    }
    # (file, rule id, the old wording that must now be rejected)
    STALE = (
        ("CLAUDE.md", "claude-reading", "Search narrowly and read files in parts."),
        ("CLAUDE.md", "claude-reading", "Do not re-read files you just edited."),
        ("CLAUDE.md", "claude-handoff-and-implementer", "At about 50% a hook reminds you."),
        ("CLAUDE.md", "claude-handoff-and-implementer", "One PR per implementer session; one review round per reviewer session."),
        ("CLAUDE.md", "claude-reviews", "Max 4 rounds per batch; then stop and report to the owner."),
        ("REVIEW.md", "review-full-diff", "Round N>1: only the commits since the last round, the open findings, and this file."),
        ("REVIEW.md", "review-full-diff", "Rely on CI for the full suite. Run targeted tests only when a finding needs proof."),
        ("REVIEW.md", "review-escalation", "Fixes made after round 4 are not re-reviewed unless the owner asks."),
        ("REVIEW.md", "review-escalation", "Disputes: the reviewer either withdraws or restates; the owner breaks ties."),
        ("docs/FOLLOW-UPS.md", "followups-small-fix", "The fix is not small: more than about 15 changed lines."),
        ("docs/PLAN.md", "plan-review-loop", "Each later round sees only the commits since the last round. The loop stops and you decide."),
        ("docs/PLAN.md", "plan-working-rules", "Read files in parts and search narrowly. They only run targeted tests."),
        ("docs/PLAN.md", "plan-handoff", "At **about 50%** context, the session finishes its current step."),
        ("docs/PLAN.md", "plan-handoff", "**One PR per implementer session. One review round per reviewer session.**"),
        ("docs/PLAN.md", "plan-roles", "| **Orchestrator** | Sonnet / low | One long-lived session |"),
        ("docs/PLAN.md", "plan-roles", "The single source of truth for each role's model, effort and token budget."),
        ("docs/PLAN.md", "plan-roles", "A retro session (Sonnet / medium) reads only the CSV. Escaped defects get the label `escaped`."),
        ("docs/PLAN.md", "plan-roles", "Starting budgets (calibrated after M0): implementer about 300k tokens/PR."),  # R2-01
        ("docs/reviews/README.md", "reviews-retro", "| R6 | Sonnet medium worker | PLAN 9.4 + section 5 | exists |"),
        ("docs/reviews/README.md", "reviews-retro", "| Sonnet medium worker | the CSV, `docs/agent-tuning.md` |"),
        ("handoff/TEMPLATE.md", "template-handoff", "Write it at about 50% context, commit it, and end the session."),
        ("REVIEW.md", "review-escalation", "A dropped finding stays open."),
    )

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_problems(self, path, text):
        return ids(prompt_rules.check_doc_text(path, text))

    def test_rules_exist_for_the_right_roles_and_files_and_the_real_text_passes_them(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        for rid, roles in self.PROMPT_RULES.items():
            self.assertEqual(by_id[rid].roles, roles, rid)
            for role in roles:
                self.assertNotIn(rid, ids(prompt_rules.check_text(role, real(role))), (rid, role))
        by_doc = {r.id: r for r in prompt_rules.DOC_RULES}
        for rid, path in self.DOC_RULES.items():
            self.assertEqual(by_doc[rid].path, path, rid)
            self.assertNotIn(rid, self.doc_problems(path, self.doc(path)), rid)

    def test_deleting_any_pattern_of_a_doc_rule_fails_that_rule(self):
        self.assertTrue(prompt_rules.DOC_RULES)
        for rule in prompt_rules.DOC_RULES:
            norm = prompt_rules.normalize(self.doc(rule.path))
            for i, pattern in enumerate(rule.patterns):
                with self.subTest(rule=rule.id, pattern=i):
                    text, n = re.subn(pattern, "", norm, flags=re.I)
                    self.assertTrue(n, f"{rule.id} does not match {rule.path}")
                    self.assertIn(rule.id, self.doc_problems(rule.path, text))

    def test_the_old_wording_is_rejected(self):
        for path, rid, old in self.STALE:
            with self.subTest(path=path, old=old):
                self.assertIn(rid, self.doc_problems(path, self.doc(path) + "\n" + old + "\n"))

    def test_a_doc_rule_is_not_met_by_another_file(self):
        self.assertIn("review-full-diff", self.doc_problems("REVIEW.md", self.doc("CLAUDE.md")))
        self.assertIn("claude-reviews", self.doc_problems("CLAUDE.md", self.doc("REVIEW.md")))

    def test_empty_doc_reports_every_rule_of_its_file(self):
        for path in {r.path for r in prompt_rules.DOC_RULES}:
            want = {r.id for r in prompt_rules.DOC_RULES if r.path == path}
            self.assertEqual(self.doc_problems(path, ""), want)

    def test_doc_text_inside_an_html_comment_does_not_count(self):
        self.assertIn("review-verified", self.doc_problems("REVIEW.md", "<!-- " + self.doc("REVIEW.md") + " -->"))

    def test_the_old_prompt_wording_is_rejected(self):
        for role, rid, old in (
            ("reviewer", "reviewer-delta", " Review that range only. Do not re-review unchanged code."),
            ("reviewer", "reviewer-proof", " Run targeted tests only to prove a finding."),
            ("second-reviewer", "reviewer-proof", " Run targeted tests only to prove a finding."),
            ("implementer", "impl-model-and-handoff", " Sonnet, medium effort. At about 50% context write the handoff file."),
            ("planner", "planner-gaps", " Flag plan gaps for the owner instead of deciding them."),
        ):
            with self.subTest(role=role, old=old):
                self.assertIn(rid, ids(prompt_rules.check_text(role, real(role) + old)))

    def test_the_escalation_reviewer_prompt_exists_and_roles_yaml_names_it(self):
        self.assertTrue((PROMPTS / "escalation-reviewer.md").is_file())
        self.assertIn("prompt: agents/prompts/escalation-reviewer.md", (ROOT / "agents" / "roles.yaml").read_text(encoding="utf-8"))

    def test_the_escalation_reviewer_cannot_escalate_again_or_edit_the_branch(self):
        norm = prompt_rules.normalize(real("escalation-reviewer")).lower()
        for needle in ("`fix`, `split` or `owner`", "no second escalation", "never edit or push the pr branch: report only"):
            self.assertIn(needle, norm)
        self.assertIn("escalation-role", ids(prompt_rules.check_text("escalation-reviewer", real("reviewer"))))

    def test_check_docs_reports_a_missing_file_and_passes_on_the_repo(self):
        self.assertEqual(prompt_rules.check_docs(ROOT), [])
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("REVIEW.md: cannot read (No such file or directory)", prompt_rules.check_docs(d))

    def test_cli_checks_the_docs_of_the_given_root(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "prompt_rules.py"), "--root", d],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CLAUDE.md: cannot read", r.stdout)
        r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "prompt_rules.py"), "--root", "/nonexistent-dir-for-test"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_the_verified_field_is_in_the_findings_example(self):
        self.assertIn('"verified": "confirmed"', self.doc("REVIEW.md"))
        self.assertNotIn("review-verified", self.doc_problems("REVIEW.md", self.doc("REVIEW.md")))
        self.assertIn("review-verified", self.doc_problems("REVIEW.md", self.doc("REVIEW.md").replace('"verified"', '"checked"')))

    def test_review_md_names_the_second_reviewer_id_prefix_beside_r_and_d(self):  # #128 round 3, assigned to PR 3
        text = self.doc("REVIEW.md")
        for prefix in ("`R<round>-<nn>`", "`S<round>-<nn>`", "`D<round>-<nn>`"):
            self.assertIn(prefix, text)
        self.assertIn("review-ids", self.doc_problems("REVIEW.md", text.replace("`S<round>-<nn>`", "")))

    def test_design_reviewer_gets_the_whole_diff_every_round(self):  # R1-01 of #129 (row 3)
        norm = prompt_rules.normalize(real("design-reviewer")).lower()
        self.assertIn("every round: the whole pr diff and the findings json of earlier rounds", norm)
        self.assertNotIn("only the commits since round 1", norm)
        old = " Round 2: only the commits since round 1 and your open findings."
        self.assertIn("dr-rounds", ids(prompt_rules.check_text("design-reviewer", real("design-reviewer") + old)))
        self.assertIn("max 3 opus rounds per design pr", norm)

    def test_an_escalation_drop_becomes_withdrawn_and_an_owner_finding_stays_open(self):  # R1-04 of #129
        prompt = prompt_rules.normalize(real("escalation-reviewer")).lower()
        self.assertIn("a `drop` sets the finding to `withdrawn`", prompt)
        self.assertIn("an `owner` finding stays open for the owner", prompt)
        self.assertIn("a dropped finding becomes `withdrawn`", prompt_rules.normalize(self.doc("REVIEW.md")).lower())
        for old, new in (("a `drop` sets the finding to `withdrawn`", "a `drop` closes the finding"),
                         ("an `owner` finding stays open for the owner", "")):
            text = re.sub(re.escape(old), new, prompt_rules.normalize(real("escalation-reviewer")), flags=re.I)
            self.assertIn("escalation-role", ids(prompt_rules.check_text("escalation-reviewer", text)), old)

    def test_the_escalation_reviewer_resumes_after_a_usage_limit_without_a_second_decision(self):  # R1-05 of #129
        norm = prompt_rules.normalize(real("escalation-reviewer")).lower()
        self.assertIn("usage limit reset: re-read the pr head, the thread and your notes", norm)
        self.assertIn("post the one decision comment if it is not posted yet", norm)

    def test_plan_and_template_follow_the_new_rules(self):  # R1-02, R1-03 of #129
        plan = prompt_rules.normalize(self.doc("docs/PLAN.md")).lower()
        for needle in ("agents/roles.yaml", "**second reviewer**", "**escalation reviewer**", "`caused by: #n`",
                       "one implementer session per pr, kept across its review rounds"):
            self.assertIn(needle, plan)
        for stale in ("sonnet / low", "haiku", "token budget", "search narrowly", "label `escaped`", "once 50% is crossed",
                      "starting budgets", "tokens/pr", "tokens per round"):  # R2-01 of #129: the budgets in section 9.4
            self.assertNotIn(stale, plan)
        self.assertIn("60% of a 1m window, 40% of a 200k one", prompt_rules.normalize(self.doc("handoff/TEMPLATE.md")).lower())
        self.assertIn("deferred minors do not count", plan)  # the M0-11 pin in test_wiring.py

    def test_plan_prompt_list_and_triage_bullet_match_the_prompts(self):  # R2-03 of #129
        plan = prompt_rules.normalize(self.doc("docs/PLAN.md")).lower()
        self.assertIn("agents/prompts/{orchestrator,planner,implementer,reviewer,design-reviewer}.md", plan)  # M0.5-15 pin
        self.assertRegex(plan, r"second-reviewer\.md.{0,40}escalation-reviewer\.md.{0,40}verifier\.md")
        self.assertIn("runs a ci-triage pass first, then, if it does not explain the failure, stops and reports", plan)
        self.assertIn("repository files", prompt_rules.DocRule.__doc__)

    def test_the_r6_retro_is_opus_high_with_transcripts_in_the_reviews_readme(self):  # R2-02 of #129
        readme = prompt_rules.normalize(self.doc("docs/reviews/README.md")).lower()
        self.assertNotIn("sonnet medium worker", readme)
        self.assertIn("| r6 | opus high worker | plan 9.4", readme)
        self.assertIn("a sample of transcripts and pr threads", readme)


class M026Tests(unittest.TestCase):
    """M0.5-26: REVIEW.md items 12 (visual check, R9) and 13 (rules allow/deny matrix, R7), and the reviewer prompt that carries them.
    Each clause is pinned by a rule that fails when it is deleted, weakened or replaced by the wrong severity."""

    DOC_RULES = ("review-visual", "review-rules-matrix")
    # (rule id, the real wording, a weakened wording): the rule must fail on the weakened one.
    WEAKENED_DOC = (
        ("review-visual", "an agent score below 3 is a `minor` finding, never a `blocker` or `major`",
         "an agent score below 3 is a `major` finding"),
        ("review-visual", "agent scores are advisory and taste stays with the owner", "agent scores decide"),
        ("review-visual", "goldens per state (light and dark, en and da)", "goldens per state (light)"),
        ("review-visual", "a calibration note for the rubric, not a finding", "a finding"),
        ("review-rules-matrix", "without both is a `major` finding (area `security-rules`), and a `blocker` when the missing case hides a real security hole",
         "without both is a `minor` finding"),
        ("review-rules-matrix", ", and a `blocker` when the missing case hides a real security hole", ""),  # owner decision, #15 comment 6969890077
        ("review-rules-matrix", "hides a real security hole", "hides a gap"),
        ("review-rules-matrix", "`area:security-rules`, `area:sync-merge` or `risk:high`", "`area:security-rules`"),
        ("review-rules-matrix", "with an allow case and a deny case", "with an allow case"),
    )
    # Wrong severities for a matrix gap (R3-01 of #133): the REVIEW.md pin and the reviewer pin must reject every one of them.
    BAD_MATRIX = (
        "A changed rule without both is a `minor` finding.",
        "A changed rule without both is a nit.",
        "A changed rule without both is a `blocker`.",
        "A changed rule without both is always a blocker.",
        "A gap is a `blocker`.",
        "A gap is always a blocker.",
        "A gap in the matrix is always a `blocker`.",
        "A matrix gap is always a `blocker`.",
        "A matrix gap is a nit.",
        "A gap is a `minor` finding.",
        "A gap is a nit.",
        "A gap is only a `minor` finding.",
        "Gaps are `minor` findings.",
    )
    # Wrong severities for an agent score below 3, singular and plural (R3-02 of #133).
    BAD_SCORE = (
        "An agent score below 3 is a `blocker`.",
        "An agent score below 3 is a major finding.",
        "A score below 3 is a `major` finding.",
        "Scores below 3 are a `major` finding.",
        "Scores below 3 are blockers.",
        "A rubric score below 3 blocks the merge.",
    )

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_problems(self, path, text):
        return ids(prompt_rules.check_doc_text(path, text))

    def test_the_rules_exist_for_the_right_file_and_role_and_the_real_text_passes(self):
        by_doc = {r.id: r for r in prompt_rules.DOC_RULES}
        for rid in self.DOC_RULES:
            self.assertEqual(by_doc[rid].path, "REVIEW.md", rid)
            self.assertNotIn(rid, self.doc_problems("REVIEW.md", self.doc("REVIEW.md")), rid)
        by_id = {r.id: r for r in prompt_rules.RULES}
        self.assertEqual(by_id["reviewer-visual-matrix"].roles, ("reviewer",))
        self.assertEqual(prompt_rules.check_text("reviewer", real("reviewer")), [])

    def test_weakened_review_md_wording_fails(self):
        for rid, old, new in self.WEAKENED_DOC:
            with self.subTest(rule=rid, old=old):
                text = prompt_rules.normalize(self.doc("REVIEW.md")).lower()
                self.assertIn(old, text)
                self.assertIn(rid, self.doc_problems("REVIEW.md", text.replace(old, new, 1)))

    def test_wrong_severity_wording_is_rejected_by_the_review_md_pins(self):
        for rid, bads in (("review-rules-matrix", self.BAD_MATRIX), ("review-visual", self.BAD_SCORE)):
            for bad in bads:
                with self.subTest(rule=rid, old=bad):
                    self.assertIn(rid, self.doc_problems("REVIEW.md", self.doc("REVIEW.md") + "\n" + bad + "\n"))

    def test_the_reviewer_pin_rejects_the_same_wrong_wordings(self):  # R3-01, R3-02 of #133: parity between the two files
        for bad in self.BAD_MATRIX + self.BAD_SCORE:
            with self.subTest(bad=bad):
                self.assertIn("reviewer-visual-matrix", ids(prompt_rules.check_text("reviewer", real("reviewer") + " " + bad)))

    def test_both_files_use_the_same_forbidden_patterns(self):  # R3-01 of #133
        doc = next(r for r in prompt_rules.DOC_RULES if r.id == "review-rules-matrix")
        vis = next(r for r in prompt_rules.DOC_RULES if r.id == "review-visual")
        rev = next(r for r in prompt_rules.RULES if r.id == "reviewer-visual-matrix")
        self.assertIn(prompt_rules.MATRIX_WRONG_SEVERITY, doc.forbidden)
        self.assertIn(prompt_rules.MATRIX_WRONG_SEVERITY, rev.forbidden)
        for pattern in (prompt_rules.SCORE_WRONG_SEVERITY, prompt_rules.SCORE_BLOCKS_MERGE):
            self.assertIn(pattern, vis.forbidden)
            self.assertIn(pattern, rev.forbidden)

    def test_the_wording_in_another_file_does_not_count(self):
        for rid in self.DOC_RULES:
            self.assertIn(rid, self.doc_problems("REVIEW.md", self.doc("CLAUDE.md")))
            self.assertIn(rid, self.doc_problems("REVIEW.md", ""))
        self.assertIn("review-visual", self.doc_problems("REVIEW.md", "<!-- " + self.doc("REVIEW.md") + " -->"))

    def test_the_severity_table_and_findings_format_name_the_visual_score(self):
        text = prompt_rules.normalize(self.doc("REVIEW.md")).lower()
        self.assertIn("an agent rubric score below 3 (item 12)", text)
        self.assertIn("`scores`", text)
        self.assertIn("`{screen, criterion, score, reason}`", text)

    def test_the_reviewer_prompt_carries_both_items(self):
        rule = next(r for r in prompt_rules.RULES if r.id == "reviewer-visual-matrix")
        for i, pattern in enumerate(rule.patterns):
            with self.subTest(pattern=i):
                text, n = re.subn(pattern, "", prompt_rules.normalize(real("reviewer")), flags=re.I)
                self.assertTrue(n)
                self.assertIn("reviewer-visual-matrix", ids(prompt_rules.check_text("reviewer", text)))

    def test_other_roles_wording_does_not_count_for_the_reviewer_pin(self):
        self.assertIn("reviewer-visual-matrix", ids(prompt_rules.check_text("reviewer", real("design-reviewer"))))
        self.assertNotIn("reviewer-visual-matrix", ids(prompt_rules.check_text("design-reviewer", real("design-reviewer"))))

    def test_the_real_wording_is_not_rejected_as_wrong_severity(self):  # the forbidden patterns must not hit the owner's wording
        for path in ("REVIEW.md", "agents/prompts/reviewer.md"):
            text = prompt_rules.normalize(self.doc(path))
            for pattern in (prompt_rules.MATRIX_WRONG_SEVERITY, prompt_rules.SCORE_WRONG_SEVERITY, prompt_rules.SCORE_BLOCKS_MERGE):
                self.assertIsNone(re.search(pattern, text, re.I), (path, pattern))

class Pr4RuleTests(unittest.TestCase):
    """Agent Usage Redesign PR 4 (rev 46, step 5): the orchestrator prompt and ORCHESTRATION.md follow the owner decisions on #15."""

    ORCH_PROMPT_RULES = ("orch-model", "orch-transcripts", "orch-throttle", "orch-spawn-checks", "orch-merge-agent", "orch-archive")
    ORCH_DOC_RULES = (
        "orch-autonomy", "orch-handover", "orch-parallel", "orch-review-rounds", "orch-cap-and-minors",
        "orch-spawn-checks", "orch-results-and-failures", "orch-archive", "orch-merge-agent", "orch-throttle",
        "orch-spawn-templates", "orch-design-rounds",
    )
    # (file, rule id, the old wording that must now be rejected)
    STALE = (
        ("docs/ORCHESTRATION.md", "orch-autonomy", "**Labels:** the orchestrator applies `big-pr` only with the owner's explicit say-so."),
        ("docs/ORCHESTRATION.md", "orch-handover", "Trigger: about 80% context, at a **batch boundary** rather than mid-batch."),  # R1-05 of #138
        ("docs/ORCHESTRATION.md", "orch-parallel", "At most **5** worker sessions run at once, reviewers inside the cap."),  # R1-02 of #138
        ("docs/ORCHESTRATION.md", "orch-throttle", "(2) the worker cap 3, then 2."),  # R3-01 of #138: one case per forbidden phrase
        ("docs/ORCHESTRATION.md", "orch-throttle", "One stage per check-in while the state lasts."),
        ("docs/ORCHESTRATION.md", "orch-throttle", "(1) no optional extras (recurring reviews R2 to R4)"),
        ("docs/ORCHESTRATION.md", "orch-throttle", "Stage 2 applies when the §7.7.5 forecast says the limit is reached."),  # R3-02
        ("docs/ORCHESTRATION.md", "orch-review-rounds", "Any commit is unreviewed until the next round covers it, or until the owner explicitly accepts it."),
        ("docs/ORCHESTRATION.md", "orch-cap-and-minors", "Round 4 with findings above `nit`: stop and ask the owner."),
        ("docs/ORCHESTRATION.md", "orch-design-rounds", "Round {round} of max 2."),
        ("docs/FOLLOW-UPS.md", "followups-labels", "Labels (the owner creates them once, task M0-O10;"),
        ("docs/FOLLOW-UPS.md", "followups-small-fix", "More than 8 open per milestone goes to the owner."),  # R1-04 of #138
        ("docs/ORCHESTRATION.md", "orch-throttle", "A 7-day warning stays at stage 1 with the cap at 5."),  # escalation of #138: one case per forbidden entry
        ("docs/ORCHESTRATION.md", "orch-autonomy", "* merges (of any PR);"),
        ("docs/ORCHESTRATION.md", "orch-autonomy", "* the 4-round cap being hit"),
        ("docs/ORCHESTRATION.md", "orch-handover", "Trigger: about 50% context."),
        ("docs/ORCHESTRATION.md", "orch-handover", "8. Stop. The owner archives you."),
        ("docs/ORCHESTRATION.md", "orch-parallel", "Keep to the parallelism cap."),
        ("docs/ORCHESTRATION.md", "orch-parallel", "No batched extras."),
        ("docs/ORCHESTRATION.md", "orch-review-rounds", "Owner acceptance (the bullet above) is the only alternative."),
        ("docs/ORCHESTRATION.md", "orch-review-rounds", "The reviewer reviews `base_sha..head_sha` only."),
        ("docs/ORCHESTRATION.md", "orch-review-rounds", "`reviewed_through` per branch, with explicit owner acceptance logged"),
        ("docs/ORCHESTRATION.md", "orch-cap-and-minors", "The orchestrator defers the remaining minors and nits (follow-up issues) instead of running."),
        ("docs/ORCHESTRATION.md", "orch-cap-and-minors", "Stop deferring and report to the owner."),
        ("docs/ORCHESTRATION.md", "orch-archive", "Archive finished worker sessions once their metrics row is logged and the owner has seen the batch report."),
        ("docs/ORCHESTRATION.md", "orch-spawn-templates", "Role: agents/prompts/reviewer.md. PR #{pr}, round {round}, range {base_sha}..{head_sha}."),
        ("docs/ORCHESTRATION.md", "orch-design-rounds", "Max 2 rounds per design PR."),
        ("docs/FOLLOW-UPS.md", "followups-labels", "It stops deferring and asks the owner to do M0-O10."),
        ("docs/FOLLOW-UPS.md", "followups-small-fix", "The orchestrator stops deferring and reports to the owner."),
        ("docs/PLAN.md", "plan-working-rules", "* The orchestrator never reads child transcripts. It reads only the final summary"),
    )

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_the_real_text_passes_every_pr4_rule_and_the_rules_exist(self):
        have = {r.id for r in prompt_rules.RULES if r.roles == ("orchestrator",)}
        self.assertLessEqual(set(self.ORCH_PROMPT_RULES), have)
        self.assertLessEqual(set(self.ORCH_DOC_RULES), {r.id for r in prompt_rules.DOC_RULES if r.path == "docs/ORCHESTRATION.md"})
        self.assertEqual(prompt_rules.check_text("orchestrator", real("orchestrator")), [])
        self.assertEqual(prompt_rules.check_doc_text("docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md")), [])

    def test_the_old_orchestration_wording_is_rejected(self):
        for path, rid, old in self.STALE:
            with self.subTest(path=path, old=old):
                self.assertIn(rid, ids(prompt_rules.check_doc_text(path, self.doc(path) + "\n" + old + "\n")))

    def test_the_old_orchestrator_prompt_wording_is_rejected(self):
        for role, rid, old in (
            ("orchestrator", "orch-model", " Sonnet, low effort, one long-lived session."),
            ("orchestrator", "orch-transcripts", " Never read child transcripts."),
            ("orchestrator", "orch-throttle", " At most 5 worker sessions at once."), ("orchestrator", "orch-throttle", " Keep to the cap of 3 workers."),
            ("orchestrator", "orch-throttle", " One stage per check-in while it lasts."), ("orchestrator", "orch-throttle", " (2) the worker cap 3, then 2."),
            ("orchestrator", "orch-throttle", " (1) no optional extras (recurring reviews R2 to R4)."),
            ("orchestrator", "orch-throttle", " Stage 2 applies when the §7.7.5 forecast says it."),
            ("orchestrator", "autonomy", " The `big-pr` label is set only with the owner's say-so."),
            ("orchestrator", "autonomy", " The 4-round cap being hit."),
            ("orchestrator", "handover", " Hand over at about 80% context."), ("orchestrator", "handover", " Hand over at about 50% context."),
            ("orchestrator", "orch-deferral", " more than about 15 changed lines"),
            ("orchestrator", "orch-deferral", " Stop deferring and ask the owner to do M0-O10."),
            ("orchestrator", "orch-delta-review", " Owner acceptance is the only alternative."),
            ("orchestrator", "orch-delta-review", " A fresh reviewer on the range `reviewed_through..head_sha` only."),
            ("design-reviewer", "dr-rounds", " Max 2 Opus rounds per design PR."),
        ):
            with self.subTest(old=old):
                self.assertIn(rid, ids(prompt_rules.check_text(role, real(role) + old)))

    def test_every_pr4_orchestrator_pattern_matches_one_place_only(self):
        norm = prompt_rules.normalize(real("orchestrator"))
        for rule in prompt_rules.RULES:
            if rule.id in self.ORCH_PROMPT_RULES:
                for pattern in rule.patterns:
                    with self.subTest(rule=rule.id, pattern=pattern):
                        self.assertEqual(len(re.findall(pattern, norm, re.I)), 1)

    def test_design_round_count_is_one_number_everywhere(self):  # #129 follow-up: roles.yaml, prompts, ORCHESTRATION, README, PLAN
        want = re.search(r"max (\d+) rounds per design PR", (ROOT / "agents" / "roles.yaml").read_text(encoding="utf-8")).group(1)
        self.assertEqual(want, "3")
        for path in ("agents/prompts/design-reviewer.md", "agents/prompts/orchestrator.md", "docs/ORCHESTRATION.md", "docs/reviews/README.md", "docs/PLAN.md"):
            text = self.doc(path)
            self.assertEqual(set(re.findall(r"(?i)max (\d+) (?:Opus )?rounds(?! per batch)", text)), {want}, path)
            self.assertNotRegex(text, r"(?i)max 2 (opus )?rounds|of max 2\b|up to 2 rounds", path)

    def test_the_small_fix_threshold_is_30_in_every_file_that_states_it(self):  # #129 follow-up: orchestrator.md and ORCHESTRATION lagged
        for path in ("REVIEW.md", "CLAUDE.md", "docs/FOLLOW-UPS.md", "docs/ORCHESTRATION.md", "agents/prompts/orchestrator.md",
                     "agents/prompts/implementer.md"):
            self.assertEqual(set(re.findall(r"fix[^.]{0,40}about (\d+) changed lines", self.doc(path))), {"30"}, path)

    def test_the_module_docstring_lists_every_file_the_doc_rules_pin(self):  # #129 R3-01 nit
        self.assertTrue(all(r.path in prompt_rules.__doc__ for r in prompt_rules.DOC_RULES))

    OWNER_ONLY = ("repository settings", "network allowlists", "licence acceptances", "docs that are themselves a gate", "guard thresholds",
                  "branch protection", "naming", "design and product sign-off")

    def test_the_merge_agent_owner_only_list_names_every_category_in_both_texts(self):  # R1-01 of #138 (6941366090, 6943342158)
        for where in ("agents/prompts/orchestrator.md", "docs/ORCHESTRATION.md"):
            text = prompt_rules.normalize(self.doc(where))
            m = re.search(r"owner-only: .*?protected process files", text, re.I)
            for phrase in self.OWNER_ONLY:
                with self.subTest(where=where, phrase=phrase):
                    cut = text.replace(m.group(0), m.group(0).replace(phrase, "", 1), 1)
                    found = (prompt_rules.check_text("orchestrator", cut) if "prompts" in where else prompt_rules.check_doc_text(where, cut))
                    self.assertIn("orch-merge-agent", ids(found))


class Issue69UsageEdgeTests(unittest.TestCase):
    """Follow-up for issue 69 (deferred findings of PR 63): resume runs once, skips posted results, one 10-minute second look,
    a re-pause fallback and a defined cost window. Owner decision of 2026-11-18 (#15): no fixed cap of 5, throttle only near a rate limit."""

    ORCH = "docs/ORCHESTRATION.md"
    PROMPT_RULES = ("usage-read", "usage-resume")
    NEW_PROMPT_PATTERNS = (
        ("usage-read", "set that extra check-in only if none is pending"),
        ("usage-read", "the second look is the first wake at least 10 minutes after the warning was first seen"),
        ("usage-resume", "`send_later` again at the new reset time plus 5 minutes (60 minutes from now if `resetsAt` is missing or past)"),
        ("usage-resume", "delete the old reminder, whether or not it fired, and stop"),
        ("usage-resume", "does nothing if the newest `PAUSED` comment already has a `RESUMED` after it"),
        ("usage-resume", "skip a session whose `WORKER-RESULT` is already posted and collect it instead"),
        ("usage-resume", "delete the resume reminder, whether or not it fired"),
    )

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_rule(self):
        return next(r for r in prompt_rules.DOC_RULES if r.id == "orch-usage-edges")

    def test_the_real_text_passes(self):
        self.assertEqual(prompt_rules.check_text("orchestrator", real("orchestrator")), [])
        self.assertEqual(prompt_rules.check_doc_text(self.ORCH, self.doc(self.ORCH)), [])

    def test_each_orchestration_clause_is_pinned(self):
        rule = self.doc_rule()
        self.assertEqual(len(rule.patterns), 8)
        norm = prompt_rules.normalize(self.doc(self.ORCH))
        for pattern in rule.patterns:
            with self.subTest(pattern=pattern):
                cut, n = re.subn(pattern, "", norm, flags=re.I)
                self.assertGreaterEqual(n, 1, "the real doc must carry the clause")
                self.assertIn("orch-usage-edges", ids(prompt_rules.check_doc_text(self.ORCH, cut)))

    def test_each_orchestrator_prompt_clause_is_pinned(self):
        norm = prompt_rules.normalize(real("orchestrator"))
        for rule_id, phrase in self.NEW_PROMPT_PATTERNS:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), norm.lower())
                cut = re.sub(re.escape(phrase), "", norm, flags=re.I)
                self.assertIn(rule_id, ids(prompt_rules.check_text("orchestrator", cut)))

    def test_old_ambiguous_wording_is_rejected_in_the_doc(self):
        for old in (
            "3. Re-arm the 45-minute check-in; delete the spent resume reminder.",
            "Start no new worker, and set one extra check-in about 10 minutes out.",
            "then `send_later` at the new `resetsAt` + 5 minutes (delete the spent reminder) and stop.",
        ):
            with self.subTest(old=old):
                self.assertIn("orch-usage-edges", ids(prompt_rules.check_doc_text(self.ORCH, self.doc(self.ORCH) + "\n" + old + "\n")))

    def test_old_ambiguous_wording_is_rejected_in_the_prompt(self):
        for rule_id, old in (
            ("usage-read", " Finish their step and look again in about 10 minutes."),
            ("usage-resume", " Delete the spent reminder and stop."),
            ("usage-resume", " Then delete the spent resume reminder."),
        ):
            with self.subTest(old=old):
                self.assertIn(rule_id, ids(prompt_rules.check_text("orchestrator", real("orchestrator") + old)))

    def test_the_usage_sections_never_bring_back_a_fixed_cap_of_5(self):  # owner decision, #15 comment 6974903898
        sec = re.search(r"### 7\.7 Usage limits.*?(?=\n## 8\.)", self.doc(self.ORCH), re.S).group(0)
        for where, text in (("ORCHESTRATION 7.7", sec), ("orchestrator prompt", real("orchestrator"))):
            self.assertNotRegex(text, r"(?i)\b(?:cap|limit|at most|up to|max(?:imum)?)\b[^.\n]{0,20}\*{0,2}\b5\b(?![- ]?(?:minutes?|hours?)\b)", where)
        for old in (" At most 5 worker sessions at once.", " Keep to the cap of 5 workers."):
            with self.subTest(old=old):
                self.assertIn("orch-throttle", ids(prompt_rules.check_text("orchestrator", real("orchestrator") + old)))

    FINDINGS_ROLES = ("reviewer", "design-reviewer", "second-reviewer")
    FINDINGS_RULE = "usage-reviewer-findings"

    def test_reviewer_findings_live_in_the_pr_comment_not_a_scratch_file(self):  # item 4b of #60
        for role in self.FINDINGS_ROLES:
            with self.subTest(role=role):
                self.assertEqual(prompt_rules.check_text(role, real(role)), [])
                self.assertNotRegex(prompt_rules.normalize(real(role)), r"(?i)scratch file")

    def test_a_scratch_file_alone_is_rejected_for_every_reviewer_role(self):  # the old wording, with nothing else
        old = "Keep the findings you have proved in a scratch file outside the repo."
        for role in self.FINDINGS_ROLES:
            with self.subTest(role=role):
                self.assertIn(self.FINDINGS_RULE, ids(prompt_rules.check_text(role, old)))

    def test_the_scratch_file_is_rejected_even_next_to_the_comment_rule(self):
        for role in self.FINDINGS_ROLES:
            with self.subTest(role=role):
                text = real(role) + " Also keep a copy in a scratch file."
                self.assertIn(self.FINDINGS_RULE, ids(prompt_rules.check_text(role, text)))

    def test_each_comment_clause_is_pinned_in_every_reviewer_role(self):
        for role in self.FINDINGS_ROLES:
            for phrase in ("`ROUND IN PROGRESS`", "edit that same comment as findings accumulate", "§8.3"):
                with self.subTest(role=role, phrase=phrase):
                    norm = prompt_rules.normalize(real(role))
                    self.assertIn(phrase.lower(), norm.lower())
                    cut = re.sub(re.escape(phrase), "", norm, flags=re.I)
                    self.assertIn(self.FINDINGS_RULE, ids(prompt_rules.check_text(role, cut)))

    def test_the_rule_applies_to_no_other_role(self):
        self.assertNotIn(self.FINDINGS_RULE, ids(prompt_rules.check_text("implementer", "")))
        self.assertNotIn(self.FINDINGS_RULE, ids(prompt_rules.check_text("escalation-reviewer", "")))


class NoResolveThreadTests(unittest.TestCase):
    """Follow-up #44 (R1-07): agents never resolve a collaborator's review thread; they reply and leave it for the collaborator or the owner.
    The prompts already carry the ban (rule no-resolve-thread); these pin the reply-and-leave half and the process docs."""

    REPLY_ROLES = ("implementer", "orchestrator")  # the roles that answer on threads; read-only roles only carry the ban
    DOCS = {
        "docs/ORCHESTRATION.md": (
            "orch-no-resolve-thread",
            "never resolve a collaborator's review thread (follow-up #44): reply and leave it for the collaborator or the owner",
        ),
        "docs/COLLABORATING.md": ("collab-no-resolve", "**Resolve conversation**"),
    }

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_the_real_prompts_and_docs_pass(self):
        for role in self.REPLY_ROLES:
            self.assertNotIn("no-resolve-thread-reply", ids(prompt_rules.check_text(role, real(role))))
        for path in self.DOCS:
            self.assertEqual(prompt_rules.check_doc_text(path, self.doc(path)), [], path)

    def test_the_reply_rule_exists_for_exactly_the_reply_roles(self):
        rule = next((r for r in prompt_rules.RULES if r.id == "no-resolve-thread-reply"), None)
        self.assertIsNotNone(rule)
        self.assertEqual(set(rule.roles), set(self.REPLY_ROLES))

    def test_dropping_the_reply_and_leave_it_half_is_rejected(self):
        for role in self.REPLY_ROLES:
            text = real(role)
            self.assertRegex(prompt_rules.normalize(text), r"reply and leave it for the collaborator or the owner")
            cut = re.sub(r"reply\s+and\s+leave\s+it\s+for\s+the\s+collaborator\s+or\s+the\s+owner", "", text, count=1)
            with self.subTest(role=role):
                self.assertIn("no-resolve-thread-reply", ids(prompt_rules.check_text(role, cut)))

    def test_reply_then_leave_it_to_the_owner_alone_is_rejected(self):
        for role in self.REPLY_ROLES:
            cut = re.sub(r"for\s+the\s+collaborator\s+or\s+the\s+owner", "for nobody", real(role), count=1)
            with self.subTest(role=role):
                self.assertIn("no-resolve-thread-reply", ids(prompt_rules.check_text(role, cut)))

    def test_permission_to_resolve_is_rejected(self):
        for role in ROLES:
            for stale in (" You may resolve the thread once you have replied.", " Resolve the collaborator's review thread after answering.",
                          " Agents can resolve a review thread when the question is answered."):
                with self.subTest(role=role, stale=stale):
                    self.assertIn("no-resolve-thread", ids(prompt_rules.check_text(role, real(role) + stale)))

    # R1-02 of #150: the natural permission phrasings (plural, no article, imperative, "feel free").
    MISSED_PERMISSION = (
        "You may resolve threads once answered.",
        "The orchestrator may resolve review threads.",
        "Resolve the thread after answering.",
        "Then resolve the conversation.",
        "Feel free to resolve the thread after replying.",
        "Agents are allowed to resolve a collaborator's thread.",
        "Reply and resolve the thread.",
        "- Resolve the collaborator's review thread.",
        # R2-02 of #150
        "Once answered, resolve the thread.",
        "After replying, resolve the thread.",
        "When done, resolve the collaborator's thread.",
        "Resolve threads once answered.",
        "Resolve review threads after replying.",
        "Reviewers may resolve the thread.",
        "Workers may resolve threads.",
        "Implementers can resolve threads.",
        "You may now resolve the thread.",
    )
    # R1-01 of #150: correct ban or owner-only wording must not be flagged.
    BAN_WORDING = (
        "Do not resolve a collaborator's review thread.",
        "Agents must not resolve a collaborator's thread.",
        "The owner resolves a collaborator's thread when done.",
        "Only the owner may resolve the thread.",
        "Agents are not allowed to resolve a collaborator's thread.",
        "Never resolve a collaborator's review thread.",
        "The collaborator may resolve their own thread.",
        # R2-01 of #150
        "No agent may resolve a collaborator's review thread.",
        "No agent can resolve the thread.",
        "Neither the orchestrator nor the reviewer may resolve the thread.",
        "Do not reply and resolve the thread.",
        "Never approve and resolve the thread yourself.",
        # a hard-wrapped ban must not read as a new sentence
        "Agents must not\nresolve the collaborator's review thread.",
    )
    # R2-03 of #150: a line-start imperative under a heading (normalize joins lines, so the sentence break has to come from the layout).
    HEADING_LAYOUTS = (
        "\n## Threads\n\nResolve the thread after answering.\n",
        "\n## Threads\nResolve the conversation once answered.\n",
        "\n\n* Resolve the collaborator's review thread once answered.\n",
    )
    PERMISSION_IDS = {"no-resolve-thread", "orch-no-resolve-thread", "collab-no-resolve"}

    def flagged(self, where, text):
        if where in ROLES:
            return ids(prompt_rules.check_text(where, text))
        return ids(prompt_rules.check_doc_text(where, text))

    def test_the_missed_permission_phrasings_are_rejected_everywhere(self):
        for stale in self.MISSED_PERMISSION:
            for where in (*ROLES, "docs/ORCHESTRATION.md", "docs/COLLABORATING.md"):
                base = real(where) if where in ROLES else self.doc(where)
                with self.subTest(where=where, stale=stale):
                    self.assertTrue(self.PERMISSION_IDS & self.flagged(where, base + "\n\n" + stale + "\n"))

    def test_correct_ban_and_owner_only_wording_is_not_rejected(self):
        for good in self.BAN_WORDING:
            for where in (*ROLES, "docs/ORCHESTRATION.md", "docs/COLLABORATING.md"):
                base = real(where) if where in ROLES else self.doc(where)
                with self.subTest(where=where, good=good):
                    self.assertFalse(self.PERMISSION_IDS & self.flagged(where, base + "\n\n" + good + "\n"))

    def test_an_imperative_under_a_heading_or_bullet_is_rejected(self):
        for layout in self.HEADING_LAYOUTS:
            for where in (*ROLES, "docs/ORCHESTRATION.md", "docs/COLLABORATING.md"):
                base = real(where) if where in ROLES else self.doc(where)
                with self.subTest(where=where, layout=layout):
                    self.assertTrue(self.PERMISSION_IDS & self.flagged(where, base + layout))

    def test_a_hard_wrapped_continuation_line_is_not_a_new_sentence(self):
        for where in ROLES:
            with self.subTest(where=where):
                self.assertFalse(self.PERMISSION_IDS & self.flagged(where, real(where) + "\nAgents must not\nresolve the thread.\n"))

    def test_every_prompt_still_needs_the_ban_itself(self):
        for role in ROLES:
            for index in range(3):
                with self.subTest(role=role, pattern=index):
                    self.assertIn("no-resolve-thread", ids(prompt_rules.check_text(role, delete_match(role, "no-resolve-thread", index))))

    def test_the_process_docs_carry_the_ban(self):
        for path, (rid, needle) in self.DOCS.items():
            with self.subTest(path=path):
                self.assertIn(needle.lower(), prompt_rules.normalize(self.doc(path)).lower())
                self.assertTrue(any(r.id == rid and r.path == path for r in prompt_rules.DOC_RULES), rid)

    def test_deleting_the_doc_wording_is_rejected(self):
        for path, (rid, needle) in self.DOCS.items():
            text = prompt_rules.normalize(self.doc(path))
            cut = re.sub(re.escape(needle), "", text, count=1, flags=re.I)
            with self.subTest(path=path):
                self.assertNotEqual(cut, text)
                self.assertIn(rid, ids(prompt_rules.check_doc_text(path, cut)))

    def test_the_orchestration_role_table_keeps_resolve_threads_in_the_collaborator_never_cell(self):
        text = prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md"))
        cut = text.replace("delete branches, resolve threads, labels", "delete branches, labels", 1)
        self.assertNotEqual(cut, text)
        self.assertIn("orch-no-resolve-thread", ids(prompt_rules.check_doc_text("docs/ORCHESTRATION.md", cut)))

    def test_stale_doc_wording_is_rejected(self):
        for path, stale in (
            ("docs/ORCHESTRATION.md", "Agents may resolve a collaborator's review thread once answered."),
            ("docs/ORCHESTRATION.md", "The orchestrator resolves the collaborator's thread after replying."),
            ("docs/COLLABORATING.md", "Agents resolve the conversation when your question is answered."),
        ):
            with self.subTest(path=path, stale=stale):
                self.assertTrue({"orch-no-resolve-thread", "collab-no-resolve"} & ids(prompt_rules.check_doc_text(path, self.doc(path) + "\n" + stale + "\n")))

    def test_check_docs_on_the_repo_passes_and_names_both_files(self):
        self.assertEqual(prompt_rules.check_docs(ROOT), [])
        self.assertTrue({"docs/ORCHESTRATION.md", "docs/COLLABORATING.md"} <= {r.path for r in prompt_rules.DOC_RULES})


class Issue134ReviewerEffortTests(unittest.TestCase):
    """#134 (owner decision, comment 6989468926): a reviewer of an area:security-rules or area:sync-merge PR runs at max effort even
    without risk:high, as docs/reviews/README.md R7 says. The reviewer prompt must say so, in step with agents/roles.yaml."""

    RULE = "reviewer-effort"
    OLD = "Opus, high effort (max for risk:high PRs)."

    def mutate(self, old, new):
        text = real("reviewer")
        self.assertIn(old, text)
        return prompt_rules.check_text("reviewer", text.replace(old, new, 1))

    def test_the_rule_exists_for_the_reviewer_only_and_the_real_prompt_passes(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        self.assertEqual(by_id[self.RULE].roles, ("reviewer",))
        self.assertNotIn(self.RULE, ids(prompt_rules.check_text("reviewer", real("reviewer"))))

    def test_the_old_risk_high_only_wording_is_rejected(self):
        text = prompt_rules.normalize(real("reviewer"))
        first = text.split(". Fresh session")[0]  # the opening line carrying the effort
        self.assertIn(self.RULE, ids(prompt_rules.check_text("reviewer", text.replace(first, self.OLD.rstrip("."), 1))))

    def test_dropping_either_label_or_the_even_without_clause_is_rejected(self):
        text = prompt_rules.normalize(real("reviewer"))
        for clause in ("`area:security-rules`", "`area:sync-merge`", "even without `risk:high`"):
            with self.subTest(clause=clause):
                self.assertIn(clause, text)
                self.assertIn(self.RULE, ids(prompt_rules.check_text("reviewer", text.replace(clause, "", 1))))

    def test_the_rule_applies_to_no_other_role(self):
        for role in ("implementer", "second-reviewer", "escalation-reviewer"):
            self.assertNotIn(self.RULE, ids(prompt_rules.check_text(role, "")), role)


if __name__ == "__main__":
    unittest.main()
