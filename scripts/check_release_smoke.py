"""Checks the release smoke build with R8 in CI (M1-33, best-practices checklist follow-up 7).

  * ci.yml `release-smoke` job: the parsed job equals one frozen mapping (EXPECTED_JOB): it builds `:app:assembleRelease` with
    `-Ptally.allowStandInRelease=true` (no google-services.json in CI, so the demo-tally stand-in; M1-30), then checks that R8 wrote its
    mapping file and that the APK is unsigned. No signing key, no secret, no upload. Any other key, step, flag, `if` or `needs` fails,
  * the opt-in flag appears in no other ci.yml job, no workflow-level key of ci.yml (env reaches every job), no other workflow, no local
    composite action (.github/actions), no shell script under scripts/ (verify.sh, screenshots.sh, ...) and not in the root
    gradle.properties: any other release build must still fail (tested by scripts/test_google_services_release_gate.py),
  * the release build type keeps `isMinifyEnabled = true`, or the smoke build would not run R8,
  * verify.sh and the CI `tasks` job run this check and its tests.
Run: python3 -I scripts/check_release_smoke.py  (exit 1 and one line per problem).
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TESTS_CMD = "python3 -I scripts/test_check_release_smoke.py"
CHECK_CMD = "python3 -I scripts/check_release_smoke.py"
VERIFY_STEPS = (f"step release-smoke-tests {TESTS_CMD}", f"step release-smoke {CHECK_CMD}")
FLAG = "allowStandInRelease"
JOB = "release-smoke"
# The whole job, frozen like the `ui` job in check_ui_emulators.py: an allowlist fails closed where a deny list (--dry-run, -x, `; true`,
# an upload, a signing secret, a quoted `"if": false`) can always be bypassed. Changing the job changes this mapping, in the same PR.
EXPECTED_JOB = {
    "name": "release-smoke",
    "runs-on": "ubuntu-latest",
    "timeout-minutes": 30,
    "steps": [
        {"uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "with": {"persist-credentials": False}},
        {"uses": "actions/setup-java@d1374f8ac74474200d16ef8ecee22c7ae7a51880", "with": {"distribution": "temurin", "java-version": 21}},
        {"uses": "gradle/actions/setup-gradle@8da46b539cd8fe6ab27ca75128919a18d757604c"},
        {
            "name": "release build with R8 (demo-tally stand-in config, unsigned; the one build that may pass the stand-in flag, M1-33)",
            "run": "./gradlew -q --console=plain -Ptally.allowStandInRelease=true :app:assembleRelease",
        },
        {
            "name": "R8 ran (mapping file) and the APK is unsigned (nothing is signed, published or uploaded)",
            "run": "test -s app/build/outputs/mapping/release/mapping.txt\nls app/build/outputs/apk/release/*-release-unsigned.apk\n",
        },
    ],
}
JOB_PROBLEM = "ci.yml jobs.release-smoke (parsed) is not equal to EXPECTED_JOB in check_release_smoke.py"
MINIFY_PROBLEM = "app/build.gradle.kts: the release build type must set isMinifyEnabled = true, or the smoke build does not run R8"


def flag_problem(where):
    return f"-Ptally.{FLAG}=true (the CI smoke build's opt-in, M1-33) appears outside the release-smoke job: {where}"


def _active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _has_flag(text):
    return any(FLAG in ln for ln in _active_lines(text))


def _ci(root):
    return yaml.safe_load((root / ".github/workflows/ci.yml").read_text()) or {}


def _jobs(root):
    return _ci(root).get("jobs") or {}


def job_problems(root):
    return [] if _jobs(root).get(JOB) == EXPECTED_JOB else [JOB_PROBLEM]


def flag_problems(root):
    """Every place that could pass the stand-in opt-in to a release build other than the frozen job."""
    found = [f"ci.yml job {name}" for name, job in _jobs(root).items() if name != JOB and FLAG in json.dumps(job)]
    if FLAG in json.dumps({key: value for key, value in _ci(root).items() if key != "jobs"}):
        found.append("ci.yml workflow-level keys")
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        if path.name != "ci.yml" and _has_flag(path.read_text()):
            found.append(path.name)
    for path in sorted((root / ".github/actions").rglob("*.y*ml")):  # local composite actions run inside whichever job uses them
        if _has_flag(path.read_text()):
            found.append(path.relative_to(root).as_posix())
    files = sorted((root / "scripts").rglob("*.sh")) + [root / "gradle.properties"]
    for path in files:
        if path.is_file() and _has_flag(path.read_text()):
            found.append(path.relative_to(root).as_posix())
    return [flag_problem(where) for where in found]


def minify_problems(root):
    build = (root / "app/build.gradle.kts").read_text()
    m = re.search(r"(?m)^        release \{\n(.*?)^        \}\n", build, re.S)
    ok = m is not None and re.search(r"(?m)^\s*isMinifyEnabled = true\s*$", m.group(1)) is not None
    return [] if ok else [MINIFY_PROBLEM]


def _tasks_steps(root):
    text = (root / ".github/workflows/ci.yml").read_text()
    m = re.search(r"^  tasks:\n(.*?)(?=^  [A-Za-z][\w-]*:[ \t]*$|\Z)", text, re.S | re.M)
    return re.split(r"(?m)^      - ", m.group(1))[1:] if m else []


def wiring_problems(root):
    verify = _active_lines((root / "scripts/verify.sh").read_text())
    problems = [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in verify]
    tasks = _tasks_steps(root)
    for cmd in (TESTS_CMD, CHECK_CMD):
        if not any(ln.removeprefix("- ") == f"run: {cmd}" for s in tasks for ln in _active_lines(s)):
            problems.append(f"ci.yml tasks job has no step running: {cmd}")
    return problems


def problems(root=ROOT):
    root = Path(root)
    return job_problems(root) + flag_problems(root) + minify_problems(root) + wiring_problems(root)


def main(root=ROOT):
    found = problems(root)
    for p in found:
        print(f"check_release_smoke: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
