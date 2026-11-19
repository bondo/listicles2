#!/bin/bash -p
# Updates one PR branch of this repo with main, server side. The only command (with mark-ready.sh) the project permission rules let the agent that
# lands PRs run for this (docs/ORCHESTRATION.md 7.5). GitHub refuses the update when the head is no longer the expected one.
# Usage: scripts/update-branch.sh <PR number> <expected head sha>
# Exactly two arguments: digits only (1 to 6, no leading zero) and 40 lowercase hex characters. Everything else is refused before gh runs.
set -eu

# Neither bash nor gh is found through PATH (a planted shim would run under the allow rule): /bin/bash -p (no BASH_ENV, no imported functions), gh only from these directories, fixed PATH.
gh_dirs="/usr/local/bin /opt/homebrew/bin /usr/bin /bin"
PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export PATH

if [ "$#" -ne 2 ]; then
  echo "usage: scripts/update-branch.sh <PR number> <expected head sha>" >&2
  exit 2
fi

n="$1"
sha="$2"
case "$n" in
  '' | *[!0-9]* | 0*)
    echo "update-branch: the PR number must be digits only, without a leading zero" >&2
    exit 2
    ;;
esac
if [ "${#n}" -gt 6 ]; then
  echo "update-branch: the PR number has too many digits" >&2
  exit 2
fi
case "$sha" in
  *[!0-9a-f]*)
    echo "update-branch: the sha must be 40 lowercase hex characters" >&2
    exit 2
    ;;
esac
if [ "${#sha}" -ne 40 ]; then
  echo "update-branch: the sha must be 40 lowercase hex characters" >&2
  exit 2
fi

# The host and repository are fixed here; the environment cannot redirect the call.
unset GH_HOST GH_REPO
for d in $gh_dirs; do
  if [ -x "$d/gh" ]; then
    exec "$d/gh" api -X PUT "repos/bondo/listicles2/pulls/${n}/update-branch" -f "expected_head_sha=${sha}"
  fi
done
echo "update-branch: gh not found in: $gh_dirs" >&2
exit 127
