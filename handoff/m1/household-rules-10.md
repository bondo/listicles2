# Handoff: M1-10 household rules, PR #352 (branch m1/household-rules-10)

Delete in the PR's final commit; kept short because the 600-line guard counts it.

## Goal / done
PLAN 3.1 Create household + owner and Update own member doc (M1.md row 4, section 5). Red 2b05ac1; green 3beb4aa;
PLAN joinedAt and mutation notes 4045266; main merged; tasks.toml M1-10 done (pr 352), new task M1-83 (member reads)
b7cfa3e; verifier fixes 87effdf. Round 1 (R1 changes_requested, S1 ready_nits_only): main merged 6b65eee; R1-01 and
S1-01 fixed in 5f4b8c1; R1-02/S1-02 (coverage) in the PR body; R1-03 label added by the orchestrator. Open: none;
round 2 next. Transfer is M1-53's (M1.md split, PR body).

## Facts that save time
- Fast loop, in firebase/: `npx firebase emulators:exec --only firestore --project demo-tally "npx jest --runInBand
  test/household.test.ts"`; not while `scripts/verify.sh` runs (port 8080).
- Shallow clone: `git fetch --unshallow origin main` first, or the Gradle gate self-tests run here.
- `test-results-gate-tests` can fail here on a Maven Central 429 (cold fixture build); rerun the step alone.

## Commands to resume
`scripts/install-hooks.sh`, then `scripts/verify.sh --fast`.
