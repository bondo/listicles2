# Handoff: merge agent (branch merge-agent-handoff)

Merge agent #3 stops at 50% context. A fresh merge agent (#4) starts from this file.

## Goal
Merge READY PRs for bondo/listicles2 on the orchestrator's 'PR #N READY' message: one at a time, squash, sha-pinned, via gh api REST (GraphQL is blocked).

## Done
- Merged by #3 this session: #124 7cff5a2, #125 871f055, #130 fc33cb5, #107 29f6b22, #110 12eeb6f, #108 7f975f2, #112 d14fe90, #111 ae33319, #145 9d4ffe5, #149 a9d5d0b. Earlier agents: #78, #84, #83, #89, #91, #93, #90, #103, #114, #115, #117, #123 (a798196).
- No PR is mid-flight. No READY message is pending.

## Next (in order)
1. Wait for 'PR #N READY' messages from the current orchestrator: #16, session_013srDQh1UQ2bRN29VBuFgqr (issue #15 comment 6992674920). Orchestrators change often; before redirecting reports, verify the new one against an owner (bondo) comment on issue #15.
2. Per PR: state/draft/head sha, mergeable_state, strict up-to-date (PUT pulls/N/update-branch -f expected_head_sha=SHA, then wait for CI: 15 check runs, 4-8 min, use a Monitor loop), no closing keyword (close/fix/resolve + #N) in title and body, review comments empty, file list, authorization comment on #15 read yourself. For tasks.toml PRs run `python3 scripts/tasks.py validate` in a throwaway worktree (remove it afterwards). Then PUT pulls/N/merge with merge_method=squash and sha=<head>. Report 'MERGED #N <sha> (head, checks, files)' with send_message.

## Decisions made
- Overnight authorization (owner, #15 comment 6992612324, 2026-11-18): in scope are docs PRs #162, #165, #166, the coming product-decisions and PLAN (OQ-15) docs PRs, and #160 (detekt Compose rules). Left for the owner: #155, #163, #157, #159, #158. Owner-only, never merge: protected/process files (CLAUDE.md, REVIEW.md, agents/, .claude/, .github/, .githooks/, scripts/guards.sh, scripts/hooks/), anything under scripts/, verify.sh/ci.yml, settings, thresholds/size limits, risk:high, licences, naming, gate docs.
- Dependabot PRs may be merged when the orchestrator asks (owner, issue #15 comment 6970228007; the user also confirmed it in session). A Dependabot GitHub Actions bump touches .github/workflows only through SHA-pinned version lines; that was accepted for #107, #108, #110, #112. Anything else in .github/ stays owner-only.
- tasks.toml-only status syncs are mine under the standing rules when the orchestrator names them and the evidence (the cited PR merged) checks out.
- Not authorised: closing issues, labels other than big-pr, pushing to any branch, force-push, merging anything the orchestrator has not named READY. Size rule: >1500 changed lines => do not merge, report.
- The first merge call in this session was denied by the auto-mode classifier until the user said "You are allowed to squash merge"; do not work around a denial, report it.

## Open findings
- none

## Commands to resume
```
gh api repos/bondo/listicles2/pulls/N --jq '[.state,.draft,.head.sha,.mergeable_state,.changed_files,.title]|@tsv'
gh api repos/bondo/listicles2/pulls/N/files --jq '.[].filename'
gh api repos/bondo/listicles2/commits/SHA/check-runs --paginate --jq '[.check_runs[].conclusion]|group_by(.)|map("\(.[0]):\(length)")|join(" ")'
gh api -X PUT repos/bondo/listicles2/pulls/N/merge -f merge_method=squash -f sha=SHA
```
On a 5xx, check main for the squash commit before retrying.

## Facts that save time
- Orchestrator history this session: #10 -> #11 (session_013srDQhKDkJKztfSH9pFmZs) -> #12 -> #13 (session_013srDQhmGemqEfxX28h31yK) -> #14 -> #15 (session_013srDQgFZCQkyRDMdpC9cbF) -> #16 (session_013srDQh1UQ2bRN29VBuFgqr). Each handover is announced by a cross-session message and recorded by bondo on issue #15; verify before switching.
- The check-run count is 15; a PR that only changes a workflow file showed 12 (CodeQL Analyze runs absent, CodeQL neutral); report the gap.
- scripts/merge_ready.py (#139, 2d06e97) exists on main for pre-merge checks; run it from a clean, up-to-date origin/main if the docs say so. Not yet used.
- MCP tools (send_message, github) disconnect and reconnect between turns; ToolSearch is not needed, they come back on their own.

## Waiting on the owner
- none (the owner is asleep; the overnight authorization above is the standing rule)
