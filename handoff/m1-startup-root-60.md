# Handoff: M1-60 start-up root (branch m1/startup-root-60)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-60 (docs/milestones/M1.md rows 8b/8c, section 5.1; tasks.toml notes): Navigation 3 root, the M1 home (Q1 A, see #194),
signed-in/out routing, signed-out start shows sign-in. Split per the task's own rule (about 600 lines in full): this PR is
b1; the other P10 gates (see #195, Q2 A) and the routing test over all gates are the new task M1-62.

## Done
- Test commit first (StartRoutingTest, SignedOutStartTest, AppGraphTest session, ThemeTokensTest spacing/sizes,
  screenshot and androidTest moved to the stateless root), then the implementation.
- tasks.toml: M1-60 narrowed, M1-62 added (depends on M1-60); M1-17, M1-18, M1-27, M1-39, M1-48, M1-FU depend on M1-62.

## Next (in order)
1. Green `scripts/verify.sh --fast`; record goldens (`scripts/screenshots.sh record`, TallyApp_* now show the home).
2. Push, open the draft PR, verifier subagent, M1-60 status done in the final commit with this file's deletion.

## Decisions made
- Back stack derived from the gate state (`listOf(route)`), not saved, so keys are not `@Serializable` (checklist 3 row).
- Home top bar: title only; household icon with M1-19, avatar with M1-25 (no button that leads nowhere).
- `SessionState` (domain, Flow) with a signed-out stand-in binding (`SessionModule`) until M1-14.

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/startup-root-60 && git checkout m1/startup-root-60
scripts/install-hooks.sh
scripts/verify.sh --fast
```

## Facts that save time
- Pre-commit runs `:core:testing:detektMain` (type-resolved), so a test double must compile against main code.
- New dependencies: verification metadata via `--write-verification-metadata sha256` over the CI task list (checklist 11).
