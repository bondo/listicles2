# Handoff: #229 D4a split of #245 (branch tooling/merge-ready-general-229, A1 = PR #248, kind general)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
Owner decision #15 comment 7017597600: `scripts/merge_ready.py` kind `general` is PR #248 (A1, from main); owner-batch, `--wait` and the merge-tree check are A2 = PR #245 (branch tooling/merge-ready-kinds-229a, built on A1). Orchestrator: session_013srDQhZuYQs2ZjmM8JSVFd (#15 comment 7060408900); send results there.

## Done
- #248 head 97160c7 (this branch before the handoff commit): kind `general` is FAIL-CLOSED (owner decision #15 7058755858): only an allowlist merges (Kotlin under `dev/listicles` or `dk/bjarkebjarke/tally` in app/core modules, app res, non-owner-only docs, README, docs/tasks.toml only for status/pr todo->done of agent tasks). Rounds R2..R10 fixed test-first (red then green each time); mapping comments on #248 (latest 7064939637); PR body current (Deferred section lists #273-#276).
- verify.sh passed and CI 15/15 green at 97160c7. `mergeable_state` is `behind` (main moves often): the merge agent runs update-branch.sh before merging; a plain merge of origin/main into this branch is fine if asked.
- #245 head 1d6ce3c (A2): has R1-02 (git merge-tree check), A1 R2/R3/R4-01 carried in, CI green; base = the A1 branch.

## Next (in order)
1. #248: nothing left but the owner's approval (orchestrator asks). If main must be merged again: `git merge origin/main`, run the tests, verify.sh, plain push.
2. #245 carry (ONLY when the orchestrator says go): from tooling/merge-ready-kinds-229a run `git merge origin/tooling/merge-ready-general-229`; conflicts come up in docs/ORCHESTRATION.md, agents/prompts/orchestrator.md (line 99/108 only), scripts/merge_ready.py, scripts/test_merge_ready.py, scripts/prompt_rules.py. Resolve by hand: keep A2's owner-batch/`--wait` wording and code, take A1's allowlist code (`GENERAL_ALLOW`, `owner_only`, `res_xml_problems`, `tasks_problems`, `_NoDoctype`), drop A1's interim sentence ("until kind `owner-batch` exists ..."), and keep the test line containing the word threshold byte-identical to A1's (guards.sh flags removed lines with that word; check with `GUARD_BASE=origin/tooling/merge-ready-general-229 CI=true scripts/guards.sh`). Size: A2 vs the A1 branch must stay under 600 lines (was 585 before the allowlist work; recheck with `git diff --numstat origin/tooling/merge-ready-general-229 HEAD`). After #248 is squash-merged: merge origin/main into 229a and set the #245 base to main (`gh api -X PATCH repos/bondo/listicles2/pulls/245 -f base=main`).
3. A2 doc work still to check after the carry: ORCHESTRATION first-line reword, the allowlist sentences must name owner-batch correctly (owner-only PRs are merged as kind `owner-batch`; the A1 text says they are merged by hand), prompt_rules pins.

## Decisions made
- `general` allowlist, not blocklist (owner, #15 7058755858, reverses ruling 1 of 7019683156). Kotest/lint/res-xml/tasks.toml rules: owner decisions 7059534826, 7062026912, 7062956773 and the orchestrator-relayed round 10 decision ("fix, then approve").
- Deferred with follow-up issues (labels follow-up, severity, target:M1): #273 goldens, #274 gate list by name, #275 tasks-sync has no tasks.toml check, #276 ORCHESTRATION 4.4 owner-task row. Also for a later follow-up: drop `dev/listicles` from `ROOT` once M1-29 is merged.

## Open findings
- none open on #248 (R7-05, R7-08, R8-02, R8-03 deferred: #273-#276).

## Commands to resume
```
git fetch origin && git switch tooling/merge-ready-general-229    # A1; for A2: tooling/merge-ready-kinds-229a
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- LISTICLES_TASK=tooling must be set (it was). GitHub MCP tools are retired: use `gh api` REST (PATCH pulls/N with -F body=@file, issues/N/comments, commits/<sha>/check-runs); GraphQL and `gh pr` fail.
- Python lint line limit is 160 (ruff E501); wrapping a string can push the overflow to the next line, so run `./scripts/lint_python.sh` before committing. Run scripts that mention protected paths from a file.
- Do not `pkill -f scripts/verify.sh` (it also kills a background command whose text contains that name). Pre-push runs the hook tests and takes up to ~10 minutes while verify.sh runs; start both in the background and wait with an until-loop.
- Foreign-commit check before each push: `git log origin/main..HEAD --format="%ae %ce" | sort | uniq -c` must show only noreply@anthropic.com.
- Measure size with `git diff --numstat $(git merge-base HEAD origin/main) HEAD`; guards counts against the PR base (the A1 branch for #245).

## Waiting on the owner
- Approval of #248 (process files) and later #245; no owner to-do is restated here.
