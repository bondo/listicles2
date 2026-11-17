# REVIEW.md: how reviews work

Reviewers are fresh Claude sessions with no authoring context. This file is the contract between
author and reviewer. Source of the process: `docs/PLAN.md` section 6.

## What the reviewer gets and does
- Every round, delta reviews included: the whole PR diff (`<base>..<head>`), the PR description, this file, `docs/PLAN.md` for
  the relevant section, and from round 2 the findings JSON of all earlier rounds. Focus on the commits since the last round:
  re-check each open finding, then review the new code and how the fixes interact with the old code.
- Run whatever proves a finding: any test, the app's JVM screenshots, or a script. CI runs the full suite. Findings come with proof.
- On `risk:high` PRs and in the protected areas a second reviewer (`agents/prompts/second-reviewer.md`) reviews the same round
  independently; the orchestrator merges both reports.
- **Reviewers never edit or push the PR branch.** Report only: severity, file:line, recommendation, and per finding an
  `area` and a `recommend` (`fix-now` or `defer`, see Findings format). The reviewer recommends and never decides deferral:
  the orchestrator (or the implementer in a manual loop) decides by `docs/FOLLOW-UPS.md`. The author fixes. A reviewer may use a throwaway branch or worktree to
  prove a finding; it is never pushed anywhere and is deleted afterwards.

## What to check
1. **Correctness**: logic errors, edge cases, overflow, nullability, concurrency, error handling.
2. **Security rules** (Firestore): every allow has a deny test; no path lets a non-member read or write;
   no privilege escalation; no unbounded writes.
3. **Test adequacy**: would the tests fail if the code were wrong? Look for assertions that cannot fail,
   mocks that replace the thing under test, and missing negative cases.
4. **Offline and sync**: behavior with no network, last-write-wins conflicts, listener cleanup.
5. **i18n**: no hardcoded strings; English and Danish both present; plurals use `<plurals>`.
6. **Accessibility**: touch targets, contrast, content descriptions, dark theme.
7. **Free-tier cost**: Firestore reads and writes per user action; no listeners on large collections without need.
8. **Process files and suppressions**: every `// justified:` reason is true and specific; no disabled tests,
   baselines or lowered thresholds (`scripts/guards.sh` catches the mechanical cases; check intent).
9. **Scope**: one concern per PR; flag unrelated changes.
10. **Test-first**: every code change, tooling included (hooks, scripts, guards, CI checks, metrics, status line), needs
    automated tests wired into `scripts/verify.sh` and CI, including negative cases (the check must fail on bad input).
    The commit order must show the failing test first, then the fix. Flag any untested change or untested tooling
    (`major` when it is a gate or guard, otherwise `minor`; see Severity).
11. **Android guidance**: code under `app/` follows `docs/ANDROID-BEST-PRACTICES.md` (implementers too); a deviation needs a recorded decision, otherwise `minor`.

## Severity
| Severity | Meaning | Author must |
|---|---|---|
| `blocker` | Data loss or corruption, security hole, crash on a main path, or a broken build/gate. Must not merge. | Fix |
| `major` | Wrong behavior in a realistic case, a test that cannot catch the bug it claims to, a weakened gate, an untested gate, guard or other tooling check (item 10). | Fix, or `deferred` only with owner OK (`docs/FOLLOW-UPS.md`) |
| `minor` | Real but low-impact: edge case, unclear code that invites bugs, other untested change or missing non-critical test (item 10). | Fix (small fixes, about 30 changed lines or fewer, are always made now), mark `disputed` with a reason, or `deferred` per `docs/FOLLOW-UPS.md` with an issue link (see Loop and cap) |
| `nit` | Style, naming, wording, taste. | Optional, or `deferred` per `docs/FOLLOW-UPS.md` |

When unsure between two levels, choose the lower and say why. Do not pad: no findings is a valid result.
Every finding must be checkable: cite file and line, and describe the failing input or scenario.

## Findings format
Post one PR comment (or write one file for local reviews) containing a fenced `json` block:

