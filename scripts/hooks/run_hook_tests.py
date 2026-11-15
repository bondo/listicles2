"""Runs the hook test suite and fails when any test was skipped (R12-04, #28).

Usage: python3 -I scripts/hooks/run_hook_tests.py [start_dir]   (default: the directory of this script)

The suite is a CI gate, so a skipped test is a failure however the skip was written (`import unittest as ut` + `@ut.skip`,
a call form, `self.skipTest`). The check reads the run's result, not the source text. Expected failures and unexpected
successes count too, and so does a run that finds no tests.
"""

import os
import sys
import unittest


def main(argv):
    start = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    suite = unittest.TestLoader().discover(start)
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
