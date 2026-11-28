# Handoff: M1-98 isolated projects spike (branch m1/isolated-projects-98)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
M1-98 (docs/tasks.toml): try `org.gradle.unsafe.isolated-projects=true`, enable it only when the whole of `scripts/verify.sh`
passes, else record the blockers. Spike result: it cannot be enabled yet; gradle-pitest-plugin 1.19.0 is the one blocker (M1-121).

## Done
- b8a649c failing tests for build-guards check 5; 1bfdda7 check 5 + the gradle.properties line + docs row (the enabling commit);
  58399c8 reverts both (kept in history for the follow-up: `git cherry-pick b8a649c 1bfdda7`).
- be27f85 the four Gradle gate self-tests use gradle.lifecycle.beforeProject/afterProject (not allprojects/afterEvaluate), and the
  root Spotless targets are file trees (Spotless reads subproject layouts for a `**/` string). Both work with the mode on and off.
- Task notes: M1-98 stays todo, depends on the new M1-121 (replace the PIT plugin), M1-121 added to M1-FU.

## Next (in order)
1. Review rounds: fix findings above nit (REVIEW.md).
2. Keep M1-98 `todo`; report it under needs_owner in the WORKER-RESULT.

## Decisions made
- Replacing the PIT plugin is its own concern (M1-121), not this PR: size and the one-concern rule.
- No upstream issue filed for gradle-pitest-plugin (outward-facing); none exists as of 2026-11-28.

## Open findings
- none yet

## Commands to resume
```
git fetch origin m1/isolated-projects-98 && git checkout m1/isolated-projects-98
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- With the mode on, `--no-configuration-cache` is an error ("Configuration Cache cannot be disabled when Isolated Projects is enabled").
- The spike's full verify with the mode on: only coverage and mutation fail (`:core:domain:pitest` creation); koverVerify and
  koverXmlReport pass with PIT removed; assembleRelease (stand-in), connectedDebugAndroidTest --dry-run and the CodeQL build pass.

## Waiting on the owner
- none
