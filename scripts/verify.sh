#!/usr/bin/env bash
# One entrypoint, same steps as CI. Quiet: one line per step, details only on failure.
# Usage: scripts/verify.sh [--fast]   (--fast skips unit tests and coverage)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

FAST=0
SKIPPED=0
[ "${1:-}" = "--fast" ] && FAST=1
fail=0
LOG_DIR="${TMPDIR:-/tmp}/listicles-verify"
mkdir -p "$LOG_DIR"

step() {
  local name="$1"; shift
  local log="$LOG_DIR/${name// /_}.log"
  local start=$SECONDS
  if "$@" >"$log" 2>&1; then
    printf 'ok    %-22s %3ss\n' "$name" "$((SECONDS - start))"
  else
    printf 'FAIL  %-22s %3ss\n' "$name" "$((SECONDS - start))"
    grep -v '^Picked up' "$log" > "$log.f"
    { grep -E '^guard|FAILED|Error|error:|warning:|Violation|\* What went wrong|^e: |^> ' "$log.f" || tail -25 "$log.f"; } | head -25
    echo "      full log: $log"
    fail=1
  fi
}

gradle() { ./gradlew -q --console=plain "$@"; }

step guards ./scripts/guards.sh
step hook-tests python3 -I scripts/hooks/run_hook_tests.py
step warnings-gate-tests python3 -I scripts/test_warnings_gate.py
step tasks-tests python3 -I scripts/test_tasks.py
step issue-forms-tests python3 -I scripts/test_issue_forms.py
step issue-forms python3 -I scripts/issue_forms.py
step collab-inbox-tests python3 -I scripts/test_collab_inbox.py
step status-visual-tests python3 -I scripts/test_status_visual.py
step status-page-tests python3 -I scripts/test_status_page.py
step status-publish-tests python3 -I scripts/test_status_publish.py
step status-workflow-tests python3 -I scripts/test_status_workflow.py
step prompt-rules-tests python3 -I scripts/test_prompt_rules.py
step prompt-rules python3 -I scripts/prompt_rules.py
step tasks-validate python3 -I scripts/tasks.py validate
step owner-drift-tests python3 -I scripts/test_owner_drift_check.py
step metrics-tests python3 -I scripts/test_agent_metrics.py
step metrics-check python3 -I scripts/agent_metrics.py --check
step docs-check-tests python3 -I scripts/test_docs_check.py
step docs-check python3 -I scripts/docs_check.py
step design-tokens-tests python3 -I scripts/test_design_tokens.py
step design-tokens python3 -I scripts/design_tokens.py
step wireframes-safety-tests python3 -I scripts/test_wireframes_safety.py
step wireframes-safety python3 -I scripts/wireframes_safety.py
step gradle-repos-tests python3 -I scripts/test_check_gradle_repos.py
step gradle-repos python3 -I scripts/check_gradle_repos.py
step python-lint-tests python3 -I scripts/test_lint_python.py
step python-lint ./scripts/lint_python.sh
step workflow-lint-tests python3 -I scripts/test_lint_workflows.py
step workflow-lint ./scripts/lint_workflows.sh
step spotless gradle spotlessCheck
step detekt gradle detekt :core:domain:detektMain :core:domain:detektTest
step lint gradle :app:lintDebug
if [ "$FAST" = 0 ]; then
  step unit-tests gradle testDebugUnitTest :core:domain:test
  step coverage gradle koverVerify
else
  echo "skip  unit-tests, coverage (--fast)"; SKIPPED=1
fi
step build gradle :app:assembleDebug :app:assembleDebugAndroidTest
step firebase-install bash -c 'cd firebase && npm ci --silent'
step firebase-typecheck bash -c 'cd firebase && npm run typecheck --silent'
step firebase-lint bash -c 'cd firebase && npm run lint --silent'
step firebase-format bash -c 'cd firebase && npm run format:check --silent'
step firebase-ts-tests python3 -I scripts/test_firebase_ts.py
if [ "${SKIP_FIREBASE:-0}" = 1 ]; then
  echo "skip  firebase-rules (SKIP_FIREBASE=1)"; SKIPPED=1
else
  step firebase-rules bash -c 'cd firebase && npm test --silent'
fi

[ "$fail" = 0 ] && echo "verify: all steps passed$([ "$SKIPPED" = 1 ] && echo " (some skipped)")" || echo "verify: FAILED"
exit "$fail"
