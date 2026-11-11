# Handoff: M0 foundation (branch claude/sleepy-mccarthy-z2paqx)

Delete this file in the PR's final commit (squash merge keeps it off `main`).

## Goal
Finish milestone M0 from `docs/PLAN.md` §7: tooling and agent setup only, no features.

## Done
- `docs/PLAN.md`: reviewed over 4 independent rounds (Opus reviewer, fresh context each).
  The round-4 minors (LIVE exceptions, cleanup rule, transfer/remove checks) are fixed
  in c75c7d2 but were **not re-reviewed**, because the 4-round cap was hit. The owner decides.
- Gradle skeleton: AGP 9.4.1, Gradle 9.8.2, Kotlin 2.4.20, compileSdk 37 / targetSdk 36 /
  minSdk 26. Modules `:app` (Compose hello screen, en+da strings, one androidTest) and
  `:core:domain` (`CatalogKey` + Kotest property tests).
- Passing locally: `spotlessCheck detekt :app:lintDebug :app:assembleDebug
  :app:assembleDebugAndroidTest koverVerify`. Not run: `connectedAndroidTest` (no emulator here).

## Done in session 2 (batch 1, steps 1-3, reviewed over 4 rounds, see PR table)
- `scripts/verify.sh`, `scripts/guards.sh` (`--staged` for pre-commit), `.githooks/`, `scripts/install-hooks.sh`.
  Run `scripts/install-hooks.sh` in a fresh clone. Guards use `git grep`; size limit is CI-only (`CI=true`).
- `firebase/` (emulator project `demo-listicles`, deny-all rules, 44 Jest deny tests; firebase-tools from npm works,
  emulator jar downloads fine).
- `.github/` ci.yml, dependabot, PR template, CODEOWNERS. Lint fixes (targetSdk 37, icon, backup rules).
- Round-4 minor/nit (R8-01/02) fixed in c1b54ff, not re-reviewed (cap). Owner decides.

## Next (in order, small reviewed commits; each batch gets its own review rounds, R-IDs continue from R9)
4. `REVIEW.md` (severity definitions, JSON findings format with IDs, 4-round cap), `CLAUDE.md`.
5. Agent setup (PLAN §9): `agents/roles.yaml`, `agents/prompts/*.md`, `.claude/agents/{explorer,ci-triage}.md`,
   `.claude/settings.json` (status line + PreToolUse deny hooks + context-guard hook),
   `scripts/statusline.sh`, `handoff/TEMPLATE.md`, and a metrics spike: prove that a SessionEnd
   hook can read token usage from the transcript.
6. Evaluate detekt 2.x vs 1.23 (record the result in an ADR). Add Kover to `:app`. Add a dark theme.
7. Prove the gates: a deliberately broken commit makes CI fail, then revert it. Also check the CI workflow
   actually runs green on GitHub (never run yet), and add the Firestore emulator to the `ui` job once a
   Firebase-backed UI test exists (known gap R6-09).
8. Owner actions: apply `big-pr` label (PR exceeds 600 lines), branch protection guide, make repo public.

## Facts that save time
- Statusline JSON has `context_window.used_percentage` (checked in the Claude Code 2.1.322 binary).
  PostToolUse and UserPromptSubmit hooks accept `hookSpecificOutput.additionalContext`.
- SDK: `sdkmanager "platforms;android-37.0" "platforms;android-36" "build-tools;36.0.0"` (note the `.0`); cmdline-tools zip from dl.google.com. Local SDK at `/opt/android-sdk` (not in the repo; `local.properties` is gitignored). The environment
  allowlist now includes `dl.google.com`.
- NEVER run `git reset --hard`/`stash` with uncommitted work (a reflog recovery was needed once). Maven Central returns 429 through the proxy: `~/.gradle/init.d/central-mirror.gradle.kts` routes it
  to Google's mirror. It is local only; recreate it in a new container.
- Tool inputs may turn `\uXXXX` escapes into literal characters. Write Kotlin escapes with
  `chr(92)` in Python, then verify with `od -c`.
