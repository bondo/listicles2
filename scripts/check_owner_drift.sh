#!/usr/bin/env bash
# CI gate for #92: fail when an owner task in docs/tasks.toml is `todo` while its GitHub issue is closed or its PR is
# merged (the owner confirmed it, the status row lagged). Reads GitHub through `gh` (GH_TOKEN, read-only) and runs
# `tasks.py drift --check`. A gh failure, incomplete_results or more than 1000 search results fail the check ("could not
# look" is not "no drift").
# Env: GITHUB_REPOSITORY (default bondo/listicles2), OWNER_DRIFT_RETRIES (3), OWNER_DRIFT_SLEEP (5 s, doubled each
# retry), OWNER_DRIFT_TASKS (task file; tests only). Needs python3 and gh.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

REPO="${GITHUB_REPOSITORY:-bondo/listicles2}"
RETRIES="${OWNER_DRIFT_RETRIES:-3}"
PAUSE="${OWNER_DRIFT_SLEEP:-5}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch() { # fetch <query> <output file>: search/issues, every page, one JSON array of pages (see ORCHESTRATION 4.3)
  local n=1 delay="$PAUSE"
  while :; do
    if gh api -X GET search/issues --paginate --slurp -f q="$1" -f per_page=100 > "$2" 2> "$TMP/err" && [ -s "$2" ]; then
      return 0
    fi
    if [ "$n" -ge "$RETRIES" ]; then
      echo "check_owner_drift: gh could not read GitHub after $n tries: $(head -c 300 "$TMP/err")" >&2
      return 1
    fi
    sleep "$delay"
    delay=$((delay * 2))
    n=$((n + 1))
  done
}

complete() { # complete <file> <what>: search/issues caps at 1000 results and may say incomplete_results; never pass on a partial list
  python3 -I - "$1" "$2" <<'PY' || return 1
import json
import sys

path, what = sys.argv[1], sys.argv[2]
for page in json.load(open(path)):
    if page.get("incomplete_results"):
        sys.exit(f"check_owner_drift: GitHub search returned incomplete_results for {what}; narrow the query or retry")
    if page.get("total_count", 0) > 1000:
        sys.exit(f"check_owner_drift: GitHub search has more than 1000 results for {what} (search cap); narrow the query")
PY
}

# All issues, not only labelled ones: owner issues are linked by `issue = N` or by title and the label is not relied on
# (#12-#14 never had it), and tasks.py needs the open issues too (an open one wins over a closed duplicate).
fetch "repo:$REPO is:issue is:closed" "$TMP/issues.json" || exit 1
complete "$TMP/issues.json" "issues" || exit 1
fetch "repo:$REPO is:pr is:merged" "$TMP/prs.json" || exit 1
complete "$TMP/prs.json" "merged PRs" || exit 1

args=(--issues "$TMP/issues.json" --prs "$TMP/prs.json")
[ -n "${OWNER_DRIFT_TASKS:-}" ] && args=(--file "$OWNER_DRIFT_TASKS" "${args[@]}")
if python3 -I scripts/tasks.py "${args[@]}" drift --check; then
  exit 0
fi
echo "check_owner_drift: set status in docs/tasks.toml to match (done, or dropped with a note); see ORCHESTRATION 4.4." >&2
exit 1
