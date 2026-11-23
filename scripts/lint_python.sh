#!/usr/bin/env bash
# ruff check and mypy over scripts/ (or the paths given), with the root ruff.toml and mypy.ini.
# The installed ruff and mypy must match scripts/requirements-lint.txt: pip install -r scripts/requirements-lint.txt
# Usage: scripts/lint_python.sh [path ...]   (LINT_PY_REQUIREMENTS overrides the pin file; used by the tests only)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

REQ="${LINT_PY_REQUIREMENTS:-scripts/requirements-lint.txt}"
[ -r "$REQ" ] || { echo "lint_python: cannot read $REQ" >&2; exit 1; }
[ "$#" -gt 0 ] || set -- scripts

bad=0
for tool in ruff mypy; do
  want=$(grep -E "^${tool}==" "$REQ" | head -1 | cut -d= -f3)
  have=$("$tool" --version 2>/dev/null | awk '{print $2}')
  if [ -z "$want" ] || [ "$have" != "$want" ]; then
    echo "lint_python: $tool is '${have:-not installed}', requirements-lint.txt pins '${want:-nothing}'." >&2
    echo "             run: pip install -r scripts/requirements-lint.txt" >&2
    bad=1
  fi
done
[ "$bad" = 0 ] || exit 1

fail=0
ruff check --config ruff.toml --no-cache --output-format concise "$@" || fail=1
mypy --config-file mypy.ini "$@" || fail=1
exit "$fail"
