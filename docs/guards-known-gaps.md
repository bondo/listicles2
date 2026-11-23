# guards.sh: known gaps (issue 46)

`scripts/guards.sh` is line and diff based, and CODEOWNERS review of config files stays the real control. This page records what the
second batch of issue 46 added, and what it left out and why. Each addition has a positive and a negative case in
`scripts/hooks/test_guards_sh.py`.

## Policy: the `justified:` reason

Owner decision (issue 46): the reason needs at least 3 words of letters. A word is a run of 2 or more ASCII letters, so `-`, `x`, `ok`,
`two words` and `123 456 789` fail; Danish words count by their ASCII letters. Only the reason counts: it ends at a closing `*/` or `-->` and at the next comment opener (` # word`, ` // word`), so code or a
directive after it adds no words; `#46` and `http://` do not end it. It holds on every check that reads `justified:`, including the command-line flag check (2c, issue 45). The guard only counts. Reviewers judge whether the
reason is true and specific (`REVIEW.md`, item 8).

## Added

| Gap | Check |
|---|---|
| `coverageThreshold` (Jest), `fail_under` and `--cov-fail-under` (coverage.py) | the diff check for lowered or removed thresholds now names them |
| per-metric values on their own lines (`branches: 80,`) | the same check, in `jest`, `vitest` and `vite` config, `.nycrc` and `.c8rc` files only |
| config embedded in `package.json` (`eslintConfig`, `eslintIgnore`, `prettier`, `jest`, `nyc`, `c8`) | refused (`embedded config`), top-level keys only (nested `overrides` and `peerDependenciesMeta` entries are dependency data); JSON has no comment for a justification, so no escape hatch |
| `/* global foo */` | needs `justified:`; any block comment that starts with `global` or `globals` and a name, closed on the same line, in JS and TS files. ESLint reads `/* global state is kept */` as a directive too, so it is matched; an optional `-- description` is fine |
| `line-length` raised (ruff, flake8, `.editorconfig`, detekt, prettier `printWidth`) | diff check `raised line length` (issues 46, 176): every setting of the family (`line-length`, `max-line-length`, `max_line_length`, `maxLineLength`, `printWidth`; quotes and comments ignored; the ktlint rule switch `ktlint_standard_max-line-length` is not a limit) is read from all style files of the tool, at the merge base and at HEAD, and the largest value is compared per file, per tool, per tool and setting name, and per tool, setting name and section (an `.editorconfig` section or a TOML table). A raise therefore is not masked by a lowering of another setting or section, and a family split over two kept files is one group. A section that is new or renamed at HEAD, while the setting is already no limit at the base (`[*.md] max_line_length = off`), is compared with the largest finite base value, so `off` there fails. A value counts as a number only when its digits end at a delimiter; `off`, `1_60`, `0xA0`, `2e2` and `100 * 2` are no limit, and a value on the next line is read. CRLF and CR-only files, a BOM, and `/* */` comments after a value (prettier configs, also over several lines when the comment opens at the start of a line) are read. The files are not parsed, so the check fails closed: every value in a pyproject.toml, setup.cfg or tox.ini counts as the tool's, whatever table or spelling holds it (`[tool."ruff"]`, `tool.ruff.line-length`, an inline table, `[flake8]x`), so another tool's raise there (black, isort) fails too. A ruff or flake8 file that is in use (ruff.toml, a `[tool.ruff` table or `ruff.` key, `.flake8`, `[flake8]`) with no setting of its own counts the tool default (ruff 88, flake8 79) for that file, so a base without the setting, a removal below the default and a nearer ruff.toml without the setting are compared. Ruff's and flake8's own values and the default are also compared in groups of their own, so a wider black or isort value in the same file hides none of this. A file that is gone at HEAD is compared with the same tool's files at `HEAD`; a symlink is no limit; a non-ASCII path is read |
| `strictTypeChecked` to `recommended` and the other ESLint presets | diff check `weaker lint preset`, ranked per plugin (strictTypeChecked > strict > recommendedTypeChecked > recommended); a renamed import alias reads as a removal |
| ruff `select` shrinking | diff check `narrowed ruff select`: a head item that is a prefix of the removed one (`E` for `E4`, `PL` for `PLR`) or `ALL` covers it; no escape hatch |
| tsconfig `include` narrowing, `exclude` growing | diff checks; a dropped `include` entry has no escape hatch, a new `exclude` entry needs `justified:` on its own line |
| `skipLibCheck: true` | content check, needs `justified:` (cheap: it hides errors in declaration files, not in our code) |

