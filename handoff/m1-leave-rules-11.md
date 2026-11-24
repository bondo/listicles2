# Handoff: M1-95, PR #390 (branch m1/leave-rules-11)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-95 (split from M1-11, R2-08): PLAN 3.1 Delete household rules (soft delete, no household delete, the owner's
tombstone cleanup, P6) with allow and deny tests. Orchestrator #44: session_013srDQiMaumvwrR37dMMLfe.

## Done
- Rules `e6a6fd8`; round 1 (R1, S1 on `74fa581`): main merged (`0b9141a`, #372 fuzz), S1-01/S1-02 tests and the
  fuzz exactly-once check (`43471e3`), then the fix commit: model.ts rows, fuzz.ts `tombstone` template (the old
  soft-delete slot), 4 mutants repaired and 2 added (R1-01), M1.md #242 row, "their" (R1-03; tasks.toml untouched).

## Next (in order)
1. If round 2 has findings: fix test-first, keep the diff under the 600-line guard (about 590 with this file).
2. Last commit before READY: delete this file.

## Facts that save time
- `fuzz.test.ts` runs about 5 minutes; the mutants need the emulator alone (one port, 8080).
- The Leave and Remove tests drafted for M1-11 are in PR #390 comment 7135306110.
