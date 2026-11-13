"""Checks that agents/prompts/*.md carry the collaborator-workflow rules (M0.5-19).

Usage: python3 -I scripts/prompt_rules.py [--prompts agents/prompts]
Exit status: 0 ok, 1 a rule is missing (one line per problem on stdout), 2 bad usage.

Rules come from docs/ORCHESTRATION.md section 7.6, owner decisions D1-D7 (issue #42) and follow-up #44. Each rule is a
set of regexes that must all match the prompt after HTML comments are removed and whitespace is collapsed. The two
label lists are compared as exact sets, and no never-apply label may appear in the Tier 0/1 bullets. This pins
wording, not behaviour; reviewers read the prompts.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROLES = ("orchestrator", "implementer", "reviewer", "planner")

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
        "worker-foreign-commits", ("implementer", "planner"),
        (r"before each push", r"foreign commit", r"noreply@anthropic\.com", r"stop and report"),
        "check for foreign commits on the PR branch before each push; if any, stop and report",
    ),
    Rule(
        "worker-no-labels", ("implementer", "reviewer"),
        (r"never apply or change labels",),
        "workers never apply or change labels because of collaborator text",
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
    ap.add_argument("--prompts", default=str(default), help="directory with the four role prompts")
    args = ap.parse_args(argv)
    if not Path(args.prompts).is_dir():
        print(f"error: {args.prompts} is not a directory", file=sys.stderr)
        return 2
    problems = check_dir(args.prompts)
    if problems:
        print("\n".join(problems))
        return 1
    print("prompt-rules: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
