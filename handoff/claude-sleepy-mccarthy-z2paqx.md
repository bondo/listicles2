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
