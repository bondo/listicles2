#!/usr/bin/env bash
# One entrypoint, same steps as CI. Quiet: one line per step, details only on failure.
# Usage: scripts/verify.sh [--fast]   (--fast skips unit tests and coverage)
set -uo pipefail
cd "$(dirname "$0")/.."

FAST=0
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
    grep -v '^Picked up' "$log" | grep -E 'FAILED|Error|error:|warning:|Violation|\* What went wrong|^e: |^> ' | head -25
    echo "      full log: $log"
    fail=1
  fi
}

gradle() { ./gradlew -q --console=plain "$@"; }

step guards ./scripts/guards.sh
step spotless gradle spotlessCheck
step detekt gradle detekt
step lint gradle :app:lintDebug
if [ "$FAST" = 0 ]; then
  step unit-tests gradle testDebugUnitTest :core:domain:test
  step coverage gradle koverVerify
fi
step build gradle :app:assembleDebug :app:assembleDebugAndroidTest
if [ -f firebase/package.json ] && [ "${SKIP_FIREBASE:-0}" != 1 ]; then
  step firebase-rules bash -c 'cd firebase && npm ci --silent && npm test --silent'
fi

[ "$fail" = 0 ] && echo "verify: all steps passed" || echo "verify: FAILED"
exit "$fail"
