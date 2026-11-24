# Handoff: M1-18 part 1, PR #395 (branch m1/household-data-18)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-18 as narrowed by its split (`docs/tasks.toml`; `docs/milestones/M1.md` section 5, "M1-18 / M1-31 Household data" and
the split note after it): the create-household batch and create invite of PLAN 3.1 in `:core:domain` and `:core:data`,
with Firestore emulator tests (`ui` job).

## Done
- Test first: 230d2e9 (domain and emulator tests against drafts), d40c841 and 0bfe685 (the users-doc check). Green steps:
  4830a71 (Invites), 2858fab (`membership`), b428104 (FirestoreHouseholds, with a join draft kept for M1-96), a2e7f31
  (narrowed to create and invite), 2aed3cc (split recorded; M1-18 done, pr 395).
- Self-review (verifier subagent): no blocker or major; minors fixed (74c237a failing emulator test, 4b5b9ba fix: a
  call on an instance a sign-out terminated fails instead of throwing; KDocs on queued writes), nits in 03f8c00.
- Merge of main 1a850c0 (M1-91, M1-92, M1-06; no conflict).
- `scripts/verify.sh` at 1a850c0: all 72 steps passed; the gate self-tests skipped (no gate input changed). Mutation 88
  of 99 killed (household 10 of 11: the survivor is `Membership.Member.householdId`'s getter, no domain test reads it).
- CI on 03f8c00: `ui` red only on the termination test (IllegalStateException from `get()`, before its fix); the other
  16 emulator tests green. CI on 1a850c0 was running when this file was written.

## Next (in order)
1. Review rounds start on push (ORCHESTRATION §7.1); the `ui` job must pass HouseholdsEmulatorTest (three tests) before
   READY. CI on 03f8c00 runs the termination test without its fix (expected red there).
2. Fix findings above nit (and minors of about 30 lines or fewer); keep the PR near its 454 changed lines (this file aside).
3. Before READY: delete this file in the final commit; refresh the PR body (review table, test evidence).

## Decisions made
- Split of M1-18 (implementer proposal, ids for the orchestrator to confirm): M1-18 create and invite; M1-96 lookup and
  join; M1-97 reads with the household-name copy, revoke, expired cleanup; M1-98 self-heal, notices, the copy's deletion.
- `membership()` in `core/domain` decides from `users/{uid}` (one household, P9 name) and runs the batch with the name,
  so the domain result types are covered (`:core:domain` line floor 95 %).
- Reads before a write use `Source.SERVER`: a call made offline fails at its read; a write that loses the connection
  after it stays queued and the call waits. Screens check the connection first (SYNC-03).
- `started { }` guards only the call that starts a Firestore task, never `await()` (FirestoreSession's rule).
- Emulator tests switch users through `FirestoreSession.clear()`, as the app's sign-out does, so no write goes out under
  the previous user (Firestore takes a user change asynchronously).
- KDocs that name M1-18 for moved work (StartGates `HouseholdNotices`, GateModule, SignOut `LocalUserData`, AppGraphTest)
  stay for M1-98 to rewrite; the M1.md split note points readers there (line budget).

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/household-data-18 && git checkout m1/household-data-18
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- No KVM here: the androidTest emulator tests run only in CI's `ui` job; `:core:data:compileDebugAndroidTestKotlin`
  compiles them locally.
- A commit with Kotlin changes takes about 4 minutes: the pre-commit detekt runs the licensee gate self-tests.
- ktlint wraps call chains of 4 or more calls; `db.document("users/$uid")` keeps them on one line.
- The clone was shallow, which makes `ci_scope.py local-scope` answer `run` (verify.sh then runs the slow gate
  self-tests, about 50 minutes); `git fetch --unshallow origin main` fixed it here.
- PR size: about 454 changed lines against main (this file aside), at the task's limit; review fixes should stay small.
- The constructor's `clock` is its last parameter on purpose: the test passes it as a trailing lambda.

## Waiting on the owner
- none
