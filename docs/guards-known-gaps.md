# guards.sh: known gaps (issue 46)

`scripts/guards.sh` is line and diff based, and CODEOWNERS review of config files stays the real control. This page records what the
second batch of issue 46 added, and what it left out and why. Each addition has a positive and a negative case in
`scripts/hooks/test_guards_sh.py`.

## Policy: the `justified:` reason

Owner decision (issue 46): the reason needs at least 3 words of letters. A word is a run of 2 or more ASCII letters, so `-`, `x`, `ok`,
`two words` and `123 456 789` fail; Danish words count by their ASCII letters. Only the reason counts: it ends at a closing `*/` or `-->` and at the next comment opener (` # word`, ` // word`), so code or a
directive after it adds no words; `#46` and `http://` do not end it. The guard only counts. Reviewers judge whether the
reason is true and specific (`REVIEW.md`, item 8).

## Added

| Gap | Check |
|---|---|
| `coverageThreshold` (Jest), `fail_under` and `--cov-fail-under` (coverage.py) | the diff check for lowered or removed thresholds now names them |
| per-metric values on their own lines (`branches: 80,`) | the same check, in `jest`, `vitest` and `vite` config, `.nycrc` and `.c8rc` files only |
| config embedded in `package.json` (`eslintConfig`, `eslintIgnore`, `prettier`, `jest`, `nyc`, `c8`) | refused (`embedded config`), top-level keys only (nested `overrides` and `peerDependenciesMeta` entries are dependency data); JSON has no comment for a justification, so no escape hatch |
| `/* global foo */` | needs `justified:`; any block comment that starts with `global` or `globals` and a name, closed on the same line, in JS and TS files. ESLint reads `/* global state is kept */` as a directive too, so it is matched; an optional `-- description` is fine |
| `line-length` raised (ruff, flake8, `.editorconfig`, detekt, prettier `printWidth`) | diff check `raised line length`: per style file the largest value of the setting family (`line-length`, `max-line-length`, `max_line_length`, `maxLineLength`, `printWidth`; quotes and comments ignored) against the merge base, so an added setting counts like an edited one; a value such as `off` counts as no limit; a deleted file is compared with the style files of the same tool at `HEAD` (prettier, `.editorconfig`, detekt, ruff, flake8 kin) |
| `strictTypeChecked` to `recommended` and the other ESLint presets | diff check `weaker lint preset`, ranked per plugin (strictTypeChecked > strict > recommendedTypeChecked > recommended); a renamed import alias reads as a removal |
| ruff `select` shrinking | diff check `narrowed ruff select`: a head item that is a prefix of the removed one (`E` for `E4`, `PL` for `PLR`) or `ALL` covers it; no escape hatch |
| tsconfig `include` narrowing, `exclude` growing | diff checks; a dropped `include` entry has no escape hatch, a new `exclude` entry needs `justified:` on its own line |
| `skipLibCheck: true` | content check, needs `justified:` (cheap: it hides errors in declaration files, not in our code) |

## Not done, and why

- **Line length, where the check cannot compare.** A removed value below the tool default (ruff `line-length = 60` falls back to 88)
  loosens the check and is not caught. A base file without the setting is not compared, because the tool default is not known. The largest
  value per file is compared, so one setting raised while another in the same file is lowered by more is missed. The same setting family
  split over two files that both stay (a `line-length` in ruff.toml, a new `max-line-length` in pyproject.toml) is not compared across
  them. A raise below a larger value already in the same file is missed too: `[*.md] max_line_length = off` makes the base maximum "no
  limit", and the ktlint property `ktlint_standard_max-line-length = enabled` is read as a `max-line-length` value, so as no limit.
  Tracked in issue 176: compare the largest value per tool across all style files, once ruff and flake8 settings are mapped to their
  defaults.
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
