# Handoff: #229 D4a split of #245 (branch tooling/merge-ready-general-229, A1 = kind general)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
Owner decision #15 comment 7017597600 (via orchestrator #19, session_013srDQgRZxzQ13LBEge7FEy): split #245 into two PRs, each under the 600-line guard, test-first:
- **A1** = kind `general` only (owner-only set incl. ci.yml-driven gate scripts, casefold, drafts, docs for general). NEW draft PR from this branch, cut from main (7440c98 at cut time).
- **A2** = owner-batch + `--wait` + merge check + batch docs, built on A1. Re-use #245 (head branch tooling/merge-ready-kinds-229a, head 80fef5a) as A2 and say so in its body.
- R1-02 (new rule for A2): a merge of main after the approved sha is accepted only if its tree equals `git merge-tree --write-tree <p1> <p2>` with no conflicts (local git in the merge agent's clean checkout, after fetching pull/N/head); otherwise refuse (a hand-resolved conflict needs a fresh owner approval). Negative tests: a moved line, a conflict resolution, an extra file. Replaces the compare-based patch check (`_changes`, `_compare_files`, `COMPARE_CAP`).
- The deviation from 7009274639 is ACCEPTED: no guards.sh change.

## State of the other PRs (do not touch unless the orchestrator sends findings)
- #237 (PR B, update-branch.sh): head 4b01394, R3 fixed, in its R4 review. Do not push to it.
- #245 head 80fef5a on the remote has everything (general + owner-batch + wait), R1 fixes except R1-02, mapping comment 7016654172. It is red only on the guards size check (644 lines).

## Done
- Nothing of A1/A2 written yet. This branch holds only this handoff file.
- Full final file versions of the current #245 tree are recoverable with `git show 80fef5a:<path>` for: scripts/merge_ready.py, scripts/test_merge_ready.py, scripts/prompt_rules.py, scripts/test_prompt_rules.py, docs/ORCHESTRATION.md, agents/prompts/orchestrator.md.

## Next (in order)
1. A1 on this branch (from main): red commit = general tests only (copy `GeneralKindTests`, `pretooluse_guard` import, the kinds list test -> `["dependabot","general","tasks-sync","working-draft-docs"]`, wiring test with KINDS + "standing authorization") + prompt_rules/test_prompt_rules pins for A1 wording; green commit = merge_ready.py (header line, imports functools/Path, OWNER_ONLY_* constants, `ci_scripts`, `owner_only`, `allowed` general branch, general draft clause in `file_problems`, KINDS) + docs. A1 docs: STANDING sentence (replaces the per-window sentence; keep "the owner authorizes it there before its first merge"), "a ready PR that is not owner-only is merged as kind `general` (D3, #15 7007421567)", OWNER_HANDS list, "the owner-only exception above means not under the standing authorization" (orchestrator.md line 99 only; NEVER edit orchestrator.md line 98, guards.sh flags 'guard thresholds'), merge order in its original form (bring owner-only PRs to the owner only once no general PR is ready; "(e.g. ...)"), recipes line "merges under the standing authorization on #15 (§7.5)". Diff must stay under 600 (guards.sh counts vs merge-base; CI enforces).
2. A1: verify.sh (about 25 min; run in background, wait with an until-loop), plain push (red+green in one push, say so), DRAFT PR via GitHub MCP tools, body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, no closing keywords, cite 7017597600, wait for CI, WORKER-RESULT to the orchestrator.
3. A2 = branch tooling/merge-ready-kinds-229a: first add R1-02 tests (red) and the merge-tree check (green) on top of 80fef5a; then plain-merge the A1 branch (`git merge -X ours` for conflicts in merge_ready.py / prompt_rules.py / docs: keep the 229a side, it is the superset; the tree must stay 229a's plus R1-02 changes); then `update_pull_request` base = the A1 branch name so #245's diff is A2 only (<600 lines); after A1 is squash-merged on main, merge origin/main into 229a and set the base back to main. A2 doc changes on top of A1: ORCH first line reword ("merges every READY PR that is not owner-only under the owner's standing authorization ... an owner-only PR only as kind `owner-batch`"), CLASSES owner-batch sentence, BATCH, APPROVAL_FORM, SAME_PATCH, ORDER_TAIL with "asks the owner for a batch approval", Strict bullet "--wait", Merge agent (issue 136) bullet; adapt prompt_rules constants accordingly. Refresh #245 body (say it is A2, built on A1) and post a mapping comment.
4. Held for the owner or orchestrator rulings: none left; owner decided everything on #245.

## Decisions made
- Parser (R1-01): first non-empty line must be `batch approval:` + only `#N@sha` entries and (notes); no performed_via_github_app check (owner 7014222068: keep chat approvals; docs say the check proves the account only).
- R1-05: every `scripts/` path in ci.yml is owner-only for general; unreadable ci.yml makes every scripts/ path owner-only.

## Commands to resume
```
git fetch origin && git switch tooling/merge-ready-general-229   # if pushed; else it is the local branch
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- Run scripts that mention protected paths from a file (the PreToolUse hook blocks inline code naming them), and commit before any `git checkout` (the hook blocks it with uncommitted changes).
- Measure size with `git diff --numstat $(git merge-base HEAD origin/main) HEAD`; guards.sh only sees committed HEAD.
- GitHub MCP tools come and go: ToolSearch `select:mcp__github__create_pull_request,mcp__github__add_issue_comment,mcp__github__update_pull_request` loads them again.
- Orchestrator #19 is session_013srDQgRZxzQ13LBEge7FEy (#15 comment 7010829679); #18 is inactive.

## Waiting on the owner
- Nothing for me; the owner's rulings are in #15 comment 7017597600.