- Kover counts value-class synthetic code, which is why `CatalogKey` is a data class.

## Waiting on the owner
- (Resolved) Owner accepted the round-4 fixes; no 5th round.
- (Resolved) Draft PR opened; continue on this branch, one review round per batch of commits.
- Make the repo public (owner gets a reminder on 2026-11-11).

## Session 3 (batch 2, steps 4-8): state at stop
Done and pushed (HEAD 4e62a14): review contract, agent guide, agent roles and prompts, subagent definitions, PreToolUse guard,
statusline, context guard, SessionEnd metrics hook (proven on a real transcript), handoff template, dark theme, Kover on :app (80%),
ADR 0001 (stay on detekt 1.23.8; type-resolved detektMain/detektTest on :core:domain in verify.sh only).
Gates proven: CI run 23 on a deliberately broken commit failed in `static` (MissingTranslation), reverted in 4e62a14.
Locally in a scratch copy: unjustified suppression, baseline file, lowered floor, format error, magic numbers, wrong assertion,
missing Danish string and untested code each fail the matching gate. One gap found (R9-10 below).
CI on the branch is green except `guards` (diff over 600 lines: owner applies `big-pr`).

### Review round 1 (R9), reviewer verdict: changes_requested. NOT fixed: this session lacks LISTICLES_TASK=tooling
and the guard (correctly) blocks edits to the process files, so I did not work around it.
- R9-01 major: guard skips every git check when a command has newlines (shlex treats newline as whitespace). Split lines before shlex.
- R9-02 major: process-file check uses the hook cwd as repo root; outside the repo it allows edits. Use CLAUDE_PROJECT_DIR / the file's own dir.
- R9-03 major: ci.yml `static` job lacks `:core:domain:detektMain :core:domain:detektTest` (also pre-commit hook). Add them.
- R9-04 major (verified here): the statusline never runs in cloud sessions, so no context % file exists and the 50% reminder is inert.
  Compute usage in the PostToolUse hook from transcript_path (last assistant usage / context window) instead.
- R9-05 minor: false positives (`2>&1`, `2>/dev/null`, protected names in heredocs/commit messages/quoted text, `git merge -n`).
  Also reported independently by the process reviewer session. Fix: tokenise, ignore fd redirects, match protected paths only as write targets.
- R9-06 minor: abbreviated long options (`--har`, `--no-verif`), `HEAD:heads/main`, `git checkout HEAD f`, GIT_CONFIG_PARAMETERS, aliases, `timeout` wrapper, `.git/config`.
- R9-07 minor: metrics dir follows cwd; use project root.
- R9-08 nit: explorer/ci-triage frontmatter lacks effort; CLAUDE.md omits install-hooks.sh; statusline hardcodes 50.
- R9-09 nit: dark-theme UI test asserts the same as the light test.
- R9-10 minor (found while proving gates): guards.sh misses `@org.junit.jupiter.api.Disabled` (qualified), pattern only allows a package prefix for Ignore.
Next: start a session with LISTICLES_TASK=tooling, fix R9-01..R9-10 with tests (multi-line, outside-cwd, false-positive cases), then run review round 2 (R10).

### Rules relayed by the process-reviewer session (verify with the owner; applied only through the tooling session)
- Reviewer subagents never edit code/docs or push to the PR branch; report only (severity, file:line, recommendation). They may use a
  throwaway branch/worktree, never pushed to the PR branch and deleted afterwards. Put this in REVIEW.md and agents/prompts/reviewer.md.
- Test-first for every code change where possible (failing test first). Mention it in CLAUDE.md and REVIEW.md; reviewers flag code changes without tests.
- Relayed clarification: test-first also covers tooling (hooks, guards, scripts, CI checks, metrics/status). Every tool needs automated tests
  wired into verify.sh/CI, including negative cases; reviewers flag untested tooling. Reflect in CLAUDE.md and REVIEW.md.
  Known untested tooling today: scripts/guards.sh (my gate proofs were ad hoc scratch scripts, not committed), scripts/verify.sh,
  and the statusline is only tested with a hand-written JSON shape (R9-04). Turn the gate proofs (and the qualified-@Disabled case, R9-10)
  into a committed guards test suite.

