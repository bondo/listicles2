# Handoff: M1-68 part B3 / PR 359 (branch tooling/root-checks-68-b3)

Delete this file in the PR's final commit (squash merge keeps it off `main`).
Write it when the context hook reminds you (60% of a 1M window, 40% of a 200k one; hard stage 80% / 60%), commit it, and end the session. The next session starts from this file.

## Goal
Finish M1-68 (docs/tasks.toml): no build script reads or configures another project (see #48). Part B3 covers three things:
- checkJavaApiLevel runs per JVM library module from build-logic;
- checkWarningsAsErrors denies issue 48's flags;
- check 4 of scripts/check_build_guards.py fails on any allprojects/subprojects use.

## Done
- Tests first in 18b6797, then the implementation in f5212a3:
  - build-logic ModuleChecks.kt holds registerJavaApiLevelCheck and registerJavaApiLevelInputs.
  - The app hands its minSdk and the api-versions.xml path to the JVM modules over a consumable configuration (`listiclesJavaApiLevelElements`, Usage `listicles-java-api-level`).
  - The root task is gone.
- Self-review fixes in 479cd2a and 37be18c: detekt and listiclesChecks were added to GRADLE_PYTHON_TASKS. New task M1-84 holds the check 4 known gaps. It was renamed from M1-82 in 97dc44c, because M1-82 was taken. M1-68 is set to done and `pr = 359` is recorded (71b905c).
- Round 1 (findings comment 7105035482): R1-01, R1-02 and R1-03 are fixed. Tests first in 8b1f0c8, the fix in cef317f.
- origin/main is merged with merge commits 8694de3 and 7ecde93 (main at 1665bca). The only conflict was M1-FU depends_on, and both sides were kept.
- `scripts/verify.sh --fast` is green at 7ecde93: 70 ok, gate self-tests included. The full verify.sh was green at 37be18c.
- WORKER-RESULT comments are 7104932352 (initial) and 7108648508 (R1). The PR body has the review table up to R1.

## Next (in order)
1. A fresh reviewer re-checks the R1 fix commits (8b1f0c8, cef317f) and the merges (8694de3, 7ecde93). The orchestrator starts it.
2. Fix anything it finds, test-first, then run `scripts/verify.sh --fast` and push plainly.
3. Once CI is green: ready for review, then the approver (orchestrator §7.5). Refresh the PR body review table first.
4. Delete this handoff file in the final commit.

## Decisions made
- checkJavaApiLevel gets its inputs from :app through a project dependency and a consumable configuration, not from constants or an SDK lookup. This keeps minSdk and the platform from drifting from the app, and resolving the app's boot classpath makes AGP install a missing platform. Implementer's choice; the R1 reviewer accepted it.
- The separate checkJavaApiLevel step in verify.sh and ci.yml is kept, although detekt now runs the same check. It names the check in the output, and test_check_java_api_level.py pins it. This was a self-review nit, kept.
- The remaining check 4 gaps are task M1-84, not a deferral: rootProject.<member> reads, parent, gradle.rootProject { }, a project(...) held in a variable, and configure(listOf(project(...))).

## Open findings
- R1-01 minor: fixed in cef317f (scripts/check_build_guards.py:530).
- R1-02 nit: fixed in 8b1f0c8 (scripts/test_warnings_gate.py:53).
- R1-03 nit: fixed in cef317f (docs/tasks.toml, M1-68 notes).

## Commands to resume
```
git fetch origin tooling/root-checks-68-b3 && git checkout tooling/root-checks-68-b3
scripts/install-hooks.sh
scripts/verify.sh
```

## Facts that save time
- The gate self-tests and full verify.sh take about 60 min, and `--fast` about 35 min. Maven Central sometimes answers 429. Retry, it is not a test failure.
- docs/tasks.toml conflicts with main mostly in the M1-FU depends_on list. Keep both sides and run `scripts/tasks.py validate`.
- No GitHub MCP tools were attached in this session, so PR bodies and comments went through `gh api` REST with a JSON `--input` file.
- The owner is renaming the repository from bondo/listicles2 to bondo/tally (see #15).

## Waiting on the owner
- none
