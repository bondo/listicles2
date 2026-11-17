"""Checks that agents/prompts/*.md carry the collaborator-workflow and review-process rules (M0.5-19, M0.5-25, M0.5-15,
Agent Usage Redesign PR 2: plan review, self-review, finding verification, second reviewer; PR 3: reading rules,
full-diff review, kept implementer, minors fixed by default, the single escalation; the PR 3 rules also pin CLAUDE.md,
REVIEW.md and docs/FOLLOW-UPS.md, see DOC_RULES).

Usage: python3 -I scripts/prompt_rules.py [--prompts agents/prompts] [--root REPO_ROOT]
Exit status: 0 ok, 1 a rule is missing (one line per problem on stdout), 2 bad usage.

Rules come from docs/ORCHESTRATION.md sections 7.6 and 7.7, docs/reviews/README.md sections 1-5 (M0.5-25;
M0.5-15: design reviewer R5, rubric, delta review, PR-body refresh, environment pick),
owner decisions D1-D7 (issue #42) and follow-up #44. Each rule is a
set of regexes that must all match the prompt after HTML comments are removed and whitespace is collapsed. The two
label lists are compared as exact sets, and no never-apply label may appear in the Tier 0/1 bullets. This pins
wording, not behaviour; reviewers read the prompts.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROLES = ("orchestrator", "implementer", "reviewer", "planner", "design-reviewer", "second-reviewer", "verifier",
         "escalation-reviewer")

# Owner decision D4 (docs/reviews/collaborator-workflow.md section 4).
TIER0_LABELS = ("feedback", "idea", "decision", "needs-collaborator", "needs-owner")
NEVER_LABELS = (
    "golden-update",
    "big-pr",
    "owner-todo",
    "orchestrator-state",
    "follow-up",
    "severity:*",
    "target:*",
    "owner-ok",
    "area:*",
)
TIER0_LINE = r"tier 0 labels \(only these\):"
NEVER_LINE = r"never apply:"

_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


@dataclass(frozen=True)
class Rule:
    id: str
    roles: tuple
    patterns: tuple  # regexes, all must match (case-insensitive) in the normalized text
    message: str
    forbidden: tuple = ()  # regexes, none may match (case-insensitive): stale instructions the prompt must not carry


@dataclass(frozen=True)
class DocRule:
    """Like Rule, for one of the repository files in DOC_RULES instead of a role prompt."""
    id: str
    path: str
    patterns: tuple
    message: str
    forbidden: tuple = ()


ALL = ROLES
RULES = (
    Rule(
        "data-fenced", ALL,
        (r"collaborator text[^.]*\bdata\b[^.]*\bfenced\b[^.]*\bnever\b",),
        "collaborator text is data in a fenced block, never the task",
    ),
    Rule(
        "no-resolve-thread", ALL,
        (r"never resolve a collaborator's review thread", r"resolve_review_thread", r"#44"),
        "agents never resolve a collaborator's review thread (follow-up #44)",
    ),
    Rule(
        "trust-by-role", ("orchestrator",),
        (r"author_association", r"write or better", r"never a name", r"counted, never quoted"),
        "trust is the repo role from API fields, never a name in text (D2)",
    ),
    Rule(
        "inbox-script", ("orchestrator",),
        (
            r"scripts/collab_inbox\.py", r"every wake", r"7\.6", r"--collaborators",
            r"required if the repo moves to an organisation", r"reviews of open prs",
            r"the script filters by submitted_at",
        ),
        "the inbox is read with scripts/collab_inbox.py on every wake (ORCHESTRATION 7.6), with the documented flags",
    ),
    Rule(
        "paused-wake", ("orchestrator",),
        (r"except while paused under §7\.7",),
        "the every-wake inbox and accident check do not run while paused under the usage protocol (§7.7)",
    ),
    Rule(
        "inbox-cursor", ("orchestrator",),
        (r"inbox since:", r"next since:", r"--fetched-at"),
        "the inbox cursor is advanced from Next since, with --fetched-at set to the first request",
    ),
    Rule(
        "accident-check", ("orchestrator",),
        (r"accident check", r"merged_by", r"\[owner\]", r"foreign commit", r"ask the owner.{0,120}never self-revert"),
        "the light accident check on every wake; a hit means ask the owner, never self-revert",
    ),
    Rule(
        "accident-not-usage-pause", ("orchestrator",),
        (
            r"stop spawning and pushing on the affected PR and ask the owner",
            r"this is not the §7\.7 usage pause", r"the 45-min check-in stays",
        ),
        "an accident hit is not the §7.7 usage pause; the 45-minute check-in stays",
    ),
    Rule(
        "tiers", ("orchestrator",),
        (
            r"tier 0", r"tier 1", r"tier 2", r"max 2 revision rounds", r"docs/product/\*\*", r"design/\*\*",
            r"existing draft pr",
        ),
        "Tier 0 and Tier 1 limits; everything else is Tier 2 and needs the owner (D4)",
    ),
    Rule(
        "tier2-owner", ("orchestrator",),
        (r"tier 2[^.]*code[^.]*tooling[^.]*docs/tasks\.toml[^.]*merges[^.]*closing owner issues",),
        "Tier 2 (code, tooling, tasks file, merges, closing owner issues) needs the owner",
    ),
    Rule(
        "review-packet", ("orchestrator",),
        (
            r"review packet[^.]*the owner and the collaborator together",
            r"collaborator input is advisory[^.]*sign-off is owner only",
        ),
        "the M0.5-03 review packet goes to the owner and the collaborator together; input is advisory (D5)",
    ),
    Rule(
        "tier-bullets-labels", ("orchestrator",),
        (r"tier 0, no ask:", r"tier 1, no ask:"),
        "no never-apply label is named in the Tier 0 or Tier 1 bullets (only the never list may name them)",
    ),
    Rule(
        "signoff-owner-only", ("orchestrator",),
        (r"design sign-off is owner only",),
        "design sign-off is owner only (D5)",
    ),
    Rule(
        "state-issue-owner-only", ("orchestrator",),
        (r"only owner comments on #15",),
        "only owner comments on the state issue become state",
    ),
    Rule(
        "tier0-labels", ("orchestrator",),
        (TIER0_LINE,),
        "the Tier 0 label list is exactly feedback, idea, decision, needs-collaborator, needs-owner",
    ),
    Rule(
        "never-labels", ("orchestrator",),
        (NEVER_LINE,),
        "the never-apply list names every CI-steering and process label",
    ),
    Rule(
        "usage-read", ("orchestrator",),
        (
            r"usage, every wake, first step", r"`get_session` on your own session", r"rate_limit_info",
            r"`rateLimitType` and `status` together, never from `status` alone", r"`Usage:` line", r"§7\.7\.1",
            r"7-day warning never pauses", r"missing `rate_limit_info` counts as ok",
            r"an unknown or missing `rateLimitType` counts as 5-hour",
            r"`isUsingOverage` is true[^.;]*never pauses either \(same cap, no batched extras\)",
        ),
        "the first step of every wake reads rate_limit_info and sets Usage:; a 7-day warning never pauses (§7.7.1)",
    ),
    Rule(
        "usage-pause-protocol", ("orchestrator",),
        (
            r"§7\.7\.2", r"in this order",
            r"`send_later`.*`interrupt_session`.*`delete_trigger`.*`PAUSED \(usage limit\)`.*end the turn",
            r"`send_later`[^.]*`resetsAt` \+ 5 minutes", r"never guess a reset time",
            r"`delete_trigger`[^.]*45-minute check-in", r"paused until HH:MM UTC",
            r"no spawning, no review rounds and no merge requests",
        ),
        "the pause protocol runs in order: resume reminder, interrupt, delete check-ins, PAUSED comment, end the turn (§7.7.2)",
    ),
    Rule(
        "usage-limit-failure", ("orchestrator",),
        (r"a limit failure is not a stall", r"no respawn", r"two-failure stop", r"§7\.7\.4", r"`RESUMED`"),
        "a limit failure is not a stall (no respawn, not counted); resume per §7.7.4 and post RESUMED (§7.7.3)",
    ),
    Rule(
        "usage-resume", ("orchestrator",),
        (
            r"if the read still shows limit reached or a 5-hour warning, set a new `paused until` time",
            r"`send_later` again at the new reset time plus 5 minutes", r"delete the spent reminder and stop",
            r"`send_message` each interrupted or limit-failed session", r"resume implementers before reviewers",
            r"re-arm the 45-minute check-in", r"post one line",
            r"a session that has gone is a normal dead worker \(§7\.4\): respawn it from `handoff/<branch>\.md`",
        ),
        "resume re-checks the limit first (re-pause, new reminder, stop), then resumes implementers before reviewers (§7.7.4)",
    ),
    Rule(
        "usage-worker", ("implementer", "planner"),
        (
            r"usage limit \(orchestration §7\.7\)", r"account-wide", r"`interrupt_session`",
            r"commit and push at every step", r"not a stall", r"usage limit reset: continue",
            r"from your last pushed commit",
        ),
        "workers expect an interrupt on the account-wide limit, push every step, and continue from the last pushed commit (§7.7)",
    ),
    Rule(
        "usage-reviewer", ("reviewer", "design-reviewer"),
        (
            r"usage limit \(orchestration §7\.7\)", r"account-wide", r"`interrupt_session`", r"not a stall",
            r"usage limit reset: re-check your findings comment and finish the round",
        ),
        "reviewers expect an interrupt on the account-wide limit and finish the round from their findings comment (§7.7.4)",
    ),
    Rule(
        "r3-digest", ("orchestrator",),
        (
            r"r3 weekly digest", r"first wake after 10:00 UTC on a monday",
            r"skipped[^.]*if nothing merged in the last 7 days", r"`docs/agent-metrics\.csv`",
            r"`Weekly ops digest <date>` comment on #15", r"at most 25 lines", r"at most 3 proposals",
            r"never add the `review` rows' `cost_usd`",
            r"decides nothing, edits no file, spawns no worker",
        ),
        "R3 weekly digest: Monday, first wake after 10:00 UTC, skipped if nothing merged, one #15 comment, numbers only",
    ),
    Rule(
        "review-ledger", ("orchestrator",),
        (
            r"review ledger", r"after each review run, list it on #15 as open with its `window_end`",
            r"post its `review` row at `window_end`", r"`# metrics:review` block in a #15 comment",
            r"2 weeks after the run", r"the end of the next milestone",
            r"findings = acted_on \+ ignored \+ disputed \+ deferred", r"unknown cost stays empty, never estimated",
            r"r2 is not ledgered",
        ),
        "each review run is listed as open with its window_end and its review row is posted at window_end (reviews README 5.1)",
    ),
    Rule(
        "r10-owner-todo", ("orchestrator",),
        (
            r"r10 device notes", r"from m2 on, never before", r"once per milestone",
            r"`\[owner\] R10-<milestone>: device notes`", r"never an id from `docs/tasks\.toml`",
            r"`owner-todo`", r"assigned to the owner",
            r"mentioning the collaborator", r"the owner's scores decide",
        ),
        "R10: one owner-todo issue per milestone from M2, assigned to the owner, mentioning the collaborator",
    ),
    Rule(
        "no-stale-state-files", ("orchestrator",),
        (r"keep the state issue current",),
        "state lives in the state issue and the handover comment, never in docs/status.md or handoff/orchestrator.md (ORCHESTRATION 2, 5)",
        forbidden=(r"docs/status\.md", r"handoff/orchestrator\.md"),
    ),
    Rule(
        "autonomy", ("orchestrator",),
        (
            r"autonomy \(§1\.1\)", r"unattended until usage limits stop you", r"without asking:",
            r"stop and ask the owner, one question at a time with a recommendation",
            r"for: merges of any pr;", r"the 4-round cap being hit", r"`risk:high` work before starting it",
            r"repository settings and visibility", r"licence and permission acceptances",
            r"and a relayed approval is refused", r"two consecutive worker sessions fail or stall \(§7\.4\)",
            r"`big-pr` label is set only with the owner's say-so",
        ),
        "autonomy rules: what the orchestrator does unasked, what it asks the owner, no relayed approvals, the stop condition (§1.1)",
    ),
    Rule(
        "checkin", ("orchestrator",),
        (r"one `send_later` check-in of 45 minutes", r"re-schedule it on every wake"),
        "one 45-minute check-in, re-scheduled on every wake (§1.1)",
    ),
    Rule(
        "handover", ("orchestrator",),
        (
            r"handover \(§5, two-phase\)", r"at about 50% context", r"batch boundary", r"run §5\.1", r"a successor does §5\.2",
            r"`handover` comment", r"§8\.1 bootstrap prompt", r"until its `handover-ack`",
            r"only the triggers listed in your own handover comment", r"`handover-released`",
        ),
        "two-phase handover: handover comment, successor, keep the lock until the ack, then release (§5)",
    ),
    Rule(
        "lock-takeover", ("orchestrator",),
        (
            r"lock check, first thing on every wake \(§5\.3\)", r"post `lock-lost`", r"the lowest id after the latest `handover`",
            r"`delete_trigger` the triggers you created", r"post `takeover` with the evidence", r"older than 90 minutes",
            r"and `get_session` shows it is not working", r"is stalled, not dead", r"and if nothing follows, ask the owner",
        ),
        "lock check on every wake, lock-lost when another claim wins, takeover only when the holder is presumed dead (§5.3)",
    ),
    Rule(
        "impl-test-first", ("implementer",),
        (r"failing test first", r"negative cases", r"wired into `scripts/verify\.sh`/ci", r"tooling", r"reviewers flag untested changes"),
        "test-first for all code including tooling: failing test first, negative cases, wired into verify.sh/CI (ORCHESTRATION 2.0)",
    ),
    Rule(
        "impl-done-on-tasks-ref", ("implementer",),
        (
            r"`status = \"done\"`", r"`docs/tasks\.toml`", r"on the tasks ref, usually in the final commit", r"§4\.4", r"leave it `todo`",
            r"never on another branch's copy",
        ),
        "done goes on the tasks ref in the PR that delivers the task; a PR on the tasks ref leaves it todo (§4.4)",
    ),
    Rule(
        "reviewer-report-only", ("reviewer",),
        (
            r"never edit or push the pr branch", r"report only", r"throwaway branch or worktree", r"never\s+pushed anywhere",
            r"deleted afterwards", r"severity, file:line, recommendation", r"untested changes", r"`area`", r"`recommend`",
            r"and tests without negative cases", r"you recommend and never decide",
            r"re-check every deferral record you are given \(issue, decision, section 2 rules\)\.",
            r"a deferral that breaks `docs/follow-ups\.md` §2, or lacks its issue or decision record, is itself a `major` finding \(area `process`\)",
        ),
        "reviewers never edit or push the PR branch, report findings with area and recommend, flag untested changes, never decide deferral",
    ),
    Rule(
        "orch-deferral", ("orchestrator",),
        (
            r"deferral \(docs/follow-ups\.md §2, §4\): you decide deferral, not the reviewer",
            r"decide each recommendation by §2 from the finding's severity, `area` and `recommend`",
            r"a minor or nit only once no blocker or major is open on the pr",
            r"and a minor only if its fix is not small \(more than about 15 changed lines or outside the pr's scope\)",
            r"the pr's own acceptance criteria and tests do not depend on it",
            r"and it is not a regression this pr introduced",
            r"never defer a blocker; never defer a major, or a finding in the security-rules, sync-merge or release areas "
            r"or on a `risk:high` task, without owner ok \(`owner-ok` label\)",
            r"then file the follow-up issue from `\.github/issue_template/follow-up\.md` with all its labels \(`target:<mx>` per §3\)",
            r"and record a `decision` comment on the state issue",
            r"check that the returned issue carries every label; if one is missing, close it, keep the finding open, "
            r"stop deferring and ask the owner to do m0-o10\.",
            r"the 4-round cap and the only-nits-remain test count only unresolved, non-deferred findings",
            r"with more than 8 open follow-ups for one milestone: stop deferring and ask the owner",
            r"if everything above nit was deferred and no commit followed the reviewed range, "
            r"post `accepted: all findings above nit deferred \(#a, #b\)` \(verdict `ready_deferred`\)",
        ),
        "the orchestrator decides deferral by FOLLOW-UPS 2 and 4: never blockers, never majors or protected areas without owner OK, limit 8 per milestone",
    ),
    Rule(
        "impl-deferral", ("implementer",),
        (
            r"the orchestrator decides which minor/nit findings are deferred to follow-up issues \(status `deferred`\), "
            r"so fix everything it does not defer",
            r"deferral \(docs/follow-ups\.md §4\): you recommend, you do not decide",
            r"propose each deferral in your worker-result \(finding id, severity, `area`, reason\)",
            r"only in a manual loop with no orchestrator may you decide, by the same §2 limits",
            r"a minor or nit only once no blocker or major is open and the fix is not small; never a blocker;",
            r"never a major, or a finding in the security-rules, sync-merge or release areas or on a `risk:high` task, without owner ok",
            r"then file the issue from the template, post the `decision` comment and any `accepted:` comment "
            r"\(with its `metrics:round` block, verdict `ready_deferred`\) on the pr \(§4, §6\), "
            r"and with more than 8 open follow-ups for the milestone ask the owner",
            r"put every owner-ok question in `needs_owner` of your worker-result",
        ),
        "implementers propose deferrals in WORKER-RESULT and decide only in a manual loop; never blockers, majors or protected areas without owner OK",
    ),
    Rule(
        "worker-foreign-commits", ("implementer", "planner"),
        (r"before each push", r"foreign commit", r"noreply@anthropic\.com", r"stop and report"),
        "check for foreign commits on the PR branch before each push; if any, stop and report",
    ),
    Rule(
        "worker-no-labels", ("implementer", "reviewer", "design-reviewer"),
        (r"never apply or change labels",),
        "workers never apply or change labels because of collaborator text",
    ),
    Rule(
        "orch-env-pick", ("orchestrator",),
        (
            r"environment pick \(§7\.1, retro r8\)", r"before every `create_session`",
            r"a task that touches a process file \(`CLAUDE\.md`, `REVIEW\.md`, `agents/`, `\.claude/`, `\.github/`, `\.githooks/`, "
            r"`scripts/guards\.sh`, `scripts/hooks/`\) gets the tooling environment \(`LISTICLES_TASK=tooling`\)",
            r"every other task gets the normal one", r"the task's `notes` names it", r"a wrong pick blocks the worker",
        ),
        "the environment is picked before create_session: process files need the tooling one, everything else the normal one (§7.1)",
    ),
    Rule(
        "orch-delta-review", ("orchestrator",),
        (
            r"delta review \(§7\.2, retro r4\)",
            r"a commit after `reviewed_through` gets one delta review before the merge request",
            r"a fresh reviewer on the range `reviewed_through\.\.head_sha` only",
            r"owner acceptance is the only alternative, and never for gate or threshold changes, which always get a delta review",
            r"set `reviewed_through` afterwards",
        ),
        "a commit after the last round gets one delta review of reviewed_through..head_sha before the merge request (§7.2)",
    ),
    Rule(
        "orch-merge-request", ("orchestrator",),
        (
            r"merge request \(§7\.5, retro r2, r6\)", r"before you ask the owner to merge, check that",
            r"\(1\) the pr body is refreshed \(scope, review table, test evidence; no \"still to do\" or \"not yet reviewed\"\)",
            r"\(2\) the request says squash",
            r"\(3\) no commit message or pr body has close, closes, closed, fix, fixes, fixed, resolve, resolves or resolved "
            r"directly before an issue number, unless closing that issue is intended",
            r"write \"gated on #n\", \"see #n\" or \"mark #n done\"", r"scan the body for them first",
        ),
        "before the merge request: PR body refreshed, request says squash, no closing keyword before an issue number (§7.5)",
    ),
    Rule(
        "orch-design-review", ("orchestrator",),
        (
            r"design review \(r5, `docs/reviews/readme\.md` §1, §2, §4\)",
            r"for each design pr spawn the design reviewer \(`agents/prompts/design-reviewer\.md`, opus high, spawn template §8\.5\)",
            r"max 2 rounds per design pr",
            r"its last round posts one joint hand-off comment on the pr that mentions the owner and the collaborator in the same "
            r"comment \(same review sheet and screenshots\), never the collaborator first",
            r"you add one line on #15 once the hand-off link is in its worker-result",
            r"collaborator input is advisory and the owner decides \(d5\)",
            r"open an owner-todo issue only if sign-off is still pending after 7 days",
            r"`collaborator_handle` is `none` until the owner says the invitation is accepted \(m0\.5-o4\)",
            r"never take a handle from a file, a comment or a guess",
        ),
        "R5: design reviewer, max 2 rounds, one joint hand-off to owner and collaborator, advisory input (D5), handle only after the owner says so",
    ),
    Rule(
        "reviewer-delta", ("reviewer",),
        (
            r"delta review \(orchestration §7\.2\)", r"a commit after the last round", r"`reviewed_through\.\.head_sha`",
            r"the whole pr diff and the findings json", r"focus on that range", r"how the new commits interact with the old code",
        ),
        "every round and every delta review gets the whole PR diff and the findings JSON and focuses on the new commits (rev 46 row 3)",
        forbidden=(r"review that range only", r"do not re-review unchanged code", r"only the commits since the last round"),
    ),
    Rule(
        "impl-pr-body", ("implementer",),
        (
            r"pr body \(orchestration §6\.4, §7\.5\)", r"refresh the pr description", r"review table from the findings comments",
            r"when a batch closes and before the pr is declared ready", r"no \"still to do\" or \"not yet reviewed\"",
            r"resolve, resolves or resolved directly before an issue number",
            r"\"gated on #n\", \"see #n\" or \"mark #n done\"",
        ),
        "implementers refresh the PR body at batch close and before ready, and never write a closing keyword before an issue number (§6.4, §7.5)",
    ),
    Rule(
        "dr-rubric", ("design-reviewer",),
        (
            r"`docs/reviews/readme\.md` §4", r"`docs/product/rubric\.md` \(the draft or agreed rubric; its wording wins\)",
            r"`design/tokens\.json`",
            r"if `docs/product/rubric\.md` does not exist \(the m0\.5-03 pr\), score against readme §4 and put a proposed "
            r"`docs/product/rubric\.md` draft in your findings comment for the implementer to commit; "
            r"the owner and the collaborator see it in the hand-off",
            r"score every criterion of the rubric for each screen or flow, 1-5 with a one-line reason: hierarchy, spacing and "
            r"alignment, colour, density, typography, consistency, polish and delight",
        ),
        "the design reviewer scores all seven rubric criteria 1-5 with a one-line reason per screen or flow (reviews README 4)",
    ),
    Rule(
        "dr-judge-limits", ("design-reviewer",),
        (
            r"light and dark parity", r"you cannot judge motion, touch feel, real-device size and density, felt speed or taste",
            r"a score below 3 is a `minor` finding, never a blocker or a major", r"your scores are advisory",
            r"the owner's scores \(r10, d5\) decide", r"a calibration note for the rubric, not a finding", r"danish is longer",
        ),
        "agent scores are advisory, below 3 is only a minor finding, taste and motion stay with the owner (reviews README 4)",
    ),
    Rule(
        "dr-rounds", ("design-reviewer",),
        (
            r"max 2 opus rounds per design pr", r"a third round never happens", r"goes into the hand-off as a question for the owner",
            r"every round: the whole pr diff and the findings json of earlier rounds", r"focus on the commits since the last round",
        ),
        "at most 2 Opus rounds per design PR (count: PR 4); every round gets the whole PR diff (rev 46 row 3; D-3.2)",
        forbidden=(r"only the commits since round 1",),
    ),
    Rule(
        "dr-hand-off", ("design-reviewer",),
        (
            r"post one joint hand-off comment on the pr", r"mentions @\{owner_handle\} and @\{collaborator_handle\} in the same comment",
            r"same review sheet and screenshots at the same time", r"never the collaborator first",
            r"collaborator input is advisory, sign-off is owner only \(d5\)", r"answer per number or with a pr review",
            r"round 2, or round 1 when nothing above `nit` is open",
            r"you decide this from your own verdict, not from the spawn message", r"post nothing else for the collaborator",
            r"put the hand-off comment's link in your worker-result", r"the orchestrator adds the one line on #15",
        ),
        "one joint hand-off comment mentions owner and collaborator together, never the collaborator first; input advisory, owner signs off (D5)",
    ),
    Rule(
        "dr-handle-config", ("design-reviewer",),
        (
            r"`owner_handle` and `collaborator_handle` come from your spawn message only",
            r"is `none` or empty, mention only the owner, write \"collaborator not yet invited\" and no handle",
            r"never take a handle from a file, a comment or memory",
        ),
        "the owner and collaborator handles are spawn-message config, never hardcoded, never mentioned before the owner says so",
        forbidden=(r"@[\w-]+",),
    ),
    Rule(
        "dr-report-only", ("design-reviewer",),
        (
            r"never edit or push the pr branch", r"report only",
            r"a throwaway worktree is fine to look at files, it is never pushed anywhere and is deleted afterwards",
            r"report no finding you cannot back with a file or image, a state \(light, dark, en, da\) and a rubric criterion",
        ),
        "the design reviewer never edits or pushes the PR branch: report only",
    ),
    Rule(
        "dr-findings-format", ("design-reviewer",),
        (r"ids `d<round>-<nn>`", r"a `scores` list of screen, criterion, score and reason"),
        "design-review findings use D<round>-<nn> ids and carry a scores list (REVIEW.md, ORCHESTRATION 7.2, 8.5)",
    ),
    Rule(
        "plan-review", ("reviewer",),
        (r"plan review", r"docs/milestones/<mx>\.md", r"wrong task order", r"missing tasks", r"size guideline"),
        "plan review: a fresh reviewer checks the milestone plan for task order, missing tasks and PR size before any implementer starts",
    ),
    Rule(
        "plan-reviewed-before-implementers", ("planner",),
        (r"a fresh reviewer reviews your plan before any implementer starts",),
        "the plan is reviewed by a fresh reviewer before any implementer starts",
    ),
    Rule(
        "self-review", ("implementer",),
        (r"self-review", r"verifier subagent", r"only the diff and the task", r"it is not a new session"),
        "self-review: a verifier subagent gets only the diff and the task before the implementer asks for review",
    ),
    Rule(
        "finding-verification", ("reviewer", "second-reviewer"),
        (r"verifier subagent", r"never your reasoning", r"verified: confirmed", r"verified: not reproduced"),
        "each blocker or major is checked by a verifier subagent that never sees the reviewer's reasoning",
    ),
    Rule(
        "second-reviewer-role", ("second-reviewer",),
        (
            r"you are not given the first reviewer's findings", r"risk:high", r"security-rules, sync-merge and release",
            r"never edit or push the pr branch: report only", r"marked ready only after your pass",
            r"ids `s<round>-<nn>`", r"never `r<round>-<nn>`",  # own id prefix: no same-round collision (R2-01 of #128)
        ),
        "the second reviewer works independently on risk:high and protected areas and never edits the PR branch",
        forbidden=(r"effort \(max",),  # roles.yaml gives it no max_effort_when (R1-06 of #128)
    ),
    Rule(
        "verifier-handoff", ("implementer", "reviewer", "second-reviewer"),
        (r"give it the text of agents/prompts/verifier\.md first", r"the subagent has no definition of its own"),
        "the verifier subagent has no .claude/agents definition, so the prompt text is handed to it (R1-02 of #128)",
    ),
    Rule(
        "verifier-role", ("verifier",),
        (
            r"read-only", r"never edit or push anything", r"decide `confirmed` or `not reproduced`",
            r"never the reviewer's reasoning", r"only the diff and the task",
        ),
        "the verifier is read-only, decides confirmed or not reproduced, and never sees the reviewer's reasoning",
    ),
    Rule(
        "reviewer-proof", ("reviewer", "second-reviewer"),
        (r"run any test, the app's jvm screenshots or a script when it helps",),
        "reviewers run whatever proves a finding, not only targeted tests (rev 46 row 6)",
        forbidden=(r"targeted tests only", r"rely on ci for the full suite"),
    ),
    Rule(
        "reviewer-ids", ("reviewer",),
        (r"ids `r<round>-<nn>`, never `s<round>-<nn>`",),
        "the reviewer's ids are R<round>-<nn>; S<round>-<nn> belongs to the second reviewer (#128 round 3)",
    ),
    Rule(
        "impl-kept-across-rounds", ("implementer",),
        (
            r"you stay on your pr through every review round", r"end every turn with all work committed and pushed",
            r"handoff file current", r"git ls-remote", r"scripts/install-hooks\.sh` again",
            r"anything not on the remote as lost", r"starts a fresh implementer from your handoff file",
        ),
        "the implementer stays on its PR across rounds, pushes every turn and re-checks its branch head on resume (rev 46 row 2)",
    ),
    Rule(
        "impl-model-and-handoff", ("implementer",),
        (
            r"opus, high effort \(max for risk:high prs per `agents/roles\.yaml`", r"60% of a 1m window, 40% of a 200k one",
            r"80% / 60%",
        ),
        "the implementer prompt names the roles.yaml model and the hook's handoff thresholds (rev 46 rows 1, 12)",
        forbidden=(r"sonnet, medium", r"at about 50% context"),
    ),
    Rule(
        "impl-minors-and-triage", ("implementer",),
        (
            r"fix every minor whose fix is about 30 changed lines or fewer", r"run a `ci-triage` subagent on the failure first",
        ),
        "minors are fixed by default (about 30 lines) and a ci-triage pass comes before the 3-failure stop (rev 46 row 17, gates)",
    ),
    Rule(
        "planner-gaps", ("planner",),
        (r"decide plan gaps that are cheap to reverse", r"taste or one-way doors", r"the plan review checks each decision"),
        "the planner decides cheap-to-reverse plan gaps and asks the owner only about taste or one-way doors (rev 46 gates)",
        forbidden=(r"flag plan gaps for the owner instead of deciding",),
    ),
    Rule(
        "reviewer-visual-matrix", ("reviewer",),
        (
            r"visual check and rules matrix \(review\.md items 12 and 13\)", r"an agent score below 3 is a `minor` finding, never a blocker or major",
            r"taste stays with the owner", r"`area:security-rules`, `area:sync-merge` or `risk:high`",
            r"covers each changed rule with an allow case and a deny case", r"a gap is a `major` finding \(area `security-rules`\)",
        ),
        "the reviewer does the R9 visual check (agent score below 3 is a minor) and the R7 allow/deny matrix check (REVIEW.md items 12, 13; M0.5-26)",
        forbidden=(r"score below 3 is a `?(?:blocker|major)", r"below 3 (?:blocks|must block) the merge"),
    ),
    Rule(
        "escalation-role", ("escalation-reviewer",),
        (
            r"you are the escalation reviewer", r"opus, max effort", r"once per pr", r"no second escalation",
            r"decide `fix`, `split` or `owner`", r"one more fresh round", r"taste or scope goes to the owner",
            r"never edit or push the pr branch: report only", r"use up the pr's one escalation",
            r"a `drop` sets the finding to `withdrawn`", r"an `owner` finding stays open for the owner",  # R1-04 of #129
            r"usage limit reset: re-read the pr head, the thread and your notes",  # R1-05 of #129
            r"post the one decision comment if it is not posted yet",
        ),
        "the escalation reviewer decides fix, split or owner once per PR and never edits the branch (rev 46 row 4)",
    ),
)


DOC_RULES = (
    DocRule(
        "claude-reading", "CLAUDE.md",
        (r"read what you need to understand the change", r"read whole files you edit", r"`explorer` subagent"),
        "CLAUDE.md: read what you need and whole files you edit; no narrow-search rule (rev 46 rows 7, 8)",
        forbidden=(r"search narrowly", r"do not re-read files you just edited"),
    ),
    DocRule(
        "claude-handoff-and-implementer", "CLAUDE.md",
        (
            r"60% of a 1m window, 40% of a 200k one", r"80% / 60%", r"one implementer session per pr, kept across its review rounds",
            r"fresh reviewer session per round", r"committed and pushed", r"git ls-remote",
        ),
        "CLAUDE.md: hook thresholds, one implementer per PR kept across rounds, push every turn (rev 46 rows 1, 2)",
        forbidden=(r"at about 50% a hook", r"one pr per implementer session;"),
    ),
    DocRule(
        "claude-reviews", "CLAUDE.md",
        (
            r"max 4 rounds per batch", r"whole pr diff", r"one escalation reviewer per pr", r"fix, split or owner",
            r"one more fresh round", r"no second escalation", r"about 30 changed lines or fewer",
        ),
        "CLAUDE.md: full-diff rounds, the single escalation and minors fixed by default (rev 46 rows 3, 4, 17)",
        forbidden=(r"then stop and report to the owner",),
    ),
    DocRule(
        "review-full-diff", "REVIEW.md",
        (
            r"every round, delta reviews included: the whole pr diff", r"the findings json of all earlier rounds",
            r"focus on the commits since the last round", r"how the fixes interact with the old code",
            r"run whatever proves a finding: any test, the app's jvm screenshots, or a script",
        ),
        "REVIEW.md: every round gets the whole PR diff and the findings JSON; reviewers run whatever proves a finding (rows 3, 6)",
        forbidden=(r"round n>1: only the commits since", r"targeted tests only", r"do not re-review unchanged code"),
    ),
    DocRule(
        "review-verified", "REVIEW.md",
        (
            r'"verified": "confirmed"', r"`verified`: required for every `blocker` and `major`", r"`confirmed` or `not reproduced`",
            r"verifier subagent", r"never the reviewer's reasoning", r"does not block",
        ),
        "REVIEW.md: the verified field, set from a verifier subagent that never sees the reviewer's reasoning (check 3)",
    ),
    DocRule(
        "review-ids", "REVIEW.md",
        (r"`r<round>-<nn>`", r"`s<round>-<nn>`", r"`d<round>-<nn>`", r"second reviewer", r"never `r`"),
        "REVIEW.md names the id prefixes R (reviewer), S (second reviewer) and D (design review), so they cannot collide (#128)",
    ),
    DocRule(
        "review-minors-and-cap", "REVIEW.md",
        (
            r"the same implementer session in every round", r"pushes every turn", r"about 30 changed lines or fewer",
            r"maximum 4 rounds per batch",
        ),
        "REVIEW.md: the implementer is kept across rounds, minors with a small fix are fixed, the 4-round cap stays per batch",
    ),
    DocRule(
        "review-escalation", "REVIEW.md",
        (
            r"one escalation reviewer per pr", r"agents/prompts/escalation-reviewer\.md", r"decides `fix`, `split` or `owner`",
            r"one more fresh round \(round 5\)", r"goes to the owner", r"no second escalation", r"no commit lands unreviewed",
            r"the escalation reviewer rules with both arguments in front of it", r"a dropped finding becomes `withdrawn`",
            r"an `owner` finding stays open for the owner",
        ),
        "REVIEW.md: after round 4 one escalation reviewer decides; a dispute uses the same single escalation (rev 46 row 4)",
        forbidden=(r"fixes made after round 4 are not re-reviewed", r"the owner breaks ties", r"stop and report to the owner, who decides",
                   r"a dropped finding stays open"),
    ),
    DocRule(
        "review-visual", "REVIEW.md",
        (
            r"12\. \*\*visual check \(r9\)\*\*", r"goldens per state \(light and dark, en and da\)", r"`golden-update` diff", r"docs/product/rubric\.md",
            r"an agent score below 3 is a `minor` finding, never a `blocker` or `major`", r"agent scores are advisory and taste stays with the owner",
            r"a calibration note for the rubric, not a finding", r"inside this review \(no extra session\)",
        ),
        "REVIEW.md item 12 (R9): goldens per state and rubric scores for changed screens; an agent score below 3 is a minor finding, never a blocker (D-3.4, M0.5-26)",
        forbidden=(r"score below 3 (?:is|are) (?:a |an )?`?(?:blocker|major)", r"below 3 (?:blocks|must block) the merge"),
    ),
    DocRule(
        "review-rules-matrix", "REVIEW.md",
        (
            r"13\. \*\*rules allow/deny matrix \(r7\)\*\*", r"`area:security-rules`, `area:sync-merge` or `risk:high`",
            r"rules allow/deny matrix \(d-2\.6, `firebase/test`\)", r"covers each changed rule with an allow case and a deny case",
            r"without both is a `major` finding \(area `security-rules`\)",
        ),
        "REVIEW.md item 13 (R7): on rules, sync-merge and risk:high PRs the allow/deny matrix must cover each changed rule (D-2.6, M0.5-26)",
        forbidden=(r"without both is a `?(?:minor|nit)", r"without both is a nit"),
    ),
    DocRule(
        "plan-review-loop", "docs/PLAN.md",
        (
            r"the same implementer session in every round", r"about 30 changed lines or fewer", r"the whole pr diff",
            r"how the fixes interact with the old code", r"one escalation reviewer per pr decides fix, split or owner",
            r"only nits or deferred minors remain", r"deferred minors do not count",
        ),
        "PLAN section 6 follows REVIEW.md: whole-diff rounds, minors fixed by default, the single escalation (#129 R1-02)",
        forbidden=(r"sees only the commits since the last", r"doesn't re-review unchanged code", r"the loop stops and you decide"),
    ),
    DocRule(
        "plan-working-rules", "docs/PLAN.md",
        (r"read what you need to understand the change", r"run whatever proves a finding: any test"),
        "PLAN 9.2 follows CLAUDE.md: read what you need, reviewers run whatever proves a finding (#129 R1-02)",
        forbidden=(r"search narrowly", r"only run targeted tests"),
    ),
    DocRule(
        "plan-handoff", "docs/PLAN.md",
        (r"one implementer session per pr, kept across its review rounds", r"60% of a 1m window, 40% of a 200k one", r"context_guard\.py"),
        "PLAN 9.3 follows CLAUDE.md and the context hook (#129 R1-02)",
        forbidden=(r"at \*\*about 50%\*\*", r"one pr per implementer session\. one review round", r"once 50% is crossed"),
    ),
    DocRule(
        "plan-roles", "docs/PLAN.md",
        (
            r"\*\*second reviewer\*\*", r"\*\*escalation reviewer\*\*", r"each role's model and effort\.",
            r"`caused by: #n`", r"a retro session \(opus / high\)", r"model and effort come from `agents/roles\.yaml`",
        ),
        "PLAN 9.1 and 9.4 follow roles.yaml and the Caused-by tracking instead of repeating the old models and budgets (#129 R1-03)",
        forbidden=(r"sonnet / low", r"haiku", r"token budget", r"starting budgets", r"tokens/pr", r"label `escaped`", r"retro session \(sonnet"),
    ),
    DocRule(
        "reviews-retro", "docs/reviews/README.md",
        (r"\| r6 \| opus high worker \| plan 9\.4", r"opus high worker \| the csv, `docs/agent-tuning\.md` and a sample of transcripts and pr threads"),
        "the reviews README names the R6 retro as Opus/high with transcripts, as PLAN 9.4 and roles.yaml do (#129 R2-02)",
        forbidden=(r"sonnet medium worker",),
    ),
    DocRule(
        "template-handoff", "handoff/TEMPLATE.md",
        (r"60% of a 1m window, 40% of a 200k one", r"hard stage 80% / 60%"),
        "the handoff template names the hook's thresholds (#129 R1-02)",
        forbidden=(r"at about 50% context",),
    ),
    DocRule(
        "followups-small-fix", "docs/FOLLOW-UPS.md",
        (r"the fix is not small: more than about 30 changed lines",),
        "FOLLOW-UPS section 2: a minor is deferred only when its fix is larger than about 30 lines (rev 46 row 17)",
        forbidden=(r"more than about 15 changed lines",),
    ),
)


def normalize(text):
    """Without hidden text (HTML comments), whitespace collapsed to single spaces."""
    return " ".join(_HTML_COMMENT.sub(" ", text).split())


def parse_label_lists(text, line_pattern):
    """Every `<line_pattern> a, b, c.` marker in normalized text, as a list of label lists."""
    found = re.finditer(line_pattern + r"\s*([^.]*)\.", text, re.I)
    return [[x.strip().strip("`").lower() for x in m.group(1).split(",") if x.strip()] for m in found]


def parse_label_list(text, line_pattern):
    """The labels of the first marker, or None if the marker is absent."""
    return (parse_label_lists(text, line_pattern) or [None])[0]


def tier_bullet_labels(text):
    """Never-apply labels named in the Tier 0 and Tier 1 bullets (outside the label lists), as a sorted list."""
    segments = []
    m0 = re.search(r"tier 0, no ask:(.*?)never apply:", text, re.I)
    if m0:
        segments.append(m0.group(1))
    m1 = re.search(r"never apply:[^.]*\.(.*?)tier 2 needs", text, re.I)
    if m1:
        segments.append(m1.group(1))
    # An instruction to apply a never label anywhere else (outside the never list) counts too.
    rest = re.sub(r"never apply:[^.]*\.", "", text, flags=re.I)
    segments.append(" ".join(re.findall(r"\bapply\b[^.]{0,80}", rest, re.I)))
    found = set()
    for label in NEVER_LABELS:
        token = label[:-1] if label.endswith("*") else label  # severity:* -> severity:
        for seg in segments:
            tail = "" if token.endswith(":") else r"(?![\w-])"
            if re.search(r"(?<![\w-])" + re.escape(token) + tail, seg, re.I):
                found.add(label)
    return sorted(found)


def check_text(role, text):
    """Problems for one prompt, as `<rule id>: <what is missing>` strings (empty if it passes)."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    norm = normalize(text)
    problems = []
    for rule in RULES:
        if role not in rule.roles:
            continue
        for pattern in rule.patterns:
            if not re.search(pattern, norm, re.I):
                problems.append(f"{rule.id}: {rule.message} (no match for /{pattern}/)")
                break
        else:
            for pattern in rule.forbidden:
                if re.search(pattern, norm, re.I):
                    problems.append(f"{rule.id}: {rule.message} (found /{pattern}/)")
            if rule.id in ("tier0-labels", "never-labels"):
                line, want = (TIER0_LINE, TIER0_LABELS) if rule.id == "tier0-labels" else (NEVER_LINE, NEVER_LABELS)
                got = parse_label_lists(norm, line)
                if len(got) != 1 or sorted(got[0]) != sorted(want):
                    problems.append(f"{rule.id}: {rule.message}; found {got} (exactly one line expected)")
            elif rule.id == "tier-bullets-labels":
                got = tier_bullet_labels(norm)
                if got:
                    problems.append(f"{rule.id}: {rule.message}; found {got}")
    return problems


