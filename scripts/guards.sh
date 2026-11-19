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
[ "$STAGED" = 1 ] && LS=(git diff --cached --name-only --diff-filter=AMRT) # added, modified, renamed (new path) and type-changed (file to symlink)

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
# and on the first element of an ESLint rule array that sets off/warn/0/1.
ENTRY_AWK='
function strip(l) { sub(/[ \t]*(#|\/\/).*$/, "", l); return l }
function blank(l) { gsub(/"[^"]*"/, "\"\"", l); gsub(/\047[^\047]*\047/, "\047\047", l); return l }
function nest(l,   t, o) { t = l; gsub(/[^[({]/, "", t); o = length(t); t = l; gsub(/[^])}]/, "", t); return o - length(t) }
function check() { if (!just(line)) printf "%s:%d:%s\n", F, NR, line }
BEGIN { ini = (F ~ /(\.ini|\.cfg|\.flake8|\.coveragerc)$/); es = (F ~ /eslint/) }
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
  cfgcheck 'requirePragma["'"'"']?[[:space:]]*[:=][[:space:]]*true|ignore-?[Pp]ath' '*prettierrc*' '*prettier.config.*')
[ -n "$out" ] && { echo "$out"; fail=1; }

# 2c. Command-line flags on tool invocation lines (issues 45 and 177): ruff, mypy, tsc, ESLint, Prettier, shellcheck and actionlint, in shell
# scripts, git hooks, CI workflows, composite actions, Makefiles, pre-commit config and package.json. Per-tool ALLOWLIST (owner decision, #15):
# a flag passes only when CLI_ALLOW below lists it for that tool (ruff: for that subcommand) and its value passes the check of its kind.
# Any other flag, listed or not by anyone before, fails unless the logical line has one `justified: <reason>` (3 words, just() above), which waives
# every command on the line. A backslash continuation is one logical line; it loses its unquoted trailing ` # comment` and is split at ; & | so
# a flag only counts for the tool in its own command; only the text after the tool name is read (`grep -i shellcheck` has no flag), and a bare
# `--` ends the flags. A tool named as the thing being installed (`pip install ruff --upgrade`, `npm i -D eslint`, `cargo install`) is not run, so datacmd skips it.
# For npm and npx (and yarn, pnpm, bun and bunx when they use `--`) the JS tools also see what follows a bare `--` (`npm run lint -- --quiet`): a flag
# there passes when ANY of eslint, prettier and tsc lists it, because the script that runs is not known, so `npm test -- -u` needs a `justified:`
# too (issue 164 item 3). The options of npm itself never count. Flags may be quoted, shellcheck short options may be combined (-xS warning),
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
# Not covered: action `with: args:` lines, YAML folded scalars (`run: >`), a `.github/actionlint.y*ml` config (2b does not read it), flags held in
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
  dd = ddseg(p)
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
function flush(   n, i, parts, j) {
  if (cur == "") return
  j = just(cur)
  n = split(stripc(cur), parts, /[;&|]+/)
  if (F ~ /([Mm]akefile|\.mk)$/) for (i = 1; i <= n; i++) sub(/^[ \t@+-]+/, "", parts[i])  # recipe prefixes: silent, always run, ignore errors
  for (i = 1; i <= n; i++) if (baseline(parts[i]) || (!j && relaxed(parts[i]))) { printf "%s:%d:%s\n", F, start, cur; break }
  cur = ""
}
BEGIN { TSOK = "((^|/)(\\.\\.?|[^./= \t]+)/?$)|((tsconfig|jsconfig)[^/= \t]*\\.json$)"
  SP = "(^|[ \t])[\"\047]?"; cur = ""; cont = 0
  RUFFSUB = "^(check|format|rule|config|linter|clean|server|analyze|version|help|generate-shell-completion)$"
  SRCRE = "^[^-][^=]*\\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$"; SEVOK = "^(warning|info|style)$"; COLOROK = "^(always|never|auto)$"
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
    if [ "$STAGED" = 1 ]; then git show ":$f" 2>/dev/null | CLI_ALLOW="$CLI_ALLOW" LC_ALL=C awk -v F="$f" "$JUSTFN$CLI_AWK"
    else CLI_ALLOW="$CLI_ALLOW" LC_ALL=C awk -v F="$f" "$JUSTFN$CLI_AWK" "$f" 2>/dev/null; fi
  done < <(git ls-files -- "$@" "${EXCL[@]}") | sed 's/^/guard: unjustified CLI flag: /'
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
out=$("${LS[@]}" | grep -iE 'baseline|(^|/)eslint-suppressions\.json$')
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

# 7. A raised line length (owner decision in #46). Per style config file the largest value of the setting family (line-length,
# max-line-length, max_line_length, maxLineLength, printWidth; quotes and comments ignored, a word such as `off` counts as no limit)
# is compared with the same file at the merge base, so an added setting counts as well as an edited one. A deleted file (rename or
# move) is compared with the largest value in the style files of the same tool at HEAD (prettier, editorconfig, detekt, ruff, flake8
# and their kin each form one group). Lowered or removed is stricter and passes. Not compared: a base
# without the setting (the tool default is not known), and the same family split over two files when neither is deleted.
STYLERE='(ruff\.toml|pyproject\.toml|\.flake8|setup\.cfg|tox\.ini|\.editorconfig|detekt\.yml|prettierrc[^/]*|prettier\.config\.[^/]*)$'
LL_AWK='{ lo = tolower($0); sub(/(^|[ \t])(#|;|\/\/).*$/, "", lo)
  while (match(lo, /(max[-_]?line[-_]?length|line[-_]?length|printwidth)["\047]?[ \t]*[:=][ \t]*["\047]?/)) {
    lo = substr(lo, RSTART + RLENGTH); if (lo ~ /^[ \t]*$/) continue  # a YAML parent key (`MaxLineLength:`) has no value
    v = match(lo, /^[0-9]+/) ? substr(lo, 1, RLENGTH) + 0 : 999999999; if (!f || v > m) m = v; f = 1 } }
  END { if (f) print m }'
stylekind() { # the style files of the same tool as <path>
  case "$1" in
    *prettierrc*|*prettier.config.*) echo 'prettierrc[^/]*$|prettier\.config\.[^/]*$' ;;
    *.editorconfig) echo '\.editorconfig$' ;;
    *detekt.yml) echo 'detekt\.yml$' ;;
    *ruff.toml|*pyproject.toml) echo 'ruff\.toml$|pyproject\.toml$' ;;
    *) echo '\.flake8$|setup\.cfg$|tox\.ini$' ;;
  esac
}
linemax() { git show "$1" 2>/dev/null | LC_ALL=C awk "$LL_AWK"; }
linecheck() { # linecheck <merge-base>
  local mb="$1" f g b h kind
  while IFS= read -r f; do
    git cat-file -e "$mb:$f" 2>/dev/null || continue
    b=$(linemax "$mb:$f"); [ -n "$b" ] || continue
    if git cat-file -e "HEAD:$f" 2>/dev/null; then h=$(linemax "HEAD:$f")
    else kind=$(stylekind "$f"); h=$(while IFS= read -r g; do linemax "HEAD:$g"; done < <(git ls-tree -r --name-only HEAD | grep -E "$kind") | sort -n | tail -1); fi
    [ -n "$h" ] && [ "$h" -gt "$b" ] && bad "raised line length: $f: $([ "$b" -gt 99999 ] && echo "no limit" || echo "$b") -> $([ "$h" -gt 99999 ] && echo "no limit" || echo "$h")"
  done < <(git diff --name-only --no-renames --diff-filter=MD "$mb" HEAD -- . "${EXCL[@]}" | grep -E "$STYLERE")
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
      # coverageThreshold (Jest) and fail_under / --cov-fail-under (coverage.py) are named like thresholds but not spelled `threshold`.
      # In a Jest, Vitest, nyc or c8 config the per-metric values sit on their own lines (`branches: 80,`), so those lines count too.
      kw ~ /(minBound|mutationThreshold|threshold|coverageThreshold|fail[-_]under|failOnNoDiscoveredTests|useJUnitPlatform|error *\+?=|fatal *\+?=|warningsAsErrors|maxIssues|failOnSeverity)/ ||
      (file ~ /(jest|vitest|vite)\.config\.[^\/]*$|nycrc[^\/]*$|c8rc[^\/]*$/ && kw ~ /^[-+][ \t]*["\047]?(branches|functions|lines|statements)["\047]?[ \t]*:[ \t]*[0-9]/) {
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
    if [ "${GOLDEN_UPDATE:-0}" != 1 ] && git diff --name-only "$MB" HEAD \
      | grep -E '(screenshots|golden|snapshots|roborazzi)/.*\.png$|src/[A-Za-z]*[Tt]est[A-Za-z]*/.*\.png$' | grep -q .; then
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