## Not done, and why

- **Line length (issue 176 closed most of it).** Still not compared: prettier, `.editorconfig` and detekt have no default mapped, so a
  base without the setting and a removal from a kept file are not compared (the ktlint default depends on `ktlint_code_style`, detekt's
  `MaxLineLength` only applies when the rule is active). A setting removed from a kept ruff or flake8 file is compared with the default of that file, not with
  ruff's precedence: `lint.pycodestyle.max-line-length = 60` removed while `line-length = 100` stays loosens E501 and passes. Two values of
  one setting in one place (a second `printWidth` in a prettier file, such as an `overrides` entry, on any line) are one group, so a
  raise of one masked by a lowering of the other passes. A ruff file with `extend = "..."` gets no default (flake8 has no `extend`, so there it counts) and the extending file's own value is not compared with the value it inherits: ruff.toml `line-length = 160` and a nearer ruff.toml with only `select` (88) that gains `extend = "../ruff.toml"` passes (R2-04).
  A section that is new or renamed at HEAD may go up to the widest finite base value of the same tool and setting, because it has no base to compare with (R2-08). Deleting every ruff config passes (no tool in use, no
  default). A ruff setting in a spelling that the default logic does not know (a multi-line inline table, a root key with blanks or quotes such as `tool . ruff . line-length`) counts as a value but not as the file's own setting, so a removal below the default there is missed. A symlink is read as no limit, not through its target. A Gradle spotless ktlint `editorConfigOverride("max_line_length" to N)` and a detekt config not
  named `detekt.yml` are not read (issue 176, R4-01). ruff's default selection (no base `select`, or `extend-select` turned into
  `select`) and the tsconfig `"files"` list are not compared against a tool default either (issue 176, R4-02, the related narrowing gap).
- **A raised ESLint `max-len`**, a preset added that turns checks off (`tseslint.configs.disableTypeChecked`), and Vitest thresholds in a
  config file not named `jest|vitest|vite.config.*`, `.nycrc*` or `.c8rc*`.
- **ruff `select` is read from every table** of ruff.toml or pyproject.toml, so another table's `select = ["W"]` keeps `W` counted as present. The
  prefix rule is plain string prefix, so `E` is taken to cover `EXE`, which ruff treats as a separate linter.
- **A deleted or renamed config** is compared with every config of its kind at `HEAD`, so another tsconfig that still lists the dropped
  `include` entry hides it. Its base `exclude` entries are compared with the configs of that kind added in the same PR (a rename that adds an
  `exclude` entry needs a justification like any other).
- **Multi-line `extends` arrays and bases not named `*tsconfig*.json`**: the opener line is flagged and needs a justification today,
  which is the safe direction. Following `extends` to the base files needs a JSON parser, and no config here extends another one yet.
- **The ESLint option-object approximation** (`max: 1,` on its own line read as a severity): a false positive, never a miss; the
  justification on that line is a cheap fix. Telling an option object from a rule array needs a real parser.
- **`prettier` as a string in `package.json`** (`"prettier": "@scope/config"`): it looks like a dependency entry
  (`"prettier": "3.10.1"`). Not worth a false positive on every project; the dedicated config file stays the supported form.
- **Multi-line `/* global ... */` directives and a computed ESLint config**: a regex cannot see them.
- **Values split from their key** (`"strict":` then `false` on the next line), the YAML eslintrc form, a multi-line block directive, rarer
  mypy and ruff options, and the INI key case (comments on issue 46 from PR 43 review rounds 1 to 4): not done in this batch. They are
  small and independent, so a later batch can take them one at a time with tests.
- **Check settings moved into build-logic (M1-68 part A, PR 329 R2-01, accepted residual).** The next-line continuation check reads the
  first code line after the setting with only spaces and tabs stripped, and only `{` starts a lambda. So a labeled or annotated lambda on
  the next line (`useJUnitPlatform()` then `fast@{ includeTags("fast") }`), and a continuation after a form feed or lone CR (`= true`
  then `\f&& flag`), still count as the setting. These are not accidental forms; the guard is a tripwire (F18), and part B's per-module
  Test-task check (`checkTestSettings` in every module, `scripts/test_test_settings_gate.py`) closes the gap at build level.
