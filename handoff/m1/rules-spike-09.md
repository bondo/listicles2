# Handoff: M1-09 rules spike, PR #333 (branch m1/rules-spike-09)

Delete in the PR's final commit; kept short because the 600-line guard counts it.

## Goal / done
PLAN 3.1 items (a)-(e) in the emulator, ADR 0002 (M1.md section 5, M1-09). Red a449b8c, 61baa3a; green 1018160; ADR
24d0553; self-review fixes 819f0fc, bdac4a6; tasks.toml done (pr 333). Draft PR #333, awaiting review round 1. Open
findings: none. Decisions: spike rules test-only (`firebase/test/spike.rules`); no split (reasons in the PR body).

## Facts that save time
- Fast loop: start the emulator, then `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npx jest --runInBand test/spike.test.ts`
  in firebase/; stop it before `scripts/verify.sh` (port 8080).
- Shallow clone: `git fetch --unshallow origin main` first, or the Gradle gate self-tests run and fail here.

## Commands to resume
`scripts/install-hooks.sh`, then `scripts/verify.sh --fast`. Waiting on the owner: merge of #333.
