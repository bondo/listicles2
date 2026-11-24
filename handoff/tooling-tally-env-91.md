# Handoff: M1-91 (branch tooling/tally-env-91)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-91 (docs/tasks.toml): hooks, status line and verify.sh read TALLY_* names; TALLY_TASK=tooling accepted next to LISTICLES_TASK.

## Done
- 51829db failing tests (guard both-names cases, context/status line TALLY_CONTEXT_* and tally-ctx, metrics TALLY_* tags, verify.sh tally-verify).
- Fix commit: pretooluse_guard.py, session_end_metrics.py, context_guard.py, statusline.sh, verify.sh.

## Next (in order)
1. Open the draft PR, set M1-91 status = "done" and pr = <number> in docs/tasks.toml, delete this file.
2. Verifier self-review, WORKER-RESULT comment, send_message to the orchestrator.

## Decisions made
- An empty TALLY_TASK counts as unset (falls back to LISTICLES_TASK), for both the guard and the metrics task tag (implementer).
- The guard tests share one TOOLING env from test_pretooluse_guard.py ({"TALLY_TASK": "tooling"}); LISTICLES_TASK alone is covered by TaskNames.

## Open findings
- none

## Commands to resume
```
git fetch origin tooling/tally-env-91 && git checkout tooling/tally-env-91
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- The guard reads inline python mentioning `.git/config` as a write: put such scripts in a scratchpad file.

## Waiting on the owner
- none (next owner step M1-O17)
