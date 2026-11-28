"""Checks that agents/prompts/*.md carry the collaborator-workflow and review-process rules (M0.5-19, M0.5-25, M0.5-15,
Agent Usage Redesign PR 2: plan review, self-review, finding verification, second reviewer; PR 3: reading rules,
full-diff review, kept implementer, minors fixed by default, the single escalation; PR 4: orchestration (pipeline-flow concurrency, throttle,
gates, merge agent, archive sweep, design rounds 3). DOC_RULES also pin CLAUDE.md, REVIEW.md, docs/FOLLOW-UPS.md,
docs/PLAN.md, docs/ORCHESTRATION.md, docs/COLLABORATING.md, docs/BRANCH-PROTECTION.md, docs/reviews/README.md,
docs/reviews/collaborator-workflow.md, docs/milestones/M1.md, config/licensee/google-sdk-terms.txt, agents/roles.yaml and handoff/TEMPLATE.md).

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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROLES = ("orchestrator", "implementer", "reviewer", "planner", "design-reviewer", "second-reviewer", "verifier",
         "escalation-reviewer", "approver")

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
# Owner decision, #15 comment 7082564807: the orchestrator adds `golden-update` after a review round found the goldens intended.
_GOLDEN_CHECKED = (r"add the `golden-update` label to a pr only after that pr's review round has checked the new or changed screenshot goldens "
                   r"and found them intended \(no reviewer finding open against them\)")
# The label given to the wrong party, or back to the owner alone.
_GOLDEN_BAD = (
    r"only the owner (?:may |can |should )?(?:add|apply|set)s? the `golden-update`",
    r"`golden-update` (?:label )?(?:stays|is|remains) owner-only",
    r"(?:implementers?|workers?|collaborators?|reviewers?|second reviewers?|escalation reviewers?|design reviewers?|approvers?|merge agents?) "
    r"(?:(?:may|can|will|should) )?(?:add|apply|set)s? the `golden-update`",
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
    # callable(text) -> patterns found per sentence, negation-aware (resolve_permissions); headings, blank lines and bullets end a sentence
    forbidden_sentences: Callable[[str], list] | None = None


@dataclass(frozen=True)
class DocRule:
    """Like Rule, for one of the repository files in DOC_RULES instead of a role prompt."""
    id: str
    path: str
    patterns: tuple
    message: str
    forbidden: tuple = ()
    forbidden_sentences: Callable[[str], list] | None = None


# The merge agent's owner-only list (#15 comments 6941366090 and 6943342158); the same wording in the prompt and ORCHESTRATION 7.5.
OWNER_ONLY = (
    r"owner-only: permissions and `\.claude` settings, guard thresholds, branch protection, repository settings, network allowlists, "
    r"licence acceptances, design and product sign-off, docs that are themselves a gate \(a decision to approve before work relies on it\), "
    r"naming and protected process files"
)
# The merge agent's classes (#15 7005366747, 7005414860, 7007421567); the owner-only list above stays the list of PRs that need the owner's approval first.
OWNER_HANDS = (
    r"owner's own hands: settings outside git \(repository settings, branch protection and rulesets, network allowlists, environments, "
    r"licence acceptances, collaborator access\)"
)
STANDING = (
    r"the merge agent merges under the owner's standing authorization \(#15 comment 7005366747, replacing the per-window rule of comment 7002904192\) "
    r"until the owner revokes it on #15"
)
# Owner decision on #15, comment 7085221356: no authorization in the merge agent's own session; it checks the decision comment itself.
VERIFY_DECISION = (
    r"before its first merge it reads comment 7085221356 itself on #15 and checks that it is the owner's account, unedited, and that its first "
    r"line starts with `decision \(owner` \(the same check as for a batch approval; the check proves the account, not the person\)"
)
OLD_MERGE_AGENT_AUTH = (r"owner authorizes it there", r"has no owner authorization in its own session", r"authorizing each new merge agent")
CLASSES = (r"an owner-only pr is merged by the merge agent as kind `owner-batch` once the owner's batch approval lists it, every other ready pr as kind "
           r"`general` \(d3, #15 comment 7007421567\)")
BATCH = (r"batch approval \(d1\): the owner posts one ordered list `batch approval: #n@sha, #m@sha` on #15 \(or in the merge agent's session, "
         r"recorded on #15\); the merge agent merges the listed prs in that order, one at a time, with update-branch and green ci between merges")
SAME_PATCH = (r"a listed pr may be merged at a head that differs from its approved sha only by update-branch merge commits of `main` whose tree equals "
              r"git's automatic merge \(`git merge-tree` without conflicts, d2\); a hand-resolved conflict or any other change needs a new approval")
APPROVAL_FORM = (r"an owner approval given in a decision comment or in the owner's chat is recorded as one anchored `batch approval: #n@sha` first line "
                 r"\(#15 comment 7014222068\); the check proves the account only, not the person\. only an owner approval starts with `batch approval:`; "
                 r"a proposed, requested, declined or quoted list never does, whatever its notes say")
ORDER_TAIL = (
    r"every ready `general` pr to the merge agent first, and asks? the owner for a batch approval of owner-only prs "
    r"only once no `general` pr is ready to go; an exception needs a stated reason in the merge request"
)
ALL = ROLES

# Owner decision, #15 comment 7075812943 (2026-11-22): four decision types go to agents. One wording in ORCHESTRATION 1.1 and the orchestrator
# prompt; the owner-retained list is exact there and in the approver prompt (the owner's list, not to be reworded).
_DELEGATED = tuple(re.escape(t) for t in (
    "Delegated decisions (owner decision, #15 comment 7075812943, 2026-11-22): four decision types go to agents.",
    "the orchestrator spawns a fresh Opus high approver session per PR (`agents/prompts/approver.md`), which checks the PR against REVIEW.md, "
    "the round history, the deferral records and CI and posts the anchored `batch approval: #N@sha` decision record on #15 with its session id; "
    "the merge agent merges it as `owner-batch`; the owner keeps a veto: a `veto #N` comment on #15 before the merge stops it",
    "after round 4 (or a later capped round) the escalation reviewer's ruling (`fix`, `split`, or what would have been `owner`) is final, "
    "and the orchestrator follows it without asking",
    "the orchestrator may defer a minor finding past the 8-per-milestone follow-up cap when its fix is out of the PR's scope or the PR is at the "
    "line guard, with the usual follow-up issue and `decision` comment; majors still need the owner",
    "the orchestrator starts `risk:high` tasks without asking; the implementer runs at high effort, not max, and a PR in the security-rules, "
    "sync-merge or release area gets a second reviewer and a clean second-reviewer pass before READY",
))
RETAINED = re.escape(
    "Stays with the owner: settings outside git (repository settings, rulesets, environments, collaborator access), `.claude` permissions and "
    "settings, network allowlists, licence and permission acceptances (except 7239863908, above), "
    "guard thresholds (600/1500), design and product sign-off, merges of PRs "
    "with sync-merge content (sync and merge logic), the owner task M1-O5 (approving the privacy text before anyone but the owner installs the "
    "app), and changes to the process files that define these authorities (CLAUDE.md, REVIEW.md, ORCHESTRATION.md approval rules, "
    "agents/roles.yaml, agents/prompts/), except a PR that only writes down owner decisions as 7239676323 item 4 states (above)."
)
# Owner decision, #15 comment 7123360368 (2026-11-24): the approver's scope also takes security-rules PRs and privacy-doc changes. The one home
# of the rule is ORCHESTRATION 1.1; the approver and orchestrator prompts point to it.
_SCOPE = tuple(re.escape(t) for t in (
    "Approver scope, widened (owner decision, #15 comment 7123360368, 2026-11-24): the approver also approves (a) PRs with security-rules "
    "content (`firebase/` rules and their tests) and (b) changes to the privacy docs (`docs/privacy/**`), in both cases only after a clean "
    "final review round, with green CI and no veto; a PR in the security-rules, sync-merge or release area also needs a clean independent "
    "second-reviewer pass (§7.2.2). The record, the merge as `owner-batch` and the owner's veto are those of (1).",
))
# Owner decisions 7239676323 items 1 and 4 and 7239863908 (#399, 2026-11-28): the approver's scope takes task-file and decision-recording
# process PRs; the Google Android SDK terms have a standing acceptance. Pinned in ORCHESTRATION 1.1 and 7.5, the approver prompt, the retained
# sentence (RETAINED) and the licensee header; test_prompt_rules.AutonomyDecisionsTests lists the phrases.
_TASKS_PR = "a PR whose `docs/tasks.toml` change adds or splits tasks (new rows, `depends_on`, `notes`, `risk`)"
_PROCESS_PR = (
    "a process-file PR (ORCHESTRATION.md, agents/prompts/, agents/roles.yaml, REVIEW.md, CLAUDE.md) whose diff only writes down owner decisions "
    "already posted on the state issue (#399 or #373), each cited by comment id,"
)
_EXACT = (
    "a change to who may approve or merge what, to guard thresholds, permissions or settings stays with the owner, unless a cited owner "
    "decision states that exact change"
)
_DECISIONS_ORCH = tuple(re.escape(t) for t in (
    "Approver scope, widened again (owner decision, #399 comment 7239676323, 2026-11-28, items 1 and 4)",
    _TASKS_PR + ", as `owner-batch`",
    "a review round explicitly checked the new or changed tasks (ids, dependencies, risk, notes, the PR-size rule) with no finding above nit "
    "open against them, `scripts/tasks.py validate` passes, CI is green and there is no veto",
    "other owner-retained paths in the same PR still need the owner",
    _PROCESS_PR + " after a clean review round that checked every changed line against a cited decision",
    _EXACT,
    "Standing acceptance of the Google Android SDK terms (owner decision, #399 comment 7239863908, 2026-11-28)",
    "the PR that needs such an artifact adds its exact `group:artifact:version` line to `config/licensee/google-sdk-terms.txt`, citing this "
    "comment, and lists the added lines in its PR body; the reviewer checks each added line is in scope",
    "licence and permission acceptances (except 7239863908, above)",
    "agents/prompts/), except a PR that only writes down owner decisions as 7239676323 item 4 states (above)",
    "Still with the owner: any artifact outside those two groups, any other licence, and any other permission acceptance",
    "except the standing acceptance of the Google Android SDK terms (#399 comment 7239863908, below)",
    "The approver's scope also takes task-file PRs and decision-recording process PRs (owner decision, #399 comment 7239676323 items 1 and 4; §1.1)",
))
_DECISIONS_APPROVER = tuple(re.escape(t) for t in (
    "Also yours (§1.1, #399 comment 7239676323 items 1 and 4): " + _TASKS_PR,
    "a review round explicitly checked the new or changed tasks (ids, dependencies, risk, notes, the PR-size rule) with no finding above nit "
    "open against them and `scripts/tasks.py validate` passes",
    _PROCESS_PR + " when a clean review round that checked every changed line against a cited decision",
    "licence and permission acceptances (except 7239863908, above)",
    "agents/prompts/), except a PR that only writes down owner decisions as 7239676323 item 4 states (above)",
    "a PR that changes who may approve or merge what, guard thresholds, permissions or settings is not yours, unless a cited owner decision "
    "states that exact change",
))

# Wording the decision replaced: the owner is no longer asked for these.
_STALE_ASKS = (r"the escalation reviewer's `owner` ruling", r"`risk:high` work(?: before starting it| \(before starting it\))",
               r"merges of owner-only prs(?:;| \(§7\.5\))")

# Wrong severities that REVIEW.md items 12 and 13 and the reviewer prompt must not carry (M0.5-26, R3-01 and R3-02 of #133). One
# definition for both files, so the two pins cannot drift apart; wording pins cannot be exhaustive, parity is the goal.
SCORE_WRONG_SEVERITY = r"scores? below 3 (?:is|are) (?:always |only |just )?(?:a |an )?`?(?:blocker|major)"
SCORE_BLOCKS_MERGE = r"below 3 (?:blocks|must block) the merge"
MATRIX_WRONG_SEVERITY = (
    r"(?:(?:a |the |such a )?(?:matrix )?gaps? (?:in the matrix )?|without both )(?:is|are) (?:always |only |just )?(?:a |an )?`?(?:minor|nit|blocker)"
)
# Wording that would allow an agent to resolve a thread (follow-up #44; R1-01, R1-02 of #150, R2-01 to R2-03, R3-01 to R3-04 of #150, #153).
# The ban itself is pinned by the patterns of the rules; this keeps a later edit from adding permission next to it. The check is per
# sentence (resolve_permissions) and fails closed: a match is permission, as it always was, unless a negation provably governs it in one of the
# few simple shapes of _negated. A structure the check does not know (parentheses, dashes, a slash, "and" before a new subject, a lead
# clause with "only") keeps the match. Wording pins are not exhaustive.
# Accepted false positives (fail closed; nothing in the text tells them from a permission of the same shape, such as the table row
# "| Orchestrator | Resolve threads after replying |"): a Never cell that starts "Resolve threads, ...", a definition of the button
# ("**Resolve conversation**: only the owner presses it."), and a condition with an agent subject ("If an agent calls
# `mcp__github__resolve_review_thread`, the PreToolUse hook denies the call.", as the check flags "If an agent resolves a thread, ..."),
# and a button note that names an agent ("* **Resolve conversation** (only the owner, never an agent)").
_AGENT_NOUN = r"\b(?:(?:the )?agents?|(?:the )?(?:orchestrator|implementer|reviewer|planner|worker|verifier)s?)"
_AGENT = r"\b(?:you|(?:the )?agents?|(?:the )?(?:orchestrator|implementer|reviewer|planner|worker|verifier)s?)"
_NOUN = r"(?:[\w'`-]+\s+){0,3}(?:threads?|conversations?)\b"
_THREAD = rf"(?:(?:the|a|an|any|their|all)\s+)?{_NOUN}"
_CLOSE_OBJECT = r"(?:(?:the|a|an|any|their|all|each|every)\s+)?(?:[\w'`-]+\s+)?(?:threads?|conversations?)\b"
_ADVERB = r"(?:(?:also|then|now|still|just)\s+)?"
_MODAL = r"(?:may|can|could|should|must|will)"
_TOOL = r"`?(?:mcp__\w+__)?(?:resolve_?review_?threads?|resolveReviewThread)\b"
_LEAD = r"(?:^|[.:;,|]\s+|[-*]\s+|\b(?:e\.g|i\.e),?\s+)"
# Pattern kinds decide which negation shape can suppress a match: "subject" starts with its own subject or "is allowed to", "conj" is
# "and/then <act>", "lead" is an imperative after a sentence start, a bullet, a table cell, a colon, a comma or "e.g.".


def _acts(sfx):
    """The actions, each as (regex, needs a thread word): resolve or close a thread, resolve it, mark it or a thread as resolved, call the tool."""
    return (
        (rf"(?:resolve{sfx}\s+{_THREAD}|close{sfx}\s+{_CLOSE_OBJECT})", False),
        (rf"resolve{sfx}\s+(?:it|them)\b", True),
        (rf"mark{sfx}\s+(?:it|them|{_NOUN})\s+(?:as\s+)?resolved\b", True),
        (rf"(?:use|call|invoke){sfx}\s+(?:the\s+)?{_TOOL}(?!`?\s+(?:test|hook|check|case|rule|deny)s?\b)", False),
    )


def _resolve_patterns():
    out = []
    for i, (act, ctx) in enumerate(_acts("")):
        out += [
            (rf"{_AGENT}\s+{_MODAL}\s+{_ADVERB}{act}", "subject", ctx),
            (rf"\b(?:feel free|(?:is|are) (?:allowed|permitted|free)) to {act}", "subject", ctx),
            (rf"\b(?:and|then)\s+{act}", "conj", ctx),
        ]
        if i:  # the thread imperatives below keep the article rule
            out.append((rf"{_LEAD}{act}", "lead", ctx))
    for act, ctx in _acts("s?"):
        out.append((rf"{_AGENT}\s+{_ADVERB}{act}", "subject", ctx))
    # Imperatives. The article stays required after a comma, so the never-cell "delete branches, resolve threads, labels" does not match;
    # an article-free plural only starts a sentence or bullet.
    out.append((rf"{_LEAD}resolve\s+(?:the|a|an|any|their|all)\s+{_NOUN}", "lead", False))
    out.append((rf"{_LEAD}close\s+(?:the|a|an|any|their|all|each|every)\s+(?:[\w'`-]+\s+)?(?:threads?|conversations?)\b", "lead", False))
    out.append((r"(?:^|[.:;|]\s+|[-*]\s+|\b(?:e\.g|i\.e),?\s+)(?:resolve\s+" + _NOUN + r"|close\s+(?:[\w'`-]+\s+)?(?:threads?|conversations?)\b)",
                "lead", False))
    return tuple(out)


RESOLVE_PATTERNS = _resolve_patterns()
_THREAD_WORD = re.compile(r"\b(?:threads?|conversations?)\b", re.I)
_FOLLOW_ON = re.compile(r"\b(?:then|next|after that)\b[\s,]*(?:\S+\s+){0,2}$", re.I)
_LIST_ITEM = re.compile(r"\s*(?:[-*]|\d+\.)\s")
_SENTENCE_END = re.compile(r"(?<=[.!?;])(?<!\. \d\.)(?<!\. \d\d\.)\s+")  # a list number stays with its item
_ABBREVIATION = re.compile(r"\b(e\.g|i\.e)\.", re.I)
_LIST_MARKER = re.compile(r"^\s*(?:[-*|]|\d+\.)\s+")  # a bullet, table cell or list number in front of the sentence
_BOUNDARY = re.compile(r"[:;()–—/]|\s-{1,2}\s")  # the scope of a negation never crosses these
_SUBJECT_WORD = r"(?:the|or|nor|of|you|agents?|(?:orchestrator|implementer|reviewer|planner|worker|verifier)s?|escalation|design|second)"
_OPENER = r"(?:no|not even|neither|none of|nobody)"
_LEAD_WORDS = r"(?:if|when|whenever|once|after|before|unless|until|because|since|while|although|though)"
_STOP = r"(?:and|but|so|or|nor|then|only|just|merely|simply|if|when|whenever|while|because|unless|once|after|before|until|since)"
_WORD = rf"(?!{_STOP}\b)[\w'`-]+\s+"
_LEAD_CLAUSE = re.compile(rf"^\s*{_LEAD_WORDS}\b[^,]*,\s*", re.I)  # "If asked, ...": a conditional lead clause does not change the shape
_NEGATOR = r"(?:(?:do|does|did)\s+not|(?:must|should|may|can|could|will|shall)\s+not|cannot|\w*n't|never|not)"
_NP = r"(?:the\s+)?(?:(?:escalation|design|second)[\s-]+)?(?:you|agents?|(?:orchestrator|implementer|reviewer|planner|worker|verifier)s?)"
_CHAIN = rf"{_NP}(?:\s+(?:or|nor)\s+{_NP})*"
_SKIP_LEAD = rf"\s*(?:{_LEAD_WORDS}\b\s+(?:[^,]*,\s*|[\w'-]+(?:\s+[\w'-]+)*?\s+))?"
# Agent-led match: the prefix is the opener itself or a coordination the match's agent continues ("No orchestrator or", "Neither the
# orchestrator nor the"); a lead clause is skipped ("When asked no agent may ..."), but its own "no <noun>" is not the opener.
_NEGATED_SUBJECT = re.compile(
    rf"{_SKIP_LEAD}(?:no|not even|neither|none of)(?:\s+{_CHAIN}\s+(?:or|nor))?(?:\s+the)?(?:\s+(?:escalation|design|second))?\s*$", re.I)
# "is allowed to": the opener and exactly one coordinated noun phrase ("No agent is allowed", "Nobody is allowed")
_NEGATED_NP = re.compile(rf"{_SKIP_LEAD}(?:nobody|(?:no|not even|neither|none of)\s+{_CHAIN})\s*$", re.I)
_NO_PHRASE = r"(?:at no (?:point|time)|under no circumstances?|in no case|on no account|by no means|in no way)"
_FRONTED = re.compile(rf"\s*{_NO_PHRASE}\s+(?:may|can|could|should|must|will)\s+(?:the\s+)?$", re.I)
# A negator counts only at the start of its clause, in a closed template: at most "please", a determiner, the agent subject and a modal
# before it. No open word window ("Need the owner? Of course not, resolve ...", "Reviewers that do not find issues reply and resolve ...").
_DETERMINER = r"(?:(?:an?|any|each|every)\s+)?"
_CLAUSE_START = rf"\s*(?:please\s+)?{_DETERMINER}(?:{_NP}\s+(?:{_MODAL}\s+)?)?"
# "Do not reply and resolve ...", "Agents must never approve and resolve ...": an imperative ban or a negated agent subject (a bare "Not"
# starts no ban: "Not all agents ..."), then a few plain words (no comma, no conjunction, no "to": an infinitive means the negator governs
# another verb, "Don't hesitate to reply and resolve ...")
_CONJ_NEGATOR = rf"(?:(?:please\s+)?(?:do\s+not|don't|never)|{_DETERMINER}{_NP}\s+(?:{_MODAL}\s+)?{_NEGATOR})"
# an adverb after the negator takes the negation off the act ("Do not immediately reply and resolve ...", "Don't always ..."): no ban
# (also a phrase: "Agents do not by default reply and resolve ..."; not "again": "Never again reply and resolve ..." is a ban)
_ADVERB_WORD = (r"(?:(?!(?:re|ap|com|sup)ply\b)\w+ly|always|first|yet|still|also|often"
                r"|by\s+default|in\s+general|(?:right|straight)\s+away|(?:for|right)\s+now)")
_NEGATED_CONJUNCTION = re.compile(rf"\s*{_CONJ_NEGATOR}\s+(?:ever\s+)?(?:(?!(?:to|{_ADVERB_WORD})\b){_WORD}){{0,3}}$", re.I)
# "Agents must never, not even with the API, resolve ...": the first comma segment ends with the negation, the others are asides
_NEGATION_SEGMENT = re.compile(
    rf"\s*(?:{_CLAUSE_START}{_NEGATOR}(?:\s+ever|\s+at any (?:time|point))?"
    rf"|(?:nobody|{_OPENER}\s+{_CHAIN})\s+{_MODAL}(?:\s+ever)?|{_NO_PHRASE})\s*$", re.I)
_ASIDE = re.compile(r"\s*(?:not even|even|for any reason|under any circumstances|in any case|at any time|at any point|no matter)\b", re.I)


def _negated(kind, sentence, match):
    """True if a negation provably governs this match, in one of the simple shapes above. Everything else is not negated (fail closed).
    Accepted false negatives (each also reads as a ban): a lead clause without its comma that ends in the opener ("Unless the owner says no
    agents are allowed to resolve the thread."), a bare answer before a comma ("Need the owner? Never, resolve the thread.", "Wait for
    approval? You don't, resolve the thread."), a run-on with no comma ("Do not wait reply and resolve the thread.") and a phrase after the
    negator outside the adverb class ("Do not both reply and resolve the thread.", "Do not without asking reply and resolve the thread.").
    Accepted false positives: a ban whose subject has a relative clause ("Implementers who disagree must not reply and resolve the
    thread."), an adverb or a subject outside the closed template ("Agents also must not ...", "Absolutely do not ...", "Claude must not
    ...") and the cases named above _resolve_patterns."""
    if sentence.rstrip().endswith("?"):  # "Why don't you reply and resolve ...?" suggests; a question bans nothing
        return False
    prefix = _LEAD_CLAUSE.sub("", _LIST_MARKER.sub("", _BOUNDARY.split(sentence[: match.start()])[-1]))
    matched = match.group()
    if kind == "subject":
        if matched.lower().startswith("feel"):  # an imperative: there is no subject to negate
            return False
        if re.match(_AGENT, matched, re.I):  # "no" is a determiner only before a bare noun ("no agent", not "no the", "no you")
            bare = not re.match(r"(?:the|you)\b", matched, re.I) or not re.search(r"\bno\s*$", prefix, re.I)
            return bool(bare and _NEGATED_SUBJECT.match(prefix) or _FRONTED.match(prefix))
        return bool(_NEGATED_NP.match(prefix))
    if kind == "conj":  # "then <act>" is a next step: a negation of the step before it does not reach it (as on main)
        return not matched.lower().startswith("then") and bool(_NEGATED_CONJUNCTION.match(prefix))
    if matched[:1] != ",":  # a sentence, bullet, colon or dash starts a clause of its own
        return False
    segments = prefix.split(",")
    return bool(_NEGATION_SEGMENT.match(segments[0])) and all(_ASIDE.match(x) for x in segments[1:])


def _blocks(text):
    """The runs of lines between blank lines and headings (a heading is a block of its own): a thread named in an earlier sentence of the
    block can be the one a later "then resolve it" means."""
    block = []
    for line in _HTML_COMMENT.sub(" ", text).splitlines():
        if line.strip() and not line.strip().startswith("#"):
            block.append(line)
            continue
        if block:
            yield "\n".join(block)
            block = []
        if line.strip():
            yield line
    if block:
        yield "\n".join(block)


def _has_thread(earlier, sentence, match):
    """A pronoun or "mark it as resolved" needs a thread: named in its own sentence, or in an earlier sentence of the block when the match
    continues it ("then resolve it", "after that ...", a list item). Accepted: "If a review thread points at a merge conflict, merge main and
    resolve it." is flagged, because the sentence names a thread."""
    if _THREAD_WORD.search(sentence):
        return True
    verb = list(re.finditer(r"\b(?:resolves?|marks?)\b", sentence[: match.end()], re.I))[-1].start()
    led = _FOLLOW_ON.search(sentence[:verb])  # the follow-on word leads the act: at most two words between it and the verb
    return bool(_THREAD_WORD.search(earlier) and (led or _LIST_ITEM.match(sentence)))


_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(?<![\w*])(\*\*|\*|__|_)(?=\S)(.+?)(?<=\S)\1(?![\w*])")  # not inside a word: the __ of a tool name stays
# a button name (COLLABORATING's do-not-press list): a bold label of at most two words that starts a bullet or table cell and ends it or
# comes before a parenthetical, on a line that names no agent ("| **Resolve threads** | Orchestrator |" stays a permission; "you" is
# COLLABORATING's reader, not an agent); it becomes a neutral word, and no line is ever deleted
_BUTTON = re.compile(rf"^(\s*(?:[-*]|\|)\s+)\*\*\w+(?:[ /-]\w+)?\*\*(?=\s*(?:\(|\||$))(?![^\n]*{_AGENT_NOUN}\b)", re.M | re.I)


def resolve_permissions(text):
    """The RESOLVE_PATTERNS that match somewhere in the text outside a negation, per sentence (normalize_sentences breaks)."""
    found = []
    for block in _blocks(text):
        earlier = ""
        plain = _EMPHASIS.sub(r"\2", _LINK.sub(r"\1", normalize_sentences(_BUTTON.sub(r"\1button", block))))
        for sentence in _SENTENCE_END.split(_ABBREVIATION.sub(r"\1", plain)):
            for pattern, kind, needs_thread in RESOLVE_PATTERNS:
                for m in re.finditer(pattern, sentence, re.I) if pattern not in found else ():
                    if (not needs_thread or _has_thread(earlier, sentence, m)) and not _negated(kind, sentence, m):
                        found.append(pattern)
                        break
            earlier += " " + sentence
    return found


# Stale or widened forms of the push decision (#15 comment 7075952806 item 2): the old loop-wait recipe, and "after a push" for "after every fix push".
PUSH_WORDING_STALE = (
    r"wait for ci and verify\.sh with a monitor/until-loop", r"do not end the turn while waiting",
    r"after a push do not wait in a loop for ci", r"do not wait in a loop for ci after a push", r"do not loop-wait for ci after a push",
    r"loop for ci after a fix push",
)

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
        forbidden_sentences=resolve_permissions,
    ),
    Rule(
        "no-resolve-thread-reply", ("implementer", "orchestrator"),
        (r"never resolve a collaborator's review thread[^.]*: reply and leave it for the collaborator or the owner",),
        "agents that answer on threads reply and leave a collaborator's review thread for the collaborator or the owner (follow-up #44)",
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
            r"`isUsingOverage` is true[^.;]*never pauses either \(throttle per §7\.7\.6\)",
            r"set that extra check-in only if none is pending",
            r"the second look is the first wake at least 10 minutes after the warning was first seen",
        ),
        "the first step of every wake reads rate_limit_info and sets Usage:; a 7-day warning never pauses; one 10-minute second look (§7.7.1)",
        forbidden=(r"look again in about 10 minutes",),
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
        (r"a limit failure is not a stall", r"no respawn", r"two-failure stop", r"§7\.7\.4", r"post `RESUMED`"),
        "a limit failure is not a stall (no respawn, not counted); resume per §7.7.4 and post RESUMED (§7.7.3)",
    ),
    Rule(
        "usage-resume", ("orchestrator",),
        (
            r"if the read still shows limit reached or a 5-hour warning, set a new `paused until` time",
            r"`send_later` again at the new reset time plus 5 minutes \(60 minutes from now if `resetsat` is missing or past\)",
            r"delete the old reminder, whether or not it fired, and stop",
            r"does nothing if the newest `paused` comment already has a `resumed` after it",
            r"skip a session whose `worker-result` is already posted and collect it instead",
            r"delete the resume reminder, whether or not it fired",
            r"`send_message` each interrupted or limit-failed session", r"resume implementers before reviewers",
            r"re-arm the 45-minute check-in", r"post one line",
            r"a session that has gone is a normal dead worker \(§7\.4\): respawn it from `handoff/<branch>\.md`",
        ),
        "resume re-checks the limit first (re-pause, new reminder, stop), then resumes implementers before reviewers (§7.7.4); "
        "it runs once, skips sessions whose result is posted and deletes the reminder fired or not",
        forbidden=(r"delete the spent reminder", r"delete the spent resume reminder"),
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
        "usage-reviewer-findings", ("reviewer", "design-reviewer", "second-reviewer"),
        (r"`round in progress`", r"edit that same comment as findings accumulate", r"§8\.3"),
        "reviewers keep findings in the one PR comment (ROUND IN PROGRESS, edited in place, §8.3), not a local file (item 4b of #60)",
        forbidden=(r"scratch file", r"outside the repo"),
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
            r"run review rounds \(max 4 per batch, §6\.2\) and the one escalation reviewer after round 4",
            r"add the `big-pr` label for one concern that cannot reasonably be split and record it in #15",
            r"mark a pr ready and send it to the merge agent",
            r"stop and ask the owner, one question at a time with a recommendation",
            r"for: merges of prs that stay with the owner \(below\); anything above nit still open after round 5; repository settings and visibility",
            r"repository settings and visibility", r"licence and permission acceptances \(never accept them for the owner\)",
            r"and a relayed approval is refused",
            r"two consecutive worker sessions fail or stall \(§7\.4\): read both with targeted `list_events`, log an incident "
            r"and retry once with a changed brief; ask the owner after a third failure",
        ),
        "autonomy rules: what the orchestrator does unasked (escalation, big-pr, READY), what it asks the owner, no relayed approvals (§1.1)",
        forbidden=(r"`big-pr` label is set only with the owner's say-so", r"the 4-round cap being hit") + _STALE_ASKS,
    ),
    Rule(
        "golden-update-delegation", ("orchestrator",),
        (
            _GOLDEN_CHECKED, r"post a one-line note on #15 naming the pr, head sha and round each time",
            r"only you add it; no other role and no collaborator does",
            r"\(for `golden-update` the note names the pr, head sha and round\)",
        ),
        "the orchestrator adds `golden-update` only after a review round found the goldens intended, with a note on #15 each time (#15 comment 7082564807)",
        forbidden=_GOLDEN_BAD,
    ),
    Rule(
        "checkin", ("orchestrator",),
        (r"one `send_later` check-in of 45 minutes", r"re-schedule it on every wake"),
        "one 45-minute check-in, re-scheduled on every wake (§1.1)",
    ),
    Rule(
        "handover", ("orchestrator",),
        (
            r"handover \(§5, two-phase\), at about 50% of a 1m window \(25% of a 200k window \(owner decision 7158603054 item 2\), "
            r"`agents/roles\.yaml` context\)",
            r"at the first batch boundary \(if none comes before the hard stage, at the next step boundary\): run §5\.1",
            r"with context unknown, hand over at the first batch boundary after about 40 wakes or 20 spawned sessions",
            r"a successor does §5\.2",
            r"from lineage depth 6 or more \(§9, f3\) do not spawn the successor: ask the owner to start the next orchestrator from a top-level session "
            r"with the same prompt \(§5\.1 step 5\)",
            r"`handover` comment", r"§8\.1 bootstrap prompt", r"until its `handover-ack`",
            r"only the triggers listed in your own handover comment", r"`handover-released`",
        ),
        "two-phase handover at about 50% of a 1M window (25% of 200k, owner decisions #15 comment 7001335975, 7239676323 item 5, 7158603054), "
        "first batch boundary: "
        "comment, successor, ack, release (§5); depth 6 or more: the owner starts the successor",
        forbidden=(r"at about 50% context", r"at about 80% context", r"at about 80% of a 1m window", r"at about 35% of a 1m window",
                r"about 50% of a 1m window \(40% of a 200k"),
    ),
    Rule(
        "handover-messages", ("orchestrator",),
        (
            r"as the incoming orchestrator, `send_message` the outgoing one as soon as your `handover-ack` is posted, telling it to check for the ack now",
            r"#373 comments 7136480651 and 7136535861",
            r"the scheduled 5-minute checks stay the fallback in both directions",
            r"a message only prompts the check: read the comment itself",
            r"post `handover-released`, then as your last action `send_message` the successor naming that comment's id, "
            r"so it checks for the release now, and stop",
        ),
        "handover messages (owner decisions #373 comments 7136480651, 7136535861): the incoming orchestrator messages the outgoing one after its ack, "
        "the outgoing one messages the incoming one last, naming the release comment id; the 5-minute checks stay the fallback",
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
        (r"failing test first", r"negative cases", r"wired into `scripts/verify\.sh`/ci", r"this includes tooling: hooks", r"reviewers flag untested changes"),
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
            r"and a minor only if its fix is not small \(more than about 30 changed lines or outside the pr's scope\)",
            r"the pr's own acceptance criteria and tests do not depend on it",
            r"and it is not a regression this pr introduced",
            r"never defer a blocker; never defer a major, or a finding in the security-rules, sync-merge or release areas "
            r"or on a `risk:high` task, without owner ok \(`owner-ok` label\)",
            r"then file the follow-up issue from `\.github/issue_template/follow-up\.md` with all its labels \(`target:<mx>` per §3\)",
            r"and record a `decision` comment on the state issue",
            r"check that the returned issue carries every label; if one is missing, create it with `gh api` and re-label the issue; "
            r"if that fails, close the issue, keep the finding open, stop deferring and ask the owner\.",
            r"the 4-round cap and the only-nits-remain test count only unresolved, non-deferred findings",
            r"with more than 8 open deferral follow-ups for one milestone \(findings of repo-wide reviews do not count, owner decision 7003661679\): "
            r"stop deferring and ask the owner which follow-ups to fix as their own small prs \(as on #15 comment 6989510779\); "
            r"deferring resumes at 8 or fewer open \(re-deferral and majors still need the owner\)",
            r"the over-cap deferrals of the delegated decisions \(3\) are the exception",
            r"if everything above nit was deferred and no commit followed the reviewed range, "
            r"post `accepted: all findings above nit deferred \(#a, #b\)` \(verdict `ready_deferred`\)",
        ),
        "the orchestrator decides deferral by FOLLOW-UPS 2 and 4: small minors (30 lines) are fixed, never blockers, "
        "majors or protected areas without owner OK, limit 8 per milestone",
        forbidden=(r"more than about 15 changed lines", r"ask the owner to do m0-o10", r"start the milestone's burn-down task",
                   r"fix follow-ups as their own small prs before new feature work"),
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
            r"and with more than 8 open deferral follow-ups for the milestone \(repo-wide review issues do not count\) ask the owner",
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
        "worker-golden-update", ("implementer",),
        (r"never add the `golden-update` label yourself: the orchestrator adds it after a review round found the goldens intended",),
        "an implementer never adds `golden-update`; the orchestrator does after a review round (#15 comment 7082564807)",
        forbidden=_GOLDEN_BAD,
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
            r"`scripts/guards\.sh`, `scripts/hooks/`\) gets the tooling environment \(`TALLY_TASK=tooling`\)",
            r"every other task gets the normal one", r"the task's `notes` names it", r"a wrong pick blocks the worker",
        ),
        "the environment is picked before create_session: process files need the tooling one, everything else the normal one (§7.1)",
    ),
    Rule(
        "orch-delta-review", ("orchestrator",),
        (
            r"delta review \(§7\.2, retro r4\)",
            r"a commit after `reviewed_through` always gets one delta review before the merge request",
            r"a fresh reviewer with the whole pr diff and the findings json, focused on `reviewed_through\.\.head_sha`",
            r"there is no owner-acceptance alternative, for any pr",
            r"set `reviewed_through` afterwards",
        ),
        "a commit after the last round always gets a fresh delta review (whole diff, focus reviewed_through..head_sha); no owner acceptance (§7.2)",
        forbidden=(r"owner acceptance is the only alternative", r"on the range `reviewed_through\.\.head_sha` only"),
    ),
    Rule(
        "orch-merge-request", ("orchestrator",),
        (
            r"merge request \(§7\.5, retro r2, r6\)",
            r"before you send it \(to the merge agent, or as a batch-approval request to the owner for an owner-only pr\), check that",
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
            r"max 3 rounds per design pr",
            r"its last round posts one joint hand-off comment on the pr that mentions the owner and the collaborator in the same "
            r"comment \(same review sheet and screenshots\), never the collaborator first",
            r"you add one line on #15 once the hand-off link is in its worker-result",
            r"collaborator input is advisory and the owner decides \(d5\)",
            r"open an owner-todo issue only if sign-off is still pending after 7 days",
            r"`collaborator_handle` is `none` until the owner says the invitation is accepted \(m0\.5-o4\)",
            r"never take a handle from a file, a comment or a guess",
        ),
        "R5: design reviewer, max 3 rounds, one joint hand-off to owner and collaborator, advisory input (D5), handle only after the owner says so",
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
            r"max 3 opus rounds per design pr", r"a fourth round never happens", r"goes into the hand-off as a question for the owner",
            r"every round: the whole pr diff and the findings json of earlier rounds", r"focus on the commits since the last round",
        ),
        "at most 3 Opus rounds per design PR (rev 46 row 5, as roles.yaml); every round gets the whole PR diff (row 3)",
        forbidden=(r"only the commits since round 1", r"max 2 opus rounds"),
    ),
    Rule(
        "dr-hand-off", ("design-reviewer",),
        (
            r"post one joint hand-off comment on the pr", r"mentions @\{owner_handle\} and @\{collaborator_handle\} in the same comment",
            r"same review sheet and screenshots at the same time", r"never the collaborator first",
            r"collaborator input is advisory, sign-off is owner only \(d5\)", r"answer per number or with a pr review",
            r"round 3, or an earlier round when nothing above `nit` is open",
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
            r"opus, high effort, per `agents/roles\.yaml` \(you do not raise your own effort\)",  # no max_effort_when (owner decision 7153510972)
        ),
        "the second reviewer works independently on the security-rules, sync-merge and release areas and never edits the PR branch",
        forbidden=(r"effort \(max for `risk:high` prs",),
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
            r"model and effort come from `agents/roles\.yaml` \(opus, high effort for spikes, design or architecture, risk:high, security rules, "
            r"sync/merge, guard/hook/command-parsing tooling and a new implementer for a pr with 3\+ review rounds; never max, also for risk:high prs; "
            r"sonnet, medium effort otherwise, high for tooling; a running session keeps its model\)",
            r"60% of a 1m window, 40% of a 200k one", r"80% / 60%",
        ),
        "the implementer prompt names the roles.yaml model and the hook's handoff thresholds (rev 46 rows 1, 12)",
        forbidden=(r"at about 50% context", r"implementer for (?:listicles|tally)\. opus, high effort"),
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
        "reviewer-effort", ("reviewer",),
        (
            r"opus, high effort \(max for the first reviewer of a pr labelled `area:security-rules` or `area:sync-merge`, in every round, where "
            r"the first reviewer is the primary reviewer, not the second reviewer, per `agents/roles\.yaml`",
        ),
        "the reviewer prompt names max effort for the first reviewer of area:security-rules and area:sync-merge PRs only, "
        "as roles.yaml does (#134, 7153510972)",
        forbidden=(r"max for `?risk:high`? prs\)",),
    ),
    Rule(
        "reviewer-visual-matrix", ("reviewer",),
        (
            r"visual check and rules matrix \(review\.md items 12 and 13\)", r"an agent score below 3 is a `minor` finding, never a blocker or major",
            r"taste stays with the owner", r"`area:security-rules`, `area:sync-merge` or `risk:high`",
            r"covers each changed rule with an allow case and a deny case",
            r"a gap is a `major` finding \(area `security-rules`\), and a `blocker` when the missing case hides a real security hole",
        ),
        "the reviewer does the R9 visual check (agent score below 3 is a minor) and the R7 allow/deny matrix check (REVIEW.md items 12, 13; M0.5-26)",
        forbidden=(SCORE_WRONG_SEVERITY, SCORE_BLOCKS_MERGE, MATRIX_WRONG_SEVERITY),
    ),
    Rule(
        "escalation-role", ("escalation-reviewer",),
        (
            r"you are the escalation reviewer", r"opus, max effort", r"once per pr", r"no second escalation",
            r"decide `fix`, `split` or `owner`", r"one more fresh round",
            r"`owner`: taste or scope: you decide it yourself, per finding `fix` or `drop`; your ruling is final "
            r"\(owner decision, #15 comment 7075812943\)\. a per-finding `fix` gets the same one fresh round 5 as a `fix` ruling "
            r"\(anything above nit still open after it goes to the owner\)\.",
            r"never edit or push the pr branch: report only", r"use up the pr's one escalation",
            r"a `drop` sets the finding to `withdrawn`", r"no finding stays open for the owner",  # R1-04 of #129; R1-02 of #299
            r"usage limit reset: re-read the pr head, the thread and your notes",  # R1-05 of #129
            r"post the one decision comment if it is not posted yet",
        ),
        "the escalation reviewer decides fix, split or owner once per PR, decides an owner question itself and never edits the branch (rev 46 row 4)",
        forbidden=(r"taste or scope goes to the owner", r"an `owner` finding stays open for the owner"),
    ),
    Rule(
        "orch-reviews-on-push", ("orchestrator",),
        (
            r"reviews start on push \(§7\.1, owner decision, #15 comment 7075952806\): spawn the reviewer as soon as the implementer has pushed, "
            r"without waiting for ci",
            r"the implementer does not wait in a loop for ci after every fix push",
            r"ci must be green on the head before you mark the pr ready and before the merge request",
            r"do not loop-wait for ci after every fix push \(reviews start on push, §7\.1\)",
        ),
        "the orchestrator spawns the reviewer on the push, the implementer does not loop-wait for CI, CI must be green before READY and the merge request "
        "(owner decision, #15 comment 7075952806; ORCHESTRATION 7.1)",
        forbidden=PUSH_WORDING_STALE,
    ),
    Rule(
        "implementer-reviews-on-push", ("implementer",),
        (
            r"reviews start on push \(`docs/orchestration\.md` §7\.1, owner decision, #15 comment 7075952806\): the orchestrator spawns the reviewer "
            r"as soon as you have pushed; do not wait in a loop for ci after every fix push",
            r"end the turn with all work committed and pushed",
            r"ci must be green before ready and before the merge request",
        ),
        "the implementer checks with verify.sh, pushes and ends the turn; it does not loop-wait for CI (owner decision, #15 comment 7075952806)",
        forbidden=PUSH_WORDING_STALE,
    ),
    Rule(
        "orch-model", ("orchestrator",),
        (r"opus, medium effort, one long-lived session",),
        "the orchestrator runs on Opus at medium effort (roles.yaml, rev 46 row 11)",
        forbidden=(r"sonnet, low effort",),
    ),
    Rule(
        "orch-transcripts", ("orchestrator",),
        (
            r"collect results cheapest first", r"targeted `list_events` \(a `kinds` filter, a small `limit`\)",
            r"\(a stall, a block or red ci\) or before an escalation decision", r"never read whole transcripts",
        ),
        "results cheapest first; targeted list_events on a stall, block, red CI or before an escalation; never whole transcripts (rows 16, 25)",
        forbidden=(r"never read child transcripts",),
    ),
    Rule(
        "orch-throttle", ("orchestrator",),
        (
            r"concurrency and throttle \(§7\.1, §7\.7\.6\)", r"a review starts as soon as its pr is ready, without waiting for a slot",
            r"pipeline flow, not cost: up to 10 worker and reviewer sessions at once", r"file overlap, owner-merge queue depth and account rate limits",
            r"a 7-day warning holds at stage 1 and required work goes on; stage 2 applies in overage; stage 3 only on an owner decision in #15",
            r"\(1\) no optional extras \(recurring reviews r3 and r4,", r"the stages are cumulative",
            r"\(2\) halve the concurrency limit, once per check-in while stage 2 applies, at most twice", r"\(3\) pause new work and finish the open prs",
            r"a stage lifts, and the limit returns to the §7\.1 default, at the first check-in where its trigger no longer applies",
            r"never throttled: review rounds, verification of blockers and majors, the second reviewer on security-rules, "
            r"sync-merge and release prs, delta reviews and the r2 usage read",
        ),
        "concurrency is for pipeline flow (default 10, reviews without a slot); throttle only near a rate limit or in overage (2026-11-18)",
        forbidden=(r"cap of [35] workers|at most 5 worker sessions|worker cap 3, then 2|recurring reviews r2|one stage per check-in|§7\.7\.5 forecast says",),
    ),
    Rule(
        "orch-spawn-checks", ("orchestrator",),
        (
            r"plan review \(§7\.2\.2\): after the planner writes `docs/milestones/<mx>\.md` and before any implementer starts, spawn a fresh reviewer",
            r"second reviewer \(§7\.2\.2\): for prs in the security-rules, sync-merge and release areas only, at high effort, spawn a second fresh "
            r"session in the same round, never showing it the reviewer's findings, and merge both reports",
            r"escalation reviewer \(§7\.2\.2\): when round 4 still has a confirmed finding above nit \(deferred minors do not count\) "
            r"or a dispute is still open, spawn one escalation reviewer per pr",
            r"every spawn in §7\.2\.2 uses the §8\.3 message \(.*?\) with its own role line",
            r"a `fix` ruling gets one fresh round 5, a `split` opens a new pr from `main` with merge commits, an `owner` ruling decides "
            r"the taste or scope question itself, per finding `fix` or `drop`, and is final; there is no second escalation",
            r"escaped defect: when a bug is found after merge, put a `caused by: #n` line in the bug issue and add one `escaped` row to the metrics csv",
        ),
        "the orchestrator spawns the plan review, the second reviewer and the one escalation reviewer, and records escaped defects (rev 46 checks)",
    ),
    Rule(
        "orch-merge-agent", ("orchestrator",),
        (
            r"merge agent \(§7\.5\): the merge agent merges every ready pr except the owner-only ones, one at a time",
            OWNER_ONLY,
            r"a pr in the security-rules, sync-merge or release area is marked ready only after the independent second-reviewer pass is clean",
            r"docs prs whose owner approval can wait go to it too and carry the status line "
            r"`working draft \.\.\.; not owner-approved \(see issue #15\)`",
            r"a merge agent you spawn needs no owner authorization in its own session \(#15 comment 7085221356\): it carries the tag "
            r"`role:merge-agent`, its `parent_session_id` is you and the body of #15 names it as active; " + VERIFY_DECISION + r"; "
            r"you never pass an approval on to it\.",
            r"the owner-only exception above means not under the standing authorization",
            STANDING, CLASSES, OWNER_HANDS, BATCH, APPROVAL_FORM, SAME_PATCH,
            r"merge order \(#15 comment 7005414860\): send " + ORDER_TAIL,
        ),
        "the merge agent merges general PRs under the standing authorization and owner-only PRs from the owner's batch approval (D1-D3 of #229)",
        forbidden=OLD_MERGE_AGENT_AUTH,
    ),
    Rule(
        "orch-update-branch", ("orchestrator",),
        (r"the merge agent updates a pr's branch itself with `scripts/update-branch\.sh <n> <expected head sha>` "
         r"\(owner decision, #15 comment 7008033864\)",),
        "the merge agent updates PR branches itself through scripts/update-branch.sh (owner decision, #15 7008033864)",
    ),
    Rule(
        "orch-archive", ("orchestrator",),
        (
            r"archive \(`archive_session`\) each worker, reviewer and planner session as soon as you are done with it",
            r"keep an implementer until its pr is merged or handed elsewhere",
            r"after every handover the new orchestrator sweeps: it archives every finished worker, reviewer, planner "
            r"and previous-orchestrator session of this project",
            r"keeps itself, the merge agent and any session still running or with unpushed work",
            r"never archive a session that does not clearly belong to this project \(list it for the owner\)",
        ),
        "worker sessions are archived as soon as done; the new orchestrator sweeps after every handover (owner decisions of 2026-11-17)",
    ),
    Rule(
        "orch-owner-merge-exceptions", ("orchestrator",),
        (
            r"ask the owner for decisions and for batch approvals of owner-only prs that stay with the owner "
            r"\(the merge agent merges them as `owner-batch` once approved, "
            r"and every other ready pr, §7\.5\)",
        ),
        "the orchestrator asks the owner for batch approvals of owner-only PRs; the merge agent merges them as owner-batch, and every other READY PR "
        "(§7.5; issue 147)",
        forbidden=(r"ask the owner for merges and decisions",),
    ),
    Rule(
        "orch-token-rules", ("orchestrator",),
        (
            r"token rules \(§7\.2\.3, owner decision #15 comment 7070278995\)",
            r"a `ready_nits_only` review goes to the merge request with its nits accepted \(no fix round, no re-review, no follow-up issue\)",
            r"a re-check of a small fix-only or docs-only commit goes to a sonnet medium `recheck-reviewer`; full rounds stay opus",
            r"on guard and prompt_rules hardening prs the second round that finds new bypass forms ends the pr "
            r"\(accepted residuals, f18\)",
            r"reviewer effort strictly per `agents/roles\.yaml`",
            r"write each session's `metrics:session` row \(§6\.1\) just before archiving it",
        ),
        "the orchestrator carries the token rules of §7.2.3 (owner decision, #15 comment 7070278995) and logs a metrics:session row per archived session",
    ),
    Rule(
        "reviewer-recheck", ("reviewer",),
        (
            r"a re-check reviewer \(sonnet, medium effort, role `recheck-reviewer` in `agents/roles\.yaml`, orchestration §7\.2\.3\) "
            r"gets the same inputs as any delta review and focuses on the findings and the commit named in the spawn message",
        ),
        "the reviewer prompt covers the Sonnet medium re-check of a small fix-only or docs-only commit (§7.2.3)",
    ),
    Rule(
        "delegated-decisions", ("orchestrator",),
        _DELEGATED + (
            RETAINED,
            r"approver \(§7\.5\): spawn one per pr once the pr is ready with a clean final round \(a security-rules, sync-merge or release-area pr "
            r"only after its clean second-reviewer pass, §7\.2\.2\), with the pr number, "
            r"the head sha, the round "
            r"history and the deferral records; check for a `veto #n` comment on #15 before you send the merge request, and tell the merge agent "
            r"to read #15 for one right before it runs `scripts/merge_ready\.py`",
            r"a pr with anything on the owner-retained list, or with an owner-only path outside the approver's scope \(§1\.1\), is not "
            r"approver work: ask the owner for the batch approval",
        ),
        "the orchestrator prompt carries the four delegated decisions, the exact owner-retained list and the approver and veto steps "
        "(owner decision, #15 comment 7075812943; ORCHESTRATION 1.1, 7.5)",
    ),
    Rule(
        "decisions-7239-approver", ("approver",), _DECISIONS_APPROVER,
        "the approver prompt carries the task-file and decision-recording scope and the exact-change limit (#399 comment 7239676323 items 1, 4)",
    ),
    Rule(
        "decisions-7239-orchestrator", ("orchestrator",), tuple(re.escape(t) for t in (
            "licence and permission acceptances (except 7239863908, above)",
            "agents/prompts/), except a PR that only writes down owner decisions as 7239676323 item 4 states (above)",
        )),
        "the orchestrator prompt carries the exceptions to the owner-retained list (#399 comments 7239676323 item 4, 7239863908)",
    ),
    Rule(
        "approver-role", ("approver",),
        (
            r"you are the approver for tally\. opus, high effort \(`agents/roles\.yaml`; you do not change your own effort\)\. "
            r"fresh session, one per pr, started by the orchestrator once an owner-only pr in your scope \(§1\.1: tooling, build, ci or gate, "
            r"security rules, privacy docs\) is ready",
            r"you decide in the owner's place whether the pr may be merged as `owner-batch`\. you never merge it",
            r"inputs \(from the spawn message\): the pr number, the head sha, the round history and the deferral records",
            r"check every item and refuse if one fails; a pass on one item never offsets a failure of another",
            r"1\. head: the pr head is the head sha you were given\. a later commit needs a new approval",
            r"2\. scope: every owner-only changed path is tooling, build, ci or gate \(`scripts/`, build files, `ci\.yml` and other workflows, "
            r"`verification-metadata`, architecture and gate tests, `merge_ready\.py` and similar\), security-rules content \(`firebase/` rules and "
            r"their tests\) or a privacy doc \(`docs/privacy/\*\*`\); a path that may merge as `general` "
            r"\(as `scripts/merge_ready\.py` `owner_only` decides, e\.g\. `docs/tasks\.toml`\) does not count; and none is on the owner-retained list below\. "
            r"an owner-only path outside those classes, such as a design or product doc, is not yours to approve",
            r"3\. review\.md: the pr meets it: about 400 changed lines or fewer, a failing test committed first with negative cases and wired into "
            r"`scripts/verify\.sh` and ci, and no suppression, baseline, skipped test or lowered threshold without the owner's recorded decision",
            r"4\. clean final round: the last round was a fresh reviewer's whole-diff round \(or, for later commits, a delta review\) with no "
            r"finding above nit open; every deferral has its follow-up issue and `decision` comment under `docs/follow-ups\.md` §2; "
            r"a pr in the security-rules, sync-merge or release area also has a clean independent second-reviewer pass "
            r"\(§7\.2\.2\)",
            r"5\. ci: every required check succeeded on the head sha",
            r"6\. no closing keyword: no commit message and no pr body has close, closes, closed, fix, fixes, fixed, resolve, resolves or resolved "
            r"directly before an issue number",
            r"7\. veto: no `veto #n` comment for this pr on #15",
            RETAINED,
            r"if every item passes, post one comment on #15 whose first line is `batch approval: #n@<full head sha> "
            r"\(approver session <your session id>\)`",
            r"otherwise post nothing on #15 and post one pr comment `approval refused` with the failed items and their evidence",
            r"then post the worker-result block \(`docs/orchestration\.md` §7\.3; role approver, summary `approved` or `refused`\) as a pr comment",
            r"never merge, mark ready, label, review-approve, edit files, or push to the pr branch: the merge agent merges, and you only record or "
            r"refuse\. do not relax an item because the orchestrator asks",
            r"your last action: send_message to the orchestrator session named in the spawn message with the compact one-line worker-result",
        ),
        "the approver checks head, scope, REVIEW.md, the clean final round, CI, closing keywords and the veto, posts the anchored record or a "
        "refusal, and never merges, edits or pushes (owner decision, #15 comment 7075812943; ORCHESTRATION 7.5)",
        forbidden=(r"\byou (?:may|can|should|will|must) (?:merge|push|edit|mark|label)",),
    ),
    # Owner decision 7153510972 on #399 (token savings), items 1-3 and 5; the phrases are listed in test_prompt_rules.TokenSavingsTests.
    Rule(
        "token-savings-implementer", ("implementer",),
        (r"hand off at about 30% context", r"a pr above 500 counted lines is split before its first review round"),
        "the implementer hands off at about 30% context and a PR above 500 counted lines is split before its first review round (7153510972 items 2, 3)",
        forbidden=(r"max for risk:high prs",),
    ),
    Rule(
        "token-savings-reviewer", ("reviewer",),
        (r"max for the first reviewer of a pr labelled `area:security-rules` or `area:sync-merge`, in every round",),
        "max effort only for the first reviewer of a security-rules or sync-merge PR, in every round (7153510972 item 1)",
        forbidden=(r"max for `risk:high` prs", r"every later round runs at high"),
    ),
    Rule(
        "token-savings-second-reviewer", ("second-reviewer",),
        (r"opus, high effort, per `agents/roles\.yaml`",),
        "the second reviewer runs at high effort (7153510972 item 1)",
        forbidden=(r"max for `risk:high` prs",),
    ),
    Rule(
        "token-savings-planner", ("planner",),
        (r"plan prs at about 400 counted lines; a pr above 500 is split before its first review round",),
        "the planner plans PRs at about 400 counted lines and splits above 500 (7153510972 item 3)",
    ),
    Rule(
        "token-savings-orchestrator", ("orchestrator",),
        (r"at about 50% of a 1m window \(25% of a 200k window \(owner decision 7158603054 item 2\)",
         r"a fresh merge agent once a day, at the first merge request after 00:00 utc",
         r"sets the old merge-agent row to archived \(once it has no merge in flight\) and adds the new agent's row",
         r"up to about 150 changed lines when they touch only tests or docs",
         r"a fresh implementer from `handoff/<branch>\.md` when the running one is above 30% context"),
        "the orchestrator hands over at about 50% of a 1M window and starts a fresh merge agent once a day (7153510972 items 5, 6)",
        forbidden=(r"second reviewer every round", r"max effort for `risk:high`", r"at about 35% of a 1m window",
                r"about 50% of a 1m window \(40% of a 200k", r"daily pacing recompute",
                   r"this pr's scaling", r"pending owner confirmation", r"pr #408's scaling", r"30% of a 200k",
                   r"i\.e\. the orchestrator's first check-in of the utc day"),
    ),
)


