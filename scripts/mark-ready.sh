#!/bin/bash -p
# Marks one draft PR of this repo ready for review. The only command the project permission rule allows (see docs/ORCHESTRATION.md 7.5).
# Usage: scripts/mark-ready.sh <PR number>
# Exactly one argument, digits only (1 to 6 digits, no leading zero). Everything else is refused before gh runs.
set -eu

# Neither bash nor gh is found through PATH (a planted shim would run under the allow rule): /bin/bash -p (no BASH_ENV, no imported functions), gh only from these directories, fixed PATH.
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

# The host is fixed and the repository is the origin remote of this script's own checkout (M1-85). It is parsed here, not by a helper, so the
# pinned content is all that runs; git gets no environment and no global config, so neither GITHUB_REPOSITORY nor git variables redirect the call.
unset GH_HOST GH_REPO
remote="$(env -i PATH="$PATH" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -C "$(dirname -- "$0")" remote get-url origin 2>/dev/null)" || remote=""
# slug-parse: begin (the forms of scripts/repo_slug.py; test_mark_ready.py checks both wrappers carry this block and that it agrees with it)
u='([^@/[:space:]]+@)?'
s='([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})/?$'
repo=""
for form in "^https?://${u}(www\.)?github\.com/$s" "^${u}github\.com:$s" "^ssh://${u}github\.com(:[0-9]{1,5})?/$s" \
  "^https?://${u}(127\.0\.0\.1|localhost)(:[0-9]{1,5})?/git/$s"; do
  if [[ "$remote" =~ $form ]]; then
    repo="${BASH_REMATCH[${#BASH_REMATCH[@]}-1]}"
    break
  fi
done
repo="${repo%.git}"
case "${repo#*/}" in '' | . | ..) repo="" ;; esac
# slug-parse: end
if [ -z "$repo" ]; then
  echo "mark-ready: the origin remote of this checkout is missing or not a GitHub repository URL" >&2
  exit 1
fi
for d in $gh_dirs; do
  if [ -x "$d/gh" ]; then
    exec "$d/gh" api -X POST "repos/${repo}/pulls/${n}/ccr/ready_for_review"
  fi
done
echo "mark-ready: gh not found in: $gh_dirs" >&2
exit 127
