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

## Next (in order, small reviewed commits)
1. `scripts/verify.sh` (quiet, one line per step) + `scripts/guards.sh` (PLAN §5.4) + `.githooks/` + `scripts/install-hooks.sh`.
2. `firebase/`: `firebase.json` (emulator project `demo-listicles`), deny-all `firestore.rules`, Jest +
   `@firebase/rules-unit-testing` with one deny test. firebase-tools comes from npm. Check that the
   emulator jar download host is reachable (storage.googleapis.com answered 400 at root, which is probably fine).
3. `.github/workflows/ci.yml` (jobs: static, unit, firebase, ui, guards, secrets), `dependabot.yml`,
   `pull_request_template.md`, `CODEOWNERS` (`* @bondo` for the guarded paths), wrapper validation.
4. `REVIEW.md` (severity definitions, JSON findings format with IDs, 4-round cap), `CLAUDE.md`.
5. Agent setup (PLAN §9): `agents/roles.yaml`, `agents/prompts/*.md`, `.claude/agents/{explorer,ci-triage}.md`,
   `.claude/settings.json` (status line + PreToolUse deny hooks + context-guard hook),
   `scripts/statusline.sh`, `handoff/TEMPLATE.md`, and a metrics spike: prove that a SessionEnd
   hook can read token usage from the transcript.
6. Evaluate detekt 2.x vs 1.23 (record the result in an ADR). Add Kover to `:app`. Add a dark theme.
7. Prove the gates: a deliberately broken commit makes CI fail, then revert it.

## Facts that save time
- Statusline JSON has `context_window.used_percentage` (checked in the Claude Code 2.1.322 binary).
  PostToolUse and UserPromptSubmit hooks accept `hookSpecificOutput.additionalContext`.
- Local SDK at `/opt/android-sdk` (not in the repo; `local.properties` is gitignored). The environment
  allowlist now includes `dl.google.com`.
- Maven Central returns 429 through the proxy: `~/.gradle/init.d/central-mirror.gradle.kts` routes it
  to Google's mirror. It is local only; recreate it in a new container.
- Tool inputs may turn `\uXXXX` escapes into literal characters. Write Kotlin escapes with
  `chr(92)` in Python, then verify with `od -c`.
- Kover counts value-class synthetic code, which is why `CatalogKey` is a data class.

## Waiting on the owner
- (Resolved) Owner accepted the round-4 fixes; no 5th round.
- (Resolved) Draft PR opened; continue on this branch, one review round per batch of commits.
- Make the repo public (owner gets a reminder on 2026-11-11).
