#!/usr/bin/env python3
"""Publish status.svg and status.json to the `status` branch with a plain push (git plumbing, no working tree).

Usage: python3 -I scripts/status_publish.py --svg status.svg --json status.json [--repo .] [--remote origin] [--branch status]

Creates the orphan branch when the remote has none; builds a new commit on the remote tip otherwise; makes no
commit when the SVG is unchanged apart from its generated stamp. Never force-pushes: a rejected push is retried once
on the fresh tip, then fails. Prints created, updated or unchanged. Exit 2 on any error.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status_visual  # noqa: E402  # justified: must follow the sys.path insert above

IDENTITY = ("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
PROTECTED = ("main", "master")


class PublishError(Exception):
    pass


def git(repo, *args, stdin=None, ok=(0,)):
    res = subprocess.run(["git", "-C", repo, *args], input=stdin, capture_output=True, text=True)
    if res.returncode not in ok:
        raise PublishError(f"git {args[0]} failed: {res.stderr.strip()[:200]}")
    return res


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise PublishError(f"{path}: cannot read ({e.strerror})") from None


def _attempt(repo, svg, js, remote, branch):
    ref = f"refs/heads/{branch}"
    found = git(repo, "ls-remote", "--exit-code", "--heads", remote, ref, ok=(0, 2))
    parent, outcome = None, "created"
    if found.returncode == 0:
        git(repo, "fetch", "--quiet", remote, ref)
        parent = git(repo, "rev-parse", "FETCH_HEAD").stdout.strip()
        old = git(repo, "show", f"{parent}:status.svg", ok=(0, 128))
        if old.returncode == 0 and status_visual.same_ignoring_stamp(old.stdout, svg):
            return "unchanged"
        outcome = "updated"
    blobs = [git(repo, "hash-object", "-w", "--stdin", stdin=content).stdout.strip() for content in (js, svg)]
    tree = git(repo, "mktree", stdin=f"100644 blob {blobs[0]}\tstatus.json\n100644 blob {blobs[1]}\tstatus.svg\n").stdout.strip()
    parents = ("-p", parent) if parent else ()
    commit = git(repo, *IDENTITY, "commit-tree", tree, *parents, "-m", "status: update").stdout.strip()
    push = git(repo, "push", "--quiet", remote, f"{commit}:{ref}", ok=(0, 1))
    if push.returncode != 0:
        raise _Rejected(push.stderr.strip()[:200])
    return outcome


class _Rejected(PublishError):
    pass


def publish(repo, svg_path, json_path, remote="origin", branch="status"):
    if branch in PROTECTED or not BRANCH.fullmatch(branch) or not re.fullmatch(r"[A-Za-z0-9._/-]+", remote):
        raise PublishError(f"refusing to publish to branch {branch!r}")
    svg, js = _read(svg_path), _read(json_path)
    try:
        return _attempt(repo, svg, js, remote, branch)
    except _Rejected:
        return _attempt(repo, svg, js, remote, branch)  # the tip moved: rebuild on it, still a plain push


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publish the status image to the status branch.")
    ap.add_argument("--svg", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="status")
    args = ap.parse_args(argv)
    try:
        print(publish(args.repo, args.svg, args.json, args.remote, args.branch))
    except PublishError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