```json
{
  "round": 1,
  "reviewed_range": "<base>..<head>",
  "findings": [
    {
      "id": "R1-01",
      "severity": "major",
      "file": "path/File.kt",
      "line": 42,
      "title": "Short statement of the defect",
      "detail": "Failing scenario: input, expected, actual.",
      "recommendation": "What to change.",
      "status": "open",
      "area": "general",
      "recommend": "fix-now",
      "recommend_reason": "",
      "verified": "confirmed"
    }
  ],
  "verdict": "changes_requested"
}
```

- IDs are `R<round>-<nn>` (reviewer), `S<round>-<nn>` (second reviewer, never `R`: it runs in the same round, so a shared prefix would collide)
  and `D<round>-<nn>` (design-review rounds, `docs/ORCHESTRATION.md` 8.5). They are stable; a finding keeps its ID in later rounds. When the repository has
  earlier review rounds recorded in commit messages or comments, continue the numbering from the last used.
- `verified`: required for every `blocker` and `major`, left out for minor and nit. `confirmed` or `not reproduced`, taken from the answer of a verifier
  subagent (`agents/prompts/verifier.md`) that gets the finding and the code, never the reviewer's reasoning. A `not reproduced` finding is reported as such,
  never as `confirmed`, and does not block: the verdict, the cap and the loop count only findings that are confirmed (minor and nit need no verification).
- `area`: `security-rules | sync-merge | release | process | general`. Use the first three whenever the finding concerns Firestore
  rules and their tests, offline/last-write-wins merge, or the release workflow (never deferred without owner OK, `docs/FOLLOW-UPS.md`).
- `recommend` (the reviewer's advice, never a decision): `fix-now`, or `defer` (only for `minor`/`nit`, see below; blockers and majors are always `fix-now`).
  `recommend_reason` is one line, required for `defer`. The decider (orchestrator, or the implementer in a manual loop) may still say fix-now.
- `status`: `open | fixed | disputed | withdrawn | deferred` (`deferred` = moved to a follow-up issue by the decider, who links it). The reviewer sets `fixed` or `withdrawn` after checking;
  the author may set `disputed` with a reason in the PR, never `fixed`.
- `verdict`: `changes_requested`, or `ready_nits_only` when nothing above `nit` is open, or every remaining minor is deferred.
  `ready_deferred` and `cap_reached` are set by the decider, never by the reviewer.

## Loop and cap
1. The author (the same implementer session in every round) fixes everything above `nit` and every `minor` whose fix is small
   (about 30 changed lines or fewer), or disputes with a reason, and pushes every turn.
2. A new reviewer session runs the next round, with the whole PR diff.
3. When only nits or deferred minors remain the reviewer posts `ready_nits_only` and the owner squash-merges.
   Deferral: once no blocker or major is open, a `minor` whose fix is larger than about 30 changed lines or outside the PR's scope, and any `nit`, may be deferred
   to follow-up issues instead of another round, by the rules and issue template of `docs/FOLLOW-UPS.md` (one issue per deferred finding: title, file:line, scenario; linked in the PR and its review table).
   Blockers are never deferred; majors and protected areas only with owner OK. If every finding above `nit` was deferred and no commit
   followed the reviewed range, the decider accepts the PR without another round (`ready_deferred`, `accepted:` comment): a second signal for the owner to merge.
4. **Maximum 4 rounds per batch** (a one-batch PR: per PR; `docs/ORCHESTRATION.md` 6.2). The cap and the "only nits remain" test count only unresolved, non-deferred findings.
   If round 4 still has open findings above `nit` (deferred minors do not count), **one escalation reviewer per PR** (Opus, max effort,
   `agents/prompts/escalation-reviewer.md`, started by the orchestrator) reads the whole thread and decides `fix`, `split` or `owner`:
   - `fix`: the author fixes, and one more fresh round (round 5) reviews. Anything above `nit` still open after it goes to the owner.
   - `split`: the work moves to a new PR from `main` that takes `main` in with merge commits, never a rebase or force-push.
   - `owner`: taste or scope questions, which stay with the owner.
   There is no second escalation, and no commit lands unreviewed: a commit after a round gets a delta review.
5. Disputes: the reviewer either withdraws or restates with new evidence. If it is still disputed, the escalation reviewer rules with both arguments in front of it
   (this uses the PR's one escalation); taste or scope goes to the owner.