- **Mentions the threshold scan lets through (task 1b, see #322; M1-68 part B; tests in `scripts/hooks/test_guards_mentions.py`).** Plural
  `thresholds` in markdown before `,` `;` `)`, a full stop or a word is prose even with a digit on the line, so `coverage thresholds are 80`
  in markdown is not compared. In a `.py` file that is no test file, `useJUnitPlatform` and `failOnNoDiscoveredTests` inside a `#` comment
  or a plain string are a mention: a gate's regex or message that pins them may be removed (the gate's own tests still count). A line
  inside a multi-line string reads as code, the safe direction, except its closing line, where the closing quotes can pair with a later
  quote (`doc""" if failOnNoDiscoveredTests else "x"` passes; in Python those names in code are no Gradle setting; PR 334 R1-02). Only
  `test_*.py` and `*_test.py` are test files: a `conftest.py` or shared fixture module that pins the strings is not (R0 self-review nit).
  Accepted residual (PR 334 R1-01, F18): Gradle runs an `apply(from = ...)` target that does not end in `.kts` as Groovy whatever its
  extension, and the guard reads every `.py` file as Python. So removing `tasks.withType(Test).configureEach { def h = /#/;
  useJUnitPlatform() }` from a `config/gradle/junit.py` that a build applies passes, and so do `def x = /'/; useJUnitPlatform(); def y = /'/`
  and `/* " */ useJUnitPlatform() /* " */`. The live setting was confirmed with `gradle --offline`. No `apply(from` target here is a `.py`
  file, and one would have to be set up on purpose. No Groovy lexer is added for it.

## Check 2c: command-line flags are an allowlist (issues 177, 174, 164)

Owner decision (issue 15, comments 7000552252 and 7002040979): the blocklist of PR 157 never converged (5, 2, 5 and 2 new gaps per review
round, and `ruff check --fix`, `--target-version` and a global option before the subcommand were still open). Check 2c now keeps one
allowlist per tool. A flag on an invocation of ruff, mypy, tsc, ESLint, Prettier, shellcheck or actionlint passes only when
`CLI_ALLOW` in `scripts/guards.sh` lists it for that tool, and its value passes the check of its kind. Any other flag fails unless the
logical line has a valid `justified:` reason (3 words, the policy above). New options of those tools therefore fail closed.

**The allowlists (one table, one reason per flag, in `scripts/guards.sh`).** A flag is listed only when it cannot make a run pass that
would otherwise fail: it switches a check on, says where a config or output goes, or only changes how findings print.

| Tool | Listed flags |
|---|---|
| ruff | `--config` (a 2b-scanned file), `--no-cache`, `--output-format`, `--version`; `check`: `--extend-select`; `format`: `--check`, `--diff` |
| mypy | `--config-file` (a 2b-scanned file), `--follow-imports` (`normal` or `error`), `--strict`, `--check-untyped-defs`, `--strict-equality`, `--strict-bytes`, `--extra-checks`, `--no-implicit-reexport`, `--no-implicit-optional`, `--warn-*`, `--disallow-*`, `--version` |
| tsc | `--noEmit`, `-p` and `--project` (a scanned tsconfig), `-b` and `--build` (every project argument checked), `--verbose`, `--force`, `--pretty`, `--outDir`, `--outFile`, `--version`, and the strict family unless set to false (`--strict*`, `--noImplicitAny`, `--noImplicitThis`, `--noImplicitReturns`, `--noImplicitOverride`, `--noUnused*`, `--alwaysStrict`, `--useUnknownInCatchVariables`, `--noUncheckedIndexedAccess`, `--exactOptionalPropertyTypes`, `--noFallthroughCasesInSwitch`, `--noPropertyAccessFromIndexSignature`, `--checkJs`) |
| ESLint | `--max-warnings 0`, `-c` and `--config` (a scanned file), `--rule` (severity `error` only), `--report-unused-disable-directives`, `--report-unused-disable-directives-severity` (`error` or `2`), `--no-inline-config`, `--prune-suppressions`, `--format` and `-f` (a built-in formatter: `stylish`, `json`, `json-with-metadata` or `html`; a formatter module is code), `--color`, `--no-color`, `--version` |
| Prettier | `--check`, `--write`, `--list-different`, `--config` (a scanned file), `--log-level`, `--version` |
| shellcheck | `-S` and `--severity` (`warning`, `info` or `style`, never `error`), `-x`, `-a`, `-o`, `-C`, `-f`, `-P` and their long forms, `--norc`, `--version`; short options may be combined |
| actionlint | `-shellcheck` and `-pyflakes` (the value must end in `shellcheck` or `pyflakes`: an empty value or a stub program such as `true` switches the integration off), `-color`, `-no-color`, `-oneline`, `-verbose`, `-format`, `-version` |

