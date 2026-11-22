# Handoff: M1-14 auth data 1, domain sign-in and sign-out steps (branch m1/auth-data-14)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-14 (`docs/milestones/M1.md` section 5), narrowed by the split in `docs/tasks.toml` to the Google sign-in flow and
the OQ-13 sign-out steps in `core/domain`, with fakes in `core/testing`. PR #319 (draft).

## Done
- Failing tests 4cad1ac, implementation 1e1b785, `main` merged a0d649e, split ddb9f08, verifier fixes 8bfeceb,
  trim db6c3b2, data-layer task renumbered M1-65 to M1-67 (orchestrator #31).
- PR comments: licence list 7084644086 (owner task M1-O14), compiled never-run data-layer draft 7084644287 (M1-67).

## Next (in order)
1. Review rounds: fix findings above nit; `scripts/verify.sh --fast` before each push; diff guard 600 lines.
2. Final commit: delete this file (M1-14 is already `done` with `pr = 319`).

## Decisions made
- Split (implementer proposal, PR body): about 780 lines before the wiring, and the wiring needs M1-O14.
- Sign-out wait 5 s; steps 2-5 in an injected application scope; `unsentChangesSeen` from listeners only.

## Facts that save time
- `advanceUntilIdle()` stops at `backgroundScope` work; `runCurrent()` and `advanceTimeBy()` run it.
- Task ids (orchestrator #31): M1-63 to M1-65, M1-68 and M1-69 belong to #315, #320 and #321; M1-O13 is on `main`.

## Waiting on the owner
- M1-O14
