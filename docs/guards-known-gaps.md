# guards.sh: known gaps (issue 46)

`scripts/guards.sh` is line and diff based, and CODEOWNERS review of config files stays the real control. This page records what the
second batch of issue 46 added, and what it left out and why. Each addition has a positive and a negative case in
`scripts/hooks/test_guards_sh.py`.

## Policy: the `justified:` reason

Owner decision (issue 46): the reason needs at least 3 words of letters. A word is a run of 2 or more ASCII letters, so `-`, `x`, `ok`,
`two words` and `123 456 789` fail; Danish words count by their ASCII letters. The guard only counts. Reviewers judge whether the
reason is true and specific (`REVIEW.md`, item 8).

## Added

| Gap | Check |
|---|---|
| `coverageThreshold` (Jest), `fail_under` and `--cov-fail-under` (coverage.py) | the diff check for lowered or removed thresholds now names them |
| per-metric values on their own lines (`branches: 80,`) | the same check, in `jest`/`vitest` config, `.nycrc` and `.c8rc` files only |
| config embedded in `package.json` (`eslintConfig`, `prettier`, `jest`, `nyc`, `c8`) | refused (`embedded config`); JSON has no comment for a justification, so no escape hatch |
| `/* global foo */` | needs `justified:`; only a comma list of identifiers closed on the same line, in JS and TS files |
| `line-length` raised (ruff, flake8, `.editorconfig`, detekt, prettier `printWidth`) | diff check `raised line length` |
| `strictTypeChecked` to `recommended` and the other ESLint presets | diff check `weaker lint preset`, ranked per plugin (strictTypeChecked > strict > recommendedTypeChecked > recommended); a renamed import alias reads as a removal |
| ruff `select` shrinking | diff check `narrowed ruff select` (a replacement by `"ALL"` passes); no escape hatch |
| tsconfig `include` narrowing, `exclude` growing | diff checks; a dropped `include` entry has no escape hatch, a new `exclude` entry needs `justified:` on its own line |
| `skipLibCheck: true` | content check, needs `justified:` (cheap: it hides errors in declaration files, not in our code) |

## Not done, and why

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