To add a flag: a line in `CLI_ALLOW` with its kind and reason, one allowed and one disallowed-value case in
`scripts/hooks/test_guards_cli_flags.py`, and this table. The owner reviews it, like any process file.

**What the redesign changed.**
- Abbreviated long options (mypy, shellcheck) are read as the listed option they abbreviate; an unlisted abbreviation fails.
- tsc option names are read case-insensitively, as tsc does (`--NoCheck` used to pass).
- A bare `--` ends the flags of a tool. The ruff subcommand is found among the arguments, so `ruff --config ruff.toml check --diff .` fails
  (issue 174, R5-01) while `ruff format --diff .` passes.
- actionlint: `-ignore`, an empty `-pyflakes=` or `-shellcheck=` and every unlisted flag fail; a non-empty `-shellcheck=<path>` passes
  (issue 164 item 1). The wrapper in `scripts/install_linters.sh` carries a `justified:` reason for its `-pyflakes=`. The `ignore:`
  entries of the actionlint config (`actionlint.yaml` or `actionlint.yml` in `.github/`) are read by 2b: the `ignore:` line and every
  `- entry` of its block list need a reason, also when the key is quoted or written as a flow, and after an anchor or a tag
  (`ignore: &a`, `ignore: !!seq`); an `ignore:` whose value is an alias (`*name`) fails with no escape hatch, because 2b cannot follow it, and so does a double-quoted key written with an escape (`"ign\x6Fre":`).
- Makefiles (`Makefile`, `makefile`, `GNUmakefile`, `*.mk`), `.github/actions/*` and `.pre-commit-config.yaml` are scanned too (issue 164 item 2; recipe prefixes `@`, `+` and `-`, with blanks between them, are stripped before the lookup, and the `-` prefix, which makes make ignore the exit status, is not checked).
- YAML args keys (issue 164 item 2): a sequence item (a workflow step or a pre-commit hook) is read as a whole, in any key order. Its
  `uses:` (an action whose name contains the tool, such as `astral-sh/ruff-action` or `docker://rhysd/actionlint`), or in pre-commit
  config its `entry:` or `id:` (`ruff` and `ruff-check` run `ruff check`, `ruff-format` runs `ruff format`), gives the command, and each
  of its args-like keys (`args`, `extra_args`, `flags`, `options`, or a key that starts with the tool name such as `eslint_flags`; not
  `reviewdog_flags`; at any depth, quoted or not, in any letter case, also after a bare `-` line) holds that command's flags, inline, as
  a flow or block list (a flow list splits on every comma outside quotes, `[.,--fix]`), in a flow mapping (`- {id: ruff, args: [--fix]}`, `with: {args: check}`) or a block scalar. A reason waives
  its own line only: the lines of a key that have no reason are checked together. A double-quoted key written with an escape (`"ar\x67s":`)
  fails unless its line has a reason, because it may spell any key. This only adds failures to the line scan.
- False positives removed: `uvx mypy@1.15`, `tsc -b > build.log` (issue 164 item 5) and `tsc --outFile dist/out.js` (item 4), and tools that
  are being installed (`pip install ruff --upgrade`, `npm i -D eslint --save-exact`, `cargo install`, `go install`).

**Still not covered, or a new cost.**
- A flag after `--` of `npm`, `npx` and kin is checked, also when the line names the tool (`npm run lint:eslint -- --quiet`), and passes
  when any of eslint, prettier and tsc lists it (tsc names read case-insensitively), unless the tail is known to reach a test runner
  (next section). So `npm run build -- --watch` with `build` running `node build.mjs` still needs a `justified:`.
- YAML values over several lines (task M1-64, issue 164 item 2): see "Check 2c: YAML values over several lines" below for what the joined-line check leaves out.
- Flags held in shell variables, tools run from Python (subprocess), and yarn, pnpm or bun forms without `--` (`bun run lint --quiet`).
- A tool named as an argument of an installer is skipped by its first words; `xargs pip install` style wrappers are not recognised.
- YAML args keys: a job-level reusable workflow (`uses: org/x/.github/workflows/ruff.yml@v1` with `with: args:`) is not a sequence item;
  other inputs of a lint action (`severity:`, `ignore_paths:`, `fail_on_error:`, `reviewdog_flags:`) are not read; a `${{ }}`
  expression or a YAML alias in an args key is not followed; a step item `- &anchor` or `- !!map` with its keys on the next lines is
  not read (PR 309 R2-07). An actionlint `ignore:` alias whose name starts with `-` (`*-l`) is not detected (R2-06).
