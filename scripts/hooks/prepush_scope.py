#!/usr/bin/env python3
"""Pre-push scope: reads git's pre-push stdin ("<local ref> <local sha> <remote ref> <remote sha>" per line) and prints
`skip` when everything being pushed is prose, scripts, hooks, CI or firebase files that cannot affect the Android build,
otherwise `android`. Fails closed: unknown paths, unknown remote commits or unparseable input print `android`.
With `--paths`, stdin is a list of newline-separated paths instead (the staged files, for .githooks/pre-commit); no paths at
all print `android` too, because unknown means build.
With `--hook-tests`, stdin is the pre-push input again and the answer is `run` or `skip` for the hook suite (scripts/hooks, run by
run_hook_tests.py; owner decision 7075952806 item 1 on #15): `skip` only when no pushed path can affect it. Unknown, unreadable or
empty ranges print `run`. CI's guards job runs the full suite on every PR, which is what makes this local skip safe."""

import fnmatch
import subprocess
import sys

ZERO = "0" * 40
# Top-level locations that cannot affect the Android build. Anything else (including new directories) builds.
# Kotlin and Kotlin script files build wherever they are: spotless and detekt target **/*.kt and **/*.gradle.kts (R1-01).
SKIP_PREFIXES = ("docs/", "handoff/", "scripts/", ".githooks/", ".claude/", ".github/", "agents/", "firebase/", "metrics/")
SKIP_FILES = {"README.md", "CLAUDE.md", "REVIEW.md"}


# What the hook suite reads, runs, copies or imports. Derived from the hook code: test_prepush_scope.HookSuiteInputs parses every
# scripts/hooks/*.py and fails when a repo path it names is not covered here. scripts/ is a prefix because the suite runs scripts by
# computed names and they read further files; *.py anywhere because test_guards_sh greps every tracked .py file for lint suppressions.
# guards.sh on the whole repository (test_guards_sh's self-check) needs nothing here: pre-push runs guards.sh on every push.
# .gitattributes and .gitmodules change what the git commands the suite runs see (git grep -I, diffs in test repos).
HOOK_SUITE_PREFIXES = ("scripts/", ".githooks/", ".claude/", ".github/", "agents/")
HOOK_SUITE_FILES = {
    "CLAUDE.md", "REVIEW.md", ".gitignore", ".gitattributes", ".gitmodules", "docs/PLAN.md", "docs/ORCHESTRATION.md", "docs/tasks.toml", "handoff/TEMPLATE.md",
    "app/src/androidTest/kotlin/dk/bjarkebjarke/tally/TallyAppTest.kt",
}
HOOK_SUITE_GLOBS = ("core/*/build.gradle.kts",)


def hook_tests_scope(paths):
    """`run` when one of the changed paths can affect the hook suite, else `skip`. No paths, or an odd one, means run."""
    if not paths:
        return "run"
    for p in paths:
        if not p or p.startswith("/") or {".", ".."} & set(p.split("/")):
            return "run"
        if p.endswith(".py") or p in HOOK_SUITE_FILES or p.startswith(HOOK_SUITE_PREFIXES):
            return "run"
        if any(fnmatch.fnmatchcase(p, g) for g in HOOK_SUITE_GLOBS):
            return "run"
    return "skip"


def classify(paths):
    for p in paths:
        if ".." in p.split("/"):
            return "android"
        if p.endswith((".kt", ".kts")):
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
    # Renames must show both paths; -z and quotePath off keep non-ASCII names unquoted (a quoted name matches no prefix).
    out = run_git("-c", "core.quotePath=false", "diff", "--name-only", "-z", "--no-renames", base, local)
    return None if out is None else [p for p in out.split("\0") if p]


def paths_mode():
    paths = [p for p in sys.stdin.read().splitlines() if p.strip()]
    print(classify(paths) if paths else "android")


def pushed_paths(text):
    """Every path the pushed refs change; None when unknown (no lines, a malformed line or an unreadable range)."""
    paths, seen = [], False
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            return None
        local, remote = parts[1], parts[3]
        seen = True
        if local == ZERO:  # deleting a remote branch: nothing to build
            continue
        found = changed_paths(local, remote)
        if found is None:
            return None
        paths += found
    return paths if seen else None


def main():
    if sys.argv[1:] == ["--paths"]:
        return paths_mode()
    paths = pushed_paths(sys.stdin.read())
    if sys.argv[1:] == ["--hook-tests"]:
        print("run" if paths is None else hook_tests_scope(paths))
    else:
        print("android" if paths is None else classify(paths))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # fail closed
        print(f"prepush_scope: {e}", file=sys.stderr)
        print("run" if sys.argv[1:] == ["--hook-tests"] else "android")
    sys.exit(0)