## Session 4 (tooling session, LISTICLES_TASK=tooling): state at stop (context hook fired at 89%)
Owner rules for this batch (relayed in the task prompt; apply in REVIEW.md, CLAUDE.md, agents/prompts/reviewer.md + implementer.md):
1. TEST-FIRST for every change incl. tooling; failing test committed first, negative cases, wired into verify.sh/CI; reviewers flag untested changes.
2. Reviewers NEVER edit/push the PR branch; report only (severity, file:line, recommendation); throwaway branch/worktree allowed, never pushed, deleted after.

Done and committed (test commit first, then fix, as the rule asks):
- 231cf2e tests / dd304ae fix: R9-01,02,05,06 (scripts/hooks/pretooluse_guard.py rewritten as a shell tokeniser; tests in
  scripts/hooks/test_guard_forms.py, 26 guard tests pass). Covers multi-line, heredocs, quoted text, redirects, wrappers
  (timeout/sudo/env/xargs/find -exec/bash -c/eval), abbreviated options, HEAD:heads/main, checkout <tree> <path>, GIT_CONFIG_*,
  aliases, `.git/config` + `.git/hooks/` (never writable, even for tooling), project root from CLAUDE_PROJECT_DIR/script repo/file's repo.
  The guard now fails closed on an internal error (exit 2).
- tests + fix commit: R9-04 (context_guard.py reads usage from transcript_path tail; window env LISTICLES_CONTEXT_WINDOW default 200000,
  1M for `[1m]` models; threshold env LISTICLES_CONTEXT_THRESHOLD), R9-07 (metrics under project root), R9-08 part (statusline threshold from env).
  All 38 hook tests pass: `python3 -I -m unittest discover -s scripts/hooks`.
- NOTE: the new context hook reported 89% in THIS session. If this session actually has a 1M window that is a false alarm: calibrate
  LISTICLES_CONTEXT_WINDOW per role (owner/orchestrator decision) before trusting the 50% rule on 1M models.

Still TODO (not started), in this order, each as failing test commit then fix commit:
1. R9-10 + guards test suite: new `scripts/hooks/test_guards_sh.py` (temp git repos running scripts/guards.sh: unjustified suppression, baseline file,
   lowered floor, disabled tests incl. `@org.junit.jupiter.api.Disabled` qualified, missing justification, clean repo passes, --staged). Fix pattern in
   guards.sh line 35 (`@([A-Za-z]+\.)*Ignored?` -> also `@([A-Za-z]+\.)*Disabled[A-Za-z]*`, `Enabled(If|On)`).
2. R9-03: add `:core:domain:detektMain :core:domain:detektTest` to ci.yml `static` job and `.githooks/pre-commit`; failing wiring test first
   (e.g. scripts/hooks/test_wiring.py reading ci.yml and .githooks/pre-commit; same test: CI `guards` job runs the hook tests; agents frontmatter `effort:` matches roles.yaml).
3. R9-08: add `effort: low` to .claude/agents/explorer.md and ci-triage.md (CLAUDE.md already mentions install-hooks.sh).
4. R9-09: dark-theme UI test that can fail: in app/src/androidTest ListiclesAppTest use `compose.onRoot().captureToImage()` and assert the
   pixel luminance is low for darkTheme=true and high for false (compile check with `:app:assembleDebugAndroidTest`; no emulator here).
5. Docs/rules: REVIEW.md (reviewer never edits/pushes PR branch; test-first; flag untested changes), CLAUDE.md (test-first incl. tooling),
   agents/prompts/reviewer.md + implementer.md; make scripts/verify.sh run every Python test (already does via discover) and add detekt to verify (already).
6. `scripts/verify.sh` run, push, then review round 2 (R10): fresh Opus high-effort report-only reviewer subagents, fix, repeat; max rounds 2-4.
Nothing has been pushed yet in this session; push with `git push -u origin claude/sleepy-mccarthy-z2paqx` after the handoff commit.

