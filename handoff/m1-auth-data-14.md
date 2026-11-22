# Handoff: M1-14 auth data 1, domain sign-in and sign-out steps (branch m1/auth-data-14)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-14, narrowed by the split in `docs/tasks.toml` (M1-67 data layer, M1-66 wiring), PR #319 (draft); fix round 1.

## Done
- Domain steps and fakes (4cad1ac, 1e1b785), split ddb9f08 and renumber 246e924 (R1-05 = S1-03 done there).
- `main` merged c7bd2d0 (main's M1-14 Auth-record check, privacy Q5, moved to M1-67) and 5a00b3d (#315).
- R1-01, R1-02 tests 4a37050 (each fails its reviewer mutant). R1-06, R1-07: accepted by the orchestrator, no change.
- R1-03 = S1-01: M1-15 on M1-66 (ready simulation: it was ready once M1-62 and M1-67 were done; now waits).

## Next (in order)
1. R1-04 = S1-02: M1-14 -> M1-66 in `core/data/build.gradle.kts:5`,
   `app/src/main/kotlin/dk/bjarkebjarke/tally/start/SessionModule.kt:10` and
   `app/src/test/kotlin/dk/bjarkebjarke/tally/AppGraphTest.kt:44`; M1-14 -> M1-67 in
   `core/domain/src/main/kotlin/dk/bjarkebjarke/tally/domain/session/SessionState.kt:7`.
2. Final commit: delete this file, and M1-14 -> M1-67 in `docs/privacy/privacy-en.md:23` and
   `docs/privacy/privacy-da.md:23` (4 lines: fit only with this file gone). M1-O14 stays `todo` (orchestrator).
3. `scripts/verify.sh --fast`, push; PR body review table (R1: 0/0/5/2, S1: 0/0/2/1, both changes_requested);
   WORKER-RESULT comment on #319, one line to the orchestrator that the #15 body names.

## Facts that save time
- Diff guard: 589 lines at 5a00b3d (CI fails above 600; this file counts). R1-04 adds 8 lines; edits inside
  blocks this PR already adds or changes cost no extra.
- `advanceUntilIdle()` stops at `backgroundScope` work; `runCurrent()` and `advanceTimeBy()` run it.
- Task ids: M1-63 to M1-65, M1-68, M1-69 belong to #315, #320, #321; M1-O13 is on `main`.

## Waiting on the owner
- none (M1-O14 decided: #15 comment 7085175461; not this PR's to mark done)
