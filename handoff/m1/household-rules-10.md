# Handoff: M1-10 household rules, PR #352 (branch m1/household-rules-10)

Delete in the PR's final commit; kept short because the 600-line guard counts it.

## Goal / done
PLAN 3.1 Create household + owner and Update own member doc (M1.md row 4, section 5). Red 2b05ac1; green 3beb4aa;
PLAN joinedAt and mutation notes 4045266; main merged; tasks.toml M1-10 done (pr 352), new task M1-83 (member reads)
b7cfa3e; verifier fixes in the commit after it. Draft PR #352, awaiting review round 1. Open findings: none.
Transfer is M1-53's (M1.md split, PR body).

## Facts that save time
- Fast loop, in firebase/: `npx firebase emulators:exec --only firestore --project demo-tally "npx jest --runInBand
  test/household.test.ts"`; not while `scripts/verify.sh` runs (port 8080).
- Shallow clone: `git fetch --unshallow origin main` first, or the Gradle gate self-tests run here.
- `test-results-gate-tests` can fail here on a Maven Central 429 (cold fixture build); rerun the step alone.

## Commands to resume
`scripts/install-hooks.sh`, then `scripts/verify.sh --fast`.