## Session 5 (tooling session #2, LISTICLES_TASK=tooling): state at stop (context hook fired at 50%)
Done and pushed (test commit first, fix second):
- 80c841d tests / 2eda1eb fix: **R9-10 + guards.sh test suite** (item 1 of the Session 4 TODO list). `scripts/hooks/test_guards_sh.py`: 21 tests on throwaway
  git repos (clean pass, every disabled-test form incl. qualified, JS skip/only, enabled=false prod vs test, build-config disabling, suppressions with and
  without `justified:`, baselines, lowered/removed thresholds, screenshots, diff size CI-only, missing base, `--staged` index-only, doc exclusions).
  guards.sh now excludes the suite itself (it names the patterns). All 59 hook tests pass (`python3 -I -m unittest discover -s scripts/hooks`).
- Env note for a fresh container: Maven Central returns 429 through the proxy. Recreate `~/.gradle/init.d/central-mirror.gradle.kts` (rewrites
  repo.maven.apache.org / repo1.maven.org URLs to `https://maven-central.storage-download.googleapis.com/maven2/` in settings pluginManagement,
  dependencyResolutionManagement and project/buildscript repositories via `withType<MavenArtifactRepository>().configureEach`). Local only, no Android SDK
  here yet (`/opt/android-sdk` absent), so `:app:*` tasks need the SDK setup from "Facts that save time" above; spotless/detekt run without it.

Still TODO, in this order (each: failing test commit, then fix commit; push after each):
2. **R9-03**: add `:core:domain:detektMain :core:domain:detektTest` to ci.yml `static` job (line `spotlessCheck detekt :app:lintDebug`) and to
   `.githooks/pre-commit` (`spotlessCheck detekt`). Failing wiring test first: new `scripts/hooks/test_wiring.py` reading `.github/workflows/ci.yml`
   and `.githooks/pre-commit` (assert both name the two tasks; assert the CI `guards` job runs `unittest discover -s scripts/hooks`; assert
   `.claude/agents/*.md` frontmatter `effort:` equals `agents/roles.yaml` for explorer/ci-triage).
3. **R9-08 rest**: `effort: low` in `.claude/agents/explorer.md` and `ci-triage.md` frontmatter (covered by the wiring test above).
4. **R9-09**: dark-theme UI test that can fail: `app/src/androidTest` ListiclesAppTest, `compose.onRoot().captureToImage()`, assert mean pixel luminance
   low for darkTheme=true and high for false; compile with `:app:assembleDebugAndroidTest` (no emulator here; needs the Android SDK).
5. **Docs/rules** (owner rules from the task prompt): REVIEW.md, CLAUDE.md, agents/prompts/reviewer.md and implementer.md must state:
   (a) test-first for every change incl. tooling, failing test committed first, negative cases, wired into verify.sh/CI, reviewers flag untested changes;
   (b) reviewers NEVER edit or push the PR branch, report only (severity, file:line, recommendation, recommended disposition fix-now/defer),
   throwaway branch/worktree allowed, never pushed, deleted afterwards; (c) minor/nit findings may be deferred to follow-up issues once no
   blocker/major is open (process in docs/ORCHESTRATION.md on the PR #16 branch once merged; until then report deferrable findings clearly).
   Add a test (in test_wiring.py) that REVIEW.md and both prompts contain the reviewer-never-pushes and test-first sentences.
6. Run `scripts/verify.sh`, push, then review round 2 (R10): FRESH Opus high-effort report-only reviewer subagents (no authoring context), fix, repeat
   until only nits remain; max 4 rounds in this batch (round 1 = R9 already ran). Final summary: what changed, rounds, findings per severity per
   round, incidents, owner actions (big-pr label, make repo public, branch protection).
Open question for the owner/orchestrator: the context hook fires at 50% of a 200k default window. If this session model has a 1M window this is a
false alarm; calibrate `LISTICLES_CONTEXT_WINDOW` per role (same note as session 4). Two sessions in a row hit the hook early, so the calibration matters.
