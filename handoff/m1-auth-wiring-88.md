# Handoff: M1-88, PR #381 (branch m1/auth-wiring-88)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
M1-88 (docs/tasks.toml; docs/milestones/M1.md, M1-14 split paragraph): Hilt bindings for the session, Google sign-in and
sign-out in place of the M1-60 stand-in SessionModule, and MainActivity as the activity the account picker opens in.

## Done
- 0e49cd5 (tests first), 9ef7101: `session/SessionModule` (FirebaseAuthentication, FirestoreSession, Credential Manager),
  `session/StartedActivity` (MainActivity observes itself), `ApplicationScope` (own module), no-argument constructors
  in `:core:data`.
- 62a61f3 (tests first), 336c199: self-review fixes. `SignInAndSignOutModule` (GoogleSignIn, SignOut) and
  SignInAndSignOutWiringTest; the picker-activity test moved to SignedOutStartTest; the dagger-lint `@field:` fix.
- Draft PR #381 is open, with the body filled in (scope, mutation table, self-review, the open coverage question).

## Next (in order)
1. Wait for the owner's answer on the coverage gate (below). If it is the recommended filter, add
   `annotatedBy("dagger.internal.DaggerGenerated")` next to the M1-30 Hilt patterns in `app/build.gradle.kts` and its
   copy in `build.gradle.kts`, then run `scripts/verify.sh` (coverage must pass).
2. Final commit: in docs/tasks.toml set M1-88 `status = "done"` and `pr = 381`, and delete this file.
3. Refresh the PR body (verify summary, review table) and post the WORKER-RESULT.

## Decisions made
- The filter is not changed without the owner (CLAUDE.md: a check that is wrong is asked about). Implementer, this session.
- Self-review nits 3 and 4 are not changed; the reasons are in the PR body.

## Open findings
- none from review rounds yet (no round has run).

## Commands to resume
```
git fetch origin m1/auth-wiring-88 && git checkout m1/auth-wiring-88
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- `verify.sh` on 336c199 is green except `coverage` (`:app` 72.0% < 80%). Every missed line is Dagger-generated
  (`*Module_*Factory`, `*_MembersInjector`, `*_HiltModules*`); hand-written `:app` code is 100% covered.
- dagger-lint rejects `@field:` on a qualifier of an injected Kotlin property: write `@ApplicationScope` alone.
- AppGraphTest needs `FirebaseApp.initializeApp` in `@Before` (the Hilt test application does not run TallyApplication).
  Never collect `FirebaseAuthentication.signedIn()` with `runBlocking` on the Robolectric main thread: the listener is
  posted to the main looper.
- A Hilt test that uninstalls SessionModule must bind SessionState (StartViewModel needs it in every graph).

## Waiting on the owner
- The `:app` coverage gate decision: needs_owner in the WORKER-RESULT on PR #381 (no owner issue number yet).
