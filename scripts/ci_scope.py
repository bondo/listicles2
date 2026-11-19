#!/usr/bin/env python3
"""CI scope (issue 229, see 216): can this pull request affect the slow Gradle gate self-tests?

Usage (in the static job, which checks out the PR merge commit with fetch-depth 2; the job has no `if:`, because
scripts/check_gradle_repos.py forbids one, so the decision is made here):
    python3 -I scripts/ci_scope.py selftests [--scripts a.py b.py]   runs the Gradle gate self-tests, or none of them
    python3 -I scripts/ci_scope.py gradle-exclude                    prints `-x testLicenseeGate` or nothing

The answer is `skip` only when the event is a pull request, HEAD is a merge commit and every path changed against its first parent (the
base branch tip) is known to be unrelated. Everything else is `run`: a push (main always runs everything), an unknown or
odd path, an empty list, a git failure. The answer only gates steps, never a job, so every required check still reports.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The slow self-tests, about 20 cold Gradle builds each; the licensee gate's are excluded from detekt by gradle-exclude.
SELFTESTS = ("scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py")
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


def scope():
    paths = changed_paths()
    return gradle_selftests(paths) if paths is not None else "run"


def selftests(scripts):
    if scope() == "skip":
        print("gradle gate self-tests skipped: this PR changes nothing they inspect (see scripts/ci_scope.py)")
        return 0
    failed = []
    for script in scripts:
        path = script if os.path.isabs(script) else os.path.join(ROOT, script)
        if subprocess.run([sys.executable, "-I", path]).returncode != 0:  # all of them run, so one failure hides nothing
            failed.append(script)
    if failed:
        print("gradle gate self-tests failed: " + ", ".join(failed), file=sys.stderr)
    return 1 if failed else 0


def main(argv):
    if argv[1:2] == ["gradle-exclude"] and len(argv) == 2:
        print("-x testLicenseeGate" if scope() == "skip" else "")
        return 0
    if argv[1:2] == ["selftests"]:
        if len(argv) == 2:
            return selftests(SELFTESTS)
        if argv[2] == "--scripts" and len(argv) > 3:
            return selftests(argv[3:])
    print("usage: ci_scope.py selftests [--scripts FILE...] | gradle-exclude", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
