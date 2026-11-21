"""Checks that the screenshot gate (M1-03) is wired into verify.sh and CI.

  * verify.sh runs the gate's tests, this check and `scripts/screenshots.sh verify` as active steps,
  * ci.yml: the `tasks` job runs the tests and this check; the `screenshots` job runs the gate, then uploads the Roborazzi
    diffs when a step failed (a pinned actions/upload-artifact step after the gate), and the gate step cannot be allowed
    to fail. It is its own job because test_ci_scope.py forbids `if:` in the jobs that are required checks.
Run: python3 -I scripts/check_screenshots.py  (exit 1 and one line per problem).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_CMD = "python3 -I scripts/test_screenshots.py"
CHECK_CMD = "python3 -I scripts/check_screenshots.py"
GATE_CMD = "./scripts/screenshots.sh verify"
VERIFY_STEPS = (f"step screenshots-tests {TESTS_CMD}", f"step screenshots-wiring {CHECK_CMD}", f"step screenshots {GATE_CMD}")
DIFF_PATH = "app/build/outputs/roborazzi"
PINNED = re.compile(r"uses:\s*actions/upload-artifact@[0-9a-f]{40}(?:\s|$)")


def _active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _job_steps(ci, job):
    """One job of ci.yml as a list of step texts."""
    m = re.search(rf"^  {job}:\n(.*?)(?=^  [A-Za-z][\w-]*:[ \t]*$|\Z)", ci, re.S | re.M)
    if m is None:
        return []
    return [s for s in re.split(r"(?m)^      - ", m.group(1))[1:]]


def _runs(step, command):
    return any(ln.removeprefix("- ") == f"run: {command}" for ln in _active_lines(step))


def wiring_problems(root):
    root = Path(root)
    problems = []
    verify = _active_lines((root / "scripts/verify.sh").read_text())
    problems += [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in verify]

    ci = (root / ".github/workflows/ci.yml").read_text()
    for job, cmds in (("tasks", (TESTS_CMD, CHECK_CMD)), ("screenshots", (GATE_CMD,))):
        steps = _job_steps(ci, job)
        problems += [f"ci.yml {job} job has no step running: {cmd}" for cmd in cmds if not any(_runs(s, cmd) for s in steps)]
    steps = _job_steps(ci, "screenshots")
    gate = next((i for i, s in enumerate(steps) if _runs(s, GATE_CMD)), None)
    if gate is not None and "continue-on-error" in steps[gate]:
        problems.append("ci.yml screenshot gate step has continue-on-error")

    upload = next((i for i, s in enumerate(steps) if "uses: actions/upload-artifact@" in s), None)
    if upload is None:
        problems.append("ci.yml screenshots job has no actions/upload-artifact step")
        return problems
    step = steps[upload]
    lines = _active_lines(step)
    if not PINNED.search(step):
        problems.append("ci.yml upload-artifact must be pinned to a 40-character commit SHA")
    if "if: failure()" not in lines:
        problems.append("ci.yml screenshot-diffs upload must have if: failure()")
    if f"path: {DIFF_PATH}" not in lines:
        problems.append(f"ci.yml screenshot-diffs upload must have path: {DIFF_PATH}")
    if gate is not None and upload < gate:
        problems.append("ci.yml screenshot-diffs upload must come after the screenshot gate step")
    return problems


def main():
    problems = wiring_problems(ROOT)
    for p in problems:
        print(f"check_screenshots: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
