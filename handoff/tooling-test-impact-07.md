# Handoff: M1-07 test-impact summary (branch tooling/test-impact-07)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-07 / P19: report changed lines the unit tests do not execute, to the CI step summary and in verify.sh.

## Done
- 9cc49ff failing tests first (scripts/test_coverage_impact.py); 8502f56 scripts/coverage_impact.py, verify.sh and ci.yml (unit job) wiring, test_ci_scope CI_STEPS entry.

## Next (in order)
1. Open the draft PR, wait for CI (the real `koverXmlReport` path build/reports/kover/report.xml is untested locally: Gradle gets 429 from Maven here).
2. Verifier subagent on the diff, fix findings; set M1-07 status = "done" and pr = <number> in docs/tasks.toml; delete this file; WORKER-RESULT comment and send_message to the orchestrator.

## Decisions made
- Report only, exit 0 on uncovered lines (koverVerify stays the gate); exit 2 on missing/empty/invalid coverage data or an undiffable base.
- Diff base = merge-base(<ref>, HEAD) against the working tree plus untracked files; CI uses HEAD^1 (unit job checkout is fetch-depth 2).

## Facts that save time
- Local `origin/main` ref can be stale: `git fetch origin main` before comparing. The pre-push hook takes ~10 minutes here (hook tests).
