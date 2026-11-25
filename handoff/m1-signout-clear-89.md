# Handoff: M1-89, PR #398 (branch m1/signout-clear-89)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-89 (`docs/tasks.toml`, `docs/milestones/M1.md` row 10c): clear the copy on the phone at every signed-out state, also
when Firebase signs out by itself (#357). Fix round after review round 1 (orchestrator #46, `session_013srDQjuovULJERZ9i5rcCS`).

## Done
- Round 1 work, all committed and pushed with this file: merge of main 482e394 (a26eb09, M1-82 conflict in
  SignedOutStartTest kept both bindings); R1-01 failing test 958fdf1, fix 86e1713 (MainActivity starts SignedOutCleanup
  after StartViewModel's first Ready, so the update gate's config/app read comes first); S1-02, S1-03 and R1-01's notes
  in aa0eb7e (LocalUserData KDoc names clear() for every per-account store; M1-25 notes and M1.md; privacy timing en/da;
  M1-82 notes name the signed-out read).
- Checked: `:app:testDebugUnitTest` for SignedOutStartTest (4/4) and SignInAndSignOutWiringTest (3/3) at 86e1713; the
  new test failed before the fix (expected [] but was [clear, cleared]). Full `scripts/verify.sh` NOT run on this round.

## Next (in order)
1. Trim the PR to about 450 changed lines or fewer (`git diff --shortstat origin/main...HEAD` said 464 before this file):
   revert the cosmetic `file()` change in core/data/src/androidTest/.../FirebaseEmulator.kt (back to `org.json` names)
   and the SignInAndSignOutModule KDoc in app/src/main/.../session/SessionModule.kt to main's one line, then tighten
   KDoc where it repeats. If it cannot get under ~450 without losing substance, propose a split in the WORKER-RESULT.
2. Delete this file in the same or the last commit.
3. `scripts/verify.sh` to completion (Monitor or until-loop); push plainly (foreign-commit check first: API commit list,
   only `claude` / Claude <noreply@anthropic.com> and the owner).
4. Refresh the PR body (scratch copy is gone with the container: rebuild from the live body): review table rows for
   round 1 (R1: 1 major, 1 minor, 1 nit; S1: 2 minor, 1 nit), R1-02 and S1-01 `deferred` -> #405 (owner OK, #399
   comment 7145629110), the open-question section answered by that deferral, R1-03 disputed (below), R1-01 in
   Consequences (the gate's signed-out read and the start order), evidence lines from the new verify run.
5. WORKER-RESULT comment on PR #398, then send_message to session_013srDQjuovULJERZ9i5rcCS with the one-line version.

## Decisions made
- R1-01: start the cleanup after the start-up root's first Ready (reviewer's option b), not a gate retry (a per-try
  timeout would add seconds at most signed-out starts) or a FirestoreSession lock (larger change). Implementer, this round.
- R1-03 disputed: `scripts/merge_ready.py` refuses a closing keyword before an issue number in title, body or commits
  for every kind (lines 15, 576), so the body keeps "mark #357 done"; FOLLOW-UPS.md section 7's "Closes #n" conflicts
  with it (a note for the orchestrator, not this PR).

## Open findings
- R1-01 major: fixed (958fdf1, 86e1713). S1-02 minor: fixed (aa0eb7e). S1-03 nit: fixed (aa0eb7e).
- R1-03 nit: disputed (above). R1-02, S1-01 minor: deferred -> #405 with owner OK; do not fix.

## Commands to resume
```
git fetch origin m1/signout-clear-89 && git checkout m1/signout-clear-89
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- The clone is shallow: run `git fetch --unshallow origin` first, or ci_scope.py runs the slow gate self-tests (10+ min).
- No KVM here: the emulator tests run only in CI's `ui` job. The inline-Python guard blocks text that names `agents/`.

## Waiting on the owner
- none
