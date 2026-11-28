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
         "escalation-reviewer", "approver")

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
            ("orchestrator", "autonomy", "merges of PRs that stay with the owner (below); "),
            ("orchestrator", "autonomy", "and a relayed approval is refused"),
            ("orchestrator", "handover", "From lineage depth 6 or more"),  # R1-01 of #179: the depth-6 clause is pinned
            ("orchestrator", "handover", "ask the owner to start the next orchestrator from a top-level session"),  # R1-04 of #179
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
        ("implementer", "impl-deferral", ", and with more than 8 open deferral follow-ups for the milestone (repo-wide review issues do not count) "
         "ask the owner", ", and with more than 8 open follow-ups for the milestone ask the owner"),
        ("orchestrator", "orch-deferral", "(findings of repo-wide reviews do not count, owner decision 7003661679)", ""),
        ("orchestrator", "orch-deferral", "stop deferring and ask the owner which follow-ups to fix as their own small PRs "
         "(as on #15 comment 6989510779); deferring resumes at 8 or fewer open",
         "stop deferring and start the milestone's burn-down task `Mx-FU` next"),  # #256: Mx-FU depends on every task of its milestone
        ("orchestrator", "orch-deferral", "(as on #15 comment 6989510779); deferring resumes at 8 or fewer open", ""),  # R1-02: owner starts them, end point
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
                           "more than 8 open deferral follow-ups", "`decision` comment", "`ready_deferred`", "not small", "no blocker or major is open"):
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
            ("gets the tooling environment (`tally_task=tooling`)", "gets the normal environment"),
            ("(`tally_task=tooling`)", "(`listicles_task=tooling`)"),
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
            ("before you send it (to the merge agent, or as a batch-approval request to the owner for an owner-only pr)", "after the owner merged"),
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

    def test_the_second_reviewer_is_high_effort_and_only_in_three_areas_per_roles_yaml(self):  # owner decision 7153510972 item 1
        block = (ROOT / "agents" / "roles.yaml").read_text().split("  escalation-reviewer:")[0].split("  second-reviewer:")[1]
        self.assertNotIn("max_effort_when", block)
        self.assertIn("effort: high", block)
        self.assertIn("only for security-rules, sync-merge and release PRs", block)
        pin = "Opus, high effort, per `agents/roles.yaml` (you do not raise your own effort)"
        self.assertIn(pin.lower(), prompt_rules.normalize(real("second-reviewer")).lower())
        self.assertIn("second-reviewer-role", self.mutate("second-reviewer", pin, "Opus, high effort (`agents/roles.yaml`; you do not raise your own effort)"))
        old = "Opus, high effort (max for `risk:high` PRs, per `agents/roles.yaml`; you do not raise your own effort)"
        self.assertIn("second-reviewer-role", self.mutate("second-reviewer", pin, old))

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
        "plan-implementer-split": "docs/PLAN.md",  # #255: owner decision 7032210967 and the merge agent
        "followups-cap-exemption": "docs/FOLLOW-UPS.md",  # #256: owner decision 7003661679
        "followups-accepted-signal": "docs/FOLLOW-UPS.md",  # R2-01: the accepted: comment signals READY, not an owner merge
        "orch-implementer-split": "docs/ORCHESTRATION.md",
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
        ("docs/PLAN.md", "plan-implementer-split", "the owner squash-merges"),
        ("docs/PLAN.md", "plan-implementer-split", "you squash-merge."),
        ("docs/FOLLOW-UPS.md", "followups-accepted-signal", "`ready_deferred`); that is the owner's signal to merge."),  # R2-01
        ("docs/FOLLOW-UPS.md", "followups-accepted-signal", "Deferrals are re-checked by the owner at merge time (PR review table)"),
        ("docs/ORCHESTRATION.md", "orch-cap-and-minors", "`cap_reached`); that is the owner's signal to merge."),
        ("docs/PLAN.md", "plan-implementer-split", "trusted on their own; the owner's merge is the review."),  # R1-04
        ("REVIEW.md", "review-minors-and-cap", "the reviewer posts `ready_nits_only` and the owner squash-merges."),  # R1-04
        ("REVIEW.md", "review-minors-and-cap", "`ready_deferred`, `accepted:` comment): a second signal for the owner to merge."),
        ("docs/FOLLOW-UPS.md", "followups-cap-exemption", "more than 8 open per milestone starts the burn-down"),  # R1-05
        ("docs/FOLLOW-UPS.md", "followups-cap-exemption", "counts only deferrals from individual PR reviews (the issue's `Source:` line names a PR)."),  # R1-01
        ("docs/FOLLOW-UPS.md", "followups-cap-exemption",
         "the orchestrator stops deferring and fixes follow-ups as their own small PRs before new feature work"),  # R1-02
        ("docs/PLAN.md", "plan-roles",
         "De-escalation (lower effort or a cheaper model for a role) happens only through the metrics retro (section 9.4), never ad hoc."),  # R1-06
        ("docs/FOLLOW-UPS.md", "followups-cap-exemption", "the orchestrator stops deferring and starts the milestone's burn-down task"),
        ("docs/ORCHESTRATION.md", "orch-implementer-split", "| **Implementer** | Opus / high (max for `risk:high`) | One batch or PR |"),
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

    def test_the_implementer_prompt_names_the_model_split_and_rejects_the_all_opus_line(self):  # owner decision 7032210967
        norm = prompt_rules.normalize(real("implementer")).lower()
        for needle in ("model and effort come from `agents/roles.yaml`", "opus, high effort for", "sonnet, medium effort otherwise, high for tooling",
                       "design or architecture", "guard/hook/command-parsing tooling", "a new implementer for a pr with 3+ review rounds"):  # R1-07
            self.assertIn(needle, norm)
        old = ("You are an IMPLEMENTER for Tally. Opus, high effort (max for risk:high PRs per `agents/roles.yaml`; "
               "you do not raise your own effort), fresh session, one PR, kept across its review rounds.")
        text = prompt_rules.normalize(real("implementer"))
        first, _, rest = text.partition(" Read:")
        self.assertIn("impl-model-and-handoff", ids(prompt_rules.check_text("implementer", old + " Read:" + rest)))

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

    def test_an_escalation_drop_becomes_withdrawn_and_no_finding_stays_open_for_the_owner(self):  # R1-04 of #129; R1-02 of #299 (7075812943)
        prompt = prompt_rules.normalize(real("escalation-reviewer")).lower()
        self.assertIn("a `drop` sets the finding to `withdrawn`", prompt)
        self.assertIn("no finding stays open for the owner", prompt)
        self.assertIn("a dropped finding becomes `withdrawn`", prompt_rules.normalize(self.doc("REVIEW.md")).lower())
        for old, new in (("a `drop` sets the finding to `withdrawn`", "a `drop` closes the finding"),
                         ("no finding stays open for the owner", "")):
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
        ("docs/ORCHESTRATION.md", "orch-handover", "Trigger: about 80% of a 1M window (60% of a 200k one, `agents/roles.yaml` context)"),  # R1-01 of #179
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
        ("docs/ORCHESTRATION.md", "orch-cap-and-minors",
         "Stop deferring and start the milestone's burn-down task `Mx-FU` next (re-deferral and majors still need the owner)."),
        ("docs/ORCHESTRATION.md", "orch-cap-and-minors",
         "Stop deferring and fix follow-ups as their own small PRs before new feature work (re-deferral and majors still need the owner)."),  # R1-02
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
            ("orchestrator", "handover", " Hand over at about 80% of a 1M window (60% of a 200k one)."),  # R1-01 of #179
            ("orchestrator", "orch-deferral", " more than about 15 changed lines"),
            ("orchestrator", "orch-deferral", " Stop deferring and ask the owner to do M0-O10."),
            ("orchestrator", "orch-deferral", " Stop deferring and start the milestone's burn-down task `Mx-FU` next."),  # #256
            ("orchestrator", "orch-deferral", " Stop deferring and fix follow-ups as their own small PRs before new feature work."),  # R1-02
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

