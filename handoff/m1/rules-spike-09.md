# Handoff: M1-09 rules spike, PR #333 (branch m1/rules-spike-09); context hook at 60%
Delete in the PR's final commit. Size: 577 lines + this file; the 600 guard counts it, so keep it short.
## Goal / done
PLAN 3.1 items (a)-(e), ADR 0002 (M1.md section 5, M1-09). Rounds 1 and 2 fixed: R1-01..05, S1-01..02; R2-01, R2-02,
S2-01 in the last 3 commits (an (e) test pins let/argument charging, the ADR layout keeps calls out of lets).
## Next
1. Wait for R3/S3 (orchestrator #34, session_013srDQi1nnQZMFHNzUgY1cH); fix, verify, push, refresh the PR body table.
2. Final commit: delete this file. Owner merges #333.
## Decisions made
- Spike rules test-only (`firebase/test/spike.rules`); no split (PR body). S2-01 confirmed by scratch probes, not disputed.
## Facts that save time
- Emulator: `let` charged when its function runs, argument when called, used or not; unused errors ignored.
- Fast loop: emulator up, then `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npx jest --runInBand test/spike.test.ts` in
  firebase/; stop it before `scripts/verify.sh` (port 8080). Shallow clone: `git fetch --unshallow origin main` first.
## Commands to resume
`scripts/install-hooks.sh`, then `scripts/verify.sh --fast`. Waiting on the owner: merge of #333.
