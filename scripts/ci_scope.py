#!/usr/bin/env python3
"""CI scope (issue 229, see 216): can this pull request affect the slow Gradle gate self-tests?

Usage (in the static job, which checks out the PR merge commit with fetch-depth 2):
    python3 -I scripts/ci_scope.py >> "$GITHUB_OUTPUT"      prints `gradle_selftests=run` or `gradle_selftests=skip`

`skip` only when the event is a pull request, HEAD is a merge commit and every path changed against its first parent (the
base branch tip) is known to be unrelated. Everything else is `run`: a push (main always runs everything), an unknown or
odd path, an empty list, a git failure. The answer only gates steps, never a job, so every required check still reports.
"""

import os
import subprocess
import sys

# Anything that can change what the gate self-tests inspect or how the build is configured.
RUN_SUFFIXES = (".gradle.kts", ".gradle", ".properties")
RUN_PREFIXES = ("gradle/", "config/", "buildSrc/", "build-logic/", ".github/")
RUN_FILES = {"gradlew", "gradlew.bat", "scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py", "scripts/ci_scope.py"}
# Locations that cannot (docs, tooling, firebase) or only via sources the gates never read (module `src` trees).
SKIP_PREFIXES = ("docs/", "handoff/", "agents/", "firebase/", "scripts/", ".githooks/", ".claude/", "metrics/", "design/")
SKIP_FILES = {"README.md", "CLAUDE.md", "REVIEW.md"}


def gradle_selftests(paths):
    """`skip` when every path is known to be unrelated to the Gradle gates, else `run` (fail closed)."""
    if not paths:
        return "run"
    for p in paths:
        if not p or p.startswith("/") or ".." in p.split("/"):
            return "run"
        if p in RUN_FILES or p.endswith(RUN_SUFFIXES) or p.startswith(RUN_PREFIXES):
            return "run"
        parts = p.split("/")
        in_module_src = len(parts) > 2 and "src" in parts[1:3]
        if p in SKIP_FILES or p.startswith(SKIP_PREFIXES) or in_module_src:
            continue
        return "run"
    return "skip"


def changed_paths():
    """Paths of the PR against the base branch tip (first parent of the merge commit), or None when unknown."""
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    try:
        parents = subprocess.run(["git", "rev-list", "--parents", "-n", "1", "HEAD"], capture_output=True, text=True, check=True)
        if len(parents.stdout.split()) != 3:  # the commit and exactly two parents
            return None
        diff = subprocess.run(["git", "diff", "-z", "--name-only", "--no-renames", "HEAD^1", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return [p for p in diff.stdout.split("\0") if p]


def main():
    paths = changed_paths()
    print(f"gradle_selftests={gradle_selftests(paths) if paths is not None else 'run'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
