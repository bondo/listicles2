# Handoff: merge agent (branch merge-agent-handoff)

Context reached ~53%; this agent stops. A fresh merge agent session starts from this file.

## Goal
Merge READY PRs for bondo/listicles2 on the orchestrator's 'PR #N READY' message: one at a time, squash, sha-pinned, via gh api REST.

## Done
- Merged: #78, #84, #83, #89, #91, #93, #90, #103, #114, #115, #117. #85 landed on main as cb3d98e but its PR record is stuck open (orchestrator handles).

## Next (in order)
1. Wait for 'PR #113 READY' (docs wireframes; XSS fix in progress). It needs update-branch (expected_head_sha), CI wait, re-verify.
2. Later PRs only when the orchestrator names them.

## Decisions made
- Standing owner rules on issue #15: M0.5 merges allowed; docs PRs whose owner approval can wait (status line 'not owner-approved') are mine (comment of 2026-11-17).
- Owner-only, never merge: protected/process files (CLAUDE.md, REVIEW.md, agents/, .claude/, .github/, .githooks/, scripts/guards.sh, scripts/hooks/), guard thresholds, settings/permissions, risk:high, branch protection, licences, naming, gate docs, #86, #102.
- Not authorised: closing issues (#27, #28 left open), labels other than big-pr.
- Size rule: >1500 changed lines => do not merge, report (lockfile question for #96 was resolved by the owner merging it).

## Open findings
- none

## Commands to resume
Pre-merge checks per PR: state/draft/head sha/mergeable_state/size, no closing keyword in title+body, all check runs success, ccr/review_threads empty, no protected paths; then PUT pulls/N/merge with merge_method=squash and sha=<head>. On 5xx check main for the squash commit before retrying.

## Facts that save time
- Orchestrator is session_013srDQhQCtekWs8z37ix8an (#10); report results with send_message to it.

## Waiting on the owner
- none
