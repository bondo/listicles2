#!/usr/bin/env python3
"""CI scope (issue 229, see 216): can this pull request affect the slow Gradle gate self-tests?

Used by the static job (checkout of the PR merge commit, fetch-depth 2; the job may have no `if:`, see check_gradle_repos.py):
    python3 -I scripts/ci_scope.py selftests [--scripts a.py b.py]   runs the Gradle gate self-tests, or none of them
    python3 -I scripts/ci_scope.py gradle-exclude                    prints `-x testLicenseeGate` or nothing
Used by verify.sh (issue 216, owner decision 7003898899):
    python3 -I scripts/ci_scope.py local-scope                       prints `skip` or `run`

`skip` only for a pull request whose merge commit changes, against its first parent, nothing but known-unrelated paths.
Everything else is `run`: a push (main always runs everything), an unknown or odd path, no paths, a git failure.
`local-scope` does the same for everything since the merge base with origin/main (commits, staged, unstaged and untracked
files); no origin/main, no merge base, a shallow clone whose history above the merge base is incomplete, or any error: `run`.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The slow self-tests, about 20 cold Gradle builds each; the licensee gate's are excluded from detekt by gradle-exclude.
SELFTESTS = ("scripts/test_warnings_gate.py", "scripts/test_jdk_release_gate.py", "scripts/test_java_api_level_gate.py",
             "scripts/test_google_services_release_gate.py", "scripts/test_test_settings_gate.py", "scripts/test_spotless_gate.py")
# Anything that can change what the gate self-tests inspect or how the build is configured.
RUN_SUFFIXES = (".gradle.kts", ".gradle", ".properties")
RUN_PREFIXES = ("gradle/", "config/", "buildSrc/", "build-logic/", ".github/")
RUN_FILES = {
    "gradlew",
    "gradlew.bat",
    "scripts/test_warnings_gate.py",
    "scripts/test_jdk_release_gate.py",
    "scripts/test_java_api_level_gate.py",
    "scripts/test_google_services_release_gate.py",
    "scripts/test_test_settings_gate.py",
    "scripts/test_spotless_gate.py",
    "scripts/check_java_api_level.py",
    "scripts/ci_scope.py",
}
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


def git_lines(top, *args):
    r = subprocess.run(["git", *args], cwd=top, capture_output=True, text=True, check=True)
    return [p for p in r.stdout.split("\0" if "-z" in args else "\n") if p]


def history_complete(top, base):
    """True unless the clone is shallow and a cut-off commit is not an ancestor of `base` (or itself). When every cut is
    below `base`, every commit from `base` up to both tips is present, so `base` is the merge base of the full history."""
    if git_lines(top, "rev-parse", "--is-shallow-repository") == ["false"]:
        return True
    # --git-path, not the git dir: a linked worktree keeps `shallow` in the common git dir.
    with open(os.path.join(top, git_lines(top, "rev-parse", "--git-path", "shallow")[0]), encoding="utf-8") as f:
        cuts = f.read().split()
    if not cuts:
        return False
    return all(subprocess.run(["git", "merge-base", "--is-ancestor", c, base], cwd=top, capture_output=True).returncode == 0 for c in cuts)


def local_paths():
    """Paths changed since the merge base with origin/main, including the uncommitted ones; None when unknown."""
    try:
        top = git_lines(None, "rev-parse", "--show-toplevel")[0]
        base = git_lines(top, "merge-base", "refs/remotes/origin/main", "HEAD")[0]
        if not history_complete(top, base):
            return None
        return (git_lines(top, "diff", "-z", "--name-only", "--no-renames", base)  # the merge base against the working tree
                + git_lines(top, "ls-files", "-z", "--others", "--exclude-standard"))
    except (OSError, IndexError, ValueError, subprocess.CalledProcessError):  # ValueError: a path that is not UTF-8
        return None


def local_scope():
    paths = local_paths()
    return gradle_selftests(paths) if paths is not None else "run"


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
    if argv[1:] == ["local-scope"]:
        print(local_scope())
        return 0
    if argv[1:2] == ["selftests"]:
        if len(argv) == 2:
            return selftests(SELFTESTS)
        if argv[2] == "--scripts" and len(argv) > 3:
            return selftests(argv[3:])
    print("usage: ci_scope.py selftests [--scripts FILE...] | gradle-exclude | local-scope", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