- A tool name held in a Make or shell variable (`$(RUFF) check --ignore E501 .`), and a flag hidden by shell escapes (`eslint \--quiet .`, `eslint $'--quiet' .`).
- Installer commands are matched by their subcommand (`pipx install`, `conda install`, `apt-get install`); `pipx run` and `conda run`
  run the tool, so they are scanned. A tsc `@response-file` fails, because the options inside it cannot be read. Because the rule covers the
  whole eslint, prettier and tsc union, any `@` word after an npm `--` fails too (`npm run build -- @scope/pkg`, `npm exec -- @commitlint/cli --edit`),
  and needs a `justified:`; `npx @scope/tool` without `--` passes. A segment with a `--` tail after npm, yarn, pnpm or bun is never an installer, and the
  npm script verbs (`test`, `t`, `tst`, `start`, `stop`, `restart`, `run`, `rum`, `urn`, `run-script`, `exec`, `x`) are read as runs.

## Check 2c: an npm `--` tail resolved through package.json (task M1-65, issue 164 item 3)

Escalation ruling on PR 309 (comment 7084379032): fail closed by construction. npm appends the tail to the last command of the script, so
a tail that reaches a test runner skips the eslint, prettier and tsc union check, and every other tail keeps it, as before. It skips only when:
- the command is an npm form: a bare `npm` is the first word (a path such as `./bin/npm` or a prefix such as `sudo` is not), then
  only `-s`, `--silent`, `-q`, `--quiet`, `--if-present` or `--ignore-scripts`, and `test`, `t` or `tst` (script `test`) or `run`, `rum`, `urn` or `run-script` with a name, and nothing else before the `--`. yarn, pnpm and
  bun forms (`yarn t` runs script `t`, not `test`: C1, C2), `npx`, `npm exec`, an npm option that takes a value (`--prefix x`,
  `--workspace=x`), an env prefix and `npm start` are never resolved;
- every tracked package.json (under excluded paths such as `docs/` or `node_modules/` too; one that cannot be read is unknown) that
  defines the script reads it from the one strict layout (`pkgscripts`): the file's only `"scripts"` token on a line of its own as `"scripts": {`, then one `"name": "command",` per line up to a `}` line. Any other `"scripts"` token
  (a split key, R4-01 and N1 to N4; a second or nested object; the word as a value), any other line in the object, and any `\u` escape
  in any package.json make every tail unknown. The depth is not counted: a file whose only `"scripts"` object is nested has no npm
  scripts, so npm runs none of the names read from it;
- every definition is one plain `[npx] <runner> <words>` and nothing else, the runner one of jest, mocha, playwright and cypress: no
  command before it (a shell function, a `PATH=` assignment or a copy over the runner's file could make the name run a linter), so
  `tsc --noEmit && jest` is not resolved, and no `;`, `&`, `|`, quote, `$`, backtick, bracket, redirection, `#`, `~` or backslash.
  firebase is no such runner (`emulators:exec` runs its argument as a command), and nor is vitest (its typecheck mode runs tsc).

**Not covered, or a new cost.**
- A resolved tail skips the union check; its runner options are read by check 1 on command lines (next section, task M1-71).
- A `\u` anywhere in a package.json, a value included (`"description": "caf\u00e9"`), makes every tail unknown: a false positive, never
  a miss (PR 309 R3-03, accepted). The repo's own `firebase/package.json` `test` script (firebase, with escaped quotes) is not resolved.
- Only tracked package.json files are read. A command run where an untracked one decides (`node_modules`, a generated file), and npm
  settings from `.npmrc` or `npm_config_*` (`script-shell`), are not followed.

## Check 1 on command lines: test-runner options (task M1-71)

Owner decision (issue 15, comment 7092471489). `runopt` in the 2c scan (same files, same logical lines, the joined YAML lines too) fails
a jest, vitest or mocha command that rewrites or skips tests, with no `justified:` escape hatch, like the rest of check 1:
- rewrite and skip-all: `-u`, `--updateSnapshot` (vitest `--update`), `--passWithNoTests`;
- name and path filters: `-t`, `--testNamePattern`, `--testPathIgnorePatterns`, `--testPathPattern(s)` (what a positional jest word sets),
  positional path filters, mocha `--grep`, `-g`, `--fgrep`, `-f`, `--invert`, `-i`, the path excludes `--exclude` (vitest, mocha) and
  `--ignore` (mocha), a jest `--filter` module, and a jest config given as inline JSON (`-c` or `--config` with a value that starts with
  `{`, which no config scan reads);
- changed-only: jest `-o`, `--onlyChanged`, `--changedSince`, `--findRelatedTests`, `--lastCommit`, `-f`/`--onlyFailures`, vitest `--changed`.

`--shard` passes (kept for CI splitting). Names past the decision's list (`--testPathPattern(s)`, `--lastCommit`, `--onlyFailures`,
`--exclude`, `--ignore`, `--filter`, inline JSON config, mocha `-f` and `-i`) are spellings or siblings of the listed ones, denied because that is the fail-closed side.

