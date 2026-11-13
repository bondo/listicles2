# Handoff: <milestone / PR> (branch <branch>)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it at about 50% context, commit it, and end the session. The next session starts from this file.

## Goal
<one or two sentences; link the milestone doc section>

## Done
- <what is finished and verified; commit hashes>

## Next (in order)
1. <next small step>

## Decisions made
- <decision, reason, who made it>

## Open findings
- <review finding ID, severity, status open|fixed|disputed|withdrawn, file:line>

## Commands to resume
```
git fetch origin <branch> && git checkout <branch>
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- <gotchas, environment quirks>

## Waiting on the owner
- <owner task id / issue number only; details live in the issue (docs/ORCHESTRATION.md §4.5). Never restate an owner to-do here>