class OrchestratorHandoverAndRecipesTests(unittest.TestCase):
    """Owner decisions on #15, comments 7000637274 and 7001335975: handover at about 50% of a 1M window, lineage depth 6 means
    the owner starts the next orchestrator, orchestrator effort medium, and the handover-only recipes written into the repo."""

    ORCH_MD = PROMPTS / "orchestrator.md"
    ORCH_DOC = ROOT / "docs" / "ORCHESTRATION.md"
    ROLES_YAML = ROOT / "agents" / "roles.yaml"

    @classmethod
    def norm(cls, path):
        return prompt_rules.normalize(path.read_text(encoding="utf-8")).lower()

    def context_value(self, key):
        m = re.search(rf"^  {key}: (\d+)\s*$", self.ROLES_YAML.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(m, f"roles.yaml context needs {key}")
        return int(m.group(1))

    def test_roles_yaml_has_the_orchestrator_handover_values_and_keeps_the_hook_values(self):
        big, small = self.context_value("orchestrator_handover_at_percent_1m"), self.context_value("orchestrator_handover_at_percent_200k")
        self.assertEqual(big, 50)  # owner decision 7239676323 item 5
        self.assertLess(small, big)  # a 200k window hands over earlier, as the hook stages do
        # the context-guard hook stages are for every session and are not part of this decision
        self.assertEqual((self.context_value("step_boundary_after_percent_1m"), self.context_value("handoff_at_percent_1m")), (60, 80))
        self.assertEqual((self.context_value("step_boundary_after_percent_200k"), self.context_value("handoff_at_percent_200k")), (40, 60))

    def test_roles_yaml_orchestrator_session_line_names_the_same_threshold_and_medium_effort(self):
        block = self.ROLES_YAML.read_text(encoding="utf-8").split("  orchestrator:\n", 1)[1].split("\n  planner:", 1)[0]
        self.assertIn("effort: medium", block)
        self.assertIn(f"near {self.context_value('orchestrator_handover_at_percent_1m')}% context", block)
        self.assertNotIn("80%", block)

    def test_orchestrator_prompt_and_orchestration_section_5_carry_the_roles_yaml_threshold(self):
        phrase = (f"at about {self.context_value('orchestrator_handover_at_percent_1m')}% of a 1m window "
                  f"({self.context_value('orchestrator_handover_at_percent_200k')}% of a 200k window (owner decision 7158603054")
        for path in (self.ORCH_MD, self.ORCH_DOC):
            with self.subTest(path=path.name):
                text = self.norm(path)
                self.assertIn(phrase.replace("at about", "about") if path == self.ORCH_DOC else phrase, text)
                self.assertNotRegex(text, r"about 80% of a 1m window \(60% of a 200k one")

    def test_the_bootstrap_prompt_states_threshold_and_depth_rule(self):
        boot = self.norm(self.ORCH_DOC).split("### 8.1 orchestrator bootstrap", 1)[1].split("### 8.2", 1)[0]
        big, small = self.context_value("orchestrator_handover_at_percent_1m"), self.context_value("orchestrator_handover_at_percent_200k")
        self.assertIn(f"hand over at about {big}% of a 1m window ({small}% of a 200k window (owner decision 7158603054", boot)
        self.assertRegex(boot, r"lineage depth (?:is )?6 or more.{0,80}the owner starts the next orchestrator")

    def test_orchestrator_prompt_states_the_depth_6_owner_start_rule_and_no_depth_7(self):
        text = self.norm(self.ORCH_MD)
        self.assertRegex(text, r"lineage depth 6 or more.{0,120}ask the owner to start the next orchestrator from a top-level session "
                               r"with the same prompt \(§5\.1 step 5\)")
        self.assertRegex(text, r"§9, f3")
        self.assertNotRegex(text, r"depth (?:of )?7|lineage depth \u2265 ?7|depth 7")

    def test_orchestration_f3_and_5_1_keep_depth_6(self):
        text = self.norm(self.ORCH_DOC)
        self.assertRegex(text, r"unless lineage depth is ≥ 6 \(§9, f3\)")
        self.assertRegex(text, r"at depth ≥ 6, the owner starts the next orchestrator")
        self.assertNotRegex(text, r"depth (?:is )?(?:≥|>=) ?7")

    def test_effort_is_medium_everywhere_the_orchestrator_is_described(self):
        self.assertRegex(self.norm(self.ORCH_MD), r"^you are the orchestrator for tally \(repo bondo/tally\)\. opus, medium effort")
        self.assertRegex(self.norm(self.ORCH_DOC), r"\| \*\*orchestrator\*\* \| opus / medium \|")

    RECIPE_HEADING = "repo access and worker-prompt recipes"
    # Every recipe of #15 comment 7001335975, item 4: (label, regex over the normalized lower-case text).
    RECIPES = (
        ("rest only", r"rest only \(graphql is blocked"),
        ("pagination", r"&page=n or `since="),
        ("ready for review", r"post `pulls/n/ccr/ready_for_review`"),
        ("update branch", r"put `pulls/n/update-branch` with `expected_head_sha`"),
        ("no clone", r"no clone in the orchestrator"),
        ("body from a file", r"-f body=@file"),
        ("scripts from a file", r"run a script that mentions a protected path from a file"),
        ("source_revision", r"`source_revision` is the pr branch name"),
        ("wait with monitor", r"monitor/until-loop.{0,80}do not end the turn while it runs; do not loop-wait for ci after every fix push"),
        ("red green one push", r"a red/green pair may go up in one push \(say so in the pr body\)"),
        ("pr bodies by mcp", r"pr bodies only through the github mcp tools"),
        ("close after merge", r"comment on the completed issue, then close it with `state=closed`, `state_reason=completed`"),
        ("merge agent authorization", r"merges under the standing authorization on #15 \(§7\.5\)"),
        ("archive policy", r"keep implementers until their pr merges; archive the others when they are done"),
        ("owner-only list", r"owner-only merge list"),
    )

    def recipe_text(self, path):
        text = self.norm(path)
        self.assertIn(self.RECIPE_HEADING, text, path.name)
        return text.split(self.RECIPE_HEADING, 1)[1]

    def test_orchestrator_prompt_has_every_recipe_in_a_short_section(self):
        section = self.recipe_text(self.ORCH_MD)
        self.assertEqual(self.missing_recipes(section), [])
        self.assertRegex(section, r"docs/orchestration\.md`? §7\.8")  # the pointer to the detailed section

    def test_orchestration_md_holds_the_detailed_section_7_8(self):
        text = self.norm(self.ORCH_DOC)
        self.assertIn("### 7.8 repo access and worker-prompt recipes", text)
        section = text.split("### 7.8 repo access and worker-prompt recipes", 1)[1].split("## 8. spawn messages", 1)[0]
        self.assertEqual(self.missing_recipes(section), [])  # all 15, not only the repo-access ones (R1-05 of #179)

    def test_section_5_says_the_orchestrator_follows_it_not_the_soft_hook_reminder(self):  # R1-03 of #179
        text = self.norm(self.ORCH_DOC).split("## 5. orchestrator handover", 1)[1].split("### 5.1", 1)[0]
        self.assertRegex(text, r"earlier than the hook stages every session gets \(60% / 80%\)")
        self.assertRegex(text, r"until the hard stage, the orchestrator follows this section, not the soft reminder")
        self.assertNotIn("for other sessions", text)

    # Owner decision on #15, comment 7005366747: a standing authorization replaces the per-window one of 7002904192 (R2-01 of #179).
    # R3-01 of #179: the record is a condition on merging, not a per-agent action.
    # Owner decision on #15, comment 7085221356: a merge agent the orchestrator spawns and #15 names as active merges under it without
    # an authorization in its own session, after checking the decision comment itself.
    STANDING = (r"merges under the owner's standing authorization \(#15 comment 7005366747, replacing the per-window rule of comment 7002904192\) "
                r"until the owner revokes it on #15")
    ACTIVE = (r"when it carries the tag `role:merge-agent`, its `parent_session_id` is that orchestrator and the body of #15 names it as active, "
              r"the merge agent " + STANDING)
    VERIFY = (r"before its first merge it reads comment 7085221356 itself on #15 and checks that it is the owner's account, unedited, and that "
              r"its first line starts with `decision \(owner` \(the same check as for a batch approval; the check proves the account, not the person\)")
    OLD_RULE = r"owner authorizes it there|has no owner authorization in its own session|authorizing each new merge agent"

    def test_standing_authorization_is_stated_in_7_5_and_agrees_with_the_prompt(self):  # R1-02 of #179, updated for 7085221356
        doc = self.norm(self.ORCH_DOC).split("### 7.5 pull requests and the merge request", 1)[1].split("### 7.6", 1)[0]
        self.assertRegex(doc, r"a merge agent the orchestrator spawns needs no owner authorization in its own session "
                              r"\(owner decision, #15 comment 7085221356\): " + self.ACTIVE)
        self.assertRegex(doc, self.VERIFY + r"; the orchestrator never passes an approval on to it; owner-only prs still need a batch approval, "
                              r"`veto #n` still stops a merge and `scripts/merge_ready\.py` still runs every check")
        # orchestrator.md line 98 holds "guard thresholds", so the process guard rejects an edit of that line; the #15 record is the next line
        prompt = self.norm(self.ORCH_MD)
        self.assertRegex(prompt, r"a merge agent you spawn needs no owner authorization in its own session \(#15 comment 7085221356\): "
                                 r"it carries the tag `role:merge-agent`, its `parent_session_id` is you and the body of #15 names it as active; "
                                 + self.VERIFY + r"; you never pass an approval on to it\.")
        self.assertRegex(prompt, r"the merge agent " + self.STANDING)
        for text in (doc, prompt):  # the per-window form and the per-session one are gone
            self.assertNotRegex(text, r"one authorization covers exactly the time window|records a new authorization|" + self.OLD_RULE)
        self.assertNotRegex(self.norm(self.ORCH_DOC), self.OLD_RULE)

    def test_the_old_per_session_rule_is_gone_from_every_process_file(self):  # 7085221356
        for path in (self.ORCH_MD, self.ORCH_DOC, self.ROLES_YAML, ROOT / "docs" / "PLAN.md", ROOT / "REVIEW.md"):
            with self.subTest(path=path.name):
                self.assertNotRegex(self.norm(path), self.OLD_RULE)
        for path in sorted((ROOT / "docs" / "reviews").glob("*.md")) + sorted(PROMPTS.glob("*.md")):
            with self.subTest(path=path.name):
                self.assertNotRegex(self.norm(path), self.OLD_RULE)

    def test_the_other_places_state_the_new_rule(self):  # 7085221356: 1.1, 2.1 tags, roles.yaml
        doc = self.norm(self.ORCH_DOC)
        s11 = doc.split("### 1.1 autonomy and limits", 1)[1].split("**stop condition:**", 1)[0]
        self.assertRegex(s11, r"the merge agent is described in §7\.5; once the body of #15 names it as active it merges under the owner's "
                              r"standing authorization, with no authorization in its own session \(owner decision, #15 comment 7085221356\)")
        self.assertRegex(s11, r"the one standing exception: a merge agent merges under the standing authorization 7005366747 by the owner's "
                              r"decision 7085221356, which it reads and verifies itself on #15 \(§7\.5\); nothing is relayed")
        self.assertRegex(doc, r"role:<role>\s+orchestrator \| implementer \| merge-agent \|")
        self.assertRegex(doc, r"\*\*sessions\*\*: one row per live worker: id, role, tags, branch,.*a `merge-agent` row whose status is not "
                              r"`archived` or `failed` is what names it as active \(§7\.5\)")
        roles = self.ROLES_YAML.read_text(encoding="utf-8").split("  merge-agent:", 1)[1].split("\n  # ", 1)[0]
        self.assertIn("merges under the standing authorization 7005366747 once #15 names it as active (tag role:merge-agent, parent "
                      "session the orchestrator; 7085221356) and for owner-only PRs under a batch approval 7007421567; "
                      "it verifies 7085221356 itself before its first merge", roles)

    def test_the_merge_agent_rule_flags_each_old_sentence_in_both_files(self):  # R1-01 of #322: the gate itself, not a copy of its regex
        prompt, doc = self.ORCH_MD.read_text(encoding="utf-8"), self.ORCH_DOC.read_text(encoding="utf-8")

        def ids(problems):
            return {p.split(":", 1)[0] for p in problems}

        self.assertNotIn("orch-merge-agent", ids(prompt_rules.check_text("orchestrator", prompt)))
        self.assertNotIn("orch-merge-agent", ids(prompt_rules.check_doc_text("docs/ORCHESTRATION.md", doc)))
        self.assertTrue(prompt_rules.OLD_MERGE_AGENT_AUTH)
        for old in prompt_rules.OLD_MERGE_AGENT_AUTH:  # every entry is plain text, so it is also the sample that must be flagged
            with self.subTest(old=old):
                self.assertIn("orch-merge-agent", ids(prompt_rules.check_text("orchestrator", prompt + "\n" + old)))
                self.assertIn("orch-merge-agent", ids(prompt_rules.check_doc_text("docs/ORCHESTRATION.md", doc + "\n" + old)))

    @classmethod
    def norm_text(cls, text):
        return prompt_rules.normalize(text).lower()

    def test_no_per_merge_agent_unit_of_authorization_is_left(self):  # R2-01 of #179: no owner source states it
        for path in (self.ORCH_MD, self.ORCH_DOC, ROOT / "scripts" / "prompt_rules.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("per merge agent", path.read_text(encoding="utf-8").lower())

    def missing_recipes(self, section):
        return [label for label, pattern in self.RECIPES if not re.search(pattern, section)]

    def test_a_section_missing_one_recipe_is_reported_for_both_files(self):  # R1-01 of #179: the check itself can fail
        for path in (self.ORCH_MD, self.ORCH_DOC):
            heading = self.RECIPE_HEADING if path == self.ORCH_MD else "### 7.8 repo access and worker-prompt recipes"
            section = self.norm(path).split(heading, 1)[1].split("## 8. spawn messages", 1)[0]
            for label, pattern in self.RECIPES:
                with self.subTest(path=path.name, recipe=label):
                    cut = re.sub(pattern, "", section)
                    self.assertNotEqual(cut, section)
                    self.assertEqual(self.missing_recipes(cut), [label])


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


class ResolveThreadSentenceTests(unittest.TestCase):
    """#153 (R3-01 to R3-04 of #150): the resolve-thread permission check works per sentence. A negating word anywhere earlier in the
    sentence (not only one word back) makes it a ban; a verb other than "reply" before "and resolve", a pronoun object, the tool name,
    "mark as resolved" and "close the conversation" count as permission when nothing negates them."""

    PERMISSION_IDS = {"no-resolve-thread", "orch-no-resolve-thread", "collab-no-resolve"}
    WHERE = (*ROLES, "docs/ORCHESTRATION.md", "docs/COLLABORATING.md")

    # R3-01: any verb before "and resolve", and "it"/"them" as the object.
    PERMISSION = (
        "Answer each with one line on its thread and resolve it.",
        "Post one line on each thread, then resolve them.",
        "Answer the question and resolve the thread.",
        "Once the thread is answered, resolve it.",
        # R3-02: the tool name, "mark as resolved", "close the conversation".
        "Use `mcp__github__resolve_review_thread` once you have replied.",
        "Call resolve_review_thread when the question is answered.",
        "Mark the thread as resolved after replying.",
        "Agents may mark conversations as resolved.",
        "Close the conversation once it is answered.",
        "You can close the thread when the collaborator is satisfied.",
        "The orchestrator closes the conversation after replying.",
        # a negation that belongs to another clause or sentence does not turn a permission into a ban
        "If the question is not answered, you may resolve the thread.",
        "Agents must not wait; you may resolve the thread.",
        "Do not wait, but you may resolve the thread.",
        "Never merge. Resolve the thread after answering.",
        "Do not guess. You may resolve it when the thread is answered.",
        # R1-01 of #267: a negation in another clause (before a colon, a bare comma, "so" or a lead clause) does not reach the permission
        "Never resolve a collaborator's review thread (follow-up #44): reply, then resolve the thread once the collaborator agrees.",
        "Never leave a collaborator waiting: reply and resolve the thread.",
        "Never leave a collaborator's review thread open: reply and resolve it.",
        "No need to ask: you may resolve the thread.",
        "Don't wait for the owner, resolve the thread.",
        "Only after replying, resolve the thread.",
        "Without waiting for the owner, you may resolve the thread.",
        "You may, without asking, resolve the thread.",
        "If there is no reply in a day you may resolve the thread.",
        "There is no rule against it, so you may resolve the thread.",
        'There is no rule against "never resolve threads", so you may resolve the thread.',
        # R1-02 of #267: the thread is named in an earlier sentence or in the lead-in line of a list
        "Answer each with one line on its thread; then resolve it.",
        "Answer each with one line on its thread. Then resolve it.",
        "Reply on the thread. Then mark it as resolved.",
        "Answer each review thread:\n- reply with one line\n- resolve it",
        # R1-01 of #267, round 2: parentheses, dashes, a slash, "and" before a new subject, "only" in a lead clause, a nested lead word.
        # The scope of a negation is only trusted in a few simple shapes; every other structure keeps the ban on the permission.
        "Never leave a collaborator waiting (reply and resolve the thread).",
        "No need to ask (you may resolve the thread).",
        "Never leave a collaborator waiting - reply and resolve the thread.",
        "Never leave a collaborator waiting -- reply and resolve the thread.",
        "Never leave a collaborator waiting \u2014 reply and resolve the thread.",
        "Never leave a collaborator waiting \u2013 reply and resolve the thread.",
        "Never leave a collaborator waiting / reply and resolve the thread.",
        "No need to ask - you may resolve the thread.",
        "No need to ask \u2014 you may resolve the thread.",
        "Never leave a collaborator waiting - resolve the thread once answered.",
        "Don't wait for the owner -- resolve the thread.",
        "There is no rule against it and you may resolve the thread.",
        "No approval is needed and you may resolve the thread.",
        "The owner does not need to approve and agents may resolve the thread.",
        "Nobody has to approve and the orchestrator may resolve the thread.",
        "Only after replying, you may resolve the thread.",
        "Only after replying, agents may resolve the thread.",
        "Only once the collaborator agrees, you may resolve the thread.",
        "Only after replying may you resolve the thread.",
        "Only when the collaborator agrees may the orchestrator resolve the thread.",
        "Only after the collaborator confirms, the orchestrator resolves the thread.",
        "When nobody answers, and not before, you may resolve the thread.",
        "Never merge the PR yourself\nYou may resolve the thread once answered.",
        # R1-01 of #267, round 3, shape (a): a negation inside a lead clause without its comma ("no <agent>") is not a negated subject
        "If the PR has no reviewer you may resolve the thread.",
        "If there is no reviewer the orchestrator may resolve the thread.",
        "When there are no reviewers the agents may resolve the thread.",
        "If there is no reviewer the orchestrator resolves the thread.",
        "If a PR has no reviewer the orchestrator is allowed to resolve the thread.",
        "If the PR has no reviewer agents are allowed to resolve the thread.",
        "If there's no reviewer feel free to resolve the thread.",
        "If there's nobody you may resolve the thread.",
        "Unless there is no orchestrator you may resolve the thread.",
        "No reviewer the orchestrator may resolve the thread.",
        # shape (b): a negator that governs another verb ("hesitate to", "forget to"), and "then <act>" after a negated step
        "Don't hesitate to reply and resolve the thread.",
        "Do not hesitate to reply and resolve the thread.",
        "Do not forget to reply and resolve the thread.",
        "Never forget to reply and resolve the thread.",
        "Never fail to reply and resolve the thread.",
        "It never hurts to reply and resolve the thread.",
        "It is not hard to reply and resolve the thread.",
        "Agents needn't wait to reply and resolve the thread.",
        "Agents should never wait to reply and resolve the thread.",
        "Do not wait to reply and resolve the thread.",
        "Don't wait long then resolve the thread.",
        "Never wait a day then resolve the thread.",
        "Don't forget to reply then resolve the thread.",
        "Not only reply and resolve the thread.",
        # shape (c): "In no ..." and a bare "No," are not a negation of the verb
        "In no particular order, resolve the threads.",
        "In no particular order, resolve the review threads once answered.",
        "In no time, resolve the thread.",
        "Need the owner? No, resolve the thread yourself.",
        "Should you wait for the owner? No, even if unsure, resolve the thread yourself.",
        "In no time can you resolve the thread.",
        # shape (d): "e.g." and "i.e." lead into an imperative
        "Handle small things yourself, e.g. resolve the thread after replying.",
        "Close the loop, i.e. resolve the thread once answered.",
        "Small steps need no approval (e.g. resolve the thread).",
        # R3-01 of #267: a numbered list item gets the thread from its lead-in, like a bulleted one
        "Answer each review thread:\n1. reply with one line\n2. resolve it",
        "Answer each review thread:\n1. reply with one line\n2. mark it as resolved",
        # R1-05 of #267: emphasis, links and table cells do not hide the permission
        "Agents may **resolve the thread** once answered.",
        "**Resolve the thread** after answering.",
        "- **Resolve the thread** after answering.",
        "Agents may [resolve the thread](https://example.com) once answered.",
        "| Orchestrator | Resolve threads after replying |",
        # R4-01 of #267: an all-bold bullet is not a button name; it keeps its permission
        "- **Agents may resolve the thread once answered.**",
        "* **You may resolve the thread after replying**",
        "- **Reply and resolve the thread.**",
        "- **Agents are allowed to resolve the thread.**",
        "- **The orchestrator resolves the conversation after replying.**",
        "- **Once answered, resolve the thread.**",
        "  - **Agents may resolve the thread once answered.**",
        # R1-01 of #267, round 4 and the escalation ruling: a focus adverb, a question, an answer before a comma, a negation inside a
        # relative clause of the subject and "Not all" are not a ban on the act
        "Not just reply and resolve the thread, but also thank the collaborator.",
        "Not merely reply and resolve the thread, but also thank the collaborator.",
        "Not simply reply and resolve the thread, but also thank the collaborator.",
        "Don't just reply and resolve the thread; also add a test.",
        "Why don't you reply and resolve the thread?",
        "Why not just reply and resolve the thread?",
        "Can't you just reply and resolve the thread?",
        "Couldn't you just reply and resolve the thread yourself?",
        "Won't you reply and resolve the thread?",
        "Shouldn't you reply and resolve the thread?",
        "Why shouldn't agents reply and resolve the thread?",
        "Need the owner? Of course not, resolve the thread yourself.",
        "Need approval? Certainly not, resolve the thread yourself.",
        "Need approval? Definitely not, resolve the thread yourself.",
        "Ask the owner first? Absolutely not, resolve the thread yourself.",
        "Need the owner? Surely not, resolve the thread yourself.",
        "Need the owner? I think not, resolve the thread yourself.",
        "Need the owner? Usually not, resolve the thread yourself.",
        "Need the owner? Probably not, resolve the thread yourself.",
        "Do agents need approval? They don't, resolve the thread after replying.",
        "Reviewers that do not find issues reply and resolve the thread.",
        "Agents who don't hear back reply and resolve the thread.",
        "Not all agents reply and resolve the thread.",
        # a bold label is a button name only when its line names no agent (self-review of the escalation fix): the same shape with an
        # agent in the next cell or the parenthetical is a permission (stricter than main, which passes these rows)
        "| **Resolve threads** | Orchestrator |",
        "| **Resolve thread** | orchestrator may do it |",
        "- **Resolve threads** (orchestrator, after replying)",
        "* **Resolve conversation** (agents may resolve it after replying)",
        "- **Resolve threads** after replying",
        "| Orchestrator | **Resolve threads** |",
        # R1-01 of #267, round 5: an adverb after the negator takes the negation off the act; R5-02: merely and simply after a real negator
        "Do not immediately reply and resolve the thread; give the collaborator a day to answer.",
        "Never automatically reply and resolve the thread.",
        "Agents should not unilaterally reply and resolve the thread.",
        "Don't always reply and resolve the thread yourself.",
        "The orchestrator does not immediately reply and resolve the thread; it waits a day.",
        "Agents do not usually reply and resolve the thread themselves.",
        "Please don't blindly reply and resolve the thread.",
        "Do not prematurely reply and resolve the thread.",
        "Don't merely reply and resolve the thread; also add a test.",
        "Never simply reply and resolve the thread; also thank them.",
        # R6-02 of #267: a multi-word adverb phrase after the negator takes the negation too
        "Agents do not by default reply and resolve the thread.",
        "The orchestrator does not by default reply and resolve the thread.",
    )
    BAN = (
        # R3-03: a comma clause between the negation and the verb
        "Agents must never, not even with the API, resolve a thread.",
        "Never, not even via the tool, resolve the thread yourself.",
        "Agents must never, even when asked, resolve a conversation.",
        # R3-04: the negation is more than one word before the subject
        "No orchestrator or implementer may resolve the thread.",
        "Not even the orchestrator may resolve a collaborator's thread.",
        "Not even the orchestrator or the reviewer resolves a thread.",
        "Neither the orchestrator nor the reviewer nor the planner may resolve the conversation.",
        # the new wordings, negated
        "Never call `mcp__github__resolve_review_thread`.",
        "Never resolve a thread, not even with `mcp__github__resolve_review_thread`: reply and leave it.",
        "Do not mark the thread as resolved.",
        "Do not answer and resolve it on the thread.",
        "Only the owner closes the conversation.",
        "Agents never close a collaborator's conversation.",
        "Leave the thread for the collaborator; do not resolve it.",
        # not about an agent resolving a thread at all
        "The owner marks the thread as resolved when done.",
        "The collaborator, who resolves the thread, is told.",
        "Close the issue when the PR has merged.",
        "Mark the finding as resolved in the findings file.",
        "The tool is named resolve_review_thread in the GitHub server.",
        # R1-04 of #267
        "None of the agents may resolve a thread.",
        "None of you may resolve the thread.",
        # the shapes of R3-03 and R3-04 with other negating phrases
        "Agents must not, under any circumstances, resolve a thread.",
        "Under no circumstances, resolve the thread yourself.",
        "At no point may the orchestrator resolve a collaborator's thread.",
        # R1-03 of #267: a sentence about the tool with no actor, and an "it" or "resolved" that is not the thread
        "A thread resolved with `resolve_review_thread` cannot be reopened by an agent.",
        "The PreToolUse hook denies calls via `mcp__github__resolve_review_thread`.",
        "Mark each finding as resolved once fixed, and reply on the thread.",
        "Mark the finding as resolved, then reply on the thread.",
        # R1-03 of #267, round 2: the tool after a gerund or infinitive, a that/those/these that is a determiner
        "Calling `mcp__github__resolve_review_thread` is blocked by the PreToolUse hook.",
        "The hook stops agents from using `mcp__github__resolve_review_thread`.",
        "Using resolve_review_thread is never allowed.",
        "Any attempt to call `resolve_review_thread` is denied.",
        "Reply on the thread and resolve those conflicts first.",
        "Answer each thread and resolve these findings in the next commit.",
        # R2-01: a thread named in an earlier sentence is not the "it" of a later, unrelated one
        "Reply on the review thread. If the merge has a conflict, resolve it.",
        "Answer each review thread. If verify.sh fails, find the cause and resolve it.",
        "Answer each thread with one line.\nIf CI fails on a flake, re-run the job; if the merge has conflicts, resolve them.",
        "Reply to each review thread with one line. Mark each finding as resolved in the findings JSON.",
        "Reply on the thread. When a finding is fixed, mark it as resolved in the findings JSON.",
        # R2-02: bans with a lead clause before the negated subject, and with an aside after "ever" or "at any point"
        "When asked no agent may resolve the thread.",
        "Until the owner agrees no agent may resolve the thread.",
        "While a thread is open no agent may resolve it.",
        "Do not ever, for any reason, resolve the thread.",
        "Agents must not ever, even when asked, resolve the thread.",
        "No agent should ever, even when asked, resolve the thread.",
        "Never at any point, even when asked, resolve the thread.",
        "Do not at any time, even when asked, resolve the thread.",
        # R2-03: "close" with words in between is an idiom, not the thread
        "Agents close the loop on each thread by replying.",
        "Then close the loop on the thread with one reply.",
        "Keep each reply short and close to the thread's topic.",
        # round 3: a test of the hook is not the tool; a "then" that leads another step does not lend its thread to a later "it"; close idioms
        "Run the resolve_review_thread hook test after editing the hook.",
        "- Run the `mcp__github__resolve_review_thread` deny case in the hook tests.",
        "Answer each review thread. Then run the tests and, if one fails, resolve it.",
        "Close the loop on threads by replying.",
        "Close the PR whose threads are all answered.",
        "- Close issues from the conversation once they are fixed.",
        # emphasis and links around a ban, and the do-not-press bullet of COLLABORATING
        "Agents must **never** resolve the thread.",
        "Do not [resolve the thread](https://example.com).",
        "- **Resolve conversation**",
        "mcp__github__resolve_review_thread is the tool name.",
        # R4-02 of #267: a button label in the docs' own list and table formats; R1-01: a negator after an agent subject or "please"
        "* **Resolve conversation** (on a review thread)",
        "| **Resolve conversation** | the owner |",
        "An agent must not reply and resolve the thread.",
        "Please do not reply and resolve the thread.",
        "Agents shouldn't answer and resolve it on the thread.",
        # R5-01 of #267: "you" in a button note is COLLABORATING's reader, not an agent; adverb-free bans with "ever" or an object stay bans
        "* **Resolve conversation** (even after you get an answer)",
        "* **Resolve conversation** (on a review thread you started)",
        "* **Resolve conversation** (the owner resolves threads, not you)",
        "| **Resolve conversation** | not you: only the owner |",
        "Do not ever reply and resolve the thread.",
        "Agents must never approve the PR and resolve the thread.",
        # R6-01 of #267: reply/apply/comply/supply are verbs, not adverbs; "never again" is a ban
        "Do not apply the suggestion and resolve the thread.",
        "Agents must not comply and resolve the thread.",
        "Never supply a patch and resolve the thread.",
        "Never again reply and resolve the thread.",
    )

    def flagged(self, where, text):
        if where in ROLES:
            return ids(prompt_rules.check_text(where, text))
        return ids(prompt_rules.check_doc_text(where, text))

    def base(self, where):
        return real(where) if where in ROLES else (ROOT / where).read_text(encoding="utf-8")

    def test_the_real_prompts_and_docs_still_pass(self):
        for where in self.WHERE:
            with self.subTest(where=where):
                self.assertFalse(self.PERMISSION_IDS & self.flagged(where, self.base(where)))

    def test_permission_wording_is_rejected_everywhere(self):
        for stale in self.PERMISSION:
            for where in self.WHERE:
                with self.subTest(where=where, stale=stale):
                    self.assertTrue(self.PERMISSION_IDS & self.flagged(where, self.base(where) + "\n\n" + stale + "\n"))

    def test_negated_and_unrelated_wording_is_not_rejected_anywhere(self):
        for good in self.BAN:
            for where in self.WHERE:
                with self.subTest(where=where, good=good):
                    self.assertFalse(self.PERMISSION_IDS & self.flagged(where, self.base(where) + "\n\n" + good + "\n"))

    # Round 3 of #267: the four ways a negation word can sit in a sentence without governing the permission, generated over cores and
    # separators so that a fifth spelling of the same shape is caught here and not by the next review round. Each combination is a permission.
    LEAD_CLAUSES = ("If the PR has no reviewer", "If there is no reviewer", "When there are no reviewers", "Unless there is no orchestrator",
                    "If there's nobody", "No reviewer")
    SUBJECT_CORES = ("you may resolve the thread", "the orchestrator may resolve the thread", "agents may resolve the thread",
                     "the orchestrator resolves the thread", "agents are allowed to resolve the thread", "feel free to resolve the thread")
    OTHER_VERB_NEGATORS = ("Don't hesitate to", "Do not forget to", "Never fail to", "It is not hard to", "Agents should never wait to",
                           "Do not wait to", "Agents needn't wait to")
    THEN_STEPS = ("Don't wait long", "Never wait a day", "Don't forget to reply", "Do not hesitate")
    COMMA_PHRASES = ("In no particular order,", "In no time,", "No,", "Need the owner? No,", "In no way whatsoever,", "Of course not,",
                     "Certainly not,")
    # escalation ruling of #267: a negation that does not start the clause as an imperative or after the agent subject is no ban
    CONJ_NON_NEGATORS = ("Not just", "Don't just", "Not all agents", "Reviewers that do not find issues", "Agents who don't hear back")
    QUESTIONS = ("Why don't you", "Can't you")
    # round 5 of #267: a negator, then an adverb that takes the negation, before "reply and resolve"
    ADVERB_NEGATORS = ("Do not", "Don't", "Never", "Please don't", "Agents should not", "The orchestrator does not")
    ADVERBS = ("immediately", "automatically", "always", "blindly", "unilaterally", "usually", "prematurely", "just", "merely", "simply",
               "first", "yet", "still", "also", "often", "by default", "in general", "right away", "straight away", "for now", "right now")
    ROLES = ("orchestrator", "implementer", "reviewer", "planner", "worker", "verifier", "agent")
    ABBREVIATIONS = ("e.g.", "i.e.", "(e.g.")
    SEPARATORS = ("", "- ", "* ", "Note: ", "1. ", "| ")

    def generated_permissions(self):
        for sep in self.SEPARATORS:
            for lead in self.LEAD_CLAUSES:
                for core in self.SUBJECT_CORES:
                    yield f"{sep}{lead} {core}."
            for neg in self.OTHER_VERB_NEGATORS + self.CONJ_NON_NEGATORS:
                yield f"{sep}{neg} reply and resolve the thread."
                yield f"{sep}{neg} reply and resolve it on the thread."
            for role in self.ROLES:  # R6-01 of #267: a button label on a line that names any agent role is no button
                yield f"| **Resolve threads** | {role.capitalize()} |"
                yield f"- **Resolve threads** ({role}, after replying)"
            for neg in self.ADVERB_NEGATORS:
                for adverb in self.ADVERBS:
                    yield f"{sep}{neg} {adverb} reply and resolve the thread."
            for question in self.QUESTIONS:
                yield f"{sep}{question} reply and resolve the thread?"
                yield f"{sep}{question} reply and resolve it on the thread?"
            for step in self.THEN_STEPS:
                yield f"{sep}{step} then resolve the thread."
            for phrase in self.COMMA_PHRASES:
                yield f"{sep}{phrase} resolve the thread yourself."
                yield f"{sep}{phrase} resolve the threads."
            for abbreviation in self.ABBREVIATIONS:
                yield f"{sep}Handle small things yourself, {abbreviation} resolve the thread after replying."

    def test_generated_permission_wordings_are_rejected(self):
        missed = [t for t in self.generated_permissions() if not prompt_rules.resolve_permissions(t + "\n")]
        self.assertGreater(len(list(self.generated_permissions())), 300)
        self.assertEqual(missed, [])

    def test_generated_bans_are_not_rejected(self):
        bans = ("No agent may resolve the thread.", "No orchestrator or implementer may resolve the thread.",
                "Not even the orchestrator may resolve the thread.", "Neither the orchestrator nor the reviewer may resolve the thread.",
                "None of the agents may resolve the thread.", "Under no circumstances may you resolve the thread.",
                "Do not reply and resolve the thread.", "Never approve and resolve the thread.",
                "Agents must never, not even with the API, resolve the thread.",
                "Nobody may ever, for any reason, resolve the thread.", "Do not ever, for any reason, resolve the thread.",
                "An agent must not reply and resolve the thread.", "Please do not reply and resolve the thread.",
                "Agents shouldn't answer and resolve it on the thread.", "An agent must never, even when asked, resolve the thread.")
        leads = ("", "- ", "* ", "Note: ", "1. ", "If a collaborator asks, ", "| ")
        flagged = [lead + ban for lead in leads for ban in bans if prompt_rules.resolve_permissions(lead + ban + "\n")]
        self.assertEqual(flagged, [])

    def test_a_hard_wrapped_sentence_is_one_sentence(self):
        wrapped = "Agents must never,\nnot even with the API,\nresolve a thread.\n"
        loose = "Agents may\nresolve a thread.\n"
        for where in self.WHERE:
            with self.subTest(where=where):
                self.assertFalse(self.PERMISSION_IDS & self.flagged(where, self.base(where) + "\n" + wrapped))
                self.assertTrue(self.PERMISSION_IDS & self.flagged(where, self.base(where) + "\n" + loose))


class Issue134ReviewerEffortTests(unittest.TestCase):
    """#134 (owner decision, comment 6989468926): a reviewer of an area:security-rules or area:sync-merge PR runs at max effort even
    without risk:high, as docs/reviews/README.md R7 says. The reviewer prompt must say so, in step with agents/roles.yaml."""

    RULE = "reviewer-effort"
    OLD = "Opus, high effort (max for risk:high PRs)."

    def test_the_rule_exists_for_the_reviewer_only_and_the_real_prompt_passes(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        self.assertEqual(by_id[self.RULE].roles, ("reviewer",))
        self.assertNotIn(self.RULE, ids(prompt_rules.check_text("reviewer", real("reviewer"))))

    def test_the_old_risk_high_only_wording_is_rejected(self):
        text = prompt_rules.normalize(real("reviewer"))
        first = text.split(". Fresh session")[0]  # the opening line carrying the effort
        self.assertIn(self.RULE, ids(prompt_rules.check_text("reviewer", text.replace(first, self.OLD.rstrip("."), 1))))

    def test_a_stale_old_spelling_next_to_the_new_line_is_rejected(self):  # R1-01 of #155: only `forbidden` can catch this
        for old in ("Opus, high effort (max for risk:high PRs).", "Opus, high effort (max for `risk:high` PRs).",
                    "Opus, high effort (MAX FOR `RISK:HIGH` PRs)."):
            with self.subTest(old=old):
                self.assertNotIn(self.RULE, ids(prompt_rules.check_text("reviewer", real("reviewer"))))
                self.assertIn(self.RULE, ids(prompt_rules.check_text("reviewer", real("reviewer") + "\n" + old)))

    def test_dropping_either_label_or_the_even_without_clause_is_rejected(self):
        text = prompt_rules.normalize(real("reviewer"))
        for clause in ("`area:security-rules`", "`area:sync-merge`", "the first reviewer"):
            with self.subTest(clause=clause):
                self.assertIn(clause, text)
                self.assertIn(self.RULE, ids(prompt_rules.check_text("reviewer", text.replace(clause, "", 1))))

    def test_the_rule_applies_to_no_other_role(self):
        for role in ("implementer", "second-reviewer", "escalation-reviewer"):
            self.assertNotIn(self.RULE, ids(prompt_rules.check_text(role, "")), role)


class TokenRulesAndOwnerMergeTests(unittest.TestCase):
    """M1-40: the token rules (owner decision, #15 comment 7070278995) and the owner-merge exceptions (issue 147) in the process docs.
    Each is pinned by a rule that fails when the wording is deleted, weakened or replaced by the old text."""

    PROMPT_RULES = {
        "orch-owner-merge-exceptions": ("orchestrator",),
        "orch-token-rules": ("orchestrator",),
        "reviewer-recheck": ("reviewer",),
    }
    DOC_RULES = {
        "orch-token-rules": "docs/ORCHESTRATION.md",
        "orch-owner-merge-exceptions": "docs/ORCHESTRATION.md",
        "orch-labels-exist": "docs/ORCHESTRATION.md",
        "review-token-rules": "REVIEW.md",
        "review-dispatchers": "REVIEW.md",
        "roles-recheck-reviewer": "agents/roles.yaml",
        "followups-title-forms": "docs/FOLLOW-UPS.md",
        "followups-burndown-alerts": "docs/FOLLOW-UPS.md",
        "branch-protection-job-count": "docs/BRANCH-PROTECTION.md",
    }

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_ids(self, path, text):
        return ids(prompt_rules.check_doc_text(path, text))

    def doc_replace(self, path, old, new):
        norm = prompt_rules.normalize(self.doc(path))
        self.assertIn(old.lower(), norm.lower(), f"{path} lacks {old!r}")
        return self.doc_ids(path, re.sub(re.escape(old), new, norm, count=1, flags=re.I))

    def role_replace(self, role, old, new):
        norm = prompt_rules.normalize(real(role))
        self.assertIn(old.lower(), norm.lower(), f"{role}.md lacks {old!r}")
        return ids(prompt_rules.check_text(role, re.sub(re.escape(old), new, norm, count=1, flags=re.I)))

    def test_the_rules_exist_for_the_right_roles_and_files_and_the_real_text_passes(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        for rid, roles in self.PROMPT_RULES.items():
            self.assertEqual(by_id[rid].roles, roles, rid)
            for role in roles:
                self.assertNotIn(rid, ids(prompt_rules.check_text(role, real(role))), (rid, role))
        by_doc = {(r.id, r.path) for r in prompt_rules.DOC_RULES}
        for rid, path in self.DOC_RULES.items():
            self.assertIn((rid, path), by_doc)
            self.assertNotIn(rid, self.doc_ids(path, self.doc(path)), rid)

    def test_the_wording_in_the_wrong_file_does_not_count(self):
        self.assertIn("review-token-rules", self.doc_ids("REVIEW.md", self.doc("docs/ORCHESTRATION.md")))
        self.assertIn("orch-token-rules", self.doc_ids("docs/ORCHESTRATION.md", self.doc("REVIEW.md")))
        self.assertIn("roles-recheck-reviewer", self.doc_ids("agents/roles.yaml", ""))
        self.assertIn("reviewer-recheck", ids(prompt_rules.check_text("reviewer", real("orchestrator"))))

    # Rule 1: ready_nits_only accepts its nits.
    def test_a_weakened_nits_rule_is_rejected_in_every_place_that_states_it(self):
        for old, new in (
            ("its nits are recorded as accepted in the pr review table and the round row: no fix round, no re-review, no follow-up issue",
             "its nits go back to the implementer for one more round"),
            ("a review with verdict `ready_nits_only` goes to the merge request", "a review with verdict `ready_nits_only` gets one more round"),
        ):
            with self.subTest(old=old):
                self.assertIn("orch-token-rules", self.doc_replace("docs/ORCHESTRATION.md", old, new))
        self.assertIn("review-token-rules", self.doc_replace(
            "REVIEW.md", "a `ready_nits_only` verdict is final, its nits are accepted with no fix round, no re-review and no follow-up issue",
            "a `ready_nits_only` verdict is final, its nits are fixed in a last round"))
        self.assertIn("orch-token-rules", self.role_replace(
            "orchestrator", "a `ready_nits_only` review goes to the merge request with its nits accepted (no fix round, no re-review, no follow-up issue)",
            "a `ready_nits_only` review goes to one more round"))

    # Rule 2: a Sonnet medium re-check of a small fix-only or docs-only commit; full rounds stay Opus.
    def test_a_weakened_recheck_rule_is_rejected(self):
        self.assertIn("orch-token-rules", self.doc_replace(
            "docs/ORCHESTRATION.md", "done by a fresh sonnet medium reviewer", "done by a fresh opus max reviewer"))
        self.assertIn("orch-token-rules", self.doc_replace("docs/ORCHESTRATION.md", "full rounds stay opus", "full rounds are sonnet"))
        self.assertIn("orch-token-rules", self.doc_replace("docs/ORCHESTRATION.md", "about 30 changed lines or fewer in total", "of any size"))
        self.assertIn("orch-token-rules", self.doc_replace(
            "docs/ORCHESTRATION.md", "a small fix-only or docs-only commit that fixes the previous round's findings gets the cheap re-check",
            "a small fix-only or docs-only commit gets the cheap re-check"))
        for stale in ("(the fixes of the previous round's findings, each about 30 changed lines or fewer, or docs only)",):  # R1-01
            self.assertIn("orch-token-rules", self.doc_ids("docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md") + "\n" + stale + "\n"))
        self.assertIn("orch-token-rules", self.role_replace("orchestrator", "goes to a sonnet medium `recheck-reviewer`; full rounds stay opus",
                                                             "goes to a fresh opus round"))
        self.assertIn("reviewer-recheck", self.role_replace(
            "reviewer", "gets the same inputs as any delta review and focuses on the findings and the commit named in the spawn message",
            "reviews everything again"))
        self.assertIn("reviewer-recheck", self.role_replace("reviewer", "gets the same inputs as any delta review and focuses on",
                                                            "checks only"))  # R1-04: one statement of the inputs

    def test_the_recheck_role_is_sonnet_medium_and_the_reviewer_effort_is_not_max_for_consistency(self):
        roles = self.doc("agents/roles.yaml")
        old = "  recheck-reviewer:\n    model: sonnet"
        self.assertIn(old, roles)
        self.assertIn("roles-recheck-reviewer", self.doc_ids("agents/roles.yaml", roles.replace(old, "  recheck-reviewer:\n    model: opus", 1)))
        self.assertIn("roles-recheck-reviewer", self.doc_ids("agents/roles.yaml", roles + "\n# Reviewers run at max for consistency.\n"))
        self.assertIn("roles-recheck-reviewer", self.doc_ids("agents/roles.yaml", roles.replace("effort: medium\n    session: fresh, for the re-check",
                                                                                                "effort: max\n    session: fresh, for the re-check", 1)))
        self.assertNotIn("roles-recheck-reviewer", self.doc_ids("agents/roles.yaml", roles))

    # Rule 3: hardening PRs stop at the second round with new bypass forms.
    def test_a_weakened_hardening_stop_is_rejected(self):
        for old, new in (
            ("the second round that finds new bypass forms ends the pr", "every round that finds new bypass forms gets a fix round"),
            ("the forms are recorded as accepted residuals in the pr body", "the forms are fixed before the merge request"),
            ("on a pr that hardens `scripts/guards.sh`, `scripts/hooks/pretooluse_guard.py` or `scripts/prompt_rules.py`", "on any pr"),
        ):
            with self.subTest(old=old):
                self.assertIn("orch-token-rules", self.doc_replace("docs/ORCHESTRATION.md", old, new))
        # R1-02: no clause beyond the owner text ("the PR stops there")
        self.assertIn("orch-token-rules", self.doc_ids(
            "docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md") + "\nAny other finding above nit is still fixed.\n"))
        self.assertIn("review-token-rules", self.doc_replace(
            "REVIEW.md", "the second round that reports new bypass forms ends the pr", "the fourth round that reports new bypass forms ends the pr"))
        self.assertIn("orch-token-rules", self.role_replace(
            "orchestrator", "the second round that finds new bypass forms ends the pr", "a new bypass form always gets a fix round"))

    # Metrics: one row per archived session.
    def test_the_metrics_row_per_archived_session_is_pinned(self):
        self.assertIn("orch-token-rules", self.doc_replace("docs/ORCHESTRATION.md", "(one per session, written as it is archived)", "(one per worker)"))
        self.assertIn("orch-token-rules", self.doc_replace("docs/ORCHESTRATION.md", "for every role, reviewers included", "for implementers"))
        self.assertIn("orch-token-rules", self.role_replace("orchestrator", "write each session's `metrics:session` row (§6.1) just before archiving it",
                                                             "archive each session"))

    # Issue 147: the owner merges owner-only PRs, not every PR.
    def test_the_stale_owner_merges_every_pr_wording_is_rejected(self):
        for path, stale in (
            ("docs/ORCHESTRATION.md", "The owner's queue is `is:open is:pr draft:false`."),
            ("docs/ORCHESTRATION.md", "**Before asking the owner to merge** the orchestrator checks"),
            ("docs/ORCHESTRATION.md", "After each owner merge, the **orchestrator** updates the next ready PR."),
            ("docs/ORCHESTRATION.md", "agent PRs stay draft until the orchestrator marks one ready because it is mergeable; the owner merges."),
            ("docs/ORCHESTRATION.md", "then the merge agent merges it, or the owner for an owner-only PR (§7.5)."),  # R1-03
            ("docs/ORCHESTRATION.md", "After each merge by the owner, the **orchestrator** updates the next ready owner-only PR."),
            ("docs/ORCHESTRATION.md", "Owner-only PRs wait in the owner's queue."),
        ):
            with self.subTest(stale=stale):
                self.assertIn("orch-owner-merge-exceptions", self.doc_ids(path, self.doc(path) + "\n" + stale + "\n"))
        self.assertIn("orch-owner-merge-exceptions", ids(prompt_rules.check_text(
            "orchestrator", real("orchestrator") + "\nAsk the owner for merges and decisions.\n")))

    def test_each_owner_merge_exception_is_needed(self):
        for old, new in (
            ("owner-only prs wait for the owner's batch approval (below), every other one goes to the merge agent",
             "every ready pr goes to the owner"),
            ("to the merge agent, or as a batch-approval request to the owner for an owner-only pr) the orchestrator checks",
             "to the owner) the orchestrator checks"),
            ("then the merge agent merges it: a `general` pr under the standing authorization, an owner-only pr as kind `owner-batch` once the "
             "owner's batch approval lists it (§7.5)", "then the owner merges it"),
            ("by the merge agent itself with `scripts/update-branch.sh` (above) when it is in the merge agent's batch; otherwise",
             "by the owner; otherwise"),
        ):
            with self.subTest(old=old):
                self.assertIn("orch-owner-merge-exceptions", self.doc_replace("docs/ORCHESTRATION.md", old, new))
        self.assertIn("orch-owner-merge-exceptions", self.role_replace(
            "orchestrator", "(the merge agent merges them as `owner-batch` once approved, and every other ready pr, §7.5)", "(never the merge agent)"))
        self.assertIn("orch-merge-request", self.role_replace(
            "orchestrator", "before you send it (to the merge agent, or as a batch-approval request to the owner for an owner-only pr), check that",
            "after the owner merged, check that"))

    # Issue 218: the manual dispatcher line stays until detekt 2.0 is stable.
    def test_the_dispatcher_review_line_needs_its_scope_and_its_severity(self):
        for old, new in (
            ("(`:core:data` and `:app` prs)", "(`:core:data` prs)"),
            ("tracked on m6", "tracked on m1"),
            ("a hard-coded dispatcher is a `minor` finding", "a hard-coded dispatcher is a `nit`"),
            ("`dispatchers.io`, `dispatchers.default` or `dispatchers.main`", "`dispatchers.io`"),
        ):
            with self.subTest(old=old):
                self.assertIn("review-dispatchers", self.doc_replace("REVIEW.md", old, new))

    # #260 items 1, 9, 10, 11.
    def test_the_nit_wording_of_issue_260_is_pinned(self):
        for stale in ("eight", "ten", "eleven"):
            self.assertIn("branch-protection-job-count", self.doc_ids(
                "docs/BRANCH-PROTECTION.md", self.doc("docs/BRANCH-PROTECTION.md") + f"\n- Only the {stale} jobs above.\n"))
        self.assertIn("orch-labels-exist", self.doc_ids(
            "docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md") + "\nThe `owner-todo` label is not created yet.\n"))
        self.assertIn("followups-title-forms", self.doc_ids(
            "docs/FOLLOW-UPS.md", self.doc("docs/FOLLOW-UPS.md") + "\nIssue title: `[follow-up] <finding title>`. Labels exist.\n"))
        self.assertIn("followups-burndown-alerts", self.doc_replace(
            "docs/FOLLOW-UPS.md", "it also reviews every open dependabot alert", "it also closes nothing"))


class DelegatedDecisionsTests(unittest.TestCase):
    """Owner decision, #15 comment 7075812943: four decision types go to agents (tooling PR approval, round-cap rulings, over-cap deferrals,
    risk:high starts). Each clause is pinned in ORCHESTRATION, the orchestrator prompt and the approver prompt, and fails when deleted or weakened."""

    RETAINED = (
        "settings outside git (repository settings, rulesets, environments, collaborator access)",
        "`.claude` permissions and settings", "network allowlists", "licence and permission acceptances", "guard thresholds (600/1500)",
        "design and product sign-off",
        "merges of PRs with sync-merge content (sync and merge logic)",
        "the owner task M1-O5 (approving the privacy text before anyone but the owner installs the app)",
        "changes to the process files that define these authorities "
        "(CLAUDE.md, REVIEW.md, ORCHESTRATION.md approval rules, agents/roles.yaml, agents/prompts/)",
    )
    # The shared block of ORCHESTRATION 1.1 and the orchestrator prompt: (rule's clause, a weakened form).
    BLOCK = (
        ("Delegated decisions (owner decision, #15 comment 7075812943, 2026-11-22): four decision types go to agents.", "Decisions stay with the owner."),
        ("the orchestrator spawns a fresh Opus high approver session per PR (`agents/prompts/approver.md`)", "the orchestrator asks the owner per PR"),
        ("and posts the anchored `batch approval: #N@sha` decision record on #15 with its session id", "and comments on the PR"),
        ("the merge agent merges it as `owner-batch`", "the merge agent waits for the owner"),
        ("the owner keeps a veto: a `veto #N` comment on #15 before the merge stops it", "the owner has no say"),
        ("after round 4 (or a later capped round) the escalation reviewer's ruling (`fix`, `split`, or what would have been `owner`) is final, "
         "and the orchestrator follows it without asking", "the escalation reviewer's ruling goes to the owner"),
        ("the orchestrator may defer a minor finding past the 8-per-milestone follow-up cap when its fix is out of the PR's scope or the PR is "
         "at the line guard, with the usual follow-up issue and `decision` comment; majors still need the owner",
         "the orchestrator may defer any finding past the cap"),
        ("the orchestrator starts `risk:high` tasks without asking; the implementer runs at high effort, not max, and a PR in the security-rules, "
         "sync-merge or release area gets a second reviewer and a clean second-reviewer pass before READY",
         "the orchestrator asks before it starts `risk:high` tasks"),
    )

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_ids(self, path, text):
        return ids(prompt_rules.check_doc_text(path, text))

    def doc_replace(self, path, old, new):
        norm = prompt_rules.normalize(self.doc(path))
        self.assertIn(old.lower(), norm.lower(), f"{path} lacks {old!r}")
        return self.doc_ids(path, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I))

    def role_replace(self, role, old, new):
        norm = prompt_rules.normalize(real(role))
        self.assertIn(old.lower(), norm.lower(), f"{role}.md lacks {old!r}")
        return ids(prompt_rules.check_text(role, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    def test_the_rules_exist_for_the_right_roles_and_files_and_the_real_text_passes(self):
        by_id = {r.id: r for r in prompt_rules.RULES}
        for rid, role in (("delegated-decisions", "orchestrator"), ("approver-role", "approver")):
            self.assertEqual(by_id[rid].roles, (role,), rid)
            self.assertNotIn(rid, ids(prompt_rules.check_text(role, real(role))), rid)
        by_doc = {(r.id, r.path) for r in prompt_rules.DOC_RULES}
        for rid, path in (("orch-delegated-decisions", "docs/ORCHESTRATION.md"), ("roles-approver", "agents/roles.yaml")):
            self.assertIn((rid, path), by_doc)
            self.assertNotIn(rid, self.doc_ids(path, self.doc(path)), rid)

    def test_the_wording_in_the_wrong_file_does_not_count(self):
        self.assertIn("orch-delegated-decisions", self.doc_ids("docs/ORCHESTRATION.md", self.doc("REVIEW.md")))
        self.assertIn("roles-approver", self.doc_ids("agents/roles.yaml", ""))
        self.assertIn("approver-role", ids(prompt_rules.check_text("approver", real("orchestrator"))))
        self.assertIn("delegated-decisions", ids(prompt_rules.check_text("orchestrator", real("approver"))))

    def test_every_clause_of_the_shared_block_is_pinned_in_orchestration_and_the_orchestrator_prompt(self):
        for old, new in self.BLOCK:
            with self.subTest(old=old[:50]):
                self.assertIn("orch-delegated-decisions", self.doc_replace("docs/ORCHESTRATION.md", old, new))
                self.assertIn("delegated-decisions", self.role_replace("orchestrator", old, new))

    def test_the_owner_retained_list_is_exact_in_all_three_texts(self):
        lead = "Stays with the owner: "

        def edited(norm, old, new):  # edit only inside the retained sentence: the ask list names some of the same items
            if old == lead:
                return norm.replace(lead, new, 1)
            head, sep, tail = norm.partition(lead)
            self.assertTrue(sep and old in tail, f"{old!r} is not in the retained sentence")
            return head + sep + tail.replace(old, new, 1)

        def failing(label, norm, old, new):
            if label == "ORCHESTRATION":
                return self.doc_ids("docs/ORCHESTRATION.md", edited(norm, old, new))
            role = "orchestrator" if label == "orchestrator" else "approver"
            return ids(prompt_rules.check_text(role, edited(norm, old, new)))

        norms = {"ORCHESTRATION": prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md")),
                 "orchestrator": prompt_rules.normalize(real("orchestrator")), "approver": prompt_rules.normalize(real("approver"))}
        rule_of = {"ORCHESTRATION": "orch-delegated-decisions", "orchestrator": "delegated-decisions", "approver": "approver-role"}
        for label, norm in norms.items():
            edits = [(item, "") for item in self.RETAINED]
            edits += [(lead, "Also with the owner: "), ("network allowlists, ", "network allowlists, branch names, ")]
            for old, new in edits:
                with self.subTest(text=label, old=old[:40]):
                    self.assertIn(rule_of[label], failing(label, norm, old, new))

    def test_the_ask_list_no_longer_sends_the_three_delegated_decisions_to_the_owner(self):
        for stale in ("\n* the escalation reviewer's `owner` ruling, or anything above nit still open after round 5 (§6.2, §7.2.2);\n",
                      "\n* `risk:high` work (before starting it);\n"):
            self.assertIn("orch-autonomy", self.doc_ids("docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md") + stale))
        for stale in ("Stop and ask the owner for: `risk:high` work before starting it.",
                      "Stop and ask the owner for: the escalation reviewer's `owner` ruling."):
            self.assertIn("autonomy", ids(prompt_rules.check_text("orchestrator", real("orchestrator") + "\n" + stale + "\n")))
        self.assertIn("orch-autonomy", self.doc_replace(
            "docs/ORCHESTRATION.md", "* merges of PRs that stay with the owner (below, §7.5);", "* merges of owner-only PRs (§7.5);"))
        self.assertIn("autonomy", self.role_replace(
            "orchestrator", "for: merges of PRs that stay with the owner (below);", "for: merges of owner-only PRs;"))

    def test_orchestration_7_5_pins_the_approver_procedure(self):
        for old, new in (
            ("an approver agent's anchored `batch approval:` record on #15 counts as the owner's batch approval",
             "an approver agent's comment is advice"),
            ("(`agents/prompts/approver.md`, Opus high, `agents/roles.yaml`)", "(Sonnet)"),
            ("with the PR number, the head SHA, the round history and the deferral records", "with the PR number"),
            ("It checks `REVIEW.md`, the clean final round, CI, that no closing keyword precedes an issue number, the PR's changed paths against the "
             "owner-retained list (§1.1) and the owner's veto", "It checks CI"),
            ("it never merges, edits or pushes", "it may merge"),
            ("The merge agent merges the listed PR as `owner-batch` with `--approval <comment-id>`", "The orchestrator merges the PR"),
            ("the merge agent right before it runs `scripts/merge_ready.py`", "the merge agent after the merge"),
            ("is refused by the approver and waits for the owner's own batch approval", "is approved as well"),
        ):
            with self.subTest(old=old[:50]):
                self.assertIn("orch-delegated-decisions", self.doc_replace("docs/ORCHESTRATION.md", old, new))
        self.assertIn("delegated-decisions", self.role_replace(
            "orchestrator", "check for a `veto #N` comment on #15 before you send the merge request", "ignore vetoes"))

    def test_the_cap_and_ruling_sections_carry_the_decision(self):
        for old, new in (
            ("Over the cap the orchestrator may still defer a minor finding whose fix is out of the PR's scope, or when the PR is at the line guard, "
             "with the usual follow-up issue and `decision` comment, without asking; majors still need the owner",
             "Over the cap the orchestrator asks the owner"),
            ("Its ruling per PR is final (owner decision, #15 comment 7075812943) and the orchestrator follows it without asking",
             "Its ruling per PR goes to the orchestrator"),
        ):
            with self.subTest(old=old[:50]):
                self.assertIn("orch-delegated-decisions", self.doc_replace("docs/ORCHESTRATION.md", old, new))

    def test_the_approver_record_is_the_one_exception_to_owner_only_batch_approvals(self):
        self.assertIn("orch-delegated-decisions", self.doc_replace(
            "docs/ORCHESTRATION.md", "The approver's record of the delegation below is the one exception.", ""))

    # Owner decision, #15 comment 7123360368: the approver's scope also takes security-rules PRs and privacy-doc changes.
    SCOPE = (
        ("Approver scope, widened (owner decision, #15 comment 7123360368, 2026-11-24)", "Approver scope (owner decision)"),
        ("the approver also approves (a) PRs with security-rules content (`firebase/` rules and their tests)", "the approver also approves (a) PRs"),
        ("(b) changes to the privacy docs (`docs/privacy/**`)", "(b) changes to docs"),
        ("only after a clean final review round, with green CI and no veto", "after the owner looks"),
        ("a PR in the security-rules, sync-merge or release area also needs a clean independent second-reviewer pass (§7.2.2)", "a second look"),
    )

    def test_the_widened_scope_is_pinned_in_orchestration(self):
        for old, new in self.SCOPE:
            with self.subTest(old=old[:50]):
                self.assertIn("orch-delegated-decisions", self.doc_replace("docs/ORCHESTRATION.md", old, new))

    def test_security_rules_and_privacy_docs_are_no_longer_owner_retained_but_sync_merge_and_m1_o5_are(self):
        for label, norm in (("ORCHESTRATION", prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md"))),
                            ("orchestrator", prompt_rules.normalize(real("orchestrator"))), ("approver", prompt_rules.normalize(real("approver")))):
            retained = norm.partition("Stays with the owner: ")[2].partition("authorities (")[0]
            with self.subTest(text=label):
                self.assertTrue(retained, label)
                self.assertNotIn("security-rules", retained)
                self.assertNotIn("firebase/", retained)
                self.assertIn("sync-merge content (sync and merge logic)", retained)
                self.assertIn("the owner task M1-O5", retained)
        # the old wording coming back is caught in every text
        old = "merges of PRs with security-rules or sync-merge content (firebase/ rules, sync and merge logic), "
        for label, norm in (("ORCHESTRATION", prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md"))),
                            ("orchestrator", prompt_rules.normalize(real("orchestrator"))), ("approver", prompt_rules.normalize(real("approver")))):
            stale = norm.replace("merges of PRs with sync-merge content (sync and merge logic), ", old, 1)
            self.assertNotEqual(stale, norm, label)
            if label == "ORCHESTRATION":
                self.assertIn("orch-delegated-decisions", self.doc_ids("docs/ORCHESTRATION.md", stale))
            else:
                self.assertIn("delegated-decisions" if label == "orchestrator" else "approver-role", ids(prompt_rules.check_text(label, stale)))

    def test_the_max_effort_and_the_protected_areas_of_the_second_reviewer_pass_are_pinned(self):  # R1-01, R1-02 of #385
        # The decision (#15 comment 7123360368) says "at max effort"; the effort itself is set by roles.yaml max_effort_when. The release area
        # stays gated on the pass as before the decision (second-reviewer.md, REVIEW.md).
        for old, new in (
            ("a PR in the security-rules, sync-merge or release area also has a clean independent second-reviewer pass (§7.2.2)", ""),
            ("a PR in the security-rules, sync-merge or release area also has", "a PR in the security-rules area also has"),
        ):
            with self.subTest(text="approver", old=old):
                self.assertIn("approver-role", self.role_replace("approver", old, new))
        for old, new in (("security-rules, sync-merge or release-area PR", "security-rules PR"),):
            with self.subTest(text="orchestrator", old=old):
                self.assertIn("delegated-decisions", self.role_replace("orchestrator", old, new))
        self.assertIn("orch-delegated-decisions", self.doc_replace(
            "docs/ORCHESTRATION.md", "The second reviewer runs at high effort (`agents/roles.yaml`; owner decision 7153510972, item 1).", ""))
        self.assertIn("roles-second-reviewer", self.doc_replace(
            "agents/roles.yaml", "only for security-rules, sync-merge and release PRs", "for risk:high PRs and protected areas"))
        self.assertIn("roles-second-reviewer", self.doc_replace(
            "agents/roles.yaml", "prompts/second-reviewer.md escalation-reviewer:", "prompts/second-reviewer.md max_effort_when: escalation-reviewer:"))

    def test_the_orchestrator_sends_security_rules_and_privacy_prs_to_the_approver_only_inside_the_scope(self):
        for old, new in (
            ("or with an owner-only path outside the approver's scope (§1.1), is not approver work",
             "or with an owner-only path outside tooling, build, CI and gate files, is not approver work"),
            ("a security-rules, sync-merge or release-area PR only after its clean second-reviewer pass, §7.2.2", "a security-rules PR at any time"),
        ):
            with self.subTest(old=old[:40]):
                self.assertIn("delegated-decisions", self.role_replace("orchestrator", old, new))

    def test_orchestration_names_the_approver_scope_where_it_states_it(self):
        for old, new in (
            ("for an owner-only PR in the approver's scope (§1.1), an approver agent's anchored",
             "for an owner-only PR that is tooling, build, CI or gate (§1.1), an approver agent's anchored"),
            ("or any owner-only path outside the approver's scope (§1.1), is refused by the approver",
             "or any owner-only path outside tooling, build, CI and gate files, is refused by the approver"),
        ):
            with self.subTest(old=old[:40]):
                self.assertIn("orch-delegated-decisions", self.doc_replace("docs/ORCHESTRATION.md", old, new))

    def test_review_md_names_the_approver_scope_not_only_tooling(self):
        self.assertIn("review-approver-record", self.doc_replace(
            "REVIEW.md", "for PRs in the approver's scope (`docs/ORCHESTRATION.md` §1.1), the approver's record",
            "for tooling, build, CI and gate PRs, the approver's record"))

    # The approver prompt.
    def test_each_approver_clause_is_pinned(self):
        for old in (
            "Fresh session, one per PR",
            "Opus, high effort (`agents/roles.yaml`; you do not change your own effort)",
            "Inputs (from the spawn message): the PR number, the head SHA, the round history and the deferral records",
            "1. Head:", "2. Scope:", "3. REVIEW.md:", "4. Clean final round:", "5. CI:", "6. No closing keyword:", "7. Veto:",
            "refuse if one fails",
            "a design or product doc, is not yours to approve",
            "security-rules content (`firebase/` rules and their tests)", "or a privacy doc (`docs/privacy/**`)",
            "a PR in the security-rules, sync-merge or release area also has a clean independent second-reviewer pass (§7.2.2)",
            "whose first line is `batch approval: #N@<full head sha> (approver session <your session id>)`",
            "post one PR comment `approval refused` with the failed items and their evidence",
            "Then post the WORKER-RESULT block",
            "NEVER merge, mark ready, label, review-approve, edit files, or push to the PR branch",
            "Your last action: send_message to the orchestrator session named in the spawn message",
        ):
            with self.subTest(old=old[:40]):
                self.assertIn("approver-role", self.role_replace("approver", old, "x"))

    def test_an_approver_prompt_that_lets_it_merge_edit_or_push_is_rejected(self):
        for stale in ("You may merge the PR when every check passes.", "You can push a fix to the PR branch.",
                      "You should edit the files to fix small findings.", "You will mark the PR ready."):
            with self.subTest(stale=stale):
                self.assertIn("approver-role", ids(prompt_rules.check_text("approver", real("approver") + "\n" + stale + "\n")))

    def test_the_approver_carries_the_common_rules_and_check_dir_needs_its_file(self):
        got = ids(prompt_rules.check_text("approver", "report only"))
        self.assertTrue({"data-fenced", "no-resolve-thread"} <= got)
        with tempfile.TemporaryDirectory() as d:
            for role in ROLES:
                if role != "approver":
                    shutil.copy(PROMPTS / f"{role}.md", d)
            self.assertIn("approver.md: cannot read (No such file or directory)", prompt_rules.check_dir(d))

    # roles.yaml.
    def test_roles_yaml_has_the_approver_as_opus_high_one_per_pr(self):
        for old, new in (
            ("approver: model: opus effort: high", "approver: model: sonnet effort: medium"),
            ("approver: model: opus effort: high", "approver: model: opus effort: max"),
            ("session: fresh, one per PR (inputs: PR number, head SHA, round history, deferral records)", "session: long-lived"),
            ("prompt: agents/prompts/approver.md", "prompt: agents/prompts/reviewer.md"),
        ):
            with self.subTest(old=old):
                self.assertIn("roles-approver", self.doc_replace("agents/roles.yaml", old, new))

    def test_the_approver_prompt_exists_and_roles_yaml_names_it(self):
        self.assertTrue((PROMPTS / "approver.md").is_file())
        self.assertIn("approver", prompt_rules.ROLES)


class PrReviewRound1Tests(unittest.TestCase):
    """PR #299, round 1 (R1-01 to R1-04): the autonomy pin bites, an `owner` ruling is decided by the escalation reviewer, the over-cap
    exception and the approver record are stated where the old rule is, and the approver scope is the one of ORCHESTRATION 7.5."""

    OWNER_RULING = ("`owner`: taste or scope: you decide it yourself, per finding `fix` or `drop`; "
                    "your ruling is final (owner decision, #15 comment 7075812943).")
    ORCH_OWNER = "an `owner` ruling decides the taste or scope question itself, per finding `fix` or `drop`, and is final"

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_swap(self, path, old, new):
        norm = prompt_rules.normalize(self.doc(path))
        self.assertIn(old.lower(), norm.lower(), f"{path} lacks {old!r}")
        return ids(prompt_rules.check_doc_text(path, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    def role_swap(self, role, old, new):
        norm = prompt_rules.normalize(real(role))
        self.assertIn(old.lower(), norm.lower(), f"{role}.md lacks {old!r}")
        return ids(prompt_rules.check_text(role, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    # R1-01: the pin must still bite when the same words are in the owner-retained sentence.
    def test_the_ask_list_clauses_stay_pinned_although_the_retained_list_repeats_them(self):
        for old in ("licence and permission acceptances (never accept them for the owner)", "repository settings and visibility"):
            with self.subTest(old=old):
                self.assertIn("autonomy", self.role_swap("orchestrator", old, ""))
        self.assertTrue(len(re.findall(r"licence and permission acceptances", prompt_rules.normalize(real("orchestrator")))) >= 2)

    # R1-02: what an `owner` ruling means.
    def test_the_escalation_reviewer_decides_an_owner_ruling_itself(self):
        norm = prompt_rules.normalize(real("escalation-reviewer"))
        self.assertIn(self.OWNER_RULING, norm)
        self.assertIn("escalation-role", self.role_swap("escalation-reviewer", self.OWNER_RULING, "`owner`: taste or scope goes to the owner."))
        self.assertIn("escalation-role", ids(prompt_rules.check_text(
            "escalation-reviewer", real("escalation-reviewer") + "\nAn `owner` finding stays open for the owner.\n")))

    def test_the_orchestrator_and_orchestration_follow_the_owner_ruling_of_the_escalation_reviewer(self):
        self.assertIn(self.ORCH_OWNER, prompt_rules.normalize(real("orchestrator")))
        self.assertIn(self.ORCH_OWNER, prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md")))
        self.assertIn("orch-spawn-checks", self.role_swap("orchestrator", self.ORCH_OWNER, "`owner` goes to the owner"))
        self.assertIn("orch-spawn-checks", self.doc_swap("docs/ORCHESTRATION.md", self.ORCH_OWNER, "`owner` goes to the owner"))

    def test_review_md_says_the_escalation_reviewer_decides_taste_or_scope(self):
        for old, new in (("which the escalation reviewer decides itself, per finding `fix` or `drop`", "which stay with the owner"),
                         ("No finding is left open for the owner.", "An `owner` finding stays open for the owner.")):
            self.assertIn("review-escalation", self.doc_swap("REVIEW.md", old, new))

    # R1-03: the stale ask wording.
    def test_the_over_cap_exception_is_stated_where_the_stop_and_ask_rule_is(self):
        clause = "The over-cap deferrals of the delegated decisions (3) are the exception."
        self.assertIn(clause.lower(), prompt_rules.normalize(real("orchestrator")).lower())
        self.assertIn("orch-deferral", self.role_swap("orchestrator", clause, ""))
        follow = ("the orchestrator may still defer minors out of the PR's scope or at the line guard "
                  "(owner decision, #15 comment 7075812943; an implementer in a manual loop still asks the owner)")
        self.assertIn("followups-over-cap", self.doc_swap("docs/FOLLOW-UPS.md", follow, ""))

    def test_risk_high_is_no_longer_listed_as_needing_an_owner_approval(self):
        norm = prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md"))
        self.assertNotIn("starting `risk:high` work", norm)
        self.assertIn("orch-delegated-decisions", self.doc_swap(
            "docs/ORCHESTRATION.md", "Approvals of orchestrator decisions (merges of PRs that stay with the owner)",
            "Approvals of orchestrator decisions (merges, starting `risk:high` work)"))

    def test_the_approver_record_is_named_where_owner_only_prs_wait_for_the_owner(self):
        for path, rule in (("REVIEW.md", "review-approver-record"), ("docs/PLAN.md", "plan-approver-record")):
            norm = prompt_rules.normalize(self.doc(path))
            self.assertIn("the approver's record", norm, path)
            self.assertIn(rule, self.doc_swap(path, "the approver's record", "nothing"))

    # R1-04: one scope rule in both texts.
    def test_the_approver_scope_is_that_of_section_7_5_and_matches_merge_ready(self):
        clause = ("every owner-only changed path is tooling, build, CI or gate (`scripts/`, build files, `ci.yml` and other workflows, "
                  "`verification-metadata`, architecture and gate tests, `merge_ready.py` and similar), security-rules content (`firebase/` rules "
                  "and their tests) or a privacy doc (`docs/privacy/**`); a path that may merge as `general` "
                  "(as `scripts/merge_ready.py` `owner_only` decides, e.g. `docs/tasks.toml`) does not count")
        self.assertIn(clause.lower(), prompt_rules.normalize(real("approver")).lower())
        self.assertIn("approver-role", self.role_swap(
            "approver", "a path that may merge as `general` (as `scripts/merge_ready.py` `owner_only` decides, e.g. `docs/tasks.toml`) does not count", ""))
        self.assertIn("approver-role", self.role_swap("approver", "every owner-only changed path is", "every changed path is"))
        import merge_ready
        self.assertFalse(merge_ready.owner_only("docs/tasks.toml"))  # the example of R1-04: a gate PR that marks its task done


class SpeedWordingTests(unittest.TestCase):
    """Owner decision, #15 comment 7075952806 item 2 (reviews start on push, no loop-wait for CI, CI green before READY and the merge request),
    and the four accepted nits of PR #299 round 2 (R2-01 to R2-04). Each new wording is pinned and fails when removed or when the old form returns."""

    PUSH_BULLET = ("**Reviews start on push (owner decision, #15 comment 7075952806):** the orchestrator spawns the reviewer as soon as the "
                   "implementer has pushed, without waiting for CI.")
    OLD_RECIPE = "Wait for CI and verify.sh with a Monitor/until-loop and do not end the turn while waiting."
    ESCALATION_FIX = ("A per-finding `fix` gets the same one fresh round 5 as a `fix` ruling "
                      "(anything above nit still open after it goes to the owner).")
    ESCALATION_FIX_REVIEW = ("a per-finding `fix` gets the same one fresh round 5 as a `fix` ruling "
                             "(anything above nit still open after it goes to the owner)")

    def doc(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def doc_swap(self, path, old, new):
        norm = prompt_rules.normalize(self.doc(path))
        self.assertIn(old.lower(), norm.lower(), f"{path} lacks {old!r}")
        return ids(prompt_rules.check_doc_text(path, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    def role_swap(self, role, old, new):
        norm = prompt_rules.normalize(real(role))
        self.assertIn(old.lower(), norm.lower(), f"{role}.md lacks {old!r}")
        return ids(prompt_rules.check_text(role, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    def test_orchestration_has_one_home_for_the_push_rule_and_the_other_sections_link_to_it(self):
        norm = prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md"))
        self.assertIn(self.PUSH_BULLET.lower(), norm.lower())
        for old in (self.PUSH_BULLET, "(4) CI is green on the PR head (§7.1)",
                    "marks a draft PR ready after clean review rounds and with CI green on the head (§7.1)",
                    "do not loop-wait for CI after every fix push (reviews start on push, §7.1)",
                    "After every fix push do not wait in a loop for CI: the reviewer starts on your push (ORCHESTRATION §7.1)"):
            with self.subTest(old=old):
                self.assertIn("orch-reviews-on-push", self.doc_swap("docs/ORCHESTRATION.md", old, "nothing"))

    def test_the_old_loop_wait_recipe_is_forbidden_everywhere(self):
        self.assertIn("orch-reviews-on-push", ids(prompt_rules.check_doc_text(
            "docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md") + "\n" + self.OLD_RECIPE + "\n")))
        for role in ("orchestrator", "implementer"):
            with self.subTest(role=role):
                self.assertIn(f"{'orch' if role == 'orchestrator' else 'implementer'}-reviews-on-push",
                              ids(prompt_rules.check_text(role, real(role) + "\n" + self.OLD_RECIPE + "\n")))
                self.assertNotIn(self.OLD_RECIPE.lower(), prompt_rules.normalize(real(role)).lower())
        self.assertNotIn(self.OLD_RECIPE.lower(), prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md")).lower())

    def test_the_role_prompts_carry_the_push_rule(self):
        for role, rule, old in (
                ("orchestrator", "orch-reviews-on-push",
                 "Reviews start on push (§7.1, owner decision, #15 comment 7075952806): spawn the reviewer as soon as the implementer has "
                 "pushed, without waiting for CI"),
                ("orchestrator", "orch-reviews-on-push", "CI must be green on the head before you mark the PR READY and before the merge request"),
                ("orchestrator", "orch-reviews-on-push", "the implementer does not wait in a loop for CI after every fix push"),
                ("orchestrator", "orch-reviews-on-push", "do not loop-wait for CI after every fix push (reviews start on push, §7.1)"),
                ("implementer", "implementer-reviews-on-push",
                 "Reviews start on push (`docs/ORCHESTRATION.md` §7.1, owner decision, #15 comment 7075952806): the orchestrator spawns the reviewer "
                 "as soon as you have pushed; do not wait in a loop for CI after every fix push"),
                ("implementer", "implementer-reviews-on-push", "end the turn with all work committed and pushed"),
                ("implementer", "implementer-reviews-on-push", "CI must be green before READY and before the merge request")):
            with self.subTest(role=role, old=old):
                self.assertIn(old.lower(), prompt_rules.normalize(real(role)).lower())
                self.assertIn(rule, self.role_swap(role, old, "nothing"))

    # R2-01
    def test_plan_says_what_still_reaches_the_owner_after_a_fix_ruling(self):
        clause = "its ruling is final; only a finding above nit still open after a `fix` ruling's round 5 reaches you"
        self.assertIn(clause.lower(), prompt_rules.normalize(self.doc("docs/PLAN.md")).lower())
        self.assertIn("plan-escalation-final", self.doc_swap("docs/PLAN.md", clause, ""))
        for stale in ("its ruling is final, so nothing it decides reaches you", "only what it sends to the owner reaches you"):
            with self.subTest(stale=stale):
                self.assertIn("plan-escalation-final", self.doc_swap("docs/PLAN.md", clause, stale))

    # R2-02
    def test_followups_names_who_may_defer_over_the_cap_and_the_summary_row_has_the_exception(self):
        norm = prompt_rules.normalize(self.doc("docs/FOLLOW-UPS.md")).lower()
        row = ("asks the owner which follow-ups to fix as small PRs (except the orchestrator's deferral of minors out of the PR's scope "
               "or at the line guard, #15 comment 7075812943)")
        self.assertIn(row.lower(), norm)
        self.assertIn("followups-over-cap", self.doc_swap("docs/FOLLOW-UPS.md", row, "asks the owner which follow-ups to fix as small PRs"))
        self.assertIn("followups-over-cap", self.doc_swap(
            "docs/FOLLOW-UPS.md", "the orchestrator may still defer minors out of the PR's scope",
            "minors out of the PR's scope"))
        self.assertIn("followups-over-cap", self.doc_swap(
            "docs/FOLLOW-UPS.md", "the orchestrator may still defer minors out of the PR's scope or at the line guard",
            "minors out of the PR's scope or at the line guard may still be deferred"))

    # R2-03: see PrReviewRound1Tests.test_the_approver_scope_is_that_of_section_7_5_and_matches_merge_ready for the pin and its negative cases.
    def test_the_approver_parenthetical_names_the_deciding_script_not_an_example_of_a_general_path(self):
        norm = prompt_rules.normalize(real("approver")).lower()
        self.assertNotIn("(`scripts/merge_ready.py`) does not count", norm)
        self.assertIn("approver-role", ids(prompt_rules.check_text(
            "approver", real("approver").replace(
                "(as `scripts/merge_ready.py` `owner_only` decides, e.g. `docs/tasks.toml`) does not count",
                "(`scripts/merge_ready.py`) does not count"))))

    # R2-04
    def test_a_per_finding_fix_gets_the_round_5_of_a_fix_ruling(self):
        self.assertIn(self.ESCALATION_FIX.lower(), prompt_rules.normalize(real("escalation-reviewer")).lower())
        self.assertIn("escalation-role", self.role_swap("escalation-reviewer", self.ESCALATION_FIX, ""))
        self.assertIn(self.ESCALATION_FIX_REVIEW.lower(), prompt_rules.normalize(self.doc("REVIEW.md")).lower())
        self.assertIn("review-escalation", self.doc_swap("REVIEW.md", self.ESCALATION_FIX_REVIEW, ""))

    # PR #306 round 1, R1-02: the decision has two parts, each in its right place.
    WIDENED = ("After a push do not wait in a loop for CI.", "do not loop-wait for CI after a push", "does not wait in a loop for CI after a fix push")

    def test_the_decision_is_split_in_its_two_parts_and_the_widened_forms_are_forbidden(self):
        home = prompt_rules.normalize(self.doc("docs/ORCHESTRATION.md")).lower()
        for part in ("spawns the reviewer as soon as the implementer has pushed, without waiting for ci",
                     "does not wait in a loop for ci after every fix push"):
            self.assertIn(part, home)
        for role, rule in (("orchestrator", "orch-reviews-on-push"), ("implementer", "implementer-reviews-on-push")):
            for widened in self.WIDENED:
                with self.subTest(role=role, widened=widened):
                    self.assertIn(rule, ids(prompt_rules.check_text(role, real(role) + "\n" + widened + "\n")))
        for widened in self.WIDENED:
            with self.subTest(doc="ORCHESTRATION", widened=widened):
                self.assertIn("orch-reviews-on-push", ids(prompt_rules.check_doc_text(
                    "docs/ORCHESTRATION.md", self.doc("docs/ORCHESTRATION.md") + "\n" + widened + "\n")))

    def test_the_implementer_prompt_says_the_reviewer_starts_on_its_push_and_that_a_fix_push_is_not_waited_on(self):
        norm = prompt_rules.normalize(real("implementer")).lower()
        self.assertIn("the orchestrator spawns the reviewer as soon as you have pushed", norm)
        self.assertIn("do not wait in a loop for ci after every fix push", norm)

    # PR #306 round 1, R1-01: the round-5 clause of the `fix` bullet stays pinned although REVIEW.md item 4 repeats the words.
    def test_the_round_5_clause_of_the_fix_bullet_is_pinned_apart_from_the_per_finding_sentence(self):
        clause = "Anything above `nit` still open after it goes to the owner."
        norm = prompt_rules.normalize(self.doc("REVIEW.md"))
        self.assertGreaterEqual(len(re.findall(r"goes to the owner", norm)), 2)
        self.assertIn("review-escalation", self.doc_swap("REVIEW.md", "and one more fresh round (round 5) reviews. " + clause,
                                                         "and one more fresh round (round 5) reviews."))

    # PR #306 round 2, R2-02: PLAN section 6 item 2 followed the decision.
    PLAN_REVIEW = ("A **fresh Claude session** (no shared context) reviews the diff against `REVIEW.md` as soon as the author has pushed, "
                   "without waiting for CI (`docs/ORCHESTRATION.md` §7.1; CI must be green before the PR is marked READY and before the merge request)")

    def test_plan_section_6_starts_the_review_on_the_push_and_keeps_ci_green_before_ready(self):
        self.assertIn(self.PLAN_REVIEW.lower(), prompt_rules.normalize(self.doc("docs/PLAN.md")).lower())
        self.assertIn("plan-review-loop", self.doc_swap(
            "docs/PLAN.md", self.PLAN_REVIEW, "After CI is green, a **fresh Claude session** (no shared context) reviews the diff"))
        for part in ("as soon as the author has pushed, without waiting for CI",
                     "CI must be green before the PR is marked READY and before the merge request"):
            with self.subTest(part=part):
                self.assertIn("plan-review-loop", self.doc_swap("docs/PLAN.md", part, "after CI is green"))


class GoldenUpdateDelegationTests(unittest.TestCase):
    """Owner decision, #15 comment 7082564807: the orchestrator may add `golden-update` after a review round found the goldens
    intended, with a one-line note on #15 each time; implementers and collaborators still never add it; Tier 0 is unchanged."""

    ORCH = "docs/ORCHESTRATION.md"
    CHECKED = ("only after that PR's review round has checked the new or changed screenshot goldens and found them intended "
               "(no reviewer finding open against them)")
    DOC_PHRASES = (
        "add the `golden-update` label to a PR " + CHECKED,
        "a one-line note on #15 naming the PR, the head SHA and the round",
        "Only the orchestrator adds `golden-update`, and only as in the bullet above; no other agent role (implementer, reviewer, second reviewer, "
        "escalation reviewer, approver, merge agent) and no collaborator adds it; the collaborator Tier 0 label list is unchanged",
        "(for `golden-update`, the orchestrator's one-line note naming the PR, the head SHA and the round)",
    )
    PROMPT_PHRASES = (
        "add the `golden-update` label to a PR " + CHECKED,
        "post a one-line note on #15 naming the PR, head SHA and round each time",
        "only you add it; no other role and no collaborator does",
        "(for `golden-update` the note names the PR, head SHA and round)",
    )
    # Wording that gives the label to the wrong party, or back to the owner alone: rejected wherever it appears.
    BAD = (
        " Only the owner may add the `golden-update` label.",
        " The `golden-update` label stays owner-only.",
        " Implementers may add the `golden-update` label.",
        " A collaborator can apply the `golden-update` label.",
        " A reviewer may add the `golden-update` label once the goldens are intended.",
        " The second reviewer adds the `golden-update` label.",
        " The approver can set the `golden-update` label.",
        " The merge agent adds the `golden-update` label.",
    )
    COLLAB = "docs/reviews/collaborator-workflow.md"
    COLLAB_PHRASES = (
        "(never a collaborator; only the orchestrator adds them, ORCHESTRATION §1.1)",
        "CI-steering labels (the orchestrator under §1.1, never a collaborator)",
    )

    def swap_doc(self, old, new):
        norm = prompt_rules.normalize((ROOT / self.ORCH).read_text(encoding="utf-8"))
        self.assertIn(old.lower(), norm.lower(), f"{self.ORCH} lacks {old!r}")
        return ids(prompt_rules.check_doc_text(self.ORCH, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    def swap_prompt(self, role, old, new):
        norm = prompt_rules.normalize(real(role))
        self.assertIn(old.lower(), norm.lower(), f"{role}.md lacks {old!r}")
        return ids(prompt_rules.check_text(role, re.sub(re.escape(old), lambda _: new, norm, count=1, flags=re.I)))

    def test_the_real_text_passes(self):
        self.assertEqual(prompt_rules.check_text("orchestrator", real("orchestrator")), [])
        self.assertEqual(prompt_rules.check_text("implementer", real("implementer")), [])
        self.assertEqual(prompt_rules.check_doc_text(self.ORCH, (ROOT / self.ORCH).read_text(encoding="utf-8")), [])

    def test_orchestration_says_it_in_1_1_the_labels_paragraph_and_the_accident_check(self):
        norm = prompt_rules.normalize((ROOT / self.ORCH).read_text(encoding="utf-8")).lower()
        for ph in self.DOC_PHRASES:
            with self.subTest(phrase=ph):
                self.assertIn(ph.lower(), norm)
                self.assertIn("orch-golden-update", self.swap_doc(ph, ""))

    def test_the_orchestrator_prompt_says_it_and_each_part_is_pinned(self):
        norm = prompt_rules.normalize(real("orchestrator")).lower()
        for ph in self.PROMPT_PHRASES:
            with self.subTest(phrase=ph):
                self.assertIn(ph.lower(), norm)
                self.assertIn("golden-update-delegation", self.swap_prompt("orchestrator", ph, ""))

    def test_weakening_the_review_gate_is_rejected(self):
        for old, new in (("only after that PR's review round", "after a review round"),
                         ("found them intended (no reviewer finding open against them)", "found them intended")):
            with self.subTest(old=old):
                self.assertIn("golden-update-delegation", self.swap_prompt("orchestrator", old, new))
                self.assertIn("orch-golden-update", self.swap_doc(old, new))

    def test_wording_that_gives_the_label_to_the_wrong_party_is_rejected(self):
        for bad in self.BAD:
            with self.subTest(bad=bad):
                self.assertIn("golden-update-delegation", ids(prompt_rules.check_text("orchestrator", real("orchestrator") + "\n\n" + bad)))
                self.assertIn("orch-golden-update", ids(prompt_rules.check_doc_text(
                    self.ORCH, (ROOT / self.ORCH).read_text(encoding="utf-8") + "\n\n" + bad)))
                self.assertIn("worker-golden-update", ids(prompt_rules.check_text("implementer", real("implementer") + "\n\n" + bad)))

    def test_dropping_only_the_orchestrator_is_rejected(self):
        self.assertIn("orch-golden-update", self.swap_doc("Only the orchestrator adds `golden-update`", "The orchestrator adds `golden-update`"))
        self.assertIn("golden-update-delegation", self.swap_prompt("orchestrator", "only you add it; no other role and no collaborator does",
                                                                    "implementers and collaborators never add it"))

    def test_the_collaborator_workflow_doc_no_longer_calls_the_label_owner_only(self):
        text = (ROOT / self.COLLAB).read_text(encoding="utf-8")
        norm = prompt_rules.normalize(text).lower()
        self.assertEqual(prompt_rules.check_doc_text(self.COLLAB, text), [])
        for ph in self.COLLAB_PHRASES:
            with self.subTest(phrase=ph):
                self.assertIn(ph.lower(), norm)
                mutated = re.sub(re.escape(ph), "", prompt_rules.normalize(text), count=1, flags=re.I)
                self.assertIn("collab-golden-update", ids(prompt_rules.check_doc_text(self.COLLAB, mutated)))
        for old in ("(owner-only, ORCHESTRATION §1.1)", "*Owner-only*: merges, settings, spend, `risk:high`, tooling, CI-steering labels."):
            with self.subTest(old=old):
                self.assertIn("collab-golden-update", ids(prompt_rules.check_doc_text(self.COLLAB, text + "\n\n" + old)))

    def test_the_implementer_prompt_says_the_orchestrator_adds_the_label(self):
        ph = "Never add the `golden-update` label yourself: the orchestrator adds it after a review round found the goldens intended."
        self.assertIn(ph.lower(), prompt_rules.normalize(real("implementer")).lower())
        self.assertIn("worker-golden-update", self.swap_prompt("implementer", ph, ""))

    def test_tier_0_and_the_never_list_still_name_it(self):
        text = prompt_rules.normalize(real("orchestrator"))
        self.assertIn("tier0-labels", ids(prompt_rules.check_text("orchestrator", text.replace("needs-owner.", "needs-owner, golden-update.", 1))))
        self.assertIn("never-labels", ids(prompt_rules.check_text("orchestrator", text.replace("golden-update, big-pr,", "big-pr,", 1))))
        self.assertIn("tier-bullets-labels", ids(prompt_rules.check_text(
            "orchestrator", text.replace("Tier 0, no ask: reply;", "Tier 0, no ask: reply; apply golden-update;", 1))))


class TallyNamesTests(unittest.TestCase):
    """M1-92: process docs, prompts and status output say Tally; session tags are tally:* and the live-worker reads match both
    tally:* and listicles:* until no running session carries the old prefix. M1-94: LISTICLES_TASK and dev/listicles are gone too."""

    KEPT = re.compile(r"`listicles:\*`|listicles:<|listicles2", re.I)

    @staticmethod
    def text(rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def leftovers(self, rel):
        return [ln.strip()[:80] for ln in self.text(rel).splitlines()
                if "listicles" in self.KEPT.sub("", ln).lower()]

    def test_line_1_of_every_prompt_names_tally_and_not_listicles(self):
        for role in ROLES:
            with self.subTest(role=role):
                first = real(role).splitlines()[0]
                self.assertIn("Tally", first)
                self.assertNotIn("listicles", first.lower())

    def test_no_prompt_or_process_doc_has_a_stray_old_name(self):
        for rel in [f"agents/prompts/{r}.md" for r in ROLES] + ["CLAUDE.md", "README.md", "docs/COLLABORATING.md", "docs/ORCHESTRATION.md",
                                                                "docs/orchestrator-state.md", "scripts/tasks.py", "scripts/status_page.py",
                                                                "scripts/status_visual.py", "scripts/merge_ready.py",
                                                                "scripts/hooks/pretooluse_guard.py", "scripts/hooks/session_end_metrics.py"]:
            with self.subTest(path=rel):
                self.assertEqual(self.leftovers(rel), [])

    def test_the_first_lines_of_the_docs_and_the_task_graph_say_tally(self):
        for rel, start in (("CLAUDE.md", "# CLAUDE.md: rules for agents working on Tally"), ("README.md", "# Tally"),
                           ("docs/COLLABORATING.md", "# Working together on Tally"), ("docs/tasks.toml", "# Tally task graph"),
                           ("docs/orchestrator-state.md", None)):
            with self.subTest(path=rel):
                text = self.text(rel)
                if start:
                    self.assertTrue(text.startswith(start), rel)
                else:
                    self.assertIn("Living state for the Tally orchestrator.", text)
        self.assertIn("Task graph for Tally:", self.text("scripts/tasks.py"))

    def test_the_orchestration_templates_say_tally(self):
        text = self.text("docs/ORCHESTRATION.md")
        self.assertIn("How Tally work is coordinated", text)
        self.assertIn("You are the Tally orchestrator for bondo/tally", text)
        self.assertIn("You are a fresh-context {role} for Tally (bondo/tally)", text)

    def test_new_sessions_get_tally_tags_and_the_note_names_the_old_prefix(self):
        text = self.text("docs/ORCHESTRATION.md")
        block = text.split("### 2.1 Session tags", 1)[1].split("## 3.", 1)[0]
        self.assertRegex(block, r"tally:<milestone or task> +e\.g\. tally:M0, tally:process")
        self.assertNotIn("listicles:<", block)
        self.assertRegex(" ".join(block.split()), r"(?i)sessions spawned before M1-92 carry `listicles:\*`, not `tally:\*`\. metrics over history match both")

    def test_every_live_worker_read_matches_both_prefixes_and_no_tag_filter_is_left_with_only_the_old_one(self):
        for rel in ("docs/ORCHESTRATION.md", "agents/prompts/orchestrator.md"):
            lines = [ln for ln in self.text(rel).splitlines() if "listicles:*" in ln]
            self.assertTrue(lines, rel)
            for ln in lines:
                with self.subTest(path=rel, line=ln[:60]):
                    self.assertIn("`tally:*`", ln)
        reads = [ln for ln in self.text("docs/ORCHESTRATION.md").splitlines() if "tagged `" in ln]
        self.assertGreaterEqual(len(reads), 2)
        for ln in reads:
            self.assertIn("`tally:*`", ln)
            self.assertIn("`listicles:*`", ln)
        self.assertIn("every running `tally:*` or `listicles:*` session", self.text("agents/prompts/orchestrator.md"))

    def test_naming_status_says_the_working_name_is_history(self):
        text = self.text("docs/product/naming.md")
        self.assertNotIn("Working name: **Listicles**", text)
        self.assertIn("Working name until 2026-11-15 was Listicles; the name is Tally.", text)

    def test_other_names_the_check_must_not_miss(self):  # negative case: the filter finds an old name that is not kept
        self.assertEqual(self.KEPT.sub("", "You are an IMPLEMENTER for Listicles. Match `listicles:*`").lower().count("listicles"), 1)
        self.assertEqual(self.KEPT.sub("", "Set LISTICLES_TASK=tooling; match `listicles:*`").lower().count("listicles"), 1)  # M1-94
        self.assertEqual(self.KEPT.sub("", "Kotlin outside `dev/listicles/`").lower().count("listicles"), 1)  # M1-94

    def test_the_tooling_environment_is_named_tally_task(self):  # M1-94: CLAUDE.md line 16, ORCHESTRATION 7.1, orchestrator.md
        claude = self.text("CLAUDE.md").splitlines()
        self.assertIn("Only sessions started with `TALLY_TASK=tooling` may edit them.", claude[15])
        flat = " ".join(self.text("docs/ORCHESTRATION.md").split())
        self.assertIn("need the tooling environment (`TALLY_TASK=tooling`); everything else uses the normal one.", flat)
        self.assertIn("gets the tooling environment (`TALLY_TASK=tooling`);", self.text("agents/prompts/orchestrator.md"))


class HandoverMessageTests(unittest.TestCase):
    """M1-97, owner decisions on #373: 7136480651 (the incoming orchestrator messages the outgoing one once its `handover-ack` is posted)
    and 7136535861 (the outgoing one's last action, after `handover-released`, is a message naming that comment id to the incoming one).
    The scheduled 5-minute checks stay the fallback in both directions."""

    DOC_RULE = "orch-handover-messages"
    PROMPT_RULE = "handover-messages"
    DOC = "docs/ORCHESTRATION.md"

    def doc(self):
        return (ROOT / self.DOC).read_text(encoding="utf-8")

    def test_both_rules_exist_with_patterns_for_both_decisions(self):
        prompt = next((r for r in prompt_rules.RULES if r.id == self.PROMPT_RULE), None)
        doc = next((r for r in prompt_rules.DOC_RULES if r.id == self.DOC_RULE), None)
        self.assertIsNotNone(prompt, self.PROMPT_RULE)
        self.assertIsNotNone(doc, self.DOC_RULE)
        self.assertEqual(prompt.roles, ("orchestrator",))
        self.assertEqual(doc.path, self.DOC)
        for rule in (prompt, doc):
            joined = " ".join(rule.patterns)
            for needle in ("7136480651", "7136535861", "send_message", "handover-released", "fallback", "5-minute"):
                self.assertIn(needle, joined, f"{rule.id} does not pin {needle}")
        self.assertIn("handover-ack", " ".join(prompt.patterns))  # the prompt names the comment; the doc says "the ack" (its step 4 names the comment)

    def test_the_real_files_pass_both_rules(self):
        self.assertNotIn(self.PROMPT_RULE, ids(prompt_rules.check_text("orchestrator", real("orchestrator"))))
        self.assertNotIn(self.DOC_RULE, ids(prompt_rules.check_doc_text(self.DOC, self.doc())))

    def test_deleting_any_pinned_clause_fails_its_rule(self):  # negative cases: every pattern matters
        prompt_rule = next(r for r in prompt_rules.RULES if r.id == self.PROMPT_RULE)
        doc_rule = next(r for r in prompt_rules.DOC_RULES if r.id == self.DOC_RULE)
        prompt_norm = prompt_rules.normalize(real("orchestrator"))
        doc_norm = prompt_rules.normalize(self.doc())
        for i, pattern in enumerate(prompt_rule.patterns):
            with self.subTest(rule=prompt_rule.id, pattern=i):
                cut, n = re.subn(pattern, "", prompt_norm, flags=re.I)
                self.assertTrue(n)
                self.assertIn(self.PROMPT_RULE, ids(prompt_rules.check_text("orchestrator", cut)))
        for i, pattern in enumerate(doc_rule.patterns):
            with self.subTest(rule=doc_rule.id, pattern=i):
                cut, n = re.subn(pattern, "", doc_norm, flags=re.I)
                self.assertTrue(n)
                self.assertIn(self.DOC_RULE, ids(prompt_rules.check_doc_text(self.DOC, cut)))

    def test_the_scheduled_checks_stay_the_fallback_in_both_directions(self):
        text = prompt_rules.normalize(self.doc()).lower()
        s51 = text.split("### 5.1", 1)[1].split("### 5.2", 1)[0]
        s52 = text.split("### 5.2", 1)[1].split("### 5.3", 1)[0]
        self.assertRegex(s51, r"send_later.{0,300}fallback|fallback.{0,300}send_later|5-minute checks stay the fallback")
        self.assertRegex(s52, r"5-minute .{0,40}stay the fallback")

    def test_step_orders_in_5_1_and_5_2(self):
        text = prompt_rules.normalize(self.doc()).lower()
        s51 = text.split("### 5.1", 1)[1].split("### 5.2", 1)[0]
        s52 = text.split("### 5.2", 1)[1].split("### 5.3", 1)[0]
        # the outgoing orchestrator's last action is the message, after the release comment; it never messages workers
        self.assertRegex(s51, r"post `handover-released`.{0,400}last action.{0,200}`send_message`.{0,200}`handover-released` comment id")
        # the incoming one messages the outgoing one right after posting its ack
        self.assertRegex(s52, r"post `handover-ack`.{0,600}`send_message` the outgoing orchestrator.{0,200}check.{0,60}now")

    def test_a_message_never_replaces_the_comment(self):  # the message only prompts a look; the lock rules read the comments
        text = prompt_rules.normalize(self.doc()).lower()
        self.assertRegex(text, r"a message only prompts the check: .{0,120}comment")


class TokenSavingsTests(unittest.TestCase):
    """Owner decision 7153510972 (state issue #399), items 1-5 and the doc of item 6: effort, implementer context, PR size, re-check, merge agent.

    Each phrase must be in the real file and pinned by a `token-savings-*` rule (deleting it fails the checker); the replaced wording must be rejected.
    """

    ORCH, ROLES_YAML, M1 = "docs/ORCHESTRATION.md", "agents/roles.yaml", "docs/milestones/M1.md"
    P200 = "25% of a 200k window (owner decision 7158603054 item 2)"  # answers the open 200k question of #408 (R1-05, R2-03)
    PINNED = (
        (ROLES_YAML, "the first reviewer of a pr labelled area:security-rules or area:sync-merge"),
        (ROLES_YAML, "a risk:high implementer runs at high effort, not max"),
        (ROLES_YAML, "for security-rules, sync-merge and release prs"),
        (ROLES_YAML, "up to about 150 changed lines when they touch only tests or docs"),
        (ROLES_YAML, "a fresh merge agent once a day, at the first merge request after 00:00 utc"),
        (ROLES_YAML, P200),
        (ROLES_YAML, "the first reviewer (the primary reviewer, not the second reviewer) in every round (owner decision 7158603054 item 1)"),
        (ROLES_YAML, "orchestrator_handover_at_percent_200k: 25"),
        (ORCH, "the first reviewer is the primary reviewer in every round (owner decision 7158603054, item 1)"),
        (M1, "max only for the first reviewer of an `area:security-rules` or `area:sync-merge` pr"),
        (ROLES_YAML, "implementer_handoff_at_percent: 30"),
        (ROLES_YAML, "orchestrator_handover_at_percent_1m: 50"),
        (ORCH, "opus / high (max for the first reviewer of a pr labelled `area:security-rules` or `area:sync-merge`)"),
        (ORCH, "the implementer runs at high effort, not max"),
        (ORCH, "a pr in the security-rules, sync-merge or release area also needs a clean independent second-reviewer pass"),
        (ORCH, "the second reviewer runs at high effort"),
        (ORCH, "about 30 changed lines or fewer in total, or up to about 150 when they touch only tests or docs"),
        (ORCH, "an implementer hands off at about 30% context"),
        (ORCH, "a fix round goes to a fresh implementer"),
        (ORCH, "a pr above 500 counted lines is split before its first review round"),
        (ORCH, "a fresh merge agent once a day, at the first merge request after 00:00 utc (checked at each check-in)"),
        (ORCH, "spawn it in three steps: (1) `create_session` with the template below and `merge requests: wait for the first merge request`"),
        (ORCH, "(3) send the first merge request with `send_message`, only after that update"),
        (ORCH, "a `merge-agent` row that is not archived or failed"),
        (ORCH, "if the body does not name you as active, do not merge; send_message the orchestrator and wait"),
        (ORCH, "sets the old merge-agent row to archived (once it has no merge in flight) and adds the new agent's row"),
        (ORCH, "the merge-agent row's `spawned-at` records the rotation time"),
        (ORCH, "check that the state issue body names you as active before your first merge"),
        (ORCH, "trigger: about 50% of a 1m window (" + P200),
        (ORCH, "hand over at about 50% of a 1m window (" + P200),
        (ORCH, "### 8.6 merge agent"),
        (ORCH, "tags `role:merge-agent`, `tally:process`"),
        ("implementer", "hand off at about 30% context"),
        ("implementer", "a pr above 500 counted lines is split before its first review round"),
        ("reviewer", "max for the first reviewer of a pr labelled `area:security-rules` or `area:sync-merge`, in every round"),
        ("second-reviewer", "opus, high effort, per `agents/roles.yaml`"),
        ("planner", "plan prs at about 400 counted lines; a pr above 500 is split before its first review round"),
        ("orchestrator", "at about 50% of a 1m window (" + P200),
        ("orchestrator", "a fresh merge agent once a day, at the first merge request after 00:00 utc"),
        ("orchestrator", "sets the old merge-agent row to archived (once it has no merge in flight) and adds the new agent's row"),
        ("orchestrator", "up to about 150 changed lines when they touch only tests or docs"),
        ("orchestrator", "a fresh implementer from `handoff/<branch>.md` when the running one is above 30% context"),
    )
    STALE = (
        (ORCH, "Opus / high (max for `risk:high`) or Sonnet"),
        (ORCH, "they still get max effort, a second reviewer every round"),
        (ORCH, "a second reviewer runs at max effort for `risk:high` and `area:security-rules` PRs"),
        (ORCH, "Trigger: about 50% of a 1M window (40% of a 200k one)"),
        (ROLES_YAML, "second-reviewer: model: opus effort: max"),
        (ROLES_YAML, "every other reviewer and every later round runs at high"),
        (ORCH, "after the daily pacing recompute"),
        (ORCH, "at the first merge request after 00:00 UTC, i.e. the orchestrator's first check-in of the UTC day"),
        (ORCH, "this PR's scaling, pending owner confirmation"),
        ("orchestrator", "this PR's scaling, pending owner confirmation"),
        (ORCH, "30% of a 200k window: PR #408's scaling (scaled to 26, set to 30), pending owner confirmation"),
        ("orchestrator", "30% of a 200k window: PR #408's scaling (scaled to 26, set to 30), pending owner confirmation"),
        (ROLES_YAML, "orchestrator_handover_at_percent_200k: 30"),
        (ORCH, "(30% of a 200k one"),
        (M1, "implementer and reviewer at high effort, both at max for `risk:high`"),
        ("reviewer", "every other reviewer and every later round runs at high"),
        ("orchestrator", "after the daily pacing recompute"),
        ("reviewer", "Opus, high effort (max for `risk:high` PRs and for PRs labelled `area:security-rules`"),
        ("second-reviewer", "Opus, high effort (max for `risk:high` PRs and for PRs labelled `area:security-rules`"),
        ("implementer", "max for risk:high PRs"),
        ("orchestrator", "a second reviewer every round"),
        ("orchestrator", "at max effort for `risk:high` and security-rules"),
        ("orchestrator", "at about 50% of a 1M window (40% of a 200k one"),
        # Owner decision 7239676323 item 5 (2026-11-28): 50% of a 1M window replaces 35%.
        (ROLES_YAML, "orchestrator_handover_at_percent_1m: 35"),
        (ORCH, "trigger: about 35% of a 1M window (" + P200),
        (ORCH, "Hand over at about 35% of a 1M window (" + P200),
        ("orchestrator", "at about 35% of a 1M window (" + P200),
    )

    def text(self, key):
        path = ROOT / key if "/" in key else PROMPTS / f"{key}.md"
        return path.read_text(encoding="utf-8")

    def problems(self, key, text):
        found = prompt_rules.check_doc_text(key, text) if "/" in key else prompt_rules.check_text(key, text)
        return [p for p in found if p.startswith("token-savings")]

    def test_the_real_files_carry_every_phrase(self):
        for key, phrase in self.PINNED:
            with self.subTest(key=key, phrase=phrase):
                self.assertIn(phrase, prompt_rules.normalize(self.text(key)).lower())

    def test_the_real_files_pass_the_token_savings_rules(self):
        for key in sorted({k for k, _ in self.PINNED}):
            with self.subTest(key=key):
                self.assertEqual(self.problems(key, self.text(key)), [])

    def test_deleting_any_phrase_fails_a_token_savings_rule(self):
        for key, phrase in self.PINNED:
            with self.subTest(key=key, phrase=phrase):
                norm = prompt_rules.normalize(self.text(key))
                cut = re.sub(re.escape(phrase), " ", norm, flags=re.I)
                self.assertNotEqual(cut, norm)
                self.assertTrue(self.problems(key, cut))

    def test_the_replaced_wording_is_rejected(self):
        for key, old in self.STALE:
            with self.subTest(key=key, old=old):
                self.assertTrue(self.problems(key, self.text(key) + "\n\n" + old + "\n"))


class AutonomyDecisionsTests(unittest.TestCase):
    """Owner decisions 7239676323 items 1 and 4 and 7239863908 (state issue #399, 2026-11-28): the approver scope takes task-file and
    decision-recording process PRs, and the Google Android SDK terms have a standing acceptance. Each phrase must be in the real file and
    pinned by a `decisions-7239` rule (deleting it fails the checker)."""

    ORCH, APPROVER, LICENSEE = "docs/ORCHESTRATION.md", "approver", "config/licensee/google-sdk-terms.txt"
    SCOPE = ("approver scope, widened again (owner decision, #399 comment 7239676323, 2026-11-28, items 1 and 4)")
    TASKS = ("a pr whose `docs/tasks.toml` change adds or splits tasks (new rows, `depends_on`, `notes`, `risk`), as `owner-batch`")
    CHECKED = ("a review round explicitly checked the new or changed tasks (ids, dependencies, risk, notes, the pr-size rule) with no finding "
               "above nit open against them, `scripts/tasks.py validate` passes, ci is green and there is no veto")
    PROCESS = ("a process-file pr (orchestration.md, agents/prompts/, agents/roles.yaml, review.md, claude.md) whose diff only writes down "
               "owner decisions already posted on the state issue (#399 or #373), each cited by comment id, after a clean review round that "
               "checked every changed line against a cited decision")
    EXACT = ("a change to who may approve or merge what, to guard thresholds, permissions or settings stays with the owner, unless a cited "
             "owner decision states that exact change")
    PINNED = (
        (ORCH, SCOPE), (ORCH, TASKS), (ORCH, CHECKED), (ORCH, PROCESS), (ORCH, EXACT),
        (ORCH, "other owner-retained paths in the same pr still need the owner"),
        (ORCH, "standing acceptance of the google android sdk terms (owner decision, #399 comment 7239863908, 2026-11-28)"),
        (ORCH, "the pr that needs such an artifact adds its exact `group:artifact:version` line to `config/licensee/google-sdk-terms.txt`, "
               "citing this comment, and lists the added lines in its pr body; the reviewer checks each added line is in scope"),
        (ORCH, "still with the owner: any artifact outside those two groups, any other licence, and any other permission acceptance"),
        (ORCH, "except the standing acceptance of the google android sdk terms (#399 comment 7239863908, below)"),
        (ORCH, "licence and permission acceptances (except 7239863908, above)"),
        (ORCH, "agents/prompts/), except a pr that only writes down owner decisions as 7239676323 item 4 states (above)"),
        (ORCH, "the approver's scope also takes task-file prs and decision-recording process prs (owner decision, #399 comment 7239676323 "
               "items 1 and 4; §1.1)"),
        (APPROVER, "also yours (§1.1, #399 comment 7239676323 items 1 and 4): " + TASKS.replace(", as `owner-batch`", "")),
        (APPROVER, "a review round explicitly checked the new or changed tasks (ids, dependencies, risk, notes, the pr-size rule) with no "
                   "finding above nit open against them and `scripts/tasks.py validate` passes"),
        (APPROVER, PROCESS.replace("after a clean", "when a clean")),
        (APPROVER, EXACT.replace("a change to who may approve or merge what, to guard thresholds, permissions or settings stays with the "
                                 "owner", "a pr that changes who may approve or merge what, guard thresholds, permissions or settings is not "
                                 "yours")),
        (APPROVER, "licence and permission acceptances (except 7239863908, above)"),
        (APPROVER, "agents/prompts/), except a pr that only writes down owner decisions as 7239676323 item 4 states (above)"),
        ("orchestrator", "licence and permission acceptances (except 7239863908, above)"),
        ("orchestrator", "agents/prompts/), except a pr that only writes down owner decisions as 7239676323 item 4 states (above)"),
        (LICENSEE, "except lines under the standing acceptance of the google android sdk terms (#399 comment 7239863908)"),
    )

    def text(self, key):
        path = ROOT / key if "/" in key else PROMPTS / f"{key}.md"
        return path.read_text(encoding="utf-8")

    def problems(self, key, text):
        found = prompt_rules.check_doc_text(key, text) if "/" in key else prompt_rules.check_text(key, text)
        return [p for p in found if p.startswith("decisions-7239")]

    def test_the_real_files_carry_every_phrase(self):
        for key, phrase in self.PINNED:
            with self.subTest(key=key, phrase=phrase[:60]):
                self.assertIn(phrase, prompt_rules.normalize(self.text(key)).lower().replace("# ", ""))

    def test_the_real_files_pass_the_rules(self):
        for key in sorted({k for k, _ in self.PINNED}):
            with self.subTest(key=key):
                self.assertEqual(self.problems(key, self.text(key)), [])

    def test_deleting_any_phrase_fails_a_rule(self):
        for key, phrase in self.PINNED:
            with self.subTest(key=key, phrase=phrase[:60]):
                norm = prompt_rules.normalize(self.text(key)).replace("# ", "")
                cut = re.sub(re.escape(phrase), " ", norm, flags=re.I)
                self.assertNotEqual(cut, norm)
                self.assertTrue(self.problems(key, cut))


if __name__ == "__main__":
    unittest.main()
