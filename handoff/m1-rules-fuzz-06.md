# Handoff: M1-06, PR #372 before round 5 (branch m1/rules-fuzz-06)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-06 (P17, docs/milestones/M1.md row 7): rules fuzz against the TS model of PLAN 3.1. Escalation ruling FIX (comment
7132111440); orchestrator #43 (session_013srDQi3Uj4ui3DD2dLheiG) asked: merge main, update the PR body (round 4 row and the
ruling in the review table; Scope "keeps its codes" -> "keeps its invites"), run verify.sh, push, one-line WORKER-RESULT.
Round 5 (reviewer and second reviewer at max) starts on the push.

## Done
- Round 3 fixed (4cc3ea0..ced62a3); main with #382 merged and the Join batch modeled (751011f..60f97ab), PR body and
  WORKER-RESULTs 7131228901, 7132073844.
- Before round 5, at the context step boundary: a58b51b merges main b56ac33 (process files only); 6c0957f adds the mutant
  "Join: through another household's invite" (red: emulator, seed 1, 9000 cases); a09f2f4 adds join variants 7 to 10
  (another household's invite that dan, its owner, may delete; a tombstone keeping its name; dan already a member; his doc
  naming another code). Emulator on a09f2f4: fuzz.test.ts 41/41 (126 s); the new mutant 99, 2865, 528 (seeds 1-3, equal to
  the proxies); the unmutated rules agree with the model on seeds 1, 2, 3 for 9000 cases each (R4-01's check).
- Not done: the PR body, verify.sh on the new head, the WORKER-RESULT for this step.
- Session session_013srDQj8AHv6sByuzJoV48J (from this file): the verifier self-review found one major: join variant 10
  was denied by the member create too (no invite at CODE2), so the delete's `viaInvite == code` was never reached alone.
  ecca9e7 (red: emulator, seed 1, 9000 cases) adds the mutant `.data.viaInvite == code` -> `!= null`; the next commit
  makes v10 a valid join that also deletes CODE3, another of carol's invites, and v9 dan's doc set again unchanged (only
  the delete's !M(uid) denies; verifier nit). Emulator: new mutant 522, 1070, 581; burn 555, 109, 246 (seeds 1-3, equal
  to the proxies); the unmutated rules agree with the model on seeds 1-3 for 9000 cases each.
- Proxies on the fix (seeds 1-100; they reproduce the round 3 table and the join table exactly on the old generators):
  new mutant 99 / 100 / 3312 (0 before); burn worst 1022 (2439); the whole viaInvite term 1094 (1740); invite delete by
  any member before expiry worst 756 (979); users-doc set without membership 98 / 100 / 3148. Every other row as before.

## Next (in order)
0. Add to the PR body below: the verifier finding (self-review table, round 5 prep), the new mutant (twenty-four), the
   join table rows above, v9 and v10 as now; the round 3 table's two changed rows.
1. PR body (REST: `gh api -X PATCH repos/bondo/tally/pulls/372 -F body=@file`; read the live body first):
   - Review rounds table: row `| 4 (reviewer R4, second reviewer S4) | 0 | 1 | 0 | 0 | 0 | changes_requested |` (R4-01 =
     S4-01, one major) and the escalation ruling (7132111440: fix; R4-01 and S4-01 fixed by 751011f..a09f2f4; round 5 next).
     A round 4 findings table: R4-01 / S4-01 major, fixed by the merge-order work (751011f, 126c32e, 4b5b49e, 60f97ab, and
     6c0957f, a09f2f4 for R4-01's variant list).
   - Scope, fuzz.ts bullet: "so a renamed household keeps its codes" -> "keeps its invites"; add variants 7 to 10 to the
     join sentence; mutant count twenty-three (add "a join through another household's invite"); merge note: a58b51b.
   - Evidence: the "Round 3, after #382 merged" section: head, the commits above, the seed 1-3 agreement check, 41/41.
     Join table, now (100 seeds): another household's invite 97 / 100 / worst 4347 (mutant; 1 before), the joiner-only
     displayName 66 / 95 / none (one check with the owner's in createsMember: found there in 100), single use worst 2770,
     the joiner path's viaInvite worst 1740. Remove the claim that another household's invite is masked; LIVE stays masked
     (the invite delete and the users-doc set check it too). Older rows: one-household check worst 555; users-doc set
     without membership 99 / 100 / 3124. Every mutant still within 8672; the sample check passes on all 100 seeds; the
     comment above MUTANTS stays true (seed 1 within 2701, seeds 2 and 3 within 3363).
   - Size: recount with the guard's command (merge base b56ac33).
2. `scripts/verify.sh` (full). If `git rev-parse --is-shallow-repository` says true, first `git fetch --unshallow origin`:
   otherwise ci_scope runs the Gradle gate self-tests, whose Gradle build cannot fetch the pitest plugin in this container.
3. Delete this file, commit, foreign-commit check (§7.6 2(e)), plain push, WORKER-RESULT comment on #372, one-line
   send_message to orchestrator #43 with the new head.

## Decisions made
- The join keeps its share of the ninth draw weight (FORMER in fuzz.ts), so the other templates' draws and all earlier
  mutant numbers stay as measured (only P1, the one-household check and the users-doc set changed, all earlier or level).
- Accepted: a rename of H1 does not rewrite `viaInvite` (R4-01 allowed "accept that loss of reach").

## Open findings
- R4-01 major, fixed (a09f2f4 head), awaiting round 5. S4-01 major, same.

## Commands to resume
```
git fetch origin m1/rules-fuzz-06 && git checkout m1/rules-fuzz-06
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Several emulator test files at once: `jest --runInBand`, or they share one emulator and fail at random.
- The guard reads a string in firebase/test that opens with `"!` and a letter as a Jest pattern: start anchors at `&&`.
- Reach numbers come from a scratch model copy with one condition switched off (never committed), compared with model.ts
  on `fc.sample(cases)` for seeds 1-100; it has matched every emulator first find measured (all mutants, seeds 1-3).

## Waiting on the owner
- none
