# Handoff: M1-14 auth data 1, domain sign-in and sign-out steps (branch m1/auth-data-14)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-14, narrowed by the split in `docs/tasks.toml` (M1-67 data layer, M1-66 wiring), PR #319 (draft); fix round 1.

## Done
- Domain steps and fakes (4cad1ac, 1e1b785), split ddb9f08 and renumber 246e924 (R1-05 = S1-03 done there).
- `main` merged c7bd2d0: kept main's M1-25 notes; main's M1-14 Auth-record check (privacy Q5) moved to M1-67's notes.
- R1-01, R1-02 tests 4a37050 (each fails its reviewer mutant). R1-06, R1-07: accepted by the orchestrator, no change.

## Next (in order)
1. R1-03 = S1-01: `docs/tasks.toml` M1-15 `depends_on = ["M1-66", "M1-62"]`; `docs/milestones/M1.md` row 11 to match.
2. R1-04 = S1-02: M1-14 -> M1-66 in `core/data/build.gradle.kts:5`,
   `app/src/main/kotlin/dk/bjarkebjarke/tally/start/SessionModule.kt:10` and
   `app/src/test/kotlin/dk/bjarkebjarke/tally/AppGraphTest.kt:44`; M1-14 -> M1-67 in
   `core/domain/src/main/kotlin/dk/bjarkebjarke/tally/domain/session/SessionState.kt:7`.
3. Optional (ORCHESTRATION 4.4): M1-O14 `done`, notes cite #15 comment 7085175461 (owner accepted A, B, C); M1-66
   notes: licence lines go in an owner-merged PR citing it. Not asked for by the orchestrator: say so.
4. `scripts/verify.sh --fast`, push; PR body review table (R1: 0/0/5/2, S1: 0/0/2/1, both changes_requested);
   WORKER-RESULT comment on #319, one line to orchestrator #31 (session_013srDQhMFXe8fKEpt2LUoew).

## Facts that save time
- Diff guard: 585 lines at 4a37050 (CI fails above 600; this file counts). R1-04 adds about 8 lines; edits inside
  blocks this PR already adds or changes cost no extra. Spare lines: the split note in M1.md section 5 (3 lines).
- `advanceUntilIdle()` stops at `backgroundScope` work; `runCurrent()` and `advanceTimeBy()` run it.
- Task ids: M1-63 to M1-65, M1-68, M1-69 belong to #315, #320, #321; M1-O13 is on `main`.

## Waiting on the owner
- none (M1-O14 decided: #15 comment 7085175461)
