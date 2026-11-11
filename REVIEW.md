# REVIEW.md: how reviews work

Reviewers are fresh Claude sessions with no authoring context. This file is the contract between
author and reviewer. Source of the process: `docs/PLAN.md` section 6.

## What the reviewer gets and does
- Round 1: the PR diff, the PR description, this file, and `docs/PLAN.md` for the relevant section.
- Round N>1: only the commits since the last round, the open findings, and this file. Re-check each
  open finding, then review the new code. Do not re-review unchanged code.
- Rely on CI for the full suite. Run targeted tests only when a finding needs proof.
- **Reviewers never edit or push the PR branch.** Report only: severity, file:line, recommendation, and a recommended
  disposition (`fix-now` or `defer`) per finding. The author fixes. A reviewer may use a throwaway branch or worktree to
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
    (`major` when it is a gate or guard, otherwise `minor`).

## Severity
| Severity | Meaning | Author must |
|---|---|---|
| `blocker` | Data loss or corruption, security hole, crash on a main path, or a broken build/gate. Must not merge. | Fix |
| `major` | Wrong behavior in a realistic case, a test that cannot catch the bug it claims to, a weakened gate. | Fix |
| `minor` | Real but low-impact: edge case, unclear code that invites bugs, missing non-critical test. | Fix, mark `disputed` with a reason, or `deferred` with an issue link (see Loop and cap) |
| `nit` | Style, naming, wording, taste. | Optional |

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
      "disposition": "fix-now",
      "status": "open"
    }
  ],
  "verdict": "changes_requested"
}
```

- IDs are `R<round>-<nn>` and are stable; a finding keeps its ID in later rounds. When the repository has
  earlier review rounds recorded in commit messages or comments, continue the numbering from the last used.
- `disposition` (recommended by the reviewer): `fix-now`, or `defer` (only for `minor`/`nit`, see below).
- `status`: `open | fixed | disputed | withdrawn | deferred` (`deferred` = minor/nit moved to a follow-up issue; the author links it). The reviewer sets `fixed` or `withdrawn` after checking;
  the author may set `disputed` with a reason in the PR, never `fixed`.
- `verdict`: `changes_requested`, or `ready_nits_only` when nothing above `nit` is open, or every remaining minor is deferred.

## Loop and cap
1. Author fixes everything above `nit` (or disputes with a reason; minors may be deferred, see below) and pushes.
2. A new reviewer session runs the next round.
3. When only nits remain the reviewer posts `ready_nits_only` and the owner squash-merges.
   Deferral: once no blocker or major is open, `minor` and `nit` findings may be deferred to follow-up issues instead of
   another round. The author opens one issue per deferred finding (title, file:line, scenario) and links it in the PR.
   Blockers and majors are never deferred.
4. **Maximum 4 rounds.** If round 4 still has findings above `nit`, stop and report to the owner, who decides.
   Fixes made after round 4 are not re-reviewed unless the owner asks.
5. Disputes: the reviewer either withdraws or restates with new evidence; the owner breaks ties.
