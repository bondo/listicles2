#!/usr/bin/env bash
# Guard checks (PLAN section 5.4). Fails on weakened checks.
#   guards.sh            content checks on the working tree + diff checks against $GUARD_BASE (default origin/main)
#   guards.sh --staged   content checks on the staged index only (pre-commit)
# Env: CI=true makes a missing base a hard failure and enables the diff-size limit (GUARD_MAX_DIFF, default 600).
#      GOLDEN_UPDATE=1 allows changed screenshot references (CI sets it from the PR label).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

STAGED=0
[ "${1:-}" = "--staged" ] && STAGED=1
BASE="${GUARD_BASE:-origin/main}"
fail=0
bad() { echo "guard: $*"; fail=1; }

# Everything tracked except prose, generated and third-party files, and this script (it names the patterns).
EXCL=(':!docs' ':!handoff' ':!*.md' ':!scripts/guards.sh' ':!*package-lock.json' ':!*.lock' ':!*.png' ':!*.jar'
  ':!gradle/wrapper' ':!gradlew' ':!gradlew.bat' ':!**/node_modules/**' ':!**/build/**')
GREP=(git grep -nHI -E)
[ "$STAGED" = 1 ] && GREP=(git grep --cached -nHI -E)

# 1. Disabled or focused tests.
out=$("${GREP[@]}" '@([A-Za-z]+\.)*Ignored?\b|@Disabled[A-Za-z]*|@EnabledIf|\bx(it|test|describe|context|should|[A-Z][A-Za-z]*)\(|enabled *= *false|\.(only|skip)\(|\bfit\(' -- "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled test: /'; fail=1; }
out=$("${GREP[@]}" '"(!|f:)[A-Za-z]' -- '*/src/*[Tt]est*/*.kt' '*/src/*[Tt]est*/*.js')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled or focused test name: /'; fail=1; }

# 2. Suppressions and weakened settings need "justified: <reason>" on the same line.
PAT='Suppress\(|tools:ignore|ktlint-disable|detekt:|lint\.disable|noinspection|disable *\+?=|disable\.add|disable\(|'
PAT+='ktlint_[A-Za-z0-9_-]+ *= *disabled|ij_[a-z_]*ktlint[a-z_]*|(informational|warning|ignore) *\+?= *["(s]|'
PAT+='severity *[=:] *"?(ignore|informational|info)|warningsAsErrors *[=:] *false|ignoreWarnings|ignoreFailures *= *true|'
PAT+='abortOnError *= *false|checkReleaseBuilds *= *false|maxIssues: *[1-9]|active: *false'
out=$("${GREP[@]}" "$PAT" -- "${EXCL[@]}" | grep -vE 'justified:[[:space:]]*[^[:space:]*/]')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }

# 3. Baselines, by name, by wiring and by content.
LS=(git ls-files)
[ "$STAGED" = 1 ] && LS=(git diff --cached --name-only --diff-filter=AM)
out=$("${LS[@]}" | grep -E '(^|/)[^/]*baseline[^/]*\.xml$')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline file: /'; fail=1; }
out=$("${GREP[@]}" 'baseline *[=(]|<SmellBaseline>|<issues format=' -- '*.kts' '*.gradle' '*.xml' '*.yml' | grep -v 'justified:')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline wiring: /'; fail=1; }

if [ "$STAGED" = 0 ]; then
  # 4. Diff checks need the base ref.
  MB=""
  git rev-parse --verify -q "$BASE" >/dev/null && MB=$(git merge-base "$BASE" HEAD 2>/dev/null)
  if [ -z "$MB" ]; then
    if [ "${CI:-}" = true ]; then bad "no base/merge-base '$BASE' (CI checkout needs fetch-depth: 0)"
    else echo "guard: note: base '$BASE' not found, skipped diff-based checks"; fi
  else
    DSPEC=(. ':!docs' ':!handoff' ':!scripts/guards.sh' ':!*package-lock.json')
    # Lowered or removed thresholds and severities.
    git diff -U0 "$MB" HEAD -- "${DSPEC[@]}" | awk '
      function norm(l,   n) { sub(/^[-+]/, "", l); gsub(/^[ \t]+|[ \t]+$/, "", l); return l }
      function num(l) { if (match(l, /[0-9]+/)) return substr(l, RSTART, RLENGTH) + 0; return -1 }
      /^(---|\+\+\+)/ { next }
      /(minBound|mutationThreshold|threshold|error *\+?=|fatal *\+?=|warningsAsErrors|maxIssues|failOnSeverity)/ {
        l = norm($0); key = l; gsub(/[0-9]+/, "N", key)
        if (substr($0, 1, 1) == "-") { rem[key] = l; remn[key] = num(l) } else { add[key] = l; addn[key] = num(l) }
      }
      END {
        for (k in rem) {
          if (!(k in add)) { print "guard: removed check setting: " rem[k]; bad = 1 }
          else if (remn[k] >= 0 && addn[k] >= 0 && addn[k] < remn[k] && rem[k] !~ /maxIssues/) { print "guard: lowered threshold: " add[k]; bad = 1 }
        }
        exit bad
      }' || fail=1
    # Screenshot references.
    if [ "${GOLDEN_UPDATE:-0}" != 1 ] && git diff --name-only "$MB" HEAD \
      | grep -E '(screenshots|golden|snapshots|roborazzi)/.*\.png$|src/[A-Za-z]*[Tt]est[A-Za-z]*/.*\.png$' | grep -q .; then
      bad "screenshot references changed without the golden-update label"
    fi
    # Diff size outside generated files (docs count). Enforced in CI only.
    if [ "${CI:-}" = true ]; then
      max="${GUARD_MAX_DIFF:-600}"
      case "$max" in ''|*[!0-9]*) bad "GUARD_MAX_DIFF is not a number: '$max'"; max=600 ;; esac
      n=$(git diff --numstat "$MB" HEAD -- . ':!*.lock' ':!gradle/wrapper' ':!gradlew' ':!gradlew.bat' ':!*package-lock.json' \
          ':!*.png' ':!*.jar' | awk '$1 != "-" {s += $1 + $2} END {print s + 0}')
      [ "$n" -gt "$max" ] && bad "diff is $n changed lines (limit $max); split the PR or ask the owner for the big-pr label"
    fi
  fi
fi

[ "$fail" = 0 ] && echo "guards: ok"
exit "$fail"
