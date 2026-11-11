#!/usr/bin/env python3
"""Pre-push scope: reads git's pre-push stdin ("<local ref> <local sha> <remote ref> <remote sha>" per line) and prints
`skip` when everything being pushed is prose, scripts, hooks, CI or firebase files that cannot affect the Android build,
otherwise `android`. Fails closed: unknown paths, unknown remote commits or unparseable input print `android`."""

import subprocess
import sys

ZERO = "0" * 40
# Top-level locations that cannot affect the Android build. Anything else (including new directories) builds.
SKIP_PREFIXES = ("docs/", "handoff/", "scripts/", ".githooks/", ".claude/", ".github/", "agents/", "firebase/", "metrics/")
SKIP_FILES = {"README.md", "CLAUDE.md", "REVIEW.md"}


def classify(paths):
    for p in paths:
        if ".." in p.split("/"):
            return "android"
        if p in SKIP_FILES or p.startswith(SKIP_PREFIXES):
            continue
        return "android"
    return "skip"


def run_git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def changed_paths(local, remote):
    """Paths changed by pushing `local` over `remote`; None when unknown (the caller builds)."""
    if remote == ZERO:
        base = run_git("merge-base", "refs/remotes/origin/main", local)
        if not base:
            return None
    elif run_git("cat-file", "-e", remote + "^{commit}") is None:  # "" means the commit exists
        return None
    else:
        base = remote
    out = run_git("diff", "--name-only", base, local)
    return None if out is None else [p for p in out.splitlines() if p]


def main():
    paths, seen = [], False
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            print("android")
            return
        local, remote = parts[1], parts[3]
        seen = True
        if local == ZERO:  # deleting a remote branch: nothing to build
            continue
        found = changed_paths(local, remote)
        if found is None:
            print("android")
            return
        paths += found
    print(classify(paths) if seen else "android")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail closed
        print(f"prepush_scope: {e}", file=sys.stderr)
        print("android")
    sys.exit(0)
