#!/usr/bin/env python3
"""Pre-push golden-update label check (M1-126, owner decision 7239508302 item 2 on #399). guards.sh --pre-push runs this when
screenshot references changed and GOLDEN_UPDATE is not 1, so a push of reviewed goldens passes locally once the orchestrator has
labelled the PR, as CI does from the label. CI never runs it: there GOLDEN_UPDATE comes from the PR label.

Usage: golden_label.py PUSH_URL, with git's pre-push input on stdin ("<local ref> <local sha> <remote ref> <remote sha>").
Exit 0 and a note when the one open PR whose head is the pushed branch of this repository carries the label, else exit 1 and the
reason. Fail closed: the push must be exactly one branch, the checked-out one at HEAD, pushed to the same name at a URL of the
origin repository; then exactly one open PR of that repository must have that branch of that repository as its head. A gh error,
a timeout or an answer that does not parse refuses. The repository comes from the origin remote only (not $GITHUB_REPOSITORY), and
the variables that pick gh's repository, host or output form are dropped, so no variable other than GOLDEN_UPDATE (read by
guards.sh) changes the answer. PATH (which gh), HOME and gh's own config and token stay as they are: they select the gh binary and
its login, not the question (a tripwire, F18). Standard library only."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import repo_slug  # noqa: E402  # justified: after the sys.path insert, python3 -I does not add the scripts directory itself

LABEL = "golden-update"
HOST = "github.com"
ZERO = "0" * 40
SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)
BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,200}", re.ASCII)
# Variables that would point gh at another repository or host, or change the form of its output.
DROPPED = ("GH_REPO", "GH_HOST", "GITHUB_REPOSITORY", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG", "DEBUG",
           "GH_PAGER", "PAGER", "GH_FORCE_TTY", "CLICOLOR_FORCE", "CLICOLOR", "GH_TELEMETRY")
TIMEOUT = 60


class Refused(Exception):
    pass


def git(root: Path, *args: str) -> str:
    """git in `root` with the repository variables and global/system config dropped (as repo_slug.origin_url)."""
    env = {k: v for k, v in os.environ.items() if k not in repo_slug.REPO_GIT_VARS and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(root.resolve().parent))
    env.pop("GIT_CONFIG_COUNT", None)
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refused(f"could not run git: {e}") from None
    if p.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed")
    return p.stdout.strip()


def pushed_branch(stdin: str, root: Path) -> str:
    """The one branch being pushed, when it is the checked-out branch at HEAD pushed to the same name."""
    lines = [line for line in stdin.splitlines() if line.strip()]
    if len(lines) != 1:
        raise Refused(f"push exactly one branch to use the label (git gave {len(lines)} refs)")
    parts = lines[0].split(" ")
    if len(parts) != 4:
        raise Refused("pre-push input is not '<local ref> <local sha> <remote ref> <remote sha>'")
    local_ref, local_sha, remote_ref, _ = parts
    if not (local_ref.startswith("refs/heads/") and remote_ref.startswith("refs/heads/")):
        raise Refused(f"not a branch push: {local_ref[:100]!r} -> {remote_ref[:100]!r}")
    branch = local_ref[len("refs/heads/"):]
    if remote_ref != local_ref:
        raise Refused(f"the remote branch {remote_ref[:100]!r} is not {local_ref[:100]!r}")
    if not BRANCH.fullmatch(branch) or ".." in branch or branch.startswith(("/", "-")):
        raise Refused(f"branch name not supported: {branch[:100]!r}")
    if not SHA.fullmatch(local_sha) or local_sha == ZERO:
        raise Refused("a branch delete or an unparsable commit id")
    head_ref = git(root, "symbolic-ref", "-q", "HEAD")
    if head_ref != local_ref:
        raise Refused(f"{local_ref} is not the checked-out branch ({head_ref or 'detached HEAD'}), which the guards checked")
    if git(root, "rev-parse", "--verify", "-q", "HEAD^{commit}") != local_sha:
        raise Refused(f"the pushed commit is not HEAD of {branch}, which the guards checked")
    return branch


def repository(push_url: str, root: Path) -> str:
    """OWNER/NAME of the origin remote, when the push goes to it."""
    try:
        slug = repo_slug.resolve(environ={}, root=root)
    except repo_slug.RepoSlugError as e:
        raise Refused(str(e)) from None
    if repo_slug.slug_from_url(push_url) != slug:
        raise Refused(f"the push does not go to the origin repository {slug}")
    return slug


def ask_gh(slug: str, branch: str) -> str:
    owner = slug.split("/")[0]
    env = {k: v for k, v in os.environ.items() if k not in DROPPED}
    env.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", NO_COLOR="1")
    cmd = ["gh", "api", "--hostname", HOST, "-X", "GET", f"repos/{slug}/pulls", "-f", "state=open", "-f", f"head={owner}:{branch}",
           "-f", "per_page=100"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refused(f"gh api failed: {e}") from None
    if p.returncode != 0:
        raise Refused(f"gh api failed (exit {p.returncode}): {p.stderr.strip()[:200]}")
    return p.stdout


def labelled_pr(answer: str, slug: str, branch: str) -> int:
    """The PR number when the answer is exactly one open PR of `slug` with head `slug`:`branch` that carries the label."""
    try:
        prs = json.loads(answer)
    except ValueError:
        raise Refused("gh answer is not JSON") from None
    if not isinstance(prs, list):
        raise Refused("gh answer is not a list of PRs")
    if not prs:
        raise Refused(f"no open PR has head {slug}:{branch}")
    if len(prs) != 1:
        raise Refused(f"{len(prs)} open PRs have head {slug}:{branch}")
    pr = prs[0]
    try:
        number, state, labels = pr["number"], pr["state"], pr["labels"]
        head_ref, head_repo, base_repo = pr["head"]["ref"], pr["head"]["repo"]["full_name"], pr["base"]["repo"]["full_name"]
        names = [label["name"] for label in labels]
    except (TypeError, KeyError):
        raise Refused("gh answer is not a PR with number, state, labels, head and base") from None
    if type(number) is not int or not isinstance(labels, list) or not all(isinstance(n, str) for n in names):
        raise Refused("gh answer has a PR number or labels of the wrong type")
    if (state, head_ref, head_repo, base_repo) != ("open", branch, slug, slug):
        raise Refused(f"PR #{number} is not an open PR of {slug} with head {slug}:{branch}")
    if LABEL not in names:
        raise Refused(f"PR #{number} has no {LABEL} label")
    return number


def check(push_url: str, stdin: str, root: Path = ROOT) -> int:
    branch = pushed_branch(stdin, root)
    slug = repository(push_url, root)
    return labelled_pr(ask_gh(slug, branch), slug, branch)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("golden_label: usage: golden_label.py PUSH_URL (pre-push input on stdin)")
        return 1
    try:
        number = check(argv[0], sys.stdin.read())
    except Refused as e:
        print(f"golden_label: {e}")
        return 1
    print(f"{LABEL} label on PR #{number}, changed screenshot references allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
