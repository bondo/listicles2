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
[ "$STAGED" = 1 ] && LS=(git diff --cached --name-only --no-renames --diff-filter=AMT) # added, modified, type-changed; --no-renames so a rename or copy is an add whatever diff.renames says

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
# Owner decision (#46): the reason after `justified:` needs at least 3 words of letters (a word is a run of 2 or more ASCII letters,
# so "-", "x", "ok" and "two words" fail); reviewers still judge the content. just() is awk, shared by the line filter and entrycheck.
# Only the reason counts: it ends at a closing `*/` or `-->` and at a following comment opener (` # word`, ` // word`), so code or a
# directive after it (`/* justified: x */ // eslint-disable-line no-console`) adds no words. `#46` and `http://` do not end it.
JUSTFN='function just(l,   i, r, n) { i = index(l, "justified:"); if (!i) return 0; r = substr(l, i + 10); n = 0
  i = index(r, "*/"); if (i) r = substr(r, 1, i - 1); i = index(r, "-->"); if (i) r = substr(r, 1, i - 1)
  if (match(r, /[ \t](#|\/\/)[ \t]*[A-Za-z]/)) r = substr(r, 1, RSTART)
  while (match(r, /[A-Za-z][A-Za-z]+/)) { n++; r = substr(r, RSTART + RLENGTH) } return n >= 3 }'
unjust() { LC_ALL=C awk "$JUSTFN"' !just($0)'; } # keeps the lines that have no valid justification
out=$(gg "$PAT" -- "${EXCL[@]}" | unjust)
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }

# 2b. Relaxed settings in the linter config files themselves (same justification rule). Each pattern only applies to the files
# named with it, so ordinary code and data (`ignore = x`, "off") never match.
# The checks above are line by line, so a justification on a TOML table header or an array opener would waive every entry after it.
# entrycheck therefore reads the config files itself and requires the justification on every entry line of a relaxing multi-line
# table (per-file-ignores), array/object (ignore = [, exclude_lines = [, ignores: [) or INI continuation (ignore =<newline>  E501),
# and on the first element of an ESLint rule array that sets off/warn/0/1, and on every `- entry` of an actionlint `ignore:` block list.
ENTRY_AWK='
function strip(l) { sub(/[ \t]*(#|\/\/).*$/, "", l); return l }
function blank(l) { gsub(/"[^"]*"/, "\"\"", l); gsub(/\047[^\047]*\047/, "\047\047", l); return l }
function nest(l,   t, o) { t = l; gsub(/[^[({]/, "", t); o = length(t); t = l; gsub(/[^])}]/, "", t); return o - length(t) }
function check() { if (!just(line)) printf "%s:%d:%s\n", F, NR, line }
function ind(l) { sub(/[^ \t].*$/, "", l); return length(l) }
BEGIN { ini = (F ~ /(\.ini|\.cfg|\.flake8|\.coveragerc)$/); es = (F ~ /eslint/); yml = (F ~ /actionlint\.ya?ml$/) }
{
  line = $0; nc = strip(line); c = blank(nc); lc = tolower(nc)
  if (c ~ /^[ \t]*$/) next
  closer = (c ~ /^[ \t]*[])},;]*[ \t]*$/)
  if (mode == 4) { if (ind(line) > yi || (ind(line) == yi && c ~ /^[ \t]*-/)) { check(); next } mode = 0 }
  if (yml && line ~ /(^[ \t]*(-[ \t]+)?|[{,][ \t]*)"[^"]*\\[^"]*"[ \t]*:/) { printf "%s:%d:%s\n", F, NR, line; next }  # an escaped key may spell ignore
  if (yml && lc ~ /ignore["\047]?[ \t]*:[^#]*[][ \t,]\*[A-Za-z0-9_]/) { printf "%s:%d:%s\n", F, NR, line; next }  # an alias: 2b cannot follow it
  if (yml && lc ~ /^[ \t]*-?[ \t]*["\047]?ignore["\047]?[ \t]*:([ \t]+(&|!)[^ \t]*)*[ \t]*$/) { mode = 4; yi = ind(line); next }  # block list (anchor, tag)
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
    if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null | LC_ALL=C awk -v F="$f" "$JUSTFN$ENTRY_AWK"
    else LC_ALL=C awk -v F="$f" "$JUSTFN$ENTRY_AWK" "$f" 2>/dev/null; fi
  done < <(git ls-files -- "$@" "${EXCL[@]}") | sed 's/^/guard: unjustified suppression: /'
}
cfgcheck() { # cfgcheck <pattern> <pathspec>...
  local pat="$1" o; shift
  o=$(gg "$pat" -- "$@" "${EXCL[@]}" | unjust)
  [ -n "$o" ] && echo "$o" | sed 's/^/guard: unjustified suppression: /'
  entrycheck "$@"
  return 0
}
# tsconfig: a base named by "extends" is only scanned when it matches *tsconfig*.json, so any other base needs a justification.
extcheck() {
  local ok='"extends"[[:space:]]*:[[:space:]]*("[^"]*(tsconfig|jsconfig)[^"]*"[[:space:]]*(,|$|//)|'
  ok+='\[[[:space:]]*"[^"]*(tsconfig|jsconfig)[^"]*"([[:space:]]*,[[:space:]]*"[^"]*(tsconfig|jsconfig)[^"]*")*[[:space:]]*\])'
  local o
  o=$(gg '"extends"[[:space:]]*:' -- '*tsconfig*.json' '*jsconfig*.json' "${EXCL[@]}" | grep -vE "$ok" | unjust)
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
TSPAT+='"(allowUnreachableCode|allowUnusedLabels|suppressImplicitAnyIndexErrors|suppressExcessPropertyErrors|noCheck|skipLibCheck)"[[:space:]]*:[[:space:]]*true'
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
  cfgcheck 'requirePragma["'"'"']?[[:space:]]*[:=][[:space:]]*true|ignore-?[Pp]ath' '*prettierrc*' '*prettier.config.*'
  # actionlint: `ignore:` patterns drop its errors (issue 164 item 1)
  cfgcheck '(^|[^A-Za-z0-9_-])["'"'"']?ignore["'"'"']?[[:space:]]*:' '*.github/actionlint.yaml' '*.github/actionlint.yml')  # a leading * (git ls-files drops a literal path next to :!)
[ -n "$out" ] && { echo "$out"; fail=1; }

# 2c. Command-line flags on tool invocation lines (issues 45 and 177): ruff, mypy, tsc, ESLint, Prettier, shellcheck and actionlint, in shell
# scripts, git hooks, CI workflows, composite actions, Makefiles, pre-commit config and package.json. Per-tool ALLOWLIST (owner decision, #15):
# a flag passes only when CLI_ALLOW below lists it for that tool (ruff: for that subcommand) and its value passes the check of its kind.
# Any other flag, listed or not by anyone before, fails unless the logical line has one `justified: <reason>` (3 words, just() above), which waives
# every command on the line. A backslash continuation is one logical line; it loses its unquoted trailing ` # comment` and is split at ; & | so
# a flag only counts for the tool in its own command; only the text after the tool name is read (`grep -i shellcheck` has no flag), and a bare
# `--` ends the flags. A tool named as the thing being installed (`pip install ruff --upgrade`, `npm i -D eslint`, `cargo install`) is not run, so datacmd skips it.
# For npm and npx (and yarn, pnpm, bun and bunx when they use `--`) the JS tools also see what follows a bare `--` (`npm run lint -- --quiet`): a flag
# there passes when ANY of eslint, prettier and tsc lists it, because the script that runs is not known. Only an npm form whose script is
# known to end in a test runner (ddrun, pkgscripts below; issue 164 item 3) skips that check, so `npm test -- --ci` passes when every tracked
# `test` script is a plain `jest ...` (its runner options are check 1 on command lines: runopt below, tasks M1-71, M1-81); in every other case the check is as before (fail closed). The options of npm itself never count. Flags may be quoted, shellcheck short options may be combined (-xS warning),
# tsc names are read case-insensitively (as tsc does), mypy and shellcheck accept unique prefixes of long options so a proper prefix of a
# listed option counts as that option (a prefix that is ambiguous is an error in the tool itself), and SHELLCHECK_OPTS counts as
# `SHELLCHECK_OPTS=`, `+=` or a YAML `SHELLCHECK_OPTS: value`.
# Kinds: f = plain flag; v = takes a value, any; c = takes a config path that must be a file the config scan (2b) reads, not an inline
# `key = value`, an absolute, `~` or `..` path or one built from `$` or backticks (they may be generated at run time); nf = switch that
# may not be set to false; z = value must be 0; e = value must be error or 2; s = shellcheck severity, not error; fi = mypy follow-imports,
# normal or error; fm = an ESLint built-in formatter name (stylish, json, json-with-metadata, html); o = optional value attached to the flag (shellcheck colour: always, never or auto); r = ESLint --rule, no severity of off, warn, 0 or 1; n = the last part of the value must be the flag name (`-shellcheck=$d/shellcheck`); an empty value or a stub program disables the integration.
# Beyond the allowlist: `tsc` with a source file argument and no -p/-b ignores tsconfig.json, so it fails; every project argument of `tsc -b` is
# checked; a mypy `@argfile` fails; an empty quoted config (`--config-file ""`) disables the config, so it fails.
# ESLint --suppress-all, --suppress-rule, --suppressions-location and --pass-on-unpruned-suppressions write or read a suppressions file,
# which is a baseline: no `justified:` waives them (check 3 has no escape hatch either).
# In YAML the args-like keys of a step or hook (`with: args:`, `eslint_flags:`, pre-commit `args:`) are flags of the tool its `uses:`, `id:` or
# `entry:` names (issue 164 item 2, yamlitem below). A YAML value over several lines (`run: >`, a plain or quoted scalar, a flow
# collection) is checked once more as one line (YFOLD_AWK below). Not covered: flags held in
# shell variables (`FLAGS="--ignore E501"; ruff check $FLAGS`), because a line scan cannot follow a variable, tools run from Python (subprocess),
# and yarn, pnpm and bun forms that forward arguments without `--` (`yarn lint --quiet`; the repo is npm-only). Keep the list small: a flag
# is added only with a reason a reviewer can check, in scripts/hooks/test_guards_cli_flags.py too (docs/guards-known-gaps.md has the rationale).
CLI_ALLOW='
ruff --config c a config file that 2b reads, so its settings are reviewed there
ruff --no-cache f the cache never changes a result
ruff --output-format v only changes how findings are printed
ruff --version f prints the version
ruff:check --extend-select v adds rules to the selection and never removes one
ruff:format --check f reports unformatted files and writes nothing
ruff:format --diff f like --check, printing the diff
mypy --config-file c a config file that 2b reads
mypy --follow-imports fi only normal or error: skip and silent hide errors in imported code
mypy --strict f switches every strict check on
mypy --check-untyped-defs f switches a check on
mypy --strict-equality f switches a check on
mypy --strict-bytes f switches a check on
mypy --extra-checks f switches a check on
mypy --no-implicit-reexport f stricter than the default
mypy --no-implicit-optional f stricter than the default
mypy --warn-* f every --warn- option switches a warning on (the --no-warn- ones relax and stay off the list)
mypy --disallow-* f every --disallow- option switches a check on
mypy --version f prints the version
tsc --noEmit f type-checks and writes nothing
tsc --project c the config file tsc reads
tsc -p c the config file tsc reads
tsc --build f build mode, every project argument is checked by tscbuild
tsc -b f build mode, every project argument is checked by tscbuild
tsc --verbose f only changes the output
tsc --force f rebuilds everything, skipping nothing
tsc --pretty f only changes the output
tsc --outDir v where build output goes
tsc --outFile v where build output goes
tsc --version f prints the version
tsc -v f prints the version
tsc --strict* nf every --strict option switches a check on, unless it is set to false
tsc --noImplicitAny nf switches a check on, unless it is set to false
tsc --noImplicitThis nf switches a check on, unless it is set to false
tsc --noImplicitReturns nf switches a check on, unless it is set to false
tsc --noImplicitOverride nf switches a check on, unless it is set to false
tsc --noUnused* nf switches a check on, unless it is set to false
tsc --alwaysStrict nf switches a check on, unless it is set to false
tsc --useUnknownInCatchVariables nf switches a check on, unless it is set to false
tsc --noUncheckedIndexedAccess nf switches a check on, unless it is set to false
tsc --exactOptionalPropertyTypes nf switches a check on, unless it is set to false
tsc --noFallthroughCasesInSwitch nf switches a check on, unless it is set to false
tsc --noPropertyAccessFromIndexSignature nf switches a check on, unless it is set to false
tsc --checkJs nf switches a check on, unless it is set to false
eslint --max-warnings z only 0 makes a warning fail the run
eslint --config c a config file that 2b reads
eslint -c c a config file that 2b reads
eslint --rule r a rule may be set to error, never to off, warn, 0 or 1
eslint --report-unused-disable-directives f switches a check on
eslint --report-unused-disable-directives-severity e only error or 2 keeps unused directives failing
eslint --no-inline-config f makes inline directives inert
eslint --prune-suppressions f only removes entries from a suppressions file (check 3 refuses the file itself)
eslint --format fm only a built-in formatter: a formatter module is code and can exit 0
eslint -f fm only a built-in formatter: a formatter module is code and can exit 0
eslint --color f only changes the output
eslint --no-color f only changes the output
eslint --version f prints the version
prettier --check f reports unformatted files and writes nothing
prettier --write f formats in place; like a bare run it never fails on formatting, which no flag check can see
prettier --list-different f reports unformatted files
prettier --config c a config file that 2b reads
prettier --log-level v only changes the output
prettier --version f prints the version
shellcheck -S s a severity of warning, info or style, never error
shellcheck --severity s a severity of warning, info or style, never error
shellcheck -x f follows sourced files, so more is checked
shellcheck --external-sources f follows sourced files, so more is checked
shellcheck -a f checks sourced files too
shellcheck --check-sourced f checks sourced files too
shellcheck -o v enables optional checks
shellcheck --enable v enables optional checks
shellcheck -C o only changes the colour of the output
shellcheck --color o only changes the colour of the output
shellcheck -f v only changes how findings are printed
shellcheck --format v only changes how findings are printed
shellcheck -P v where sourced files are looked up
shellcheck --source-path v where sourced files are looked up
shellcheck --norc f ignores any .shellcheckrc, and none may exist (scripts/test_lint_workflows.py)
shellcheck --version f prints the version
actionlint -shellcheck n a path whose last part is shellcheck; an empty value or another program can switch shellcheck off
actionlint -pyflakes n a path whose last part is pyflakes; an empty value or another program can switch pyflakes off
actionlint -color f only changes the output
actionlint -no-color f only changes the output
actionlint -oneline f only changes the output
actionlint -verbose f only changes the output
actionlint -format v only changes how findings are printed
actionlint -version f prints the version
'
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
# hit: a long flag from names, relaxing unless set to false (only the ESLint suppressions baseline uses it).
function hit(p, names,   re, t) {
  re = SP "--(" names ")"
  while (match(p, re)) {
    p = substr(p, RSTART + RLENGTH); t = p
    if (t !~ /^([ \t="\047]|$)/) continue
    if (t !~ /^[ \t]*=?[ \t]*["\047]?false([ \t"\047]|$)/) return 1
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
    if (v == "" && (q == "\"" || q == "\047")) return 1
    if (v == "" || v ~ /^-/) continue
    if (badpath(v, okre)) return 1
  }
  return 0
}
function badpath(v, okre) { return (v ~ /^[\/~]/ || v ~ /[$`]/ || v ~ /(^|\/)\.\.(\/|$)/ || v !~ okre) }
# pre: the prefixes of a long option name from m characters up, as a regex alternation (the cfg flags of mypy accept unique prefixes).
function pre(n, m,   i, r) { for (i = m; i <= length(n); i++) r = r (r == "" ? "" : "|") substr(n, 1, i); return r }
# tscbuild: every project argument of tsc -b / --build (any number, in any position among flags) must be a scanned tsconfig. A redirection
# and its target are not projects (`tsc -b > build.log`).
function tscbuild(p,   t, n, w, i) {
  while (match(p, SP "(-b|--build)([ \t=]|$)")) {
    t = substr(p, RSTART + RLENGTH); p = t
    n = split(t, w, /[ \t]+/)
    for (i = 1; i <= n; i++) {
      if (w[i] ~ /^[0-9]*[<>]/) { if (w[i] ~ /^[0-9]*(>>?|<)$/) i++; continue }
      gsub(/["\047,]/, "", w[i]); if (w[i] != "" && w[i] !~ /^-/ && badpath(w[i], TSOK)) return 1
    }
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
# look: the kind of flag nm for the first of the tools (space separated) that lists it, for subcommand sb or for any; "" when none does.
function look(tools, sb, nm,   n, tl, i, t, j) {
  n = split(tools, tl, " ")
  for (i = 1; i <= n; i++) {
    t = tl[i]
    if ((t, sb, nm) in K) return K[t, sb, nm]
    if ((t, "", nm) in K) return K[t, "", nm]
    for (j = 1; j <= NG[t]; j++) if ((GS[t, j] == "" || GS[t, j] == sb) && index(nm, GP[t, j]) == 1) return GK[t, j]
  }
  return ""
}
# abbr: mypy and shellcheck take a unique prefix of a long option; one that is a proper prefix of a listed option is that option.
function abbr(tool, nm,   m, n, f, i) {
  m = (tool == "mypy" ? 5 : (tool == "shellcheck" ? 4 : 0))
  if (!m || nm !~ /^--/ || length(nm) < m) return ""
  n = split(EX[tool], f, " ")
  for (i = 1; i <= n; i++) if (length(nm) < length(f[i]) && index(f[i], nm) == 1) return K[tool, "", f[i]]
  return ""
}
function unq(v) { gsub(/^["\047]+|["\047,;)]+$/, "", v); return v }
# scan: 1 when a flag in s (the text after the tool name) is not allowed for one of the tools, or its value fails the check of its kind.
function scan(s, tools, direct,   n, w, i, j, t, nm, eq, v, k, sb, c, body, rest, hp, one) {
  n = split(s, w, /[ \t]+/); one = (index(tools, " ") == 0); sb = ""
  if (tools == "ruff") for (i = 1; i <= n; i++) { t = w[i]; gsub(/^["\047]+|["\047]+$/, "", t); if (t ~ RUFFSUB) { sb = t; break } }
  hp = (s ~ (SP "(-p|--project|-b|--build)([ \t=\"\047]|$)"))
  for (i = 1; i <= n; i++) {
    t = w[i]; sub(/^["\047]+/, "", t)
    if (t == "") continue
    if (t == "--") break
    if (index(tools, "tsc") && substr(t, 1, 1) == "@") return 1
    if (t == "-" || substr(t, 1, 1) != "-") {
      v = t; sub(/["\047,]+$/, "", v)
      if (direct && !hp && v !~ /=/ && v ~ SRCRE) return 1
      continue
    }
    if (tools == "shellcheck" && t ~ /^-[^-]/) {
      body = t; sub(/^-/, "", body); sub(/["\047,;]+$/, "", body)
      for (j = 1; j <= length(body); j++) {
        c = substr(body, j, 1); k = look(tools, "", "-" c)
        if (k == "") return 1
        if (k == "f") continue
        rest = substr(body, j + 1)
        if (k == "o") { if (rest != "" && rest !~ COLOROK) return 1; break }
        if (rest == "") { i++; rest = w[i] }
        if (k == "s" && unq(rest) !~ SEVOK) return 1
        break
      }
      continue
    }
    nm = t; eq = 0; v = ""
    if (index(nm, "=")) { eq = 1; v = substr(nm, index(nm, "=") + 1); nm = substr(nm, 1, index(nm, "=") - 1) } else sub(/["\047,;]+$/, "", nm)
    if (index(tools, "tsc")) nm = tolower(nm)
    if (tools == "actionlint") sub(/^--/, "-", nm)
    k = look(tools, sb, nm)
    if (k == "" && one) k = abbr(tools, nm)
    if (k == "") return 1
    if (k == "f") continue
    if (k == "o") { if (eq && unq(v) !~ COLOROK) return 1; continue }
    if (k == "nf") {
      if (!eq) { v = tolower(unq(w[i + 1])); if (v == "true" || v == "false") i++; else v = "" } else v = tolower(unq(v))
      if (v == "false") return 1
      continue
    }
    if (!eq) { i++; v = w[i] }
    v = unq(v)
    if (k == "z" && v != "0") return 1
    if (k == "fm" && v !~ /^(stylish|json|json-with-metadata|html)$/) return 1
    if (k == "e" && v !~ /^(error|2)$/) return 1
    if (k == "s" && v !~ SEVOK) return 1
    if (k == "fi" && v !~ /^(normal|error)$/) return 1
    if (k == "n" && v !~ ("(^|/)" substr(nm, 2) "$")) return 1
  }
  return 0
}
function eslintbase(s) { return hit(s, "suppress-all|suppress-rule|suppressions-location|pass-on-unpruned-suppressions") }
function ddseg(p) { if (p ~ /(^|[^A-Za-z0-9_.-])(npm|npx|yarn|pnpm|bun|bunx)([^A-Za-z0-9_.-]|$)/ && match(p, /(^|[ \t])--([ \t]|$)/)) return substr(p, RSTART + RLENGTH); return "" }
# ddrun: 1 when the `--` tail of p reaches a test runner, never a linter (PR 309 ruling 7084379032): a bare npm is the first word (after
# a YAML `- key:` or a package.json key), then only -s/--silent/-q/--quiet/--if-present/--ignore-scripts, the verb test, t or tst (script
# `test`) or run, rum, urn or run-script with a name, and nothing else up to the `--`; every tracked package.json definition of the script
# must pass plainrun, and no package.json may be unknown.
function ddrun(p,   n, w, i, a, v) {
  if (NPMU) return 0
  match(p, /(^|[ \t])--([ \t]|$)/); n = split(substr(p, 1, RSTART), w, /[ \t]+/)
  for (i = 1; i <= n && (w[i] == "" || (F ~ /(\.ya?ml|package\.json)$/ && (w[i] == "-" || w[i] ~ /:$/))); i++) ;
  a = w[i]; if (F ~ /package\.json$/) sub(/^"/, "", a)
  if (a != "npm") return 0
  for (i++; i <= n && w[i] ~ NPMBOOL; i++) ;
  v = w[i]
  if (v ~ /^(run|rum|urn|run-script)$/) { for (i++; i <= n && w[i] ~ NPMBOOL; i++) ; v = w[i] } else if (v ~ /^(test|t|tst)$/) v = "test"; else return 0
  for (i++; i <= n; i++) if (w[i] != "" && w[i] !~ NPMBOOL) return 0
  if (v == "" || !(v in NS)) return 0
  for (i = 1; i <= NS[v]; i++) if (!plainrun(NC[v, i])) return 0
  DDN = v; return 1
}
# plainrun: script c (npm appends the tail to it) is one plain `[npx] <runner> <words>` and nothing else: no command before it (one could
# redefine the runner: a function, PATH=, a copy over its file), no separator, quote, `$`, backtick, bracket, redirection, `#`, `~` or `\`.
function plainrun(c) { return (c ~ RUNRE) }
# Check 1 on command lines (task M1-71, owner decision #15 comment 7092471489): jest, vitest and mocha options that rewrite or skip tests
# (snapshot update, --passWithNoTests), filter them (-t, path patterns, positional path filters, mocha --grep and kin) or run only changed
# ones (jest -o, --changedSince, --findRelatedTests, vitest --changed) fail with no escape hatch, like check 1. --shard passes.
# Long names are read as yargs and cac read them (kebab-case is camelCase) and case-insensitively; they are denied for every runner
# (RDL). Short options differ per runner (RDS: jest -t filters, mocha -t is --timeout) and may be grouped (-iu). Positional words are
# path filters after jest and after vitest (but its first one may be run, watch or dev) when the runner is the command (cmdat), and in
# an npm `--` tail that ddrun resolves to jest or mocha (a mocha spec there may replace the configured one). The value of an option in
# RVL or RVS is no positional word; the value of any other option is (fail closed: write it with =). A runner word that is not the command
# (`firebase emulators:exec "jest -u"`) has its options read, not its positional words. Task M1-81 (#15 comment 7102820038) adds playwright
# and cypress, read only as `playwright test` and `cypress run`, with the commander grouping and their own value-taking names; positional
# words after the subcommand fail for both, and so do those of a resolved tail. An unresolved tail is read with the long names
# only, because its short options are ambiguous (-t is tsc --target): 2c keeps them, waivable as before.
function rclean(t) { sub(/^["\047\\]+/, "", t); sub(/["\047\\,;]+$/, "", t); return t }
# rscan: 1 when the words of s hold a denied option of the runners R (rtab; none: an unresolved tail, long names only), pos makes
# positional words deny (fw: a first word that is not one), dl adds denied long names. A group (-w2u) is read as yargs-parser reads it
# (R1-01): every character is a flag, digits too, until one takes the rest as its value: the rest starts with `=`, is a number (a letter
# only), or starts with a character that is no word character; mri (vitest, and runners with mixed parsers) only stops at `=`; commander
# (playwright, cypress) stops at a value letter. A word is skipped only as a negative number. A one-letter long option (--u) is that short
# option (R1-02). The value of -c, --config, and cypress -e, --env is checked by rval. In a package.json the command ends with its JSON
# value (jsend).
function jsend(x) { return JSF && x ~ /(^|[^\\])"[],}]*$/ }
# rtab: the tables of the runners R (blank-separated) joined: denied and value-taking short letters (TDS, TVS) and long names (TDL, TVL),
# the value checks (TCK) and the parser (TMR: y yargs, m mri, c commander; two different ones read as mri, the strictest).
function rtab(R,   n, x, i) {
  TDS = TVS = TDL = TVL = TCK = TMR = ""
  if (!(n = split(R, x, " "))) { TVL = RVL; TCK = "j"; TMR = "y"; return }
  for (i = 1; i <= n; i++) {
    TDS = TDS RDS[x[i]]; TVS = TVS RVS[x[i]]; TDL = TDL RDX[x[i]]; TVL = TVL ((x[i] in RVX) ? RVX[x[i]] : RVL); TCK = TCK RCK[x[i]]
    TMR = (TMR == "" || TMR == RM[x[i]]) ? RM[x[i]] : "m"
  }
}
# rval: 1 when the value v of a config (isc) or env (ise) option is denied: jest inline JSON (no config scan reads it), a playwright
# config that is no `*.config.{ts,js,mts,mjs,cts,cjs}` file (a test directory narrows testDir), a cypress config naming specPattern or
# excludeSpecPattern, a cypress env naming a @cypress/grep key (grep, grepTags, grepInvert, ...). Task M1-81, #15 comment 7102820038.
function rval(isc, ise, v) {
  v = rclean(v); if (v == "") return 0
  if (isc && index(TCK, "j") && v ~ /^\{/) return 1
  if (isc && index(TCK, "p") && v !~ /(^|\/)[^\/]*\.config\.[cm]?[jt]s$/) return 1
  v = tolower(v)
  if (isc && index(TCK, "y") && index(v, "specpattern")) return 1
  return ise && index(TCK, "y") && v ~ /(^|[^a-z0-9_])grep[a-z]*[\\"\047]*[ \t]*[=:]/
}
# rqopen: 1 when word x leaves a quote open or ends in an escaped blank, so rscan joins it with the next word (`--project "Mobile
# Chrome"`, PR 358 R0-01). In a package.json only an escaped `\"` and `\047` count: a bare `"` delimits the JSON value.
function rqopen(x,   i, c, q, n) {
  n = length(x); q = ""
  for (i = 1; i <= n; i++) {
    c = substr(x, i, 1)
    if (c == "\\" && q != "\047") { if (i == n && !JSF) return 1; c = substr(x, ++i, 1); if (!JSF || c != "\"") continue }
    else if (JSF && c == "\"") continue
    if (q == "") { if (c == "\"" || c == "\047") q = c } else if (c == q) q = ""
  }
  return q != ""
}
# rsub: the words of s after the test subcommand of runner a (RSUB: playwright `test`, cypress `run`), or a newline when s does not
# start with it (another subcommand, or a path or package that names the runner: `e2e/playwright -c x`, PR 358 R0-02).
function rsub(s, a,   w1) { w1 = s; sub(/^[ \t]+/, "", w1); sub(/[ \t].*$/, "", w1); return (rclean(w1) ~ RSUB[a] ? substr(s, index(s, w1) + length(w1)) : "\n") }
function rscan(s, R, pos, fw, dl,   n, w, w0, m, o, i, j, t, c, nm, n0, q, first, rest, v, r, br, st) {
  rtab(R); m = split(s, w0, /[ \t]+/); n = o = 0; first = 1; rest = 0; st = 0
  for (i = 1; i <= m; i++) { if (o) w[n] = w[n] " " w0[i]; else w[++n] = w0[i]; o = !jsend(w[n]) && rqopen(w[n]) }
  for (i = 1; i <= n; i++) {
    if (st) break
    st = jsend(w[i]); t = rclean(w[i]); if (t == "") continue
    if (t ~ /^[0-9]*(<|>|&>)/) { if (t ~ /^[0-9]*(<|>>?|&>>?|>&)$/) i++; continue }  # a redirection and its target
    if (t == "--") { rest = 1; continue }
    if (rest && pos) return 1  # after `--` every word is a path filter
    if (t ~ /^--./) {
      nm = substr(t, 3); q = index(nm, "="); if (q) nm = substr(nm, 1, q - 1)
      n0 = nm; nm = tolower(nm); gsub(/-/, "", nm)
      if (index(RDL TDL dl, " " nm " ") || (length(n0) == 1 && index(TDS, n0))) return 1
      v = (q ? substr(t, q + 3) : "")
      if (!q && (index(TVL, " " nm " ") || (length(n0) == 1 && index(TVS, n0))) && i < n && rclean(w[i + 1]) !~ /^-/) { i++; v = w[i] }
      if (rval(nm == "config" || n0 == "c", nm == "env" || n0 == "e", v)) return 1
      continue
    }
    if (t ~ /^-([0-9]+(\.[0-9]+)?|\.[0-9]+)$/ || t == "-") continue  # a negative number
    if (t ~ /^-/) {
      br = 0
      for (j = 2; j <= length(t); j++) {
        c = substr(t, j, 1); r = substr(t, j + 1)
        if (index(TDS, c)) return 1
        if (r ~ /^=/) { v = substr(r, 2); br = 1; break }
        if (TMR == "c" && r != "" && index(TVS, c)) { v = r; br = 1; break }
        if (TMR == "y" && ((c ~ /[A-Za-z]/ && r ~ /^-?[0-9]+(\.[0-9]*)?(e-?[0-9]+)?$/) || r ~ /^[^A-Za-z0-9_]/)) { v = r; br = 1; break }
      }
      if (!br && index(TVS, c) && i < n && rclean(w[i + 1]) !~ /^-/) { i++; v = w[i]; br = 1 }
      if (br && rval(c == "c", c == "e", v)) return 1
      continue
    }
    if (pos && !(fw != "" && first && t ~ fw)) return 1
    first = 0
  }
  return 0
}
# rname: the runner a word names, as a path, `name@version` or `name.js`, after `(`, `{` or `$(`, and `@playwright/test`; RDS holds the runners.
function rname(t) { t = rclean(t); sub(/^\$?[({]+/, "", t); if (t ~ /^@playwright\/test(@[^\/]*)?$/ || t ~ /(^|\/)(@playwright\/test|playwright)\/cli\.[cm]?js$/) return "playwright"; sub(/^.*\//, "", t); if (t ~ /^[^@]+@/) sub(/@.*$/, "", t); sub(/\.[cm]?js$/, "", t); return t }
# cmdat: the index of the command word of the words w[1..n] after a YAML `- key:` or a package.json key, VAR= assignments (a quoted value
# may hold blanks), shell keywords and launchers (npx, npm exec, yarn run, bunx, node, env, sudo, timeout, nice, ...) with their
# options, a value after a one-letter option (sudo -u bob, nice -n 5) and a number (timeout 60), from word i0 on; 0 when there is none
# (R1-03).
function cmdat(w, n, i0,   i, t, l, v, q, lw, pl) {
  for (i = i0; i <= n; i++) {
    t = rclean(w[i]); sub(/^\$?[({]+/, "", t)
    if (t == "" || t == "-" || w[i] ~ /:$/) continue
    if (t ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
      v = w[i]; gsub(/\\/, "", v); v = substr(v, index(v, "=") + 1); q = substr(v, 1, 1)
      if (q ~ /["\047]/ && (length(v) == 1 || substr(v, length(v)) != q)) for (i++; i <= n; i++) { v = w[i]; gsub(/\\/, "", v); if (index(v, q)) break }
      continue
    }
    if (t ~ /^(sudo|env|time|timeout|exec|command|nice|nohup|node|npm|npx|pnpx|bunx|yarn|pnpm|bun|dlx|x|run|if|then|do|else|elif|while|until|!)$/) { pl = lw; lw = t; l = 1; continue }
    # the package of npx, pnpx, bunx, dlx, npm exec and npm x, also a runner name (R1-02); `time -p`, `command -p` take no value (R2-01)
    if (t ~ /^(-p|--package)$/ && i < n && (lw ~ /^(npx|pnpx|bunx|dlx)$/ || (lw ~ /^(exec|x)$/ && pl ~ /^(npm|pnpm|yarn|bun)$/))) { i++; continue }
    if (l && t ~ /^-/) { if (t ~ /^-[A-Za-z]$/ && i < n && rclean(w[i + 1]) !~ /^-/ && !(rname(w[i + 1]) in RDS)) i++; continue }
    if (l && t ~ /^[0-9.]+[smhd]?$/) continue
    return i
  }
  return 0
}
# runopt: 1 when command p passes a denied option to jest, vitest, mocha, playwright or cypress, directly or in an npm `--` tail.
# playwright and cypress are read only with their test subcommand (RSUB, RREQ: `playwright test`, `cypress run`) as the command.
function runopt(p,   n, w, k, a, r, i, dd, rs, dl, tl, s0, t1) {
  if (datacmd(p)) return 0
  n = split(p, w, /[ \t]+/)
  for (k = cmdat(w, n, 1); k; k = (JSF ? cmdat(w, n, i) : 0)) {  # in a package.json, every script value on the line
    a = rname(w[k]); tl = ""; for (i = k + 1; i <= n && !jsend(w[i - 1]); i++) tl = tl " " w[i]
    if (!(a in RDS)) continue
    if ((a in RREQ) && (tl = rsub(tl, a)) == "\n") continue
    if (rscan(tl, a, a != "mocha", (a in RREQ) ? "" : RSUB[a], "")) return 1
  }
  for (r in RDS) for (s0 = p; has(s0, r); s0 = substr(s0, 2)) {  # every mention: a package.json value ends a scan (R2-02)
    s0 = after(s0, r); t1 = s0; if (r == "playwright") sub(/^(\/test(@[^ \t\/]*)?)?(\/cli\.[cm]?js)?/, "", t1)  # @playwright/test, .../cli.js (R1-01)
    if ((r in RREQ) && (t1 = rsub(t1, r)) == "\n") continue
    if (rscan(t1, r, 0, "", "")) return 1
  }
  dd = ddseg(p); if (dd == "") return 0
  if (!ddrun(p)) return rscan(dd, "", 0, "", "")
  rs = dl = ""
  for (i = 1; i <= NS[DDN]; i++) {  # plainrun: every definition is `[npx] <runner> ...`, a runner of RUNRE, all in RDS
    a = NC[DDN, i]; sub(/^[ \t]*(npx[ \t]+)?/, "", a); sub(/[ \t].*$/, "", a); rs = rs " " a
    if (a == "mocha") dl = "spec "  # a spec in the tail, like a positional word, may replace the configured one
  }
  return rscan(dd, rs, 1, "", dl)
}
function jsseg(p, tool) { return (has(p, tool) ? after(p, tool) : "") " " ddseg(p) }
# baseline: ESLint suppression flags write or read a suppressions file, a baseline; no justified: waives them (check 3 has no escape hatch).
function baseline(p) { return (has(p, "eslint") || ddseg(p) != "") && eslintbase(jsseg(p, "eslint")) }
# datacmd: the command installs a tool (its name is an argument, not a command): `pip install ruff --upgrade`, `npm i -D eslint`.
function datacmd(p,   n, w, i, j, k, a, b, c, m) {
  if (ddseg(p) != "") return 0  # a `--` tail after npm, yarn, pnpm or bun is passed to a script, so the segment runs something
  n = split(p, w, /[ \t]+/); i = 1
  while (i <= n && (w[i] == "" || w[i] == "-" || w[i] ~ /:$/ || w[i] ~ /^[A-Za-z_][A-Za-z0-9_]*=/ || w[i] ~ /^(sudo|env|time|export|exec|command)$/)) i++
  a = w[i]; sub(/^["\047]+/, "", a); sub(/^.*\//, "", a)
  for (m = i + 1; m <= n; m++) if (w[m] ~ /^(run|exec|dlx|run-script|test|start|stop|restart)$/ || (a == "npm" && w[m] ~ /^(x|rum|urn|t|tst)$/)) return 0  # a run verb: the tool is run, whatever else precedes
  j = i + 1; while (j <= n && w[j] ~ /^-/) j++; b = w[j]; k = j + 1; while (k <= n && w[k] ~ /^-/) k++; c = w[k]
  if (a ~ /^(pip|pip3|pipx)$/ && b ~ /^(install|uninstall|upgrade|upgrade-all|inject|reinstall|reinstall-all|download)$/) return 1
  if (a == "conda" && b ~ /^(install|create|update|remove|uninstall)$/) return 1
  if (a ~ /^(apt|apt-get|apk|brew|dnf|yum|gem)$/ && b ~ /^(install|add|reinstall|upgrade|update|remove|uninstall)$/) return 1
  if (a ~ /^(npm|pnpm|yarn|bun)$/ && b ~ /^(install|i|ci|add|update|upgrade|uninstall|remove|rm|link)$/) return 1
  if (a == "uv" && (b ~ /^(pip|add|sync|lock|remove)$/ || (b == "tool" && c ~ /^(install|upgrade|uninstall)$/))) return 1
  if (a ~ /^python[0-9.]*$/ && w[i + 1] == "-m" && w[i + 2] ~ /^(pip|ensurepip|venv)$/) return 1
  return (a ~ /^(cargo|go)$/ && b == "install")
}
function relaxed(p,   dd, e, pr, t, ok, s) {
  dd = ddseg(p); if (dd != "" && ddrun(p)) dd = ""
  if (match(p, /SHELLCHECK_OPTS(\+?=|:[ \t])/) && scan(substr(p, RSTART + RLENGTH), "shellcheck", 0)) return 1
  if (datacmd(p)) return 0
  if (has(p, "ruff")) { s = after(p, "ruff"); if (scan(s, "ruff", 0) || cfg(s, "--config", "^[^= \t]*(ruff|pyproject)\\.toml$")) return 1 }
  if (has(p, "mypy")) {
    s = after(p, "mypy")
    if (scan(s, "mypy", 0) || (s ~ "[ \t][\"\047]?@[^ \t\"\047]") || cfg(s, "--(" pre("config-file", 3) ")", "^[^= \t]*(mypy\\.ini|setup\\.cfg|tox\\.ini|pyproject\\.toml)$")) return 1
  }
  if (has(p, "shellcheck") && scan(after(p, "shellcheck"), "shellcheck", 0)) return 1
  if (has(p, "actionlint") && scan(after(p, "actionlint"), "actionlint", 0)) return 1
  e = has(p, "eslint"); pr = has(p, "prettier"); t = has(p, "tsc")
  if (dd != "" && scan(dd, "eslint prettier tsc", 0)) return 1
  if (e) ok = "((^|/)[^= \t]*(eslint\\.config\\.[A-Za-z]+|eslintrc[^/= \t]*|biome\\.json[^/= \t]*)$)"
  else if (pr) ok = "((^|/)[^= \t]*(prettierrc[^/= \t]*|prettier\\.config\\.[A-Za-z]+)$)"
  else ok = "((^|/)[^= \t]*(eslint\\.config\\.[A-Za-z]+|eslintrc[^/= \t]*|biome\\.json[^/= \t]*|prettierrc[^/= \t]*|prettier\\.config\\.[A-Za-z]+)$)"
  if (t || dd != "") { s = (t ? after(p, "tsc") : "") " " dd; if ((t && scan(s, "tsc", 1)) || cfg(s, "-p|--project", TSOK) || tscbuild(s)) return 1 }
  if (e || dd != "") { s = (e ? after(p, "eslint") : "") " " dd; if ((e && scan(s, "eslint", 0)) || eslintrule(s) || cfg(s, "-c|--config", ok)) return 1 }
  if (pr || dd != "") { s = (pr ? after(p, "prettier") : "") " " dd; if ((pr && scan(s, "prettier", 0)) || cfg(s, "--config", ok)) return 1 }
  return 0
}
# yamlitem: one YAML sequence item is a workflow step or a pre-commit hook. Its `uses:` (an action named after the tool), or in pre-commit
# config its `entry:` or `id:`, gives the command; its args-like keys (ARGKEY, at any depth, in any order, quoted or not: inline, a flow or
# block list, a flow mapping, a block scalar) are flags of that command, each checked by itemend when the item ends, when the key is a
# generic one or starts with the tool name (`eslint_flags`, not `reviewdog_flags`). Lines inside another block scalar (`run: |`) are skipped.
function notag(v) { while (v ~ /^[&!][^ \t]*([ \t]|$)/) sub(/^[&!][^ \t]*[ \t]*/, "", v); return v }  # anchors, tags
function keycol(l) { sub(/[^ \t-].*$/, "", l); return length(l) }
function indent(l) { sub(/[^ \t].*$/, "", l); return length(l) }
function toolof(v,   i, n, tl) {
  n = split("ruff mypy eslint prettier shellcheck actionlint tsc", tl, " ")
  for (i = 1; i <= n; i++) if (v ~ ("(^|[^A-Za-z])" tl[i] "([^A-Za-z]|$)")) return tl[i]
  return ""
}
function hookcmd(v) { v = unq(v); return (v ~ /^ruff(-check)?$/ ? "ruff check" : (v == "ruff-format" ? "ruff format" : toolof(v))) }
# AU: the text of the lines of an args key that have no reason; a reason waives its own line only (R1-06).
# flowsplit: a flow collection with every comma outside quotes made a blank, as YAML splits `[.,--fix]` into two items (R1-01).
function flowsplit(a,   i, c, q, r) {
  for (i = 1; i <= length(a); i++) {
    c = substr(a, i, 1)
    if (q != "") { if (c == q) q = "" } else if (c == "\"" || c == "\047") q = c; else if (c == ",") c = " "
    r = r c
  }
  return r
}
function argadd(k, v, l) { NA++; AK[NA] = k; AF[NA] = (v ~ /^[[{]/); AU[NA] = (v ~ /^[|>][-+0-9]*$/ || just(l) ? "" : v); AL[NA] = NR; ALN[NA] = l }
function itemend(   a, i, tool) {
  tool = toolof(IT)
  for (i = 1; i <= NA; i++) {
    a = (AF[i] ? flowsplit(AU[i]) : AU[i]); gsub(/[][{}]/, " ", a); gsub(/,([ \t]|$)/, " ", a)
    if (IT != "" && (AK[i] ~ /^(extra_)?(args|flags|options|arguments)$/ || index(AK[i], tool "_") == 1) && a ~ /[^ \t]/ && relaxed(IT " " a))
      printf "%s:%d:%s\n", F, AL[i], ALN[i]
  }
  IT = ""; NA = 0; IE = 0; IK = -1; IKP = 0; AM = 0; BS = -1
}
function ykey(k, v) {
  if (k == "uses" && !PC) { v = unq(v); sub(/@.*$/, "", v); IT = toolof(v) }
  else if (k == "entry" && PC) { IT = unq(v); IE = 1 }
  else if (k == "id" && PC && !IE) IT = hookcmd(v)
}
# flowmap: the keys of a flow mapping (`- {id: ruff, args: [--fix]}`, `with: {args: check}`), nested ones included.
function flowmap(v, l,   m, k, x) {
  while (match(v, /[{,][ \t]*["\047]?[A-Za-z_][A-Za-z0-9_-]*["\047]?[ \t]*:[ \t]*(\[[^]]*\]|[^]{},]*)/)) {
    m = substr(v, RSTART + 1, RLENGTH - 1); v = substr(v, RSTART + RLENGTH)
    k = m; sub(/[ \t]*:.*$/, "", k); gsub(/["\047 \t]/, "", k); k = tolower(k); x = m; sub(/^[^:]*:[ \t]*/, "", x); sub(/[ \t]+$/, "", x)
    if (k ~ ARGKEY) argadd(k, x, l); else ykey(k, x)
  }
}
function yamlitem(l,   c, key, v) {
  if (l ~ /^[ \t]*(#|$)/) return
  if (AM) { if (indent(l) > AC || (indent(l) == AC && l ~ /^[ \t]*-([ \t]|$)/)) { v = l; sub(/^[ \t]*(-[ \t]+)?/, "", v); if (!just(l)) AU[NA] = AU[NA] " " stripc(v); return } AM = 0 }
  if (BS >= 0) { if (indent(l) > BS) return; BS = -1 }
  if (l ~ /(^[ \t]*(-[ \t]+)?|[{,][ \t]*)"[^"]*\\[^"]*"[ \t]*:/ && !just(l)) printf "%s:%d:%s\n", F, NR, l  # an escaped key (R1-02)
  if (l ~ /^[ \t]*-[ \t]+(["\047]?[A-Za-z_][A-Za-z0-9_-]*["\047]?[ \t]*:([ \t]|$)|\{)/) { itemend(); IK = keycol(l) }
  else if (l ~ /^[ \t]*-[ \t]*(#.*)?$/) { itemend(); IKP = 1; return }  # a bare `-`: the keys of the item start on the next line
  else if (IKP) { IK = indent(l); IKP = 0 }
  else if (IK >= 0 && indent(l) < IK) itemend()
  if (IK < 0) return
  v = l; sub(/^[ \t]*(-[ \t]+)?/, "", v); c = length(l) - length(v)
  if (v ~ /^\{/) { flowmap(v, l); return }
  if (!match(v, /^["\047]?[A-Za-z_][A-Za-z0-9_-]*["\047]?[ \t]*:([ \t]|$)/)) return
  key = v; sub(/[ \t]*:.*$/, "", key); gsub(/["\047]/, "", key); key = tolower(key); v = stripc(substr(v, RLENGTH + 1)); sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v); v = notag(v)
  if (v ~ /^\{/) { flowmap(v, l); return }
  if (key ~ ARGKEY) { argadd(key, v, l); AM = 1; AC = c; return }
  if (v ~ /^[|>][-+0-9]*$/) { BS = c; return }
  if (c == IK) ykey(key, v)
}
function flush(   n, i, parts, j) {
  if (cur == "") return
  j = just(cur)
  n = split(stripc(cur), parts, /[;&|]+/)
  if (F ~ /([Mm]akefile|\.mk)$/) for (i = 1; i <= n; i++) sub(/^[ \t@+-]+/, "", parts[i])  # recipe prefixes: silent, always run, ignore errors
  for (i = 1; i <= n; i++) if (runopt(parts[i])) { printf "@runopt@%s:%d:%s\n", F, start, cur; break }
  for (i = 1; i <= n; i++) if (baseline(parts[i]) || (!j && relaxed(parts[i]))) { printf "%s:%d:%s\n", F, start, cur; break }
  cur = ""
}
BEGIN { TSOK = "((^|/)(\\.\\.?|[^./= \t]+)/?$)|((tsconfig|jsconfig)[^/= \t]*\\.json$)"
  SP = "(^|[ \t])[\"\047]?"; cur = ""; cont = 0
  RUFFSUB = "^(check|format|rule|config|linter|clean|server|analyze|version|help|generate-shell-completion)$"
  SRCRE = "^[^-][^=]*\\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$"; SEVOK = "^(warning|info|style)$"; COLOROK = "^(always|never|auto)$"
  ARGKEY = "^([A-Za-z0-9-]*_)?(args|flags|options|arguments)$"; YML = (F ~ /\.ya?ml$/); JSF = (F ~ /package\.json$/); PC = (F ~ /pre-commit-config\.yaml$/); IK = -1; BS = -1
  # Test runners that are no linter and take an npm `--` tail as their own options (not firebase: emulators:exec runs its argument;
  # not vitest: its typecheck mode runs tsc).
  RUNRE = "^[ \t]*(npx[ \t]+)?(jest|mocha|playwright|cypress)([ \t]+[A-Za-z0-9_./:=@,+%-]+)*[ \t]*$"
  NPMBOOL = "^(-s|--silent|-q|--quiet|--if-present|--ignore-scripts)$"
  # runopt (check 1, task M1-71): denied long names (normalized: lower case, no dashes) and short letters per runner, and the allowed
  # options whose value may follow as the next word. jest -t, -o, -f: name filter, onlyChanged, onlyFailures; vitest -u: update;
  # mocha -g, -f, -i: grep, fgrep, invert (its -t, -u, -R are timeout, ui, reporter).
  RDL = " updatesnapshot update passwithnotests testnamepattern testpathignorepatterns testpathpattern testpathpatterns onlychanged changedsince findrelatedtests lastcommit onlyfailures changed grep fgrep invert exclude ignore filter updatesnapshots ignoresnapshots list grepinvert testlist testlistinvert nodeps lastfailed "
  RVL = " config maxworkers shard testtimeout timeout reporters reporter reporteroption reporteroptions outputfile coveragereporters coveragedirectory seed testenvironment environment env cachedirectory pool ui slow require spec jobs "
  RDS["jest"] = "utof"; RDS["vitest"] = "ut"; RDS["mocha"] = "gfi"
  RVS["jest"] = "cw"; RVS["vitest"] = "c"; RVS["mocha"] = "tuRsrj"
  RM["jest"] = RM["mocha"] = "y"; RM["vitest"] = "m"; RCK["jest"] = RCK["vitest"] = RCK["mocha"] = "j"; RSUB["vitest"] = "^(run|watch|dev)$"
  # Task M1-81 (#15 comment 7102820038): playwright and cypress (commander) with their own value-taking long names (RVX, in place of
  # RVL) and denied extras (RDX); their long denied names are in RDL. playwright -u, -g (also -gv); cypress -s (--spec).
  RDS["playwright"] = "ug"; RVS["playwright"] = "cj"; RM["playwright"] = "c"; RCK["playwright"] = "p"; RSUB["playwright"] = "^test$"
  RVX["playwright"] = " config workers reporter output trace timeout globaltimeout maxfailures repeateach tsconfig updatesourcemethod uihost uiport project retries shard "
  RDS["cypress"] = "s"; RVS["cypress"] = "bcCekpProt"; RM["cypress"] = "c"; RCK["cypress"] = "y"; RSUB["cypress"] = "^run$"; RDX["cypress"] = "spec "
  RVX["cypress"] = " browser config configfile env port project reporter reporteroptions key tag record group cibuildid autocancelafterfailures "
  RREQ["playwright"] = RREQ["cypress"] = 1
  np = split(ENVIRON["NPMS"], P, "\n")  # pkgscripts: name TAB command; a bare TAB makes every tail unknown
  for (i = 1; i <= np; i++) if ((j = index(P[i], "\t")) == 1) NPMU = 1; else if (j) { nm = substr(P[i], 1, j - 1); NC[nm, ++NS[nm]] = substr(P[i], j + 1) }
  nl = split(ENVIRON["CLI_ALLOW"], L, "\n")
  for (i = 1; i <= nl; i++) {
    if (L[i] ~ /^[ \t]*$/) continue
    split(L[i], f, " "); t = f[1]; sb = ""
    if (index(t, ":")) { sb = substr(t, index(t, ":") + 1); t = substr(t, 1, index(t, ":") - 1) }
    fl = (t == "tsc" ? tolower(f[2]) : f[2])
    if (fl ~ /\*$/) { NG[t]++; GP[t, NG[t]] = substr(fl, 1, length(fl) - 1); GK[t, NG[t]] = f[3]; GS[t, NG[t]] = sb }
    else { K[t, sb, fl] = f[3]; if (sb == "") EX[t] = EX[t] " " fl }
  } }
{
  line = $0; sub(/\r$/, "", line)
  if (YML) yamlitem(line)
  if (!cont && line ~ /^[ \t]*#/) next
  if (!cont) start = NR
  cont = (line ~ /\\[ \t]*$/)
  if (cont) sub(/\\[ \t]*$/, "", line)
  cur = (cur == "" ? "" : cur " ") line
  if (!cont) flush()
}
END { flush(); if (YML) itemend() }'
# YFOLD_AWK: prints a YAML file with each value that goes on over several lines joined into one line, as the runner reads it (issue 164
# item 2). cliflags runs CLI_AWK on this text IN ADDITION to the file itself, so it can only add failures (PR 309 ruling 7084379032).
# A group is a run of lines YAML joins with blanks: the lines of a plain or quoted scalar or a flow collection up to a blank line (a
# line break), or the lines of equal indentation of a folded block (`>`; a more-indented line keeps its breaks). The group goes on
# its first line and its other lines become blank, so line numbers hold. Double-quoted escapes are decoded (`\x2d` is `-`, `\n` a
# command separator, an escaped line break joins with no blank). A reason waives a group only when every line of it has one.
YFOLD_AWK='
# yent: a pre-commit `entry:` (key on line h, value from line i) is split into words, so a line break is a blank there: the whole
# value is one line on the key line, and a `#` in a block scalar is a word, not a comment.
function yent(h, i, o, p,   j, m, g, e, w) {
  j = yval(i, o, p); g = L[h]; sub(/[^ \t].*$/, "", g); e = h
  for (m = h; m < j; m++) if (O[m] !~ /^[ \t]*$/) { w = O[m]; sub(/^[ \t]+/, "", w); if (YB && m > i) gsub(/#/, "\\#", w); g = g (e == h && m == h ? "" : " ") w; e = m }
  put(h, e, g); return j
}
function yi(l) { sub(/[^ \t].*$/, "", l); return length(l) }
function hexc(h,   i, n, k) {
  n = 0
  for (i = 1; i <= length(h); i++) { k = index("0123456789abcdef", tolower(substr(h, i, 1))); if (!k) return "?"; n = n * 16 + k - 1 }
  return (n == 10 ? ";" : (n == 9 ? "\t" : (n >= 32 && n < 127 ? sprintf("%c", n) : "?")))
}
# yscan: the text of s as YAML reads it, tracking an open quote (Q), the flow depth (D) and a node start (NS) over lines. A quoted
# scalar loses its quotes in block context and keeps them in a flow, where 2c splits a list on commas outside quotes. A node property
# (`&a`, `!!str`) keeps the node start; in a flow a `:` right after a closing quote is a value indicator (`{"run":"x"}`). CM is set when
# a comment starts (its text is kept outside a flow), EB when s ends with an escaped line break.
function yscan(s,   i, n, c, t, h, jq) {
  t = ""; CM = 0; EB = 0; n = length(s)
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (Q == "\"") {
      if (c == "\"") { Q = ""; jq = 1; if (KQ) t = t c; continue }
      if (c == "\\") {
        if (i == n) { EB = 1; break }
        c = substr(s, ++i, 1)
        if (c == "x" || c == "u" || c == "U") { h = (c == "x" ? 2 : (c == "u" ? 4 : 8)); c = hexc(substr(s, i + 1, h)); i += h }
        else if (c == "n") c = ";"; else if (c == "t") c = "\t"; else if (c == "\"" || c == "\\") { if (KQ) c = "\\" c } else if (c !~ /[ \/]/) c = "?"
      }
      t = t c; continue
    }
    if (Q == "\047") { if (c == "\047") { if (substr(s, i + 1, 1) != "\047") { Q = ""; jq = 1; if (KQ) t = t c; continue } i++; if (KQ) t = t c } t = t c; continue }
    if (c ~ /[ \t]/) { t = t c; continue }
    if (c == "#" && (i == 1 || substr(s, i - 1, 1) ~ /[ \t]/)) { CM = 1; return (D ? t : t substr(s, i)) }
    if (NS && (c == "&" || c == "!")) { while (i < n && substr(s, i + 1, 1) !~ (D ? "[] \t,[{}]" : "[ \t]")) { t = t c; c = substr(s, ++i, 1) } t = t c; continue }
    if (NS && (c == "\"" || c == "\047")) { Q = c; KQ = (D > 0); NS = 0; if (KQ) t = t c; continue }
    else if ((NS || D) && (c == "[" || c == "{")) { D++; NS = 1 }
    else if (D && (c == "]" || c == "}")) { D--; NS = 0 }
    else if (D && (c == "," || (c == ":" && (jq || substr(s, i + 1, 1) ~ /^[] \t,}]?$/)))) NS = 1
    else NS = 0
    jq = 0; t = t c
  }
  return t
}
function notag(v) { while (v ~ /^[&!][^ \t]*([ \t]|$)/) sub(/^[&!][^ \t]*[ \t]*/, "", v); return v }
# put: the group of lines a..b (text G) on line a, the others blank; a reason on only some lines of it is no reason (R2-01, Y1).
function put(a, b, g,   i, ok) {
  if (a < 0) return
  ok = 1; for (i = a; i <= b; i++) if (L[i] !~ /^[ \t]*$/ && !just(L[i])) ok = 0
  if (!ok && a < b) gsub(/justified:/, "justified-", g)
  O[a] = g; for (i = a + 1; i <= b; i++) O[i] = ""
}
# yval: the value that starts at offset o of line i, under a parent at column p; returns the line after it. A plain value goes on over
# lines indented more than p, up to a comment; a quoted value or a flow collection goes on until it closes.
function yval(i, o, p,   v, w, j, a, e, g, pl, eb) {
  v = substr(L[i], o); w = v; sub(/^[ \t]+/, "", w); w = notag(w); o += length(v) - length(w); v = w; a = -1; YB = (v ~ /^[|>]/)
  if (v ~ /^[|>]/) {
    for (j = i + 1; j <= N && (L[j] ~ /^[ \t]*$/ || yi(L[j]) > p); j++) if (v ~ /^>/) {
      if (a >= 0 && (L[j] ~ /^[ \t]*$/ || yi(L[j]) != yi(L[a]))) { put(a, e, g); a = -1 }
      if (L[j] ~ /^[ \t]*$/) continue
      w = L[j]; sub(/^[ \t]+/, "", w)
      if (a < 0) { a = j; g = L[j] } else g = g " " w
      e = j
    }
    put(a, e, g); return j
  }
  Q = ""; D = 0; NS = 1; pl = (v !~ /^["\047[{]/); a = i; e = i; g = substr(L[i], 1, o - 1) yscan(v); eb = EB
  for (j = i + 1; j <= N; j++) {
    if (Q == "" && !D && (!pl || CM)) break
    if (L[j] ~ /^[ \t]*$/) { put(a, e, g); a = -1; continue }
    if (Q == "" && L[j] ~ /^[ \t]*#/) { if (!D) break; O[j] = ""; continue }
    if (Q == "" && !D && yi(L[j]) <= p) break
    w = L[j]; sub(/^[ \t]+/, "", w); w = yscan(w)
    if (a < 0) { a = j; g = L[j]; sub(/[^ \t].*$/, "", g); g = g w } else g = g (eb ? "" : " ") w
    eb = EB; e = j
  }
  put(a, e, g); return j
}
{ sub(/\r$/, ""); L[++N] = $0; O[N] = $0 }
END {
  PK = -1
  for (i = 1; i <= N; ) {
    l = L[i]
    if (l ~ /^[ \t]*(#|$)/ || l ~ /^(---|\.\.\.)([ \t]|$)/) { i++; continue }
    r = l; sub(/^[ \t]*/, "", r); while (r ~ /^-([ \t]|$)/) sub(/^-[ \t]*/, "", r)
    dash = (length(l) - length(r) > yi(l)); r = notag(r); c = length(l) - length(r)
    k = 0
    if (r ~ /^"/ && match(r, /^"([^"\\]|\\.)*"[ \t]*:([ \t]|$)/)) k = RLENGTH
    else if (r ~ /^\047/ && match(r, /^\047[^\047]*\047[ \t]*:([ \t]|$)/)) k = RLENGTH
    else if (r ~ /^([^]["\047 \t#&*!|>%@`{},?:-]|[-?:][^ \t])/ && match(r, /:([ \t]|$)/) && substr(r, 1, RSTART) !~ /[ \t]#/) k = RSTART + RLENGTH - 1
    if (PK >= 0 && yi(l) > PK && !k && !dash) { p = PK; PK = -1; i = (PE ? yent(PH, i, c + 1, p) : yval(i, c + 1, p)); continue }
    PK = -1
    if (k) {
      PE = (F ~ /pre-commit-config\.yaml$/ && substr(r, 1, k) ~ /^["\047]?entry["\047]?[ \t]*:/)
      v = notag(substr(r, k + 1)); sub(/^[ \t]+/, "", v)
      if (v ~ /^(#|$)/) { PK = c; PH = i; i++; continue }
      i = (PE ? yent(i, i, c + k + 1, c) : yval(i, c + k + 1, c)); continue
    }
    if (dash && r ~ /^(#|$)/) { PK = yi(l); PH = i; PE = 0; i++; continue }  # `-` or `- &x` alone: a mapping or a value follows (R1-01)
    if (dash) { i = yval(i, c + 1, yi(l)); continue }
    i = (yi(l) ? yval(i, c + 1, yi(l) - 1) : i + 1)
  }
  for (i = 1; i <= N; i++) print O[i]
}'
# pkgscripts: `name TAB command` for every script of every tracked package.json (excluded paths too; one it cannot read is unknown), read
# only from the one strict layout: the file's only
# "scripts" token, on a line of its own as `"scripts": {`, then one `"name": "command",` per line up to a `}` line. Any other "scripts"
# token or layout, and any \u escape (it can spell any key; also in a value, PR 309 R3-03), prints a bare TAB: every tail is then unknown.
pkgscripts() {
  local f
  while IFS= read -r f; do
    if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null || echo '"scripts"'; else cat -- "$f" 2>/dev/null || echo '"scripts"'; fi | LC_ALL=C awk '
      { sub(/\r$/, ""); t = $0; c = gsub(/"scripts"/, "", t) }
      /\\u/ { print "\t" }
      s { if (c) print "\t"
          else if ($0 ~ /^[ \t]*\}[ \t]*,?[ \t]*$/) s = 0
          else if ($0 ~ /^[ \t]*"[^"\\\t]+"[ \t]*:[ \t]*"([^"\\]|\\.)*"[ \t]*,?[ \t]*$/) {
            n = $0; sub(/^[ \t]*"/, "", n); v = n; sub(/".*$/, "", n); sub(/^[^"]*"[ \t]*:[ \t]*"/, "", v); sub(/"[ \t]*,?[ \t]*$/, "", v); print n "\t" v }
          else print "\t"
          next }
      c { if (++k > 1 || $0 !~ /^[ \t]*"scripts"[ \t]*:[ \t]*\{[ \t]*$/) print "\t"; else s = 1 }
      END { if (s) print "\t" }'
  done < <(git ls-files -- '*package.json')
}
NPMS=$(pkgscripts)
cliflags() { # cliflags <pathspec>...
  local f y
  while IFS= read -r f; do
    if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null | NPMS="$NPMS" CLI_ALLOW="$CLI_ALLOW" LC_ALL=C awk -v F="$f" "$JUSTFN$CLI_AWK"
    else NPMS="$NPMS" CLI_ALLOW="$CLI_ALLOW" LC_ALL=C awk -v F="$f" "$JUSTFN$CLI_AWK" "$f" 2>/dev/null; fi
    case "$f" in *.yml | *.yaml) # the joined lines, in addition to the lines above; a fold scan that cannot run fails (no quiet gap)
      if [ "$STAGED" = 1 ]; then y=$(git show ":$f" 2>/dev/null | LC_ALL=C awk -v F="$f" "$JUSTFN$YFOLD_AWK")
      elif [ -f "$f" ]; then y=$(LC_ALL=C awk -v F="$f" "$JUSTFN$YFOLD_AWK" "$f")
      else continue; fi || { echo "$f:0: the YAML fold scan failed"; continue; }  # a file missing from the tree has nothing to scan (R1-02)
      printf '%s\n' "$y" | NPMS="$NPMS" CLI_ALLOW="$CLI_ALLOW" LC_ALL=C awk -v F="$f" "$JUSTFN$CLI_AWK" ;;
    esac
  done < <(git ls-files -- "$@" "${EXCL[@]}") | awk '!seen[$0]++ { if (sub(/^@runopt@/, "")) print "guard: test-runner option that skips or rewrites tests: " $0; else print "guard: unjustified CLI flag: " $0 }'
}
out=$(cliflags '*.sh' '.githooks/*' '.github/workflows/*' '.github/actions/*' '*package.json' '*Makefile' '*makefile' '*.mk' '*pre-commit-config.yaml')
[ -n "$out" ] && { echo "$out"; fail=1; }
# 2d. `/* global foo, bar:writable */` (ESLint) switches off no-undef for the names. Any block comment that starts with `global` or
# `globals` and a name, closed on the same line, in a JS or TS file: that is how ESLint reads it (names split on commas and spaces, an
# optional `-- description`), so `/* global state is kept */` is a directive too. A multi-line comment is not matched.
out=$(gg '/\*[[:space:]]*globals?[[:space:]]+[A-Za-z_$][^*]*\*/' \
  -- '*.js' '*.mjs' '*.cjs' '*.jsx' '*.ts' '*.mts' '*.cts' '*.tsx' '*.vue' "${EXCL[@]}" | unjust)
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }
# 2e. Linter, formatter and test config embedded in package.json is not scanned by the checks above (and ESLint 9 ignores eslintConfig).
# JSON has no comment for a justification, so there is no escape hatch: keep that config in the dedicated file. A dependency entry
# (`"jest": "30.5.2"`) has a string value and does not match; the string form of "prettier" is not detected. Only top-level keys count
# (brace depth 1), so `"overrides": { "jest": { ... } }` and `"peerDependenciesMeta"` are dependency data.
PKG_AWK='
{ s = $0; n = length(s); i = 1
  while (i <= n) {
    c = substr(s, i, 1)
    if (c == "\"") {
      k = ""; j = i + 1
      while (j <= n && (d = substr(s, j, 1)) != "\"") { if (d == "\\") { j++; d = d substr(s, j, 1) } k = k d; j++ }
      rest = substr(s, j + 1); i = j + 1
      if (depth == 1 && rest ~ /^[ \t]*:/) { sub(/^[ \t]*:[ \t]*/, "", rest)
        if (k == "eslintConfig" || k == "eslintIgnore" || (k ~ /^(prettier|jest|nyc|c8)$/ && rest ~ /^(\{|$)/)) { printf "%s:%d:%s\n", F, NR, $0; next } }
      continue
    }
    if (c == "{" || c == "[") depth++; else if (c == "}" || c == "]") depth--
    i++
  }
}'
out=$(while IFS= read -r f; do
  if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null | awk -v F="$f" "$PKG_AWK"; else awk -v F="$f" "$PKG_AWK" "$f" 2>/dev/null; fi
done < <(git ls-files -- '*package.json' "${EXCL[@]}"))
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: embedded config: package.json must not hold linter or test config (use the dedicated file): /'; fail=1; }

# 3. Baselines (no escape hatch): by name, by wiring and by content, any file type.
# ESLint loads a committed eslint-suppressions.json (bulk suppressions) on its own, in any directory: a baseline too (#173).
# A directory of that name is its cache dir, which ESLint also reads suppressions from, so files under it count as well.
out=$("${LS[@]}" | grep -iE 'baseline|(^|/)eslint-suppressions\.json(/|$)')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: baseline file: /'; fail=1; }
# Formatter and linter ignore files cannot carry a same-line justification, so they are refused outright (ask the owner).
out=$("${LS[@]}" | grep -E '(^|/)\.(prettier|eslint|stylelint|dprint)ignore$')
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: ignore file: /'; fail=1; }
# The ESLint Node API options applySuppressions and suppressionsLocation load a suppressions file of any name (whole identifiers only).
out=$(gg 'baseline *(=|\(|\.set)|<SmellBaseline>|<issues format=|(^|[^[:alnum:]_])(applySuppressions|suppressionsLocation)($|[^[:alnum:]_])' -- "${EXCL[@]}")
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

# 6. Narrowed lists (owner decision in #46: diff-based, against the merge base). `listitems <key regex> <rev:path>` prints
# key<TAB>item<TAB>line for every quoted item of an array value of that key (single or multi-line, several keys per line). Comments
# (`#`, `//`) are cut. A removed ruff `select` item or tsconfig `include` entry fails with no escape hatch (a replacement by "ALL" is fine);
# an added tsconfig `exclude` entry needs `justified:` on its own line (tsconfig allows comments). Files new in the PR are not compared; a deleted one is compared with every config of its kind at HEAD.
LISTS_AWK='
BEGIN { RE = "(^|[^A-Za-z_-])[\"\047]?(" KEYRE ")[\"\047]?[ \t]*[:=][ \t]*\\[" }
{
  s = $0; n = length(s); i = 1; q = ""; gsub(/\t/, " ", s)
  while (i <= n) {
    if (bc) { j = index(substr(s, i), "*/"); if (!j) break; i += j + 1; bc = 0; continue }
    if (depth == 0) {
      t = substr(s, i)
      if (!match(t, RE)) break
      st = RSTART; ln = RLENGTH; m = substr(t, st, ln); match(m, KEYRE); key = substr(m, RSTART, RLENGTH); i += st + ln - 1; depth = 1; continue
    }
    c = substr(s, i, 1); i++
    if (q != "") { if (c == q) { q = ""; print key "\t" cur "\t" s } else cur = cur c; continue }
    if (c == "\"" || c == "\047") { q = c; cur = ""; continue }
    if (c == "[") depth++
    else if (c == "]") depth--
    else if (c == "/" && substr(s, i, 1) == "*") { bc = 1; i++ }
    else if (c == "#" || (c == "/" && substr(s, i, 1) == "/")) break
  }
}'
listitems() { git show "$2" 2>/dev/null | LC_ALL=C awk -v KEYRE="$1" "$LISTS_AWK" | sed 's/^extend-//'; }
widened() { # widened <file> <base items> <head items>: exclude entries the head adds, without a justification on their own line
  local k it ln
  while IFS=$'\t' read -r k it ln; do
    [ "$k" = exclude ] || continue
    if printf '%s\n' "$2" | cut -f1,2 | grep -qxF -- "$k"$'\t'"$it"; then continue; fi
    [ -n "$(printf '%s\n' "$ln" | unjust)" ] && bad "widened tsconfig exclude: $1: $it was added without a justified: reason"
  done <<<"$3"
}
narrowcheck() { # narrowcheck <merge-base>
  local mb="$1" f g re kind base head added k it hk hit kept
  while IFS= read -r f; do
    git cat-file -e "$mb:$f" 2>/dev/null || continue
    case "$f" in
      *ruff.toml|*pyproject.toml) re='(extend-)?select'; kind='ruff\.toml$|pyproject\.toml$' ;;
      *) re='include|exclude'; kind='(ts|js)config[^/]*\.json$' ;;
    esac
    base=$(listitems "$re" "$mb:$f"); added=""
    # A deleted file (a rename or a move shows as delete plus add) is compared with the items of every file of its kind at HEAD, and
    # its base exclude entries with the exclude entries of the files of that kind added in the PR.
    if git cat-file -e "HEAD:$f" 2>/dev/null; then head=$(listitems "$re" "HEAD:$f"); added=$head
    else
      head=$(while IFS= read -r g; do listitems "$re" "HEAD:$g"; done < <(git ls-tree -r --name-only HEAD | grep -E "$kind"))
      added=$(while IFS= read -r g; do listitems "$re" "HEAD:$g"; done < <(git diff --name-only --no-renames --diff-filter=A "$mb" HEAD | grep -E "$kind"))
    fi
    while IFS=$'\t' read -r k it _; do
      [ -n "$k" ] || continue
      if printf '%s\n' "$head" | cut -f1,2 | grep -qxF -- "$k"$'\t'"$it"; then continue; fi
      if [ "$k" = select ]; then
        # Ruff selectors are code prefixes: a head item that is a prefix of the removed one (or ALL) still covers it.
        kept=0
        while IFS=$'\t' read -r hk hit _; do [ "$hk" = select ] && case "$it" in "$hit"*) kept=1 ;; esac; [ "$hit" = ALL ] && kept=1; done <<<"$head"
        [ "$kept" = 1 ] || bad "narrowed ruff select: $f: $it was removed"
      elif [ "$k" = include ]; then bad "narrowed tsconfig include: $f: $it was removed"; fi
    done <<<"$base"
    widened "$f" "$base" "$added"
  done < <(git diff --name-only --no-renames --diff-filter=MD "$mb" HEAD -- '*ruff.toml' '*pyproject.toml' '*tsconfig*.json' '*jsconfig*.json' "${EXCL[@]}")
}

# 7. A raised line length (owner decisions in #46 and #176). Every setting of the family (line-length, max-line-length, max_line_length,
# maxLineLength, printWidth) is read from every style file of a tool, at the merge base and at HEAD, and the largest value is compared per
# group: per file, per tool, per tool and setting name, and per tool, setting name and section (an `.editorconfig` section or a TOML table).
# A larger group at HEAD fails, so an added setting counts like an edited one, a family split over two kept files is one group, and a raise
# is not masked by a lowering of another setting or section. A value is a number only when its digits end at a delimiter (`off`, `1_60`,
# `100 * 2` are no limit); a value on the next line is read. Files are not parsed, so it fails closed: every value in a pyproject.toml,
# setup.cfg or tox.ini counts as the tool's, whatever holds it (another tool's raise there fails too). The default and the own groups need to know what
# is the tool's own: a ruff or flake8 file in use (ruff.toml, a `[tool.ruff` table or ruff key, .flake8, `[flake8]`) with no setting of its
# own counts the tool default (ruff 88, flake8 79) for that file, unless a ruff file has `extend =`. The tool's own values and the default
# also get groups of their own, so another tool's wider value hides nothing. A section new at HEAD, while the setting is already no limit at
# the base, is compared with the largest finite base value. A file gone at HEAD is compared with the same tool at HEAD; a symlink is no
# limit. Not compared: a setting removed from a kept file (prettier, `.editorconfig`, detekt: no default), the same setting twice in a file.
STYLERE='(ruff\.toml|pyproject\.toml|\.flake8|setup\.cfg|tox\.ini|\.editorconfig|detekt\.yml|prettierrc[^/]*|prettier\.config\.[^/]*)$'
STYLEX='^(docs|handoff)/|(^|/)(node_modules|build)/'
# Per file: `side TAB file TAB tool TAB section TAB setting TAB value` lines, plus a `present` line and, for a ruff or flake8 file in use
# with no setting, a `dflt` line. A 7th field says the value is the tool's own (ruff's table, flake8's section). Block comments are cut first.
LL_AWK='function num(x) { if (!match(x, /^[0-9]+/)) return 999999999
    d = substr(x, 1, RLENGTH); return (substr(x, RLENGTH + 1) ~ /^[ \t]*([,;}"\047]|\]|$)/) ? d + 0 : 999999999 }
  function ownline(l) {  # is this setting ruff'"'"'s or flake8'"'"'s, in a file that also holds other tools?
    if (f ~ /(^|\/)pyproject\.toml$/) return (sec ~ /^\[tool\.ruff/ || (sec == "[tool]" && l ~ /ruff/) || (sec == "" && l ~ /tool\.ruff/))
    if (f ~ /(^|\/)(setup\.cfg|tox\.ini)$/) return (sec ~ /^\[flake8\]/)
    return 1 }
  function emit(k, v, o) { if (o) any = 1; print sd, f, t, sec, k, v, o + 0 }  # every value counts (fail closed); o: the tool'"'"'s own (own groups, no default)
  BEGIN { OFS = "\t"; use = (f ~ /(^|\/)\.?(ruff\.toml|flake8)$/) }
  { lo = tolower($0); if (NR == 1) sub(/^\357\273\277/, "", lo)  # a BOM
    if (t == "prettier") {  # block comments, also over several lines (only one that opens at the start of a line, `src/*` is a glob)
      if (inc) { if (!match(lo, /\*\//)) next; lo = substr(lo, RSTART + 2); inc = 0 }
      gsub(/\/\*([^*]|\*+[^*\/])*\*+\//, "", lo)
      if (lo ~ /^[ \t]*\/\*/) { inc = 1; next } }
    hd = (f ~ /(setup\.cfg|tox\.ini|\.flake8)$/ ? lo ~ /^[ \t]*\[[^]]*\]/ : lo ~ /^[ \t]*\[[^]]*\][ \t]*([#;].*)?$/); sub(/(^|[ \t])(#|;|\/\/).*$/, "", lo)
    if (pk != "" && lo !~ /^[ \t]*$/) {  # the value of the last key was empty: it is on this line, unless this line is a key or a header
      if (lo !~ /^[ \t]*(\[.*\]|["\047]?[a-z0-9_.-]+["\047]?[ \t]*[:=])/) { sub(/^[ \t]*["\047]?/, "", lo); emit(pk, num(lo), po) }
      pk = "" }
    if (hd) { match(lo, /\[[^]]*\]/); sec = substr(lo, RSTART, RLENGTH); gsub(/[ \t"\047]/, "", sec)
      if (sec ~ /^\[(tool\.ruff|flake8)/) use = 1; next }
    ol = ownline(lo)
    if (ol && f ~ /pyproject\.toml$/ && lo ~ /ruff/) use = 1
    if (t == "ruff" && lo ~ /^[ \t]*extend[ \t]*=/) ext = 1
    gsub(/ktlint_[a-z0-9_]*max[-_]?line[-_]?length/, "ktlint_rule", lo)  # a rule switch, not a limit
    while (match(lo, /(max[-_]?line[-_]?length|line[-_]?length|printwidth)["\047]?[ \t]*[:=][ \t]*["\047]?/)) {
      k = substr(lo, RSTART, RLENGTH); sub(/[^a-z_-].*$/, "", k); gsub(/[-_]/, "", k)
      lo = substr(lo, RSTART + RLENGTH); if (lo ~ /^[ \t]*$/) { pk = k; po = ol; continue }  # a YAML parent key or a value on the next line
      emit(k, num(lo), ol) } }
  END { print sd, f, t, "", "present", 1; if (use && !any && !ext) print sd, f, t, "", "dflt", 1 }'
# Input: the lines of both sides, `B` or `H` first. Output: one `raised line length: ...` line per group that is larger at HEAD.
LL_CMP='BEGIN { FS = "\t"; DEF["ruff"] = 88; DEF["flake8"] = 79 }
  function put(k, v) { if (!(k in M) || v > M[k]) M[k] = v }
  function fmt(v) { return v > 99999 ? "no limit" : v }
  function out(g, b, h,   l) { l = g; if (g ~ /^F\|/) sub(/^F\|[^|]*\|/, "", l); else { sub(/^[A-Z]\|/, "", l); gsub(/\|/, " ", l) }
    print "raised line length: " l ": " fmt(b) " -> " fmt(h) }
  function group(side, tool, file, key, sec, v) { put(side SUBSEP "F|" tool "|" file, v); put(side SUBSEP "T|" tool, v)
    if (key == "") return
    put(side SUBSEP "K|" tool "|" key, v); put(side SUBSEP "S|" tool "|" key "|" sec, v)
    if (v <= 99999 && (!((side, tool "|" key) in KF) || v > KF[side, tool "|" key])) KF[side, tool "|" key] = v }
  $5 == "present" { P[$1, $2] = 1; next }
  $5 == "dflt" { group($1, $3, $2, "", "", DEF[$3]); group($1, $3 " own", $2, "", "", DEF[$3]); next }
  { group($1, $3, $2, $5, $4, $6); if ($7 && $3 in DEF) group($1, $3 " own", $2, $5, $4, $6) }  # the tool'"'"'s own values and default, too
  END {
    for (k in M) {
      split(k, p, SUBSEP); if (p[1] != "B") continue
      g = p[2]; b = M[k]
      if (("H", g) in M) h = M["H", g]
      else if (g ~ /^F\|/) { fl = g; sub(/^F\|[^|]*\|/, "", fl); if (("H", fl) in P) continue
        t = g; sub(/^F\|/, "", t); sub(/\|.*$/, "", t); if (!(("H", "T|" t) in M)) continue; h = M["H", "T|" t] }
      else continue
      if (h > b) out(g, b, h) }
    for (k in M) {  # a section that is new at HEAD, while the setting is already no limit at the base
      split(k, p, SUBSEP); if (p[1] != "H" || p[2] !~ /^S\|/ || ("B", p[2]) in M) continue
      kk = p[2]; sub(/^S\|/, "", kk); split(kk, q, "|"); tk = q[1] "|" q[2]
      if (!(("B", "K|" tk) in M) || M["B", "K|" tk] <= 99999 || !(("B", tk) in KF)) continue
      if (M[k] > KF["B", tk]) out(p[2], KF["B", tk], M[k]) } }'
styletool() { # the tool a style file belongs to
  case "$1" in
    *prettierrc*|*prettier.config.*) echo prettier ;;
    *.editorconfig) echo editorconfig ;;
    *detekt.yml) echo detekt ;;
    *ruff.toml|*pyproject.toml) echo ruff ;;
    *) echo flake8 ;;
  esac
}
styledump() { # styledump <rev> <side>: the settings of every style file at <rev>, each line starting with <side>
  local e m f t  # -z keeps a non-ASCII path readable; the mode tells a symlink (120000), which is no limit; a lone CR is a line end too
  git ls-tree -r -z "$1" | while IFS= read -r -d '' e; do
    f=${e#*$'\t'}; m=${e%% *}
    [[ $f =~ $STYLERE ]] && ! [[ $f =~ $STYLEX ]] || continue; t=$(styletool "$f")
    if [ "$m" = 120000 ]; then printf '%s\t%s\t%s\t\tsymlink\t999999999\n%s\t%s\t%s\t\tpresent\t1\n' "$2" "$f" "$t" "$2" "$f" "$t"
    else git show "$1:$f" 2>/dev/null | tr '\r' '\n' | LC_ALL=C awk -v sd="$2" -v f="$f" -v t="$t" "$LL_AWK"; fi
  done
}
linecheck() { # linecheck <merge-base>
  local names out l
  names=$(git -c core.quotePath=false diff --name-only --no-renames --diff-filter=ADMT "$1" HEAD -- . "${EXCL[@]}")
  grep -qE "$STYLERE" <<<"$names" || return 0  # not `git diff | grep -q`: under pipefail a long list kills git with SIGPIPE
  out=$({ styledump "$1" B; styledump HEAD H; } | LC_ALL=C awk "$LL_CMP" | sort -u)
  while IFS= read -r l; do [ -n "$l" ] && bad "$l"; done <<<"$out"
}

# M1-68 (PR 320 R1): useJUnitPlatform() and failOnNoDiscoveredTests = true may move from a module build file into the convention
# plugins. A removed line whose only check settings are these (MOVE_FN: moved) is accepted when the diff adds each of them to code of
# a regular .kt/.kts file under build-logic/src/main/kotlin/ (movedsettings). Code means outside comments (nested block comments too),
# strings, raw strings and their templates, char literals, backticked names and a `#!` first line: MOVE_LEX reads the whole head file.
# A setting counts only where a statement starts (stmt): not after `val`/`fun`, as a named argument or on the right of `=`.
# What does not count: a weaker form (useJUnitPlatform { ... }, = true && x), a setting already there, any other path or check setting.
# Known limit (part B's per-module check closes it): a text rule cannot see dead code or which modules apply the plugin.
MOVE_FN='
function chk(s) { return s ~ /(minBound|mutationThreshold|threshold|coverageThreshold|fail[-_]under|failOnNoDiscoveredTests|useJUnitPlatform|error *\+?=|fatal *\+?=|warningsAsErrors|maxIssues|failOnSeverity)/ }
function stmt(p,   nl) {  # p, the code before a setting (earlier lines first), ends where a statement starts
  sub(/[ \t]+$/, "", p); sub(/(this|it)[ \t]*\.$/, "", p)  # a receiver; `xit.` leaves `x`, which no rule below accepts
  if (match(p, /[ \t\n]+$/)) { nl = index(substr(p, RSTART), "\n"); p = substr(p, 1, RSTART - 1) }
  if (p == "" || p ~ /([;{})]|->)$/) return 1
  return nl && p ~ /[]A-Za-z0-9_$#]$/ && p !~ /(^|[^A-Za-z0-9_$])(fun|val|var|get|set)$/  # a line break ends a statement
}
function takes(t, ctx,   ids, id, at, post) {  # the movable settings in t, as " id id"; REST = t without them. A weaker form stops the scan.
  t = " " t " "; ids = ""
  while (match(t, /[^A-Za-z0-9_$]useJUnitPlatform[ \t]*\([ \t]*\)|[^A-Za-z0-9_$]failOnNoDiscoveredTests[ \t]*(=[ \t]*true|\.set\([ \t]*true[ \t]*\))/)) {
    at = RSTART; post = substr(t, RSTART + RLENGTH)  # before stmt(), whose match() and sub() reset RSTART and RLENGTH
    if (post !~ /^[ \t]*([;})]|$)/ || !stmt(ctx "\n" substr(t, 1, at))) break
    id = substr(t, at + 1, 1) == "u" ? "useJUnitPlatform" : "failOnNoDiscoveredTests"
    ids = ids " " id; t = substr(t, 1, at) ")" post
  }
  REST = t; return ids
}
function moved(f, l,   ids, n, i, a) {  # removed line l of file f (a/<path>) only held settings that the diff adds to build-logic code
  if (f !~ /^a\/(.*\.gradle(\.kts)?|build-logic\/src\/main\/kotlin\/.*\.kts?)$/) return 0
  ids = takes(l, ""); if (ids == "" || chk(REST)) return 0
  n = split(ids, a, " "); for (i = 1; i <= n; i++) if (!index(" " MOVED " ", " " a[i] " ")) return 0
  return 1
}'
MOVE_LEX='
BEGIN { n = split(ADDED, a, " "); for (i = 1; i <= n; i++) want[a[i]] = 1; top = 0; md[0] = "c"; cd = 0 }
{ # the code of each line: per lexer step a comment gives a space, a string, char or name a #, so `useJUnitPlatform("")` is no
  # plain call. State (block comment depth, string and template stack) carries over lines, and so does ctx, the code before the line.
  s = NR == 1 && substr($0, 1, 2) == "#!" ? "" : $0; L = length(s); out = ""; i = 1
  while (i <= L) {
    c = substr(s, i, 1); c2 = substr(s, i, 2); c3 = substr(s, i, 3); m = md[top]; out = out (cd > 0 || c2 == "/*" || c2 == "//" ? " " : "#")
    if (cd > 0) { if (c2 == "/*") { cd++; i += 2 } else if (c2 == "*/") { cd--; i += 2 } else i++; continue }
    if (m != "c" && m != "t") {  # "s" string (escapes), "r" raw string (closed by the last quote of a run of three or more)
      if (m == "s" && c == "\\") i += 2
      else if (m == "s" && c == "\"") { top--; i++ }
      else if (m == "r" && c3 == "\"\"\"") { while (substr(s, i, 1) == "\"") i++; top-- }
      else if (c2 == "${") { md[++top] = "t"; bd[top] = 1; i += 2 }
      else i++
      continue
    }
    if (c2 == "//") break
    if (c2 == "/*") { cd = 1; i += 2 }
    else if (c3 == "\"\"\"") { md[++top] = "r"; i += 3 }
    else if (c == "\"") { md[++top] = "s"; i++ }
    else if (c == "\047") { j = substr(s, i + 1, 1) == "\\" ? i + 3 : i + 2; while (j <= L && substr(s, j, 1) != "\047") j++; i = j + 1 }
    else if (c == "`") { j = i + 1; while (j <= L && substr(s, j, 1) != "`") j++; i = j + 1 }
    else if (m == "t") { if (c == "{") bd[top]++; else if (c == "}" && --bd[top] == 0) top--; i++ }  # template code: blanked too
    else { out = substr(out, 1, length(out) - 1) c; i++ }
  }
  # R1-03: a line break before &&, ||, ?:, ?., ., ::, as or a lambda continues the expression, so the settings of an added line wait for
  # the next line with code and are dropped when it starts with one of those.
  w = out; sub(/^[ \t]+/, "", w)
  if (w != "") { if (w !~ /^(&&|\|\||[?.{]|::|as([^A-Za-z0-9_$]|$))/) printf "%s", pend; pend = "" }
  if (NR in want) pend = pend takes(out, ctx)
  ctx = ctx "\n" out; gsub(/[ \t]*\n[ \t\n]*/, "\n", ctx); gsub(/[ \t]+/, " ", ctx); if (length(ctx) > 100) ctx = substr(ctx, length(ctx) - 99)
}
END { printf "%s", pend }'
movedsettings() { # movedsettings <merge-base>: the ids of the movable settings on lines the diff adds to code in build-logic (see above)
  local f e lines
  git -c core.quotePath=false diff -z --name-only --no-renames --diff-filter=AMT "$1" HEAD -- \
      ':(glob)build-logic/src/main/kotlin/**/*.kt' ':(glob)build-logic/src/main/kotlin/**/*.kts' | while IFS= read -r -d '' f; do
    e=$(git ls-tree HEAD -- ":(literal)$f" | head -n 1)
    case "$e" in 100644\ blob\ *|100755\ blob\ *) ;; *) continue ;; esac  # a symlink or submodule is no source
    lines=$(git diff -U0 --no-renames "$1" HEAD -- ":(literal)$f" |
      awk '/^@@ / { split($3, p, ","); n = (2 in p) ? p[2] : 1; for (k = 0; k < n; k++) printf "%d ", substr(p[1], 2) + k }')
    e=${e#* blob }; git cat-file blob "${e%%$'\t'*}" | LC_ALL=C awk -v ADDED="$lines" "$MOVE_FN$MOVE_LEX"
  done
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
    moved=$(movedsettings "$MB")
    git diff -U0 "$MB" HEAD -- "${DSPEC[@]}" | awk -v MOVED="$moved" "$MOVE_FN"'
      function norm(l,   n) { sub(/^[-+]/, "", l); gsub(/^[ \t]+|[ \t]+$/, "", l); return l }
      function num(l) { if (match(l, /[0-9]+/)) return substr(l, RSTART, RLENGTH) + 0; return -1 }
      function testpath(p) {
        return (p ~ /(^|\/)test_[^\/]*\.py$|_test\.py$/ || p ~ /^[ab]\/([^\/]+|core\/[^\/]+)\/src\/(test|androidTest|testFixtures|[a-z]+Test)\/.*\.(kt|java)$/)
      }
      # Task 1b (M1-68 part B): in a line of a .py file that is no test file on either side, useJUnitPlatform and
      # failOnNoDiscoveredTests inside a `#` comment or a plain string literal (no prefix or r, b, u, rb, br; an f-string is code)
      # are a mention, not a setting. An unterminated string leaves the rest of the line as it is. Every other keyword still counts.
      function pymention(s,   out, i, j, L, c, seg, p) {
        out = ""; i = 1; L = length(s)
        while (i <= L) {
          c = substr(s, i, 1)
          if (c == "#") { seg = substr(s, i); gsub(/useJUnitPlatform|failOnNoDiscoveredTests/, "mention", seg); return out seg }
          if (c != "\"" && c != "\047") { out = out c; i++; continue }
          for (j = i + 1; j <= L && substr(s, j, 1) != c; j++) if (substr(s, j, 1) == "\\") j++
          if (j > L) return out substr(s, i)
          seg = substr(s, i, j - i + 1); i = j + 1; p = out; sub(/^.*[^A-Za-z0-9_]/, "", p)
          if (p ~ /^([rRbBuU]|[rR][bB]|[bB][rR])?$/) gsub(/useJUnitPlatform|failOnNoDiscoveredTests/, "mention", seg)
          out = out seg
        }
        return out
      }
      /^diff --git/ {
        file = $3
        istest = (NF == 4 && testpath($3) && testpath($4))   # old AND new path must be test files
        ispy = (NF == 4 && $3 ~ /\.py$/ && $4 ~ /\.py$/ && !testpath($3) && !testpath($4))
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
        # Task 1b (see #322): in markdown, plural `thresholds` after a letter-word and before `,`, `;`, `)`, a full stop or a
        # letter-word is prose even when the line has a digit. A colon, `=`, `|`, a number or the line end after it still count.
        if (file ~ /\.md$/) {
          while (match(kw, /[A-Za-z][ \t]+thresholds([,;)]|[.]([ \t]|$)|[ \t]+[A-Za-z])/)) kw = substr(kw, 1, RSTART) " prose " substr(kw, RSTART + RLENGTH - 1)
        }
        if (ispy) kw = pymention(kw)
        # Owner decision (orchestrator #40 chat): on a changed prose line (as above: markdown, or a .py line of only string literals)
        # whose only keyword is `threshold(s) (N/N...)`, the key is that mention with its numbers, not the line. A reworded line that
        # keeps it in the same file passes; other numbers, another file or a dropped mention still fail.
        mkey = ""
        if ($0 ~ /^[-+]/ && (file ~ /\.md$/ || (file ~ /\.py$/ && lit ~ /^[-+][][ \t(){},;]*$/))) {
          pr = kw
          while (match(pr, /[^A-Za-z0-9_]thresholds?[ \t]*\([ \t]*[0-9]+([ \t]*[\/,][ \t]*[0-9]+)*[ \t]*\)/)) {
            mkey = mkey SUBSEP substr(pr, RSTART + 1, RLENGTH - 1); pr = substr(pr, 1, RSTART - 1) " " substr(pr, RSTART + RLENGTH)
          }
          if (chk(pr)) mkey = ""
        }
      }
      # coverageThreshold (Jest) and fail_under / --cov-fail-under (coverage.py) are named like thresholds but not spelled `threshold`.
      # In a Jest, Vitest, nyc or c8 config the per-metric values sit on their own lines (`branches: 80,`), so those lines count too.
      chk(kw) ||
      (file ~ /(jest|vitest|vite)\.config\.[^\/]*$|nycrc[^\/]*$|c8rc[^\/]*$/ && kw ~ /^[-+][ \t]*["\047]?(branches|functions|lines|statements)["\047]?[ \t]*:[ \t]*[0-9]/) {
        l = norm($0); key = file "|" l; gsub(/[0-9]+/, "N", key); n = num(norm(body))
        if (mkey != "") { key = file "|" mkey; n = -1; mc[key] += substr($0, 1, 1) == "-" ? 1 : -1 }  # each copy counts (PR 379 R1-01)
        if (substr($0, 1, 1) == "-") { rem[key] = l; remn[key] = n; remf[key] = file } else { add[key] = l; addn[key] = n }
      }
      END {
        for (k in rem) {
          if (!(k in add) && moved(remf[k], rem[k])) print "guard: note: check setting moved into build-logic: " rem[k]
          else if (!(k in add) || mc[k] > 0) { print "guard: removed check setting: " rem[k]; bad = 1 }
          else if (remn[k] >= 0 && addn[k] >= 0 && addn[k] < remn[k] && rem[k] !~ /maxIssues/) { print "guard: lowered threshold: " add[k]; bad = 1 }
        }
        exit bad
      }' || fail=1
    # Weaker lint presets: per plugin, the strictest preset named on removed lines must not outrank the one on added lines.
    # Flat config (`tseslint.configs.strictTypeChecked`) and eslintrc (`plugin:@typescript-eslint/strict-type-checked`) forms; the order is
    # strictTypeChecked > strict > recommendedTypeChecked > recommended, other presets (stylistic, ...) are not ranked.
    git diff -U0 "$MB" HEAD -- '*eslint.config.*' '*eslintrc*' "${EXCL[@]}" | awk '
      BEGIN { R["stricttypechecked"] = 4; R["strict"] = 3; R["recommendedtypechecked"] = 2; R["recommended"] = 1 }
      /^diff --git/ { file = $3; next }
      /^(---|\+\+\+)/ { next }
      /^[-+]/ {
        sg = substr($0, 1, 1); t = substr($0, 2); gsub(/\/\*[^*]*\*\//, "", t); sub(/(^|[ \t])(\/\/|#).*$/, "", t)
        while (match(t, /[-A-Za-z_@\/]+\.configs\.[A-Za-z]+|plugin:[-A-Za-z_@\/]+\/[-A-Za-z]+/)) {
          tok = substr(t, RSTART, RLENGTH); t = substr(t, RSTART + RLENGTH)
          if (tok ~ /^plugin:/) { g = tok; sub(/\/[^\/]*$/, "", g); p = tok; sub(/^.*\//, "", p); gsub(/-/, "", p) }
          else { g = tok; sub(/\.configs\.[A-Za-z]+$/, "", g); p = tok; sub(/^.*\./, "", p) }
          r = R[tolower(p)] + 0
          if (r) { k = file "|" g; if (sg == "-") { if (r > rem[k]) rem[k] = r } else if (r > add[k]) add[k] = r }
        }
      }
      END { for (k in rem) if (rem[k] > add[k] + 0) { print "guard: weaker lint preset: " k " (strictness " rem[k] " -> " add[k] + 0 ")"; bad = 1 } exit bad }' || fail=1
    narrowcheck "$MB"
    linecheck "$MB"
    # Screenshot references.
    # The list is read first: under pipefail `grep | grep -q` dies of SIGPIPE when more than one pipe buffer of paths matches (#251).
    gnames=$(git -c core.quotePath=false diff --name-only "$MB" HEAD)
    if [ "${GOLDEN_UPDATE:-0}" != 1 ] && grep -qE '(screenshots|golden|snapshots|roborazzi)/.*\.png$|src/[A-Za-z]*[Tt]est[A-Za-z]*/.*\.png$' <<<"$gnames"; then
      bad "screenshot references changed without the golden-update label"
    fi
    # Diff size outside generated files (docs count). Enforced in CI only.
    if [ "${CI:-}" = true ]; then
      max="${GUARD_MAX_DIFF:-600}"
      case "$max" in ''|*[!0-9]*) bad "GUARD_MAX_DIFF is not a number: '$max'"; max=600 ;; esac
      n=$(git diff --numstat "$MB" HEAD -- . ':!*.lock' ':!gradle/wrapper' ':!gradlew' ':!gradlew.bat' ':!gradle/verification-metadata.xml' ':!*package-lock.json' \
          ':!*.png' ':!*.jar' | awk '$1 != "-" {s += $1 + $2} END {print s + 0}')
      [ "$n" -gt "$max" ] && bad "diff is $n changed lines (limit $max); split the PR or ask the owner for the big-pr label"
    fi
  fi
fi

[ -s "$ERRF" ] && fail=1
[ "$fail" = 0 ] && echo "guards: ok"
exit "$fail"
