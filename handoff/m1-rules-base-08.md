# Handoff: M1-08 rules base (branch m1/rules-base-08)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-08 (docs/milestones/M1.md section 5; PLAN 3.1 with P4, P5, P9): `signedIn()`, the users doc, config/app, the own
member path and the tombstone read, with allow and deny tests. The PR body has the scope and the evidence.

## Next (in order)
1. The owner's answer on `size()` (PR body, owner question). If A: align the PLAN P4 wording and the M1-13
   `Validation.kt` comment, if the owner wants that here. If B or C: change `validName` and the 50-non-BMP tests.
2. Review rounds: fix findings above nit, and minors of about 30 lines or fewer.
3. Final commit: `pr = <number>` for M1-08 in docs/tasks.toml (status is already done), delete this file.

## Facts that save time
- `git fetch --unshallow origin main` once in a fresh clone: then `scripts/ci_scope.py local-scope` says `skip` and
  verify skips the Gradle gate self-tests, which cannot resolve the pitest plugin in this container.
- Emulator: `size()` counts UTF-16 units, `trim()` removes ASCII whitespace only, `$(x)` with a `/` is not split.
  A lone UTF-16 surrogate in a test string hangs the client.

## Waiting on the owner
- The `size()` question on this PR.