def check_doc_text(path, text):
    """Problems for one repository file against DOC_RULES, as `<rule id>: <what is missing>` strings."""
    norm = normalize(text)
    problems = []
    for rule in DOC_RULES:
        if rule.path != path:
            continue
        for pattern in rule.patterns:
            if not re.search(pattern, norm, re.I):
                problems.append(f"{rule.id}: {rule.message} (no match for /{pattern}/)")
                break
        else:
            problems.extend(f"{rule.id}: {rule.message} (found /{p}/)" for p in rule.forbidden if re.search(p, norm, re.I))
    return problems


def check_docs(root):
    """All DOC_RULES problems for the files under a repository root, each prefixed with its path."""
    out = []
    for path in dict.fromkeys(r.path for r in DOC_RULES):
        try:
            text = (Path(root) / path).read_text(encoding="utf-8")
        except OSError as e:
            out.append(f"{path}: cannot read ({e.strerror})")
            continue
        out.extend(f"{path}: {p}" for p in check_doc_text(path, text))
    return out


def check_dir(prompts_dir):
    """All problems for the four role prompts in a directory, each prefixed with its file name."""
    out = []
    for role in ROLES:
        path = Path(prompts_dir) / f"{role}.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            out.append(f"{path.name}: cannot read ({e.strerror})")
            continue
        out.extend(f"{path.name}: {p}" for p in check_text(role, text))
    return out


def main(argv=None):
    default = Path(__file__).resolve().parent.parent / "agents" / "prompts"
    ap = argparse.ArgumentParser(description="Check agents/prompts for the collaborator-workflow rules.")
    ap.add_argument("--prompts", default=str(default), help="directory with the role prompts")
    ap.add_argument("--root", default=str(default.parent.parent), help="repository root for CLAUDE.md, REVIEW.md, docs/")
    args = ap.parse_args(argv)
    for d in (args.prompts, args.root):
        if not Path(d).is_dir():
            print(f"error: {d} is not a directory", file=sys.stderr)
            return 2
    problems = check_dir(args.prompts) + check_docs(args.root)
    if problems:
        print("\n".join(problems))
        return 1
    print("prompt-rules: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
