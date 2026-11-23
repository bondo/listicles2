# Handoff: M1-83 member reads (branch m1/household-reads-83)

Delete in the PR's final commit; kept short because the 600-line guard counts it.

## Goal / done
PLAN 3.1 Reads for the household doc and its members (docs/tasks.toml M1-83; ADR 0002 layout). Red 5d82bd7 (6 allow
tests denied); green caf2094 (`readsHousehold` joins M1-08's tombstone read; member get = own path or `readsMembers`;
member list = `readsMembers`); verifier nits 608ba61 (header nit declined, PR body). Draft PR #366 (label
area:security-rules); tasks.toml M1-83 done (pr 366) in the commit that adds this file. Awaiting review round 1.
Open findings: none.

## Next (in order)
1. Review rounds: fix every finding above nit, minors of about 30 lines or fewer; reply per REVIEW.md.
2. If `main` moves (M1-53 edits the same rules file), merge it in with a merge commit; keep this PR to the read rules.
3. Final commit: delete this file.

## Facts that save time
- Fast loop, in firebase/: `npx firebase emulators:exec --only firestore --project demo-tally "jest --runInBand
  test/household-reads.test.ts test/base.test.ts"` (about 10 s); the whole suite is `npm test` (about 1 min).
- Scratch mutation pass (never committed): 19 mutants of the new conditions, 18 killed; the survivor
  `deleted != true` for `deleted == false` in `readsMembers` is equivalent while `deleted` is a boolean (PR body).
- Under a tombstone only the M1-08 tombstone read reaches the household doc in any state the rules can produce (a member
  doc there means householdId points at it), so the LIVE check of the member path is isolated by a seeded state only.

## Commands to resume
```
git fetch origin m1/household-reads-83 && git checkout m1/household-reads-83
scripts/install-hooks.sh
scripts/verify.sh --fast
```

## Waiting on the owner
- none
