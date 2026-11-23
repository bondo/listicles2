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

# The host is fixed and the repository is the origin remote of this script's own checkout (M1-85). It is parsed here, not by a helper, so the
# pinned content is all that runs; git gets no environment and no global config, so neither GITHUB_REPOSITORY nor git variables redirect the call.
# The guard does not deny `git remote set-url`, so the owner is pinned here too: a rename keeps the owner, another owner is refused.
# git starts at the checkout root (a planted scripts/.git is never read), and LC_ALL=C makes the bracket ranges below ASCII, as in repo_slug.py.
owner="bondo"
unset GH_HOST GH_REPO
LC_ALL=C
remote="$(env -i PATH="$PATH" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -C "$(dirname -- "$0")/.." remote get-url origin)" || remote=""
# slug-parse: begin (the forms of scripts/repo_slug.py; test_mark_ready.py checks both wrappers carry this block and that it agrees with it)
u='([^@/[:space:]]+@)?'
c='([^@/:[:space:]]+@)?'
s='([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})/?$'
repo=""
for form in "^https?://${u}(www\.)?github\.com/$s" "^${c}github\.com:$s" "^ssh://${u}github\.com(:[0-9]{1,5})?/$s" \
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
  echo "update-branch: the origin remote of this checkout is missing or not a GitHub repository URL" >&2
  exit 1
fi
case "$repo" in
  "$owner"/*) ;;
  *)
    echo "update-branch: the origin remote names a repository of another owner than $owner; refused" >&2
    exit 1
    ;;
esac
for d in $gh_dirs; do
  if [ -x "$d/gh" ]; then
    exec "$d/gh" api -X PUT "repos/${repo}/pulls/${n}/update-branch" -f "expected_head_sha=${sha}"
  fi
done
echo "update-branch: gh not found in: $gh_dirs" >&2
exit 127
