"""Checks that the Auth and Firestore emulators sit behind the `ui` job (M1-02, #254).

  * firebase.json starts both emulators on the ports FirebaseEmulator.kt (the :core:data androidTest helper) uses, for a `demo-` project,
  * ci.yml `ui` job: the parsed job equals one frozen mapping (EXPECTED_UI), which runs the `:app` and `:core:data` connected tests inside
    `firebase emulators:exec --only auth,firestore --project demo-tally`. Any other key, step, flag, `if`, `needs` or fallback fails,
  * verify.sh and the CI `tasks` job run this check and its tests; verify.sh compiles the :core:data androidTest sources,
  * :core:data has :core:testing and the JUnit Platform on its unit tests (#217 item 3) and a smoke test using the emulators.
Run: python3 -I scripts/check_ui_emulators.py  (exit 1 and one line per problem).
"""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HELPER = "core/data/src/androidTest/kotlin/dk/bjarkebjarke/tally/data/FirebaseEmulator.kt"
SMOKE = "core/data/src/androidTest/kotlin/dk/bjarkebjarke/tally/data/EmulatorSmokeTest.kt"
TESTS_CMD = "python3 -I scripts/test_check_ui_emulators.py"
CHECK_CMD = "python3 -I scripts/check_ui_emulators.py"
VERIFY_STEPS = (f"step ui-emulators-tests {TESTS_CMD}", f"step ui-emulators {CHECK_CMD}")
# The whole ui job, frozen (R1-01, R2-01, R2-02, R3-01): an allowlist fails closed where a deny list (--dry-run, -x, `; true`, pipes,
# other actions, extra steps, a quoted `"if": false`, `needs`) can always be bypassed. Changing the ui job changes this mapping, in the
# same PR. The fallback after gradle prints the result XML, which Gradle's log lacks.
EXPECTED_UI = {
    "name": "ui",
    "runs-on": "ubuntu-latest",
    "timeout-minutes": 45,
    "steps": [
        {"uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "with": {"persist-credentials": False}},
        {"uses": "actions/setup-java@d1374f8ac74474200d16ef8ecee22c7ae7a51880", "with": {"distribution": "temurin", "java-version": 21}},
        {"uses": "gradle/actions/setup-gradle@8da46b539cd8fe6ab27ca75128919a18d757604c"},
        {
            "uses": "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
            "with": {"node-version": 22, "cache": "npm", "cache-dependency-path": "firebase/package-lock.json"},
        },
        {
            "name": "install the Firebase CLI (the Auth and Firestore emulators the data-layer tests run against)",
            "working-directory": "firebase",
            "run": "npm ci --ignore-scripts --silent",
        },
        {
            "name": "enable KVM",
            "run": "echo 'KERNEL==\"kvm\", GROUP=\"kvm\", MODE=\"0666\", OPTIONS+=\"static_node=kvm\"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules\n"
            "sudo udevadm control --reload-rules\nsudo udevadm trigger --name-match=kvm\n",
        },
        {
            "uses": "reactivecircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d",
            "with": {
                "api-level": 34,
                "arch": "x86_64",
                "target": "google_apis",
                "script": "cd firebase && npx --no-install firebase emulators:exec --only auth,firestore --project demo-tally "
                '"cd .. && ./gradlew --console=plain :app:connectedDebugAndroidTest :core:data:connectedDebugAndroidTest '
                "|| (find core/data/build/outputs -name '*.xml' -print -exec head -c 7000 {} \\\\; ; false)\"",
            },
        },
    ],
}
UI_PROBLEM = "ci.yml jobs.ui (parsed) is not equal to EXPECTED_UI in check_ui_emulators.py"
DATA_COMPILE = ":core:data:assembleDebugAndroidTest"
CLASSPATH = 'testImplementation(project(":core:testing"))'


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
    jobs = (yaml.safe_load((root / ".github/workflows/ci.yml").read_text()) or {}).get("jobs") or {}
    return [] if jobs.get("ui") == EXPECTED_UI else [UI_PROBLEM]


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
    build = (root / "core/data/build.gradle.kts").read_text()
    if CLASSPATH not in build:
        problems.append(f":core:data must have {CLASSPATH} (#217 item 3)")
    smoke = (root / SMOKE).read_text() if (root / SMOKE).is_file() else ""
    if not re.search(r"(?m)^\s*unitTests\.all \{ it\.useJUnitPlatform\(\) \}\s*$", build):
        problems.append(
            ":core:data must run its unit tests on the JUnit Platform (unitTests.all { it.useJUnitPlatform() }), "
            "or the :core:testing network block never installs (#217 item 3)"
        )
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