**How it reads a command.** Long names are compared in lower case without dashes, as yargs (jest, mocha) and cac (vitest) accept
kebab-case for camelCase (`--pass-with-no-tests`), with or without `=value`. Short options are per runner, because they clash (jest `-t` is
the name filter, mocha `-t` is `--timeout`; jest `-i` is `--runInBand`, mocha `-i` is `--invert`), and may be grouped (`-iu`). A
group is read as yargs-parser (jest, mocha) reads it (R1-01): every character is a flag, digits included, until one takes the rest of
the group as its value, which happens only when the rest starts with `=`, is a number (after a letter: `-w2`), or starts with a
character that is no word character. So `-wu`, `-w2u`, `-1u` and `-x9u` all set `-u`. mri (vitest, and a tail resolved to a runner
the check does not know) reads every character of a single-dash word before `=` as a flag. A word that starts with a dash is skipped only as a negative
number (`--seed -1`). A one-letter long option (`--u`, mocha `--g smoke`) is that short option, as both parsers read it (R1-02).
Positional words are path filters after jest, and after vitest except a first `run`, `watch` or `dev` (`vitest related`, `list` and
`bench` fail), when the runner is the command: the first word after a YAML `- key:` or a package.json key, `VAR=` assignments (a
quoted value may hold blanks: `FOO="a b" jest src`), shell keywords (`if`, `then`, `do`, `while`, `until`, `else`, `!`, `{`, `(`,
`$(`) and launchers with their options (`npx --yes`, `npm exec`, `yarn run`, `bun run`, `pnpm exec`, `bunx`, `node --flag path/jest.js`,
`env -u X`, `sudo -u bob`, `nice -n 5`, `timeout -s KILL 60`; a one-letter option's value and a number are skipped). The runner word
may carry a path, `@version` (`npx jest@30`) or `.js` (R1-03). In a package.json a command ends with its JSON string value, and
every script value on a line is read (`{ "test": "jest --ci", "e2e": "jest src" }`). A mocha
positional word is its spec and passes. After a bare `--` every word is positional. The value of an option listed in `RVL` or `RVS`
(`--maxWorkers 2`, `-c jest.config.cjs`, `--shard 1/3`, mocha `-t 5000`) is no positional word; the value of any other option is, so
write it with `=` (`--testSequencer=./seq.js`): a false positive, never a miss. Redirections and their targets are skipped.

**npm `--` tails.** A tail that M1-65 resolves (every definition of the script a plain `[npx] jest|mocha ...`) is read with that runner's
short options, and its positional words fail (for mocha too, and its `--spec`: a spec in the tail may replace the configured one). A tail that is not
resolved is read with the long names only and fails with no escape hatch; its short options are ambiguous across tools (`-t` is tsc
`--target`, `-f` is the ESLint formatter), so 2c keeps checking them as before, waivable by a reason.

**Not covered (tripwire, F18).**
- A runner inside a quoted command string (`firebase emulators:exec "jest src"`, `bash -c "jest src"`) has its options read but not its
  positional words; nor does a runner held in a variable (`$JEST src`), one after a launcher option whose value is not one word
  directly after a one-letter option (`sudo --user=bob` passes, `sudo --user bob jest src` reads `bob` as the command), one after a
  wrapper the list does not name (`xargs jest`, `watch jest`, `cross-env CI=1 jest src`, `nyc --reporter=lcov jest src`,
  `c8 vitest run src`, `dotenv -e .env -- jest src`, `yarn workspace app jest src`, `pnpm --filter app exec jest src`,
  `stdbuf -oL jest src`, a `case` arm `a) jest src;;`), or a runner run from a Python or JS file. Their options are still read (PR 339
  R2-03, accepted residual).
- vitest (mri) reads a word with three or more dashes as a short group: `vitest run ---u` and `---t=smoke` pass the guard, which reads
  every `--` word as a long name (PR 339 R2-01, accepted residual). jest and mocha (yargs) do not read `---u` as `-u`.
- Options that weaken a run without filtering it: jest `--ci=false` (writes new snapshots), `--bail`, `--listTests`, `--watch` (only
  changed tests; it does not end in CI), vitest `--allowOnly`, dot options (`--coverage.*`, `--typecheck.only`), `--project`, jest
  `--selectProjects`, `--roots`, `--testMatch`, `--testRegex` (the last three are refused in config by check 1), and a command whose
  exit status is dropped (`jest || true`). vitest `--dir` and `--root` and jest `--rootDir` fail only when their value is a separate
  word (read as a path filter); written with `=` they pass.
- playwright and cypress: next section (task M1-81).
- yarn, pnpm and bun tails are never resolved (M1-65), so only their long runner options fail with no escape hatch. Their forms
  that pass arguments to the script without `--` (`yarn test --passWithNoTests`, `pnpm test -u`, `pnpm run test --passWithNoTests`) are
  not read at all, as in 2c (the repo is npm-only).
- A runner name used as data on a command line (`echo jest -u`) fails: a false positive.


## Check 1 on command lines: playwright and cypress (task M1-81)

Owner decision (issue 15, comment 7102820038: the full proposal of PR 358 comment 7102517597). `runopt` reads `playwright test` and
`cypress run` in the same places as jest (direct, after launchers, package.json scripts, YAML, quoted commands for options) and fails,
with no escape hatch:
- playwright: `-u`, `--update-snapshots` (any mode), `--ignore-snapshots`, `--pass-with-no-tests`, `--list`, positional file filters
  after `test`, `-g`, `--grep`, `--grep-invert` (`-gv`), `--test-list`, `--test-list-invert`, `--no-deps`, `--last-failed`,
  `--only-changed` (with or without a ref), and `-c` or `--config` whose value is no file named `*.config.{ts,js,mts,mjs,cts,cjs}` (a
  test directory there narrows `testDir`);
- cypress: `-s`, `--spec`, positional words after `run`, `-c` or `--config` whose value names `specPattern` or `excludeSpecPattern`
  (any case and nesting), and `-e` or `--env` whose value names a @cypress/grep key (`grep`, `grepTags`, `grepInvert`, `grepUntagged`,
  `grepFilterSpecs`, `grepOmitFiltered`: a key is `grep` and letters before `=` or `:`).

`--shard` and the other options of the proposal pass. Both CLIs use commander, so the guard reads short groups as commander does: every
letter is a flag until one that takes a value, which takes the rest (`-xu` sets `-u`, `-gsmoke` is `-g smoke`, `-j2 src` has the path
filter `src`). The value-taking long names are their own (`RVX`: `--workers`, `--project`, `--browser`, `--record`, ...), not jest's, so
`--ui` takes no value after playwright. A quoted value, or one with an escaped blank, is one word for every runner (`--project "Mobile
Chrome"`, `--group "UI - Chrome"`, a JSON `--env '{"grep": "x"}'`; in a package.json the `\"` quotes), so its second word is no path
filter (PR 358 R0-01). `npx @playwright/test test` is playwright. The denied long names join the shared list, so an unresolved tail
fails on them too, and so do `jest --list` and `mocha --no-deps`, which those runners refuse anyway (intended: the fail-closed side). A
tail resolved to them is read with their own letters and positional rule (jest letters there are no longer denied: `npm run e2e -- -o`
passes, commander refuses it). A tail resolved to two runners with different parsers is read as mri, the strictest.

**Not covered (tripwire, F18).**
- Known gaps by the decision: playwright `--project` and `--retries`, cypress `--component`, `-P`/`--project` (another project
  directory), `-C`/`--config-file` (another config file), `--config` keys other than the two spec patterns (`retries`, `testIsolation`),
  and `CYPRESS_*` env assignments (`CYPRESS_grep=smoke`, `CYPRESS_SPEC_PATTERN=x`). Check 1 reads neither runner's config file
  (playwright `grep`, `grepInvert`, `testIgnore`, `testMatch`, `retries`; cypress `specPattern`), nor `PWTEST_*` env.
- Other subcommands (`playwright show-report`, `merge-reports`, `install`, `codegen`; `cypress open`, `install`, `verify`, `cache`,
  `info`) are not read as test runs, nor are their options: `cypress open --spec x` passes. Every mention of playwright or cypress
  (a quoted command, a wrapper) is read only when the test subcommand follows it, so a path that names the runner passes
  (`eslint e2e/playwright -c .eslintrc.json`, `ls cypress/fixtures -s`; PR 358 R0-02). A playwright `-c` with no value passes
  (commander refuses it).
- An unresolved tail (yarn, pnpm, bun, or a script that is no plain runner) is read with the long names only: cypress `--spec` (mocha
  passes its own `--spec`), the playwright `-c` file check and the cypress `--config` and `--env` key checks are not applied there
  (`yarn e2e -- --config=tests/e2e`, `yarn cy -- --env grep=smoke`); 2c still fails them, waivable by a reason (R0-04).
- A runner after a wrapper the list does not name (`xargs npx playwright test login`) has its options read, not its positional words,
  as for jest.

## Check 2c: YAML values over several lines (task M1-64, issue 164 item 2)

Escalation ruling on PR 309 (comment 7084379032): the joined line is checked IN ADDITION to the per-line check, never instead of it.
`cliflags` runs the 2c scan twice on every YAML file: on the file, as before, and on the text `YFOLD_AWK` prints, where each value that
goes on over several lines is one line, as the runner reads it. A failure of either run fails, so the joined check only adds failures.

**What is joined.** A plain scalar (lines indented more than its key, up to a comment line or a less indented line; also when the value
starts on the line after the key, R2-05), a single- or double-quoted scalar (until it closes, at any indentation), a flow collection
(`- {name: a, run: ruff check` over lines, `with: {args:`), and the lines of equal indentation of a folded block (`run: >`, any
chomping or indentation indicator, after an anchor or a tag; R2-04). A blank line is a line break, so it starts a new line; in a
folded block so is a change of indentation (YAML keeps the breaks around a more-indented line). Double-quoted escapes are decoded
(`\x2d`, `\u002d`, `\t`, `\"`; `\n` is a command separator; an escaped line break joins with no blank; other escapes are a character that is
no blank), also after a node property (`&a`, `!!str`) and in a JSON-style flow (`{"run":"..."}`). The YAML quotes are dropped in block
context and kept in a flow collection, where an args list splits on commas outside quotes. A fold scan that cannot run fails the guard. A pre-commit `entry:` is split into words by pre-commit, so its whole value, a literal block
(`entry: |`) too, is one line on the key line, and a `#` in its block is a word. A literal block (`run: |`) is not joined: its lines are
shell lines.

**Reasons.** A reason waives a joined value only when every line of it has one (Y1, Y3 and Y5 of the ruling, R2-01). A reason in a
comment ends a plain value, so a plain value over several lines cannot carry one on each line: write a justified command on one line,
or as a folded block with the reason on each line.

**Not covered, or a new cost.**
- A shell quote that spans a YAML line break (`ruff check '` and `' --ignore E501 .` around a blank line, in a folded block or a literal
  block) leaves the tool and the flag on two lines; the same holds in a shell script. The line scan has no shell parser.
- A reason on one line of a folded block does not waive it, even when its `#` makes the shell drop the rest (`ruff check --ignore E501 .
  # justified: ...` and then `&& echo ok`): a false positive the per-line check did not have; put the reason on each line.
- A run of equally indented lines of a folded block that are more indented than the block's own lines (`echo a` and then
  `  ruff check` and `  --ignore E501 .`, or every line with an explicit indicator such as `run: >1` at +3) is joined although YAML
  keeps the breaks: a false positive, never a miss. A flow mapping joined over lines lets a flag in another entry count for
  the tool (`- {run: ruff check, name: x` and `--fix}`), as on one line.
- The single-line forms that the per-line check reads as before still pass there; the joined run reads them decoded, so a double-quoted
  `"ruff check \x2d-fix"` now fails.
- Complex keys (`? run` and `: value` over lines) are read as plain lines.
- A one-line double-quoted value whose reason exists only after escape decoding (`"ruff check \x2d-fix \x6austified: three words here"`)
  passes: a reason is cleared only from a value joined over several lines. It takes two deliberate escapes; accepted residual of
  PR 325 review round 1 (R1-04, the guard is a tripwire, F18), not a regression from main, which does not decode at all.

