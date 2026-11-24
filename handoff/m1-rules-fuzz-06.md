# Handoff: M1-06, PR #372 round 3 fixes (branch m1/rules-fuzz-06)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Details and the measuring method: the PR #372 comment that starts with `handoff details (round 3)`.

## Goal
M1-06 (P17): rules fuzz against the TS model of PLAN 3.1 (docs/milestones/M1.md row 7). Fix round 3 (orchestrator #42,
session_013srDQgNwhR99NxPHHLri9f): R3 comment 7129407171, S3 comment 7129426619. Round 4 is the last before escalation.

## Done
- Rounds 0 to 2 pushed; head 9251302 (verify.sh 72 ok, emulator 821 tests ok). S2-02 fixed (invite rows, 4d30748).
- Round 3: findings read; no code change yet.

## Next (in order)
1. R3-03 / S3-03 (nit): move config/app's comment down to its row (model.ts ~174); invites comment "get, any signed-in user".
2. S3-01 (minor): a code pool for `other()` (valid CODE, 21- and 23-character secrets, a `.`, a 19-character prefix);
   failing mutant first: createsInvite `_-]{22}` -> `_-]{21,23}` (never `$'` in a replacement); emulator seeds 1 to 3.
3. R3-01 / S3-02 (minor): vary the invite templates by n (create expiresAt; delete caller and stored expiresAt; reads with
   alice's own query and an owner without a member doc), caller and read indexes coprime. Re-measure 100 seeds.
4. R3-02 (minor): PR body Scope, merge order with #382 (see the comment). Do not take #382's rules here.
5. verify.sh, emulator suite, push, PR body (round 3 table), WORKER-RESULT on #372, send_message to orchestrator #42.

## Decisions made
- big-pr label: orchestrator #42/#41 (note 7128289161 on #373). M1-90: owner decision 7125484823, recorded in tasks.toml.

## Open findings
- R3-01 minor open, R3-02 minor open, R3-03 nit open, S3-01 minor open, S3-02 minor open, S3-03 nit open.

## Commands to resume
```
git fetch origin m1/rules-fuzz-06 && git checkout m1/rules-fuzz-06
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Mutant cap 3 * RUNS = 9000; keep every mutant's worst first find over seeds 1 to 100 under it.
- A second emulator on other ports: firebase.json copy with ports 8181/4401/4501/9151, `--config`.

## Waiting on the owner
- none
