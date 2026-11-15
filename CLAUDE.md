# CLAUDE.md: rules for agents working on Listicles

Read `docs/PLAN.md` (section for your task) and your handoff file in `handoff/` if one exists. Shared household
lists app: Kotlin, Compose, Firebase (Firestore + Auth), no Cloud Functions, English + Danish.

## Run checks with one command
- `scripts/verify.sh` (quiet: one line per step, details only for failures). `--fast` skips unit tests.
  Do not run raw Gradle or npm test commands for general verification, and do not paste full logs anywhere.
- First thing in a fresh clone: `scripts/install-hooks.sh`.
- Failure in CI: delegate log reading to the `ci-triage` subagent.

## Rules enforced by tools (do not try to get around them)
- No `--no-verify`, no force-push, no push to `main`, no `git reset --hard`/`stash`/`checkout .` with
  uncommitted changes (commit a WIP commit first). The PreToolUse hook blocks these.
- Process files are read-only for you: `CLAUDE.md`, `REVIEW.md`, `agents/`, `.claude/`, `.github/`, `.githooks/`,
  `scripts/guards.sh`, `scripts/hooks/`. Only sessions started with `LISTICLES_TASK=tooling` may edit them.
  If you think one needs a change, say so in the PR description.
- Never disable or skip a test, add a baseline, lower a threshold, or add a suppression. If a check is wrong, ask.
  A suppression needs `// justified: <specific reason>` on the same line; reviewers check it.
- Never commit secrets or `google-services.json`.

## How to work
- Test-first for ALL code, tooling included (hooks, guards, scripts, CI checks, metrics, status line): commit a failing test
  first (the commit order shows it), with negative cases, wired into `scripts/verify.sh` and CI. A bug fix starts with a
  test that fails for the right reason. Domain logic gets property tests. Reviewers flag untested changes.
- One PR = one concern, about 400 changed lines or fewer.
- Strings only in resources, always English and Danish (`values/` and `values-da/`). Plurals use `<plurals>`.
- Domain code (`core/domain`) is pure Kotlin, whole-number arithmetic only, no floating point.
- Firestore rules changes need allow and deny tests in `firebase/test`.
- Match existing style; spotless and detekt run in the pre-commit hook.

## Saving tokens
- Search narrowly and read files in parts. Delegate broad searches to the `explorer` subagent.
- Do not re-read files you just edited. Do not narrate; report results.

## Context and handoff
- The status line shows context %. At about 50% a hook reminds you: finish the current step, write
  `handoff/<branch>.md` from `handoff/TEMPLATE.md`, commit, and end the session.
- One PR per implementer session; one review round per reviewer session.

## Reviews
- Process and finding format: `REVIEW.md`. Max 4 rounds per batch (a one-batch PR: per PR); then stop and report to the owner.
- Reviewers never edit or push the PR branch: report only (a throwaway worktree is allowed, never pushed anywhere and deleted afterwards). Minor/nit findings may be
  deferred to follow-up issues once no blocker or major is open.
- Role models and effort: `agents/roles.yaml`. Do not change your own effort or model.
