"""Checks that the Auth and Firestore emulators sit behind the `ui` job (M1-02, #254).

  * firebase.json starts the `auth` and `firestore` emulators, on the host and ports FirebaseEmulator.kt (the :core:data
    androidTest helper) connects to, and the helper's project is a `demo-` one,
  * ci.yml `ui` job: installs the Firebase CLI (`npm ci` in firebase/) and runs `:app:connectedDebugAndroidTest` and
    `:core:data:connectedDebugAndroidTest` inside `firebase emulators:exec --only auth,firestore --project demo-tally`;
    no step is skippable (`if:`, the job is a required check) and no failure is swallowed (`|| true`, `continue-on-error`),
  * verify.sh runs this check and its tests, and compiles the :core:data androidTest sources; ci.yml `tasks` runs both,
  * :core:data has :core:testing on its unit-test classpath (#217 item 3) and a smoke test that talks to the emulators.
Run: python3 -I scripts/check_ui_emulators.py  (exit 1 and one line per problem).
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = "core/data/src/androidTest/kotlin/dk/bjarkebjarke/tally/data/FirebaseEmulator.kt"
SMOKE = "core/data/src/androidTest/kotlin/dk/bjarkebjarke/tally/data/EmulatorSmokeTest.kt"
TESTS_CMD = "python3 -I scripts/test_check_ui_emulators.py"
CHECK_CMD = "python3 -I scripts/check_ui_emulators.py"
VERIFY_STEPS = (f"step ui-emulators-tests {TESTS_CMD}", f"step ui-emulators {CHECK_CMD}")
EXEC = "firebase emulators:exec --only auth,firestore --project demo-tally"
UI_TASKS = (":app:connectedDebugAndroidTest", ":core:data:connectedDebugAndroidTest")
DATA_COMPILE = ":core:data:assembleDebugAndroidTest"
CLASSPATH = 'testImplementation(project(":core:testing"))'
SWALLOWED = re.compile(r"\|\|\s*(?:true|:)|continue-on-error")


def _active_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _job(ci, job):
    """One job of ci.yml: its text, or an empty string."""
    m = re.search(rf"^  {job}:\n(.*?)(?=^  [A-Za-z][\w-]*:[ \t]*$|\Z)", ci, re.S | re.M)
    return m.group(1) if m else ""


def _steps(job_text):
    return re.split(r"(?m)^      - ", job_text)[1:]


def _constant(text, name):
    m = re.search(rf"const val {name} = (\"[^\"]*\"|\d+)", text)
    return m.group(1).strip('"') if m else None


def firebase_problems(root):
    problems = []
    config = json.loads((root / "firebase/firebase.json").read_text()).get("emulators", {})
    helper = (root / HELPER).read_text()
    for emulator, constant in (("auth", "AUTH_PORT"), ("firestore", "FIRESTORE_PORT")):
        entry = config.get(emulator)
        if not isinstance(entry, dict) or not entry.get("host") or not isinstance(entry.get("port"), int):
            problems.append(f"firebase.json has no emulators.{emulator} entry with a host and a port")
        elif str(entry["port"]) != _constant(helper, constant):
            problems.append(
                f"firebase.json emulators.{emulator} port {entry['port']} differs from {constant} {_constant(helper, constant)} in FirebaseEmulator.kt"
            )
    if not (_constant(helper, "PROJECT_ID") or "").startswith("demo-tally"):
        problems.append("FirebaseEmulator.kt PROJECT_ID must be demo-tally (a demo- project never reaches the real Firebase)")
    return problems


def ui_problems(root):
    ui = _job((root / ".github/workflows/ci.yml").read_text(), "ui")
    steps = _steps(ui)
    inside = [ln for s in steps for ln in _active_lines(s) if EXEC in ln and ln.count('"') >= 2]
    problems = []
    quoted = [ln.split('"')[1] for ln in inside if len(ln.split('"')) > 2]
    if not inside:
        problems.append(f"ci.yml ui job does not run its tests inside `{EXEC}`")
    problems += [f"ci.yml ui job does not run {task} inside the emulators" for task in UI_TASKS if inside and not any(task in q for q in quoted)]
    if not any(re.search(r"working-directory:\s*firebase\b", s) and re.search(r"run:\s*npm ci\b", s) for s in steps):
        problems.append("ci.yml ui job has no `npm ci` step in firebase/ (the emulators come from firebase-tools)")
    if any(SWALLOWED.search(ln) for ln in _active_lines(ui)):
        problems.append("ci.yml ui job swallows a test failure (`|| true`, `continue-on-error`)")
    if any(ln.startswith(("if:", "- if:")) for ln in _active_lines(ui)):
        problems.append("ci.yml ui job has a step with `if:` (the job is a required check)")
    return problems


def wiring_problems(root):
    verify = _active_lines((root / "scripts/verify.sh").read_text())
    problems = [f"verify.sh has no active step: {want}" for want in VERIFY_STEPS if want not in verify]
    if not any(ln.startswith("step build ") and DATA_COMPILE in ln.split() for ln in verify):
        problems.append(f"verify.sh build step does not compile {DATA_COMPILE}")
    tasks = _steps(_job((root / ".github/workflows/ci.yml").read_text(), "tasks"))
    for cmd in (TESTS_CMD, CHECK_CMD):
        if not any(ln.removeprefix("- ") == f"run: {cmd}" for s in tasks for ln in _active_lines(s)):
            problems.append(f"ci.yml tasks job has no step running: {cmd}")
    return problems


def data_module_problems(root):
    problems = []
    if CLASSPATH not in (root / "core/data/build.gradle.kts").read_text():
        problems.append(f":core:data must have {CLASSPATH} (#217 item 3)")
    smoke = (root / SMOKE).read_text() if (root / SMOKE).is_file() else ""
    if "@Test" not in smoke or "FirebaseEmulator.requireRunning()" not in smoke:
        problems.append("core/data androidTest has no @Test that talks to the emulators (EmulatorSmokeTest)")
    return problems


def problems(root=ROOT):
    root = Path(root)
    return firebase_problems(root) + ui_problems(root) + wiring_problems(root) + data_module_problems(root)


def main(root=ROOT):
    found = problems(root)
    for p in found:
        print(f"check_ui_emulators: {p}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
