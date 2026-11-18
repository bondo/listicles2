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

# 2c. `/* global foo, bar:writable */` (ESLint) switches off no-undef for the names. Any block comment that starts with `global` or
# `globals` and a name, closed on the same line, in a JS or TS file: that is how ESLint reads it (names split on commas and spaces, an
# optional `-- description`), so `/* global state is kept */` is a directive too. A multi-line comment is not matched.
out=$(gg '/\*[[:space:]]*globals?[[:space:]]+[A-Za-z_$][^*]*\*/' \
  -- '*.js' '*.mjs' '*.cjs' '*.jsx' '*.ts' '*.mts' '*.cts' '*.tsx' '*.vue' "${EXCL[@]}" | unjust)
[ -n "$out" ] && { echo "$out" | sed 's/^/guard: unjustified suppression: /'; fail=1; }
# 2d. Linter, formatter and test config embedded in package.json is not scanned by the checks above (and ESLint 9 ignores eslintConfig).
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
narrowcheck() { # narrowcheck <merge-base>
  local mb="$1" f g re kind base head k it ln
  while IFS= read -r f; do
    git cat-file -e "$mb:$f" 2>/dev/null || continue
    case "$f" in
      *ruff.toml|*pyproject.toml) re='(extend-)?select'; kind='ruff\.toml$|pyproject\.toml$' ;;
      *) re='include|exclude'; kind='(ts|js)config[^/]*\.json$' ;;
    esac
    base=$(listitems "$re" "$mb:$f")
    # A deleted file (a rename or a move shows as delete plus add) is compared with the items of every file of its kind at HEAD.
    if git cat-file -e "HEAD:$f" 2>/dev/null; then head=$(listitems "$re" "HEAD:$f")
    else head=$(while IFS= read -r g; do listitems "$re" "HEAD:$g"; done < <(git ls-tree -r --name-only HEAD | grep -E "$kind")); fi
    while IFS=$'\t' read -r k it ln; do
      [ -n "$k" ] || continue
      if printf '%s\n' "$head" | cut -f1,2 | grep -qxF -- "$k"$'\t'"$it"; then continue; fi
      if [ "$k" = select ]; then printf '%s\n' "$head" | cut -f1,2 | grep -qxF -- select$'\t'ALL || bad "narrowed ruff select: $f: $it was removed"
      elif [ "$k" = include ]; then bad "narrowed tsconfig include: $f: $it was removed"; fi
    done <<<"$base"
    git cat-file -e "HEAD:$f" 2>/dev/null || continue
    while IFS=$'\t' read -r k it ln; do
      [ "$k" = exclude ] || continue
      if printf '%s\n' "$base" | cut -f1,2 | grep -qxF -- "$k"$'\t'"$it"; then continue; fi
      [ -n "$(printf '%s\n' "$ln" | unjust)" ] && bad "widened tsconfig exclude: $f: $it was added without a justified: reason"
    done <<<"$head"
  done < <(git diff --name-only --no-renames --diff-filter=MD "$mb" HEAD -- '*ruff.toml' '*pyproject.toml' '*tsconfig*.json' '*jsconfig*.json' "${EXCL[@]}")
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
      # A raised line length is a weaker style check (owner decision in #46); lowered or removed is stricter and passes. Style config files only.
      # Keyed by file and setting name (several settings may share a line); the value is the number after `=` or `:`, a word such as
      # `off` counts as unlimited. Per key the smallest removed value is compared with the largest added one.
      file ~ /(ruff\.toml|pyproject\.toml|\.flake8|setup\.cfg|tox\.ini|\.editorconfig|detekt\.yml|prettierrc[^\/]*|prettier\.config\.[^\/]*)$/ && tolower($0) ~ /(line[-_]?length|printwidth)/ {
        lo = tolower(substr($0, 2))
        while (match(lo, /(max[-_]?line[-_]?length|line[-_]?length|printwidth)["\047]?[ \t]*[:=][ \t]*/)) {
          k = substr(lo, RSTART, RLENGTH); sub(/["\047]?[ \t]*[:=][ \t]*$/, "", k); gsub(/[-_]/, "", k); k = file "|" k
          lo = substr(lo, RSTART + RLENGTH); v = match(lo, /^[0-9]+/) ? substr(lo, 1, RLENGTH) + 0 : 999999999
          if (substr($0, 1, 1) == "-") { if (!(k in llrem) || v < llrem[k]) llrem[k] = v } else if (!(k in lladd) || v > lladd[k]) lladd[k] = v
        }
      }
      END {
        for (k in llrem) if (k in lladd && lladd[k] > llrem[k]) { print "guard: raised line length: " k " (" llrem[k] " -> " (lladd[k] > 99999 ? "no limit" : lladd[k]) ")"; bad = 1 }
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
