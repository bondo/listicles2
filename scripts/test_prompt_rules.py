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
ROLES = ("orchestrator", "implementer", "reviewer", "planner", "design-reviewer")

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
            ("orchestrator", "autonomy", "merges of any PR; "),
            ("orchestrator", "autonomy", "and a relayed approval is refused"),
            ("orchestrator", "lock-takeover", "and if nothing follows, ask the owner"),
            ("orchestrator", "lock-takeover", "and `get_session` shows it is not working"),
            ("orchestrator", "lock-takeover", "A holder that is working but has a stale `Updated:` is stalled, not dead:"),
            ("reviewer", "reviewer-report-only", ", and tests without negative cases"),
            ("orchestrator", "orch-deferral", "Never defer a blocker;"),
            ("orchestrator", "orch-deferral", "without owner OK (`owner-ok` label)"),
            ("orchestrator", "orch-deferral", "more than 8 open follow-ups for one milestone: stop deferring and ask the owner"),
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
        ("orchestrator", "orch-deferral", "Check that the returned issue carries every label; if one is missing, close it, keep the finding open, "
         "stop deferring and ask the owner to do M0-O10.", ""),
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
        self.assertEqual(by_id["usage-reviewer"].roles, ("reviewer",))

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
            ("delete the spent reminder and stop", "delete the spent reminder"),
            ("resume implementers before reviewers", "resume reviewers first"),
            ("re-arm the 45-minute check-in", "x"), ("post one line", "x"),
            ("a session that has gone is a normal dead worker (§7.4): respawn it from `handoff/<branch>.md`", "x"),
            ("respawn it from `handoff/<branch>.md`", "leave it"),
        ):
            self.assert_fails("orchestrator", "usage-resume", old, new)

    def test_usage_read_unknown_type_and_overage_weakened(self):  # R1-03
        for old, new in (
            ("an unknown or missing `rateLimitType` counts as 5-hour", "an unknown `rateLimitType` counts as ok"),
            ("`isUsingOverage` is true the state is near limit (overage): it never pauses either (same cap, no batched extras)",
             "`isUsingOverage` is true the state is near limit (overage): pause"),
            ("never pauses either (same cap, no batched extras)", "never pauses either"),
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
            ("two-failure stop", "x"), ("`RESUMED`", "a comment"),
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
    DR = ("dr-rubric", "dr-judge-limits", "dr-rounds", "dr-hand-off", "dr-handle-config", "dr-report-only", "usage-reviewer", "worker-no-labels")

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
        for rid in self.DR:
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
            ("a commit after `reviewed_through` gets one delta review before the merge request", "a commit after `reviewed_through` is merged"),
            ("a fresh reviewer on the range `reviewed_through..head_sha` only", "a fresh reviewer on the whole pr"),
            ("owner acceptance is the only alternative", "owner acceptance or a self-review is an alternative"),
            ("never for gate or threshold changes, which always get a delta review", "also for gate or threshold changes"),
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
        for word in ("close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves", "resolved"):
            with self.subTest(word=word):
                text = prompt_rules.normalize(real("orchestrator")).lower()
                self.assertIn(word, text)
                trimmed = re.sub(r"(has|no commit message or pr body has) close, closes, closed, fix, fixes, fixed, resolve, resolves or resolved",
                                 lambda m: m.group(0).replace(word + ",", "").replace(word + " or", "or", 1), text, count=1, flags=re.I)
                self.assertIn("orch-merge-request", ids(prompt_rules.check_text("orchestrator", trimmed)))

    def test_design_review_orchestration_weakened(self):
        for old, new in (
            ("spawn the design reviewer", "skip the design reviewer"),
            ("`agents/prompts/design-reviewer.md`", "`agents/prompts/reviewer.md`"),
            ("max 2 rounds per design pr", "max 4 rounds per design pr"),
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

    def test_no_handle_is_hardcoded_anywhere_in_the_prompts(self):
        literal = "mlbe" + "89"  # the collaborator's login: not recorded until the owner says the invitation is accepted
        for role in ROLES:
            self.assertNotIn(literal, real(role).lower(), role)
        self.assertNotIn(literal, (ROOT / "agents" / "roles.yaml").read_text(encoding="utf-8").lower())
        for role in ROLES:
            self.assertNotRegex(prompt_rules.normalize(real(role)), r"@[\w-]+(?<!\{)", f"{role}.md names an @-handle")

    def test_a_hardcoded_handle_in_the_design_reviewer_is_rejected(self):
        text = real("design-reviewer")
        for extra in ("\nPing @someone for the hand-off.", "\nPing @mlbe" + "89 for the hand-off.", "\n<!-- ok -->Ping @x-y.z"):
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
            ("max 2 opus rounds per design pr", "max 3 opus rounds per design pr"),
            ("a third round never happens", "a third round is fine"),
            ("goes into the hand-off as a question for the owner", "is dropped"),
            ("round 2: only the commits since round 1 and your open findings", "round 2: the whole pr again"),
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
            ("round 2, or round 1 when nothing above `nit` is open", "round 1 always"),
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
            ("review that range only", "review the whole pr"),
            ("do not re-review unchanged code", "re-review everything"),
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
            self.assertRegex(block, rf"^    {re.escape(line)}\s*$", line)
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


if __name__ == "__main__":
    unittest.main()
