# Handoff: M1-81 guards check 1, playwright and cypress options (branch tooling/guards-runner-81)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-81 (docs/tasks.toml): check 1 on command lines (`runopt` in scripts/guards.sh) reads playwright and cypress test-runner options,
direct and in a resolved npm `--` tail, for the option set the owner decides. Tripwire (F18); the rest in docs/guards-known-gaps.md.

## Done
- Step 1: draft PR opened, "Proposed option set for M1-81" posted as a PR comment. No code yet.

## Next (in order)
1. Wait for the owner's decision (relayed by the orchestrator as data from #15).
2. Failing tests first in scripts/hooks/test_guards_cli_flags.py (positive and negative cases), commit, push.
3. runopt: per-runner tables for playwright (`test` subcommand) and cypress (`run`), commander short-option grouping; tails resolved to them read with their own tables.
4. docs/guards-known-gaps.md section "Check 1 on command lines", status = "done" for M1-81 in docs/tasks.toml, delete this file.

## Decisions made
- none yet (option set is the owner's, task notes)

## Open findings
- none

## Commands to resume
```
git fetch origin tooling/guards-runner-81 && git checkout tooling/guards-runner-81
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- runopt and rscan: scripts/guards.sh around lines 480-560; tables RDL/RVL/RDS/RVS in the awk BEGIN block (~line 680).
- The playwright/cypress tail fallback today: `ds = ds RDS["jest"] RDS["mocha"]; mr = 1` in runopt.

## Waiting on the owner
- M1-81 option set (PR comment "Proposed option set for M1-81")