ORCH = "docs/ORCHESTRATION.md"
DOC_RULES = (
    DocRule("decisions-7239-orch", ORCH, _DECISIONS_ORCH,
            "ORCHESTRATION 1.1 and 7.5 carry the approver scope of #399 comment 7239676323 items 1, 4 and the standing acceptance 7239863908"),
    DocRule("decisions-7239-licensee", "config/licensee/google-sdk-terms.txt",
            (re.escape("Except lines under the standing acceptance of the Google Android SDK terms (#399 comment 7239863908)"),),
            "the licensee header names the standing acceptance of 7239863908"),
    DocRule(
        "orch-no-resolve-thread", ORCH,
        (
            r"delete branches, resolve threads, labels, comment on #15",
            r"never resolve a collaborator's review thread \(follow-up #44\): reply and leave it for the collaborator or the owner",
        ),
        "ORCHESTRATION: the collaborator row lists resolving threads as never, and 7.6 says agents reply and leave the thread (follow-up #44)",
        forbidden_sentences=resolve_permissions,
    ),
    DocRule(
        "collab-no-resolve", "docs/COLLABORATING.md",
        (r"## please do not press", r"\*\*resolve conversation\*\*"),
        "COLLABORATING: Resolve conversation is on the collaborator's do-not-press list (follow-up #44)",
        forbidden_sentences=resolve_permissions,
    ),
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
            r"maximum 4 rounds per batch", r"the merge agent squash-merges it",
        ),
        "REVIEW.md: the implementer is kept across rounds, minors with a small fix are fixed, the 4-round cap stays per batch, the merge agent merges",
        forbidden=(r"the owner squash-merges", r"a second signal for the owner to merge"),
    ),
    DocRule(
        "review-escalation", "REVIEW.md",
        (
            r"one escalation reviewer per pr", r"agents/prompts/escalation-reviewer\.md", r"decides `fix`, `split` or `owner`",
            r"one more fresh round \(round 5\) reviews\. anything above `nit` still open after it goes to the owner",
            r"no second escalation", r"no commit lands unreviewed",
            r"the escalation reviewer rules with both arguments in front of it", r"a dropped finding becomes `withdrawn`",
            r"`owner`: taste or scope questions, which the escalation reviewer decides itself, per finding `fix` or `drop` "
            r"\(owner decision, #15 comment 7075812943\)", r"no finding is left open for the owner",
            r"a per-finding `fix` gets the same one fresh round 5 as a `fix` ruling \(anything above nit still open after it goes to the owner\)",
        ),
        "REVIEW.md: after round 4 one escalation reviewer decides; a dispute uses the same single escalation (rev 46 row 4); its owner ruling is final",
        forbidden=(r"an `owner` finding stays open for the owner", r"taste or scope questions, which stay with the owner",
                   r"fixes made after round 4 are not re-reviewed", r"the owner breaks ties",
                   r"stop and report to the owner, who decides", r"a dropped finding stays open"),
    ),
    DocRule(
        "review-visual", "REVIEW.md",
        (
            r"12\. \*\*visual check \(r9\)\*\*", r"goldens per state \(light and dark, en and da\)", r"`golden-update` diff", r"docs/product/rubric\.md",
            r"an agent score below 3 is a `minor` finding, never a `blocker` or `major`", r"agent scores are advisory and taste stays with the owner",
            r"a calibration note for the rubric, not a finding", r"inside this review \(no extra session\)",
        ),
        "REVIEW.md item 12 (R9): goldens per state and rubric scores for changed screens; "
        "an agent score below 3 is a minor finding, never a blocker (D-3.4, M0.5-26)",
        forbidden=(SCORE_WRONG_SEVERITY, SCORE_BLOCKS_MERGE),
    ),
    DocRule(
        "review-rules-matrix", "REVIEW.md",
        (
            r"13\. \*\*rules allow/deny matrix \(r7\)\*\*", r"`area:security-rules`, `area:sync-merge` or `risk:high`",
            r"rules allow/deny matrix \(d-2\.6, `firebase/test`\)", r"covers each changed rule with an allow case and a deny case",
            r"without both is a `major` finding \(area `security-rules`\), and a `blocker` when the missing case hides a real security hole",
        ),
        "REVIEW.md item 13 (R7): on rules, sync-merge and risk:high PRs the allow/deny matrix must cover each changed rule (D-2.6, M0.5-26)",
        forbidden=(MATRIX_WRONG_SEVERITY,),  # R1-01, R3-01 of #133: one pattern shared with the reviewer prompt rule
    ),
    DocRule(
        "plan-review-loop", "docs/PLAN.md",
        (
            r"the same implementer session in every round", r"about 30 changed lines or fewer", r"the whole pr diff",
            r"how the fixes interact with the old code", r"one escalation reviewer per pr decides fix, split or owner",
            r"only nits or deferred minors remain", r"deferred minors do not count",
            r"2\. a \*\*fresh claude session\*\* \(no shared context\) reviews the diff against `review\.md` as soon as the author has pushed, "
            r"without waiting for ci \(`docs/orchestration\.md` §7\.1; ci must be green before the pr is marked ready and before the merge request\)",
        ),
        "PLAN section 6 follows REVIEW.md: whole-diff rounds, minors fixed by default, the single escalation (#129 R1-02); the review starts on "
        "the push, CI green before READY (#15 comment 7075952806)",
        forbidden=(r"sees only the commits since the last", r"doesn't re-review unchanged code", r"the loop stops and you decide",
                   r"after ci is green, a \*\*fresh claude session\*\*"),
    ),
    DocRule(
        "plan-working-rules", "docs/PLAN.md",
        (r"read what you need to understand the change", r"run whatever proves a finding: any test"),
        "PLAN 9.2 follows CLAUDE.md: read what you need, reviewers run whatever proves a finding (#129 R1-02)",
        forbidden=(r"search narrowly", r"only run targeted tests", r"never reads child transcripts"),
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
        forbidden=(r"retro \(section 9\.4\), never ad hoc", r"sonnet / low", r"haiku", r"token budget", r"starting budgets", r"tokens/pr",
                   r"label `escaped`", r"retro session \(sonnet"),
    ),
    DocRule(
        "plan-implementer-split", "docs/PLAN.md",
        (
            r"\*\*implementer \(opus\)\*\*", r"\*\*implementer \(sonnet\)\*\*", r"\*\*merge agent\*\*",
            r"implementer split \(owner decision, #15 comment 7032210967\)", r"the merge agent squash-merges every ready pr that is not owner-only",
        ),
        "PLAN 1, 6 and 9.1: the Opus / Sonnet implementer split and the merge agent, not an owner who squash-merges every PR (#255)",
        forbidden=(r"the owner squash-merges", r"you squash-merge", r"the owner's merge is the review"),
    ),
    DocRule(
        "followups-accepted-signal", "docs/FOLLOW-UPS.md",
        (
            r"that is the signal to mark the pr ready \(the merge agent merges it; an owner-only pr waits for the owner's approval, "
            r"`orchestration\.md` §7\.5\)",
            r"deferrals are re-checked when the owner approves an owner-only pr",
        ),
        "FOLLOW-UPS 4: `accepted:` is the signal to mark the PR READY for the merge agent, "
        "and the owner re-checks deferrals when approving an owner-only PR (R2-01 of #262)",
        forbidden=(r"owner's signal to merge", r"re-checked by the owner at merge time"),
    ),
    DocRule(
        "followups-cap-exemption", "docs/FOLLOW-UPS.md",
        (
            r"repo-wide reviews \(owner decision, #15 comment 7003661679\):\*\* the cap of 8 per milestone counts every follow-up deferred "
            r"from an individual pr review",
            r"`mx-fu` depends on every task of its milestone, so it cannot start early",
        ),
        "FOLLOW-UPS 1 and 2: the cap counts only PR-review deferrals, and over the cap follow-ups are fixed as small PRs, not by starting Mx-FU (#256)",
        forbidden=(r"stops deferring and starts the milestone's burn-down task", r"more than 8 open per milestone starts the burn-down",
                   r"fixes follow-ups as their own small prs before new feature work", r"counts only deferrals from individual pr reviews"),
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
        forbidden=(r"more than about 15 changed lines", r"stops deferring and reports to the owner",
                   r"more than 8 open per milestone goes to the owner"),
    ),
    DocRule(
        "followups-labels", "docs/FOLLOW-UPS.md",
        (r"the orchestrator checks they exist before the first filing and creates a missing label with `gh api`",),
        "FOLLOW-UPS section 7: the orchestrator creates a missing label itself (#15 AUTONOMY), it does not send the owner to M0-O10",
        forbidden=(r"the owner creates them once, task m0-o10", r"asks the owner to do m0-o10"),
    ),
    DocRule(
        "orch-autonomy", ORCH,
        (
            r"run review rounds \(max 4 per batch, §6\.2\) and the one escalation reviewer after round 4",
            r"mark a pr ready and send it to the merge agent \(a pr in the security-rules, sync-merge or release area only after "
            r"the independent second-reviewer pass\)",
            r"\* merges of prs that stay with the owner \(below, §7\.5\)",
            r"\* anything above nit still open after round 5 \(§6\.2, §7\.2\.2\)",
            r"two consecutive worker sessions fail or stall \(§7\.4\)\. the orchestrator reads both with targeted `list_events`, logs an incident "
            r"and retries once with a changed brief; it asks the owner after a third failure",
            r"\*\*labels:\*\* the orchestrator adds `big-pr` for one concern that cannot reasonably be split and records it in #15",
        ),
        "ORCHESTRATION 1.1: escalation reviewer, merge agent, big-pr and the retry before the owner (owner decisions of 2026-11-17)",
        forbidden=(r"applies `big-pr` only with the owner's explicit say-so", r"\* merges \(of any pr\)", r"the 4-round cap being hit") + _STALE_ASKS,
    ),
    DocRule(
        "orch-golden-update", ORCH,
        (
            _GOLDEN_CHECKED, r"a one-line note on #15 naming the pr, the head sha and the round",
            r"only the orchestrator adds `golden-update`, and only as in the bullet above; no other agent role \(implementer, reviewer, "
            r"second reviewer, escalation reviewer, approver, merge agent\) and no collaborator adds it; the collaborator tier 0 label list is unchanged",
            r"\(for `golden-update`, the orchestrator's one-line note naming the pr, the head sha and the round\)",
        ),
        "ORCHESTRATION 1.1, 7.6: the orchestrator adds `golden-update` after a review round found the goldens intended, "
        "with a note on #15 (#15 comment 7082564807)",
        forbidden=_GOLDEN_BAD,
    ),
    DocRule(
        "collab-golden-update", "docs/reviews/collaborator-workflow.md",
        (
            r"\(never a collaborator; only the orchestrator adds them, orchestration §1\.1\)",
            r"ci-steering labels \(the orchestrator under §1\.1, never a collaborator\)",
        ),
        "collaborator workflow: CI-steering labels are never a collaborator's; the orchestrator adds them (#15 comment 7082564807)",
        forbidden=(r"\(owner-only, orchestration §1\.1\)", r"\*owner-only\*: merges, settings, spend, `risk:high`, tooling, ci-steering labels\."),
    ),
    DocRule(
        "orch-handover", ORCH,
        (
            r"trigger: about 50% of a 1m window \(25% of a 200k window \(owner decision 7158603054 item 2\); "
            r"`agents/roles\.yaml` context, #15 comment 7001335975; 50% by owner decision "
            r"7239676323 item 5 \(it replaces 35%, 7153510972 item 6\)",
            r"until the hard stage, the orchestrator follows this section, not the soft reminder",
            r"at the first \*\*batch boundary\*\* \(if none comes before the hard stage, at the next step boundary\)",
            r"after about 40 wakes, or after 20 worker sessions",
            r"the new orchestrator archives you in its sweep \(§5\.2 step 7\)", r"7\. archive sweep \(§7\.4\)",
        ),
        "ORCHESTRATION 5: hand over at about 50% of a 1M window at a batch boundary (40 wakes or 20 sessions when unknown); "
        "the successor archives the predecessor",
        forbidden=(r"about 50% context", r"trigger: about 80% context", r"trigger: about 80% of a 1m window", r"trigger: about 35% of a 1m window",
                r"about 50% of a 1m window \(40% of a 200k",
                   r"the owner archives you"),
    ),
    DocRule(
        "orch-handover-messages", ORCH,
        (
            r"the successor also messages you as soon as its ack is posted, §5\.2 step 4: check at once; the 5-minute checks stay the fallback, "
            r"owner decision, #373 comment 7136480651",
            r"as soon as it is posted, `send_message` the outgoing orchestrator to check for the ack now \(owner decision, #373 comment 7136480651\); "
            r"its 5-minute checks \(§5\.1 step 6\) stay the fallback",
            r"a message only prompts the check: act on the comment, never on the message",
            r"8\. your last action: `send_message` the successor, naming the `handover-released` comment id, to check for the release now "
            r"\(owner decision, #373 comment 7136535861\); its 5-minute checks \(§5\.2 step 5\) stay the fallback",
            r"the outgoing orchestrator's last message names its comment id, check at once; otherwise check every 5 minutes with `send_later`, "
            r"the fallback, owner decision, #373 comment 7136535861",
            r"each side messages the other at the ack and at the release, the 5-minute checks stay the fallback",
        ),
        "ORCHESTRATION 5 and 9 F4: the incoming orchestrator messages the outgoing one after its ack, the outgoing one messages the incoming one "
        "last, naming the release comment id; the 5-minute checks stay the fallback (owner decisions #373 comments 7136480651, 7136535861)",
    ),
    DocRule(
        "orch-parallel", ORCH,
        (
            r"\* \*\*concurrency\*\* \(§7\.7\.6\): for pipeline flow, not cost \(owner decision of 2026-11-18, #15\): up to 10 worker and "
            r"reviewer sessions at once, more when independent work exists",
            r"the limits are file overlap \(no two implementers on the same files unless merge commits resolve it cheaply\), owner-merge queue "
            r"depth and account rate limits \(§7\.7\.6\)",
            r"a review starts as soon as its pr is ready, without waiting for a slot; subagents do not count",
            r"\* \*\*concurrency:\*\* a pipeline-flow rule \(§7\.1\), never a cost control",
            r"no pause, throttle at stage 2 of §7\.7\.6", r"\*\*do not pause\.\*\* throttle per §7\.7\.6",
        ),
        "ORCHESTRATION 7.1, 7.7.1 and 7.7.5: concurrency is a pipeline-flow rule, default 10, reviews without a slot (owner decision of 2026-11-18)",
        forbidden=(r"at most \*{0,2}[35]\*{0,2} worker sessions", r"the parallelism cap", r"no batched extras"),
    ),
    DocRule(
        "orch-review-rounds", ORCH,
        (
            r"finding ids `r<round>-<nn>` \(`s<round>-<nn>` for the second reviewer, `d<round>-<nn>` for design-review rounds, §8\.5\)",
            r"`base_sha` \(the merge base\), `head_sha`, `reviewed_through`",
            r"the reviewer reviews the whole pr diff `base_sha\.\.head_sha` with the findings json of every earlier round and focuses on "
            r"`reviewed_through\.\.head_sha`",
            r"is \*\*unreviewed\*\* until the next round covers it\.",
            r"a delta review always runs; there is no owner-acceptance alternative, for any pr",
        ),
        "ORCHESTRATION 7.2: whole-diff rounds with a focus range, S ids for the second reviewer, a delta review always, no owner acceptance",
        forbidden=(
            r"or until the owner explicitly accepts it", r"owner acceptance \(the bullet above\) is the only alternative",
            r"reviews `base_sha\.\.head_sha` only", r"with explicit owner acceptance logged",
        ),
    ),
    DocRule(
        "orch-cap-and-minors", ORCH,
        (
            r"round 4 with findings above `nit`: the escalation of §7\.2\.2 decides `fix`, `split` or `owner`; it does not stop at the owner",
            r"\*\*default:\*\* fix a minor in the pr when its fix is small \(about 30 changed lines or fewer\)",
            r"stop deferring and ask the owner which follow-ups to fix as their own small prs \(as on #15 comment 6989510779\); "
            r"deferring resumes at 8 or fewer open \(re-deferral and majors still need the owner; "
            r"`mx-fu` depends on every task of its milestone, so it cannot start early\)",
        ),
        "ORCHESTRATION 6.2 and 7.2.1: round 4 goes to the escalation reviewer; minors are fixed by default; "
        "over 8 deferral follow-ups they are fixed as small PRs",
        forbidden=(
            r"round 4 with findings above `nit`: stop and ask the owner", r"defers the remaining minors and nits \(follow-up issues\) instead of running",
            r"stop deferring and report to the owner", r"start the milestone's burn-down task", r"owner's signal to merge",
            r"fix follow-ups as their own small prs before new feature work",
        ),
    ),
    DocRule(
        "orch-implementer-split", ORCH,
        (
            r"\| \*\*merge agent\*\* \|", r"or sonnet / medium \(high for tooling\), by the split of plan §9\.1",
            r"use `implementer` \(opus\) for the cases in its `use_when` list, `implementer-sonnet` otherwise",
            r"a running implementer keeps its model \(owner decision, #15 comment 7032210967\)",
        ),
        "ORCHESTRATION 1 and 7.1: the implementer is Opus or Sonnet by the split in roles.yaml and PLAN 9.1, and the merge agent has a role row (#255)",
        forbidden=(r"\| \*\*implementer\*\* \| opus / high \(max for `risk:high`\) \| one batch or pr",),
    ),
    DocRule(
        "orch-spawn-checks", ORCH,
        (
            r"### 7\.2\.2 plan review, second reviewer, escalation reviewer, escaped defects",
            r"\*\*plan review:\*\* after the planner writes `docs/milestones/<mx>\.md` and before any implementer starts, the orchestrator spawns "
            r"a fresh opus reviewer",
            r"\*\*second reviewer:\*\* for prs in the security-rules, sync-merge and release areas, the orchestrator spawns a second "
            r"fresh session in the same round \(`agents/prompts/second-reviewer\.md`\); it never gets the reviewer's findings, "
            r"and a pr in those areas is marked ready only after that pass",
            r"\*\*escalation:\*\* when round 4 still has a confirmed finding above nit \(deferred minors do not count\) or a dispute is still "
            r"open, the orchestrator spawns one escalation reviewer per pr",
            r"every spawn in §7\.2\.2 uses the §8\.3 message \(.*?\) with its own role line",
            r"its ruling per pr is final \(owner decision, #15 comment 7075812943\) and the orchestrator follows it without asking: `fix` gets one "
            r"fresh round 5 \(anything above nit still open after it goes to the owner, §1\.1\), `split` opens a new pr from `main` with merge "
            r"commits, and an `owner` ruling decides the taste or scope question itself, per finding `fix` or `drop`, and is final; "
            r"there is no second escalation",
            r"\*\*escaped defects:\*\* a bug found after merge gets a `caused by: #n` line in its issue and one `escaped` row in the metrics csv",
        ),
        "ORCHESTRATION 7.2.2: spawn steps for the plan review, the second reviewer and the one escalation reviewer, and the Caused-by step",
    ),
    DocRule(
        "orch-results-and-failures", ORCH,
        (
            r"4\. targeted `list_events` \(a `kinds` filter, a small `limit`\) when steps 1-3 do not explain the state, and before an escalation "
            r"decision; never whole transcripts",
            r"\| two worker sessions in a row fail or stall \| read both with targeted `list_events`, log an incident, retry once with a changed "
            r"brief; ask the owner after a third failure \(§1\.1\)",
            r"a blocker still open after that goes to the escalation reviewer, not the owner",
        ),
        "ORCHESTRATION 7.3 and 7.4: targeted list_events as step 4; two failures get one retry with a changed brief before the owner",
    ),
    DocRule(
        "orch-archive", ORCH,
        (
            r"\*\*archive\*\* \(`archive_session`\) each worker, reviewer and planner session as soon as you are done with it",
            r"keep an implementer until its pr is merged or handed elsewhere",
            r"\*\*sweep\*\* after every handover \(§5\.2 step 7\): the new orchestrator archives every finished worker, reviewer, planner and "
            r"previous-orchestrator session of this project",
            r"keeps itself, the merge agent and any session still running or with unpushed work",
            r"never archives a session that does not clearly belong to this project \(it lists it for the owner\)",
        ),
        "ORCHESTRATION 7.4: archive each finished worker at once; the new orchestrator sweeps after every handover (owner decisions of 2026-11-17)",
        forbidden=(r"once their metrics row is logged and the owner has seen the batch report",),
    ),
    DocRule(
        "orch-merge-agent", ORCH,
        (
            r"\* \*\*merge agent:\*\* the merge agent merges every ready pr that is not owner-only under the owner's standing authorization, one at a time, "
            r"and an owner-only pr only as kind `owner-batch`",
            OWNER_ONLY,
            r"a pr in the security-rules, sync-merge or release area is marked ready only after the independent second-reviewer pass is clean",
            r"docs prs whose owner approval can wait go to it too and carry the status line "
            r"`working draft \.\.\.; not owner-approved \(see issue #15\)`",
            r"a merge agent the orchestrator spawns needs no owner authorization in its own session \(owner decision, #15 comment 7085221356\): "
            r"when it carries the tag `role:merge-agent`, its `parent_session_id` is that orchestrator and the body of #15 names it as active, "
            + STANDING + r"; " + VERIFY_DECISION + r"; the orchestrator never passes an approval on to it; "
            r"owner-only prs still need a batch approval, `veto #n` still stops a merge and `scripts/merge_ready\.py` still runs every check",
            CLASSES, OWNER_HANDS, BATCH, APPROVAL_FORM, SAME_PATCH,
            r"merge order \(#15 comment 7005414860\): the orchestrator sends " + ORDER_TAIL,
        ),
        "ORCHESTRATION 7.5: the merge agent merges general PRs under the standing authorization and owner-only PRs from the batch approval (D1-D3 of #229)",
        forbidden=OLD_MERGE_AGENT_AUTH,
    ),
    DocRule(
        "orch-update-branch", ORCH,
        (r"the merge agent updates a pr's branch itself with `scripts/update-branch\.sh <n> <expected head sha>` "
         r"\(owner decision, #15 comment 7008033864\)",),
        "ORCHESTRATION 7.5: the merge agent updates PR branches itself through scripts/update-branch.sh (owner decision, #15 7008033864)",
    ),
    DocRule(
        "orch-throttle", ORCH,
        (
            r"§7\.7\.6 throttle order\.", r"\(1\) no optional extras \(recurring reviews r3 and r4,",
            r"a 7-day `allowed_warning` holds at stage 1 and required work goes on; stage 2 applies in overage; stage 3 only on an owner decision in #15",
            r"the stages are cumulative", r"\(3\) pause new work and finish the open prs",
            r"\(2\) halve the concurrency limit, once per check-in while stage 2 applies, at most twice",
            r"a stage lifts, and the limit returns to the §7\.1 default, at the first check-in where its trigger no longer applies",
            r"never throttled: review rounds, verification of blockers and majors, the second reviewer on security-rules, "
            r"sync-merge and release prs, delta reviews, and the r2 usage read",
        ),
        "ORCHESTRATION 7.7.6: throttle only near a rate limit or in overage: extras, halve the concurrency, pause new work; reviews are never throttled",
        forbidden=(r"the worker cap 3, then 2", r"stays at stage 1 with the cap at 5", r"recurring reviews r2", r"one stage per check-in",
                   r"§7\.7\.5 forecast says"),
    ),
    DocRule(
        "orch-usage-edges", ORCH,
        (
            r"set one extra check-in about 10 minutes out, only if none is pending",
            r"the second look is the first wake at least 10 minutes after the warning was first seen",
            r"§7\.7\.4 does nothing if the newest `paused` comment already has a `resumed` after it",
            r"`send_later` at the new `resetsat` \+ 5 minutes \(60 minutes from now if `resetsat` is missing or already past, as in §7\.7\.2 step 1\)",
            r"delete the old reminder, whether or not it fired",
            r"skip a session whose `worker-result` is already posted \(collect it instead, §7\.3\)",
            r"delete the resume reminder, whether or not it fired",
            r"the window is from `resetsat` minus 5 hours \(`five_hour`\) or from the last `resumed` comment \(any other `ratelimittype`\), up to now",
        ),
        "ORCHESTRATION 7.7.1, 7.7.4, 7.7.5: one 10-minute check-in, resume runs once, skips posted results, re-pause fallback, window defined (#69)",
        forbidden=(
            r"delete the spent resume reminder", r"set one extra check-in about 10 minutes out(?!, only if none is pending)",
            r"send_later` at the new `resetsat` \+ 5 minutes \(delete the spent",
        ),
    ),
    DocRule(
        "orch-spawn-templates", ORCH,
        (
            r"role: agents/prompts/reviewer\.md\. pr #\{pr\}, round \{round\}, whole diff \{base_sha\}\.\.\{head_sha\}, focus since \{reviewed_through\}",
            r"role:<role>\s+orchestrator \| implementer \| merge-agent \| reviewer \| second-reviewer \| escalation-reviewer \| planner \| retro",
        ),
        "ORCHESTRATION 2.1 and 8.3: the reviewer spawn carries the whole diff and a focus point; the role tags name the new reviewers",
        forbidden=(r"role: agents/prompts/reviewer\.md\. pr #\{pr\}, round \{round\}, range",),
    ),
    DocRule(
        "orch-design-rounds", ORCH,
        (
            r"max 3 rounds per design pr", r"round \{round\} of max 3", r"\(round 3, or an earlier round when nothing above nit is open\)",
        ),
        "ORCHESTRATION 8.5: 3 design rounds, as roles.yaml, design-reviewer.md and orchestrator.md (rev 46 row 5)",
        forbidden=(r"round \{round\} of max 2", r"max 2 rounds per design pr"),
    ),
    DocRule(
        "orch-token-rules", ORCH,
        (
            r"### 7\.2\.3 token rules \(owner decision, #15 comment 7070278995, 2026-11-21\)",
            r"the one home of these rules; `review\.md`, `agents/roles\.yaml` and the orchestrator prompt link here",
            r"\*\*nits are accepted without a round\.\*\* a review with verdict `ready_nits_only` goes to the merge request \(§7\.5\)\. "
            r"its nits are recorded as accepted in the pr review table and the round row: no fix round, no re-review, no follow-up issue",
            r"\*\*a small fix is re-checked cheaply\.\*\* a re-check of a small fix-only or docs-only commit \(the fixes of the previous round's "
            r"findings, about 30 changed lines or fewer in total, or up to about 150 when they touch only tests or docs; "
            r"owner decision 7153510972, item 4\) is the delta review of §7\.2, with its inputs, done by a fresh sonnet medium "
            r"reviewer \(`recheck-reviewer` in `agents/roles\.yaml`\), focused on those findings\. full rounds stay opus at the effort "
            r"`agents/roles\.yaml` gives the reviewer",
            r"\*\*guard and prompt_rules hardening prs stop early\.\*\* on a pr that hardens `scripts/guards\.sh`, "
            r"`scripts/hooks/pretooluse_guard\.py` or `scripts/prompt_rules\.py`, the second round that finds new bypass forms ends the pr\. "
            r"the forms are recorded as accepted residuals in the pr body \(the hook is a tripwire, f18\) and the pr goes to the merge request\.",
            r"\*\*reviewer effort\*\* is strictly per `agents/roles\.yaml`, which owns the rule",
            r"### 6\.1 session row \(one per session, written as it is archived\)",
            r"write it just before `archive_session` \(§7\.4\), for every role, reviewers included",
            r"\*\*archive\*\* \(`archive_session`\) each worker, reviewer and planner session as soon as you are done with it \(result read, "
            r"no follow-up planned\) and its `metrics:session` row \(§6\.1\) is written",
            r"a small fix-only or docs-only commit that fixes the previous round's findings gets the cheap re-check of §7\.2\.3",
        ),
        "ORCHESTRATION 7.2.3: ready_nits_only accepts its nits, cheap Sonnet re-check, hardening-PR stop, one metrics:session row per archived session "
        "(owner decision, #15 comment 7070278995)",
        forbidden=(r"a delta review always runs; there is no owner-acceptance alternative, for any pr\. record",
                   r"each about 30 changed lines or fewer, or docs only", r"any other finding above nit is still fixed"),
    ),
    DocRule(
        "orch-owner-merge-exceptions", ORCH,
        (
            r"ready prs are `is:open is:pr draft:false`; owner-only prs wait for the owner's batch approval \(below\), every other one goes to the merge agent",
            r"\*\*before the merge request\*\* \(to the merge agent, or as a batch-approval request to the owner for an owner-only pr\) "
            r"the orchestrator checks",
            r"scan the pr body for them before the merge request",
            r"after each merge, the next ready pr is updated: by the merge agent itself with `scripts/update-branch\.sh` \(above\) when it is in "
            r"the merge agent's batch; otherwise the \*\*orchestrator\*\* updates it with `update_pull_request_branch`",
            r"then the merge agent merges it: a `general` pr under the standing authorization, an owner-only pr as kind `owner-batch` once the "
            r"owner's batch approval lists it \(§7\.5\)",
        ),
        "ORCHESTRATION 7.5, 7.6: the merge agent merges every READY PR, an owner-only one as owner-batch once the owner's batch approval lists it (issue 147)",
        forbidden=(
            r"the owner's queue is `is:open is:pr draft:false`", r"before asking the owner to merge", r"after each owner merge, the \*\*orchestrator\*\*",
            r"because it is mergeable; the owner merges\.", r"after each merge by the owner, the \*\*orchestrator\*\*",
            r"or the owner for an owner-only pr \(§7\.5\)",
            r"owner-only prs wait in the owner's queue",
        ),
    ),
    DocRule(
        "orch-labels-exist", ORCH,
        (r"\*\*labels exist\.\*\* `orchestrator-state` and `owner-todo` were created by task m0-o9 and are in use",),
        "ORCHESTRATION 4.5: the orchestrator-state and owner-todo labels exist (M0-O9 is done; #260 item 11)",
        forbidden=(r"\b(?:are|is) not created yet", r"opens issues without the label"),
    ),
    DocRule(
        "review-token-rules", "REVIEW.md",
        (
            r"6\. \*\*token rules\*\* \(owner decision, #15 comment 7070278995; the rules are in `docs/orchestration\.md` §7\.2\.3\): "
            r"a `ready_nits_only` verdict is final, its nits are accepted with no fix round, no re-review and no follow-up issue; "
            r"a re-check of a small fix-only or docs-only commit is a sonnet medium reviewer \(`recheck-reviewer`\), not a full round; "
            r"on guard and prompt_rules hardening prs the second round that reports new bypass forms ends the pr",
        ),
        "REVIEW.md Loop and cap item 6 links the token rules of ORCHESTRATION 7.2.3 (owner decision, #15 comment 7070278995)",
    ),
    DocRule(
        "review-dispatchers", "REVIEW.md",
        (
            r"14\. \*\*dispatchers \(`:core:data` and `:app` prs\)\*\*: until detekt 2\.0 is stable and gives the android modules type resolution "
            r"\(#218, tracked on m6\), check by hand that dispatchers are injected and no `dispatchers\.io`, `dispatchers\.default` or "
            r"`dispatchers\.main` is hard-coded in a class \(`docs/android-best-practices\.md` §5\); a hard-coded dispatcher is a `minor` finding",
        ),
        "REVIEW.md What to check item 14: manual dispatcher-injection check on :core:data and :app PRs until detekt 2.0 is stable (#218)",
    ),
    DocRule(
        "roles-recheck-reviewer", "agents/roles.yaml",
        (
            r"recheck-reviewer: model: sonnet effort: medium session: fresh, for the re-check of a small fix-only or docs-only commit",
            r"prompt: agents/prompts/reviewer\.md",
            r"reviewer effort is strictly per `max_effort_when`: never max for consistency",
        ),
        "roles.yaml: the Sonnet medium recheck-reviewer, and reviewer effort strictly per max_effort_when (owner decision, #15 comment 7070278995)",
        forbidden=(r"(?<!never )max for consistency", r"recheck-reviewer: model: opus"),
    ),
    DocRule(
        "followups-title-forms", "docs/FOLLOW-UPS.md",
        (
            r"issue title: `follow-up from pr #<n>: <finding title>` \(the form in use\) or `\[follow-up\] <finding title>`; a standing item is "
            r"`track: <what>`, a finding of a repo-wide review is `repo review \(<aspect>\): <finding title>`",
        ),
        "FOLLOW-UPS section 7: the issue title forms in use are allowed (#260 item 10)",
        forbidden=(r"issue title: `\[follow-up\] <finding title>`\. labels",),
    ),
    DocRule(
        "followups-burndown-alerts", "docs/FOLLOW-UPS.md",
        (r"it also reviews every open dependabot alert \(`docs/security\.md` §1 item 2\)",),
        "FOLLOW-UPS section 8: the Mx-FU burn-down includes the Dependabot alert review of SECURITY.md (#260 item 9)",
    ),
    DocRule(
        "branch-protection-job-count", "docs/BRANCH-PROTECTION.md",
        (r"only the jobs listed above \(every job in `ci\.yml`\)",),
        "BRANCH-PROTECTION section 4: no hard-coded job count that can go stale, as the ruleset and section 2 (#260 item 1)",
        forbidden=(r"only the (?:eight|ten|eleven) jobs above",),
    ),
    DocRule(
        "orch-delegated-decisions", ORCH,
        _DELEGATED + _SCOPE + (
            RETAINED,
            r"\| \*\*approver\*\* \| opus / high \| one pr; fresh session started by the orchestrator \(§7\.5\)",
            r"over-cap deferrals \(owner decision, #15 comment 7075812943\): over the cap the orchestrator may still defer a minor finding whose "
            r"fix is out of the pr's scope, or when the pr is at the line guard, with the usual follow-up issue and `decision` comment, without "
            r"asking; majors still need the owner, and the stop-and-ask rule above still applies to every other deferral",
            r"its ruling per pr is final \(owner decision, #15 comment 7075812943\) and the orchestrator follows it without asking",
            r"the approver's record of the delegation below is the one exception",
            r"approvals of orchestrator decisions \(merges of prs that stay with the owner\)",
            r"an approver agent's anchored `batch approval:` record on #15 counts as the owner's batch approval",
            r"\(`agents/prompts/approver\.md`, opus high, `agents/roles\.yaml`\)",
            r"with the pr number, the head sha, the round history and the deferral records, and the §8\.3 closing message",
            r"it checks `review\.md`, the clean final round, ci, that no closing keyword precedes an issue number, the pr's changed paths "
            r"against the owner-retained list \(§1\.1\) and the owner's veto",
            r"it never merges, edits or pushes",
            r"the merge agent merges the listed pr as `owner-batch` with `--approval <comment-id>`",
            r"the orchestrator reads #15 for one before it sends the merge request and the merge agent right before it runs "
            r"`scripts/merge_ready\.py`, and neither merges or requests the merge of a vetoed pr",
            r"is refused by the approver and waits for the owner's own batch approval",
            r"the second reviewer runs at high effort \(`agents/roles\.yaml`; owner decision 7153510972, item 1\)",
            r"for an owner-only pr in the approver's scope \(§1\.1\), an approver agent's anchored",
            r"or any owner-only path outside the approver's scope \(§1\.1\), is refused by the approver",
        ),
        "ORCHESTRATION 1.1, 7.2.1, 7.2.2, 7.5: the four delegated decisions, the exact owner-retained list, the approver and the owner's veto "
        "(owner decision, #15 comment 7075812943)",
        forbidden=(r"for an owner-only pr, the owner's batch approval is always required",),
    ),
    DocRule(
        "roles-second-reviewer", "agents/roles.yaml",
        (
            r"second-reviewer: model: opus effort: high session: fresh, same round as the reviewer, only for security-rules, sync-merge "
            r"and release prs, at high effort \(owner decision 7153510972 item 1; replaces the second reviewer for every risk:high pr\) "
            r"prompt: agents/prompts/second-reviewer\.md escalation-reviewer:",
        ),
        "roles.yaml: the second reviewer is high effort and only for security-rules, sync-merge and release PRs (owner decision 7153510972)",
        forbidden=(r"second-reviewer: model: opus effort: max", r"second-reviewer:.{0,300}max_effort_when"),
    ),
    DocRule(
        "roles-approver", "agents/roles.yaml",
        (
            r"approver: model: opus effort: high session: fresh, one per pr \(inputs: pr number, head sha, round history, deferral records\) "
            r"prompt: agents/prompts/approver\.md",
        ),
        "roles.yaml: the approver is Opus high, one fresh session per PR (owner decision, #15 comment 7075812943)",
        forbidden=(r"approver: model: (?:sonnet|haiku)",),
    ),
    DocRule(
        "followups-over-cap", "docs/FOLLOW-UPS.md",
        (r"the orchestrator may still defer minors out of the pr's scope or at the line guard \(owner decision, #15 comment 7075812943; "
         r"an implementer in a manual loop still asks the owner\)",
         r"asks the owner which follow-ups to fix as small prs \(except the orchestrator's deferral of minors out of the pr's scope or at the "
         r"line guard, #15 comment 7075812943\)"),
        "FOLLOW-UPS section 1 and the risk table: the over-cap deferral exception of the owner decision is the orchestrator's alone and stands "
        "next to the stop-and-ask rule",
        forbidden=(r"minors out of the pr's scope or at the line guard may still be deferred",),
    ),
    DocRule(
        "review-approver-record", "REVIEW.md",
        (r"an owner-only pr waits for the owner's approval or, for prs in the approver's scope \(`docs/orchestration\.md` §1\.1\), the approver's record",),
        "REVIEW.md Loop and cap item 3: an owner-only PR waits for the owner or, for PRs in the approver's scope (ORCHESTRATION 1.1), the approver's record",
    ),
    DocRule(
        "plan-approver-record", "docs/PLAN.md",
        (r"an owner-only pr waits for the owner's approval or the approver's record",
         r"or an owner-only pr waits for the owner or the approver's record"),
        "PLAN section 6: an owner-only PR waits for the owner or the approver's record (#15 comment 7075812943)",
    ),
    DocRule(
        "plan-escalation-final", "docs/PLAN.md",
        (r"its ruling is final; only a finding above nit still open after a `fix` ruling's round 5 reaches you",),
        "PLAN section 6: the escalation ruling is final, and only what is still open above nit after a `fix` ruling's round 5 reaches the owner",
        forbidden=(r"so nothing it decides reaches you", r"only what it sends to the owner reaches you"),
    ),
    DocRule(
        "orch-reviews-on-push", ORCH,
        (
            r"\*\*reviews start on push \(owner decision, #15 comment 7075952806\):\*\* the orchestrator spawns the reviewer as soon as the "
            r"implementer has pushed, without waiting for ci\. the implementer does not wait in a loop for ci after every fix push; it checks with "
            r"`scripts/verify\.sh`, pushes and ends its turn\. ci must be green on the head before the pr is marked ready \(§7\.5\) and before "
            r"the merge request; a red ci is diagnosed at once \(§7\.4\) and fixed in the next push\. this bullet is the home of the rule",
            r"\(4\) ci is green on the pr head \(§7\.1\)",
            r"marks a draft pr ready after clean review rounds and with ci green on the head \(§7\.1\)",
            r"wait for `scripts/verify\.sh` with a monitor/until-loop and do not end the turn while it runs; do not loop-wait for ci after every fix push "
            r"\(reviews start on push, §7\.1\)",
            r"after every fix push do not wait in a loop for ci: the reviewer starts on your push \(orchestration §7\.1\)",
        ),
        "ORCHESTRATION 7.1 (home), 7.5, 7.8 and 8.2: reviews start on push, no loop-wait for CI, CI green before READY and the merge request "
        "(owner decision, #15 comment 7075952806)",
        forbidden=PUSH_WORDING_STALE,
    ),
    # Owner decision 7153510972 on #399 (token savings), items 1-6; the phrases are listed in test_prompt_rules.TokenSavingsTests.
    DocRule(
        "token-savings-roles", "agents/roles.yaml",
        tuple(re.escape(t) for t in (
            "the first reviewer of a pr labelled area:security-rules or area:sync-merge",
            "a risk:high implementer runs at high effort, not max",
            "for security-rules, sync-merge and release prs",
            "up to about 150 changed lines when they touch only tests or docs",
            "a fresh merge agent once a day, at the first merge request after 00:00 utc",
            "the first reviewer (the primary reviewer, not the second reviewer) in every round (owner decision 7158603054 item 1)",
            "25% of a 200k window (owner decision 7158603054 item 2)",
            "orchestrator_handover_at_percent_200k: 25",
            "implementer_handoff_at_percent: 30",
            "orchestrator_handover_at_percent_1m: 50",
        )),
        "roles.yaml carries the token-savings rules: reviewer max effort only for the first reviewer of security-rules and sync-merge PRs, the "
        "second reviewer high, the implementer at high and handing off at 30%, the 150-line re-check, the daily merge agent (7153510972)",
        forbidden=(r"second-reviewer: model: opus effort: max",
                   r"a new implementer for a pr that already had 3 or more review rounds max_effort_when: - the pr is tagged risk:high",
                   r"every later round", r"daily pacing recompute", r"orchestrator_handover_at_percent_200k: 30", r"orchestrator_handover_at_percent_1m: 35",
                   r"pending owner confirmation"),
    ),
    DocRule(
        "token-savings-orchestration", ORCH,
        tuple(re.escape(t) for t in (
            "opus / high (max for the first reviewer of a pr labelled `area:security-rules` or `area:sync-merge`)",
            "the implementer runs at high effort, not max",
            "a pr in the security-rules, sync-merge or release area also needs a clean independent second-reviewer pass",
            "the second reviewer runs at high effort",
            "about 30 changed lines or fewer in total, or up to about 150 when they touch only tests or docs",
            "an implementer hands off at about 30% context",
            "a fix round goes to a fresh implementer",
            "a pr above 500 counted lines is split before its first review round",
            "a fresh merge agent once a day, at the first merge request after 00:00 utc (checked at each check-in)",
            "spawn it in three steps: (1) `create_session` with the template below and `merge requests: wait for the first merge request`",
            "(3) send the first merge request with `send_message`, only after that update",
            "a `merge-agent` row that is not archived or failed",
            "if the body does not name you as active, do not merge; send_message the orchestrator and wait",
            "sets the old merge-agent row to archived (once it has no merge in flight) and adds the new agent's row",
            "the merge-agent row's `spawned-at` records the rotation time",
            "check that the state issue body names you as active before your first merge",
            "trigger: about 50% of a 1m window (25% of a 200k window (owner decision 7158603054 item 2)",
            "hand over at about 50% of a 1m window (25% of a 200k window (owner decision 7158603054 item 2)",
            "the first reviewer is the primary reviewer in every round (owner decision 7158603054, item 1)",
            "### 8.6 merge agent",
            "tags `role:merge-agent`, `tally:process`",
        )),
        "ORCHESTRATION carries the token-savings rules: effort, implementer context and fix rounds, PR size, the 150-line re-check, the daily "
        "merge agent and its spawn message, the 50% orchestrator handover (7239676323 item 5)",
        forbidden=(r"opus / high \(max for `risk:high`\)", r"second reviewer every round", r"max effort for `risk:high`",
                   r"about 35% of a 1m window", r"about 50% of a 1m window \(40% of a 200k", r"daily pacing recompute", r"this pr's scaling",
                   r"pending owner confirmation", r"pr #408's scaling", r"30% of a 200k", r"i\.e\. the orchestrator's first check-in of the utc day"),
    ),
    DocRule(
        "token-savings-m1", "docs/milestones/M1.md",
        (r"max only for the first reviewer of an `area:security-rules` or `area:sync-merge` pr",),
        "the M1 plan gives max effort only to the first reviewer of a security-rules or sync-merge PR, as PLAN 9.1 does (7153510972)",
        forbidden=(r"both at max for `risk:high`",),
    ),
)


def normalize(text):
    """Without hidden text (HTML comments), whitespace collapsed to single spaces."""
    return " ".join(_HTML_COMMENT.sub(" ", text).split())


_BLOCK_START = re.compile(r"\s*(?:[-*]\s|\d+\.\s|\|)")


def normalize_sentences(text):
    """normalize(), but a blank line, a heading line, a bullet, a numbered item or a table row also ends the sentence before it (and a
    heading after it), written as " . ". A hard-wrapped continuation line stays part of its sentence."""
    out = []
    for line in _HTML_COMMENT.sub(" ", text).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or _BLOCK_START.match(line):
            out.append(" . ")
        out.append(stripped)
        if stripped.startswith("#"):
            out.append(" . ")
    return " ".join(" ".join(out).split())


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
            if rule.forbidden_sentences:
                problems.extend(f"{rule.id}: {rule.message} (found /{p}/)" for p in rule.forbidden_sentences(text))
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
            if rule.forbidden_sentences:
                problems.extend(f"{rule.id}: {rule.message} (found /{p}/)" for p in rule.forbidden_sentences(text))
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
