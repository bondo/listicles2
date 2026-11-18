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
out=$(gg '@([A-Za-z]+\.)*`?(Ignored?\b|Disabled[A-Za-z]*|Enabled(If|On)[A-Za-z]*)|\.(only|skip)\(|import +[A-Za-z0-9_.]*\.(Ignored?|Disabled[A-Za-z]*|Enabled(If|On)[A-Za-z]*) +as +|typealias +[A-Za-z0-9_]+ *= *([A-Za-z0-9_]+\.)*(Ignored?|Disabled(If(EnvironmentVariables?|SystemPropert(y|ies))?|On(Os|Jre(Range)?)|ForJreRange|InNativeImage)?|Enabled(If|On)[A-Za-z]*)\b' -- "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled test: /'; fail=1; }
# Skipped Python tests in the hook suites (a CI gate). This includes test_guards_sh.py, which builds its fixtures by concatenation.
out=$(gg '@unittest\.skip|\bskip(If|Unless|Test)\b|SkipTest\b|expectedFailure|from +unittest +import .*\bskip|@skip\b' -- 'scripts/hooks/test_*.py')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: skipped python test: /'; fail=1; }
out=$(gg 'enabled(If|OrReasonIf)? *[=(]|\bx(it|test|describe|context|should|expect|when|then|given|feature|scenario|and|[A-Z][A-Za-z]*)\(|\bfit\(|assume(True|False)\(|"(!|f:)[A-Za-z]|passWithNoTests|testPathIgnorePatterns' -- "${TESTSRC[@]}" "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled or focused test: /'; fail=1; }

# Not exhaustive by nature; CODEOWNERS (owner review of build files) is the real control.
out=$(gg '[Ee]nabled *(= *|\() *(false|!)|onlyIf *(\([^)]*\))? *\{ *false|excludeTest(s|sMatching)?\b|exclude(Tags|Engines)\(|exclude\("[^"]*[Tt]est|passWithNoTests|testPathIgnorePatterns|testMatch|testRegex|"roots"|testNamePattern|testPathPattern| -t |kotest\.(tags|filter)' -- "${CFGSRC[@]}" "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: disabled tests via build config: /'; fail=1; }

LS=(git ls-files)
[ "$STAGED" = 1 ] && LS=(git diff --cached --name-only --diff-filter=AM)

# 2. Suppressions and weakened settings need "justified: <reason>" on the same line.
# The justification is looked for in the whole `path:line:text` grep output, so a tracked path containing it would waive every hit
# inside that path. Such paths are refused.
out=$("${LS[@]}" | grep -F 'justified:')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: justified: in a path: /'; fail=1; }
PAT='Suppress[A-Za-z]*\(|tools:ignore|ktlint-disable|detekt:|lint\.disable|noinspection|disable *\+?=|disable\.add|disable\(|'
PAT+='ktlint_[A-Za-z0-9_-]+ *= *disabled|to *"disabled"|ij_[a-z_]*ktlint[a-z_]*|(informational|warning|ignore) *\+?= *["(s]|'
PAT+='severity *[=:] *["'"'"']?(ignore|informational|info)|warningsAsErrors *[=:] *false|ignoreWarnings|ignoreFailures *= *true|'
PAT+='abortOnError *= *false|checkReleaseBuilds *= *false|maxIssues: *[1-9]|active: *false|excludes:|checkOnly|ignoreTestSources|'
PAT+='disableDefaultRuleSets|<ignore |failOnNoDiscoveredTests *= *false|'
# Linter, type-checker, coverage and formatter directives (ruff/flake8, mypy, ESLint, TypeScript, coverage.py, c8/istanbul/v8, prettier, black, biome).
PAT+='[Nn][Oo][Qq][Aa]|type: *ignore|eslint-disable|@ts-(ignore|expect-error)|@[Tt][Ss]-[Nn][Oo][Cc][Hh][Ee][Cc][Kk]|/\*[[:space:]]*eslint[[:space:]]+[@A-Za-z]|'
# mypy inline flags that relax (ignore-*, allow-*, no-*, =False, follow-imports=skip); ignore-without-code and =True are strict.
PAT+='mypy:(.*[[:space:],:])?(allow[-_]|implicit[-_](optional|reexport)|no[-_](strict|check[-_]untyped[-_]defs|(disallow|warn)[-_]))|mypy:.*(ignore[-_](errors|missing[-_]imports)|disable[-_]error[-_]code|follow[-_]imports[[:space:]]*=[[:space:]]*(skip|silent)|=[[:space:]]*([Ff]alse|0))|'
PAT+='[Pp][Rr][Aa][Gg][Mm][Aa][:[:space:]]?[[:space:]]*[Nn][Oo][[:space:]]*([Cc][Oo][Vv][Ee][Rr]|[Bb][Rr][Aa][Nn][Cc][Hh])|(c8|v8|istanbul) ignore|prettier-ignore|biome-ignore|dprint-ignore|fmt: *(off|skip)|yapf: *disable|isort: *(skip|off)|@formatter:off'
JUST='justified:[[:space:]]*[^[:space:]*/]'
out=$(gg "$PAT" -- "${EXCL[@]}" | grep -vE "$JUST")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }

# 2b. Relaxed settings in the linter config files themselves (same justification rule). Each pattern only applies to the files
# named with it, so ordinary code and data (`ignore = x`, "off") never match.
# The checks above are line by line, so a justification on a TOML table header or an array opener would waive every entry after it.
# entrycheck therefore reads the config files itself and requires the justification on every entry line of a relaxing multi-line
# table (per-file-ignores), array/object (ignore = [, exclude_lines = [, ignores: [) or INI continuation (ignore =<newline>  E501),
# and on the first element of an ESLint rule array that sets off/warn/0/1.
ENTRY_AWK='
function strip(l) { sub(/[ \t]*(#|\/\/).*$/, "", l); return l }
function blank(l) { gsub(/"[^"]*"/, "\"\"", l); gsub(/\047[^\047]*\047/, "\047\047", l); return l }
function nest(l,   t, o) { t = l; gsub(/[^[({]/, "", t); o = length(t); t = l; gsub(/[^])}]/, "", t); return o - length(t) }
function check() { if (line !~ JUSTRE) printf "%s:%d:%s\n", F, NR, line }
BEGIN { JUSTRE = "justified:[ \t]*[^ \t*/]"; ini = (F ~ /(\.ini|\.cfg|\.flake8|\.coveragerc)$/); es = (F ~ /eslint/) }
{
  line = $0; nc = strip(line); c = blank(nc); lc = tolower(nc)
  if (c ~ /^[ \t]*$/) next
  closer = (c ~ /^[ \t]*[])},;]*[ \t]*$/)
  if (mode == 1 && c ~ /^[ \t]*\[\[?[^][]+\]\]?[ \t]*$/) mode = 0
  if (mode == 3 && line !~ /^[ \t]/) mode = 0
  if (mode == 1 || mode == 3) { if (!closer) check(); next }
  if (mode == 2) { depth += nest(c); if (!closer) check(); if (depth <= 0) mode = 0; next }
  if (first) { first = 0; if (nc ~ /^[ \t]*["\047]?(off|warn|0|1)["\047]?[ \t]*,?[ \t]*$/) check() }
  if (c ~ /^[ \t]*\[\[?[^][]+\]\]?[ \t]*$/ && lc ~ /per[-_]file[-_](ignores|target[-_]version)/) { mode = 1; next }
  if (lc ~ /(ignore|exclude|omit|per[-_]file|collectcoveragefrom|disable_error_code)[a-z_.-]*["\047]?[ \t]*[:=(][ \t]*[[{(]/) { depth = nest(c); if (depth > 0) mode = 2; next }
  if (ini && line ~ /^[A-Za-z]/ && lc ~ /^(extend[-_]|force[-_])?(ignore|exclude|omit|per[-_]file[-_]ignores|per[-_]file[-_]target[-_]version|exclude_lines|exclude_also|disable_error_code)[ \t]*[=:]/) { mode = 3; next }
  if (es && nc ~ /:[ \t]*\[[ \t]*$/) first = 1
}'
entrycheck() { # entrycheck <pathspec>...
  local f
  while IFS= read -r f; do
    if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null | awk -v F="$f" "$ENTRY_AWK"
    else awk -v F="$f" "$ENTRY_AWK" "$f" 2>/dev/null; fi
  done < <(git ls-files -- "$@" "${EXCL[@]}") | sed 's/^/guard: unjustified suppression: /'
}
cfgcheck() { # cfgcheck <pattern> <pathspec>...
  local pat="$1" o; shift
  o=$(gg "$pat" -- "$@" "${EXCL[@]}" | grep -vE "$JUST")
  [ -n "$o" ] && echo "$o" | sed 's/^/guard: unjustified suppression: /'
  entrycheck "$@"
  return 0
}
# tsconfig: a base named by "extends" is only scanned when it matches *tsconfig*.json, so any other base needs a justification.
extcheck() {
  local ok='"extends"[[:space:]]*:[[:space:]]*("[^"]*(tsconfig|jsconfig)[^"]*"[[:space:]]*(,|$|//)|'
  ok+='\[[[:space:]]*"[^"]*(tsconfig|jsconfig)[^"]*"([[:space:]]*,[[:space:]]*"[^"]*(tsconfig|jsconfig)[^"]*")*[[:space:]]*\])'
  local o
  o=$(gg '"extends"[[:space:]]*:' -- '*tsconfig*.json' '*jsconfig*.json' "${EXCL[@]}" | grep -vE "$ok" | grep -vE "$JUST")
  [ -n "$o" ] && echo "$o" | sed 's/^/guard: unjustified suppression: /'
  return 0
}
# ruff, flake8, mypy, coverage.py
# A key may be bare, quoted, dotted (lint.ignore) or inside an inline table (lint = { ignore = [...] }); INI booleans are yes/on/1 and no/off/0.
KEYB='(^|[^A-Za-z0-9_-])["'"'"']?'
TRUE='([Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]|[Oo][Nn]|1)([^A-Za-z0-9_.]|$)'
FALSE='([Ff][Aa][Ll][Ss][Ee]|[Nn][Oo]|[Oo][Ff][Ff]|0)([^A-Za-z0-9_.]|$)'
PYPAT='per[-_]file[-_](ignores|target[-_]version)|'"$KEYB"'(extend[-_]|force[-_])?(ignore|exclude)["'"'"']?[[:space:]]*[=:]|'"$KEYB"'(omit|exclude_lines|exclude_also)["'"'"']?[[:space:]]*[=:]|'
PYPAT+='(^|[^a-z_])(ignore_errors|ignore_missing_imports|implicit_reexport|implicit_optional|allow_[a-z_]+)["'"'"']?[[:space:]]*[=:][[:space:]]*'"$TRUE"'|'
PYPAT+='(^|[^a-z_])no_(strict|strict_optional|strict_equality|check_untyped_defs|(disallow|warn)_[a-z_]+)["'"'"']?[[:space:]]*[=:][[:space:]]*'"$TRUE"'|'
PYPAT+='(^|[^a-z_])(strict|strict_optional|strict_equality|check_untyped_defs|no_implicit_optional|(disallow|warn)_[a-z_]+)["'"'"']?[[:space:]]*[=:][[:space:]]*'"$FALSE"'|'
PYPAT+='follow_imports[[:space:]]*[=:][[:space:]]*.?(skip|silent)|disable_error_code'
# tsconfig
TSPAT='"(strict|noImplicitAny|strictNullChecks|strictFunctionTypes|strictBindCallApply|strictPropertyInitialization|noImplicitThis|alwaysStrict|'
TSPAT+='useUnknownInCatchVariables|noUncheckedIndexedAccess|exactOptionalPropertyTypes|noImplicitReturns|noImplicitOverride|noFallthroughCasesInSwitch|'
TSPAT+='noUnusedLocals|noUnusedParameters|noPropertyAccessFromIndexSignature|checkJs)"[[:space:]]*:[[:space:]]*false|'
TSPAT+='"(allowUnreachableCode|allowUnusedLabels|suppressImplicitAnyIndexErrors|suppressExcessPropertyErrors|noCheck)"[[:space:]]*:[[:space:]]*true'
# ESLint (rules off or downgraded to warn, ignored files, unused-directive reporting off) and biome
# Numbers only count as severities after a rule key (line start or first key of `rules: {`), so option objects like { max: 1 } do not.
ESPAT=':[[:space:]]*(\[[[:space:]]*)?.?(off|warn).?[[:space:]]*([],}]|$|//)|'
ESPAT+='(^|rules["'"'"']?[[:space:]]*:[[:space:]]*\{)[[:space:]]*["'"'"']?[@A-Za-z0-9/_$-]+["'"'"']?[[:space:]]*:[[:space:]]*(\[[[:space:]]*)?[01][[:space:]]*([],}]|$|//)|'
ESPAT+='rules["'"'"']?[[:space:]]*:[[:space:]]*\{([^][{}]|\[[^]]*\])*,[[:space:]]*["'"'"']?[@A-Za-z0-9/_$-]+["'"'"']?[[:space:]]*:[[:space:]]*(\[[[:space:]]*)?[01][[:space:]]*([],}]|$|//)|'
ESPAT+='\bignores[[:space:]]*:|ignorePatterns|globalIgnores|'
ESPAT+='reportUnusedDisableDirectives[[:space:]]*:[[:space:]]*(false|.?off.?|0)'
# coverage exclusions in jest, vitest, nyc and c8 config
COVPAT='coveragePathIgnorePatterns|collectCoverageFrom|exclude[^A-Za-z0-9_:]{0,2}:'
out=$(cfgcheck "$PYPAT" '*pyproject.toml' '*ruff.toml' '*mypy.ini' '*setup.cfg' '*tox.ini' '*.flake8' '*.coveragerc'
  cfgcheck "$TSPAT" '*tsconfig*.json' '*jsconfig*.json'
  extcheck
  cfgcheck "$ESPAT" '*eslint.config.*' '*eslintrc*' '*biome.json*'
  cfgcheck "$COVPAT" '*vitest.config.*' '*jest.config.*' '*nycrc*' '*c8rc*'
  # prettier: requirePragma makes it skip every file without the pragma; ignorePath points it at another ignore file
  cfgcheck 'requirePragma["'"'"']?[[:space:]]*[:=][[:space:]]*true|ignore-?[Pp]ath' '*prettierrc*' '*prettier.config.*')
[ -n "$out" ] && { echo "$out"; fail=1; }

# 2c. Relaxations passed as command-line flags on tool invocation lines (issue 45): ruff, mypy, tsc, ESLint, Prettier, shellcheck, in
# shell scripts, git hooks, CI workflows and package.json. A backslash continuation is one logical line, and one same-line
# `justified: <reason>` waives the whole logical line (every command on it). A logical line loses its unquoted trailing ` # comment`
# and is split at ; & | so a flag only counts for the tool in its own command; only the text after the tool name is read (so
# `grep -i shellcheck` is not a flag). For npm and npx (and yarn, pnpm and bunx when they use `--`) the JS tools also see what follows a
# bare `--` (`npm run lint -- --quiet`); the options of npm itself never count. That passthrough is checked against every JS tool, so
# `npm test -- -u` or `npm run e2e -- -c x.ts` need a `justified:` too (issue 164). Flags may be quoted, shellcheck short options may be
# combined (-xe) and SHELLCHECK_OPTS counts as `SHELLCHECK_OPTS=`, `+=` or a YAML `SHELLCHECK_OPTS: value`.
# Config handed over on the command line (ruff --config, mypy --config-file, eslint -c/--config, prettier --config, tsc -p/--project/-b/--build)
# must name a file the config scan above (2b) reads, or `justified:`: an inline `--config "key = value"`, an absolute or
# `~` path, a `..` path and a path built from `$` or backticks (it may be generated at run time) are relaxations. `tsc` with a source
# file argument and no -p/-b ignores tsconfig.json, so it is flagged too.
# Strict flags (--strict, --max-warnings 0, -S warning, ...) never match. Not covered: action `with: args:` lines, YAML folded scalars,
# Makefiles, composite actions and .pre-commit-config.yaml (none exists today; issue 164), and flags held in shell variables
# (`FLAGS="--ignore E501"; ruff check $FLAGS`), because a line scan cannot follow a variable. yarn and pnpm forms that forward
# arguments without `--` (`yarn lint --quiet`) are not covered either: the repo is npm-only.
CLI_AWK='
function has(p, tool) { return p ~ ("(^|[^A-Za-z0-9_.-])" tool "([^A-Za-z0-9_.-]|$)") }
function after(p, tool) { match(p, "(^|[^A-Za-z0-9_.-])" tool "([^A-Za-z0-9_.-]|$)"); return substr(p, RSTART + RLENGTH - 1) }
function stripc(s,   i, c, q, n) {
  q = ""; n = length(s)
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") { i++; continue }
    if (q != "") { if (c == q) q = ""; continue }
    if (c == "\"" || c == "\047") { q = c; continue }
    if (c == "#" && (i == 1 || substr(s, i - 1, 1) ~ /[ \t]/)) return substr(s, 1, i - 1)
  }
  return s
}
# hit: a long flag from names; mode on = relaxing unless set to false, mode off = relaxing only when set to false.
function hit(p, names, mode,   re, t, a) {
  re = SP "--(" names ")"
  while (match(p, re)) {
    p = substr(p, RSTART + RLENGTH); t = p
    if (t !~ /^([ \t="\047]|$)/) continue
    a = (t ~ /^[ \t]*=?[ \t]*["\047]?false([ \t"\047]|$)/)
    if (mode == "on" ? !a : a) return 1
  }
  return 0
}
# cfg: a config-path flag whose value does not match okre (an inline override, or a file the config scan does not read).
function cfg(p, flags, okre,   re, t, v, q, i) {
  re = SP "(" flags ")"
  while (match(p, re)) {
    p = substr(p, RSTART + RLENGTH); t = p
    if (t !~ /^([ \t=]|$)/) continue
    gsub(/\\/, "", t); sub(/^[ \t]*=?[ \t]*/, "", t)
    q = substr(t, 1, 1)
    if (q == "\"" || q == "\047") { t = substr(t, 2); i = index(t, q); v = (i ? substr(t, 1, i - 1) : t) }
    else { v = t; sub(/[ \t].*$/, "", v); sub(/["\047,]+$/, "", v) }
    if (v == "" || v ~ /^-/) continue
    if (v ~ /^[\/~]/ || v ~ /[$`]/ || v ~ /(^|\/)\.\.(\/|$)/ || v !~ okre) return 1
  }
  return 0
}
# sevoff: a ruleset severity (the text after the first colon of key: value, or of each key at the top level of a JSON object)
# that is off, warn, 0 or 1.
function sevoff(t,   i, c, d, base, v) {
  gsub(/\\/, "", t)
  if (match(t, /[ \t]--?[A-Za-z]/)) t = substr(t, 1, RSTART)
  sub(/^[ \t=]+/, "", t); sub(/^["\047]/, "", t)
  base = (substr(t, 1, 1) == "{" ? 1 : 0)
  for (i = 1; i <= length(t); i++) {
    c = substr(t, i, 1)
    if (c == "{" || c == "[") d++
    else if (c == "}" || c == "]") d--
    else if (c == ":" && d == base) {
      v = substr(t, i + 1)
      if (v ~ /^[ \t]*(\[[ \t]*)?["\047]?(off|warn|[01])([^A-Za-z0-9_.-]|$)/) return 1
    }
  }
  return 0
}
function eslintrule(p,   t) {
  while (match(p, SP "--rule([ \t=]|$)")) {
    t = substr(p, RSTART + RLENGTH); p = t
    if (sevoff(t)) return 1
  }
  return 0
}
function numflag(p, flag, valre,   t) {
  while (match(p, SP flag "([ \t=]|$)")) {
    t = substr(p, RSTART + RLENGTH); p = t
    if (t ~ valre) return 1
  }
  return 0
}
function ruff(s) { return hit(s, "(extend-)?ignore|per-file-ignores|extend-per-file-ignores|exclude|extend-exclude|exit-zero|isolated", "on") || cfg(s, "--config", "^[^= \t]*(ruff|pyproject)\\.toml$") }
function mypy(s) {
  return hit(s, "ignore-missing-imports|allow-[a-z-]+|no-strict-[a-z-]+|no-check-untyped-defs|no-warn-[a-z-]+|no-extra-checks|disable-error-code|implicit-optional|implicit-reexport|exclude|untyped-calls-exclude", "on") || \
    (s ~ (SP "--follow-imports[ \t=]+[\"\047]?(skip|silent)([ \t\"\047]|$)")) || cfg(s, "--config-file", "^[^= \t]*(mypy\\.ini|setup\\.cfg|tox\\.ini|pyproject\\.toml)$")
}
function tsc(s, direct) {
  if (direct && s !~ SP "(-p|--project|-b|--build)([ \t=\"\047]|$)" && s ~ (SP "[^ \t\"\047=-][^ \t\"\047=]*\\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)([ \t\"\047]|$)")) return 1
  return hit(s, "noCheck|skipLibCheck|skipDefaultLibCheck|allowUnreachableCode|allowUnusedLabels|suppressImplicitAnyIndexErrors|suppressExcessPropertyErrors", "on") || \
    hit(s, "strict[A-Za-z]*|noImplicit[A-Za-z]*|noUnused[A-Za-z]*|alwaysStrict|useUnknownInCatchVariables|noUncheckedIndexedAccess|exactOptionalPropertyTypes|noFallthroughCasesInSwitch|noPropertyAccessFromIndexSignature|checkJs", "off") || \
    cfg(s, "-p|--project|-b|--build", "((^|/)(\\.\\.?|[^./= \t]+)/?$)|((tsconfig|jsconfig)[^/= \t]*\\.json$)")
}
function eslint(s, ok) {
  return hit(s, "quiet|ignore-pattern|ignore-path|no-eslintrc|no-config-lookup|no-error-on-unmatched-pattern|pass-on-no-patterns", "on") || eslintrule(s) || \
    numflag(s, "--max-warnings", "^[ \t=]*[\"\047]?(-1|[1-9][0-9]*)([^0-9]|$)") || numflag(s, "--report-unused-disable-directives-severity", "^[ \t=]*[\"\047]?(off|0)([^A-Za-z0-9_-]|$)") || cfg(s, "-c|--config", ok)
}
function prettier(s, ok) {
  return hit(s, "ignore-path|require-pragma|no-error-on-unmatched-pattern|ignore-unknown", "on") || (s ~ (SP "-u([ \t\"\047]|$)")) || cfg(s, "--config", ok)
}
function shellcheck(s) {
  return (s ~ (SP "-[A-Za-z]*e([ \t\"\047]|SC[0-9]|$)")) || (s ~ (SP "-[A-Za-z]*i([ \t\"\047]|SC[0-9]|$)")) || hit(s, "exclude|include", "on") || \
    (s ~ (SP "(-[A-Za-z]*S[ \t]*|--severity[ \t=]+)[\"\047]?error([ \t\"\047]|$)"))
}
function relaxed(p,   js, dd, s, ok) {
  js = (p ~ /(^|[^A-Za-z0-9_.-])(npm|npx|yarn|pnpm|bunx)([^A-Za-z0-9_.-]|$)/)
  dd = ""
  if (js && match(p, /(^|[ \t])--([ \t]|$)/)) dd = substr(p, RSTART + RLENGTH)
  if (match(p, /SHELLCHECK_OPTS(\+?=|:[ \t])/) && shellcheck(substr(p, RSTART + RLENGTH))) return 1
  if (has(p, "ruff") && ruff(after(p, "ruff"))) return 1
  if (has(p, "mypy") && mypy(after(p, "mypy"))) return 1
  if (has(p, "shellcheck") && shellcheck(after(p, "shellcheck"))) return 1
  if ((has(p, "tsc") || dd != "") && tsc((has(p, "tsc") ? after(p, "tsc") : "") " " dd, has(p, "tsc"))) return 1
  if (has(p, "eslint")) ok = "((^|/)[^= \t]*(eslint\\.config\\.[A-Za-z]+|eslintrc[^/= \t]*|biome\\.json[^/= \t]*)$)"
  else if (has(p, "prettier")) ok = "((^|/)[^= \t]*(prettierrc[^/= \t]*|prettier\\.config\\.[A-Za-z]+)$)"
  else ok = "((^|/)[^= \t]*(eslint\\.config\\.[A-Za-z]+|eslintrc[^/= \t]*|biome\\.json[^/= \t]*|prettierrc[^/= \t]*|prettier\\.config\\.[A-Za-z]+)$)"
  if ((has(p, "eslint") || dd != "") && eslint((has(p, "eslint") ? after(p, "eslint") : "") " " dd, ok)) return 1
  if ((has(p, "prettier") || dd != "") && prettier((has(p, "prettier") ? after(p, "prettier") : "") " " dd, ok)) return 1
  return 0
}
function flush(   n, i, parts, c) {
  if (cur == "") return
  if (cur !~ JUSTRE) {
    c = stripc(cur)
    n = split(c, parts, /[;&|]+/)
    for (i = 1; i <= n; i++) if (relaxed(parts[i])) { printf "%s:%d:%s\n", F, start, cur; break }
  }
  cur = ""
}
BEGIN { JUSTRE = "justified:[ \t]*[^ \t*/]"; SP = "(^|[ \t])[\"\047]?"; cur = ""; cont = 0 }
{
  line = $0; sub(/\r$/, "", line)
  if (!cont && line ~ /^[ \t]*#/) next
  if (!cont) start = NR
  cont = (line ~ /\\[ \t]*$/)
  if (cont) sub(/\\[ \t]*$/, "", line)
  cur = (cur == "" ? "" : cur " ") line
  if (!cont) flush()
}
END { flush() }'
cliflags() { # cliflags <pathspec>...
  local f
  while IFS= read -r f; do
    if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null | awk -v F="$f" "$CLI_AWK"
    else awk -v F="$f" "$CLI_AWK" "$f" 2>/dev/null; fi
  done < <(git ls-files -- "$@" "${EXCL[@]}") | sed 's/^/guard: unjustified CLI flag: /'
}
out=$(cliflags '*.sh' '.githooks/*' '.github/workflows/*' '*package.json')
[ -n "$out" ] && { echo "$out"; fail=1; }

# 3. Baselines (no escape hatch): by name, by wiring and by content, any file type.
out=$("${LS[@]}" | grep -iE 'baseline')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline file: /'; fail=1; }
# Formatter and linter ignore files cannot carry a same-line justification, so they are refused outright (ask the owner).
out=$("${LS[@]}" | grep -E '(^|/)\.(prettier|eslint|stylelint|dprint)ignore$')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: ignore file: /'; fail=1; }
out=$(gg 'baseline *(=|\(|\.set)|<SmellBaseline>|<issues format=' -- "${EXCL[@]}")
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline wiring: /'; fail=1; }

# 5. File size (owner decision, #15 comment 6974778901: Git LFS is not adopted, so big binaries stay out of the repo).
# An added or changed file over 1 MB fails, and so does a *.png over 300 KB outside docs/product/wireframes/. Binary units;
# a file exactly at a limit passes. Deleted files are ignored. No escape hatch: shrink the file, keep it out of the repo, or ask the owner.
MAX_FILE=$((1024 * 1024))
MAX_PNG=$((300 * 1024))
sizecheck() { # sizecheck <git diff args>...: `git diff --raw` lists new modes and blob ids, so sizes come from the changed side only
  local meta f nm nsha size lim why
  while IFS= read -r -d '' meta && IFS= read -r -d '' f; do
    read -r _ nm _ nsha _ <<<"$meta"
    [ "$nm" = 160000 ] && continue # submodule pointer, not a file
    size=$(git cat-file -s "$nsha") || { bad "cannot read the size of $f"; continue; }
    lim=$MAX_FILE; why="1 MB"
    case "$f" in # git paths are case-sensitive: only the extension is matched case-insensitively (no ${f,,}: macOS bash 3.2)
      docs/product/wireframes/*) ;;
      *.[pP][nN][gG]) lim=$MAX_PNG; why="300 KB for a PNG outside docs/product/wireframes/" ;;
    esac
    [ "$size" -gt "$lim" ] && bad "file too large: $f is $size bytes (limit $lim bytes: $why). Git LFS is not adopted (docs/tasks.toml, M6-O4); shrink it, keep it out of the repo, or ask the owner"
  done < <(git diff --raw -z --no-abbrev --no-renames --diff-filter=AMT "$@")
}

if [ "$STAGED" = 1 ]; then sizecheck --cached; fi

if [ "$STAGED" = 0 ]; then
  # 4. Diff checks need the base ref.
  MB=""
  git rev-parse --verify -q "$BASE" >/dev/null && MB=$(git merge-base "$BASE" HEAD 2>/dev/null)
  if [ -z "$MB" ]; then
    if [ "${CI:-}" = true ]; then bad "no base/merge-base '$BASE' (CI checkout needs fetch-depth: 0)"
    else echo "guard: note: base '$BASE' not found, skipped diff-based checks"; fi
  else
    sizecheck "$MB" HEAD
    DSPEC=(. ':!docs' ':!handoff' ':!scripts/guards.sh' ':!scripts/hooks/test_guards_sh.py' ':!*package-lock.json')
    # Lowered or removed thresholds and severities.
    git diff -U0 "$MB" HEAD -- "${DSPEC[@]}" | awk '
      function norm(l,   n) { sub(/^[-+]/, "", l); gsub(/^[ \t]+|[ \t]+$/, "", l); return l }
      function num(l) { if (match(l, /[0-9]+/)) return substr(l, RSTART, RLENGTH) + 0; return -1 }
      function testpath(p) {
        return (p ~ /(^|\/)test_[^\/]*\.py$|_test\.py$/ || p ~ /^[ab]\/([^\/]+|core\/[^\/]+)\/src\/(test|androidTest|testFixtures|[a-z]+Test)\/.*\.(kt|java)$/)
      }
      /^diff --git/ {
        file = $3
        istest = (NF == 4 && testpath($3) && testpath($4))   # old AND new path must be test files
        next
      }
      /^(---|\+\+\+)/ { next }
      {
        # A test function NAME is not a check setting (owner decision, #15). Only in test files, the declared name
        # of `def test...(` / `fun test...(` / fun `name`( is dropped from the line. The keyword scan ignores the
        # name only for a bare declaration: an empty parameter list (Python: only self or cls), at most a plain
        # identifier return type, and nothing else. Anything else on the line keeps the whole line in scope; its key
        # always uses the full line, and the name-free line is used only for the number comparison.
        body = $0; kw = $0; decl = 0
        if (istest) {
          if (match(body, /^[-+][ \t]*(async[ \t]+)?def[ \t]+test[A-Za-z0-9_]*[ \t]*\(/)) {
            decl = 1; rest = substr(body, RLENGTH + 1); bare = (rest ~ /^[ \t]*((self|cls)[ \t]*)?\)[ \t]*(->[ \t]*[A-Za-z_][A-Za-z0-9_.]*[ \t]*)?:[ \t]*\r?$/)
          } else if (match(body, /^[-+][ \t]*(@[A-Za-z]+[ \t]+)*fun[ \t]+(test[A-Za-z0-9_]*|`[^`]*`)[ \t]*\(/)) {
            decl = 1; rest = substr(body, RLENGTH + 1); bare = (rest ~ /^[ \t]*\)[ \t]*(:[ \t]*[A-Za-z_][A-Za-z0-9_]*[ \t]*)?\{?[ \t]*\}?[ \t]*\r?$/)
          }
        }
        if (decl) { body = substr(body, 1, 1) "test(" rest; if (bare) kw = body }
        # The word `threshold` in prose is not a check setting (owner decision, #15; PR 135 R1-R3). Prose = a letter-word
        # and spaces on each side (`gate or threshold changes`) on a line with no digit, and either the file is markdown
        # or it is a .py file and the line is made of nothing but double-quoted string literals (optional r/b/u prefix,
        # no backslash, `$`, `{` or `}` inside) and punctuation `( ) [ ] { } , ;`. Shell and config files, f-strings,
        # code, comments, keys, assignments, calls, config values and every other keyword on the line still count; a
        # stray `"`, a char literal or an escape leaves letters or symbols outside the literals.
        lit = $0; gsub(/[rRbBuU]?"[^"\\${}]*"/, "", lit)
        if ($0 !~ /[0-9]/ && (file ~ /\.md$/ || (file ~ /\.py$/ && lit ~ /^[-+][][ \t(){},;]*$/))) {
          while (match(kw, /[A-Za-z][ \t]+threshold[ \t]+[A-Za-z]/)) kw = substr(kw, 1, RSTART) " prose " substr(kw, RSTART + RLENGTH - 1)
        }
      }
      kw ~ /(minBound|mutationThreshold|threshold|failOnNoDiscoveredTests|useJUnitPlatform|error *\+?=|fatal *\+?=|warningsAsErrors|maxIssues|failOnSeverity)/ {
        l = norm($0); key = file "|" l; gsub(/[0-9]+/, "N", key); n = num(norm(body))
        if (substr($0, 1, 1) == "-") { rem[key] = l; remn[key] = n } else { add[key] = l; addn[key] = n }
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
