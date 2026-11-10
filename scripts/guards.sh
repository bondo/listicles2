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
# Runs git grep; a real error (rc>1, e.g. bad regex) fails the guard instead of looking like "no match".
ERRF=$(mktemp) || { echo "guard: mktemp failed" >&2; exit 1; }
trap 'rm -f "$ERRF"' EXIT
gg() {
  local o rc
  o=$("${GREP[@]}" "$@"); rc=$?
  # Marker file, because callers run gg in a subshell where fail=1 would be lost.
  [ "$rc" -gt 1 ] && echo "guard: internal error in git grep (rc=$rc)" | tee -a "$ERRF" >&2
  printf '%s' "$o"
}
TESTSRC=('*/src/*[Tt]est*/*.kt' '*/src/*[Tt]est*/*.js' '*/src/*[Tt]est*/*.ts' 'firebase/test/*')
CFGSRC=('*.gradle.kts' '*.gradle' '*package.json' '*jest.config.*' '*.properties' '*/src/*[Tt]est*/resources/*')

# 1. Disabled or focused tests (anywhere), and test-only forms (test sources only, so production code may use enabled = false).
out=$(gg '@([A-Za-z]+\.)*Ignored?\b|@Disabled[A-Za-z]*|@Enabled(If|On)[A-Za-z]*|\.(only|skip)\(' -- "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled test: /'; fail=1; }
out=$(gg 'enabled(If|OrReasonIf)? *[=(]|\bx(it|test|describe|context|should|expect|when|then|given|feature|scenario|and|[A-Z][A-Za-z]*)\(|\bfit\(|assume(True|False)\(|"(!|f:)[A-Za-z]|passWithNoTests|testPathIgnorePatterns' -- "${TESTSRC[@]}" "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled or focused test: /'; fail=1; }

# Not exhaustive by nature; CODEOWNERS (owner review of build files) is the real control.
out=$(gg '[Ee]nabled *(= *|\() *(false|!)|onlyIf *(\([^)]*\))? *\{ *false|excludeTest(s|sMatching)?\b|exclude(Tags|Engines)\(|exclude\("[^"]*[Tt]est|passWithNoTests|testPathIgnorePatterns|testMatch|testRegex|"roots"|testNamePattern|testPathPattern| -t |kotest\.(tags|filter)' -- "${CFGSRC[@]}" "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled tests via build config: /'; fail=1; }

# 2. Suppressions and weakened settings need "justified: <reason>" on the same line.
PAT='Suppress[A-Za-z]*\(|tools:ignore|ktlint-disable|detekt:|lint\.disable|noinspection|disable *\+?=|disable\.add|disable\(|'
PAT+='ktlint_[A-Za-z0-9_-]+ *= *disabled|to *"disabled"|ij_[a-z_]*ktlint[a-z_]*|(informational|warning|ignore) *\+?= *["(s]|'
PAT+='severity *[=:] *["'"'"']?(ignore|informational|info)|warningsAsErrors *[=:] *false|ignoreWarnings|ignoreFailures *= *true|'
PAT+='abortOnError *= *false|checkReleaseBuilds *= *false|maxIssues: *[1-9]|active: *false|excludes:|checkOnly|ignoreTestSources|'
PAT+='disableDefaultRuleSets|<ignore |failOnNoDiscoveredTests *= *false'
out=$(gg "$PAT" -- "${EXCL[@]}" | grep -vE 'justified:[[:space:]]*[^[:space:]*/]')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }

# 3. Baselines (no escape hatch): by name, by wiring and by content, any file type.
LS=(git ls-files)
[ "$STAGED" = 1 ] && LS=(git diff --cached --name-only --diff-filter=AM)
out=$("${LS[@]}" | grep -iE 'baseline')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline file: /'; fail=1; }
out=$(gg 'baseline *(=|\(|\.set)|<SmellBaseline>|<issues format=' -- "${EXCL[@]}")
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
      /^diff --git/ { file = $3; next }
      /^(---|\+\+\+)/ { next }
      /(minBound|mutationThreshold|threshold|failOnNoDiscoveredTests|useJUnitPlatform|error *\+?=|fatal *\+?=|warningsAsErrors|maxIssues|failOnSeverity)/ {
        l = norm($0); key = file "|" l; gsub(/[0-9]+/, "N", key)
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

[ -s "$ERRF" ] && fail=1
[ "$fail" = 0 ] && echo "guards: ok"
exit "$fail"
