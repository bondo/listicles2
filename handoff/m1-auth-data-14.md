# Handoff: M1-14 auth data 1, domain sign-in and sign-out steps (branch m1/auth-data-14)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
M1-14 of `docs/milestones/M1.md` section 5, narrowed to part 1 by the split recorded in `docs/tasks.toml`: the Google
sign-in flow and the OQ-13 sign-out steps in `core/domain`, with fakes in `core/testing`. PR #319 (draft).

## Done
- Failing tests first (4cad1ac), then `GoogleSignIn`, `SignOut`, `LocalUserData`, `GoogleCredentials`, `Authentication` (1e1b785).
- Boundary test follows the timeout constant (682666f); `main` merged in (a0d649e, M1-33).
- PR comments: licence list 7084644086 (M1-O14), compiled never-run data-layer draft 7084644287 (M1-65).
- Task split: M1-65 (Firebase data layer, emulator tests), M1-66 (Credential Manager wrapper and `:app` wiring), owner task M1-O14 (licences).

## Next (in order)
1. Review rounds: fix findings above nit; push after `scripts/verify.sh --fast`.
2. Final commit: delete this file (M1-14 is already `done` with `pr = 319` in `docs/tasks.toml`).

## Decisions made
- Split M1-14 (implementer, recorded in the PR body for the orchestrator): the whole task measured about 780 changed
  lines before the app wiring (guard 600), and the wiring needs licences only the owner accepts (M1-O14).
- Sign-out wait timeout 5 s (`SignOut.PENDING_WRITES_TIMEOUT_MS`); AUTH-03 names no value.
- Steps 2-5 run in an injected application scope (checklist section 5), not `NonCancellable`.
- `unsentChangesSeen` comes from listeners only (M1.md M1-14); no listener exists before M2.

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/auth-data-14 && git checkout m1/auth-data-14
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- `TestScope.advanceUntilIdle()` stops at `backgroundScope` work: drive the external scope with `runCurrent()`.
- `kotlinx-coroutines-test` 1.11.0 was already in `gradle/verification-metadata.xml` (Compose test pulls it).
- Task ids: other branches hold M1-63 (#315, m1/build-logic-46) and M1-64 (m1/build-logic-46); main holds M1-O13.
- Auth emulator (firebase-tools 15.36.0): a fake Google ID token is strict JSON with a string `sub`; anything that is
  neither JSON nor a JWT fails with `INVALID_IDP_RESPONSE`.
- No KVM in the cloud container: `androidTest` only compiles here; the `ui` CI job runs it.

## Waiting on the owner
- M1-O14
