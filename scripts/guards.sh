#!/usr/bin/env bash
# Guard checks (PLAN section 5.4). Fails on weakened checks. Compares to $GUARD_BASE (default origin/main).
# GOLDEN_UPDATE=1 allows changed screenshot references (CI sets it from the PR label).
set -uo pipefail
cd "$(dirname "$0")/.."

BASE="${GUARD_BASE:-origin/main}"
fail=0
bad() { echo "guard: $*"; fail=1; }

SRC_DIRS=(app core firebase)
mapfile -t files < <(git ls-files -- "${SRC_DIRS[@]}" '*.gradle.kts' 'gradle/libs.versions.toml' '.editorconfig' \
  | grep -vE '(^|/)(node_modules|build)/' | grep -E '\.(kt|kts|java|xml|js|ts|json|yml|yaml|toml|editorconfig|properties)$|\.editorconfig$')

if [ "${#files[@]}" -gt 0 ]; then
  # 1. Disabled tests.
  out=$(grep -nE '@Ignore\b|@Disabled\b|\bxit\(|\bxdescribe\(|\.only\(|\bfit\(' "${files[@]}")
  [ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled test: /'; fail=1; }
  # 2. Suppressions need a "// justified:" reason on the same line.
  out=$(grep -nE '@Suppress|tools:ignore|ktlint-disable|detekt:|lint\.disable|disable \+=|ij_|ktlint_[a-z_]*=\s*disabled' "${files[@]}" | grep -v 'justified:')
  [ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }
fi

# 3. Baselines.
if git ls-files | grep -E '(^|/)(detekt-baseline|lint-baseline|baseline)[^/]*\.xml$' | grep -q .; then
  bad "baseline file present"; git ls-files | grep -E '(^|/)(detekt-baseline|lint-baseline|baseline)[^/]*\.xml$'
fi

# 4+5+6 need the base ref.
if git rev-parse --verify -q "$BASE" >/dev/null; then
  MB=$(git merge-base "$BASE" HEAD)
  # Lowered thresholds: any removed minBound/threshold/severity line whose replacement is lower.
  git diff -U0 "$MB" HEAD -- '*.kts' '*.yml' '*.yaml' '*.toml' ':!docs' | awk '
    /^-.*(minBound|threshold|mutationThreshold)/ { match($0,/[0-9]+/); old=substr($0,RSTART,RLENGTH); have=1; next }
    /^\+.*(minBound|threshold|mutationThreshold)/ { match($0,/[0-9]+/); n=substr($0,RSTART,RLENGTH); if (have && n+0 < old+0) { print "guard: lowered threshold: " $0; bad=1 } have=0 }
    END { exit bad }' || fail=1
  if git diff -U0 "$MB" HEAD -- '*.kts' 'config/*' | grep -E '^\+' | grep -qE 'severity.*(info|ignore)|ignoreFailures *= *true|abortOnError *= *false'; then
    bad "lint/detekt severity lowered or failures ignored"
  fi
  # Screenshot references.
  if [ "${GOLDEN_UPDATE:-0}" != 1 ] && git diff --name-only "$MB" HEAD | grep -E '(^|/)(screenshots|golden)/.*\.png$|/roborazzi/.*\.png$' | grep -q .; then
    bad "screenshot references changed without the golden-update label"
  fi
  # Diff size outside generated files.
  n=$(git diff --numstat "$MB" HEAD -- . ':!docs' ':!handoff' ':!*.lock' ':!gradle/wrapper' ':!gradlew' ':!gradlew.bat' ':!*/package-lock.json' ':!*.png' ':!*.jar' \
      | awk '$1 != "-" {s += $1 + $2} END {print s + 0}')
  max="${GUARD_MAX_DIFF:-600}"
  [ "$n" -gt "$max" ] && bad "diff is $n changed lines (limit $max, excluding docs); split the PR"
else
  echo "guard: note: base '$BASE' not found, skipped diff-based checks"
fi

[ "$fail" = 0 ] && echo "guards: ok"
exit "$fail"
