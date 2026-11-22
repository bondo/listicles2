"""Runs the hook test suite and fails when any test was skipped (R12-04, #28).

Usage: python3 -I scripts/hooks/run_hook_tests.py [--jobs N] [start_dir]   (default: the directory of this script, serial)

With --jobs N the test files and packages are spread over N child processes (issue 229); every child applies the same gates
and the parent fails if a child fails, or if the shards ran a different number of tests than serial discovery collects.

The suite is a CI gate, so a skipped test is a failure however the skip was written (`import unittest as ut` + `@ut.skip`,
a call form, `self.skipTest`). The check reads the run's result, not the source text. Expected failures and unexpected
successes count too, and so does a run that finds no tests.
"""

import argparse
import concurrent.futures
import fnmatch
import os
import subprocess
import sys
import tempfile
import unittest

# Rough seconds of the files over about 3 s, each run alone and serially on a 4-core machine (2026-11-22, owner decision 7075952806
# item 3 on #15); unlisted files count 1. Only balances the shards: a stale entry costs time, never coverage (test_run_hook_tests).
WEIGHTS = {
    "test_gitenv_isolation.py": 171, "test_gitenv_hostile_config.py": 170, "test_guards_sh.py": 164, "test_guards_cli_flags.py": 77,
    "test_guard_hardening4.py": 18, "test_guard_hardening.py": 15, "test_guard_mark_ready.py": 14, "test_guard_round2.py": 9,
    "test_guard_hardening2.py": 8, "test_guard_hardening3.py": 8, "test_guard_round1.py": 8, "test_guard_forms.py": 8,
    "test_guard_update_branch.py": 8, "test_guard_actionlint.py": 7, "test_guard_wrapper_forms.py": 6, "test_pretooluse_guard.py": 6,
    "test_guard_linter_dir.py": 5, "test_run_hook_tests.py": 4, "test_context_guard.py": 3,
}


def partition(files, n):
    """Spreads file names over at most n shards, heaviest first onto the lightest shard. Every file lands in exactly one shard."""
    shards = [[] for _ in range(max(1, n))]
    loads = [0] * len(shards)
    for f in sorted(files, key=lambda f: (-WEIGHTS.get(f, 1), f)):
        i = loads.index(min(loads))
        shards[i].append(f)
        loads[i] += WEIGHTS.get(f, 1)
    return [sorted(s) for s in shards if s]


def units(start):
    """What the serial run collects, as shardable units: every top-level test*.py file and every top-level package."""
    found = [n for n in os.listdir(start) if fnmatch.fnmatch(n, "test*.py") and os.path.isfile(os.path.join(start, n))]
    found += [n for n in os.listdir(start) if os.path.isfile(os.path.join(start, n, "__init__.py"))]
    return sorted(found)


def stale_weights(start):
    """WEIGHTS names that are not units of the suite at `start` (renamed or deleted files)."""
    return sorted(set(WEIGHTS) - set(units(start)))


def count_problem(start, total):
    """None when the shards ran exactly as many tests as serial discovery collects, else a message (R1-01: nothing dropped)."""
    expected = unittest.TestLoader().discover(start).countTestCases()
    if total == expected:
        return None
    return f"the shards ran {total} test(s) but serial discovery collects {expected} test(s)"


def load_unit(loader, start, name):
    """One unit of work in a child: a module by name (no recursion), or a package by directory."""
    if name.endswith(".py"):
        return loader.loadTestsFromName(name[:-3])
    return loader.discover(os.path.join(start, name), pattern="test*.py", top_level_dir=start)


def run_shard(start, names):
    """One child process: the runner itself on a subset of the files. Returns (name list, return code, output)."""
    cmd = [sys.executable, "-I", os.path.abspath(__file__), "--only", ",".join(names), start]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return names, r.returncode, r.stdout + r.stderr


def run_parallel(start, jobs):
    files = units(start)
    if not files:
        print("hook tests: no tests were found", file=sys.stderr)
        return 1
    shards = partition(files, jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        results = list(pool.map(lambda names: run_shard(start, names), shards))
    total, rc = 0, 0
    for names, code, out in results:
        print(f"--- shard: {' '.join(names)} (exit {code})")
        print(out if code != 0 else "\n".join(ln for ln in out.splitlines() if ln.startswith(("Ran ", "OK"))))
        total += sum(int(ln.split()[1]) for ln in out.splitlines() if ln.startswith("Ran "))
        rc = rc or code
    print(f"hook tests: ran {total} tests in {len(shards)} shards")
    problem = count_problem(start, total)
    if problem:
        print(f"hook tests: {problem}", file=sys.stderr)
    return rc or (1 if problem else 0)


def main(argv):
    ap = argparse.ArgumentParser(prog="run_hook_tests.py")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", help="comma-separated units for one shard (used by the parent)")
    ap.add_argument("start", nargs="?", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args(argv[1:])
    if args.jobs < 1:
        print("hook tests: --jobs needs a whole number of at least 1", file=sys.stderr)
        return 2
    start = os.path.abspath(args.start)
    # R2-01 (PR 302): run from an empty temporary cwd, never the directory the runner was started in (the repo root for pre-push,
    # verify.sh and CI), so a relative path, os.getcwd() or git without cwd= cannot read the repo past the pre-push input scope.
    with tempfile.TemporaryDirectory(prefix="hook-tests-cwd-") as cwd:
        os.chdir(cwd)
        try:
            return run(args, start)
        finally:
            os.chdir(os.path.dirname(cwd))


def run(args, start):
    if args.jobs > 1 and args.only is None:
        return run_parallel(start, args.jobs)
    loader = unittest.TestLoader()
    if args.only is None:
        suite = loader.discover(start)
    else:
        sys.path.insert(0, start)  # a module is loaded by name, so its directory must be importable (discover adds it itself)
        suite = unittest.TestSuite(load_unit(loader, start, n) for n in args.only.split(","))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    problems = []
    if result.testsRun == 0:
        problems.append("no tests were found")
    if result.skipped:
        problems.append(f"{len(result.skipped)} skipped test(s): " + ", ".join(f"{t.id()} ({why})" for t, why in result.skipped))
    if result.expectedFailures:
        problems.append(f"{len(result.expectedFailures)} expected failure(s): " + ", ".join(t.id() for t, _ in result.expectedFailures))
    if result.unexpectedSuccesses:
        problems.append(f"{len(result.unexpectedSuccesses)} unexpected success(es): " + ", ".join(t.id() for t in result.unexpectedSuccesses))
    for p in problems:
        print(f"hook tests: {p}", file=sys.stderr)
    return 0 if result.wasSuccessful() and not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
