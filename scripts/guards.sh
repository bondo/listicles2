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
EXCL=(':!docs' ':!handoff' ':!*.md' ':!scripts/guards.sh' ':!scripts/hooks/test_guards_sh.py' ':!*package-lock.json' ':!*.lock' ':!*.png' ':!*.jar'
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
# Also aliased imports, typealiases and backticked names of those annotations.
out=$(gg '@([A-Za-z]+\.)*`?(Ignored?\b|Disabled[A-Za-z]*|Enabled(If|On)[A-Za-z]*)|\.(only|skip)\(|import +[A-Za-z0-9_.]*\.(Ignored?|Disabled[A-Za-z]*|Enabled(If|On)[A-Za-z]*) +as +|typealias +[A-Za-z0-9_]+ *= *([A-Za-z0-9_]+\.)*(Ignored?|Disabled((If|On|In|For)[A-Za-z]*)?|Enabled(If|On)[A-Za-z]*)\b' -- "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled test: /'; fail=1; }
# Skipped Python tests in the hook suites (a CI gate). This includes test_guards_sh.py, which builds its fixtures by concatenation.
out=$(gg '@unittest\.skip|\bskip(If|Unless|Test)\b|SkipTest\b|expectedFailure|from +unittest +import .*\bskip|@skip\b' -- 'scripts/hooks/test_*.py')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: skipped python test: /'; fail=1; }
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
PAT+='disableDefaultRuleSets|<ignore |failOnNoDiscoveredTests *= *false|'
# Linter, type-checker, coverage and formatter directives (ruff/flake8, mypy, ESLint, TypeScript, coverage.py, c8/istanbul/v8, prettier, black, biome).
PAT+='[Nn][Oo][Qq][Aa]|type: *ignore|mypy: *(ignore-errors|allow-|disable-error-code)|eslint-disable|@ts-(ignore|expect-error|nocheck)|'
PAT+='pragma: *no (cover|branch)|(c8|v8|istanbul) ignore|prettier-ignore|biome-ignore|dprint-ignore|fmt: *(off|skip)|yapf: *disable|isort: *(skip|off)|@formatter:off'
JUST='justified:[[:space:]]*[^[:space:]*/]'
out=$(gg "$PAT" -- "${EXCL[@]}" | grep -vE "$JUST")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }

# 2b. Relaxed settings in the linter config files themselves (same justification rule). Each pattern only applies to the files
# named with it, so ordinary code and data (`ignore = x`, "off") never match.
cfgcheck() { # cfgcheck <pattern> <pathspec>...
  local pat="$1" o; shift
  o=$(gg "$pat" -- "$@" "${EXCL[@]}" | grep -vE "$JUST")
  [ -n "$o" ] && echo "$o" | sed 's/^/guard: unjustified suppression: /'
  return 0
}
# ruff, flake8, mypy, coverage.py
PYPAT='per-file-ignores|per-file-target-version|^[[:space:]]*(extend-|force-)?(ignore|exclude)[[:space:]]*=|^[[:space:]]*(omit|exclude_lines|exclude_also)[[:space:]]*=|'
PYPAT+='(^|[^a-z_])(ignore_errors|ignore_missing_imports|implicit_reexport|allow_[a-z_]+)[[:space:]]*=[[:space:]]*(true|True|1)|'
PYPAT+='(strict|strict_optional|strict_equality|check_untyped_defs|no_implicit_optional|(disallow|warn)_[a-z_]+)[[:space:]]*=[[:space:]]*(false|False|0)|'
PYPAT+='follow_imports[[:space:]]*=[[:space:]]*.?(skip|silent)|disable_error_code'
# tsconfig
TSPAT='"(strict|noImplicitAny|strictNullChecks|strictFunctionTypes|strictBindCallApply|strictPropertyInitialization|noImplicitThis|alwaysStrict|'
TSPAT+='useUnknownInCatchVariables|noUncheckedIndexedAccess|exactOptionalPropertyTypes|noImplicitReturns|noImplicitOverride|noFallthroughCasesInSwitch|'
TSPAT+='noUnusedLocals|noUnusedParameters|noPropertyAccessFromIndexSignature|checkJs)"[[:space:]]*:[[:space:]]*false|'
TSPAT+='"(allowUnreachableCode|allowUnusedLabels|suppressImplicitAnyIndexErrors|suppressExcessPropertyErrors)"[[:space:]]*:[[:space:]]*true'
# ESLint (rules off or downgraded to warn, ignored files, unused-directive reporting off) and biome
ESPAT=':[[:space:]]*(\[[[:space:]]*)?(.?(off|warn).?|0|1)[[:space:]]*([],}]|$|//)|\bignores[[:space:]]*:|ignorePatterns|globalIgnores|'
ESPAT+='reportUnusedDisableDirectives[[:space:]]*:[[:space:]]*(false|.?off.?|0)'
# coverage exclusions in jest, vitest, nyc and c8 config
COVPAT='coveragePathIgnorePatterns|collectCoverageFrom|exclude[^A-Za-z0-9_:]{0,2}:'
out=$(cfgcheck "$PYPAT" '*pyproject.toml' '*ruff.toml' '*mypy.ini' '*setup.cfg' '*tox.ini' '*.flake8' '*.coveragerc'
  cfgcheck "$TSPAT" '*tsconfig*.json' '*jsconfig*.json'
  cfgcheck "$ESPAT" '*eslint.config.*' '*eslintrc*' '*biome.json*'
  cfgcheck "$COVPAT" '*vitest.config.*' '*jest.config.*' '*nycrc*' '*c8rc*')
[ -n "$out" ] && { echo "$out"; fail=1; }

# 3. Baselines (no escape hatch): by name, by wiring and by content, any file type.
LS=(git ls-files)
[ "$STAGED" = 1 ] && LS=(git diff --cached --name-only --diff-filter=AM)
out=$("${LS[@]}" | grep -iE 'baseline')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline file: /'; fail=1; }
# Formatter and linter ignore files cannot carry a same-line justification, so they are refused outright (ask the owner).
out=$("${LS[@]}" | grep -E '(^|/)\.(prettier|eslint|stylelint|dprint)ignore$')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: ignore file: /'; fail=1; }
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
    DSPEC=(. ':!docs' ':!handoff' ':!scripts/guards.sh' ':!scripts/hooks/test_guards_sh.py' ':!*package-lock.json')
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
