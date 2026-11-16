#!/bin/bash
# Marks one draft PR of this repo ready for review. The only command the project permission rule allows (see docs/ORCHESTRATION.md 7.5).
# Usage: scripts/mark-ready.sh <PR number>
# Exactly one argument, digits only (1 to 6 digits, no leading zero). Everything else is refused before gh runs.
set -eu

# Neither bash nor gh is found through PATH (a shim planted in a PATH directory would run under the allow rule): the interpreter is /bin/bash,
# gh is looked up only in these fixed system directories, and gh itself runs with this fixed PATH.
gh_dirs="/usr/local/bin /opt/homebrew/bin /usr/bin /bin"
PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export PATH

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/mark-ready.sh <PR number>" >&2
  exit 2
fi

n="$1"
case "$n" in
  '' | *[!0-9]* | 0*)
    echo "mark-ready: the PR number must be digits only, without a leading zero" >&2
    exit 2
    ;;
esac
if [ "${#n}" -gt 6 ]; then
  echo "mark-ready: the PR number has too many digits" >&2
  exit 2
fi

# The host and repository are fixed here; the environment cannot redirect the call.
unset GH_HOST GH_REPO
for d in $gh_dirs; do
  if [ -x "$d/gh" ]; then
    exec "$d/gh" api -X POST "repos/bondo/listicles2/pulls/${n}/ccr/ready_for_review"
  fi
done
echo "mark-ready: gh not found in: $gh_dirs" >&2
exit 127
