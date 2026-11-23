# Handoff: M1-78, PR #360 (branch tooling/state-rotation-78)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-78 (docs/tasks.toml): state issue rotation. merge_ready.py --approval accepts the current or the previous state issue and nothing else;
state_body.py validate reports when the rotation limits (250 comments, 15000-byte body) are passed. Owner decisions 7076085601 item 3 and 7076313976.

## Done
- 42bae6c failing tests; cebb827 implementation (STATE_ISSUE / PREVIOUS_STATE_ISSUE pointer, exact issue_url match, bad pointer refuses;
  `validate --comments N` rotate: lines; ORCHESTRATION 7.5 wording; M1-78 done, M1-79 notes extended).
- 433d36a / cd6d27e self-review fixes: CRLF body counted in bytes, per-reason refusals on both issues, docstring.
- verify.sh green on cd6d27e; draft PR #360 opened, no review round yet.

## Next (in order)
1. Review rounds: fix findings above nit (REVIEW.md); refresh the PR body review table.
2. Final commit: delete this file.

## Decisions made
- Pointer as constants in merge_ready.py (owner-only file), moved by an owner-merged PR at rotation; fail closed until it lands (implementer, PR body).
- Veto and 7085221356 prose checks, and the §3/§5 rotation steps, left to M1-79 (its notes say so).

## Open findings
- none

## Commands to resume
```
git fetch origin tooling/state-rotation-78 && git checkout tooling/state-rotation-78
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- The clone is shallow: coverage-impact fails on merge-base until `git fetch --deepen=100 origin main`.
- warnings-gate-tests can fail here when the Gradle plugin portal is unreachable (environment, not the diff).
- No GitHub MCP server in this environment: PR created with `gh api` REST, body from a file.

## Waiting on the owner
- Owner merge of #360 (scripts/merge_ready.py, docs/ORCHESTRATION.md).
