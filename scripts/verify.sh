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
step hook-tests python3 -I scripts/hooks/run_hook_tests.py --jobs 4
step ci-scope-tests python3 -I scripts/test_ci_scope.py
# Issue 216 (owner decision 7003898899): the slow Gradle gate self-tests run only when one of their inputs changed since the
# merge base with origin/main; anything but a clean `skip` from scripts/ci_scope.py runs them. CI on main always runs them.
gate_exclude=()
if gate_scope=$(python3 -I scripts/ci_scope.py local-scope 2>/dev/null) && [ "$gate_scope" = skip ]; then
  echo "skip  warnings-gate-tests, jdk-release-gate-tests, testLicenseeGate (no gate input changed since the merge base with origin/main; scripts/ci_scope.py)"
  SKIPPED=1
  gate_exclude=(-x testLicenseeGate)
else
  step warnings-gate-tests python3 -I scripts/test_warnings_gate.py
  step jdk-release-gate-tests python3 -I scripts/test_jdk_release_gate.py
fi
step pit-config-tests python3 -I scripts/test_check_pit_config.py
step pit-config python3 -I scripts/check_pit_config.py
step tasks-tests python3 -I scripts/test_tasks.py
step issue-forms-tests python3 -I scripts/test_issue_forms.py
step issue-forms python3 -I scripts/issue_forms.py
step collab-inbox-tests python3 -I scripts/test_collab_inbox.py
step merge-ready-tests python3 -I scripts/test_merge_ready.py
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
step test-results-gate-tests python3 -I scripts/test_check_test_results.py
step coverage-impact-tests python3 -I scripts/test_coverage_impact.py
step screenshots-tests python3 -I scripts/test_screenshots.py
step screenshots-wiring python3 -I scripts/check_screenshots.py
step gitignore-secrets-tests python3 -I scripts/test_gitignore_secrets.py
step wrapper-checksum-tests python3 -I scripts/test_check_gradle_wrapper.py
step wrapper-checksum python3 -I scripts/check_gradle_wrapper.py
step dependency-floors-tests python3 -I scripts/test_dependency_floors.py
step dependency-floors python3 -I scripts/dependency_floors.py
step python-lint-tests python3 -I scripts/test_lint_python.py
step python-lint ./scripts/lint_python.sh
step workflow-lint-tests python3 -I scripts/test_lint_workflows.py
step workflow-lint ./scripts/lint_workflows.sh
step spotless gradle spotlessCheck
step detekt gradle detekt :core:domain:detektMain :core:domain:detektTest :core:testing:detektMain :core:testing:detektTest ${gate_exclude[@]+"${gate_exclude[@]}"}
step lint gradle :app:lintDebug
if [ "$FAST" = 0 ]; then
  step unit-tests gradle testDebugUnitTest :core:domain:test
  step coverage gradle koverVerify -x :core:domain:pitest
  step coverage-xml gradle koverXmlReport
  step coverage-impact python3 -I scripts/coverage_impact.py --xml build/reports/kover/report.xml --base origin/main
  # M1-07: the step passes with uncovered changed lines (koverVerify is the gate); show them, they are what a reviewer will ask about.
  grep -q '^- `' "$LOG_DIR/coverage-impact.log" 2>/dev/null && sed -n '1p;3,12p' "$LOG_DIR/coverage-impact.log" | sed 's/^/      /'
  step mutation gradle :core:domain:pitest
  step screenshots ./scripts/screenshots.sh verify
else
  echo "skip  unit-tests, coverage, coverage-impact, mutation, screenshots (--fast)"; SKIPPED=1
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
