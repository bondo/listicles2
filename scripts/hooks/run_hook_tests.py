"""Runs the hook test suite and fails when any test was skipped (R12-04, #28).

Usage: python3 -I scripts/hooks/run_hook_tests.py [--jobs N] [start_dir]   (default: the directory of this script, serial)

With --jobs N the test files are spread over N child processes (issue 229); every child applies the same gates and the
parent fails if any child fails, crashes or finds nothing. The slow files are listed in WEIGHTS so they do not share a shard.

The suite is a CI gate, so a skipped test is a failure however the skip was written (`import unittest as ut` + `@ut.skip`,
a call form, `self.skipTest`). The check reads the run's result, not the source text. Expected failures and unexpected
successes count too, and so does a run that finds no tests.
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
import unittest

# Rough seconds of the slow files (measured, issue 229). Only balances the shards; a stale entry costs time, never coverage.
WEIGHTS = {"test_gitenv_isolation.py": 100, "test_gitenv_hostile_config.py": 100, "test_guards_sh.py": 107, "test_guards_cli_flags.py": 36}


def partition(files, n):
    """Spreads file names over at most n shards, heaviest first onto the lightest shard. Every file lands in exactly one shard."""
    shards = [[] for _ in range(max(1, n))]
    loads = [0] * len(shards)
    for f in sorted(files, key=lambda f: (-WEIGHTS.get(f, 1), f)):
        i = loads.index(min(loads))
        shards[i].append(f)
        loads[i] += WEIGHTS.get(f, 1)
    return [sorted(s) for s in shards if s]


def run_shard(start, names):
    """One child process: the runner itself on a subset of the files. Returns (name list, return code, output)."""
    cmd = [sys.executable, "-I", os.path.abspath(__file__), "--only", ",".join(names), start]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return names, r.returncode, r.stdout + r.stderr


def run_parallel(start, jobs):
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(start, "test_*.py")))
    if not files:
        print("hook tests: no tests were found", file=sys.stderr)
        return 1
    shards = partition(files, jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        results = list(pool.map(lambda names: run_shard(start, names), shards))
    total, rc = 0, 0
    for names, code, out in results:
        print(f"--- shard: {' '.join(names)} (exit {code})")
        print(out if code != 0 else "\n".join(ln for ln in out.splitlines() if ln.startswith(("Ran ", "OK", "FAILED"))))
        for ln in out.splitlines():
            if ln.startswith("Ran "):
                total += int(ln.split()[1])
        rc = rc or code
    print(f"hook tests: ran {total} tests in {len(shards)} shards")
    return rc


def main(argv):
    args = argv[1:]
    jobs, only = 1, None
    while args and args[0] in ("--jobs", "--only"):
        flag = args[0]
        if len(args) < 2:
            print(f"hook tests: {flag} needs a value", file=sys.stderr)
            return 2
        if flag == "--jobs":
            if not args[1].isdigit() or int(args[1]) < 1:
                print("hook tests: --jobs needs a whole number of at least 1", file=sys.stderr)
                return 2
            jobs = int(args[1])
        else:
            only = args[1].split(",")
        args = args[2:]
    start = os.path.abspath(args[0]) if args else os.path.dirname(os.path.abspath(__file__))
    if jobs > 1 and only is None:
        return run_parallel(start, jobs)
    loader = unittest.TestLoader()
    suite = loader.discover(start) if only is None else unittest.TestSuite(loader.discover(start, pattern=n) for n in only)
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
